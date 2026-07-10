"""單發錄音 — 按下開始、再按結束。"""
import tempfile
import sounddevice as sd
import soundfile as sf
import numpy as np

from core.recording.devices import resolve_input_device


class Recorder:
    def __init__(self, samplerate=16000, channels=1, device_name=None,
                 silence_rms_threshold=0.005):
        self.samplerate = samplerate
        self.channels = channels
        self.device_name = device_name
        self.silence_rms_threshold = silence_rms_threshold
        self.recording = False
        self.frames = []
        self.stream = None
        self.on_chunk = None
        self.last_rms = 0.0

    def _callback(self, indata, frames, time, status):
        if self.recording:
            self.frames.append(indata.copy())
            if self.on_chunk:
                try:
                    self.on_chunk(indata)
                except Exception:
                    pass

    def start(self, on_chunk=None):
        self.frames = []
        self.recording = True
        self.on_chunk = on_chunk
        device = resolve_input_device(self.device_name)
        self.stream = sd.InputStream(
            samplerate=self.samplerate, channels=self.channels,
            callback=self._callback, dtype='float32', device=device,
        )
        self.stream.start()

    def cancel(self):
        self.recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.frames = []

    def stop(self):
        if not self.recording:
            return None
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if not self.frames:
            return None

        audio_data = np.concatenate(self.frames, axis=0)
        if len(audio_data) < self.samplerate * 0.3:
            return None

        rms = float(np.sqrt(np.mean(audio_data ** 2)))
        self.last_rms = rms
        if rms < self.silence_rms_threshold:
            return None

        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        path = tmp.name
        tmp.close()
        sf.write(path, audio_data, self.samplerate)
        return path
