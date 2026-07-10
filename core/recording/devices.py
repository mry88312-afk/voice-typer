"""麥克風輸入裝置 — 列舉、解析、測試。過濾掉虛擬裝置。"""
import sounddevice as sd
import numpy as np


VIRTUAL_DEVICE_KEYWORDS = (
    'virtual', 'deskin', 'voice changer', 'mfdriver',
    '立體聲混音', 'stereo mix', '喇叭', 'speaker', 'output',
    '音效對應表', 'sound mapper', '擷取驅動程式',
)


def list_input_devices() -> list:
    """回傳真實麥克風 [(index, name), ...]，排除虛擬裝置與重複。"""
    devices = []
    seen = set()
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get('max_input_channels', 0) <= 0:
                continue
            name = d.get('name', '')
            low = name.lower()
            if any(kw in low for kw in VIRTUAL_DEVICE_KEYWORDS):
                continue
            key = name[:20]
            if key in seen:
                continue
            seen.add(key)
            devices.append((i, name))
    except Exception as e:
        print(f'list_input_devices failed: {e}')
    return devices


def resolve_input_device(preferred_name):
    """把裝置名稱解析成 index。找不到回 None (系統預設)。"""
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
    """錄一小段測音量，回傳 {rms, peak, ok, device_used}。"""
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
        info = sd.query_devices(device if device is not None else sd.default.device[0])
        used = info.get('name', used)
    except Exception:
        pass
    return {'rms': rms, 'peak': peak, 'ok': rms >= 0.005, 'device_used': used}
