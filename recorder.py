"""錄音模組 - 使用 sounddevice 後台錄音"""
import sounddevice as sd
import soundfile as sf
import numpy as np
import tempfile


# 虛擬裝置黑名單 — 這些不是真的麥克風，列裝置時排除
VIRTUAL_DEVICE_KEYWORDS = (
    'virtual', 'deskin', 'voice changer', 'mfdriver',
    '立體聲混音', 'stereo mix', '喇叭', 'speaker', 'output',
    '音效對應表', 'sound mapper', '擷取驅動程式',
)


def list_input_devices() -> list:
    """列出真實的麥克風輸入裝置 [(index, name), ...]，排除虛擬裝置與重複"""
    devices = []
    seen_names = set()
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get('max_input_channels', 0) <= 0:
                continue
            name = d.get('name', '')
            low = name.lower()
            if any(kw in low for kw in VIRTUAL_DEVICE_KEYWORDS):
                continue
            # MME/WASAPI/DirectSound 會列同一硬體多次 → 用名稱前 20 字去重
            key = name[:20]
            if key in seen_names:
                continue
            seen_names.add(key)
            devices.append((i, name))
    except Exception as e:
        print(f'list_input_devices failed: {e}')
    return devices


def resolve_input_device(preferred_name: str):
    """把使用者選的裝置名稱解析成 device index。找不到回 None (= 系統預設)"""
    if not preferred_name:
        return None
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get('max_input_channels', 0) <= 0:
                continue
            if preferred_name[:20] in d.get('name', ''):
                return i
    except Exception:
        pass
    return None


def test_input_device(device_name: str = '', seconds: float = 1.5) -> dict:
    """錄一小段測音量。回傳 {rms, peak, ok, device_used}"""
    device = resolve_input_device(device_name)
    fs = 16000
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1,
                   dtype='float32', device=device)
    sd.wait()
    arr = audio.flatten()
    rms = float(np.sqrt(np.mean(arr ** 2)))
    peak = float(np.max(np.abs(arr)))
    used = '系統預設'
    try:
        info = sd.query_devices(device if device is not None else
                                sd.default.device[0])
        used = info.get('name', used)
    except Exception:
        pass
    return {
        'rms': rms,
        'peak': peak,
        'ok': rms >= 0.005,
        'device_used': used,
    }


class Recorder:
    def __init__(self, samplerate=16000, channels=1, device_name=None):
        self.samplerate = samplerate
        self.channels = channels
        self.device_name = device_name  # None = 系統預設；可隨時改，下次 start 生效
        self.recording = False
        self.frames = []
        self.stream = None
        self.on_chunk = None  # 每次 audio callback 觸發，可給 UI 做波形視覺化
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
            samplerate=self.samplerate,
            channels=self.channels,
            callback=self._callback,
            dtype='float32',
            device=device,
        )
        self.stream.start()

    def cancel(self):
        """取消錄音 - 立刻停止並丟棄所有已錄音訊"""
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

        # 過短的錄音直接丟掉 (< 0.3 秒)
        if len(audio_data) < self.samplerate * 0.3:
            return None

        # 偵測音量 — 太小聲視為靜音 (避免 Whisper 幻覺)
        # RMS 是 float32 範圍 [-1,1] 的均方根，0.005 大約相當於環境噪音
        rms = float(np.sqrt(np.mean(audio_data ** 2)))
        self.last_rms = rms
        if rms < 0.005:
            return None

        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_path = temp_file.name
        temp_file.close()

        sf.write(temp_path, audio_data, self.samplerate)
        return temp_path
