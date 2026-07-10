"""會議錄音後處理 — 分段轉錄 + 摘要"""
import json
import tempfile
import time
from datetime import datetime
from pathlib import Path
import numpy as np
import soundfile as sf


# 每段最大 5 分鐘 (Whisper API 限制 25MB，wav 16kHz mono ~ 1.92MB/min)
CHUNK_SECONDS = 300


class MeetingProcessor:
    """把錄音 → 分段 → Whisper 轉錄 → Claude 摘要

    diarization=True 時用 Google Gemini 直接讀 audio，輸出 [Speaker N]: ... 格式
    """

    def __init__(self, transcriber, enhancer, gemini_api_key=None, gemini_model=None):
        self.transcriber = transcriber
        self.enhancer = enhancer
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model or 'gemini-2.5-flash'

    def process(self,
                mic_wav_path: Path,
                sys_wav_path: Path = None,
                on_progress=None,
                use_diarization: bool = False):
        """
        on_progress(message, ratio) — message 是中文狀態，ratio 是 0~1
        回傳: dict(transcript, summary, action_items, keywords, mixed_wav_path)
        """
        result = {
            'transcript': '',
            'meeting_title': '',
            'summary': {
                'overview': '',
                'key_points': [],
                'conclusions': [],
                'next_steps': [],
            },
            'decisions': [],
            'action_items': [],
            'keywords': [],
            'mixed_wav_path': None,
            'duration_seconds': 0,
        }

        # 1. 合成單一 wav (麥克風 + 系統聲音 if any)
        if on_progress:
            on_progress('準備音檔...', 0.05)
        target_wav = self._prepare_audio(mic_wav_path, sys_wav_path)
        result['mixed_wav_path'] = target_wav

        # 2. 算總時長
        try:
            info = sf.info(str(target_wav))
            result['duration_seconds'] = info.frames / info.samplerate
        except Exception:
            pass

        # 3. 分段
        if on_progress:
            on_progress('分段音檔...', 0.10)
        chunks = self._split_wav(target_wav, CHUNK_SECONDS)

        # 4. 逐段轉錄 (聲紋分離 or 一般 Whisper)
        transcripts = []
        for i, chunk_path in enumerate(chunks):
            if on_progress:
                ratio = 0.15 + (0.65 * (i / max(1, len(chunks))))
                action = '聲紋辨識' if use_diarization else '轉錄'
                on_progress(f'{action}第 {i+1}/{len(chunks)} 段...', ratio)
            try:
                if use_diarization and self.gemini_api_key:
                    text = self._transcribe_with_speakers(chunk_path)
                else:
                    tr = self.transcriber.transcribe(str(chunk_path))
                    text = tr.get('text', '').strip()
                if text:
                    transcripts.append(text)
            except Exception as e:
                print(f"chunk {i} transcribe failed: {e}")
            finally:
                try:
                    chunk_path.unlink()
                except Exception:
                    pass

        full_text = '\n\n'.join(transcripts)
        result['transcript'] = full_text

        # 5. 摘要
        if self.enhancer and full_text.strip():
            if on_progress:
                on_progress('整理摘要與行動項目...', 0.85)
            try:
                summary_data = self._summarize(full_text, result['duration_seconds'])
                result['meeting_title'] = summary_data.get('meeting_title', '') or ''
                summary_obj = summary_data.get('summary')
                if isinstance(summary_obj, dict):
                    result['summary'] = {
                        'overview': summary_obj.get('overview', '') or '',
                        'key_points': summary_obj.get('key_points', []) or [],
                        'conclusions': summary_obj.get('conclusions', []) or [],
                        'next_steps': summary_obj.get('next_steps', []) or [],
                    }
                elif isinstance(summary_obj, list):
                    # 舊格式 fallback：扁平 list → 全塞 key_points
                    result['summary'] = {
                        'overview': '',
                        'key_points': [str(x) for x in summary_obj],
                        'conclusions': [],
                        'next_steps': [],
                    }
                result['decisions'] = summary_data.get('decisions', []) or []
                result['action_items'] = summary_data.get('action_items', []) or []
                result['keywords'] = summary_data.get('keywords', []) or []
            except Exception as e:
                print(f"summarize failed: {e}")

        if on_progress:
            on_progress('完成', 1.0)

        return result

    # ---------- internal ----------
    def _prepare_audio(self, mic_path: Path, sys_path: Path = None) -> Path:
        """若有系統聲音，與麥克風 mix 成單一 wav；否則回傳原 mic 路徑"""
        if not sys_path or not Path(sys_path).exists():
            return Path(mic_path)

        try:
            # 讀兩個 wav，逐 sample mix (除以 2 避免 clip)
            mic_data, sr = sf.read(str(mic_path), dtype='float32')
            sys_data, sr2 = sf.read(str(sys_path), dtype='float32')
            if sr != sr2:
                # samplerate 不同 → 跳過 mix，只用 mic
                return Path(mic_path)
            # 對齊長度 (取短)
            n = min(len(mic_data), len(sys_data))
            mixed = (mic_data[:n] + sys_data[:n]) * 0.5
            # 確保不爆 (clip 到 [-1, 1])
            mixed = np.clip(mixed, -1.0, 1.0)

            out_path = Path(mic_path).with_name(
                Path(mic_path).stem.replace('_mic', '_mixed') + '.wav'
            )
            sf.write(str(out_path), mixed, sr, subtype='PCM_16')
            return out_path
        except Exception as e:
            print(f"mix failed, fallback to mic: {e}")
            return Path(mic_path)

    def _transcribe_with_speakers(self, chunk_path: Path) -> str:
        """ASR + Speaker Diarization Fusion

        策略：
        1. 用主 transcriber (Groq / Whisper 等) 取得高品質純文字
        2. 把音檔 + 高品質文字一起餵給 Gemini，只要它做 speaker labeling
        3. 如果第 1 步失敗，fallback 到純 Gemini 轉錄

        好處：拿到「Whisper 的準確度 + Gemini 的聲紋能力」
        """
        from google import genai
        from google.genai import types

        # ----- Step 1: 高品質轉錄 (用主 transcriber，例如 Groq Whisper) -----
        whisper_text = ''
        if self.transcriber:
            try:
                # 複製一份給 transcriber 用 (因為 transcriber 會 unlink 檔案)
                import shutil
                temp_for_asr = chunk_path.with_suffix('.asr.wav')
                shutil.copy(chunk_path, temp_for_asr)
                asr = self.transcriber.transcribe(str(temp_for_asr))
                whisper_text = (asr.get('text') or '').strip()
            except Exception as e:
                print(f"fusion: ASR step failed, fallback to Gemini-only: {e}")

        # 讀音檔 bytes (給 Gemini)
        try:
            with open(chunk_path, 'rb') as f:
                audio_bytes = f.read()
        except Exception as e:
            print(f"read audio failed: {e}")
            return whisper_text   # 至少回 Whisper 的結果

        client = genai.Client(api_key=self.gemini_api_key)

        # ----- Step 2: Gemini 做 speaker labeling -----
        if whisper_text:
            # 融合模式：給 Gemini 文字作為 reference，只要它分 speaker
            instruction = (
                '你會收到一段會議音訊，以及它已經被 ASR 模型 (Whisper) 轉好的高品質繁中文字。\n\n'
                '【已轉好的文字 (請當作 ground truth，不要重寫不要修錯字)】\n'
                f'{whisper_text}\n\n'
                '【你的任務】\n'
                '聆聽音訊，把上面的文字「依說話者」切段，每段開頭加 [Speaker 1]: / [Speaker 2]: ...\n\n'
                '【嚴格規則】\n'
                '1. 文字內容 100% 保留，連標點都不動 (即使你覺得有錯也保留)\n'
                '2. 只能加 [Speaker N]: 標籤跟換行\n'
                '3. 同一人連續說話放同一段，不要每句都新標籤\n'
                '4. 不要加 markdown、不要解釋、不要加多餘文字\n'
                '5. 第一個字必須是 [\n\n'
                '【範例】\n'
                '輸入文字: 我覺得這個方案不錯，同意，下週開始。\n'
                '輸出：\n'
                '[Speaker 1]: 我覺得這個方案不錯，\n'
                '[Speaker 2]: 同意，下週開始。\n\n'
                '直接輸出標記後的文字：'
            )
        else:
            # Fallback：純 Gemini 轉錄 + 標記
            instruction = (
                '請仔細聆聽以下會議錄音，辨識其中所有不同的說話者。\n'
                '輸出格式要求：\n'
                '1. 每一段對話開頭用 [Speaker 1]: / [Speaker 2]: ... 標註說話者\n'
                '2. 用繁體中文輸出，加入完整標點符號\n'
                '3. 不要加任何說明、不要 markdown\n\n'
                '直接輸出：'
            )

        try:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    instruction,
                    types.Part.from_bytes(data=audio_bytes, mime_type='audio/wav'),
                ],
            )
            gemini_output = (response.text or '').strip()
        except Exception as e:
            print(f"fusion: Gemini step failed: {e}")
            return whisper_text  # fallback: 至少回 Whisper 結果

        # 驗證 Gemini 是否有正確輸出 [Speaker N]: 格式
        if '[Speaker' in gemini_output:
            return gemini_output
        # 如果 Gemini 沒按格式輸出，至少有 Whisper 結果
        return whisper_text or gemini_output

    def _split_wav(self, wav_path: Path, chunk_seconds: int) -> list:
        """把 wav 切成多個 temp wav，回傳 path list"""
        chunks = []
        try:
            with sf.SoundFile(str(wav_path)) as f:
                samplerate = f.samplerate
                channels = f.channels
                chunk_frames = chunk_seconds * samplerate

                idx = 0
                while True:
                    data = f.read(chunk_frames, dtype='float32')
                    if len(data) == 0:
                        break
                    # 寫到 temp wav
                    tmp = Path(tempfile.gettempdir()) / f'vt_chunk_{int(time.time())}_{idx}.wav'
                    sf.write(str(tmp), data, samplerate, subtype='PCM_16')
                    chunks.append(tmp)
                    idx += 1
                    if len(data) < chunk_frames:
                        break
        except Exception as e:
            print(f"split wav failed: {e}")
        return chunks

    def _summarize(self, transcript: str, duration_seconds: float = 0) -> dict:
        """用 enhancer (Claude/GPT/Gemini) 產生結構化會議紀錄 JSON"""
        today = datetime.now().strftime('%Y-%m-%d')
        duration_mins = int((duration_seconds or 0) // 60)

        # 任務數量參考線（給模型 sanity check，非硬上限）
        if duration_mins <= 30:
            task_hint = '通常 3-8 項'
        elif duration_mins <= 60:
            task_hint = '通常 5-15 項'
        elif duration_mins <= 180:
            task_hint = '通常 15-30 項'
        else:
            task_hint = '依實際內容決定，不設上限'

        prompt = (
            '你是專業會議記錄助理，具備「上下文感知」與「智慧聚類」能力。\n'
            '請根據以下會議逐字稿，輸出結構化會議紀錄，**以繁體中文輸出嚴格 JSON**。\n'
            '逐字稿是你的最高參考依據。\n\n'

            '★★ 智慧聚類 SOP ★★\n'
            '【任務提取原則】\n'
            '1. 完整性優先於精簡性 — 只要會議明確提到「誰要做什麼、何時完成」都必須列入。\n'
            '   不可為了讓摘要好看而刪除具體的執行項。\n'
            '2. 質量過濾 — 排除純社交辭令、純討論而未指派的「未來再議」。\n'
            '3. 三種指派方式都要識別：\n'
            '   (a) 直接：「X 要做 Y」\n'
            '   (b) 隱含：「麻煩大家幫我...」、「之後再對一下」\n'
            '   (c) 條件：「如果...就...」\n'
            '4. 口語化辨識 — 識別口語中的隱含需求都應列為任務。\n\n'

            '【智慧歸納原則】\n'
            '1. 同人同類合併 — 同一負責人在會議不同時間點被指派的同範疇任務，'
            '歸納為一個複合型任務。\n'
            '2. 內容完整化 — 合併後必須保留所有提到過的細節與原文關鍵字。\n'
            '3. 範例：不要分成「電風扇清潔」、「公共區域標準」，'
            '而應合併為「建立清潔標準化手冊（含電風扇、公共區域等細節）」。\n\n'

            '【決議 vs 行動項目】\n'
            '- decisions（決議）：會議中已拍板的決定（不一定有負責人）\n'
            '- action_items（行動）：誰要做什麼、何時做\n'
            '- 一個議題可以同時產生決議 + 多項行動\n\n'

            '【截止日期推算】\n'
            f'- 今天日期：{today}\n'
            '- 逐字稿有提到時間 → 推算 ISO 8601 (YYYY-MM-DD)\n'
            '- 沒提到 → 用 priority 推算：HIGH=7天 / MEDIUM=14天 / LOW=30天\n\n'

            f'【任務數量參考】(本場會議時長 {duration_mins} 分鐘 → {task_hint})\n'
            '- 30 分鐘 → 通常 3-8 項\n'
            '- 1 小時 → 通常 5-15 項\n'
            '- 3 小時 → 通常 15-30 項\n'
            '- 不設硬上限，依實際內容決定\n\n'

            '【輸出 JSON 結構】(嚴格遵守，第一個字必須是 {)\n'
            '{\n'
            '  "meeting_title": "會議名稱 10-25 字，概括主題",\n'
            '  "summary": {\n'
            '    "overview": "1-2 句會議概覽",\n'
            '    "key_points": ["主要討論要點 3-6 條"],\n'
            '    "conclusions": ["重要結論 2-4 條"],\n'
            '    "next_steps": ["後續行動方向 2-4 條"]\n'
            '  },\n'
            '  "decisions": ["決議內容 1", "決議內容 2"],\n'
            '  "action_items": [\n'
            '    {\n'
            '      "title": "任務標題 (短)",\n'
            '      "detail": "任務細節說明 (合併後的完整內容)",\n'
            '      "priority": "HIGH | MEDIUM | LOW",\n'
            '      "assignee": "負責人姓名 (沒提到填空字串)",\n'
            '      "deadline": "YYYY-MM-DD"\n'
            '    }\n'
            '  ],\n'
            '  "keywords": ["關鍵字 5-10 個，含人名/公司/專案/技術術語"]\n'
            '}\n\n'

            '【嚴格規則】\n'
            '- 不要加 markdown code fence (```)\n'
            '- 不要加說明文字或前言\n'
            '- 第一個字必須是 {\n'
            '- 所有文字用繁體中文\n\n'

            '逐字稿：\n'
        )
        result = self.enhancer.enhance(prompt + transcript)
        text = result.get('text', '').strip()

        # 移除可能的 markdown code fence
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        try:
            return json.loads(text)
        except Exception as e:
            print(f"parse summary JSON failed: {e}\n  raw: {text[:200]}")
            return {
                'meeting_title': '',
                'summary': {
                    'overview': text[:500],
                    'key_points': [],
                    'conclusions': [],
                    'next_steps': [],
                },
                'decisions': [],
                'action_items': [],
                'keywords': [],
            }
