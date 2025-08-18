import logging
from typing import Optional, Dict, Any, Tuple, Callable
import numpy as np
import threading
import time

# Try to import WhisperX, fall back to mock if not available
try:
    import torch
    import whisperx
    WHISPERX_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("WhisperX library loaded successfully")
except ImportError:
    from . import mock_whisperx as whisperx
    WHISPERX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("WhisperX not available, using mock implementation for testing")

    # Mock torch for device detection
    class MockTorch:
        class cuda:
            @staticmethod
            def is_available():
                return False
            @staticmethod
            def empty_cache():
                pass
            @staticmethod
            def memory_allocated(device=0):
                return 0
            @staticmethod
            def memory_reserved(device=0):
                return 0
            @staticmethod
            def get_device_name(device=0):
                return "Mock GPU"
    torch = MockTorch()


class WhisperXEngine:
    def __init__(
        self,
        model_size: str = "base",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        language: str = "en",
        enable_diarization: bool = False,
        hf_token: Optional[str] = None
    ):
        self.model_size = model_size
        self.language = language
        self.enable_diarization = enable_diarization
        self.hf_token = hf_token
        self.cuda_fallback = False  # Track if we've fallen back from CUDA error
        self.original_device = None  # Store original device choice

        # Auto-detect device
        if device is None or device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.original_device = self.device  # Store original choice

        # Auto-select compute type based on device
        if compute_type is None:
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        else:
            self.compute_type = compute_type

        self.model = None
        self.align_model = None
        self.metadata = None
        self.diarize_model = None

        # Progress tracking
        self.loading_progress = 0
        self.loading_status = "Not loaded"
        self.progress_callback = None
        self.loading_thread = None
        self.loading_cancelled = False

        # Model fallback support
        self.available_models = ["tiny", "tiny.en", "base", "base.en", "small", "small.en"]
        self.fallback_model = "base"  # Safe fallback model

        logger.info(f"WhisperX Engine initialized: device={self.device}, compute_type={self.compute_type}")

    def load_models(self, progress_callback: Optional[Callable[[str, int], None]] = None, timeout: Optional[float] = 300) -> None:
        """Load models with progress tracking and timeout support.

        Args:
            progress_callback: Function to call with (status_text, progress_percent) updates
            timeout: Timeout in seconds (default: 5 minutes)
        """
        self.progress_callback = progress_callback
        self.loading_cancelled = False

        if timeout and timeout > 0:
            # Load with timeout in separate thread
            self.loading_thread = threading.Thread(target=self._load_models_with_timeout, args=(timeout,))
            self.loading_thread.daemon = True
            self.loading_thread.start()
            self.loading_thread.join(timeout)

            if self.loading_thread.is_alive():
                self.loading_cancelled = True
                logger.warning(f"Model loading timed out after {timeout}s, attempting fallback")
                self._update_progress("Loading timed out, trying fallback...", 0)

                # Try fallback model
                if self.model_size != self.fallback_model:
                    logger.info(f"Falling back to {self.fallback_model} model")
                    original_model = self.model_size
                    self.model_size = self.fallback_model

                    try:
                        self._load_models_sync()
                        logger.info(f"Successfully loaded fallback model: {self.fallback_model}")
                        self._update_progress(f"Loaded {self.fallback_model} (fallback)", 100)
                        return
                    except Exception as fallback_error:
                        logger.error(f"Fallback model loading failed: {fallback_error}")
                        self.model_size = original_model
                        raise TimeoutError(f"Model loading timed out after {timeout}s and fallback failed")
                else:
                    raise TimeoutError(f"Model loading timed out after {timeout}s")
        else:
            # Load synchronously without timeout
            self._load_models_sync()

    def _load_models_with_timeout(self, timeout: float):
        """Load models in a separate thread for timeout handling."""
        try:
            self._load_models_sync()
        except Exception as e:
            if not self.loading_cancelled:
                logger.error(f"Model loading failed: {e}")
                raise

    def _load_models_sync(self):
        """Synchronous model loading with progress updates."""
        try:
            self._update_progress("Loading transcription model...", 10)

            # Load main transcription model
            logger.info(f"Loading WhisperX model: {self.model_size}")
            self.model = whisperx.load_model(
                self.model_size,
                self.device,
                compute_type=self.compute_type,
                language=self.language
            )

            if self.loading_cancelled:
                return

            self._update_progress("Loading alignment model...", 50)

            # Load alignment model for word-level timestamps
            logger.info(f"Loading alignment model for language: {self.language}")
            self.align_model, self.metadata = whisperx.load_align_model(
                language_code=self.language,
                device=self.device
            )

            if self.loading_cancelled:
                return

            self._update_progress("Loading diarization model...", 80)

            # Optionally load diarization model
            if self.enable_diarization and self.hf_token:
                logger.info("Loading diarization model")
                self.diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=self.hf_token,
                    device=self.device
                )

            self._update_progress("Models loaded successfully", 100)
            logger.info("All models loaded successfully")

        except Exception as e:
            if not self.loading_cancelled:
                logger.error(f"Failed to load models: {e}")
                self._update_progress(f"Loading failed: {str(e)}", 0)
                raise

    def _update_progress(self, status: str, progress: int):
        """Update loading progress and status."""
        self.loading_status = status
        self.loading_progress = progress
        if self.progress_callback and not self.loading_cancelled:
            self.progress_callback(status, progress)

    def cancel_loading(self):
        """Cancel ongoing model loading."""
        self.loading_cancelled = True
        logger.info("Model loading cancelled by user")

    def is_loading(self) -> bool:
        """Check if models are currently loading."""
        return self.loading_thread is not None and self.loading_thread.is_alive()

    def get_loading_progress(self) -> Tuple[str, int]:
        """Get current loading status and progress percentage."""
        return self.loading_status, self.loading_progress

    def transcribe(
        self,
        audio: np.ndarray,
        batch_size: int = 16,
        language: Optional[str] = None,
        suppress_numerals: bool = False
    ) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Models not loaded. Call load_models() first.")

        try:
            # Clear GPU cache if available
            if self.device == "cuda":
                torch.cuda.empty_cache()

            # Transcribe audio
            transcribe_kwargs = {
                "batch_size": batch_size,
                "language": language or self.language
            }
            # Only add suppress_numerals if supported (not in faster-whisper)
            if not WHISPERX_AVAILABLE:
                transcribe_kwargs["suppress_numerals"] = suppress_numerals

            result = self.model.transcribe(
                audio,
                **transcribe_kwargs
            )

            # Align for word-level timestamps
            if self.align_model:
                result = whisperx.align(
                    result["segments"],
                    self.align_model,
                    self.metadata,
                    audio,
                    self.device,
                    return_char_alignments=False
                )

            # Apply speaker diarization if enabled
            if self.enable_diarization and self.diarize_model:
                diarize_segments = self.diarize_model(audio)
                result = whisperx.assign_word_speakers(
                    diarize_segments,
                    result
                )

            return result

        except Exception as e:
            # Check if this is a CUDA error that might be from suspend/resume
            error_msg = str(e)
            if "CUDA" in error_msg and ("launch failure" in error_msg or "invalid device context" in error_msg):
                logger.warning(f"CUDA error detected (likely from suspend/resume): {e}")
                logger.info("Attempting to recover by reloading models...")

                # Try to recover by reloading models
                try:
                    self._recover_from_cuda_error()

                    # Retry transcription
                    logger.info("Retrying transcription after CUDA recovery...")
                    result = self.model.transcribe(
                        audio,
                        **transcribe_kwargs
                    )

                    # Align for word-level timestamps
                    if self.align_model:
                        result = whisperx.align(
                            result["segments"],
                            self.align_model,
                            self.metadata,
                            audio,
                            self.device,
                            return_char_alignments=False
                        )

                    # Apply speaker diarization if enabled
                    if self.enable_diarization and self.diarize_model:
                        diarize_segments = self.diarize_model(audio)
                        result = whisperx.assign_word_speakers(
                            diarize_segments,
                            result
                        )

                    logger.info("Successfully recovered from CUDA error")
                    self.cuda_fallback = True  # Mark that we're in fallback mode
                    return result

                except Exception as recovery_error:
                    logger.error(f"Failed to recover from CUDA error: {recovery_error}")
                    self.cuda_fallback = True  # Mark fallback even if recovery had issues
                    raise e
            else:
                logger.error(f"Transcription failed: {e}")
                raise

    def transcribe_with_timing(
        self,
        audio: np.ndarray,
        **kwargs
    ) -> Tuple[Dict[str, Any], float]:
        start_time = time.time()
        result = self.transcribe(audio, **kwargs)
        processing_time = time.time() - start_time
        return result, processing_time

    def cleanup(self) -> None:
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def _recover_from_cuda_error(self) -> None:
        """Recover from CUDA errors by clearing memory and reloading models."""
        try:
            # Clear existing models from memory
            self.model = None
            self.align_model = None
            self.diarize_model = None
            self.metadata = None

            # Clear CUDA cache and reset if available
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

                # Some CUDA errors require a full reset
                # This is a more aggressive approach for suspend/resume issues
                import gc
                gc.collect()
                torch.cuda.empty_cache()

            # Reload all models
            logger.info("Reloading models after CUDA error...")
            self.load_models()

        except Exception as e:
            logger.error(f"Error during CUDA recovery: {e}")
            # If recovery fails, try falling back to CPU
            if self.device == "cuda":
                logger.warning("Failed to recover on CUDA, attempting to fall back to CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
                self.cuda_fallback = True  # Mark that we're in fallback mode
                self.load_models()

    def change_model(self, model_size: str, progress_callback: Optional[Callable[[str, int], None]] = None, timeout: Optional[float] = 300) -> None:
        """Change the model with progress tracking and timeout support."""
        self.model_size = model_size
        self.model = None
        self.align_model = None
        self.diarize_model = None
        self.metadata = None
        self.load_models(progress_callback, timeout)

    def format_result(self, result: Dict[str, Any]) -> str:
        segments = result.get("segments", [])

        if not segments:
            return ""

        # Check if we have speaker information
        has_speakers = any("speaker" in seg for seg in segments)

        if has_speakers:
            # Format with speaker labels
            formatted = []
            current_speaker = None
            for segment in segments:
                speaker = segment.get("speaker", "Unknown")
                text = segment.get("text", "").strip()

                if speaker != current_speaker:
                    if formatted:
                        formatted.append("")
                    formatted.append(f"[{speaker}]: {text}")
                    current_speaker = speaker
                else:
                    formatted.append(f"          {text}")

            return "\n".join(formatted)
        else:
            # Simple format without speakers
            return " ".join(seg.get("text", "").strip() for seg in segments)

    def get_device_info(self) -> Dict[str, Any]:
        info = {
            "device": self.device,
            "compute_type": self.compute_type,
            "model_size": self.model_size,
            "language": self.language,
            "models_loaded": self.model is not None,
            "cuda_fallback": self.cuda_fallback,
            "original_device": self.original_device
        }

        if self.device == "cuda":
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_allocated"] = f"{torch.cuda.memory_allocated(0) / 1024**3:.2f} GB"
                info["gpu_memory_reserved"] = f"{torch.cuda.memory_reserved(0) / 1024**3:.2f} GB"

        return info
