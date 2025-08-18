import logging
import numpy as np
from typing import Optional, Callable
from queue import Queue
from threading import Thread, Event
import time

logger = logging.getLogger(__name__)


class TranscriptionPipeline:
    def __init__(
        self,
        whisperx_engine,
        min_audio_length: float = 0.5,
        max_audio_length: float = 30.0
    ):
        self.engine = whisperx_engine
        self.min_audio_length = min_audio_length
        self.max_audio_length = max_audio_length

        # Processing queue
        self.audio_queue = Queue()
        self.result_queue = Queue()

        # Worker thread
        self.worker_thread = None
        self.stop_event = Event()

        logger.info("TranscriptionPipeline initialized")

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Pipeline already running")
            return

        self.stop_event.clear()
        self.worker_thread = Thread(target=self._process_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()

        logger.info("TranscriptionPipeline started")

    def stop(self):
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        logger.info("TranscriptionPipeline stopped")

    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        callback: Optional[Callable] = None
    ) -> Optional[str]:
        # Check audio length
        duration = len(audio_data) / 16000  # Assuming 16kHz

        if duration < self.min_audio_length:
            logger.warning(f"Audio too short: {duration:.2f}s")
            return None

        if duration > self.max_audio_length:
            logger.warning(f"Audio too long: {duration:.2f}s, truncating")
            max_samples = int(self.max_audio_length * 16000)
            audio_data = audio_data[:max_samples]

        # Add to queue for processing
        self.audio_queue.put((audio_data, callback))

        # If not using callback, wait for result
        if callback is None:
            try:
                result = self.result_queue.get(timeout=30)
                return result
            except Exception:
                return None

    def _process_loop(self):
        while not self.stop_event.is_set():
            try:
                # Get audio from queue with timeout
                audio_data, callback = self.audio_queue.get(timeout=0.5)

                # Process transcription
                start_time = time.time()
                result = self.engine.transcribe(audio_data)
                text = self.engine.format_result(result)
                processing_time = time.time() - start_time

                duration = len(audio_data) / 16000
                speed_ratio = duration / processing_time

                logger.info(
                    f"Transcribed {duration:.2f}s in {processing_time:.2f}s "
                    f"({speed_ratio:.1f}x realtime): {text[:50]}..."
                )

                # Return result
                if callback:
                    callback(text)
                else:
                    self.result_queue.put(text)

            except Exception as e:
                # Only log real errors, not queue timeouts
                import queue
                if not isinstance(e, queue.Empty):
                    logger.error(f"Pipeline processing error: {e}")


class StreamingTranscriptionPipeline(TranscriptionPipeline):
    def __init__(
        self,
        whisperx_engine,
        chunk_duration: float = 5.0,
        overlap_duration: float = 0.5,
        **kwargs
    ):
        super().__init__(whisperx_engine, **kwargs)
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration

        # Streaming buffer
        self.stream_buffer = []
        self.last_transcript = ""

    def process_stream(
        self,
        audio_chunk: np.ndarray,
        callback: Optional[Callable] = None
    ) -> Optional[str]:
        # Add chunk to buffer
        self.stream_buffer.append(audio_chunk)

        # Check if we have enough audio
        total_samples = sum(len(chunk) for chunk in self.stream_buffer)
        duration = total_samples / 16000

        if duration >= self.chunk_duration:
            # Combine buffer
            combined_audio = np.concatenate(self.stream_buffer)

            # Process
            result = self.engine.transcribe(combined_audio)
            text = self.engine.format_result(result)

            # Keep overlap for context
            overlap_samples = int(self.overlap_duration * 16000)
            if len(combined_audio) > overlap_samples:
                self.stream_buffer = [combined_audio[-overlap_samples:]]
            else:
                self.stream_buffer = []

            # Call callback with incremental text
            if callback:
                # Simple deduplication - only send new text
                if text != self.last_transcript:
                    new_text = text[len(self.last_transcript):].strip()
                    if new_text:
                        callback(new_text)
                    self.last_transcript = text

            return text

        return None

    def reset_stream(self):
        self.stream_buffer = []
        self.last_transcript = ""
