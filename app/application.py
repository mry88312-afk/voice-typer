"""Voice Typer - 商業版主程式
- 系統匣 + 全域快捷鍵 + 設定/歷史/歡迎精靈/波形浮窗
"""
import os
import sys
import logging
import subprocess
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Windows console UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from dotenv import load_dotenv
import pyperclip
import keyboard
from PIL import Image, ImageDraw
import pystray
import customtkinter as ctk

# ── 新架構：業務邏輯來自 core/，路徑/工具來自 app/ ──
from core.recording import Recorder, StreamingRecorder, MeetingRecorder
from core.meeting.processor import MeetingProcessor
from core.transcription import (
    get_transcriber, get_enhancer,
    TRANSCRIBER_PROVIDERS, ENHANCER_PROVIDERS, FallbackTranscriber,
)
from core.text.hallucinations import is_hallucination
from ui.theme import init_app_theme, set_theme, get_colors
from ui.settings_window import SettingsWindow
from ui.onboarding import OnboardingWizard
from ui.history_window import HistoryWindow
from ui.usage_window import UsageWindow
from ui.waveform import WaveformOverlay
from ui.meeting_window import MeetingProgressWindow, MeetingResultWindow
from ui.meeting_history_window import MeetingHistoryWindow

from app.paths import (
    BASE_DIR, BUNDLE_DIR, LOG_FILE, CONFIG_FILE, ENV_FILE,
    HISTORY_FILE, USAGE_FILE, LEARNED_WORDS_FILE, RECORDINGS_DIR,
)
from app.runtime import log, show_message, fatal


# ---------- App ----------
class VoiceTyperApp:
    def __init__(self, root, config_mgr, env_mgr, history_mgr, usage_mgr,
                 profile_mgr, learned_mgr):
        self.root = root
        self.config_mgr = config_mgr
        self.env_mgr = env_mgr
        self.history_mgr = history_mgr
        self.usage_mgr = usage_mgr
        self.profile_mgr = profile_mgr
        self.learned_mgr = learned_mgr

        # 套用主題
        set_theme(self.config_mgr.get('theme', 'system'))

        # 業務元件
        self.recorder = Recorder(
            device_name=self.config_mgr.get('input_device', '') or None,
        )
        self.transcriber = None
        self.enhancer = None
        self._rebuild_transcriber()
        self._rebuild_enhancer()

        # 狀態
        self.is_recording = False
        self.is_processing = False
        self._processing_since = None
        self._last_wd_tick = time.time()
        self.lock = threading.Lock()

        # UI 元件 (lazy init)
        self.tray_icon = None
        self.waveform = None
        self.settings_window = None
        self.history_window = None
        self.usage_window = None
        self.meeting_progress_window = None
        self.meeting_result_window = None
        self.meeting_history_window = None

        # 會議錄音元件
        self.meeting_recorder = MeetingRecorder(RECORDINGS_DIR)

        # Streaming 模式
        self.streaming_recorder = None  # lazy init
        self.is_streaming = False

        # 訂閱 config 變更 → 熱重載
        self.config_mgr.subscribe(self._on_config_changed)

    # ---------- 元件重建 (熱重載 / provider 切換) ----------
    def _rebuild_transcriber(self):
        cfg = self.config_mgr.get('transcriber') or {'provider': 'openai', 'model': 'whisper-1'}
        provider_id = cfg.get('provider', 'openai')
        model = cfg.get('model')
        info = TRANSCRIBER_PROVIDERS.get(provider_id)
        if not info:
            log.error(f'未知的 transcriber provider: {provider_id}')
            self.transcriber = None
            return
        api_key = self.env_mgr.get(info['api_key_env'])
        if not api_key or 'your-' in api_key.lower():
            log.info(f'尚未設定 {info["api_key_env"]} → transcriber 無法啟用')
            self.transcriber = None
            return
        try:
            primary = get_transcriber(
                provider_id,
                api_key=api_key,
                model=model,
                language=self.config_mgr.get('language', 'zh'),
                prompt=self._build_whisper_prompt(),
            )
            # 自動建一個 fallback secondary（用第一個有 key 但跟 primary 不同的 provider）
            secondary = self._build_fallback_transcriber(primary_id=provider_id)
            if secondary:
                self.transcriber = FallbackTranscriber(primary, secondary, logger=log)
                log.info(
                    f'transcriber: {provider_id}/{model} (fallback → '
                    f'{secondary.provider_id}/{secondary.model})'
                )
            else:
                self.transcriber = primary
                log.info(f'transcriber: {provider_id}/{model} (無 fallback)')
        except Exception as e:
            log.error(f'建構 transcriber 失敗: {e}')
            self.transcriber = None

    def _build_fallback_transcriber(self, primary_id: str):
        """挑一個跟 primary 不同的 provider 當 fallback。
        優先順序: openai > groq > google (其他都失敗才用更慢的)
        """
        preferred_order = ['openai', 'groq', 'google']
        for pid in preferred_order:
            if pid == primary_id:
                continue
            info = TRANSCRIBER_PROVIDERS.get(pid)
            if not info:
                continue
            api_key = self.env_mgr.get(info['api_key_env'])
            if not api_key or 'your-' in api_key.lower():
                continue
            try:
                # 用該 provider 的預設 model
                default_model = (info.get('models') or [{}])[0].get('id')
                return get_transcriber(
                    pid,
                    api_key=api_key,
                    model=default_model,
                    language=self.config_mgr.get('language', 'zh'),
                    prompt=self._build_whisper_prompt(),
                )
            except Exception as e:
                log.info(f'fallback {pid} 建構失敗: {e}')
                continue
        return None

    def _rebuild_enhancer(self):
        profile = self.profile_mgr.active()
        if not profile.get('enhance_enabled', False):
            self.enhancer = None
            return
        cfg = self.config_mgr.get('enhancer') or {'provider': 'anthropic', 'model': 'claude-haiku-4-5-20251001'}
        provider_id = cfg.get('provider', 'anthropic')
        model = cfg.get('model')
        info = ENHANCER_PROVIDERS.get(provider_id)
        if not info:
            log.error(f'未知的 enhancer provider: {provider_id}')
            self.enhancer = None
            return
        api_key = self.env_mgr.get(info['api_key_env'])
        if not api_key or 'your-' in api_key.lower():
            log.info(f'尚未設定 {info["api_key_env"]} → enhancer 無法啟用')
            self.enhancer = None
            return
        try:
            self.enhancer = get_enhancer(
                provider_id,
                api_key=api_key,
                model=model,
                prompt=profile.get('enhance_prompt', ''),
            )
            log.info(f'enhancer: {provider_id} / {model} (profile: {profile.get("name")})')
        except Exception as e:
            log.error(f'建構 enhancer 失敗: {e}')
            self.enhancer = None

    def _build_whisper_prompt(self):
        base = (self.config_mgr.get('whisper_prompt') or '').strip()
        profile = self.profile_mgr.active()
        vocab = profile.get('vocabulary') or []
        if not vocab:
            return base
        vocab_str = '、'.join(str(v) for v in vocab)
        if base:
            base_no_period = base.rstrip('。.')
            return f"{base_no_period}，內容可能包含 {vocab_str} 等用詞。"
        return f"嗯，這是繁體中文對話，內容包含 {vocab_str} 等用詞。"

    def _on_config_changed(self, new_config):
        log.info("config 已更新，重新建構元件")
        self._rebuild_transcriber()
        self._rebuild_enhancer()
        set_theme(new_config.get('theme', 'system'))
        # 快捷鍵熱重載 (設定改了立刻生效，不用重啟)
        self._register_hotkeys()
        # 麥克風裝置熱套用
        try:
            self.recorder.device_name = new_config.get('input_device', '') or None
        except Exception:
            pass

    def _switch_profile(self, profile_id: str):
        self.profile_mgr.set_active(profile_id)
        self._rebuild_transcriber()
        self._rebuild_enhancer()
        p = self.profile_mgr.active()
        log.info(f'已切換 profile → {p.get("name")}')
        self._notify_tray(f'已切換到「{p.get("name")}」')
        # 重建 tray menu 以顯示新的 checked 狀態
        if self.tray_icon:
            try:
                self.tray_icon.menu = self._build_tray_menu()
                self.tray_icon.update_menu()
            except Exception:
                pass

    # ---------- 錄音流程 ----------
    def _toggle_recording(self):
        with self.lock:
            if self.is_processing:
                return
            if not self.is_recording:
                self._start_recording()
            else:
                self._stop_and_transcribe()

    def _cancel_recording(self):
        with self.lock:
            if self.is_streaming:
                log.info("❎ 取消 streaming")
                self._stop_streaming(cancel=True)
                return
            if self.is_recording:
                log.info("❎ 取消錄音")
                self.is_recording = False
                self.recorder.cancel()
                self._update_tray('idle')
                self._play_sound('cancel')
                self._hide_waveform()
            elif self.is_processing:
                log.info("⚠️  已送 API，無法取消")

    # ---------- Streaming 模式 ----------
    def _toggle_streaming(self):
        if self.is_recording or self.is_processing:
            self._notify_tray('請先結束一般錄音')
            return
        if self.is_streaming:
            self._stop_streaming()
        else:
            self._start_streaming()

    def _start_streaming(self):
        if not self.transcriber:
            self._msgbox_async(
                '金鑰尚未載入，無法使用 streaming。\n'
                '若你已填過 Key：等 3 秒再試一次即可。\n'
                '若還沒填：托盤右鍵 → 設定 → API Keys。')
            return
        log.info("⚡ Streaming 模式開始")
        self.is_streaming = True
        self._update_tray('recording')
        self._play_sound('start')

        # 建立 streaming recorder
        # 平衡：切分節奏快 + 避免噪音觸發幻覺
        self.streaming_recorder = StreamingRecorder(
            silence_threshold_rms=0.022,    # 提高: 12 → 22 (避免呼吸聲觸發)
            silence_seconds_to_flush=0.7,
            min_chunk_seconds=1.0,           # 提高: 0.6 → 1.0 (太短的段易幻覺)
            max_chunk_seconds=8.0,
        )
        # 套用使用者選的麥克風裝置
        self.streaming_recorder.device_name = (
            self.config_mgr.get('input_device', '') or None
        )

        # callbacks
        def on_chunk(wav_path):
            """從 worker thread 呼叫 — 同步轉錄"""
            try:
                if not self.transcriber:
                    return ''
                result = self.transcriber.transcribe(wav_path)
                text = (result.get('text') or '').strip()
                duration = result.get('duration_seconds', 0)
                # 用量記錄
                try:
                    self.usage_mgr.record_transcribe(
                        result.get('provider', 'openai'),
                        result.get('model', ''),
                        audio_seconds=duration,
                        input_tokens=result.get('input_tokens', 0),
                        output_tokens=result.get('output_tokens', 0),
                    )
                except Exception:
                    pass
                # 幻覺過濾
                if is_hallucination(text):
                    log.info(f"🚫 streaming 幻覺丟棄: {text}")
                    return ''
                return text
            except Exception as e:
                log.error(f"streaming chunk transcribe failed: {e}")
                return ''

        def on_text(text):
            """從 worker thread 呼叫 — 把文字貼到游標"""
            if not text:
                return
            log.info(f"⚡ {text}")
            try:
                # streaming 中不潤色 (避免延遲，且每段太短潤色效果不好)
                # 直接貼字 + 末尾加空白讓段落自然
                pyperclip.copy(text + ' ')
                time.sleep(0.05)
                keyboard.send('ctrl+v')
            except Exception as e:
                log.error(f"streaming paste failed: {e}")

        def on_volume(rms):
            if self.waveform:
                # 用 numpy 把 rms 包成假 chunk 餵給波形 (沿用現有 API)
                try:
                    import numpy as np
                    fake_chunk = np.array([rms * 0.5], dtype='float32')
                    self.waveform.update_volume(fake_chunk)
                except Exception:
                    pass

        self.streaming_recorder.on_chunk_ready = on_chunk
        self.streaming_recorder.on_text = on_text
        self.streaming_recorder.on_volume = on_volume

        try:
            self.streaming_recorder.start()
            streaming_hotkey = self.config_mgr.get('streaming_hotkey', 'ctrl+shift+l')
            self._show_waveform(
                'recording',
                label_text='Streaming 模式',
                hint_text=f'再按 {streaming_hotkey} 結束  ·  Ctrl+Shift+X 取消',
            )
        except Exception as e:
            log.error(f"streaming 啟動失敗: {e}")
            self.is_streaming = False
            self._update_tray('idle')
            self._msgbox_async(f'Streaming 啟動失敗: {e}')

    def _stop_streaming(self, cancel: bool = False):
        if not self.is_streaming:
            return
        log.info("⏹  Streaming 結束")
        self.is_streaming = False
        try:
            if cancel:
                self.streaming_recorder.cancel()
            else:
                self.streaming_recorder.stop()
        except Exception as e:
            log.error(f"stop streaming failed: {e}")
        self._play_sound('stop' if not cancel else 'cancel')
        self._update_tray('idle')
        self._hide_waveform()
        self.streaming_recorder = None


    def _start_recording(self):
        if not self.transcriber:
            # 自我修復：啟動瞬間若 .env 被鎖 (退出後立刻重開的 race)，
            # 金鑰可能沒讀到 → transcriber=None。使用者手動按錄音時 race 早結束，
            # 重讀一次金鑰再判斷，避免假性「尚未設定」。
            log.info('transcriber 未建立，嘗試重新讀取金鑰...')
            self._rebuild_transcriber()
            self._rebuild_enhancer()
        if not self.transcriber:
            self._msgbox_async(
                '金鑰尚未載入。\n若你已填過 Key：等 3 秒再按一次即可。\n'
                '若還沒填：托盤右鍵 → 設定 → API Keys。')
            return
        log.info("🎤 開始錄音")
        try:
            self.recorder.start(on_chunk=self._on_audio_chunk)
            self.is_recording = True
            self._update_tray('recording')
            self._play_sound('start')
            self._show_waveform('recording')
        except Exception as e:
            log.error(f"錄音啟動失敗: {e}")
            self.is_recording = False

    def _on_audio_chunk(self, chunk):
        if self.waveform:
            self.waveform.update_volume(chunk)

    def _stop_and_transcribe(self):
        log.info("⏹️  錄音結束")
        self.is_recording = False
        self.is_processing = True
        self._processing_since = time.time()
        self._update_tray('processing')
        self._play_sound('stop')

        audio_path = self.recorder.stop()
        if not audio_path:
            rms = getattr(self.recorder, 'last_rms', 0.0)
            log.info(f"⚠️  錄音過短或靜音 (RMS={rms:.5f})")
            self.is_processing = False
            self._update_tray('idle')
            self._hide_waveform()
            # 主動告訴使用者，不要無聲失敗
            if rms < 0.005:
                self._notify_tray(
                    '⚠ 沒收到聲音 — 檢查 F4 麥克風靜音鍵，'
                    '或到 設定 → 辨識 → 選擇麥克風並測試'
                )
            return

        self._show_waveform('processing')
        threading.Thread(
            target=self._process_audio, args=(audio_path,), daemon=True
        ).start()

    def _transcribe_with_retry(self, recovery_path, retries=2):
        """從 recovery_path 複製一份來轉錄 (transcribe 會刪掉輸入檔)。
        遇到連線/逾時錯誤自動重試，避免一次網路閃斷就讓整段錄音失敗。"""
        import shutil, tempfile, os as _os
        last_err = None
        for attempt in range(retries + 1):
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp.close()
            try:
                shutil.copy(str(recovery_path), tmp.name)
                return self.transcriber.transcribe(tmp.name)
            except Exception as e:
                last_err = e
                try:
                    if _os.path.exists(tmp.name):
                        _os.unlink(tmp.name)
                except Exception:
                    pass
                es = str(e).lower()
                transient = any(k in es for k in
                                ('connection', 'timeout', 'timed out',
                                 'network', 'temporarily', 'unavailable'))
                if attempt < retries and transient:
                    log.info(f'轉錄連線錯誤，2 秒後重試 ({attempt + 1}/{retries})')
                    time.sleep(2)
                    continue
                raise
        raise last_err

    def _process_audio(self, audio_path):
        t0 = time.time()
        import shutil
        # 先把錄音複製成「未送出」備份，網路斷導致轉錄失敗時不會整段遺失
        recovery = None
        try:
            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            recovery = RECORDINGS_DIR / f'unsent_{time.strftime("%Y-%m-%d_%H-%M-%S")}.wav'
            shutil.copy(audio_path, recovery)
        except Exception:
            recovery = None
        try:
            if recovery and recovery.exists():
                tr_result = self._transcribe_with_retry(recovery)
            else:
                tr_result = self.transcriber.transcribe(audio_path)
            text = tr_result.get('text', '')
            duration_s = tr_result.get('duration_seconds', 0.0)
            tr_model = tr_result.get('model', '')
            tr_provider = tr_result.get('provider', 'openai')
            tr_in_tok = tr_result.get('input_tokens', 0)
            tr_out_tok = tr_result.get('output_tokens', 0)

            # 記錄轉錄用量 (支援所有 provider)
            try:
                cost = self.usage_mgr.record_transcribe(
                    tr_provider, tr_model,
                    audio_seconds=duration_s,
                    input_tokens=tr_in_tok,
                    output_tokens=tr_out_tok,
                )
                log.info(f"💰 {tr_provider}/{tr_model} {duration_s:.1f}s 估算 ${cost:.4f}")
            except Exception as e:
                log.error(f"usage 記錄失敗: {e}")

            if not text or not text.strip():
                log.info("⚠️  未辨識到內容")
                return

            text = text.strip()
            if is_hallucination(text):
                log.info(f"🚫 幻覺丟棄: {text}")
                return

            raw_text = text
            elapsed = time.time() - t0
            log.info(f"✅ 辨識 ({elapsed:.1f}s): {text}")

            enhanced = None
            en_model = None
            en_provider = None
            if self.enhancer:
                log.info("✨ AI 潤色中")
                en_result = self.enhancer.enhance(text)
                enhanced = en_result.get('text', text)
                en_model = en_result.get('model', '')
                en_provider = en_result.get('provider', '')
                try:
                    in_tok = en_result.get('input_tokens', 0)
                    out_tok = en_result.get('output_tokens', 0)
                    if (in_tok or out_tok) and en_model:
                        cost = self.usage_mgr.record_enhance(en_provider, en_model, in_tok, out_tok)
                        log.info(f"💰 {en_provider}/{en_model} in={in_tok} out={out_tok} 估算 ${cost:.4f}")
                except Exception as e:
                    log.error(f"usage 記錄失敗: {e}")
                text = enhanced
                log.info(f"✨ 潤色: {text}")

            # 寫入歷史 (含模型資訊)
            if self.config_mgr.get('save_history', True):
                try:
                    profile = self.profile_mgr.active()
                    self.history_mgr.add(
                        raw=raw_text,
                        enhanced=enhanced,
                        language=self.config_mgr.get('language', 'zh'),
                        transcriber_provider=tr_provider,
                        transcriber_model=tr_model,
                        enhancer_provider=en_provider,
                        enhancer_model=en_model,
                        profile_id=profile.get('id'),
                        profile_name=profile.get('name'),
                    )
                except Exception as e:
                    log.error(f"歷史儲存失敗: {e}")

            # 自學詞典：比對 Whisper vs Claude 找出修正
            if enhanced and enhanced != raw_text:
                try:
                    profile = self.profile_mgr.active()
                    suggestions = self.learned_mgr.analyze(
                        raw_text, enhanced, profile.get('id', 'default')
                    )
                    if suggestions:
                        log.info(f"📖 自學偵測到新建議: {suggestions}")
                except Exception as e:
                    log.error(f"自學詞典失敗: {e}")

            if self.config_mgr.get('auto_paste', True):
                self._paste_text(text)
                log.info("📋 已貼上")
            else:
                pyperclip.copy(text)
                log.info("📋 已複製")

            # 成功了 → 刪掉未送出備份
            if recovery and recovery.exists():
                try:
                    recovery.unlink()
                except Exception:
                    pass

        except Exception as e:
            log.error(f"處理失敗: {e}")
            # 保留錄音備份，告訴使用者可用「匯入音檔」重跑，2 分鐘的話不會白講
            if recovery and recovery.exists():
                self._notify_tray(
                    f'網路問題轉錄失敗，錄音已保留：{recovery.name}。'
                    f'網路恢復後到「匯入音檔」選它重跑即可'
                )
            else:
                self._notify_tray(f'處理失敗: {str(e)[:60]}')
        finally:
            self.is_processing = False
            self._processing_since = None
            self._update_tray('idle')
            self._hide_waveform()

    def _paste_text(self, text):
        original = None
        if self.config_mgr.get('restore_clipboard', True):
            try:
                original = pyperclip.paste()
            except Exception:
                original = None
        pyperclip.copy(text)
        time.sleep(0.08)
        keyboard.send('ctrl+v')
        time.sleep(0.15)
        if original is not None:
            try:
                pyperclip.copy(original)
            except Exception:
                pass

    def _play_sound(self, event):
        if not self.config_mgr.get('play_sound', True):
            return
        try:
            import winsound
            if event == 'start':
                winsound.Beep(880, 80)
            elif event == 'stop':
                winsound.Beep(660, 80)
            elif event == 'cancel':
                winsound.Beep(440, 60)
                winsound.Beep(330, 80)
        except Exception:
            pass

    # ---------- Waveform overlay 控制 ----------
    def _show_waveform(self, mode, label_text=None, hint_text=None):
        if not self.config_mgr.get('show_waveform', True):
            return
        if not self.waveform:
            return
        def do_show():
            try:
                if mode == 'recording':
                    self.waveform.show_recording(
                        mode_label=label_text or '錄音中',
                        hint_text=hint_text,
                    )
                elif mode == 'processing':
                    self.waveform.show_processing()
            except Exception as e:
                log.error(f"waveform show failed: {e}")
        self.root.after(0, do_show)

    def _hide_waveform(self):
        if not self.waveform:
            return
        def do_hide():
            try:
                self.waveform.hide()
            except Exception:
                pass
        self.root.after(0, do_hide)

    # ---------- Tray icon ----------
    def _create_icon(self, state='idle'):
        size = 64
        image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        colors = {'idle': '#4CAF50', 'recording': '#F44336', 'processing': '#FF9800'}
        color = colors.get(state, '#4CAF50')
        draw.rounded_rectangle([22, 10, 42, 40], radius=10, fill=color)
        draw.arc([16, 22, 48, 50], start=0, end=180, fill=color, width=3)
        draw.rectangle([30, 46, 34, 54], fill=color)
        draw.rectangle([22, 54, 42, 58], fill=color)
        return image

    def _update_tray(self, state):
        if not self.tray_icon:
            return
        try:
            self.tray_icon.icon = self._create_icon(state)
            titles = {
                'idle': 'Voice Typer · 待機',
                'recording': 'Voice Typer · 錄音中',
                'processing': 'Voice Typer · 處理中',
            }
            self.tray_icon.title = titles.get(state, 'Voice Typer')
        except Exception:
            pass

    def _notify_tray(self, msg):
        try:
            if self.tray_icon:
                self.tray_icon.notify(msg, 'Voice Typer')
        except Exception:
            pass

    # ---------- Tray menu callbacks ----------
    def _open_settings(self, icon=None, item=None):
        self.root.after(0, self._open_settings_internal)

    def _open_settings_internal(self):
        try:
            if self.settings_window is not None and self.settings_window.winfo_exists():
                self.settings_window.lift()
                self.settings_window.focus_force()
                return
        except Exception:
            pass
        self.settings_window = SettingsWindow(
            self.root, self.config_mgr, self.env_mgr,
            profile_mgr=self.profile_mgr,
            learned_mgr=self.learned_mgr,
        )

    def _open_history(self, icon=None, item=None):
        self.root.after(0, self._open_history_internal)

    def _open_history_internal(self):
        try:
            if self.history_window is not None and self.history_window.winfo_exists():
                self.history_window.lift()
                self.history_window.focus_force()
                return
        except Exception:
            pass
        self.history_window = HistoryWindow(
            self.root, self.history_mgr,
            on_paste=self._paste_text,
        )

    def _open_usage(self, icon=None, item=None):
        self.root.after(0, self._open_usage_internal)

    def _open_usage_internal(self):
        try:
            if self.usage_window is not None and self.usage_window.winfo_exists():
                self.usage_window.lift()
                self.usage_window.focus_force()
                return
        except Exception:
            pass
        self.usage_window = UsageWindow(
            self.root, self.usage_mgr, BASE_DIR,
        )

    # ---------- 會議錄音 ----------
    def _open_meeting_history(self, icon=None, item=None):
        self.root.after(0, self._open_meeting_history_internal)

    def _open_meeting_history_internal(self):
        try:
            if self.meeting_history_window is not None and self.meeting_history_window.winfo_exists():
                self.meeting_history_window.lift()
                self.meeting_history_window.focus_force()
                return
        except Exception:
            pass
        self.meeting_history_window = MeetingHistoryWindow(
            self.root, RECORDINGS_DIR,
            on_open_meeting=self._open_meeting_result_from_history,
            on_import_file=self._import_meeting_pick_file,
        )

    def _open_meeting_result_from_history(self, item):
        """從歷史紀錄開啟 MeetingResultWindow"""
        result = {
            'transcript': item.get('transcript', ''),
            'meeting_title': item.get('meeting_title', ''),
            'summary': item.get('summary', {}),
            'decisions': item.get('decisions', []),
            'action_items': item.get('action_items', []),
            'keywords': item.get('keywords', []),
            'duration_seconds': 0,
        }
        try:
            # 試圖算 duration
            import soundfile as sf
            if item.get('wav_path'):
                info = sf.info(str(item['wav_path']))
                result['duration_seconds'] = info.frames / info.samplerate
        except Exception:
            pass
        self.meeting_result_window = MeetingResultWindow(
            self.root, result, wav_path=item.get('wav_path'),
        )

    def _start_meeting(self, icon=None, item=None):
        self.root.after(0, self._start_meeting_internal)

    def _start_meeting_internal(self):
        # 不能跟一般錄音同時
        if self.is_recording or self.is_processing or self.meeting_recorder.recording:
            self._notify_tray('已經在錄音中')
            return
        if not self.transcriber:
            self._msgbox_async(
                '金鑰尚未載入，無法開始會議錄音。\n'
                '若你已填過 Key：等幾秒再試一次。\n'
                '若還沒填：托盤右鍵 → 設定 → API Keys。')
            return

        # 開進度視窗
        self.meeting_progress_window = MeetingProgressWindow(
            self.root,
            on_stop=self._stop_meeting,
            on_cancel=self._cancel_meeting,
            on_pause=self._pause_meeting,
        )

        # 設定 recorder 的 progress callback (注意要丟到 tk thread 更新 UI)
        def on_progress(elapsed_s, file_bytes, rms):
            try:
                self.root.after(0, lambda: (
                    self.meeting_progress_window
                    and self.meeting_progress_window.winfo_exists()
                    and self.meeting_progress_window.update_progress(elapsed_s, file_bytes, rms)
                ))
            except Exception:
                pass
        self.meeting_recorder.on_progress = on_progress

        try:
            # 嘗試包含系統聲音 (WASAPI loopback)
            self.meeting_recorder.start(include_system_audio=True)
            log.info("🎬 會議錄音開始")
            self._update_tray('recording')
        except Exception as e:
            log.error(f"會議錄音啟動失敗: {e}")
            try:
                self.meeting_progress_window.destroy()
            except Exception:
                pass
            self._msgbox_async(f'會議錄音啟動失敗: {e}')

    def _pause_meeting(self, is_paused: bool):
        if is_paused:
            self.meeting_recorder.pause()
            log.info("⏸ 會議錄音暫停")
        else:
            self.meeting_recorder.resume()
            log.info("▶ 會議錄音繼續")

    def _stop_meeting(self):
        log.info("⏹ 會議錄音結束")
        mic_path, sys_path, duration = self.meeting_recorder.stop()
        if not mic_path:
            try:
                self.meeting_progress_window.destroy()
            except Exception:
                pass
            self._update_tray('idle')
            return

        # 切到處理中模式 (不關視窗)
        try:
            self.meeting_progress_window.switch_to_processing()
        except Exception:
            pass
        self._update_tray('processing')

        # 背景 thread 跑處理 (轉錄 + 摘要)
        thread = threading.Thread(
            target=self._process_meeting,
            args=(mic_path, sys_path, duration),
            daemon=True,
        )
        thread.start()

    def _cancel_meeting(self):
        log.info("✕ 會議錄音取消")
        self.meeting_recorder.cancel()
        self._update_tray('idle')

    # ---------- 匯入外部音檔 ----------
    def _import_meeting_dialog(self, icon=None, item=None):
        """托盤 → 匯入音檔（必須 marshal 回 tk thread 開檔案對話框）"""
        self.root.after(0, self._import_meeting_pick_file)

    def _import_meeting_pick_file(self):
        if self.is_recording or self.is_processing or self.meeting_recorder.recording:
            self._notify_tray('已經在錄音或處理中')
            return
        if not self.transcriber:
            self._msgbox_async(
                '金鑰尚未載入，無法處理音檔。\n'
                '若你已填過 Key：等幾秒再試一次。\n'
                '若還沒填：托盤右鍵 → 設定 → API Keys。')
            return

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title='匯入音檔 — 跑完整轉錄 + 摘要',
            filetypes=[
                ('音檔', '*.wav *.mp3 *.m4a *.ogg *.flac *.mp4 *.aac *.webm *.mpeg'),
                ('All files', '*.*'),
            ],
        )
        if not path:
            return

        # 開進度視窗（直接進入 processing 模式，沒有錄音階段）
        self.meeting_progress_window = MeetingProgressWindow(
            self.root, on_stop=None, on_cancel=None, on_pause=None,
        )
        try:
            self.meeting_progress_window.switch_to_processing()
            self.meeting_progress_window.title_lbl.configure(text='匯入音檔處理')
            self.meeting_progress_window.update_processing('讀取音檔...', 0.02)
        except Exception:
            pass
        self._update_tray('processing')

        thread = threading.Thread(
            target=self._process_imported_file,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def _process_imported_file(self, src_path):
        """匯入音檔 → 確保是 wav 格式 → 走完整流程"""
        try:
            wav_path = self._convert_import_to_wav(src_path)
            log.info(f"📂 匯入音檔 → {wav_path.name}")
            self._process_meeting(wav_path, None, 0)
        except Exception as e:
            log.exception(f"匯入處理失敗")
            def fail():
                try:
                    self.meeting_progress_window.destroy()
                except Exception:
                    pass
                show_message(
                    'Voice Typer - 匯入失敗',
                    f'無法處理音檔：\n\n{e}\n\n'
                    f'建議：先用 Audacity / 線上工具轉成 WAV 或 MP3 再試。'
                )
                self._update_tray('idle')
            self.root.after(0, fail)

    def _convert_import_to_wav(self, src_path):
        """把任意音檔轉成 wav 存到 recordings/

        策略：
        1. 已是 .wav → 複製
        2. soundfile 能讀（flac/ogg 等）→ 用 sf.read + sf.write
        3. 試 ffmpeg subprocess（mp3/m4a/mp4/aac）
        4. 都失敗 → raise
        """
        import shutil
        import soundfile as sf
        from pathlib import Path as _Path

        src_path = _Path(src_path)
        if not src_path.exists():
            raise FileNotFoundError(f'音檔不存在: {src_path}')

        ext = src_path.suffix.lower()
        timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        stem = f'meeting_import_{timestamp}'
        out_path = RECORDINGS_DIR / f'{stem}_mic.wav'
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

        # Step 1: 已是 wav → 複製
        if ext == '.wav':
            shutil.copy(str(src_path), str(out_path))
            return out_path

        # Step 2: soundfile 能讀
        try:
            data, sr = sf.read(str(src_path), dtype='float32', always_2d=False)
            if data.ndim > 1:
                data = data.mean(axis=1)
            sf.write(str(out_path), data, sr, subtype='PCM_16')
            return out_path
        except Exception as sf_err:
            log.info(f"soundfile 無法讀取（{ext}），改試 ffmpeg: {sf_err}")

        # Step 3: ffmpeg subprocess
        import subprocess
        ffmpeg_candidates = ['ffmpeg', 'ffmpeg.exe']
        last_err = None
        for ff in ffmpeg_candidates:
            try:
                subprocess.run(
                    [ff, '-y', '-i', str(src_path),
                     '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
                     str(out_path)],
                    check=True, capture_output=True, timeout=600,
                )
                return out_path
            except FileNotFoundError as e:
                last_err = e
                continue
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b'').decode('utf-8', errors='ignore')[:500]
                raise RuntimeError(f'ffmpeg 轉檔失敗: {stderr}')
            except Exception as e:
                last_err = e

        raise RuntimeError(
            f'無法讀取 {ext} 格式。\n'
            f'此格式需要 ffmpeg，但系統中找不到 ffmpeg。\n\n'
            f'解決方法：\n'
            f'• 用 Audacity / 線上工具轉成 WAV / MP3 / OGG / FLAC\n'
            f'• 或安裝 ffmpeg 並加入 PATH'
        )

    def _process_meeting(self, mic_path, sys_path, duration):
        try:
            if not self.transcriber:
                raise RuntimeError('transcriber 未設定')

            enhancer = self.enhancer
            if not enhancer:
                log.info("⚠️ 沒有 enhancer，將跳過摘要 (只產生逐字稿)")

            # 聲紋分離 — 需要 Google API key
            use_diar = self.config_mgr.get('use_speaker_diarization', False)
            google_key = self.env_mgr.get('GOOGLE_API_KEY') or ''
            if use_diar and (not google_key or 'your-' in google_key.lower()):
                log.info("⚠️ 開啟聲紋分離但未設定 GOOGLE_API_KEY，將略過聲紋功能")
                use_diar = False

            processor = MeetingProcessor(
                self.transcriber, enhancer,
                gemini_api_key=google_key if use_diar else None,
                gemini_model='gemini-2.5-flash',
            )

            def progress_cb(message, ratio):
                try:
                    self.root.after(0, lambda m=message, r=ratio: (
                        self.meeting_progress_window
                        and self.meeting_progress_window.winfo_exists()
                        and self.meeting_progress_window.update_processing(m, r)
                    ))
                except Exception:
                    pass

            result = processor.process(
                mic_path, sys_path,
                on_progress=progress_cb,
                use_diarization=use_diar,
            )
            if use_diar:
                log.info("🎙️ 已使用 Google Gemini 聲紋分離")

            # 寫到 recordings 旁的 txt + md
            try:
                mic_stem = Path(mic_path).stem.replace('_mic', '')
                base = RECORDINGS_DIR / mic_stem
                # 逐字稿
                (base.parent / f'{mic_stem}.transcript.txt').write_text(
                    result.get('transcript', ''), encoding='utf-8',
                )
                # 摘要 JSON
                import json as _json
                (base.parent / f'{mic_stem}.summary.json').write_text(
                    _json.dumps({
                        'meeting_title': result.get('meeting_title', ''),
                        'summary': result.get('summary', {}),
                        'decisions': result.get('decisions', []),
                        'action_items': result.get('action_items', []),
                        'keywords': result.get('keywords', []),
                    }, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
            except Exception as e:
                log.error(f'會議結果寫檔失敗: {e}')

            # 顯示結果視窗 (主 thread)
            wav_to_open = result.get('mixed_wav_path') or mic_path
            def open_result():
                try:
                    self.meeting_progress_window.destroy()
                except Exception:
                    pass
                self.meeting_result_window = MeetingResultWindow(
                    self.root, result, wav_path=wav_to_open,
                )
            self.root.after(0, open_result)
            log.info("✅ 會議轉錄+摘要完成")

        except Exception as e:
            log.exception(f"會議處理失敗")
            def fail():
                try:
                    self.meeting_progress_window.destroy()
                except Exception:
                    pass
                show_message(
                    'Voice Typer - 會議處理失敗',
                    f'{str(e)[:200]}\n\n錄音檔仍保留在 recordings/ 目錄，可手動重試',
                )
            self.root.after(0, fail)
        finally:
            self._update_tray('idle')

    def _toggle_ai_enhance(self, icon, item):
        current = self.config_mgr.get('enable_ai_enhance', False)
        if not current:
            # 嘗試啟用 → 確認有 key
            key = self.env_mgr.get('ANTHROPIC_API_KEY')
            if not key or key.startswith('sk-ant-your-'):
                self._notify_tray('請先在設定加入 ANTHROPIC_API_KEY')
                return
        self.config_mgr.set('enable_ai_enhance', not current)
        self.config_mgr.save()
        self._notify_tray(
            'AI 潤色已啟用' if not current else 'AI 潤色已關閉'
        )

    def _ai_enhance_checked(self, item):
        return self.enhancer is not None

    def _open_log(self, icon=None, item=None):
        try:
            os.startfile(str(LOG_FILE))
        except Exception:
            pass

    def _msgbox_async(self, text, error=False):
        """在獨立執行緒開原生訊息框，絕不阻塞呼叫者。
        托盤選單回呼跑在 pystray 執行緒、快捷鍵回呼跑在 keyboard hook 執行緒，
        若在這些執行緒直接開 MessageBox 會阻塞其訊息迴圈 → 視窗關不掉、
        甚至拖垮 keyboard 低階 hook 讓快捷鍵失效。丟到自己的執行緒就安全。"""
        threading.Thread(
            target=lambda: show_message('Voice Typer', text, error=error),
            daemon=True,
        ).start()

    def _show_about(self, icon=None, item=None):
        hotkey = self.config_mgr.get('hotkey', 'tab+`')
        cancel = self.config_mgr.get('cancel_hotkey', 'ctrl+alt+x')
        self._msgbox_async(
            f'Voice Typer v2.0\n\n'
            f'錄音/結束: {hotkey}\n'
            f'取消錄音: {cancel}\n\n'
            f'設定檔位置:\n{BASE_DIR}'
        )

    def _restart(self, icon=None, item=None):
        log.info('🔄 使用者要求重新啟動')
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        # 先釋放單一實例鎖，讓新程序拿得到
        try:
            import ctypes
            from app import bootstrap
            if getattr(bootstrap, '_instance_mutex', None):
                ctypes.windll.kernel32.CloseHandle(bootstrap._instance_mutex)
                bootstrap._instance_mutex = None
        except Exception:
            pass
        try:
            (BASE_DIR / 'heartbeat.txt').unlink(missing_ok=True)
            (BASE_DIR / 'voice-typer.pid').unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable],
                                 cwd=str(Path(sys.executable).parent))
            else:
                subprocess.Popen([sys.executable, str(BUNDLE_DIR / 'main.py')],
                                 cwd=str(BUNDLE_DIR))
        except Exception as e:
            log.error(f'重啟失敗: {e}')
        os._exit(0)

    def _state_watchdog(self):
        """每 30 秒巡檢：1) 卡在處理中 >5 分鐘 → 強制重設  2) 偵測睡醒 → 立刻重註冊快捷鍵"""
        now = time.time()
        try:
            if (self.is_processing and self._processing_since
                    and now - self._processing_since > 300):
                log.error('⏱ 處理逾時 (>5 分鐘)，強制重設狀態')
                self.is_processing = False
                self._processing_since = None
                self._update_tray('idle')
                self._hide_waveform()
                self._notify_tray('處理逾時已重設，請再按一次快捷鍵重新錄音')
            if now - self._last_wd_tick > 90:      # 時鐘跳躍 → 剛從睡眠喚醒
                log.info('💤 偵測到睡眠喚醒，立即重新註冊快捷鍵')
                self._register_hotkeys()
        except Exception as e:
            log.error(f'state watchdog: {e}')
        self._last_wd_tick = now
        self.root.after(30_000, self._state_watchdog)

    def _heartbeat_tick(self):
        try:
            (BASE_DIR / 'heartbeat.txt').write_text(str(time.time()), encoding='utf-8')
        except Exception:
            pass
        self.root.after(15_000, self._heartbeat_tick)

    def _quit(self, icon=None, item=None):
        log.info("👋 退出")
        try:
            (BASE_DIR / 'heartbeat.txt').unlink(missing_ok=True)
            (BASE_DIR / 'voice-typer.pid').unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if self.is_recording:
                self.recorder.stop()
        except Exception:
            pass
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        # 結束 tk mainloop
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass
        # 確保 process 退出
        self.root.after(500, lambda: os._exit(0))

    # ---------- 快捷鍵管理 (熱重載 + 自癒) ----------
    _MODIFIER_KEYS = ('ctrl', 'alt', 'shift', 'win', 'windows')

    @staticmethod
    def _combo_needs_suppress(combo: str) -> bool:
        """不含標準修飾鍵的組合（如 tab+`）→ 需要吞掉按鍵，否則會把字打進游標處。"""
        parts = [p.strip().lower() for p in combo.split('+') if p.strip()]
        return bool(parts) and not any(p in VoiceTyperApp._MODIFIER_KEYS for p in parts)

    def _register_hotkeys(self):
        """註冊全部快捷鍵。逐鍵獨立處理：一個壞掉不影響其他、更不會讓 app 退出。
        可重複呼叫（設定變更 / 看門狗）— 會先清掉舊的再註冊新的。
        """
        # 先清掉舊 hook (第一次呼叫時沒有，安全略過)
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        bindings = [
            ('錄音/結束', self.config_mgr.get('hotkey', 'tab+`'),
             self._toggle_recording),
            ('取消錄音', self.config_mgr.get('cancel_hotkey', 'ctrl+alt+x'),
             self._cancel_recording),
            ('Streaming', self.config_mgr.get('streaming_hotkey', 'ctrl+shift+l'),
             self._toggle_streaming),
        ]
        failed = []
        for name, combo, callback in bindings:
            combo = (combo or '').strip()
            if not combo:
                log.warning(f'快捷鍵「{name}」未設定，略過')
                continue
            try:
                suppress = (self.config_mgr.get('hotkey_suppress', True)
                            and self._combo_needs_suppress(combo))
                keyboard.add_hotkey(combo, callback, suppress=suppress)
                log.debug(f'快捷鍵註冊: {name} = {combo} (suppress={suppress})')
            except Exception as e:
                log.error(f'快捷鍵「{name}」({combo}) 註冊失敗: {e}')
                failed.append(f'{name} ({combo})')

        if failed:
            self._notify_tray(f'⚠ 快捷鍵註冊失敗: {"、".join(failed)}，請到設定修改')
        return not failed

    def _hotkey_watchdog(self):
        """每 2 分鐘重新註冊快捷鍵 — 修復睡眠喚醒後 keyboard hook 失效的問題"""
        try:
            self._register_hotkeys()
        except Exception as e:
            log.error(f'快捷鍵看門狗失敗: {e}')
        self.root.after(2 * 60 * 1000, self._hotkey_watchdog)

    # ---------- 啟動流程 ----------
    def _ensure_transcriber_ready(self):
        """安全網：若啟動瞬間 .env 被鎖導致沒讀到金鑰 (transcriber=None)，
        開機幾秒後 race 結束，自動重讀補建，使用者完全無感。"""
        if not self.transcriber:
            log.info('安全網：transcriber 仍未建立，重讀金鑰補建...')
            self._rebuild_transcriber()
            self._rebuild_enhancer()
            if self.transcriber:
                log.info('安全網：transcriber 已補建成功')

    def start(self):
        self._register_hotkeys()
        # 看門狗：2 分鐘後開始週期性自癒
        self.root.after(2 * 60 * 1000, self._hotkey_watchdog)
        # 安全網：開機 3 秒後若金鑰沒讀到 (race)，自動補建
        self.root.after(3000, self._ensure_transcriber_ready)

        # 建立 waveform overlay (隱藏，需要時 show)
        try:
            self.waveform = WaveformOverlay(self.root)
        except Exception as e:
            log.error(f"waveform init failed: {e}")
            self.waveform = None

        # 啟動 tray icon (background thread)
        threading.Thread(target=self._run_tray, daemon=True).start()

        log.info("=" * 50)
        log.info("🎙️  Voice Typer 已啟動 (商業版 v2)")
        log.info(f"   錄音/結束: {self.config_mgr.get('hotkey', 'tab+`')}")
        log.info(f"   取消錄音:  {self.config_mgr.get('cancel_hotkey', 'ctrl+alt+x')}")
        log.info(f"   AI 潤色:   {'開啟' if self.enhancer else '關閉'}")
        log.info(f"   資料目錄:  {BASE_DIR}")
        log.info("=" * 50)

        # 心跳：讓「第二個實例」能判斷本實例是否還活著
        try:
            (BASE_DIR / 'voice-typer.pid').write_text(str(os.getpid()), encoding='utf-8')
        except Exception:
            pass
        self.root.after(1000, self._heartbeat_tick)
        # 狀態看門狗：卡處理中自動重設 + 睡醒重註冊快捷鍵
        self.root.after(30_000, self._state_watchdog)

        # tk mainloop (主執行緒)
        self.root.mainloop()

    def _make_profile_switcher(self, pid):
        """產生符合 pystray callback 規範 (icon, item) 的 switcher"""
        def handler(icon, item):
            self._switch_profile(pid)
        return handler

    def _make_profile_checker(self, pid):
        """產生符合 pystray checked 規範 (item) 的 checker"""
        def checker(item):
            return pid == self.profile_mgr.active().get('id')
        return checker

    def _build_tray_menu(self):
        """重新建構 tray menu (切換 profile 後也要呼叫，刷新 checked 狀態)"""
        hotkey = self.config_mgr.get('hotkey', 'ctrl+shift+space')
        cancel_hotkey = self.config_mgr.get('cancel_hotkey', 'ctrl+shift+x')
        streaming_hotkey = self.config_mgr.get('streaming_hotkey', 'ctrl+shift+l')

        # Profile 子選單
        profile_items = []
        for p in self.profile_mgr.all():
            pid = p.get('id')
            name = p.get('name', pid)
            profile_items.append(
                pystray.MenuItem(
                    name,
                    self._make_profile_switcher(pid),
                    checked=self._make_profile_checker(pid),
                    radio=True,
                )
            )

        return pystray.Menu(
            pystray.MenuItem(
                f'開始/停止錄音  ({hotkey})',
                self._toggle_recording, default=True,
            ),
            pystray.MenuItem(
                f'取消錄音  ({cancel_hotkey})',
                self._cancel_recording,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f'情境: {self.profile_mgr.active().get("name", "")}',
                pystray.Menu(*profile_items),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f'⚡  Streaming 模式  ({streaming_hotkey})',
                self._toggle_streaming,
            ),
            pystray.MenuItem('🎬  開始會議錄音...', self._start_meeting),
            pystray.MenuItem('📂  匯入音檔處理...', self._import_meeting_dialog),
            pystray.MenuItem('📋  會議紀錄...', self._open_meeting_history),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('設定...', self._open_settings),
            pystray.MenuItem('歷史紀錄...', self._open_history),
            pystray.MenuItem('用量統計...', self._open_usage),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('開啟 log 檔', self._open_log),
            pystray.MenuItem('關於', self._show_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('🔄  重新啟動', self._restart),
            pystray.MenuItem('退出', self._quit),
        )

    def _run_tray(self):
        import time as _time
        backoff = 5
        while True:
            try:
                hotkey = self.config_mgr.get('hotkey', 'ctrl+shift+space')

                self.tray_icon = pystray.Icon(
                    'voice_typer',
                    self._create_icon('idle'),
                    'Voice Typer · 待機',
                    self._build_tray_menu(),
                )

                def on_ready(icon):
                    icon.visible = True
                    from app.runtime import boot_stage
                    boot_stage('tray-ready')
                    try:
                        icon.notify(
                            f'按 {hotkey} 開始錄音\n圖示在右下角 ^，可拖到工作列固定',
                            'Voice Typer 已啟動',
                        )
                    except Exception:
                        pass

                self.tray_icon.run(setup=on_ready)
                # run() 正常返回 = 使用者退出 → 跳出迴圈
                break
            except Exception as e:
                log.error(f'托盤執行緒異常，{backoff} 秒後重建: {e}')
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
                self.tray_icon = None
                _time.sleep(backoff)
                backoff = min(backoff * 2, 60)
