"""歷史紀錄視窗"""
import time
import customtkinter as ctk
import pyperclip

from ui.theme import get_colors, font, Tokens


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, parent, history_mgr, on_paste=None):
        super().__init__(parent)
        self.history_mgr = history_mgr
        self.on_paste = on_paste
        self.colors = get_colors()

        self.title('Voice Typer - 歷史紀錄')
        self.geometry('680x640')
        self.minsize(580, 480)
        self.withdraw()
        self._center()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_search()
        self._build_list()
        self._refresh()

        self.update_idletasks()
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 680, 640
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0,
                              fg_color=self.colors['bg_primary'], height=60)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text='轉錄歷史',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
        )
        title.grid(row=0, column=0, padx=Tokens.PAD_LG, pady=Tokens.PAD_LG, sticky='w')

        clear_btn = ctk.CTkButton(
            header, text='清空全部',
            width=88, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['danger'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_SM),
            command=self._clear_all,
        )
        clear_btn.grid(row=0, column=1, padx=Tokens.PAD_LG, pady=Tokens.PAD_LG, sticky='e')

        sep = ctk.CTkFrame(self, height=1, fg_color=self.colors['border'])
        sep.grid(row=0, column=0, sticky='ews', pady=(59, 0))

    def _build_search(self):
        wrap = ctk.CTkFrame(self, fg_color='transparent')
        wrap.grid(row=1, column=0, sticky='ew', padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)
        wrap.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            wrap, height=38,
            placeholder_text='🔍 搜尋歷史紀錄...',
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
        )
        self.search_entry.grid(row=0, column=0, sticky='ew')
        self.search_entry.bind('<KeyRelease>', lambda e: self._refresh())

    def _build_list(self):
        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
        )
        self.scroll.grid(row=2, column=0, sticky='nsew',
                         padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_LG))
        self.scroll.grid_columnconfigure(0, weight=1)

    def _refresh(self):
        for child in self.scroll.winfo_children():
            child.destroy()

        query = self.search_entry.get().strip() if hasattr(self, 'search_entry') else ''
        records = self.history_mgr.search(query) if query else self.history_mgr.all()

        if not records:
            empty = ctk.CTkLabel(
                self.scroll,
                text='沒有紀錄' if query else '尚無轉錄紀錄\n按快捷鍵開始錄音，紀錄會顯示在這裡',
                font=font(Tokens.FONT_MD),
                text_color=self.colors['text_tertiary'],
                justify='center',
            )
            empty.grid(row=0, column=0, pady=Tokens.PAD_XL * 2)
            return

        for i, r in enumerate(records):
            self._render_record(i, r)

    def _render_record(self, idx, r):
        ts = r.get('ts', 0)
        when = self._format_time(ts)
        raw = r.get('raw', '') or ''
        enhanced = r.get('enhanced', '') or ''
        display = enhanced if enhanced else raw

        # AI 模型資訊
        tr_provider = r.get('transcriber_provider', '') or ''
        tr_model = r.get('transcriber_model', '') or ''
        en_provider = r.get('enhancer_provider', '') or ''
        en_model = r.get('enhancer_model', '') or ''
        profile_name = r.get('profile_name', '') or ''

        card = ctk.CTkFrame(
            self.scroll,
            fg_color=self.colors['bg_primary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'],
            border_width=1,
        )
        card.grid(row=idx, column=0, sticky='ew', pady=4, padx=4)
        card.grid_columnconfigure(0, weight=1)

        info_frame = ctk.CTkFrame(card, fg_color='transparent')
        info_frame.grid(row=0, column=0, sticky='ew', padx=Tokens.PAD_MD, pady=Tokens.PAD_SM)
        info_frame.grid_columnconfigure(0, weight=1)

        # 第 1 行：時間 + AI 標籤 + profile
        meta_row = ctk.CTkFrame(info_frame, fg_color='transparent')
        meta_row.grid(row=0, column=0, sticky='ew')

        ctk.CTkLabel(
            meta_row, text=when,
            font=font(Tokens.FONT_XS),
            text_color=self.colors['text_tertiary'],
            anchor='w',
        ).pack(side='left')

        # 轉錄 chip
        if tr_provider:
            chip_text = self._short_provider(tr_provider, tr_model)
            ctk.CTkLabel(
                meta_row, text=chip_text,
                font=font(Tokens.FONT_XS, 'bold'),
                text_color=self._provider_color(tr_provider),
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=1,
            ).pack(side='left', padx=(Tokens.PAD_SM, 0))

        # 潤色 chip (有的話)
        if en_provider:
            chip_text = '✨ ' + self._short_provider(en_provider, en_model)
            ctk.CTkLabel(
                meta_row, text=chip_text,
                font=font(Tokens.FONT_XS, 'bold'),
                text_color=self._provider_color(en_provider),
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=1,
            ).pack(side='left', padx=(4, 0))

        # profile chip
        if profile_name:
            ctk.CTkLabel(
                meta_row, text=f'· {profile_name}',
                font=font(Tokens.FONT_XS),
                text_color=self.colors['text_tertiary'],
            ).pack(side='left', padx=(4, 0))

        # 第 2 行：主要顯示文字
        text_lbl = ctk.CTkLabel(
            info_frame, text=display,
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_primary'],
            anchor='w', justify='left',
            wraplength=420,
        )
        text_lbl.grid(row=1, column=0, sticky='w', pady=(4, 0))

        # 第 3 行：原文 (有潤色才顯示)
        if enhanced and raw and enhanced != raw:
            orig_lbl = ctk.CTkLabel(
                info_frame, text=f'原文: {raw}',
                font=font(Tokens.FONT_XS),
                text_color=self.colors['text_tertiary'],
                anchor='w', justify='left',
                wraplength=420,
            )
            orig_lbl.grid(row=2, column=0, sticky='w', pady=(2, 0))

        # 動作按鈕
        btn_frame = ctk.CTkFrame(card, fg_color='transparent')
        btn_frame.grid(row=0, column=1, padx=Tokens.PAD_SM, pady=Tokens.PAD_SM, sticky='ne')

        copy_btn = ctk.CTkButton(
            btn_frame, text='複製', width=64, height=28,
            corner_radius=Tokens.RADIUS_SM,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_SM),
            command=lambda txt=display: self._copy(txt),
        )
        copy_btn.pack(side='top', pady=(0, 4))

        paste_btn = ctk.CTkButton(
            btn_frame, text='貼上', width=64, height=28,
            corner_radius=Tokens.RADIUS_SM,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_SM),
            command=lambda txt=display: self._paste(txt),
        )
        paste_btn.pack(side='top')

        del_btn = ctk.CTkButton(
            btn_frame, text='✕', width=28, height=24,
            corner_radius=Tokens.RADIUS_SM,
            fg_color='transparent',
            text_color=self.colors['text_tertiary'],
            hover_color=self.colors['bg_hover'],
            font=font(Tokens.FONT_SM),
            command=lambda i=idx: self._remove(i),
        )
        del_btn.pack(side='top', pady=(4, 0))

    def _short_provider(self, provider: str, model: str) -> str:
        """精簡顯示 provider/model — 如 'OpenAI · Whisper' / 'Groq · v3-turbo'"""
        display = {
            'openai': 'OpenAI',
            'anthropic': 'Claude',
            'google': 'Gemini',
            'groq': 'Groq',
        }
        # 從 model 取最後一段或簡稱
        short_model = model
        if 'whisper-large-v3-turbo' in model:
            short_model = 'v3-turbo'
        elif 'whisper-large-v3' in model:
            short_model = 'v3'
        elif 'whisper-1' in model:
            short_model = 'whisper'
        elif 'gpt-4o-mini' in model:
            short_model = '4o-mini'
        elif 'gpt-4o' in model:
            short_model = '4o'
        elif 'claude-haiku-4-5' in model:
            short_model = 'Haiku 4.5'
        elif 'claude-sonnet-4-6' in model:
            short_model = 'Sonnet 4.6'
        elif 'claude-opus-4-7' in model:
            short_model = 'Opus 4.7'
        elif 'gemini-2.5-flash' in model:
            short_model = '2.5 Flash'
        elif 'gemini-2.5-pro' in model:
            short_model = '2.5 Pro'
        elif 'llama-3.3-70b' in model:
            short_model = 'Llama 70B'
        elif 'llama-3.1-8b' in model:
            short_model = 'Llama 8B'
        return f'{display.get(provider, provider)} · {short_model}'

    def _provider_color(self, provider: str) -> str:
        return {
            'openai':    '#10B981',
            'anthropic': '#B179DE',
            'google':    '#4285F4',
            'groq':      '#FF6B35',
        }.get(provider, self.colors['text_secondary'])

    def _format_time(self, ts):
        if not ts:
            return ''
        now = time.time()
        diff = now - ts
        if diff < 60:
            return f'{int(diff)} 秒前'
        if diff < 3600:
            return f'{int(diff/60)} 分鐘前'
        if diff < 86400:
            return f'{int(diff/3600)} 小時前'
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))

    def _copy(self, text):
        pyperclip.copy(text)

    def _paste(self, text):
        pyperclip.copy(text)
        self.withdraw()  # 隱藏視窗讓 Ctrl+V 貼到下面的視窗
        self.after(200, lambda: self._do_paste(text))

    def _do_paste(self, text):
        if self.on_paste:
            try:
                self.on_paste(text)
            except Exception as e:
                print(f'paste callback failed: {e}')
        self.destroy()

    def _remove(self, idx):
        # idx 是 displayed 列表中的 index，但 records 可能被搜尋過濾
        # 簡單做法：用內容比對找到真實索引再刪
        query = self.search_entry.get().strip()
        displayed = self.history_mgr.search(query) if query else self.history_mgr.all()
        if 0 <= idx < len(displayed):
            target = displayed[idx]
            all_records = self.history_mgr.all()
            for i, r in enumerate(all_records):
                if r.get('ts') == target.get('ts') and r.get('raw') == target.get('raw'):
                    self.history_mgr.remove(i)
                    break
        self._refresh()

    def _clear_all(self):
        self.history_mgr.clear()
        self._refresh()
