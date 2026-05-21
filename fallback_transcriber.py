"""FallbackTranscriber — primary 超時/失敗 → 自動跑 secondary

設計：
- 動態 timeout：依音檔長度算（基準 10s + 音檔秒數 × 60%，最多 180s）
- 短音檔（streaming 1-3s）→ timeout 約 10-12s
- 中音檔（單發 5-30s）→ timeout 約 11-26s
- 長音檔（會議 5min）→ timeout 約 180s（給足時間，幾乎不會 fallback）
- primary 會 unlink 檔案，所以先複製一份備用
"""
import shutil
import threading
from pathlib import Path

import soundfile as sf


class FallbackTranscriber:
    """Primary transcriber 超時/失敗自動切到 secondary。

    對外保持跟 TranscriberBase 一樣的 transcribe(path) -> dict 介面，
    並 forward primary 的 provider_id / model / language / prompt 給 usage 統計用。
    """

    def __init__(self, primary, secondary=None, logger=None):
        self.primary = primary
        self.secondary = secondary
        self.logger = logger
        # 對外身分以 primary 為主（usage 統計 + UI 顯示）
        self.provider_id = primary.provider_id
        self.model = primary.model
        self.language = getattr(primary, 'language', 'auto')
        self.prompt = getattr(primary, 'prompt', '')

    def _log(self, msg):
        if self.logger:
            try:
                self.logger.warning(msg)
                return
            except Exception:
                pass
        print(msg)

    def _compute_timeout(self, audio_file_path):
        """動態 timeout：10s 起跳 + 音檔秒數 × 0.6，封頂 180s"""
        try:
            info = sf.info(audio_file_path)
            audio_secs = info.frames / info.samplerate
        except Exception:
            audio_secs = 10
        return min(180.0, max(10.0, audio_secs * 0.6 + 8))

    def transcribe(self, audio_file_path):
        # 沒 secondary 直接走 primary
        if not self.secondary:
            return self.primary.transcribe(audio_file_path)

        timeout = self._compute_timeout(audio_file_path)

        # 先複製一份，因為 primary 的 finally 會 unlink 原檔
        src = Path(audio_file_path)
        backup = src.with_suffix(src.suffix + '.fb')
        try:
            shutil.copy(str(src), str(backup))
        except Exception:
            backup = None

        # 在 thread 跑 primary，主 thread 等 timeout
        result = {}

        def _run():
            try:
                result['data'] = self.primary.transcribe(str(src))
            except Exception as e:
                result['error'] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout)

        # Primary 成功
        if 'data' in result and not t.is_alive():
            if backup and backup.exists():
                try:
                    backup.unlink()
                except Exception:
                    pass
            return result['data']

        # Primary 還在跑 → 超時
        if t.is_alive():
            self._log(
                f'⚠ {self.primary.provider_id} 轉錄超過 {timeout:.0f}s，'
                f'改用 {self.secondary.provider_id}'
            )
            # 注意：primary thread 還在跑且最後會 unlink src，但我們有 backup
            if not backup or not backup.exists():
                # 沒備份只能繼續等 primary
                t.join()
                if 'data' in result:
                    return result['data']
                raise result.get('error') or RuntimeError('primary timeout')
            try:
                return self.secondary.transcribe(str(backup))
            finally:
                if backup.exists():
                    try:
                        backup.unlink()
                    except Exception:
                        pass

        # Primary thread 結束但帶 error → 走 secondary
        err = result.get('error')
        self._log(
            f'⚠ {self.primary.provider_id} 轉錄失敗 ({err})，'
            f'改用 {self.secondary.provider_id}'
        )
        if not backup or not backup.exists():
            raise err or RuntimeError('primary failed and no backup')
        try:
            return self.secondary.transcribe(str(backup))
        finally:
            if backup.exists():
                try:
                    backup.unlink()
                except Exception:
                    pass
