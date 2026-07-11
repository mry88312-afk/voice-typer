# 🎙️ Voice Typer

> 用 AI 取代鍵盤打字。Windows 全域熱鍵 → 講一段話 → 文字自動貼到游標位置。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

---

## ✨ 特色

- 🎤 **全域熱鍵打字** — 在任何視窗按 `Ctrl + Alt + Z` 開始錄音，再按一次結束，2-3 秒後文字自動出現（快捷鍵可自訂）
- 🔀 **多 Provider + 自動 Fallback** — OpenAI / Anthropic / Google / Groq，Groq 塞車自動切 OpenAI
- ⚡ **Streaming 模式** — 邊講邊出文字，VAD 自動切段
- 🎬 **會議錄音 + 摘要** — 一鍵錄完整會議，自動產生：會議標題、4 區塊摘要、決議、行動項目（含優先級 + 截止日）、關鍵字
- 🗣️ **聲紋分離** — 用 Gemini 標記說話者（`[Speaker 1]:` / `[Speaker 2]:`），跟 Whisper 文字做 fusion
- 📂 **匯入外部音檔** — 把 zoom 錄的 mp4 / 手機錄的 m4a 丟進來就轉錄 + 摘要
- 🎨 **6 個情境 Profile** — 一般 / 文案 / Email / Commit 訊息 / 翻譯 / 自訂，各自獨立 prompt
- 📖 **自學詞典** — diff Whisper vs Claude 結果，常重複的修正自動入詞典
- 💰 **用量統計** — 4 個 provider 分開計費，今日 / 本月 / 累計
- 📊 **會議紀錄歷史** — 過去所有會議卡片式列表，可重開摘要
- 🪟 **無 CMD 視窗** — 純系統托盤，Linear 風格深色 UI
- 💾 **資料隔離** — 所有設定 / log / 錄音存在 `%APPDATA%\VoiceTyper\`

---

## 📦 安裝

### 方法 A：一般使用者（推薦）

1. 到 [Releases](../../releases) 下載最新版 `VoiceTyper-vX.X-win-x64.zip`。
2. 解壓縮到任一資料夾。
3. 雙擊 `install.bat`（會複製到 `%LOCALAPPDATA%\Programs\VoiceTyper`、建立開機自啟動與桌面捷徑並啟動）。
4. 首次啟動出現設定精靈，填入至少一個 API Key。

移除：執行 `uninstall.bat`（個人設定與 Key 會保留在 `%APPDATA%\VoiceTyper`）。

### 方法 B：開發者（從原始碼跑）

```bash
git clone https://github.com/YOUR_USERNAME/voice-typer.git
cd voice-typer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 方法 C：自己 build .exe

```bash
build.bat
# 或手動：venv\Scripts\pyinstaller.exe voice_typer.spec --noconfirm
# → dist/VoiceTyper/VoiceTyper.exe
```

---

## 🔑 設定 API Key

首次啟動會跳 onboarding wizard，把 API key 貼進去就好。

**手動設定**：
1. 複製 `.env.example` 成 `.env`
2. 填入 key（至少要設一個轉錄 provider）

```ini
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GROQ_API_KEY=gsk_xxx          # 推薦！免費 + 超快
GOOGLE_API_KEY=AIza...        # 會議聲紋分離用
```

| Provider | 用途 | 免費額度 | 申請 |
|---|---|---|---|
| OpenAI | Whisper 轉錄 + GPT 潤色 | $5 試用 | [platform.openai.com](https://platform.openai.com/api-keys) |
| Anthropic | Claude 潤色 (Haiku/Sonnet/Opus) | $5 試用 | [console.anthropic.com](https://console.anthropic.com/keys) |
| Groq | Whisper Turbo + Llama (極快) | **完全免費** | [console.groq.com](https://console.groq.com/keys) |
| Google | Gemini 多模態 (聲紋分離) | 慷慨免費額度 | [aistudio.google.com](https://aistudio.google.com/apikey) |

---

## ⌨️ 預設熱鍵

| 熱鍵 | 動作 |
|---|---|
| `Ctrl + Alt + Z` | 開始 / 結束錄音 |
| `Ctrl + Alt + X` | 取消錄音 |
| `Ctrl + Shift + L` | Streaming 模式（邊講邊出文字）|

熱鍵可在「設定 → 快捷鍵」修改，並有「🎯 錄製」按鈕可直接按鍵錄製。
若你改用**無修飾鍵**的組合（如 `tab+\``），程式會自動「吞鍵」避免把字打進游標；若吞鍵造成輸入法異常，把 `%APPDATA%\VoiceTyper\config.json` 的 `"hotkey_suppress"` 改成 `false` 再重啟即可關閉。

托盤右鍵選單還有：開始會議錄音、匯入音檔、會議紀錄、設定、歷史紀錄、用量統計、🔄 重新啟動。

---

## 🏗️ 架構

```
┌─────────────────────────────────────────────┐
│  Tray icon + Global hotkey listener         │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  Recorder (sounddevice, WASAPI loopback)    │
│  ├─ Single-shot (壓住熱鍵)                  │
│  ├─ Streaming (VAD + chunk flush)           │
│  └─ Meeting (mic + system audio mixed)      │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  FallbackTranscriber                        │
│  ├─ Primary: Groq Whisper Turbo (3-4s)     │
│  └─ Secondary: OpenAI Whisper (動態 timeout)│
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  Enhancer (Claude / GPT / Gemini / Llama)   │
│  + 自學詞典 diff Whisper ↔ Claude          │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  auto-paste to cursor (preserve clipboard)  │
└─────────────────────────────────────────────┘
```

### 會議錄音特殊流程

```
Mic + System audio (WASAPI loopback)
     ↓ mix to single wav
切成 5 分鐘 chunks
     ↓
ASR + Diarization Fusion:
  Step 1. Groq Whisper → 高品質純文字
  Step 2. Gemini 讀音檔 + Whisper 文字 → 只標 [Speaker N]:
     ↓
整段逐字稿 → Claude 結構化摘要
  · meeting_title (10-25 字)
  · summary: overview / key_points / conclusions / next_steps
  · decisions: 拍板決議
  · action_items: title / detail / priority / assignee / deadline
  · keywords: 5-10 個
```

---

## 🛠️ 技術棧

- **Python 3.12** + **CustomTkinter** (深色 Linear 風 UI)
- **PyInstaller onedir** 打包成單一資料夾，無需 Python 環境
- **sounddevice** + **soundfile** 音訊錄製 (WASAPI loopback 抓系統聲)
- **keyboard** 全域熱鍵
- **pystray** + **PIL** 系統托盤
- **OpenAI** / **Anthropic** / **Google Gen AI** / **Groq** SDK
- **dotenv** 環境變數管理
- **pyperclip** 剪貼簿存取

### 設計亮點

- **Provider 抽象 + 註冊表**：新增 LLM provider 只要寫一個 class + register
- **動態 timeout fallback**：依音檔長度算 timeout (`10s + audio_secs × 0.6`)，短片段超時快、長會議寬鬆
- **AppData 持久化**：frozen 模式存 `%APPDATA%`，避免 PyInstaller `_MEI*` 重啟資料消失
- **ASR-Diarization fusion**：用 Whisper 的準確度 + Gemini 的聲紋能力
- **Whisper 幻覺黑名單**：30+ 已知 hallucination 字串 + 短 non-CJK 過濾
- **VAD 切段參數**：threshold 0.022, silence flush 0.7s, min chunk 1.0s

---

## 📂 檔案結構

```
voice-typer/
├── main.py                    入口點（--autostart 延遲啟動）
├── app/                       啟動 / 編排層
│   ├── bootstrap.py           單一實例鎖 + 殭屍接管 + 啟動流程
│   ├── application.py         主編排器（托盤 / 熱鍵 / 自癒看門狗）
│   ├── paths.py               路徑解析（一律 %APPDATA%\VoiceTyper）
│   └── runtime.py             logger / 訊息框 / 啟動麵包屑 / 例外掛勾
├── core/                      純業務邏輯
│   ├── recording/             recorder / streaming / meeting
│   ├── transcription/         fallback + providers/（openai/anthropic/google/groq）
│   ├── meeting/processor.py   會議轉錄 + ASR fusion + 摘要
│   ├── text/hallucinations.py Whisper 幻覺黑名單
│   └── hotkeys.py
├── data/                      健壯持久化（原子寫入 + 備份 + 重試）
│   ├── config.py env.py profiles.py history.py usage.py learned.py
│   └── store.py resources.py
├── resources/                 資料即設定（預設值 / provider / schema / 黑名單）
├── ui/                        CustomTkinter 視窗
│   ├── theme.py settings_window.py onboarding.py waveform.py
│   └── meeting_window.py meeting_history_window.py history_window.py usage_window.py
├── tools/migrate_merge_data.py  一次性資料合併腳本
├── installer/                 install.bat / uninstall.bat / 安裝說明.txt
├── build.bat                  一鍵重打包
├── restart-voice-typer.bat    桌面一鍵重啟
├── voice_typer.spec           PyInstaller spec (onedir)
├── requirements.txt
└── .env.example / config.example.json
```

---

## 📁 資料與設定位置

所有個人資料都放在 `%APPDATA%\VoiceTyper\`（不分 exe / 原始碼啟動，永遠同一份）：

| 檔案 | 內容 |
|---|---|
| `.env` | API Keys（只存本機，不上傳）|
| `config.json` | 設定、快捷鍵、情境 profile、詞彙表 |
| `history.json` / `usage.json` / `learned_words.json` | 歷史 / 用量 / 自學詞典 |
| `voice-typer.log` | 執行日誌（回報問題時附上）|
| `boot-stage.txt` | 最後一次啟動走到的階段（診斷開機卡死用）|
| `recordings/` | 會議 / 匯入的音檔 |

> 可用環境變數 `VOICE_TYPER_DATA_DIR` 覆寫資料目錄（測試 / 可攜用途）。

---

## 🛟 疑難排解

- **點了沒反應 / 打不開** → 雙擊桌面「Voice Typer」捷徑，或托盤右鍵 → 🔄 重新啟動。程式若還在跑，重複啟動會提示「已在執行中」而非默默失敗。
- **按快捷鍵沒反應（圖示還在）** → 睡眠喚醒後熱鍵可能暫時失效，看門狗約 2 分鐘會自動重註冊；等不及就托盤 → 重新啟動。
- **一直卡在「處理中」** → 逾時 5 分鐘會自動重設並通知，之後再按一次快捷鍵即可。
- **快捷鍵會把字打進游標 / 輸入法異常** → 預設 `Ctrl+Alt+Z` 不會有此問題；若你自訂成無修飾鍵組合（如 `tab+\``）需要吞鍵，遇到輸入法異常可把 `config.json` 的 `"hotkey_suppress"` 改 `false`，或改用含修飾鍵的快捷鍵（避開含 Space/Shift 的組合以免撞輸入法切換）。
- **一直要我重填 API Key** → 已修正（資料統一到 `%APPDATA%\VoiceTyper`）。若仍發生請回報。
- **如何回報** → 附上 `%APPDATA%\VoiceTyper\` 裡的 `voice-typer.log` 與 `boot-stage.txt`。

---

## 🔒 隱私聲明

- 錄音的**音訊**會送到 OpenAI / Groq / Google 做**轉錄**；轉出的**文字**會送到 Anthropic 做**潤色**。
- **API Key 只存在你自己電腦**的 `%APPDATA%\VoiceTyper\.env`，不會上傳到任何伺服器。
- 本專案不收集任何遙測 / 使用資料。

---

## 🗺️ Roadmap

- [ ] 本地 NPU Whisper（離線 / 隱私模式）
- [ ] macOS 支援
- [ ] 多語言 UI (en/ja)
- [ ] Whisper prompt 自動由詞典生成
- [ ] 會議錄音的 speaker name editing
- [ ] 匯出 Notion / Google Docs

---

## 📄 License

MIT © 2026 mry88 — 詳見 [LICENSE](LICENSE)

---

## 🙏 致謝

- [OpenAI](https://openai.com/) Whisper API
- [Anthropic](https://www.anthropic.com/) Claude API
- [Groq](https://groq.com/) Whisper Turbo (極快)
- [Google](https://ai.google.dev/) Gemini API
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) 現代 UI 框架
- 設計靈感：[Linear](https://linear.app/) 深色介面風格
