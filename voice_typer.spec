# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Voice Typer
打包成單一 .exe (含內嵌 Python + 所有套件 + 資源)
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# --- Hidden imports (PyInstaller 偵測不到但執行時需要) ---
hidden = []
hidden += collect_submodules('pystray')
hidden += collect_submodules('PIL')
hidden += collect_submodules('customtkinter')
hidden += collect_submodules('sounddevice')
hidden += collect_submodules('soundfile')
hidden += collect_submodules('openai')
hidden += collect_submodules('anthropic')
hidden += collect_submodules('groq')
hidden += [
    'google',
    'google.genai',
    'google.genai.types',
    'dotenv',
    'pyperclip',
    'keyboard',
    'numpy',
    'winreg',
    'winsound',
    'ctypes',
    'pkg_resources.extern',
    # ── 新架構自家模組 ──
    'app', 'app.paths', 'app.runtime', 'app.bootstrap', 'app.application',
    'core', 'core.hotkeys',
    'core.recording', 'core.recording.devices', 'core.recording.recorder',
    'core.recording.streaming_recorder', 'core.recording.meeting_recorder',
    'core.transcription', 'core.transcription.fallback',
    'core.transcription.providers', 'core.transcription.providers.base',
    'core.transcription.providers.openai_provider',
    'core.transcription.providers.anthropic_provider',
    'core.transcription.providers.google_provider',
    'core.transcription.providers.groq_provider',
    'core.meeting', 'core.meeting.processor',
    'core.text', 'core.text.hallucinations',
    'data', 'data.store', 'data.resources', 'data.config', 'data.env',
    'data.profiles', 'data.usage', 'data.history', 'data.learned',
    'ui.theme', 'ui.settings_window', 'ui.onboarding', 'ui.history_window',
    'ui.usage_window', 'ui.waveform', 'ui.meeting_window',
    'ui.meeting_history_window',
]

# --- Data files (套件的非 .py 資源) ---
datas = []
datas += collect_data_files('customtkinter')
datas += collect_data_files('sounddevice')
# resources/*.json — 預設值/provider/schema/黑名單，執行期必讀
datas += [('resources', 'resources')]
datas += [('.env.example', '.')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'pandas',  # 不需要的大套件
        'IPython', 'jupyter',
        'PySide2', 'PySide6', 'PyQt5', 'PyQt6',
        'pytest', 'unittest',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- onedir 模式 (啟動快 3-5 倍，因為不用每次 unzip 到 temp) ---
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,        # binaries 改放在 COLLECT 一起出
    name='VoiceTyper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX 壓縮會被防毒誤判
    console=False,                # 無 console (像 pythonw)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VoiceTyper',           # → dist/VoiceTyper/
)
