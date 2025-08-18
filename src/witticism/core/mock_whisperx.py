"""
Mock WhisperX module for testing without the actual WhisperX library.
This allows us to test the application structure and UI without GPU dependencies.
"""

import logging
import time
import numpy as np
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class MockWhisperXModel:
    def __init__(self, model_size: str, device: str, compute_type: str, language: str):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        logger.info(f"Mock WhisperX model initialized: {model_size} on {device}")

    def transcribe(self, audio: np.ndarray, **kwargs) -> Dict[str, Any]:
        # Simulate processing delay based on model size
        delays = {
            "tiny": 0.5,
            "tiny.en": 0.5,
            "base": 1.0,
            "base.en": 1.0,
            "small": 1.5,
            "medium": 2.0,
            "large-v3": 3.0
        }

        delay = delays.get(self.model_size, 1.0)
        time.sleep(delay)

        # Generate mock transcription
        duration = len(audio) / 16000  # Assuming 16kHz

        return {
            "segments": [
                {
                    "text": f"This is a mock transcription of {duration:.1f} seconds of audio using {self.model_size} model.",
                    "start": 0.0,
                    "end": duration
                }
            ],
            "language": self.language
        }


def load_model(model_size: str, device: str, compute_type: str = "int8", language: str = "en") -> MockWhisperXModel:
    return MockWhisperXModel(model_size, device, compute_type, language)


def load_align_model(language_code: str, device: str) -> Tuple[None, None]:
    logger.info(f"Mock alignment model loaded for {language_code}")
    return None, None


def align(segments: list, align_model: Any, metadata: Any, audio: np.ndarray, device: str, **kwargs) -> Dict[str, Any]:
    return {"segments": segments}


class DiarizationPipeline:
    def __init__(self, use_auth_token: str, device: str):
        self.device = device
        logger.info("Mock diarization pipeline initialized")

    def __call__(self, audio: np.ndarray) -> list:
        return []


def assign_word_speakers(diarize_segments: list, result: Dict[str, Any]) -> Dict[str, Any]:
    return result
