"""Streaming 模式錄音 — VAD (Voice Activity Detection) 自動切段

工作流程：
1. 持續錄音
2. 偵測「使用者停頓 N 秒」→ 自動把前一段送 Whisper
3. 文字回來後立刻貼到游標
4. 繼續錄下一段
5. 使用者按結束 → 停止

配合 Groq Whisper Turbo (500ms) 達到「邊講邊出字」體感。
"""
import tempfile
import threading
import time
from queue import Queue, Empty
import numpy as np
import sounddevice as sd
import soundfile as sf


class StreamingRecorder:
    """VAD-based streaming recorder

    參數說明：
    - silence_threshold_rms: 多小聲算靜音 (0.0~1.0)
    - silence_seconds_to_flush: 停頓多久就切段
    - min_chunk_seconds: 最短段 (避免單字觸發)
    - max_chunk_seconds: 最長段 (防止無止盡累積)
    """

    SAMPLERATE = 16000
    CHANNELS = 1

    def __init__(self,
                 silence_threshold_rms: float = 0.012,
                 silence_seconds_to_flush: float = 1.2,
                 min_chunk_seconds: float = 1.0,
                 max_chunk_seconds: float = 12.0):
        self.silence_threshold = silence_threshold_rms
        self.silence_flush = silence_seconds_to_flush
        self.min_chunk = min_chunk_seconds
        self.max_chunk = max_chunk_seconds

        self.recording = False
        self.stream = None

        # buffer for current chunk
        self._buffer = []  # list of np.ndarray
        self._buffer_samples = 0
        self._chunk_start_ts = None
        self._last_voice_ts = None
        self._has_voice_in_chunk = False

        # flush queue (subprocess 跑轉錄)
        self._chunk_queue: Queue = Queue()
        self._worker_thread: threading.Thread = None

        # callbacks
        self.on_chunk_ready = None     # (chunk_path: str) -> transcribed_text (sync)
        self.on_text = None            # (text: str) — 收到轉錄結果時
        self.on_volume = None          # (rms: float) — 音量更新 (給 UI)
        self.on_state = None           # ('listening' | 'speaking' | 'flushing')

        self._state = 'idle'

    # ---------- 公開 API ----------
    def start(self):
        if self.recording:
            return
        self.recording = True
        self._buffer = []
        self._buffer_samples = 0
        self._chunk_start_ts = time.time()
        self._last_voice_ts = None
        self._has_voice_in_chunk = False

        # 啟動 worker thread 處理 flush
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

        from recorder import resolve_input_device
        device = resolve_input_device(getattr(self, 'device_name', None))
        self.stream = sd.InputStream(
            samplerate=self.SAMPLERATE,
            channels=self.CHANNELS,
            callback=self._callback,
            dtype='float32',
            device=device,
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

        # flush 剩餘的最後一段
        self._flush_chunk(force=True)

        # 結束 worker
        self._chunk_queue.put(None)  # 哨兵
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        self._set_state('idle')

    def cancel(self):
        """取消 — 丟棄當前 buffer，停止"""
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
        # 清空 queue
        while not self._chunk_queue.empty():
            try:
                self._chunk_queue.get_nowait()
            except Empty:
                break
        self._chunk_queue.put(None)
        self._set_state('idle')

    # ---------- audio callback ----------
    def _callback(self, indata, frames, time_info, status):
        if not self.recording:
            return
        try:
            chunk = indata.copy()
            self._buffer.append(chunk)
            self._buffer_samples += len(chunk)

            rms = float(np.sqrt(np.mean(chunk ** 2)))
            now = time.time()

            # 通知 UI 音量
            if self.on_volume:
                try:
                    self.on_volume(rms)
                except Exception:
                    pass

            # 判斷有沒有人聲
            is_voice = rms > self.silence_threshold
            if is_voice:
                self._last_voice_ts = now
                self._has_voice_in_chunk = True
                self._set_state('speaking')

            # 邏輯：若 chunk 中有人聲，但最近 silence_flush 秒沒聲音 → flush
            buffer_seconds = self._buffer_samples / self.SAMPLERATE

            should_flush = False
            if self._has_voice_in_chunk and self._last_voice_ts:
                silence_duration = now - self._last_voice_ts
                if silence_duration >= self.silence_flush and buffer_seconds >= self.min_chunk:
                    should_flush = True
            # 強制 flush (避免太長)
            if buffer_seconds >= self.max_chunk and self._has_voice_in_chunk:
                should_flush = True

            if should_flush:
                self._flush_chunk()
        except Exception as e:
            print(f"streaming callback error: {e}")

    def _flush_chunk(self, force: bool = False):
        """把當前 buffer 寫到 temp wav，送進 queue"""
        if not self._buffer:
            return
        if not self._has_voice_in_chunk and not force:
            # 完全沒人聲就不送
            self._buffer = []
            self._buffer_samples = 0
            self._last_voice_ts = None
            return

        try:
            audio_data = np.concatenate(self._buffer, axis=0)
            if len(audio_data) < self.SAMPLERATE * 0.4:
                # 太短不送
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

    # ---------- worker (處理 chunk queue) ----------
    def _worker(self):
        """從 queue 取出 wav 路徑，呼叫 on_chunk_ready 做轉錄，把結果傳給 on_text"""
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
                # transcriber 會刪 wav (transcribe() 內部 unlink)，這裡保險再刪
                try:
                    import os
                    if wav_path and __import__('os').path.exists(wav_path):
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
