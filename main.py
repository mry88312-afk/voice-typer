"""Voice Typer — 入口點。

架構分層 (各自獨立管理)：
  app/        啟動 / 編排層 (bootstrap, application orchestrator, paths)
  core/       純業務邏輯 (recording, transcription, meeting, text, hotkeys)
  data/       健壯持久化 (config/env/profiles 原子寫入+備份+重試)
  resources/  資料即設定 (預設值、provider、schema — 改設定不用改 code)
  ui/         介面層 (視窗、主題、波形)
"""
import sys

from app.runtime import log, show_message
from app.bootstrap import main


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        log.exception('未預期錯誤')
        show_message('Voice Typer - 未預期錯誤', str(e))
        sys.exit(1)
