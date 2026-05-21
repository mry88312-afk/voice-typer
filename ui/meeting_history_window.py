"""會議紀錄歷史視窗 — 掃描 recordings/ 目錄列出過去的會議"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
import customtkinter as ctk

from ui.theme import get_colors, font, Tokens, apply_font_to_descendants


def _parse_meeting_filename(name: str):
    """從 'meeting_2026-05-15_21-30-00.summary.json' 取出 datetime + base name"""
    m = re.match(r'^meeting_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', name)
    if not m:
        return None, name
    try:
        date_str = m.group(1)
        time_str = m.group(2).replace('-', ':')
        dt = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M:%S')
        # base name (不含副檔名/後綴)
        base = name.split('.')[0]
        return dt, base
    except Exception:
        return None, name


class MeetingHistoryWindow(ctk.CTkToplevel):
    """會議紀錄列表 — 從 recordings/ 掃描 *.summary.json"""

    def __init__(self, parent, recordings_dir: Path,
                 on_open_meeting=None, on_import_file=None):
        super().__init__(parent)
        self.recordings_dir = Path(recordings_dir)
        self.on_open_meeting = on_open_meeting
        self.on_import_file = on_import_file
        self.colors = get_colors()

        self.title('Voice Typer - 會議紀錄')
        self.geometry('760x640')
        self.minsize(640, 480)
        self.withdraw()
        self._center()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_list()

        self.update_idletasks()
        apply_font_to_descendants(self)
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 760, 640
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0,
                              fg_color=self.colors['bg_primary'], height=72)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text='會議紀錄',
            font=font(Tokens.FONT_TITLE, 'bold'),
            text_color=self.colors['text_primary'],
        ).grid(row=0, column=0, sticky='w',
                padx=Tokens.PAD_XL, pady=(Tokens.PAD_LG, 0))

        ctk.CTkLabel(
            header,
            text=f'從 {self.recordings_dir.name}\\ 讀取所有會議錄音與摘要',
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
        ).grid(row=1, column=0, sticky='w',
                padx=Tokens.PAD_XL, pady=(2, Tokens.PAD_LG))

        # 右上角按鈕群
        btn_group = ctk.CTkFrame(header, fg_color='transparent')
        btn_group.grid(row=0, column=1, rowspan=2,
                       padx=Tokens.PAD_XL, pady=Tokens.PAD_LG, sticky='e')

        if self.on_import_file:
            ctk.CTkButton(
                btn_group, text='匯入音檔', width=96, height=32,
                corner_radius=Tokens.RADIUS_MD,
                fg_color=self.colors['accent'],
                hover_color=self.colors['accent_hover'],
                font=font(Tokens.FONT_BODY_SM, 'bold'),
                command=self._handle_import,
            ).pack(side='left', padx=(0, Tokens.PAD_SM))

        ctk.CTkButton(
            btn_group, text='重新整理', width=88, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY_SM),
            command=self._refresh,
        ).pack(side='left')

        sep = ctk.CTkFrame(self, height=1, fg_color=self.colors['border'])
        sep.grid(row=0, column=0, sticky='ews', pady=(71, 0))

    def _build_list(self):
        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
        )
        self.scroll.grid(row=1, column=0, sticky='nsew',
                          padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_LG))
        self.scroll.grid_columnconfigure(0, weight=1)
        self._refresh()

    def _scan(self):
        """掃描 recordings/ 找 summary.json"""
        if not self.recordings_dir.exists():
            return []
        items = []
        for p in self.recordings_dir.glob('meeting_*.summary.json'):
            dt, base = _parse_meeting_filename(p.name)
            # 對應檔案
            mic_wav = self.recordings_dir / f'{base}_mic.wav'
            mixed_wav = self.recordings_dir / f'{base}_mixed.wav'
            transcript_txt = self.recordings_dir / f'{base}.transcript.txt'
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
            except Exception:
                summary_data = {}
            transcript = ''
            if transcript_txt.exists():
                try:
                    transcript = transcript_txt.read_text(encoding='utf-8')
                except Exception:
                    pass
            wav_path = mixed_wav if mixed_wav.exists() else mic_wav
            items.append({
                'dt': dt,
                'base': base,
                'wav_path': wav_path if wav_path.exists() else None,
                'summary_json': p,
                'meeting_title': summary_data.get('meeting_title', '') or '',
                'summary': summary_data.get('summary', []),
                'decisions': summary_data.get('decisions', []) or [],
                'action_items': summary_data.get('action_items', []),
                'keywords': summary_data.get('keywords', []),
                'transcript': transcript,
            })
        # 由新到舊
        items.sort(key=lambda x: x['dt'] or datetime.min, reverse=True)
        return items

    def _refresh(self):
        for child in self.scroll.winfo_children():
            child.destroy()

        items = self._scan()
        if not items:
            ctk.CTkLabel(
                self.scroll,
                text='尚無會議錄音紀錄\n\n右鍵托盤 → 開始會議錄音，錄完後會出現在這',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
                justify='center',
            ).grid(row=0, column=0, pady=Tokens.PAD_XL * 2)
            return

        for i, item in enumerate(items):
            self._render_card(i, item)

    def _render_card(self, idx, item):
        card = ctk.CTkFrame(
            self.scroll,
            fg_color=self.colors['bg_primary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'],
            border_width=1,
        )
        card.grid(row=idx, column=0, sticky='ew', pady=4, padx=4)
        card.grid_columnconfigure(0, weight=1)

        # 時間 + 動作按鈕
        top = ctk.CTkFrame(card, fg_color='transparent')
        top.grid(row=0, column=0, sticky='ew',
                 padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, Tokens.PAD_XS))
        top.grid_columnconfigure(0, weight=1)

        # 主標題：有 meeting_title 用它，沒有則用時間
        dt_str = self._format_dt(item['dt'])
        meeting_title = (item.get('meeting_title') or '').strip()
        title_frame = ctk.CTkFrame(top, fg_color='transparent')
        title_frame.grid(row=0, column=0, sticky='w')
        if meeting_title:
            ctk.CTkLabel(
                title_frame, text=meeting_title,
                font=font(Tokens.FONT_BODY_LG, 'bold'),
                text_color=self.colors['text_primary'],
                anchor='w', justify='left',
                wraplength=520,
            ).pack(side='top', anchor='w')
            ctk.CTkLabel(
                title_frame, text=dt_str,
                font=font(Tokens.FONT_CAPTION),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).pack(side='top', anchor='w', pady=(2, 0))
        else:
            ctk.CTkLabel(
                title_frame, text=dt_str,
                font=font(Tokens.FONT_BODY_LG, 'bold'),
                text_color=self.colors['text_primary'],
                anchor='w',
            ).pack(side='top', anchor='w')

        actions = ctk.CTkFrame(top, fg_color='transparent')
        actions.grid(row=0, column=1, sticky='e')

        ctk.CTkButton(
            actions, text='開啟', width=64, height=28,
            corner_radius=Tokens.RADIUS_SM,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_BODY_SM, 'bold'),
            command=lambda it=item: self._open(it),
        ).pack(side='left')

        if item['wav_path']:
            ctk.CTkButton(
                actions, text='聽錄音', width=72, height=28,
                corner_radius=Tokens.RADIUS_SM,
                fg_color='transparent',
                text_color=self.colors['text_primary'],
                hover_color=self.colors['bg_hover'],
                border_width=1, border_color=self.colors['border'],
                font=font(Tokens.FONT_BODY_SM),
                command=lambda p=item['wav_path']: self._open_wav(p),
            ).pack(side='left', padx=(4, 0))

        ctk.CTkButton(
            actions, text='✕', width=28, height=28,
            corner_radius=Tokens.RADIUS_SM,
            fg_color='transparent',
            text_color=self.colors['text_tertiary'],
            hover_color=self.colors['bg_hover'],
            font=font(Tokens.FONT_BODY_SM),
            command=lambda it=item: self._delete(it),
        ).pack(side='left', padx=(4, 0))

        # 預覽：新格式優先 overview，否則用 key_points / 舊扁平 list
        summary = item['summary']
        preview = ''
        if isinstance(summary, dict):
            preview = (summary.get('overview') or '').strip()
            if not preview:
                kp = summary.get('key_points') or []
                preview = '  ·  '.join(str(s) for s in kp[:2])
        elif isinstance(summary, list) and summary:
            preview = '  ·  '.join(str(s) for s in summary[:2])

        if preview:
            if len(preview) > 200:
                preview = preview[:200] + '...'
            ctk.CTkLabel(
                card, text=preview,
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_secondary'],
                anchor='w', justify='left',
                wraplength=680,
            ).grid(row=1, column=0, sticky='w',
                    padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS))
        elif item['transcript']:
            preview = item['transcript'][:200]
            if len(item['transcript']) > 200:
                preview += '...'
            ctk.CTkLabel(
                card, text=preview,
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
                anchor='w', justify='left',
                wraplength=680,
            ).grid(row=1, column=0, sticky='w',
                    padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS))
        else:
            ctk.CTkLabel(
                card, text='(無摘要)',
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).grid(row=1, column=0, sticky='w',
                    padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS))

        # 底部 chip: 行動項目數 + 關鍵字數
        meta = ctk.CTkFrame(card, fg_color='transparent')
        meta.grid(row=2, column=0, sticky='w',
                  padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))

        action_count = len(item['action_items'])
        decision_count = len(item.get('decisions') or [])
        keyword_count = len(item['keywords'])
        if decision_count:
            ctk.CTkLabel(
                meta, text=f'✓ {decision_count} 決議',
                font=font(Tokens.FONT_CAPTION, 'bold'),
                text_color=self.colors['success'],
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=2,
            ).pack(side='left', padx=(0, 6))
        if action_count:
            ctk.CTkLabel(
                meta, text=f'☐ {action_count} 行動項目',
                font=font(Tokens.FONT_CAPTION, 'bold'),
                text_color=self.colors['accent'],
                fg_color=self.colors['accent_subtle'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=2,
            ).pack(side='left', padx=(0, 6))
        if keyword_count:
            ctk.CTkLabel(
                meta, text=f'# {keyword_count} 關鍵字',
                font=font(Tokens.FONT_CAPTION),
                text_color=self.colors['text_secondary'],
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=2,
            ).pack(side='left', padx=(0, 6))

    def _format_dt(self, dt):
        if not dt:
            return '(未知時間)'
        now = datetime.now()
        same_day = dt.date() == now.date()
        if same_day:
            return f"今天  {dt.strftime('%H:%M')}"
        diff = (now.date() - dt.date()).days
        if diff == 1:
            return f"昨天  {dt.strftime('%H:%M')}"
        if diff <= 7:
            return f"{diff} 天前  {dt.strftime('%H:%M')}"
        return dt.strftime('%Y-%m-%d %H:%M')

    def _open(self, item):
        if self.on_open_meeting:
            try:
                self.on_open_meeting(item)
            except Exception as e:
                print(f'open meeting failed: {e}')

    def _handle_import(self):
        if self.on_import_file:
            try:
                self.on_import_file()
            except Exception as e:
                print(f'import file failed: {e}')

    def _open_wav(self, wav_path: Path):
        try:
            import os
            os.startfile(str(wav_path))
        except Exception:
            pass

    def _delete(self, item):
        import ctypes
        result = ctypes.windll.user32.MessageBoxW(
            0,
            f'確定刪除這場會議的所有檔案嗎？\n\n'
            f'時間: {self._format_dt(item["dt"])}\n'
            f'會刪除：錄音 wav、逐字稿 txt、摘要 json\n\n'
            f'此動作無法復原。',
            'Voice Typer',
            0x4 | 0x30 | 0x40000,  # YESNO | WARNING | TOPMOST
        )
        if result != 6:  # not YES
            return
        # 刪相關檔案
        base = item['base']
        for suffix in ['_mic.wav', '_system.wav', '_mixed.wav',
                       '.transcript.txt', '.summary.json']:
            f = self.recordings_dir / f'{base}{suffix}'
            try:
                if f.exists():
                    f.unlink()
            except Exception as e:
                print(f'delete {f} failed: {e}')
        self._refresh()
