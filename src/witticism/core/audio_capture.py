import logging
import pyaudio
import numpy as np
import webrtcvad
from queue import Queue
from threading import Thread, Event, Lock
from typing import Optional, Callable, List
import time

logger = logging.getLogger(__name__)

# PortAudio error codes that indicate recoverable vs fatal errors
RECOVERABLE_ERRORS = {
    -9981,  # paInputOverflowed
    -9980,  # paOutputUnderflowed
}

FATAL_ERRORS = {
    -9999,  # paUnanticipatedHostError
    -9998,  # paInternalError
    -9996,  # paDeviceUnavailable
    -9995,  # paInvalidChannelCount
    -9994,  # paInvalidSampleRate
    -9993,  # paInvalidDevice
}


class AudioCapture:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration_ms: int = 30,  # For VAD
        vad_aggressiveness: int = 2,
        min_speech_duration: float = 0.5,
        max_silence_duration: float = 1.0
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration_ms = chunk_duration_ms
        self.vad_aggressiveness = vad_aggressiveness
        self.min_speech_duration = min_speech_duration
        self.max_silence_duration = max_silence_duration

        # Calculate chunk size
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000)

        # PyAudio setup
        self.audio = pyaudio.PyAudio()
        self.stream = None

        # VAD setup
        self.vad = webrtcvad.Vad(vad_aggressiveness)

        # Audio buffer
        self.audio_queue = Queue()
        self.recording_buffer = []

        # Control flags
        self.is_recording = False
        self.stop_event = Event()
        self.capture_thread = None

        # Callbacks
        self.on_speech_start = None
        self.on_speech_end = None
        self.on_error: Optional[Callable[[Exception, bool], None]] = None  # (error, is_fatal)

        # Error state tracking
        self._error_lock = Lock()
        self._error_state = False
        self._last_error: Optional[Exception] = None
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3  # After this many errors, consider it fatal
        self._last_device_index: Optional[int] = None

        logger.info(f"AudioCapture initialized: {sample_rate}Hz, {channels} channel(s)")

    def get_audio_devices(self) -> List[dict]:
        devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels'],
                    'sample_rate': info['defaultSampleRate']
                })
        return devices

    def _is_fatal_error(self, error: Exception) -> bool:
        """Determine if an error is fatal (requires full recovery) or transient."""
        error_str = str(error)
        # Check for known fatal error codes
        for code in FATAL_ERRORS:
            if str(code) in error_str:
                return True
        # Check for consecutive errors threshold
        return self._consecutive_errors >= self._max_consecutive_errors

    def _handle_capture_error(self, error: Exception) -> bool:
        """
        Handle an error that occurred during capture.
        Returns True if capture should continue, False if it should stop.
        """
        with self._error_lock:
            self._consecutive_errors += 1
            self._last_error = error
            is_fatal = self._is_fatal_error(error)

            if is_fatal:
                self._error_state = True
                logger.error(f"Fatal audio capture error: {error}")
            else:
                logger.warning(f"Transient audio capture error ({self._consecutive_errors}/{self._max_consecutive_errors}): {error}")

        # Notify callback
        if self.on_error:
            try:
                self.on_error(error, is_fatal)
            except Exception as cb_error:
                logger.error(f"Error in on_error callback: {cb_error}")

        return not is_fatal

    def _reset_error_state(self) -> None:
        """Reset error tracking after successful operation."""
        with self._error_lock:
            self._consecutive_errors = 0
            self._error_state = False
            self._last_error = None

    def _safe_close_stream(self) -> None:
        """Safely close the audio stream, handling any errors."""
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            finally:
                self.stream = None

    def _reinitialize_audio(self) -> bool:
        """Reinitialize PyAudio after a fatal error. Returns True on success."""
        logger.info("Reinitializing PyAudio...")
        try:
            self._safe_close_stream()
            self.audio.terminate()
            time.sleep(0.5)  # Give the system time to release resources
            self.audio = pyaudio.PyAudio()
            self._reset_error_state()
            logger.info("PyAudio reinitialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to reinitialize PyAudio: {e}")
            return False

    @property
    def has_error(self) -> bool:
        """Check if the capture is in an error state."""
        with self._error_lock:
            return self._error_state

    @property
    def last_error(self) -> Optional[Exception]:
        """Get the last error that occurred."""
        with self._error_lock:
            return self._last_error

    def start_recording(
        self,
        device_index: Optional[int] = None,
        callback: Optional[Callable] = None
    ) -> None:
        if self.is_recording:
            logger.warning("Already recording")
            return

        # If in error state, try to recover first
        if self.has_error:
            logger.warning("Audio capture in error state, attempting recovery...")
            if not self._reinitialize_audio():
                raise RuntimeError("Cannot start recording: audio system in error state and recovery failed")

        self._last_device_index = device_index

        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )

            self.is_recording = True
            self.stop_event.clear()
            self.recording_buffer = []
            self._reset_error_state()  # Clear any previous errors on successful start

            # Start capture thread
            self.capture_thread = Thread(
                target=self._capture_loop,
                args=(callback,)
            )
            self.capture_thread.start()

            logger.info(f"Started recording on device {device_index}")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._handle_capture_error(e)
            raise

    def stop_recording(self) -> np.ndarray:
        if not self.is_recording:
            return np.array([], dtype=np.int16)

        self.stop_event.set()

        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)

        self._safe_close_stream()
        self.is_recording = False

        # Convert buffer to numpy array
        if self.recording_buffer:
            audio_data = np.concatenate(self.recording_buffer)
            logger.info(f"Stopped recording. Captured {len(audio_data)/self.sample_rate:.2f} seconds")
            return audio_data
        else:
            return np.array([], dtype=np.int16)

    def _capture_loop(self, callback: Optional[Callable]) -> None:
        speech_frames = []
        silence_frames = 0
        is_speech = False
        speech_start_time = None

        while not self.stop_event.is_set():
            try:
                # Read audio chunk
                if self.stream and self.stream.is_active():
                    audio_chunk = self.stream.read(
                        self.chunk_size,
                        exception_on_overflow=False
                    )

                    # Reset error count on successful read
                    self._reset_error_state()

                    # Convert to numpy
                    audio_np = np.frombuffer(audio_chunk, dtype=np.int16)

                    # Store in buffer
                    self.recording_buffer.append(audio_np)

                    # Apply VAD
                    is_speech_frame = self.vad.is_speech(audio_chunk, self.sample_rate)

                    if is_speech_frame:
                        if not is_speech:
                            # Speech started
                            is_speech = True
                            speech_start_time = time.time()
                            if self.on_speech_start:
                                self.on_speech_start()

                        speech_frames.append(audio_np)
                        silence_frames = 0

                    else:
                        if is_speech:
                            silence_frames += 1
                            silence_duration = silence_frames * self.chunk_duration_ms / 1000

                            # Check if silence is long enough to end speech
                            if silence_duration >= self.max_silence_duration:
                                speech_duration = time.time() - speech_start_time

                                if speech_duration >= self.min_speech_duration:
                                    # Valid speech segment
                                    if callback:
                                        speech_audio = np.concatenate(speech_frames)
                                        callback(speech_audio)

                                    if self.on_speech_end:
                                        self.on_speech_end()

                                # Reset
                                is_speech = False
                                speech_frames = []
                                silence_frames = 0
                                speech_start_time = None

                    # Also add frames to buffer for continuous capture
                    if is_speech:
                        speech_frames.append(audio_np)
                else:
                    # Stream not active, wait briefly before checking again
                    time.sleep(0.01)

            except Exception as e:
                should_continue = self._handle_capture_error(e)
                if not should_continue:
                    logger.error("Fatal error in capture loop, stopping capture")
                    self.stop_event.set()
                    break
                # Small delay before retry on transient errors
                time.sleep(0.1)

    def set_vad_callbacks(
        self,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable] = None
    ) -> None:
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

    def cleanup(self) -> None:
        self.stop_recording()
        self.audio.terminate()
        logger.info("AudioCapture cleaned up")


class PushToTalkCapture(AudioCapture):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ptt_buffer = []
        self.ptt_active = False

    def start_push_to_talk(self, device_index: Optional[int] = None) -> None:
        if self.ptt_active:
            return

        self.ptt_active = True
        self.ptt_buffer = []
        self.start_recording(device_index=device_index)
        logger.info("Push-to-talk started")

    def stop_push_to_talk(self) -> np.ndarray:
        if not self.ptt_active:
            return np.array([], dtype=np.int16)

        self.ptt_active = False
        audio_data = self.stop_recording()
        logger.info(f"Push-to-talk stopped. Duration: {len(audio_data)/self.sample_rate:.2f}s")
        return audio_data


class ContinuousCapture(AudioCapture):
    """Continuous audio capture with chunked processing for real-time transcription"""

    def __init__(self, chunk_callback: Optional[Callable] = None, **kwargs):
        super().__init__(**kwargs)
        self.chunk_callback = chunk_callback
        self.continuous_active = False
        self.chunk_buffer = []
        self.chunk_duration = 2.0  # Process chunks every 2 seconds
        self.last_chunk_time = None

    def start_continuous(self, device_index: Optional[int] = None) -> None:
        if self.continuous_active:
            return

        self.continuous_active = True
        self.chunk_buffer = []
        self.last_chunk_time = time.time()

        # Start recording with our custom continuous loop
        self._start_continuous_recording(device_index)
        logger.info("Continuous capture started")

    def stop_continuous(self) -> None:
        if not self.continuous_active:
            return

        self.continuous_active = False

        # Process any remaining audio
        if self.chunk_buffer:
            audio_chunk = np.concatenate(self.chunk_buffer)
            if self.chunk_callback and len(audio_chunk) > 0:
                duration = len(audio_chunk) / self.sample_rate
                logger.info(f"Processing final chunk: {duration:.1f}s")
                self.chunk_callback(audio_chunk)
            self.chunk_buffer = []

        self.stop_recording()
        logger.info("Continuous capture stopped")

    def _start_continuous_recording(self, device_index: Optional[int] = None) -> None:
        """Start continuous recording with periodic chunk processing"""
        if self.is_recording:
            return

        # If in error state, try to recover first
        if self.has_error:
            logger.warning("Audio capture in error state, attempting recovery...")
            if not self._reinitialize_audio():
                raise RuntimeError("Cannot start recording: audio system in error state and recovery failed")

        self._last_device_index = device_index

        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )

            self.is_recording = True
            self.stop_event.clear()
            self.recording_buffer = []
            self._reset_error_state()  # Clear any previous errors on successful start

            # Start continuous capture thread
            self.capture_thread = Thread(
                target=self._continuous_capture_loop
            )
            self.capture_thread.start()

            logger.info(f"Started continuous recording on device {device_index}")

        except Exception as e:
            logger.error(f"Failed to start continuous recording: {e}")
            self._handle_capture_error(e)
            raise

    def _continuous_capture_loop(self) -> None:
        """Continuous capture loop that processes chunks periodically"""
        while not self.stop_event.is_set() and self.continuous_active:
            try:
                # Read audio chunk
                if self.stream and self.stream.is_active():
                    audio_chunk = self.stream.read(
                        self.chunk_size,
                        exception_on_overflow=False
                    )

                    # Reset error count on successful read
                    self._reset_error_state()

                    # Convert to numpy
                    audio_np = np.frombuffer(audio_chunk, dtype=np.int16)

                    # Store in buffer
                    self.recording_buffer.append(audio_np)
                    self.chunk_buffer.append(audio_np)

                    # Check if it's time to process a chunk
                    current_time = time.time()
                    if current_time - self.last_chunk_time >= self.chunk_duration:
                        if self.chunk_buffer:
                            audio_to_process = np.concatenate(self.chunk_buffer)
                            duration = len(audio_to_process) / self.sample_rate

                            if duration >= 0.5:  # Only process if we have at least 0.5s
                                logger.info(f"Processing chunk: {duration:.1f}s")
                                if self.chunk_callback:
                                    self.chunk_callback(audio_to_process)

                            self.chunk_buffer = []
                            self.last_chunk_time = current_time
                else:
                    # Stream not active, wait briefly before checking again
                    time.sleep(0.01)

            except Exception as e:
                should_continue = self._handle_capture_error(e)
                if not should_continue:
                    logger.error("Fatal error in continuous capture loop, stopping capture")
                    self.continuous_active = False
                    self.stop_event.set()
                    break
                # Small delay before retry on transient errors
                time.sleep(0.1)
