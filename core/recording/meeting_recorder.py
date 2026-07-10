"""會議錄音 — 邊錄邊寫檔避免 crash 全失，可含系統聲音 (WASAPI loopback)。"""
import time
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

from core.recording.devices import resolve_input_device


class MeetingRecorder:
    SAMPLERATE = 16000
    CHANNELS = 1

    def __init__(self, output_dir: Path, device_name=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device_name = device_name
        self.recording = False
        self.paused = False
        self.start_ts = None
        self.paused_seconds = 0.0
        self._pause_start = None
        self.mic_path = None
        self.sys_path = None
        self.mic_file = None
        self.sys_file = None
        self.mic_stream = None
        self.sys_stream = None
        self.on_progress = None
        self.include_system_audio = False
        self.last_rms = 0.0

    def start(self, include_system_audio=False):
        timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.mic_path = self.output_dir / f'meeting_{timestamp}_mic.wav'
        self.include_system_audio = include_system_audio

        self.mic_file = sf.SoundFile(
            str(self.mic_path), mode='w', samplerate=self.SAMPLERATE,
            channels=self.CHANNELS, subtype='PCM_16')
        self.mic_stream = sd.InputStream(
            samplerate=self.SAMPLERATE, channels=self.CHANNELS,
            callback=self._mic_callback, dtype='float32',
            device=resolve_input_device(self.device_name))

        if include_system_audio:
            try:
                self.sys_path = self.output_dir / f'meeting_{timestamp}_system.wav'
                sys_device, sys_settings = self._find_wasapi_loopback()
                if sys_device is not None:
                    self.sys_file = sf.SoundFile(
                        str(self.sys_path), mode='w', samplerate=self.SAMPLERATE,
                        channels=self.CHANNELS, subtype='PCM_16')
                    self.sys_stream = sd.InputStream(
                        device=sys_device, samplerate=self.SAMPLERATE,
                        channels=self.CHANNELS, callback=self._sys_callback,
                        dtype='float32', extra_settings=sys_settings)
            except Exception as e:
                print(f"WASAPI loopback 失敗 (只錄麥克風): {e}")
                self.sys_path = None
                self.sys_file = None
                self.sys_stream = None

        self.recording = True
        self.paused = False
        self.start_ts = time.time()
        self.paused_seconds = 0.0
        self.mic_stream.start()
        if self.sys_stream:
            self.sys_stream.start()

    def pause(self):
        if not self.recording or self.paused:
            return
        self.paused = True
        self._pause_start = time.time()

    def resume(self):
        if not self.recording or not self.paused:
            return
        self.paused = False
        if self._pause_start:
            self.paused_seconds += time.time() - self._pause_start
            self._pause_start = None

    def stop(self):
        if not self.recording:
            return None, None, 0.0
        self.recording = False
        if self.paused and self._pause_start:
            self.paused_seconds += time.time() - self._pause_start
        for stream in (self.mic_stream, self.sys_stream):
            try:
                if stream:
                    stream.stop()
                    stream.close()
            except Exception:
                pass
        for f in (self.mic_file, self.sys_file):
            try:
                if f:
                    f.close()
            except Exception:
                pass
        elapsed = max(0.0, (time.time() - self.start_ts) - self.paused_seconds) if self.start_ts else 0.0
        return self.mic_path, self.sys_path, elapsed

    def cancel(self):
        mic, sys_p, _ = self.stop()
        for p in (mic, sys_p):
            try:
                if p and p.exists():
                    p.unlink()
            except Exception:
                pass

    def elapsed_seconds(self) -> float:
        if not self.start_ts:
            return 0.0
        now = time.time()
        if self.paused and self._pause_start:
            now = self._pause_start
        return max(0.0, (now - self.start_ts) - self.paused_seconds)

    def file_size(self) -> int:
        try:
            if self.mic_path and self.mic_path.exists():
                return self.mic_path.stat().st_size
        except Exception:
            pass
        return 0

    def _mic_callback(self, indata, frames, time_info, status):
        if not self.recording or self.paused:
            return
        try:
            self.mic_file.write(indata)
            rms = float(np.sqrt(np.mean(indata ** 2)))
            self.last_rms = rms
            if self.on_progress:
                try:
                    self.on_progress(self.elapsed_seconds(), self.file_size(), rms)
                except Exception:
                    pass
        except Exception as e:
            print(f"mic callback error: {e}")

    def _sys_callback(self, indata, frames, time_info, status):
        if not self.recording or self.paused:
            return
        try:
            self.sys_file.write(indata)
        except Exception as e:
            print(f"sys callback error: {e}")

    def _find_wasapi_loopback(self):
        for h in sd.query_hostapis():
            if 'WASAPI' in h.get('name', ''):
                default_out = h.get('default_output_device')
                if default_out is None or default_out < 0:
                    continue
                try:
                    return default_out, sd.WasapiSettings(loopback=True)
                except Exception:
                    pass
        return None, None
