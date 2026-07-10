"""FallbackTranscriber — primary 超時/失敗自動切 secondary。

動態 timeout：依音檔長度算 (10s 起 + 音檔秒數 × 0.6，封頂 180s)。
primary 會 unlink 檔案，所以先複製備份。
"""
import shutil
import threading
from pathlib import Path

import soundfile as sf


class FallbackTranscriber:
    def __init__(self, primary, secondary=None, logger=None):
        self.primary = primary
        self.secondary = secondary
        self.logger = logger
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
        try:
            info = sf.info(audio_file_path)
            audio_secs = info.frames / info.samplerate
        except Exception:
            audio_secs = 10
        return min(180.0, max(10.0, audio_secs * 0.6 + 8))

    def transcribe(self, audio_file_path):
        if not self.secondary:
            return self.primary.transcribe(audio_file_path)

        timeout = self._compute_timeout(audio_file_path)
        src = Path(audio_file_path)
        # 備份檔必須保留原始副檔名 (.wav)，否則 secondary API 會回「Invalid file format」
        backup = src.with_name(src.stem + '_fb' + src.suffix)
        try:
            shutil.copy(str(src), str(backup))
        except Exception:
            backup = None

        result = {}

        def _run():
            try:
                result['data'] = self.primary.transcribe(str(src))
            except Exception as e:
                result['error'] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if 'data' in result and not t.is_alive():
            if backup and backup.exists():
                try:
                    backup.unlink()
                except Exception:
                    pass
            return result['data']

        if t.is_alive():
            self._log(f'⚠ {self.primary.provider_id} 轉錄超過 {timeout:.0f}s，'
                      f'改用 {self.secondary.provider_id}')
            if not backup or not backup.exists():
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

        err = result.get('error')
        self._log(f'⚠ {self.primary.provider_id} 轉錄失敗 ({err})，'
                  f'改用 {self.secondary.provider_id}')
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
