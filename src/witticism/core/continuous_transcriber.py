import logging
import numpy as np
from threading import Thread, Event
from queue import Queue
import time
from typing import Callable

logger = logging.getLogger(__name__)


class ContinuousTranscriber:
    """Handles continuous transcription with proper threading"""

    def __init__(self, engine, output_callback: Callable):
        self.engine = engine
        self.output_callback = output_callback

        # Threading components
        self.audio_queue = Queue()
        self.worker_thread = None
        self.stop_event = Event()
        self.is_running = False

    def start(self):
        """Start the transcription worker thread"""
        if self.is_running:
            return

        self.is_running = True
        self.stop_event.clear()

        self.worker_thread = Thread(target=self._process_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Continuous transcriber started")

    def stop(self):
        """Stop the transcription worker thread"""
        if not self.is_running:
            return

        self.is_running = False
        self.stop_event.set()

        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)

        # Clear any remaining audio
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception:
                pass

        logger.info("Continuous transcriber stopped")

    def process_audio(self, audio_data: np.ndarray):
        """Queue audio for transcription"""
        if self.is_running:
            self.audio_queue.put(audio_data)

    def _process_loop(self):
        """Worker thread loop for processing audio chunks"""
        while not self.stop_event.is_set():
            try:
                # Get audio with timeout
                audio_data = self.audio_queue.get(timeout=0.5)

                # Convert to float32
                audio_float = audio_data.astype('float32') / 32768.0

                # Transcribe
                start_time = time.time()
                result = self.engine.transcribe(audio_float)
                text = self.engine.format_result(result)
                processing_time = time.time() - start_time

                duration = len(audio_data) / 16000
                logger.info(f"Transcribed {duration:.1f}s in {processing_time:.2f}s: {text[:50] if text else '(empty)'}...")

                # Output text if we got something
                if text:
                    self.output_callback(text + " ")

            except Exception as e:
                import queue
                if not isinstance(e, queue.Empty):
                    logger.error(f"Transcription error: {e}")
