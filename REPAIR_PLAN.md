# Voice Typer 修復與通用化計畫（執行規格書）

> 產生日期：2026-07-10
> 依據：Claude 深度盤查（log 證據 + 現場實驗）+ 使用者確認的實際症狀
> 本文件寫給「執行 AI」逐字照做。每個任務都有：目的、改哪裡、怎麼改、怎麼驗證、commit 訊息。

---

## 0. 給執行 AI 的鐵則（每次開工前重讀一遍）

1. **工作目錄必須是 `C:\Users\mry88\voice-typer`**（實際運行的程式碼在這裡）。
   **絕對不要**在 git worktree 或 fresh clone 裡工作——git HEAD 是舊版程式，真正的新架構（`app/`、`core/`、`data/`、`resources/`）只存在於這個目錄且尚未 commit（Phase 0 會處理）。
2. **絕對不要**把 `.env` 的內容、API key 的值印到終端機、log、commit 訊息或任何檔案。檢查 key 存在與否只准用「key 名稱清單」或「值的長度/雜湊」。
3. **改檔前先讀檔**：每次修改前用讀取工具確認要改的程式碼片段真的存在且與本文件描述一致。如果不一致（可能程式已被改過），**停下來回報差異**，不要硬改。
4. **小步前進**：一次只完成一個任務（P?.?），完成立即 `git add -A && git commit -m "P?.?: <描述>"`，驗證通過才做下一個。
5. **每個 Phase 的「驗證」全數通過才能進入下一個 Phase。**驗證失敗時：先讀 log（位置見 §2），修復後重驗；連續兩次失敗就停下回報。
6. 使用者看得到的 UI 文字一律**繁體中文**。
7. 測試會啟動/殺掉 VoiceTyper 程序，這是正常操作；殺程序一律用 `taskkill /IM VoiceTyper.exe /F`（或指定 PID），啟動後等 10 秒再檢查 log。
8. Python 一律用專案 venv：`C:\Users\mry88\voice-typer\venv\Scripts\python.exe`（終端機直接打 `python` 可能不存在或指到別的版本）。

---

## 1. 問題 → 修法對照表

| 使用者的痛 | 根本原因（已證實） | 對應任務 |
|---|---|---|
| API KEY／資料有時有、有時沒有；明明填過 KEY 又要重填（歡迎精靈） | 三套資料世界：exe 用 `%APPDATA%\VoiceTyper\`，`python main.py` 用專案根目錄，Claude 暫存副本什麼都沒有→跳精靈 | Phase 1 全部 |
| 開機自動啟動後偶爾整個死掉；彈窗說「尚未設定 KEY」 | 開機登入瞬間 GUI 初始化卡死成殭屍（7/9 實例卡 27 小時、0 行 log）；字型偵測在無 root 時建臨時 `tk.Tk()` 是頭號嫌疑 | P2.1～P2.3 |
| 點捷徑重開完全沒反應，只能請 Claude 下指令 | 殭屍握著單一實例鎖；新實例偵測到鎖就**默默退出**（無任何提示）；托盤選單只有「退出」沒有「重新啟動」 | P2.4～P2.6 |
| 按快捷鍵沒反應（圖示還在） | keyboard hook 睡眠喚醒後失效（現有看門狗 10 分鐘一次，空窗太長）；或 app 卡在處理中 | P3.1、P3.2 |
| 托盤圖示不見了 | pystray 執行緒死掉／explorer 重啟後圖示不會自動回來，無自癒 | P3.3 |
| 卡在「處理中」、沒貼字 | API 呼叫無總體逾時；`is_processing` 卡 True 後快捷鍵被擋，永遠恢復不了 | P3.1 |
| 快捷鍵想改 Tab+~ | 目前預設 ctrl+alt+space；設定 UI 是手打文字無錄製；已實測 `tab+\`` 可註冊 | Phase 4 |
| 通用性（本機穩定唯一＋可裝到別台＋開源） | 程式碼未 commit、exe 是 6/23 快照、無安裝流程、README 過時 | Phase 0 + Phase 5 |

---

## 2. 現況事實（執行前必讀，2026-07-10 盤查結果）

- **實際在跑的**：`C:\Users\mry88\voice-typer\dist\VoiceTyper\VoiceTyper.exe`（PyInstaller onedir，2026-06-23 打包，exe 比所有原始碼新 → exe 行為 = 目前原始碼行為）。
- **開機自啟動**：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VoiceTyper.lnk` → 上述 exe，無參數。
- **資料位置**：
  - exe（frozen）→ `C:\Users\mry88\AppData\Roaming\VoiceTyper\`（`.env`、`config.json`、`history.json`、`usage.json`、`learned_words.json`、`voice-typer.log`、`recordings/`）。**這份是最新、最活躍的**。含 4 把 key（OPENAI/ANTHROPIC/GROQ/GOOGLE）。
  - 原始碼模式 → 專案根目錄另一份（只有 3 把 key、詞彙表 BNI/包租代管/王可信 只在這份、歷史停在 6/13）。
- **程式進入點**：`main.py`（791 bytes）→ `app/bootstrap.py: main()` → `app/application.py: VoiceTyperApp`。
- **單一實例**：named mutex `VoiceTyperSingleInstance`（`app/bootstrap.py`）。
- **log 位置**：跟資料同目錄的 `voice-typer.log`。正常啟動 1~3 秒內會寫「啟動檢查：…」與三行「快捷鍵註冊」。
- 舊版殘骸（`main_legacy.py`、`storage/`、根目錄的 `recorder.py` 等）與新架構並存，Phase 5 才清理。
- 2026-07-10 Claude 已經：殺掉 7/9 的殭屍程序（PID 10908）並重啟成功。目前系統運作中。

---

## Phase 0 — 快照與地基（防止一切災難的保險）

### P0.1 把現實 commit 進 git
- **目的**：目前 git HEAD 是舊版程式，實際運行的新架構完全沒進版控。先拍快照，之後每一步都可回滾。
- **做法**（在 `C:\Users\mry88\voice-typer`）：
  ```
  git add -A
  git status   # 檢視：應看到 app/ core/ data/ resources/ 新增、舊 bat/vbs 刪除等；不應出現 .env / config.json / history.json（.gitignore 擋掉）
  git commit -m "P0.1: snapshot 實際運行中的重構版 (app/core/data/resources 架構)"
  git tag snapshot-2026-07-10
  ```
- **驗證**：`git status` 乾淨；`git log --oneline -3` 看到快照 commit；`git show --stat HEAD | head -40` 包含 `app/bootstrap.py`。
- ⚠️ 若 `git status` 顯示 `.env` 或任何含 key 的檔案將被加入 → **停止**，先確認 `.gitignore` 有擋，回報。

### P0.2 安裝執行期依賴 psutil（後面殭屍接管要用）
- **做法**：
  ```
  venv\Scripts\pip.exe install psutil
  ```
  然後在 `requirements.txt` 加一行 `psutil`。
- **驗證**：`venv\Scripts\python.exe -c "import psutil; print(psutil.__version__)"` 有版本號。
- commit：`P0.2: 加入 psutil 依賴`

---

## Phase 1 — 資料統一（根治 KEY／資料時有時無）

### P1.1 讓「原始碼模式」也永遠使用 %APPDATA%\VoiceTyper
- **目的**：不管從哪裡啟動（exe、`python main.py`、任何副本/worktree），永遠只有一份資料 → 精靈不再亂跳、KEY 不再消失。
- **改哪裡**：`app/paths.py` 的 `_resolve_base_dir()`。
- **改成**（整個函式替換）：
  ```python
  def _resolve_base_dir() -> Path:
      """使用者資料一律放 %APPDATA%/VoiceTyper — 不分 frozen / source。
      這樣 exe、python main.py、任何程式碼副本永遠共用同一份設定，
      根治「兩套資料世界」造成的 KEY/設定時有時無。
      可用環境變數 VOICE_TYPER_DATA_DIR 覆寫（測試/可攜用途）。"""
      override = os.environ.get('VOICE_TYPER_DATA_DIR')
      if override:
          base = Path(override)
      else:
          appdata = os.environ.get('APPDATA')
          base = Path(appdata) / 'VoiceTyper' if appdata else Path.home() / '.voice-typer'
      base.mkdir(parents=True, exist_ok=True)
      return base
  ```
- **注意**：`BUNDLE_DIR` 那行**不要動**（程式資源仍從程式所在位置讀）。
- **驗證**：
  ```
  venv\Scripts\python.exe -c "from app.paths import BASE_DIR; import os; print(BASE_DIR); assert 'AppData' in str(BASE_DIR)"
  ```
- commit：`P1.1: BASE_DIR 一律使用 %APPDATA%/VoiceTyper（消滅雙資料世界）`

### P1.2 一次性合併舊資料（專案根目錄 → APPDATA）
- **目的**：專案根目錄那份資料有 APPDATA 沒有的東西（自訂詞彙 BNI/包租代管/王可信 等）。合併後把舊檔搬走，避免日後混淆。
- **做法**：新建 `tools/migrate_merge_data.py`，內容如下（完整照抄）：
  ```python
  """一次性資料合併：專案根目錄 → %APPDATA%/VoiceTyper。跑一次即可。
  策略：APPDATA 為主（最新）；只補「APPDATA 缺少」的 .env key 與 profile 詞彙。
  history/usage/learned 不自動合併（風險高、價值低），原檔搬進 legacy_backup/ 保留。"""
  import json, os, re, shutil, time
  from pathlib import Path

  PROJECT = Path(r'C:\Users\mry88\voice-typer')
  APPDATA = Path(os.environ['APPDATA']) / 'VoiceTyper'
  BACKUP = APPDATA / ('backup-' + time.strftime('%Y%m%d-%H%M%S'))
  LEGACY = PROJECT / 'legacy_backup'
  DATA_FILES = ['.env', 'config.json', 'history.json', 'usage.json',
                'learned_words.json', 'voice-typer.log']

  def read_env(p: Path) -> dict:
      d = {}
      if not p.exists():
          return d
      for line in p.read_text(encoding='utf-8-sig').splitlines():
          line = line.strip()
          if not line or line.startswith('#'):
              continue
          m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', line)
          if m:
              d[m.group(1)] = m.group(2).strip().strip('"').strip("'")
      return d

  def load_json(p: Path, default):
      try:
          return json.loads(p.read_text(encoding='utf-8'))
      except Exception:
          return default

  def main():
      assert APPDATA.exists(), 'APPDATA/VoiceTyper 不存在，中止（不該發生）'
      # 1. 備份 APPDATA 現況
      BACKUP.mkdir(parents=True)
      for name in DATA_FILES:
          src = APPDATA / name
          if src.exists():
              shutil.copy(str(src), str(BACKUP / name))
      print(f'[1/4] 已備份 APPDATA -> {BACKUP}')

      # 2. .env：補上專案有、APPDATA 沒有的 key（不覆蓋既有值）
      proj_env, app_env = read_env(PROJECT / '.env'), read_env(APPDATA / '.env')
      added = [k for k, v in proj_env.items()
               if k not in app_env and v and 'your-' not in v.lower()]
      if added:
          with open(APPDATA / '.env', 'a', encoding='utf-8') as f:
              f.write('\n# merged from project dir ' + time.strftime('%Y-%m-%d') + '\n')
              for k in added:
                  f.write(f'{k}={proj_env[k]}\n')
      print(f'[2/4] .env 合併，新增 key: {added if added else "無"}')

      # 3. config：APPDATA 為主，各 profile 詞彙取聯集；舊版頂層 vocabulary 併入 default
      pc = load_json(PROJECT / 'config.json', {})
      ac = load_json(APPDATA / 'config.json', {})
      ap = {p.get('id'): p for p in ac.get('profiles', [])}
      merged = {}
      for prof in pc.get('profiles', []):
          pid = prof.get('id')
          if pid in ap:
              old = list(ap[pid].get('vocabulary') or [])
              add = [w for w in (prof.get('vocabulary') or []) if w and w not in old]
              if add:
                  ap[pid]['vocabulary'] = old + add
                  merged[pid] = add
      top_vocab = [w for w in (pc.get('vocabulary') or []) if w]
      if top_vocab and 'default' in ap:
          old = list(ap['default'].get('vocabulary') or [])
          add = [w for w in top_vocab if w not in old]
          if add:
              ap['default']['vocabulary'] = old + add
              merged.setdefault('default', [])
              merged['default'] += add
      if merged:
          ac['profiles'] = list(ap.values())
          (APPDATA / 'config.json').write_text(
              json.dumps(ac, ensure_ascii=False, indent=2), encoding='utf-8')
      print(f'[3/4] 詞彙合併: {merged if merged else "無新增"}')

      # 4. 專案根目錄舊資料檔搬進 legacy_backup/（保留可救回，避免日後混淆）
      LEGACY.mkdir(exist_ok=True)
      moved = []
      for name in DATA_FILES + ['recordings']:
          src = PROJECT / name
          if src.exists():
              shutil.move(str(src), str(LEGACY / name))
              moved.append(name)
      print(f'[4/4] 已搬移專案舊資料 -> legacy_backup/: {moved}')
      print('完成。')

  if __name__ == '__main__':
      main()
  ```
- **執行**：`venv\Scripts\python.exe tools\migrate_merge_data.py`
- **驗證**：
  1. 輸出四步都成功；「新增 key」應包含無或少量 key 名稱（**不會**印值）。
  2. `venv\Scripts\python.exe -c "import json,os;from pathlib import Path;c=json.loads((Path(os.environ['APPDATA'])/'VoiceTyper'/'config.json').read_text(encoding='utf-8'));print([w for p in c['profiles'] for w in (p.get('vocabulary') or [])])"` → 應包含 `BNI`、`包租代管`、`王可信`。
  3. 專案根目錄不再有 `.env`、`config.json`（已在 `legacy_backup/`）。
- commit：`P1.2: 一次性合併專案資料到 APPDATA，舊檔搬入 legacy_backup/`（legacy_backup 含個資，確認 `.gitignore` 加上 `legacy_backup/` 再 commit）

### P1.3 啟動 log 印出資料目錄
- **改哪裡**：`app/application.py` 的 `start()`，找到「🎙️ Voice Typer 已啟動」那段 banner，在「AI 潤色」那行後面加一行：
  ```python
  log.info(f"   資料目錄:  {BASE_DIR}")
  ```
  檔案頂部若沒有 `from app.paths import BASE_DIR`（可能已 import 其他名稱），補上。
- **驗證**：`venv\Scripts\python.exe main.py` 跑 10 秒後結束它（托盤右鍵→退出），APPDATA 的 log 出現「資料目錄: C:\Users\mry88\AppData\Roaming\VoiceTyper」。
- commit：`P1.3: 啟動 banner 顯示資料目錄`

### Phase 1 整體驗收
1. `venv\Scripts\python.exe main.py` 啟動 → **不跳歡迎精靈**、設定裡四把 key 都是「已設定」、詞彙表有 BNI 等。
2. 退出後改用 `dist\VoiceTyper\VoiceTyper.exe` 啟動 → 看到**同一份**設定（同主題、同詞彙）。
3. 在設定裡隨便改一個開關並儲存 → 兩種啟動方式重啟後都看得到該變更。

---

## Phase 2 — 開機不再卡死 + 一鍵重開

### P2.1 啟動階段麵包屑（永久診斷儀表）
- **目的**：7/9 殭屍卡死時 0 行 log，無從得知卡在哪。加一個超輕量「階段檔」，任何一次卡死都能立刻知道卡在哪一步。
- **改哪裡**：`app/runtime.py` 加函式；`app/bootstrap.py`、`app/application.py` 插入呼叫。
- **`app/runtime.py`** 檔尾加：
  ```python
  def boot_stage(name: str):
      """寫入啟動階段麵包屑（覆寫式、絕不拋錯）。卡死時看這個檔就知道卡在哪一步。"""
      try:
          from app.paths import BASE_DIR
          import time as _t
          (BASE_DIR / 'boot-stage.txt').write_text(
              f'{name} {_t.strftime("%Y-%m-%d %H:%M:%S")}', encoding='utf-8')
      except Exception:
          pass
  ```
- **`app/bootstrap.py`** 的 `main()`：
  - 函式第一行（mutex 判斷之前）加：
    ```python
    from app.runtime import boot_stage
    # 上次啟動若沒走到 tray-ready，把卡點寫進 log（開機卡死的鐵證）
    try:
        _prev = (Path(str(ENV_FILE)).parent / 'boot-stage.txt')
        if _prev.exists():
            _s = _prev.read_text(encoding='utf-8').strip()
            if _s and not _s.startswith('tray-ready'):
                log.warning(f'上次啟動未完成，卡在階段: {_s}')
    except Exception:
        pass
    boot_stage('start')
    ```
    （檔頂已有 `from pathlib import Path`？沒有就補 `from pathlib import Path`。）
  - 在既有流程中依序插入：mutex 成功後 `boot_stage('mutex-ok')`；`ensure_user_data_initialized()` 後 `boot_stage('data-init')`；六個 store 建完後 `boot_stage('stores-ready')`；`init_app_theme()` 後 `boot_stage('theme-ok')`；`root = ctk.CTk()` 後 `boot_stage('tk-root-ok')`；onboarding 判斷 log 之後 `boot_stage('onboarding-checked')`；`app.start()` 前 `boot_stage('app-starting')`。
- **`app/application.py`** 的 `_run_tray()`：找到 `def on_ready(icon):`，在 `icon.visible = True` 之後加：
  ```python
  from app.runtime import boot_stage
  boot_stage('tray-ready')
  ```
- **驗證**：源碼啟動一次、正常退出 → `%APPDATA%\VoiceTyper\boot-stage.txt` 內容為 `tray-ready ...`。
- commit：`P2.1: 啟動階段麵包屑 + 上次卡死階段回報`

### P2.2 移除登入瞬間的臨時 Tk 建立（卡死頭號嫌疑）
- **目的**：`ui/theme.py get_font_family()` 在沒有 root 時會建臨時 `tk.Tk()`；bootstrap 又在 `ctk.CTk()` **之前**呼叫 `init_app_theme()` → 開機登入瞬間做兩次 Tk 初始化，正是最可疑的卡死點。
- **改法 A**：`ui/theme.py` 的 `get_font_family()`，把整個「建臨時 root」的 fallback 刪掉，改為：
  ```python
  try:
      import tkinter.font as tkfont
      families = set(tkfont.families())   # 需要已存在的 Tk root
  except Exception:
      families = set()                    # 沒有 root / 任何錯誤 → 直接用預設字型，絕不自建 Tk
  ```
  （保留後面的候選字型迴圈與 `'Microsoft JhengHei'` 最終 fallback，不動。）
- **改法 B**：`app/bootstrap.py` 把呼叫順序改為 root 先建、字型後設：
  - 找到：
    ```python
    init_app_theme()
    root = ctk.CTk()
    ```
  - 改成：
    ```python
    from ui.theme import init_ctk_default_font
    init_app_theme()          # 只設外觀模式/色系（不碰字型、不需要 root）
    root = ctk.CTk()
    init_ctk_default_font()   # root 已存在，字型偵測安全
    ```
  - 同時到 `ui/theme.py` 的 `init_app_theme()`，把裡面的 `init_ctk_default_font()` 那行**刪掉**（避免重複呼叫）。
- **驗證**：源碼啟動 → 設定視窗開起來字型仍是微軟正黑體（不是英文字型）；log 無錯誤。
- commit：`P2.2: 移除登入瞬間臨時 Tk 建立，字型初始化移到 root 建立之後`

### P2.3 自啟動延遲 25 秒（避開登入風暴）
- **目的**：開機登入瞬間系統忙碌是卡死溫床。自啟動時先睡 25 秒再初始化，手動啟動不受影響。
- **改哪裡**：`main.py`（791 bytes 那個入口檔），在 `from app.runtime import ...` **之前**加：
  ```python
  import sys, time
  if '--autostart' in sys.argv:
      # 開機自啟動：等桌面/服務就緒再初始化，避開登入瞬間的 GUI 卡死
      time.sleep(25)
  ```
  （注意：要放在所有 app 模組 import 之前，純標準庫，絕不會卡。）
- **更新自啟動捷徑加上參數**（PowerShell 一行）：
  ```powershell
  $ws = New-Object -ComObject WScript.Shell; $p = Join-Path ([Environment]::GetFolderPath('Startup')) 'VoiceTyper.lnk'; $lnk = $ws.CreateShortcut($p); $lnk.Arguments = '--autostart'; $lnk.Save(); (New-Object -ComObject WScript.Shell).CreateShortcut($p).Arguments
  ```
  輸出應為 `--autostart`。
- **驗證**：`dist` 還沒重打包，此參數在 P2.9 重打包後的重開機測試中一併驗證。先驗證源碼：`venv\Scripts\python.exe main.py --autostart` → 應停 25 秒才出托盤。
- commit：`P2.3: --autostart 延遲啟動 25 秒 + 捷徑加參數`

### P2.4 心跳檔 + 殭屍接管（點兩下永遠有反應）
- **目的**：現況是「殭屍握鎖 → 點捷徑默默退出」。改成：新實例發現舊實例**沒心跳** → 自動殺掉接管；**有心跳**（真的在跑）→ 跳出訊息告訴使用者。從此雙擊 exe 一定有結果。
- **(a) 心跳與 PID 檔**，`app/application.py`：
  - `start()` 裡（`self.root.mainloop()` 之前）加：
    ```python
    # 心跳：讓「第二個實例」能判斷本實例是否還活著
    import os as _os
    try:
        (BASE_DIR / 'voice-typer.pid').write_text(str(_os.getpid()), encoding='utf-8')
    except Exception:
        pass
    self.root.after(1000, self._heartbeat_tick)
    ```
  - 類別內新增方法：
    ```python
    def _heartbeat_tick(self):
        try:
            (BASE_DIR / 'heartbeat.txt').write_text(str(time.time()), encoding='utf-8')
        except Exception:
            pass
        self.root.after(15_000, self._heartbeat_tick)
    ```
    （`BASE_DIR` 沿用 P1.3 的 import；`time` 檔頂已有。）
  - `_quit()` 裡（`os._exit` 之前任意處）加：
    ```python
    try:
        (BASE_DIR / 'heartbeat.txt').unlink(missing_ok=True)
        (BASE_DIR / 'voice-typer.pid').unlink(missing_ok=True)
    except Exception:
        pass
    ```
- **(b) 接管邏輯**，`app/bootstrap.py`：把 `main()` 開頭的
  ```python
  if not _acquire_single_instance():
      log.info('偵測到已有實例在執行，本次啟動直接結束')
      sys.exit(0)
  ```
  整段替換為：
  ```python
  if not _acquire_single_instance():
      if _takeover_zombie_instance():
          log.warning('偵測到前一個實例無心跳（殭屍），已強制接管重啟')
      else:
          log.info('偵測到已有實例在執行且心跳正常，本次啟動結束')
          show_message(
              'Voice Typer',
              'Voice Typer 已經在執行中（右下角托盤）。\n\n'
              '如需重開：托盤圖示右鍵 → 重新啟動。',
              error=False,
          )
          sys.exit(0)
  ```
  並在 `_acquire_single_instance()` 函式後面新增：
  ```python
  def _takeover_zombie_instance() -> bool:
      """舊實例握著 mutex 但沒心跳 → 判定殭屍，殺掉接管。
      回傳 True = 已接管可繼續啟動；False = 對方活得好好的。"""
      import os, time
      from app.paths import BASE_DIR
      try:
          import psutil
      except Exception:
          return False    # 沒有 psutil 就不冒險殺程序
      try:
          hb = BASE_DIR / 'heartbeat.txt'
          hb_age = None
          if hb.exists():
              hb_age = time.time() - float(hb.read_text(encoding='utf-8').strip() or 0)
          if hb_age is not None and hb_age < 60:
              return False            # 心跳新鮮 → 真的在跑
          pid_file = BASE_DIR / 'voice-typer.pid'
          if not pid_file.exists():
              return False            # 不知道 PID，不冒險
          pid = int(pid_file.read_text(encoding='utf-8').strip())
          if pid == os.getpid():
              return False
          p = psutil.Process(pid)
          name = p.name().lower()
          if not any(s in name for s in ('voicetyper', 'python')):
              return False            # PID 已被別的程式重用
          if time.time() - p.create_time() < 90:
              return False            # 對方剛啟動（可能還在初始化），給它時間
          p.kill()
          p.wait(timeout=10)
          time.sleep(1)
          return True                 # 我們手上的 mutex handle 仍有效，直接繼續啟動
      except Exception:
          return False
  ```
- **驗證**（實驗劇本，逐字執行）：
  1. 啟動 app（源碼模式），等 20 秒（心跳已寫入）。
  2. 再開第二個：`venv\Scripts\python.exe main.py` → 應跳出「已經在執行中」訊息框，第二個結束，第一個不受影響。
  3. 模擬殭屍：`taskkill /F /IM python.exe` 之類**不可行**（會殺掉真的那個），改用：關掉 app（托盤退出）後，手動把 `%APPDATA%\VoiceTyper\heartbeat.txt` 寫成 `1`（很舊的時間戳）、`voice-typer.pid` 寫成一個不存在的 PID（如 99999），啟動 app → 應正常啟動（PID 不存在 → 不接管但 mutex 本來就沒人握 → 直接跑）。
  4. 真實殭屍測試在 P2.9 重開機驗收時觀察 log 的「已強制接管重啟」（若發生）。
- commit：`P2.4: 心跳/PID 檔 + 殭屍接管 + 已在執行提示（點擊必有回應）`

### P2.5 托盤選單加「🔄 重新啟動」
- **改哪裡**：`app/application.py`。
- **(a)** 檔頂 import 區確認有 `import subprocess`（沒有就加）。
- **(b)** 類別內新增方法（放 `_quit` 前面）：
  ```python
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
  ```
  （`sys`、`os`、`Path`、`BUNDLE_DIR` 若檔頂沒有就補 import：`from app.paths import BASE_DIR, BUNDLE_DIR`。）
- **(c)** `_build_tray_menu()` 裡，找到 `pystray.MenuItem('退出', self._quit)`，在它**上面**加一行：
  ```python
  pystray.MenuItem('🔄  重新啟動', self._restart),
  ```
- **驗證**：源碼啟動 → 托盤右鍵 → 重新啟動 → 托盤圖示消失又出現，log 出現「🔄 使用者要求重新啟動」+ 新的啟動 banner。
- commit：`P2.5: 托盤選單新增重新啟動`

### P2.6 桌面「重啟 Voice Typer」捷徑（最後保險，app 完全掛掉也能救）
- **做法**：
  1. 新建 `restart-voice-typer.bat`：
     ```bat
     @echo off
     chcp 65001 >nul 2>&1
     echo 正在重啟 Voice Typer...
     taskkill /IM VoiceTyper.exe /F >nul 2>&1
     timeout /t 2 /nobreak >nul
     start "" "C:\Users\mry88\voice-typer\dist\VoiceTyper\VoiceTyper.exe"
     ```
  2. 建桌面捷徑（PowerShell，自動處理 OneDrive 桌面重導向）：
     ```powershell
     $ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) '重啟 Voice Typer.lnk')); $lnk.TargetPath = 'C:\Users\mry88\voice-typer\restart-voice-typer.bat'; $lnk.WorkingDirectory = 'C:\Users\mry88\voice-typer'; $lnk.Save()
     ```
- **驗證**：雙擊桌面捷徑 → 閃過黑窗 → 托盤圖示出現、log 有新啟動 banner。
- commit：`P2.6: 桌面一鍵重啟捷徑`

### P2.9 重新打包 exe 並上線（讓 P1/P2 的修復真正生效於開機自啟動）
- **步驟**：
  1. `taskkill /IM VoiceTyper.exe /F`（忽略「找不到」錯誤）。
  2. 備份舊 exe：`ren dist\VoiceTyper VoiceTyper-backup-20260710`（用當天日期）。
  3. 確認 pyinstaller：`venv\Scripts\pyinstaller.exe --version`；若不存在 → `venv\Scripts\pip.exe install pyinstaller`。
  4. 打包：`venv\Scripts\pyinstaller.exe voice_typer.spec --noconfirm`（在專案根目錄執行）。
  5. 若打包失敗且錯誤與 `resources` 或新模組路徑有關 → 讀 `voice_typer.spec`，確認 `datas` 含 `resources` 目錄、`Analysis` 的腳本是 `main.py`；修正後重跑。若 spec 錯誤複雜 → 停下回報。
  6. 啟動驗證：`dist\VoiceTyper\VoiceTyper.exe` → 10 秒內托盤出現；log 的啟動 banner 有「資料目錄: ...AppData...」；`boot-stage.txt` = `tray-ready`。
  7. 測「已在執行中」：再雙擊一次 exe → 出現訊息框（不再默默消失）。
  8. 測托盤重啟、桌面重啟捷徑各一次。
- **驗證（重開機，需要使用者配合或由使用者擇時執行）**：重新開機 → 登入後 ~30 秒內托盤出現 → 按快捷鍵錄音貼字成功 → **沒有**任何要求填 KEY 的畫面。連續兩次重開機都通過才算過。
- commit：`P2.9: 重新打包 exe（P1+P2 修復上線）`

---

## Phase 3 — 執行中自癒（快捷鍵死／托盤消失／卡處理中）

### P3.1 狀態看門狗：卡在處理中 5 分鐘自動重設 + 睡醒自癒
- **改哪裡**：`app/application.py`。
- **(a)** `__init__` 的「狀態」區（`self.is_processing = False` 附近）加：
  ```python
  self._processing_since = None
  self._last_wd_tick = time.time()
  ```
- **(b)** `_stop_and_transcribe()` 裡 `self.is_processing = True` 之後加一行：
  ```python
  self._processing_since = time.time()
  ```
- **(c)** `_process_audio()` 的 `finally:` 區塊裡加一行：
  ```python
  self._processing_since = None
  ```
- **(d)** `start()` 裡（心跳啟動附近）加：`self.root.after(30_000, self._state_watchdog)`，並新增方法：
  ```python
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
  ```
- **驗證**：源碼啟動 → 錄一段音正常貼字（確認沒弄壞主流程）。逾時路徑驗證：暫時把 300 改成 15，錄音後立刻**拔掉網路**（或關 Wi-Fi）→ 15 秒~1 分鐘內收到「處理逾時已重設」通知、快捷鍵恢復可用 → 把 15 改回 300。
- commit：`P3.1: 處理逾時自動重設 + 睡醒立即重註冊快捷鍵`

### P3.2 快捷鍵看門狗 10 分鐘 → 2 分鐘
- **改哪裡**：`app/application.py`，搜尋 `10 * 60 * 1000`（有兩處：`start()` 的首次排程與 `_hotkey_watchdog()` 的續排），都改成 `2 * 60 * 1000`。
- **同時**把 `_register_hotkeys()` 裡的 `log.info(f'快捷鍵註冊: ...')` 改成 `log.debug(...)` 以免 log 每 2 分鐘刷三行（保留註冊失敗的 `log.error`）。改完後在 `start()` 原本印 banner 之前手動 log 一次目前快捷鍵（banner 本來就有，不用重複）。
- **驗證**：跑 5 分鐘，log **沒有**每 2 分鐘刷「快捷鍵註冊」，快捷鍵仍可用。
- commit：`P3.2: 快捷鍵看門狗縮短為 2 分鐘、降噪 log`

### P3.3 托盤自癒（執行緒死掉/圖示消失自動重建）
- **改哪裡**：`app/application.py` 的 `_run_tray()` 整個函式加自癒外環。把現有函式內容包進迴圈（保留原本建 icon 與 `run(setup=on_ready)` 的內容）：
  ```python
  def _run_tray(self):
      import time as _time
      backoff = 5
      while True:
          try:
              # ↓↓ 原本 _run_tray 的全部內容放這裡（建 self.tray_icon、on_ready、self.tray_icon.run(setup=on_ready)）↓↓
              ...
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
  ```
  ⚠️ 注意：`_quit()` 會呼叫 `tray_icon.stop()` 讓 `run()` 正常返回 → `break`，不會被誤判成異常。
- **驗證**：源碼啟動正常出托盤、退出正常（不會退了又自己長出來）。
- commit：`P3.3: 托盤異常自動重建`

### P3.4 例外可見化（背景執行緒/回呼壞掉不再無聲）
- **改哪裡**：`app/runtime.py` 檔尾加：
  ```python
  def install_global_excepthooks():
      """背景 thread 與 tk callback 的未捕捉例外 → 寫進 log（原本會無聲消失）。"""
      import threading
      def _th_hook(args):
          log.error('thread 未捕捉例外',
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
      threading.excepthook = _th_hook
  ```
  `app/bootstrap.py` 的 `main()` 開頭（boot_stage('start') 之後）加：
  ```python
  from app.runtime import install_global_excepthooks
  install_global_excepthooks()
  ```
  另外在 `root = ctk.CTk()` 之後加：
  ```python
  def _tk_error(exc, val, tb):
      log.error('tk callback 例外', exc_info=(exc, val, tb))
  root.report_callback_exception = _tk_error
  ```
- **驗證**：源碼啟動正常、退出正常即可。
- commit：`P3.4: 全域例外掛勾（背景錯誤寫入 log）`

### P3.5 小修包（盤查發現的次要缺陷）
- `data/env.py`：
  1. `read()` 與 `set()` 裡的 `open(..., encoding='utf-8')` 全改 `encoding='utf-8-sig'`（容忍記事本存出的 BOM，避免第一把 key 被無聲吃掉）。**寫入**維持 `utf-8` 不變。
  2. `__init__` 裡 `self.tmp_path = self.path.with_suffix('.env.tmp')` 改為
     `self.tmp_path = self.path.parent / (self.path.name + '.tmp')`（原寫法會產生 `.env.env.tmp`）。
- `app/application.py`：搜尋 `尚未設定 OPENAI_API_KEY`（兩處以上），訊息文字統一改為：
  `'金鑰尚未載入。\n若你已填過 Key：等 3 秒再按一次即可。\n若還沒填：托盤右鍵 → 設定 → API Keys。'`
- **驗證**：源碼啟動 → 設定裡四把 key 仍顯示「已設定」；錄音貼字正常。
- commit：`P3.5: env 讀取容 BOM、tmp 檔名修正、金鑰提示文案`

### Phase 3 整體驗收
1. 正常錄音貼字 ×3 次成功。
2. 拔網路錄音 → 逾時自動重設（用 P3.1 的暫時縮短法驗過即可）。
3. 電腦睡眠 → 喚醒 → 2 分鐘內快捷鍵可用（log 出現「偵測到睡眠喚醒」或看門狗重註冊）。

---

## Phase 4 — 快捷鍵改 Tab+`（使用者已確認：要吞掉按鍵）

### P4.1 註冊邏輯支援「吞鍵」
- **改哪裡**：`app/application.py` 的 `_register_hotkeys()`。
- 在函式上方（類別內或模組層）加：
  ```python
  _MODIFIER_KEYS = ('ctrl', 'alt', 'shift', 'win', 'windows')

  @staticmethod
  def _combo_needs_suppress(combo: str) -> bool:
      """不含標準修飾鍵的組合（如 tab+`）→ 需要吞掉按鍵，否則會把字打進游標處。"""
      parts = [p.strip().lower() for p in combo.split('+') if p.strip()]
      return bool(parts) and not any(p in VoiceTyperApp._MODIFIER_KEYS for p in parts)
  ```
- 把 `keyboard.add_hotkey(combo, callback)` 那行改為：
  ```python
  suppress = (self.config_mgr.get('hotkey_suppress', True)
              and self._combo_needs_suppress(combo))
  keyboard.add_hotkey(combo, callback, suppress=suppress)
  ```
  （`hotkey_suppress` 是逃生口：若使用者遇到輸入法/遠端桌面異常，把 config.json 裡的 `hotkey_suppress` 改 false 即可全域關閉吞鍵，不用改程式。）
- `resources/default_config.json` 加一行：`"hotkey_suppress": true,`（放在 hotkey 群組附近）。
- commit：`P4.1: 快捷鍵吞鍵支援（無修飾鍵組合自動 suppress + 逃生口設定）`

### P4.2 預設值與現有設定改為 tab+`
- `resources/default_config.json`：`"hotkey": "ctrl+alt+space"` → `"hotkey": "tab+\`"`（JSON 裡就是 `"tab+`"`，反引號不用跳脫）。
- `resources/settings_schema.json`：同欄位的 `"default"` 同步改。
- `ui/onboarding.py`：搜尋 `ctrl+shift+space` 與 `ctrl+alt+space`，把作為**預設 hotkey** 的字串改為 `tab+\``（只改預設值與示例文字，別動 cancel/streaming）。
- **現有設定**（使用者機器上已存在的 config.json 不吃 default）：
  ```
  venv\Scripts\python.exe -c "import json,os;from pathlib import Path;p=Path(os.environ['APPDATA'])/'VoiceTyper'/'config.json';c=json.loads(p.read_text(encoding='utf-8'));c['hotkey']='tab+`';c['hotkey_suppress']=True;p.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8');print('done', c['hotkey'])"
  ```
- **全域搜索殘留**：`grep -rn "ctrl+alt+space" --include=*.py --include=*.json .`（排除 legacy_backup、dist、venv、main_legacy.py、storage/）→ 出現在 fallback 預設值字串的地方（如 `config_mgr.get('hotkey', 'ctrl+alt+space')`）全部把 fallback 改成 `'tab+`'`。
- commit：`P4.2: 預設錄音快捷鍵改為 tab+`` `
- **驗證**：
  1. 啟動 → log/托盤選單顯示 `tab+``。
  2. 開記事本：按住 Tab 再按 ` → 開始錄音（嗶聲）且**記事本裡沒有多出 Tab 或 ` 字元**；再按一次 → 結束並貼字。
  3. 單獨按 Tab → 記事本正常跳格（沒被吃掉）。
  4. 開中文輸入法打一段字，中途按 Tab+` 錄音 → 無異常。
  5. 若第 2~4 項任何一項異常：把 config `hotkey_suppress` 改 false 重啟再測一次並記錄差異，回報使用者選擇。

### P4.3 設定視窗加「按鍵錄製」按鈕
- **改哪裡**：`ui/settings_window.py`。
- **(a)** 檔頂確認有 `import keyboard`、`import threading`（threading 已有）。
- **(b)** 類別內新增方法：
  ```python
  def _record_hotkey_into(self, entry, button):
      """按下按鈕後錄製下一個組合鍵，填入 entry。"""
      button.configure(text='請按組合鍵…', state='disabled')
      def worker():
          try:
              combo = keyboard.read_hotkey(suppress=False)
          except Exception:
              combo = None
          def done():
              button.configure(text='🎯 錄製', state='normal')
              if combo:
                  entry.delete(0, 'end')
                  entry.insert(0, combo)
          try:
              self.after(0, done)
          except Exception:
              pass
      threading.Thread(target=worker, daemon=True).start()
  ```
- **(c)** `_build_hotkey_tab()` 裡，三個 entry（`hotkey_entry`、`streaming_hotkey_entry`、`cancel_hotkey_entry`）每個旁邊加一顆按鈕。以 `hotkey_entry` 為例（其餘兩個依樣畫葫蘆，注意 row/column 配置與現有 grid 一致、不要蓋到既有元件——把 entry 的 `columnspan` 或欄位安排調整為 entry 佔 column 0、按鈕佔 column 1）：
  ```python
  rec_btn = ctk.CTkButton(parent, text='🎯 錄製', width=76, height=Tokens.HEIGHT_INPUT)
  rec_btn.configure(command=lambda e=self.hotkey_entry, b=None: None)  # 先建立
  rec_btn.configure(command=lambda e=self.hotkey_entry, b=rec_btn: self._record_hotkey_into(e, b))
  rec_btn.grid(row=3, column=1, padx=(4, Tokens.PAD_LG))
  ```
- **(d)** `_save_all()` 的快捷鍵區塊前加驗證：
  ```python
  # 快捷鍵語法驗證：打錯字直接擋下，不寫入
  for label, ent in (('錄音/結束', self.hotkey_entry),
                     ('取消錄音', self.cancel_hotkey_entry),
                     ('Streaming', self.streaming_hotkey_entry)):
      val = ent.get().strip()
      if val:
          try:
              keyboard.parse_hotkey(val)
          except Exception:
              self._show_message(f'✕ 快捷鍵「{label}」格式無效：{val}', 'danger')
              return
  ```
- **驗證**：開設定 → 快捷鍵分頁 → 按「🎯 錄製」→ 按 Ctrl+F9 → 欄位變 `ctrl+f9`；改回按 Tab+` → 欄位變 `tab+``；亂打 `abc++` 存檔 → 被擋下顯示錯誤。
- commit：`P4.3: 快捷鍵按鍵錄製 UI + 存檔前語法驗證`

### P4.9 重新打包 exe（同 P2.9 流程）
- 備份 `dist\VoiceTyper` → 打包 → 啟動驗證 P4.2 的五項 → commit：`P4.9: 重新打包（P3+P4 上線）`

---

## Phase 5 — 打包、安裝、開源（通用性）

### P5.1 清理舊版殘骸（先查引用再動手）
- **候選刪除**：`main_legacy.py`、`storage/`（整個資料夾）、根目錄的 `recorder.py`、`transcriber.py`、`enhancer.py`、`fallback_transcriber.py`、`streaming_recorder.py`、`meeting_recorder.py`、`meeting_processor.py`、`stderr_test.tmp`、`stdout_v2.tmp`、`stderr_v2.tmp`、`build_log.txt`。
- **規則**：對每個候選 X，先跑
  `grep -rn "import X\|from X" --include=*.py .`（排除 legacy_backup、venv、dist、build、main_legacy.py 自身與 storage/ 內部互引）。
  **零引用**才可刪；有引用 → 保留並在回報中列出。特別注意：`ui/` 和 `core/` 可能還 import 根目錄舊模組——有的話**不要刪**，記錄下來。
- 刪除採 `git rm`（在 git 保護下，可隨時救回）。
- **驗證**：`venv\Scripts\python.exe main.py` 完整啟動 + 錄音貼字一次成功。
- commit：`P5.1: 移除舊版殘骸（已確認零引用）`

### P5.2 build.bat（一鍵重打包，日後改完程式自己跑）
- 新建 `build.bat`：
  ```bat
  @echo off
  chcp 65001 >nul 2>&1
  cd /d "%~dp0"
  echo [1/4] 關閉執行中的 VoiceTyper...
  taskkill /IM VoiceTyper.exe /F >nul 2>&1
  echo [2/4] 備份舊版...
  if exist dist\VoiceTyper (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set D=%%a%%b%%c
    if exist dist\VoiceTyper-prev rmdir /s /q dist\VoiceTyper-prev
    ren dist\VoiceTyper VoiceTyper-prev
  )
  echo [3/4] PyInstaller 打包...
  venv\Scripts\pyinstaller.exe voice_typer.spec --noconfirm || (echo 打包失敗 & pause & exit /b 1)
  echo [4/4] 啟動新版...
  start "" "dist\VoiceTyper\VoiceTyper.exe"
  echo 完成。舊版保留在 dist\VoiceTyper-prev（確認新版正常後可刪）。
  pause
  ```
- **驗證**：跑一次 `build.bat` → 新 exe 啟動正常。
- commit：`P5.2: build.bat 一鍵打包`

### P5.3 安裝包（裝到其他電腦）
- 新建 `installer\install.bat`：
  ```bat
  @echo off
  chcp 65001 >nul 2>&1
  set DEST=%LOCALAPPDATA%\Programs\VoiceTyper
  echo 安裝 Voice Typer 到 %DEST% ...
  robocopy "%~dp0VoiceTyper" "%DEST%" /MIR /NFL /NDL /NJH /NJS
  if %ERRORLEVEL% GEQ 8 (echo 複製失敗 & pause & exit /b 1)
  powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $lnk=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'VoiceTyper.lnk')); $lnk.TargetPath=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper\VoiceTyper.exe'); $lnk.Arguments='--autostart'; $lnk.WorkingDirectory=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper'); $lnk.Save()"
  powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $lnk=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Voice Typer.lnk')); $lnk.TargetPath=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper\VoiceTyper.exe'); $lnk.WorkingDirectory=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper'); $lnk.Save()"
  echo 安裝完成，正在啟動（首次會出現設定精靈，請填入 API Key）...
  start "" "%DEST%\VoiceTyper.exe"
  pause
  ```
  以及 `installer\uninstall.bat`（taskkill → 刪兩個捷徑 → `rmdir /s /q %LOCALAPPDATA%\Programs\VoiceTyper` → 提示 `%APPDATA%\VoiceTyper` 個人資料保留、要刪自刪）。
- **打安裝 zip**：打包後把 `dist\VoiceTyper` 資料夾 + `installer\install.bat` + `installer\uninstall.bat` + 一頁 `安裝說明.txt`（步驟：解壓 → 雙擊 install.bat → 填 Key）壓成 `releases\VoiceTyper-v1.1-win-x64.zip`。
- **驗證**：在本機用 `VOICE_TYPER_DATA_DIR` 模擬新電腦：
  ```
  set VOICE_TYPER_DATA_DIR=C:\Users\mry88\AppData\Local\Temp\vt-fresh-test
  （解壓 zip 到暫存資料夾後執行其中的 VoiceTyper.exe）
  ```
  → 應跳出**歡迎精靈**（全新資料目錄）；填測試流程不必真填 key，確認精靈出現即關閉；刪掉暫存目錄與環境變數。
- commit：`P5.3: 安裝包（install/uninstall/說明）`
- ⚠️ 注意：**使用者自己這台**維持既有路徑（`C:\Users\mry88\voice-typer\dist\...` + 既有 Startup 捷徑），**不要**在本機跑 install.bat，避免出現兩份安裝。

### P5.4 README 重寫 + 開源上架
- `README.md` 重寫，必含章節：功能特色／系統需求／一般使用者安裝（下載 Release zip → install.bat → 填 Key）／開發者安裝（clone → venv → `pip install -r requirements.txt` → `python main.py`）／快捷鍵預設表（`tab+``、ctrl+alt+x、ctrl+shift+l）／資料與設定位置（`%APPDATA%\VoiceTyper`，含 log 位置）／疑難排解（打不開→桌面重啟捷徑；快捷鍵沒反應→等 2 分鐘自癒或托盤重啟；如何回報：附上 `voice-typer.log` 與 `boot-stage.txt`）／隱私聲明（音訊送 OpenAI/Groq/Google 轉錄、文字送 Anthropic 潤色；key 只存本機 .env）。
- `config.example.json`：用 `resources/default_config.json` 內容重新生成（去掉 `_comment`）。
- `.env.example`：確認四把 key 都有佔位（`OPENAI_API_KEY=sk-your-key-here` 格式）。
- 推上 GitHub：
  ```
  git push origin main
  git tag v1.1 && git push origin v1.1
  ```
  Release 上傳 zip：若 `gh` CLI 可用且已登入 → `gh release create v1.1 releases\VoiceTyper-v1.1-win-x64.zip --title "Voice Typer v1.1" --notes "穩定性大修：資料統一、開機防卡死、一鍵重啟、Tab+\` 快捷鍵"`；`gh` 不可用 → 回報使用者手動上傳。
- **推送前最後檢查**：`git log --all --oneline | head`、確認歷史與工作樹皆無 `.env`／key（`git grep -l "sk-" -- "*.py" "*.json" "*.md"` 應無真 key 命中）。
- commit：`P5.4: README/範本更新，開源發佈 v1.1`

---

## 6. 總驗收清單（全部打勾才算完工）

| # | 測試 | 通過標準 |
|---|---|---|
| 1 | 重開機 ×2 | 登入後 ~30 秒內托盤出現；無任何要求填 KEY 的畫面；`boot-stage.txt`=tray-ready |
| 2 | Tab+` 錄音 | 記事本中觸發錄音、結束貼字，無多餘 Tab/` 字元；單按 Tab 正常 |
| 3 | 點擊重開 | app 執行中雙擊 exe → 出現「已在執行中」提示；托盤「重新啟動」有效；桌面重啟捷徑有效 |
| 4 | 殭屍復原 | （若重開機遇到卡死）log 出現「已強制接管重啟」且 app 正常起來 |
| 5 | 資料唯一 | `python main.py` 與 exe 看到同一份設定/詞彙/歷史 |
| 6 | 斷網自癒 | 錄音後斷網 → 5 分鐘內重設通知，快捷鍵恢復 |
| 7 | 睡醒自癒 | 睡眠喚醒後 2 分鐘內快捷鍵有效 |
| 8 | 新機安裝 | zip + install.bat 在乾淨資料目錄跳出精靈（P5.3 模擬法） |
| 9 | GitHub | main 已推、v1.1 tag + Release zip、README 完整、無任何 key 洩漏 |

## 7. 回滾手冊

| 情境 | 動作 |
|---|---|
| 程式碼改壞 | `git log --oneline` 找上一個好 commit → `git revert <壞的>` 或 `git reset --hard <好的>`（reset 前先 `git stash`） |
| 全部想重來 | `git reset --hard snapshot-2026-07-10`（Phase 0 的 tag） |
| 新 exe 有問題 | 關程式 → `rmdir /s /q dist\VoiceTyper` → 把 `dist\VoiceTyper-backup-*`（或 `VoiceTyper-prev`）改名回 `dist\VoiceTyper` |
| 資料合併出錯 | 從 `%APPDATA%\VoiceTyper\backup-<時間戳>\` 把檔案複製回 `%APPDATA%\VoiceTyper\`；專案舊檔在 `legacy_backup/` |
| 吞鍵造成輸入法異常 | `%APPDATA%\VoiceTyper\config.json` 把 `"hotkey_suppress": true` 改 `false`，托盤 → 重新啟動 |
