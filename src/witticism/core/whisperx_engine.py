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
    logger.info("[WHISPERX_ENGINE] LIBRARY_LOADED: WhisperX library loaded successfully")
except ImportError:
    from . import mock_whisperx as whisperx
    WHISPERX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("[WHISPERX_ENGINE] MOCK_MODE: WhisperX not available, using mock implementation for testing")

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
        self.original_device_setting = device  # Store original user setting (could be "auto", "cuda", "cpu")

        # Auto-detect device
        if device is None or device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.original_device = self.device  # Store original detected/chosen device

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

        # Sleep monitoring
        self.sleep_monitor = None
        self.suspend_recovery_attempts = 0
        self._suspend_state = None  # Store model state during suspend
        self.resume_validation_attempts = 0
        self.suspend_resume_callback = None  # Callback for suspend/resume events

        # Startup CUDA health tracking
        self.startup_cuda_fixed = False

        logger.info(f"[WHISPERX_ENGINE] INIT: device={self.device}, compute_type={self.compute_type}, model_size={self.model_size}, language={self.language}")

    def validate_and_clean_cuda_at_startup(self) -> bool:
        """Validate CUDA health at startup and perform nuclear cleanup if corrupted.

        Returns:
            bool: True if CUDA is healthy or successfully cleaned, False if should force CPU mode
        """
        if self.device != "cuda" or not torch.cuda.is_available():
            return True  # Not using CUDA, no validation needed

        try:
            logger.info("[WHISPERX_ENGINE] CUDA_HEALTH_CHECK: Performing startup CUDA health validation")

            # Test if CUDA context is healthy with minimal operation
            test_tensor = torch.tensor([1.0], device='cuda')
            test_result = test_tensor * 2
            del test_tensor, test_result
            torch.cuda.empty_cache()

            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            memory_allocated = torch.cuda.memory_allocated(0) / 1024**3 if torch.cuda.is_available() else 0
            logger.info(f"[WHISPERX_ENGINE] CUDA_HEALTHY: startup validation passed - gpu={gpu_name}, memory={memory_allocated:.2f}GB")
            return True

        except Exception as e:
            logger.warning(f"[WHISPERX_ENGINE] CUDA_CORRUPTED: startup validation failed - error='{e}'")
            logger.warning("[WHISPERX_ENGINE] CUDA_RECOVERY: performing EMERGENCY startup cleanup")

            try:
                # Perform the same nuclear cleanup as suspend handler
                self._nuclear_cuda_startup_cleanup()

                # Test again after cleanup
                test_tensor = torch.tensor([1.0], device='cuda')
                del test_tensor
                torch.cuda.empty_cache()

                logger.info("[WHISPERX_ENGINE] CUDA_RECOVERED: startup cleanup successful - context restored")
                self.startup_cuda_fixed = True
                return True

            except Exception as cleanup_error:
                logger.error(f"[WHISPERX_ENGINE] CUDA_RECOVERY_FAILED: startup cleanup failed - error='{cleanup_error}'")
                logger.warning("[WHISPERX_ENGINE] CUDA_FALLBACK: forcing CPU mode due to irrecoverable corruption")
                return False

    def _nuclear_cuda_startup_cleanup(self):
        """Nuclear CUDA cleanup identical to suspend handler but for startup"""
        try:
            if torch.cuda.is_available():
                logger.debug("[WHISPERX_ENGINE] CUDA_CLEANUP: performing nuclear cleanup at startup")

                # Force PyTorch to release all CUDA memory allocations
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()

                # Additional aggressive cleanup
                torch.cuda.ipc_collect()

                logger.debug("[WHISPERX_ENGINE] CUDA_CLEANUP: nuclear cleanup completed")

        except Exception as e:
            logger.warning(f"[WHISPERX_ENGINE] CLEANUP_ERROR: nuclear CUDA cleanup error (continuing) - {e}")

        # Force garbage collection multiple times
        import gc
        for _ in range(3):
            gc.collect()

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
                logger.warning(f"[WHISPERX_ENGINE] LOADING_TIMEOUT: model loading timed out after {timeout}s, attempting fallback")
                self._update_progress("Loading timed out, trying fallback...", 0)

                # Try fallback model
                if self.model_size != self.fallback_model:
                    logger.info(f"[WHISPERX_ENGINE] MODEL_FALLBACK: falling back to {self.fallback_model} model")
                    original_model = self.model_size
                    self.model_size = self.fallback_model

                    try:
                        self._load_models_sync()
                        logger.info(f"[WHISPERX_ENGINE] FALLBACK_SUCCESS: successfully loaded fallback model '{self.fallback_model}'")
                        self._update_progress(f"Loaded {self.fallback_model} (fallback)", 100)
                        return
                    except Exception as fallback_error:
                        logger.error(f"[WHISPERX_ENGINE] FALLBACK_FAILED: fallback model loading failed - {fallback_error}")
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
                logger.error(f"[WHISPERX_ENGINE] LOADING_FAILED: model loading failed - {e}")
                raise

    def _load_models_sync(self):
        """Synchronous model loading with progress updates."""
        try:
            self._update_progress("Loading transcription model...", 10)

            # Load main transcription model
            start_time = time.time()
            logger.info(f"[WHISPERX_ENGINE] MODEL_LOADING: transcription model '{self.model_size}' on {self.device} with {self.compute_type}")
            self.model = whisperx.load_model(
                self.model_size,
                self.device,
                compute_type=self.compute_type,
                language=self.language
            )
            load_time = time.time() - start_time
            logger.info(f"[WHISPERX_ENGINE] MODEL_LOADED: transcription model loaded in {load_time:.2f}s")

            if self.loading_cancelled:
                return

            self._update_progress("Loading alignment model...", 50)

            # Load alignment model for word-level timestamps
            start_time = time.time()
            logger.info(f"[WHISPERX_ENGINE] ALIGN_MODEL_LOADING: alignment model for language '{self.language}' on {self.device}")
            self.align_model, self.metadata = whisperx.load_align_model(
                language_code=self.language,
                device=self.device
            )
            align_load_time = time.time() - start_time
            logger.info(f"[WHISPERX_ENGINE] ALIGN_MODEL_LOADED: alignment model loaded in {align_load_time:.2f}s")

            if self.loading_cancelled:
                return

            self._update_progress("Loading diarization model...", 80)

            # Optionally load diarization model
            if self.enable_diarization and self.hf_token:
                start_time = time.time()
                logger.info(f"[WHISPERX_ENGINE] DIARIZATION_LOADING: diarization model on {self.device}")
                self.diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=self.hf_token,
                    device=self.device
                )
                diarize_load_time = time.time() - start_time
                logger.info(f"[WHISPERX_ENGINE] DIARIZATION_LOADED: diarization model loaded in {diarize_load_time:.2f}s")

            self._update_progress("Models loaded successfully", 100)
            logger.info("[WHISPERX_ENGINE] ALL_MODELS_LOADED: all models loaded successfully")

        except Exception as e:
            if not self.loading_cancelled:
                # Check if this is a CUDA initialization error
                error_msg = str(e)
                if self.device == "cuda" and ("CUDA" in error_msg and
                    ("unknown error" in error_msg or "failed with error" in error_msg or
                     "launch failure" in error_msg or "invalid device context" in error_msg)):

                    logger.warning(f"[WHISPERX_ENGINE] CUDA_ERROR: model loading failed - error='{e}'")
                    logger.info(f"[WHISPERX_ENGINE] CPU_FALLBACK: attempting to recover by switching from {self.device} to CPU")

                    # Fall back to CPU
                    self.device = "cpu"
                    self.compute_type = "int8"
                    self.cuda_fallback = True

                    # Clear any partially loaded models
                    self.model = None
                    self.align_model = None
                    self.diarize_model = None
                    self.metadata = None

                    try:
                        # Retry with CPU
                        self._update_progress("Retrying with CPU...", 10)

                        start_time = time.time()
                        logger.info(f"[WHISPERX_ENGINE] CPU_RETRY: loading transcription model '{self.model_size}' on CPU with {self.compute_type}")
                        self.model = whisperx.load_model(
                            self.model_size,
                            self.device,
                            compute_type=self.compute_type,
                            language=self.language
                        )
                        cpu_load_time = time.time() - start_time
                        logger.info(f"[WHISPERX_ENGINE] CPU_RETRY_SUCCESS: transcription model loaded in {cpu_load_time:.2f}s")

                        if self.loading_cancelled:
                            return

                        self._update_progress("Loading alignment model on CPU...", 50)

                        logger.info(f"[WHISPERX_ENGINE] CPU_ALIGN_LOADING: alignment model for language '{self.language}' on CPU")
                        self.align_model, self.metadata = whisperx.load_align_model(
                            language_code=self.language,
                            device=self.device
                        )

                        if self.loading_cancelled:
                            return

                        self._update_progress("Loading diarization model on CPU...", 80)

                        # Optionally load diarization model
                        if self.enable_diarization and self.hf_token:
                            logger.info("[WHISPERX_ENGINE] CPU_DIARIZATION_LOADING: diarization model on CPU")
                            self.diarize_model = whisperx.DiarizationPipeline(
                                use_auth_token=self.hf_token,
                                device=self.device
                            )

                        self._update_progress("Models loaded successfully (CPU mode)", 100)
                        logger.info("[WHISPERX_ENGINE] CPU_FALLBACK_SUCCESS: all models loaded successfully after CUDA fallback")
                        return

                    except Exception as cpu_error:
                        logger.error(f"[WHISPERX_ENGINE] CPU_FALLBACK_FAILED: CPU fallback also failed - error='{cpu_error}'")
                        self._update_progress("Both CUDA and CPU loading failed", 0)
                        raise cpu_error
                else:
                    logger.error(f"[WHISPERX_ENGINE] MODEL_LOADING_FAILED: failed to load models - error='{e}'")
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
        logger.info("[WHISPERX_ENGINE] LOADING_CANCELLED: model loading cancelled by user")

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
            if "CUDA" in error_msg and ("launch failure" in error_msg or "invalid device context" in error_msg or
                                       "unknown error" in error_msg or "failed with error" in error_msg):
                logger.warning(f"[WHISPERX_ENGINE] CUDA_ERROR: transcription failed (likely suspend/resume) - error='{e}'")
                logger.info("[WHISPERX_ENGINE] CUDA_RECOVERY: attempting to recover by reloading models")

                # Try to recover by reloading models
                try:
                    self._recover_from_cuda_error()

                    # Retry transcription
                    logger.info("[WHISPERX_ENGINE] TRANSCRIPTION_RETRY: retrying after CUDA recovery")
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

                    logger.info("[WHISPERX_ENGINE] CUDA_RECOVERY_SUCCESS: transcription successful after recovery")
                    self.cuda_fallback = True  # Mark that we're in fallback mode
                    return result

                except Exception as recovery_error:
                    logger.error(f"[WHISPERX_ENGINE] RECOVERY_FAILED: failed to recover from CUDA error - {recovery_error}")
                    self.cuda_fallback = True  # Mark fallback even if recovery had issues
                    raise e
            else:
                logger.error(f"[WHISPERX_ENGINE] TRANSCRIPTION_FAILED: transcription failed - {e}")
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
            logger.info("[WHISPERX_ENGINE] CUDA_RECOVERY: clearing models and resetting CUDA context")
            # Clear existing models from memory
            self.model = None
            self.align_model = None
            self.diarize_model = None
            self.metadata = None

            # Clear CUDA cache and reset if available
            if self.device == "cuda" and torch.cuda.is_available():
                logger.info("[WHISPERX_ENGINE] CUDA_CLEANUP: aggressive cleanup for suspend/resume recovery")

                # More aggressive cleanup for suspend/resume scenarios
                import gc
                gc.collect()
                torch.cuda.empty_cache()

                try:
                    # Try to reset CUDA context - this may help with suspend/resume issues
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()

                    # Force garbage collection again
                    gc.collect()

                    # Try to initialize a small tensor to test CUDA
                    test_tensor = torch.tensor([1.0], device='cuda')
                    del test_tensor
                    torch.cuda.empty_cache()

                except Exception as cuda_test_error:
                    logger.warning(f"[WHISPERX_ENGINE] CUDA_TEST_FAILED: validation after cleanup failed - error='{cuda_test_error}', will fallback to CPU")
                    raise cuda_test_error

            # Reload all models
            logger.info("[WHISPERX_ENGINE] MODEL_RELOAD: reloading models after CUDA recovery")
            self.load_models()

        except Exception as e:
            logger.error(f"[WHISPERX_ENGINE] CUDA_RECOVERY_ERROR: recovery failed - error='{e}'")
            # If recovery fails, try falling back to CPU
            if self.device == "cuda":
                logger.warning("[WHISPERX_ENGINE] CPU_FALLBACK: CUDA recovery failed, switching to CPU mode")
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
            "original_device": self.original_device,
            "original_device_setting": self.original_device_setting
        }

        if self.device == "cuda":
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_allocated"] = f"{torch.cuda.memory_allocated(0) / 1024**3:.2f} GB"
                info["gpu_memory_reserved"] = f"{torch.cuda.memory_reserved(0) / 1024**3:.2f} GB"

        return info

    def get_config_device_setting(self) -> str:
        """Get the device setting that should be saved to config.

        Returns the original user setting if we're in fallback mode,
        otherwise returns the current device.
        """
        if self.cuda_fallback and self.original_device_setting:
            # Don't save fallback device to config - preserve user's original choice
            return self.original_device_setting
        else:
            return self.device

    def enable_sleep_monitoring(self):
        """Enable proactive sleep/resume monitoring for CUDA recovery"""
        try:
            from ..platform.sleep_monitor import create_sleep_monitor

            if self.sleep_monitor is None:
                self.sleep_monitor = create_sleep_monitor(
                    on_suspend=self._on_system_suspend,
                    on_resume=self._on_system_resume
                )

                if self.sleep_monitor:
                    self.sleep_monitor.start_monitoring()
                    logger.info("Sleep monitoring enabled for proactive CUDA recovery")
                else:
                    logger.warning("Sleep monitoring not available on this platform")

        except ImportError:
            logger.warning("Sleep monitoring module not available")
        except Exception as e:
            logger.error(f"Failed to enable sleep monitoring: {e}")

    def set_suspend_resume_callback(self, callback):
        """Set callback for suspend/resume events. Callback receives (event_type, details)."""
        self.suspend_resume_callback = callback

    def disable_sleep_monitoring(self):
        """Disable sleep/resume monitoring"""
        if self.sleep_monitor:
            try:
                self.sleep_monitor.stop_monitoring()
                self.sleep_monitor = None
                logger.info("Sleep monitoring disabled")
            except Exception as e:
                logger.error(f"Failed to disable sleep monitoring: {e}")

    def _on_system_suspend(self):
        """Handle system suspend event - NUCLEAR GPU abandonment to prevent SIGABRT"""
        logger.warning(f"[WHISPERX_ENGINE] SYSTEM_SUSPEND: detected (attempt #{self.suspend_recovery_attempts + 1}) - performing EMERGENCY GPU abandonment")
        self.suspend_recovery_attempts += 1

        try:
            if self.device == "cuda" and self.is_loaded():
                # Store current state for potential restoration after resume
                self._suspend_state = {
                    'model_size': self.model_size,
                    'language': self.language,
                    'enable_diarization': self.enable_diarization,
                    'hf_token': self.hf_token,
                    'device': self.device,
                    'compute_type': self.compute_type
                }

                logger.warning(f"[WHISPERX_ENGINE] NUCLEAR_GPU_CLEANUP: destroying all models and contexts - model_size={self.model_size}, device={self.device}")

                # NUCLEAR: Complete model destruction
                if self.model:
                    try:
                        del self.model
                    except Exception as e:
                        logger.debug(f"Error deleting model: {e}")
                    finally:
                        self.model = None

                if self.align_model:
                    try:
                        del self.align_model
                    except Exception as e:
                        logger.debug(f"Error deleting align_model: {e}")
                    finally:
                        self.align_model = None

                if self.diarize_model:
                    try:
                        del self.diarize_model
                    except Exception as e:
                        logger.debug(f"Error deleting diarize_model: {e}")
                    finally:
                        self.diarize_model = None

                if self.metadata:
                    self.metadata = None

                # NUCLEAR: Force CUDA context destruction
                if torch.cuda.is_available():
                    try:
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        # Force PyTorch to release all CUDA memory allocations
                        torch.cuda.reset_peak_memory_stats()
                        # Additional aggressive cleanup
                        torch.cuda.ipc_collect()
                        logger.debug("CUDA contexts aggressively cleared")
                    except Exception as e:
                        logger.warning(f"CUDA cleanup error (continuing): {e}")

                # Force garbage collection multiple times
                import gc
                for _ in range(3):  # Multiple GC passes for thorough cleanup
                    gc.collect()

                logger.warning("[WHISPERX_ENGINE] NUCLEAR_GPU_ABANDONMENT_COMPLETE: models destroyed, contexts cleared")
            else:
                logger.debug("[WHISPERX_ENGINE] SUSPEND_SKIP: no GPU models loaded or not using CUDA - cleanup skipped")

        except Exception as e:
            logger.error(f"Error during emergency suspend cleanup: {e}")
            # Continue anyway - partial cleanup better than SIGABRT crash

    def _on_system_resume(self):
        """Handle system resume event - test CUDA health and restore models if safe"""
        logger.info(f"[WHISPERX_ENGINE] SYSTEM_RESUME: detected (attempt #{self.resume_validation_attempts + 1}) - performing CUDA health assessment")
        self.resume_validation_attempts += 1

        try:
            # Check if we have suspend state and models were unloaded
            if hasattr(self, '_suspend_state') and self._suspend_state:
                logger.info("[WHISPERX_ENGINE] SUSPEND_STATE_FOUND: testing CUDA recovery")

                # Comprehensive CUDA health test
                if self._test_cuda_health():
                    logger.info("[WHISPERX_ENGINE] CUDA_HEALTHY: after resume - initiating model restoration")

                    # Restore models in background to avoid blocking resume
                    import threading
                    restore_thread = threading.Thread(
                        target=self._restore_models_background,
                        daemon=True,
                        name="witticism-model-restore"
                    )
                    restore_thread.start()

                else:
                    logger.warning("[WHISPERX_ENGINE] CUDA_UNHEALTHY: after resume - permanent CPU fallback")
                    self._force_cpu_fallback_after_suspend()
                    self._suspend_state = None

            elif self.device == "cuda" and self.is_loaded():
                # Models are still loaded, test CUDA health
                if self._test_cuda_health():
                    logger.info("[WHISPERX_ENGINE] GPU_CONTEXT_HEALTHY: after resume")
                else:
                    logger.warning("[WHISPERX_ENGINE] GPU_CONTEXT_DAMAGED: after resume - will recover on next use")
            else:
                logger.debug("[WHISPERX_ENGINE] NO_RESTORE_NEEDED: no models to restore or not using CUDA")

        except Exception as e:
            logger.error(f"Error during resume processing: {e}")
            # Clear suspend state on error
            if hasattr(self, '_suspend_state'):
                self._suspend_state = None

    def _test_cuda_health(self) -> bool:
        """Comprehensive CUDA health check after resume - more thorough than basic validation"""
        try:
            if not torch.cuda.is_available():
                logger.debug("torch.cuda.is_available() returned False")
                return False

            # Test 1: Basic tensor operation
            test_tensor = torch.randn(100, device='cuda')
            test_tensor.sum().item()  # Force computation to test GPU
            torch.cuda.synchronize()
            del test_tensor

            # Test 2: Memory allocation and cleanup
            large_tensor = torch.zeros(1000, 1000, device='cuda')
            del large_tensor
            torch.cuda.empty_cache()

            # Test 3: Multiple GPU operations
            for _ in range(3):
                x = torch.randn(50, device='cuda')
                y = torch.randn(50, device='cuda')
                z = x @ y
                del x, y, z

            torch.cuda.synchronize()
            logger.debug("[WHISPERX_ENGINE] CUDA_HEALTH_CHECK_PASSED: GPU is fully functional")
            return True

        except Exception as e:
            logger.warning(f"[WHISPERX_ENGINE] CUDA_HEALTH_CHECK_FAILED: {e}")
            return False

    def _force_cpu_fallback_after_suspend(self):
        """Force permanent CPU mode after suspend when CUDA is damaged"""
        logger.warning("[WHISPERX_ENGINE] CPU_FALLBACK: CUDA damaged by suspend/resume - forcing permanent CPU mode")
        self.device = "cpu"
        self.compute_type = "int8"
        self.cuda_fallback = True
        # Reset any CUDA-related state
        if hasattr(self, '_suspend_state'):
            self._suspend_state = None

    def _restore_models_background(self):
        """Background method to restore models after resume - non-blocking"""
        try:
            if not hasattr(self, '_suspend_state') or not self._suspend_state:
                logger.warning("No suspend state available for model restoration")
                return

            logger.info("[WHISPERX_ENGINE] MODEL_RESTORE_START: background restoration after resume")
            suspend_state = self._suspend_state

            # Double-check CUDA health before proceeding
            if not self._test_cuda_health():
                logger.error("CUDA health deteriorated during restoration - aborting")
                self._force_cpu_fallback_after_suspend()
                return

            # Restore models with the same parameters as before suspend
            try:
                logger.info(f"[WHISPERX_ENGINE] MODEL_RESTORE: restoring WhisperX model '{suspend_state['model_size']}' on {suspend_state['device']}")

                # Load main whisper model
                self.model = whisperx.load_model(
                    suspend_state['model_size'],
                    suspend_state['device'],
                    compute_type=suspend_state['compute_type'],
                    language=suspend_state['language']
                )

                # Verify model loaded successfully
                if self.model is None:
                    raise RuntimeError("WhisperX model failed to load")

                # Load alignment model
                logger.info("Restoring alignment model")
                self.align_model, self.metadata = whisperx.load_align_model(
                    language_code=suspend_state['language'],
                    device=suspend_state['device']
                )

                # Load diarization model if enabled
                if suspend_state['enable_diarization'] and suspend_state['hf_token']:
                    logger.info("Restoring diarization model")
                    self.diarize_model = whisperx.DiarizationPipeline(
                        use_auth_token=suspend_state['hf_token'],
                        device=suspend_state['device']
                    )

                # Final health check with restored models
                if self._test_cuda_health():
                    logger.info("[WHISPERX_ENGINE] MODEL_RESTORE_SUCCESS: restoration completed - GPU fully operational")
                    # Clear suspend state after successful restoration
                    self._suspend_state = None
                else:
                    raise RuntimeError("CUDA health check failed with restored models")

            except Exception as e:
                logger.error(f"Model restoration failed: {e}")
                logger.warning("Falling back to CPU mode permanently")
                self._force_cpu_fallback_after_suspend()

        except Exception as e:
            logger.error(f"Unexpected error during background model restoration: {e}")
            self._force_cpu_fallback_after_suspend()

    def get_sleep_monitoring_stats(self) -> Dict[str, Any]:
        """Get sleep monitoring statistics"""
        return {
            "sleep_monitoring_enabled": self.sleep_monitor is not None and self.sleep_monitor.is_monitoring() if self.sleep_monitor else False,
            "suspend_recovery_attempts": self.suspend_recovery_attempts,
            "resume_validation_attempts": self.resume_validation_attempts,
            "platform_monitoring_available": self.sleep_monitor is not None
        }
