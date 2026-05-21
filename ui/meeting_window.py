"""會議錄音 — 進行中浮窗 + 處理進度 + 結果視窗"""
import time
from pathlib import Path
import customtkinter as ctk
import pyperclip

from ui.theme import get_colors, font, Tokens, apply_font_to_descendants


# ============================================================
# 進行中浮窗 — 顯示時長、音量、檔案大小
# ============================================================
class MeetingProgressWindow(ctk.CTkToplevel):
    WIDTH = 420
    HEIGHT = 200

    def __init__(self, parent, on_stop=None, on_cancel=None, on_pause=None):
        super().__init__(parent)
        self.colors = get_colors()
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.on_pause = on_pause

        self.title('會議錄音')
        self.geometry(f'{self.WIDTH}x{self.HEIGHT}')
        self.resizable(False, False)
        self.withdraw()
        self.attributes('-topmost', True)
        self._center_top()

        self.is_paused = False
        self.is_processing = False  # 從錄音 → 處理中時切換

        self._build()
        self.update_idletasks()
        apply_font_to_descendants(self)
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center_top(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        x = (sw - self.WIDTH) // 2
        y = 60
        self.geometry(f'{self.WIDTH}x{self.HEIGHT}+{x}+{y}')

    def _build(self):
        self.frame = ctk.CTkFrame(
            self, corner_radius=Tokens.RADIUS_LG,
            fg_color=self.colors['bg_primary'],
            border_color=self.colors['border'], border_width=1,
        )
        self.frame.pack(fill='both', expand=True, padx=2, pady=2)

        # 標題列
        top = ctk.CTkFrame(self.frame, fg_color='transparent', height=28)
        top.pack(fill='x', padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, 0))
        top.pack_propagate(False)

        self.dot = ctk.CTkLabel(
            top, text='●',
            text_color=self.colors['danger'],
            font=font(Tokens.FONT_BODY_LG),
            width=14,
        )
        self.dot.pack(side='left')

        self.title_lbl = ctk.CTkLabel(
            top, text='會議錄音中',
            font=font(Tokens.FONT_BODY, 'bold'),
            text_color=self.colors['text_primary'],
        )
        self.title_lbl.pack(side='left', padx=(6, 0))

        # 計時器
        self.time_lbl = ctk.CTkLabel(
            self.frame, text='00:00:00',
            font=font(32, 'bold'),
            text_color=self.colors['text_primary'],
        )
        self.time_lbl.pack(pady=(Tokens.PAD_SM, 0))

        # 副資訊 (檔案大小 + 音量提示)
        self.info_lbl = ctk.CTkLabel(
            self.frame, text='正在寫入磁碟...',
            font=font(Tokens.FONT_CAPTION),
            text_color=self.colors['text_tertiary'],
        )
        self.info_lbl.pack(pady=(2, Tokens.PAD_SM))

        # 音量長條
        self.volume_canvas = ctk.CTkCanvas(
            self.frame, height=20,
            bg=self.colors['bg_primary'],
            highlightthickness=0,
        )
        self.volume_canvas.pack(fill='x', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_SM))
        self._bar_id = None

        # 進度條 (處理中時用)
        self.progress_canvas = ctk.CTkCanvas(
            self.frame, height=4,
            bg=self.colors['bg_primary'],
            highlightthickness=0,
        )
        # 預設不 pack；進入 processing mode 才 pack

        # 按鈕區
        btn_row = ctk.CTkFrame(self.frame, fg_color='transparent')
        btn_row.pack(fill='x', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))

        self.cancel_btn = ctk.CTkButton(
            btn_row, text='取消', width=80, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['danger'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY_SM),
            command=self._handle_cancel,
        )
        self.cancel_btn.pack(side='left')

        self.pause_btn = ctk.CTkButton(
            btn_row, text='暫停', width=80, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY_SM),
            command=self._handle_pause,
        )
        self.pause_btn.pack(side='left', padx=(8, 0))

        self.stop_btn = ctk.CTkButton(
            btn_row, text='結束 + 轉錄', width=120, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_BODY_SM, 'bold'),
            command=self._handle_stop,
        )
        self.stop_btn.pack(side='right')

    # ---------- 從外部更新 (live progress) ----------
    def update_progress(self, elapsed_s: float, file_bytes: int, rms: float):
        try:
            mins = int(elapsed_s // 60)
            hours = mins // 60
            mins = mins % 60
            secs = int(elapsed_s % 60)
            self.time_lbl.configure(text=f'{hours:02d}:{mins:02d}:{secs:02d}')

            mb = file_bytes / (1024 * 1024)
            if mb >= 1:
                size_str = f'{mb:.1f} MB'
            else:
                size_str = f'{file_bytes / 1024:.0f} KB'
            self.info_lbl.configure(text=f'已寫入 {size_str}  ·  邊錄邊存檔')

            self._draw_volume(rms)
        except Exception:
            pass

    def _draw_volume(self, rms):
        try:
            self.volume_canvas.delete('all')
            w = self.volume_canvas.winfo_width()
            h = self.volume_canvas.winfo_height()
            if w <= 0 or h <= 0:
                return
            level = min(1.0, rms / 0.15)
            # 背景條
            self.volume_canvas.create_rectangle(
                0, h/2 - 2, w, h/2 + 2,
                fill=self.colors['bg_tertiary'], outline='',
            )
            # 音量
            bar_w = level * w
            color = self.colors['success'] if level > 0.05 else self.colors['warning']
            self.volume_canvas.create_rectangle(
                0, h/2 - 4, bar_w, h/2 + 4,
                fill=color, outline='',
            )
        except Exception:
            pass

    # ---------- 切換到處理中模式 ----------
    def switch_to_processing(self):
        self.is_processing = True
        self.dot.configure(text_color=self.colors['warning'], text='◐')
        self.title_lbl.configure(text='處理會議錄音')
        self.cancel_btn.pack_forget()
        self.pause_btn.pack_forget()
        self.stop_btn.pack_forget()
        # 隱藏音量
        self.volume_canvas.pack_forget()
        # 顯示進度條
        self.progress_canvas.pack(
            fill='x', padx=Tokens.PAD_LG, pady=(Tokens.PAD_SM, Tokens.PAD_MD)
        )

    def update_processing(self, message: str, ratio: float):
        try:
            self.info_lbl.configure(text=message)
            # 畫進度條
            self.progress_canvas.delete('all')
            w = self.progress_canvas.winfo_width()
            h = self.progress_canvas.winfo_height()
            if w <= 0:
                return
            self.progress_canvas.create_rectangle(
                0, 0, w, h,
                fill=self.colors['bg_tertiary'], outline='',
            )
            self.progress_canvas.create_rectangle(
                0, 0, w * max(0, min(1, ratio)), h,
                fill=self.colors['accent'], outline='',
            )
        except Exception:
            pass

    # ---------- 按鈕 handler ----------
    def _handle_cancel(self):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass
        self.destroy()

    def _handle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.configure(text='繼續')
            self.dot.configure(text='⏸', text_color=self.colors['warning'])
        else:
            self.pause_btn.configure(text='暫停')
            self.dot.configure(text='●', text_color=self.colors['danger'])
        if self.on_pause:
            try:
                self.on_pause(self.is_paused)
            except Exception:
                pass

    def _handle_stop(self):
        if self.on_stop:
            try:
                self.on_stop()
            except Exception:
                pass


# ============================================================
# 結果視窗 — 顯示摘要 / 行動項目 / 全文 / 關鍵詞
# ============================================================
class MeetingResultWindow(ctk.CTkToplevel):
    def __init__(self, parent, result: dict, wav_path: Path = None):
        super().__init__(parent)
        self.colors = get_colors()
        self.result = result
        self.wav_path = wav_path

        self.title('會議紀錄')
        self.geometry('860x720')
        self.minsize(720, 600)
        self.withdraw()
        self._center()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build()
        self.update_idletasks()
        apply_font_to_descendants(self)
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 860, 720
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def _build(self):
        # ── Header ──
        header = ctk.CTkFrame(self, corner_radius=0,
                              fg_color=self.colors['bg_primary'], height=72)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)

        # 標題：優先用 AI 生成的 meeting_title，沒有則 fallback
        meeting_title = (self.result.get('meeting_title') or '').strip() or '會議紀錄'
        title = ctk.CTkLabel(
            header, text=meeting_title,
            font=font(Tokens.FONT_TITLE, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w', justify='left',
            wraplength=820,
        )
        title.grid(row=0, column=0, sticky='w',
                   padx=Tokens.PAD_XL, pady=(Tokens.PAD_LG, 0))

        duration = self.result.get('duration_seconds', 0)
        meta_parts = []
        if duration:
            mins = int(duration // 60)
            secs = int(duration % 60)
            meta_parts.append(f'時長 {mins} 分 {secs} 秒')
        actions_n = len(self.result.get('action_items', []) or [])
        decisions_n = len(self.result.get('decisions', []) or [])
        keywords = self.result.get('keywords', []) or []
        if decisions_n:
            meta_parts.append(f'{decisions_n} 項決議')
        if actions_n:
            meta_parts.append(f'{actions_n} 項行動')
        if keywords:
            meta_parts.append(f'{len(keywords)} 個關鍵字')

        ctk.CTkLabel(
            header, text='  ·  '.join(meta_parts),
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
        ).grid(row=1, column=0, sticky='w',
                padx=Tokens.PAD_XL, pady=(2, Tokens.PAD_LG))

        sep = ctk.CTkFrame(self, height=1, fg_color=self.colors['border'])
        sep.grid(row=0, column=0, sticky='ews', pady=(71, 0))

        # ── Tabs ──
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=0,
            fg_color=self.colors['bg_primary'],
            segmented_button_selected_color=self.colors['accent'],
            segmented_button_selected_hover_color=self.colors['accent_hover'],
        )
        self.tabview.grid(row=1, column=0, sticky='nsew',
                          padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)

        for name in ['摘要', '決議', '行動項目', '逐字稿', '關鍵字']:
            self.tabview.add(name)

        self._build_summary_tab(self.tabview.tab('摘要'))
        self._build_decisions_tab(self.tabview.tab('決議'))
        self._build_actions_tab(self.tabview.tab('行動項目'))
        self._build_transcript_tab(self.tabview.tab('逐字稿'))
        self._build_keywords_tab(self.tabview.tab('關鍵字'))

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color='transparent', height=64)
        footer.grid(row=2, column=0, sticky='ew',
                    padx=Tokens.PAD_XL, pady=Tokens.PAD_MD)
        footer.grid_columnconfigure(0, weight=1)

        # 左側：匯出
        left = ctk.CTkFrame(footer, fg_color='transparent')
        left.grid(row=0, column=0, sticky='w')

        ctk.CTkButton(
            left, text='匯出 Markdown', width=130, height=36,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY),
            command=self._export_md,
        ).pack(side='left')

        if self.wav_path:
            ctk.CTkButton(
                left, text='開啟錄音檔', width=110, height=36,
                corner_radius=Tokens.RADIUS_MD,
                fg_color='transparent',
                text_color=self.colors['text_primary'],
                hover_color=self.colors['bg_hover'],
                border_width=1, border_color=self.colors['border'],
                font=font(Tokens.FONT_BODY),
                command=self._open_wav,
            ).pack(side='left', padx=(Tokens.PAD_SM, 0))

        # 右側：關閉
        ctk.CTkButton(
            footer, text='關閉', width=88, height=36,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_BODY, 'bold'),
            command=self.destroy,
        ).grid(row=0, column=1, sticky='e')

    def _normalize_summary(self):
        """把 summary 統一成 dict 結構，相容舊格式 (扁平 list)"""
        s = self.result.get('summary', {})
        if isinstance(s, dict):
            return {
                'overview': s.get('overview', '') or '',
                'key_points': s.get('key_points', []) or [],
                'conclusions': s.get('conclusions', []) or [],
                'next_steps': s.get('next_steps', []) or [],
            }
        if isinstance(s, list):
            # 舊格式：扁平 list 全當 key_points
            return {
                'overview': '',
                'key_points': [str(x) for x in s],
                'conclusions': [],
                'next_steps': [],
            }
        return {'overview': '', 'key_points': [], 'conclusions': [], 'next_steps': []}

    def _build_summary_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.colors['bg_primary'])
        scroll.grid(row=0, column=0, sticky='nsew')
        scroll.grid_columnconfigure(0, weight=1)

        s = self._normalize_summary()
        is_empty = (not s['overview'] and not s['key_points']
                    and not s['conclusions'] and not s['next_steps'])
        if is_empty:
            ctk.CTkLabel(
                scroll, text='(沒有摘要)',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
            ).grid(row=0, column=0, pady=Tokens.PAD_XL)
            return

        row_idx = 0

        # 1. Overview — 大字、置頂
        if s['overview']:
            ov = ctk.CTkFrame(
                scroll,
                fg_color=self.colors['accent_subtle'],
                corner_radius=Tokens.RADIUS_MD,
                border_color=self.colors['accent'],
                border_width=1,
            )
            ov.grid(row=row_idx, column=0, sticky='ew', pady=(4, 12), padx=4)
            ov.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                ov, text='會議概覽',
                font=font(Tokens.FONT_CAPTION, 'bold'),
                text_color=self.colors['accent'],
                anchor='w',
            ).grid(row=0, column=0, sticky='w',
                   padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, 2))
            ctk.CTkLabel(
                ov, text=s['overview'],
                font=font(Tokens.FONT_BODY_LG),
                text_color=self.colors['text_primary'],
                anchor='w', justify='left',
                wraplength=720,
            ).grid(row=1, column=0, sticky='w',
                   padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))
            row_idx += 1

        # 2/3/4 — Sections
        sections = [
            ('主要討論', s['key_points'], self.colors['text_primary']),
            ('重要結論', s['conclusions'], self.colors['success']),
            ('後續方向', s['next_steps'], self.colors['warning']),
        ]
        for label, items, accent_color in sections:
            if not items:
                continue
            sec = ctk.CTkFrame(
                scroll,
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_MD,
                border_color=self.colors['border'],
                border_width=1,
            )
            sec.grid(row=row_idx, column=0, sticky='ew', pady=4, padx=4)
            sec.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                sec, text=label,
                font=font(Tokens.FONT_BODY, 'bold'),
                text_color=accent_color,
                anchor='w',
            ).grid(row=0, column=0, sticky='w',
                   padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, Tokens.PAD_XS))

            for j, item in enumerate(items):
                ctk.CTkLabel(
                    sec, text=f'•  {item}',
                    font=font(Tokens.FONT_BODY),
                    text_color=self.colors['text_primary'],
                    anchor='w', justify='left',
                    wraplength=720,
                ).grid(row=j + 1, column=0, sticky='w',
                       padx=(Tokens.PAD_LG + 4, Tokens.PAD_LG),
                       pady=(0, 2 if j < len(items) - 1 else Tokens.PAD_MD))
            row_idx += 1

    def _build_decisions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.colors['bg_primary'])
        scroll.grid(row=0, column=0, sticky='nsew')
        scroll.grid_columnconfigure(0, weight=1)

        decisions = self.result.get('decisions', []) or []
        # 相容：dict 形式 {content: ...}
        decisions = [
            (d.get('content', '') if isinstance(d, dict) else str(d))
            for d in decisions
        ]
        decisions = [d for d in decisions if d.strip()]

        if not decisions:
            ctk.CTkLabel(
                scroll, text='(本次會議沒有明確決議)',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
            ).grid(row=0, column=0, pady=Tokens.PAD_XL)
            return

        for i, d in enumerate(decisions):
            row = ctk.CTkFrame(
                scroll,
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_MD,
                border_color=self.colors['success'],
                border_width=1,
            )
            row.grid(row=i, column=0, sticky='ew', pady=4, padx=4)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row, text='✓',
                font=font(Tokens.FONT_BODY_LG, 'bold'),
                text_color=self.colors['success'],
                width=32,
            ).grid(row=0, column=0, sticky='nw',
                   padx=(Tokens.PAD_LG, 0), pady=Tokens.PAD_MD)

            ctk.CTkLabel(
                row, text=d,
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_primary'],
                anchor='w', justify='left',
                wraplength=720,
            ).grid(row=0, column=1, sticky='w',
                   padx=(Tokens.PAD_SM, Tokens.PAD_LG), pady=Tokens.PAD_MD)

    def _build_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.colors['bg_primary'])
        scroll.grid(row=0, column=0, sticky='nsew')
        scroll.grid_columnconfigure(0, weight=1)

        actions = self.result.get('action_items', [])
        if not actions:
            ctk.CTkLabel(
                scroll, text='(沒有偵測到行動項目)',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
            ).grid(row=0, column=0, pady=Tokens.PAD_XL)
            return

        priority_styles = {
            'HIGH': (self.colors['danger'], '高'),
            'MEDIUM': (self.colors['warning'], '中'),
            'LOW': (self.colors['text_secondary'], '低'),
        }

        for i, a in enumerate(actions):
            if isinstance(a, dict):
                # 新格式優先 title，舊格式 fallback task
                title_text = (a.get('title') or a.get('task') or '').strip()
                detail = (a.get('detail') or '').strip()
                priority = (a.get('priority') or '').strip().upper()
                assignee = (a.get('assignee') or '').strip()
                deadline = (a.get('deadline') or '').strip()
            else:
                title_text = str(a)
                detail = ''
                priority = ''
                assignee = ''
                deadline = ''

            row = ctk.CTkFrame(
                scroll,
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_MD,
                border_color=self.colors['border'],
                border_width=1,
            )
            row.grid(row=i, column=0, sticky='ew', pady=4, padx=4)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row, text='☐',
                font=font(Tokens.FONT_BODY_LG),
                text_color=self.colors['text_secondary'],
                width=24,
            ).grid(row=0, column=0, rowspan=3, sticky='nw',
                   padx=(Tokens.PAD_LG, 0), pady=Tokens.PAD_MD)

            # 第 1 列：標題 + (右側) priority chip
            head = ctk.CTkFrame(row, fg_color='transparent')
            head.grid(row=0, column=1, sticky='ew',
                      padx=(Tokens.PAD_SM, Tokens.PAD_LG),
                      pady=(Tokens.PAD_MD, 2))
            head.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                head, text=title_text,
                font=font(Tokens.FONT_BODY, 'bold'),
                text_color=self.colors['text_primary'],
                anchor='w', justify='left',
                wraplength=620,
            ).grid(row=0, column=0, sticky='w')

            if priority in priority_styles:
                color, label = priority_styles[priority]
                ctk.CTkLabel(
                    head, text=label,
                    font=font(Tokens.FONT_CAPTION, 'bold'),
                    text_color='#FFFFFF',
                    fg_color=color,
                    corner_radius=Tokens.RADIUS_SM,
                    padx=8, pady=2,
                ).grid(row=0, column=1, sticky='e', padx=(8, 0))

            # 第 2 列：detail（合併後的完整內容）
            if detail and detail != title_text:
                ctk.CTkLabel(
                    row, text=detail,
                    font=font(Tokens.FONT_BODY_SM),
                    text_color=self.colors['text_secondary'],
                    anchor='w', justify='left',
                    wraplength=680,
                ).grid(row=1, column=1, sticky='w',
                       padx=(Tokens.PAD_SM, Tokens.PAD_LG),
                       pady=(0, 4))

            # 第 3 列：meta
            meta_parts = []
            if assignee:
                meta_parts.append(f'@ {assignee}')
            if deadline:
                meta_parts.append(f'⏰ {deadline}')
            if meta_parts:
                ctk.CTkLabel(
                    row, text='  ·  '.join(meta_parts),
                    font=font(Tokens.FONT_CAPTION),
                    text_color=self.colors['text_tertiary'],
                    anchor='w',
                ).grid(row=2, column=1, sticky='w',
                       padx=(Tokens.PAD_SM, Tokens.PAD_LG),
                       pady=(0, Tokens.PAD_MD))
            else:
                # 沒 meta 時要補 bottom padding
                ctk.CTkFrame(row, fg_color='transparent', height=Tokens.PAD_MD).grid(
                    row=2, column=1, sticky='w')

    def _build_transcript_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        text = ctk.CTkTextbox(
            parent,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            border_width=1,
            text_color=self.colors['text_primary'],
            font=font(Tokens.FONT_BODY),
            wrap='word',
        )
        text.grid(row=0, column=0, sticky='nsew')
        content = self.result.get('transcript', '') or ''
        text.insert('0.0', content)

        # 若內容含 [Speaker N]: 標籤，給每個說話者著色
        try:
            import re
            speaker_colors = [
                '#5E6AD2',  # 藍紫
                '#1B9A75',  # 綠
                '#D17A00',  # 橘
                '#B179DE',  # 紫
                '#D9342B',  # 紅
            ]
            seen = {}
            for match in re.finditer(r'\[Speaker\s*(\d+)\]', content):
                num = match.group(1)
                if num not in seen:
                    color_idx = len(seen) % len(speaker_colors)
                    seen[num] = speaker_colors[color_idx]
                tag = f'speaker_{num}'
                start = f'1.0+{match.start()}c'
                end = f'1.0+{match.end()}c'
                try:
                    text.tag_add(tag, start, end)
                    text.tag_config(tag, foreground=seen[num])
                except Exception:
                    pass
        except Exception as e:
            print(f'speaker color failed: {e}')

    def _build_keywords_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.colors['bg_primary'])
        scroll.grid(row=0, column=0, sticky='nsew')

        keywords = self.result.get('keywords', [])
        if not keywords:
            ctk.CTkLabel(
                scroll, text='(沒有偵測到關鍵字)',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
            ).pack(pady=Tokens.PAD_XL)
            return

        wrap = ctk.CTkFrame(scroll, fg_color='transparent')
        wrap.pack(fill='both', expand=True, pady=Tokens.PAD_MD)

        # 把關鍵字做成 chip
        from tkinter import Frame as TkFrame
        row_frame = None
        chip_count = 0
        for kw in keywords:
            if chip_count % 4 == 0:
                row_frame = ctk.CTkFrame(wrap, fg_color='transparent')
                row_frame.pack(fill='x', pady=4)
            chip = ctk.CTkLabel(
                row_frame, text=kw,
                font=font(Tokens.FONT_BODY_SM, 'bold'),
                text_color=self.colors['accent'],
                fg_color=self.colors['accent_subtle'],
                corner_radius=Tokens.RADIUS_SM,
                padx=Tokens.PAD_MD, pady=6,
            )
            chip.pack(side='left', padx=Tokens.PAD_XS)
            chip_count += 1

    # ---------- 動作 ----------
    def _export_md(self):
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                title='匯出會議紀錄',
                defaultextension='.md',
                initialfile=f'meeting-{time.strftime("%Y-%m-%d-%H%M")}.md',
                filetypes=[('Markdown', '*.md'), ('Text', '*.txt')],
            )
            if not path:
                return
            content = self._render_markdown()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f'export failed: {e}')

    def _render_markdown(self) -> str:
        out = []
        meeting_title = (self.result.get('meeting_title') or '').strip()
        out.append(f'# {meeting_title or "會議紀錄"}')
        out.append(f'_{time.strftime("%Y-%m-%d %H:%M")}_')

        duration = self.result.get('duration_seconds', 0)
        if duration:
            mins = int(duration // 60)
            secs = int(duration % 60)
            out.append(f'_時長 {mins} 分 {secs} 秒_')
        out.append('')

        # 摘要 (結構化)
        s = self._normalize_summary()
        if s['overview'] or s['key_points'] or s['conclusions'] or s['next_steps']:
            out.append('## 摘要\n')
            if s['overview']:
                out.append(f'**會議概覽**：{s["overview"]}\n')
            if s['key_points']:
                out.append('**主要討論**')
                for kp in s['key_points']:
                    out.append(f'- {kp}')
                out.append('')
            if s['conclusions']:
                out.append('**重要結論**')
                for c in s['conclusions']:
                    out.append(f'- {c}')
                out.append('')
            if s['next_steps']:
                out.append('**後續方向**')
                for n in s['next_steps']:
                    out.append(f'- {n}')
                out.append('')

        # 決議
        decisions = self.result.get('decisions', []) or []
        decisions = [
            (d.get('content', '') if isinstance(d, dict) else str(d))
            for d in decisions
        ]
        decisions = [d for d in decisions if d.strip()]
        if decisions:
            out.append('## 決議\n')
            for d in decisions:
                out.append(f'- ✓ {d}')
            out.append('')

        # 行動項目
        actions = self.result.get('action_items', [])
        if actions:
            out.append('## 行動項目\n')
            for a in actions:
                if isinstance(a, dict):
                    title_text = (a.get('title') or a.get('task') or '').strip()
                    detail = (a.get('detail') or '').strip()
                    priority = (a.get('priority') or '').strip().upper()
                    assignee = (a.get('assignee') or '').strip()
                    deadline = (a.get('deadline') or '').strip()
                    meta = []
                    if priority:
                        meta.append(priority)
                    if assignee:
                        meta.append(f'@{assignee}')
                    if deadline:
                        meta.append(deadline)
                    line = f'- [ ] **{title_text}**'
                    if meta:
                        line += '  _' + ' · '.join(meta) + '_'
                    out.append(line)
                    if detail and detail != title_text:
                        out.append(f'    {detail}')
                else:
                    out.append(f'- [ ] {a}')
            out.append('')

        keywords = self.result.get('keywords', [])
        if keywords:
            out.append('## 關鍵字\n')
            out.append(' · '.join(f'`{k}`' for k in keywords))
            out.append('')

        transcript = self.result.get('transcript', '')
        if transcript:
            out.append('## 逐字稿\n')
            out.append(transcript)

        return '\n'.join(out)

    def _open_wav(self):
        try:
            import os
            os.startfile(str(self.wav_path))
        except Exception as e:
            print(f'open wav failed: {e}')
