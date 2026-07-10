"""Streaming 模式錄音 — VAD 自動切段，邊講邊出字。"""
import tempfile
import threading
import time
from queue import Queue, Empty
import numpy as np
import sounddevice as sd
import soundfile as sf

from core.recording.devices import resolve_input_device


class StreamingRecorder:
    SAMPLERATE = 16000
    CHANNELS = 1

    def __init__(self, silence_threshold_rms=0.022, silence_seconds_to_flush=0.7,
                 min_chunk_seconds=1.0, max_chunk_seconds=8.0, device_name=None):
        self.silence_threshold = silence_threshold_rms
        self.silence_flush = silence_seconds_to_flush
        self.min_chunk = min_chunk_seconds
        self.max_chunk = max_chunk_seconds
        self.device_name = device_name

        self.recording = False
        self.stream = None
        self._buffer = []
        self._buffer_samples = 0
        self._chunk_start_ts = None
        self._last_voice_ts = None
        self._has_voice_in_chunk = False
        self._chunk_queue = Queue()
        self._worker_thread = None

        self.on_chunk_ready = None
        self.on_text = None
        self.on_volume = None
        self.on_state = None
        self._state = 'idle'

    def start(self):
        if self.recording:
            return
        self.recording = True
        self._buffer = []
        self._buffer_samples = 0
        self._chunk_start_ts = time.time()
        self._last_voice_ts = None
        self._has_voice_in_chunk = False

        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

        device = resolve_input_device(self.device_name)
        self.stream = sd.InputStream(
            samplerate=self.SAMPLERATE, channels=self.CHANNELS,
            callback=self._callback, dtype='float32', device=device,
        )
        self.stream.start()
        self._set_state('listening')

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception:
            pass
        self._flush_chunk(force=True)
        self._chunk_queue.put(None)
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        self._set_state('idle')

    def cancel(self):
        self.recording = False
        self._buffer = []
        self._buffer_samples = 0
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception:
            pass
        while not self._chunk_queue.empty():
            try:
                self._chunk_queue.get_nowait()
            except Empty:
                break
        self._chunk_queue.put(None)
        self._set_state('idle')

    def _callback(self, indata, frames, time_info, status):
        if not self.recording:
            return
        try:
            chunk = indata.copy()
            self._buffer.append(chunk)
            self._buffer_samples += len(chunk)
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            now = time.time()
            if self.on_volume:
                try:
                    self.on_volume(rms)
                except Exception:
                    pass
            if rms > self.silence_threshold:
                self._last_voice_ts = now
                self._has_voice_in_chunk = True
                self._set_state('speaking')
            buffer_seconds = self._buffer_samples / self.SAMPLERATE
            should_flush = False
            if self._has_voice_in_chunk and self._last_voice_ts:
                if (now - self._last_voice_ts) >= self.silence_flush and buffer_seconds >= self.min_chunk:
                    should_flush = True
            if buffer_seconds >= self.max_chunk and self._has_voice_in_chunk:
                should_flush = True
            if should_flush:
                self._flush_chunk()
        except Exception as e:
            print(f"streaming callback error: {e}")

    def _flush_chunk(self, force=False):
        if not self._buffer:
            return
        if not self._has_voice_in_chunk and not force:
            self._buffer = []
            self._buffer_samples = 0
            self._last_voice_ts = None
            return
        try:
            audio_data = np.concatenate(self._buffer, axis=0)
            if len(audio_data) < self.SAMPLERATE * 0.4:
                self._buffer = []
                self._buffer_samples = 0
                self._has_voice_in_chunk = False
                self._last_voice_ts = None
                return
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp.close()
            sf.write(tmp.name, audio_data, self.SAMPLERATE, subtype='PCM_16')
            self._chunk_queue.put(tmp.name)
        except Exception as e:
            print(f"flush failed: {e}")
        finally:
            self._buffer = []
            self._buffer_samples = 0
            self._has_voice_in_chunk = False
            self._last_voice_ts = None
            self._chunk_start_ts = time.time()
            self._set_state('listening')

    def _worker(self):
        import os
        while True:
            try:
                wav_path = self._chunk_queue.get(timeout=30)
            except Empty:
                continue
            if wav_path is None:
                break
            try:
                self._set_state('flushing')
                if self.on_chunk_ready:
                    text = self.on_chunk_ready(wav_path)
                    if text and self.on_text:
                        try:
                            self.on_text(text)
                        except Exception:
                            pass
            except Exception as e:
                print(f"streaming worker error: {e}")
            finally:
                try:
                    if wav_path and os.path.exists(wav_path):
                        os.unlink(wav_path)
                except Exception:
                    pass

    def _set_state(self, state):
        if state == self._state:
            return
        self._state = state
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass
