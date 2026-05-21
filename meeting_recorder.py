"""會議錄音 — 邊錄邊寫檔，避免 crash 全失"""
import time
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf


class MeetingRecorder:
    """長時間錄音 — 串流寫入 wav，每 callback 都即時 flush

    安全保證：
    - 邊錄邊寫到 disk，即使程式 crash wav 都還在
    - on_progress callback 每 chunk 觸發，給 UI 顯示音量/時長/檔案大小
    - include_system_audio=True 時嘗試用 WASAPI loopback 混音 (Windows 11)
    """

    SAMPLERATE = 16000
    CHANNELS = 1

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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

        self.on_progress = None   # callback(elapsed_s, file_size_bytes, rms)
        self.include_system_audio = False

        self.last_rms = 0.0

    # ---------- public API ----------
    def start(self, include_system_audio=False):
        timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.mic_path = self.output_dir / f'meeting_{timestamp}_mic.wav'
        self.include_system_audio = include_system_audio

        # 麥克風 stream
        self.mic_file = sf.SoundFile(
            str(self.mic_path), mode='w',
            samplerate=self.SAMPLERATE, channels=self.CHANNELS,
            subtype='PCM_16',
        )
        self.mic_stream = sd.InputStream(
            samplerate=self.SAMPLERATE,
            channels=self.CHANNELS,
            callback=self._mic_callback,
            dtype='float32',
        )

        # 系統聲音 (loopback)
        if include_system_audio:
            try:
                self.sys_path = self.output_dir / f'meeting_{timestamp}_system.wav'
                sys_device, sys_settings = self._find_wasapi_loopback()
                if sys_device is not None:
                    self.sys_file = sf.SoundFile(
                        str(self.sys_path), mode='w',
                        samplerate=self.SAMPLERATE, channels=self.CHANNELS,
                        subtype='PCM_16',
                    )
                    self.sys_stream = sd.InputStream(
                        device=sys_device,
                        samplerate=self.SAMPLERATE,
                        channels=self.CHANNELS,
                        callback=self._sys_callback,
                        dtype='float32',
                        extra_settings=sys_settings,
                    )
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
        """結束錄音，回傳 (mic_path, sys_path or None, duration_seconds)"""
        if not self.recording:
            return None, None, 0.0

        self.recording = False
        if self.paused and self._pause_start:
            self.paused_seconds += time.time() - self._pause_start

        try:
            if self.mic_stream:
                self.mic_stream.stop()
                self.mic_stream.close()
        except Exception:
            pass
        try:
            if self.sys_stream:
                self.sys_stream.stop()
                self.sys_stream.close()
        except Exception:
            pass

        try:
            if self.mic_file:
                self.mic_file.close()
        except Exception:
            pass
        try:
            if self.sys_file:
                self.sys_file.close()
        except Exception:
            pass

        elapsed = max(0.0, (time.time() - self.start_ts) - self.paused_seconds) if self.start_ts else 0.0
        return self.mic_path, self.sys_path, elapsed

    def cancel(self):
        """取消錄音 + 刪除已寫的檔案"""
        mic, sys_p, _ = self.stop()
        try:
            if mic and mic.exists():
                mic.unlink()
        except Exception:
            pass
        try:
            if sys_p and sys_p.exists():
                sys_p.unlink()
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

    # ---------- internal ----------
    def _mic_callback(self, indata, frames, time_info, status):
        if not self.recording or self.paused:
            return
        try:
            self.mic_file.write(indata)
            # 計算音量 + 通知 progress
            rms = float(np.sqrt(np.mean(indata ** 2)))
            self.last_rms = rms
            if self.on_progress:
                try:
                    self.on_progress(
                        self.elapsed_seconds(),
                        self.file_size(),
                        rms,
                    )
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
        """找預設輸出裝置 + 啟用 loopback (Windows WASAPI)"""
        hostapis = sd.query_hostapis()
        for i, h in enumerate(hostapis):
            if 'WASAPI' in h.get('name', ''):
                default_out = h.get('default_output_device')
                if default_out is None or default_out < 0:
                    continue
                try:
                    settings = sd.WasapiSettings(loopback=True)
                    return default_out, settings
                except Exception:
                    pass
        return None, None
