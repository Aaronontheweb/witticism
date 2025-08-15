import logging
from typing import Optional, Dict, Any, Tuple
import numpy as np

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
        
        # Auto-detect device
        if device is None or device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        # Auto-select compute type based on device
        if compute_type is None:
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        else:
            self.compute_type = compute_type
            
        self.model = None
        self.align_model = None
        self.metadata = None
        self.diarize_model = None
        
        logger.info(f"WhisperX Engine initialized: device={self.device}, compute_type={self.compute_type}")
        
    def load_models(self) -> None:
        try:
            # Load main transcription model
            logger.info(f"Loading WhisperX model: {self.model_size}")
            self.model = whisperx.load_model(
                self.model_size,
                self.device,
                compute_type=self.compute_type,
                language=self.language
            )
            
            # Load alignment model for word-level timestamps
            logger.info(f"Loading alignment model for language: {self.language}")
            self.align_model, self.metadata = whisperx.load_align_model(
                language_code=self.language,
                device=self.device
            )
            
            # Optionally load diarization model
            if self.enable_diarization and self.hf_token:
                logger.info("Loading diarization model")
                self.diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=self.hf_token,
                    device=self.device
                )
                
            logger.info("All models loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            raise
            
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
            logger.error(f"Transcription failed: {e}")
            raise
            
    def transcribe_with_timing(
        self,
        audio: np.ndarray,
        **kwargs
    ) -> Tuple[Dict[str, Any], float]:
        import time
        start_time = time.time()
        result = self.transcribe(audio, **kwargs)
        processing_time = time.time() - start_time
        return result, processing_time
        
    def cleanup(self) -> None:
        if self.device == "cuda":
            torch.cuda.empty_cache()
            
    def change_model(self, model_size: str) -> None:
        self.model_size = model_size
        self.model = None
        self.load_models()
        
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
            "models_loaded": self.model is not None
        }
        
        if self.device == "cuda":
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_allocated"] = f"{torch.cuda.memory_allocated(0) / 1024**3:.2f} GB"
                info["gpu_memory_reserved"] = f"{torch.cuda.memory_reserved(0) / 1024**3:.2f} GB"
                
        return info