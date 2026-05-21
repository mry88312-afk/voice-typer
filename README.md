# 🎙️ Voice Typer

> 用 AI 取代鍵盤打字。Windows 全域熱鍵 → 講一段話 → 文字自動貼到游標位置。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

---

## ✨ 特色

- 🎤 **全域熱鍵打字** — 在任何視窗按 `Ctrl + Alt + Space` 開始錄音，再按一次結束，2-3 秒後文字自動出現
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

### 方法 A：下載打包好的 .exe（推薦）

到 [Releases](../../releases) 下載最新版 `VoiceTyper-vX.X-win-x64.zip`，解壓後執行 `VoiceTyper.exe`。

### 方法 B：從原始碼跑

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
pip install pyinstaller
pyinstaller voice_typer.spec --noconfirm
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
| `Ctrl + Alt + Space` | 開始 / 結束錄音 |
| `Ctrl + Alt + X` | 取消錄音 |
| `Ctrl + Shift + L` | Streaming 模式（邊講邊出文字）|

托盤右鍵選單還有：開始會議錄音、匯入音檔、會議紀錄、設定、歷史紀錄、用量統計。

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
├── main.py                    主程式 (~1400 行)
├── recorder.py                單發錄音
├── streaming_recorder.py      Streaming VAD 錄音
├── meeting_recorder.py        會議錄音 (mic + system)
├── meeting_processor.py       會議轉錄 + ASR fusion + 摘要
├── transcriber.py             OpenAI Whisper (legacy)
├── enhancer.py                Claude (legacy)
├── fallback_transcriber.py    超時 fallback wrapper
├── providers/                 Provider 抽象 + 4 個實作
│   ├── base.py
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   ├── google_provider.py
│   └── groq_provider.py
├── storage/                   持久化管理
│   ├── config_manager.py
│   ├── env_manager.py
│   ├── history_manager.py
│   ├── usage_manager.py
│   ├── profile_manager.py
│   └── learned_words_manager.py
├── ui/                        CustomTkinter 視窗
│   ├── theme.py               色彩 token + 字型
│   ├── settings_window.py     7 個 tabs 設定
│   ├── onboarding.py          首次設定 wizard
│   ├── waveform.py            脈動波形 overlay
│   ├── meeting_window.py      會議進度 + 結果
│   ├── meeting_history_window.py
│   ├── history_window.py
│   └── usage_window.py
├── voice_typer.spec           PyInstaller spec (onedir)
├── requirements.txt
├── .env.example
└── config.json                預設 config
```

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
