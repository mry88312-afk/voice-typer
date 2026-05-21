"""歡迎精靈 - 第一次啟動引導使用者完成基礎設定"""
import webbrowser
import threading
import customtkinter as ctk

from ui.theme import get_colors, font, Tokens


class OnboardingWizard(ctk.CTkToplevel):
    """第一次啟動的引導視窗 (作為主 root 的 Toplevel)"""

    STEPS = ['歡迎', 'OpenAI Key', 'Claude Key', '快捷鍵', '完成']

    def __init__(self, parent, env_mgr, config_mgr, on_complete=None):
        super().__init__(parent)
        self.env_mgr = env_mgr
        self.config_mgr = config_mgr
        self.on_complete = on_complete
        self.colors = get_colors()

        self.title('Voice Typer - 初次設定')
        self.geometry('680x560')
        self.resizable(False, False)
        self.withdraw()  # 先隱藏，建構完再顯示
        self._center()

        self.current_step = 0
        self.openai_key = ''
        self.anthropic_key = ''

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_stepper()
        self._build_content_area()
        self._build_footer()

        self._render_step()

        self.update_idletasks()
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 680, 560
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'],
                              corner_radius=0, height=80)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)

        title = ctk.CTkLabel(
            header,
            text='歡迎使用 Voice Typer',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
        )
        title.pack(anchor='w', padx=Tokens.PAD_XL, pady=(Tokens.PAD_LG, 0))

        subtitle = ctk.CTkLabel(
            header,
            text='只要 1 分鐘設定，就能用語音取代打字',
            font=font(Tokens.FONT_SM),
            text_color=self.colors['text_secondary'],
        )
        subtitle.pack(anchor='w', padx=Tokens.PAD_XL, pady=(2, 0))

    def _build_stepper(self):
        wrapper = ctk.CTkFrame(self, fg_color='transparent', height=50)
        wrapper.grid(row=1, column=0, sticky='ew', padx=Tokens.PAD_XL)
        wrapper.grid_propagate(False)

        self.step_dots = []
        for i, name in enumerate(self.STEPS):
            dot = ctk.CTkLabel(
                wrapper,
                text=f'  {i+1}  {name}  ',
                font=font(Tokens.FONT_SM, 'bold'),
                text_color=self.colors['text_tertiary'],
                fg_color=self.colors['bg_secondary'],
                corner_radius=Tokens.RADIUS_SM,
            )
            dot.grid(row=0, column=i, padx=4, pady=Tokens.PAD_SM, sticky='w')
            self.step_dots.append(dot)

    def _build_content_area(self):
        self.content = ctk.CTkFrame(self, fg_color='transparent')
        self.content.grid(row=2, column=0, sticky='nsew', padx=Tokens.PAD_XL)
        self.content.grid_columnconfigure(0, weight=1)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color='transparent', height=70)
        footer.grid(row=3, column=0, sticky='ew', padx=Tokens.PAD_XL, pady=Tokens.PAD_MD)
        footer.grid_columnconfigure(1, weight=1)

        self.back_btn = ctk.CTkButton(
            footer, text='← 上一步', width=110, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
            command=self._prev,
        )
        self.back_btn.grid(row=0, column=0, sticky='w')

        self.skip_btn = ctk.CTkButton(
            footer, text='略過', width=80, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_tertiary'],
            hover_color=self.colors['bg_hover'],
            border_width=0,
            font=font(Tokens.FONT_SM),
            command=self._next,
        )
        self.skip_btn.grid(row=0, column=1, sticky='e', padx=Tokens.PAD_SM)

        self.next_btn = ctk.CTkButton(
            footer, text='下一步 →', width=120, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_MD, 'bold'),
            command=self._next,
        )
        self.next_btn.grid(row=0, column=2, sticky='e')

    def _render_step(self):
        # 清空 content
        for child in self.content.winfo_children():
            child.destroy()

        # 更新 stepper
        for i, dot in enumerate(self.step_dots):
            if i < self.current_step:
                dot.configure(
                    text_color=self.colors['success'],
                    fg_color=self.colors['bg_secondary'],
                )
            elif i == self.current_step:
                dot.configure(
                    text_color='#FFFFFF',
                    fg_color=self.colors['accent'],
                )
            else:
                dot.configure(
                    text_color=self.colors['text_tertiary'],
                    fg_color=self.colors['bg_secondary'],
                )

        # 按鈕狀態
        self.back_btn.configure(state='normal' if self.current_step > 0 else 'disabled')

        renderers = [
            self._render_welcome,
            self._render_openai,
            self._render_anthropic,
            self._render_hotkey,
            self._render_complete,
        ]
        renderers[self.current_step]()

    def _render_welcome(self):
        title = ctk.CTkLabel(
            self.content, text='開始之前',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )
        title.grid(row=0, column=0, sticky='w', pady=(Tokens.PAD_LG, Tokens.PAD_MD))

        desc = ctk.CTkLabel(
            self.content,
            text=(
                'Voice Typer 用 OpenAI Whisper 將你的語音轉成文字，\n'
                '搭配 Claude 做潤色，可以無縫取代日常打字。\n\n'
                '接下來會引導你：\n'
                '• 設定 OpenAI API Key (必須)\n'
                '• 設定 Anthropic API Key (選用，啟用 AI 潤色)\n'
                '• 確認快捷鍵\n\n'
                '整個過程大約 1 分鐘。'
            ),
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_secondary'],
            anchor='w', justify='left',
        )
        desc.grid(row=1, column=0, sticky='w')

        self.skip_btn.configure(text='略過')
        self.next_btn.configure(text='開始 →')

    def _render_openai(self):
        title = ctk.CTkLabel(
            self.content, text='OpenAI API Key',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )
        title.grid(row=0, column=0, sticky='w', pady=(Tokens.PAD_LG, Tokens.PAD_SM))

        steps = ctk.CTkLabel(
            self.content,
            text=(
                '1. 點下方按鈕去 OpenAI 申請 (免費註冊)\n'
                '2. 充值 $5 美金 (夠用半年以上)\n'
                '3. 複製 sk-proj-... 開頭的 Key 貼到下方'
            ),
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_secondary'],
            anchor='w', justify='left',
        )
        steps.grid(row=1, column=0, sticky='w', pady=(0, Tokens.PAD_MD))

        link = ctk.CTkButton(
            self.content, text='前往 OpenAI 申請 →', width=200, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            hover_color=self.colors['bg_hover'],
            text_color=self.colors['accent'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
            command=lambda: webbrowser.open('https://platform.openai.com/api-keys'),
        )
        link.grid(row=2, column=0, sticky='w', pady=(0, Tokens.PAD_LG))

        ctk.CTkLabel(
            self.content, text='貼上你的 Key：',
            font=font(Tokens.FONT_MD, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=3, column=0, sticky='w', pady=(0, Tokens.PAD_XS))

        self.openai_entry = ctk.CTkEntry(
            self.content, height=42,
            placeholder_text='sk-proj-...',
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
        )
        self.openai_entry.grid(row=4, column=0, sticky='ew')
        existing = self.env_mgr.get('OPENAI_API_KEY') or self.openai_key
        if existing and not existing.startswith('sk-your-'):
            self.openai_entry.insert(0, existing)

        self.openai_status = ctk.CTkLabel(
            self.content, text='',
            font=font(Tokens.FONT_SM),
            anchor='w',
        )
        self.openai_status.grid(row=5, column=0, sticky='w', pady=(Tokens.PAD_SM, 0))

        self.skip_btn.configure(text='略過 (稍後設定)')
        self.next_btn.configure(text='測試並繼續 →', command=self._validate_openai)

    def _validate_openai(self):
        key = self.openai_entry.get().strip()
        if not key:
            self.openai_status.configure(
                text='⚠️ 必填欄位 (沒有 Key 無法使用語音辨識)',
                text_color=self.colors['warning'],
            )
            return

        self.openai_status.configure(
            text='測試中...', text_color=self.colors['text_secondary']
        )

        def run():
            try:
                from openai import OpenAI
                OpenAI(api_key=key).models.list()
                self.openai_key = key
                self.env_mgr.set('OPENAI_API_KEY', key)
                self.after(0, self._do_next)
            except Exception as e:
                self.after(0, lambda: self.openai_status.configure(
                    text=f'❌ 連線失敗: {str(e)[:60]}',
                    text_color=self.colors['danger'],
                ))

        threading.Thread(target=run, daemon=True).start()

    def _render_anthropic(self):
        title = ctk.CTkLabel(
            self.content, text='Anthropic API Key (選用)',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )
        title.grid(row=0, column=0, sticky='w', pady=(Tokens.PAD_LG, Tokens.PAD_SM))

        desc = ctk.CTkLabel(
            self.content,
            text=(
                '加入 Anthropic Claude 可以啟用「AI 潤色」功能：\n'
                '把口語化的辨識結果整理成通順的書面語。\n\n'
                '不想用可以點「略過」，之後也能從設定加。'
            ),
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_secondary'],
            anchor='w', justify='left',
        )
        desc.grid(row=1, column=0, sticky='w', pady=(0, Tokens.PAD_MD))

        link = ctk.CTkButton(
            self.content, text='前往 Anthropic 申請 →', width=200, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            hover_color=self.colors['bg_hover'],
            text_color=self.colors['accent'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
            command=lambda: webbrowser.open('https://console.anthropic.com/keys'),
        )
        link.grid(row=2, column=0, sticky='w', pady=(0, Tokens.PAD_LG))

        ctk.CTkLabel(
            self.content, text='貼上你的 Key：',
            font=font(Tokens.FONT_MD, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=3, column=0, sticky='w', pady=(0, Tokens.PAD_XS))

        self.anthropic_entry = ctk.CTkEntry(
            self.content, height=42,
            placeholder_text='sk-ant-api03-... (選填)',
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
        )
        self.anthropic_entry.grid(row=4, column=0, sticky='ew')
        existing = self.env_mgr.get('ANTHROPIC_API_KEY') or self.anthropic_key
        if existing and not existing.startswith('sk-ant-your-'):
            self.anthropic_entry.insert(0, existing)

        self.anthropic_status = ctk.CTkLabel(
            self.content, text='',
            font=font(Tokens.FONT_SM),
            anchor='w',
        )
        self.anthropic_status.grid(row=5, column=0, sticky='w', pady=(Tokens.PAD_SM, 0))

        self.skip_btn.configure(text='略過 (不啟用 AI 潤色)')
        self.next_btn.configure(text='下一步 →', command=self._validate_anthropic)

    def _validate_anthropic(self):
        key = self.anthropic_entry.get().strip()
        if not key:
            # 沒填就跳過
            self._do_next()
            return

        self.anthropic_status.configure(
            text='測試中...', text_color=self.colors['text_secondary']
        )

        def run():
            try:
                from anthropic import Anthropic
                Anthropic(api_key=key).messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=8,
                    messages=[{'role': 'user', 'content': 'hi'}],
                )
                self.anthropic_key = key
                self.env_mgr.set('ANTHROPIC_API_KEY', key)
                self.config_mgr.set('enable_ai_enhance', True)
                self.after(0, self._do_next)
            except Exception as e:
                self.after(0, lambda: self.anthropic_status.configure(
                    text=f'❌ 連線失敗: {str(e)[:60]}',
                    text_color=self.colors['danger'],
                ))

        threading.Thread(target=run, daemon=True).start()

    def _render_hotkey(self):
        title = ctk.CTkLabel(
            self.content, text='快捷鍵設定',
            font=font(Tokens.FONT_XL, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )
        title.grid(row=0, column=0, sticky='w', pady=(Tokens.PAD_LG, Tokens.PAD_SM))

        desc = ctk.CTkLabel(
            self.content,
            text='你可以用快捷鍵在任何視窗開始錄音。預設值已經很好用，建議直接保留。',
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_secondary'],
            anchor='w', justify='left',
        )
        desc.grid(row=1, column=0, sticky='w', pady=(0, Tokens.PAD_LG))

        ctk.CTkLabel(
            self.content, text='開始 / 結束錄音',
            font=font(Tokens.FONT_MD, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=2, column=0, sticky='w', pady=(0, Tokens.PAD_XS))

        self.hotkey_entry = ctk.CTkEntry(
            self.content, height=42,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
        )
        self.hotkey_entry.insert(0, self.config_mgr.get('hotkey', 'ctrl+shift+space'))
        self.hotkey_entry.grid(row=3, column=0, sticky='ew', pady=(0, Tokens.PAD_MD))

        ctk.CTkLabel(
            self.content, text='取消錄音',
            font=font(Tokens.FONT_MD, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=4, column=0, sticky='w', pady=(0, Tokens.PAD_XS))

        self.cancel_hotkey_entry = ctk.CTkEntry(
            self.content, height=42,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            font=font(Tokens.FONT_MD),
        )
        self.cancel_hotkey_entry.insert(0, self.config_mgr.get('cancel_hotkey', 'ctrl+shift+x'))
        self.cancel_hotkey_entry.grid(row=5, column=0, sticky='ew')

        self.skip_btn.configure(text='略過 (使用預設)')
        self.next_btn.configure(text='下一步 →', command=self._save_hotkey)

    def _save_hotkey(self):
        self.config_mgr.set('hotkey', self.hotkey_entry.get().strip() or 'ctrl+shift+space')
        self.config_mgr.set('cancel_hotkey', self.cancel_hotkey_entry.get().strip() or 'ctrl+shift+x')
        self._do_next()

    def _render_complete(self):
        title = ctk.CTkLabel(
            self.content, text='完成設定',
            font=font(Tokens.FONT_XXL, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )
        title.grid(row=0, column=0, sticky='w', pady=(Tokens.PAD_XL, Tokens.PAD_MD))

        hotkey = self.config_mgr.get('hotkey', 'ctrl+shift+space')
        cancel = self.config_mgr.get('cancel_hotkey', 'ctrl+shift+x')

        desc = ctk.CTkLabel(
            self.content,
            text=(
                f'你已經完成所有設定！\n\n'
                f'快捷鍵：\n'
                f'  • {hotkey} → 開始 / 結束錄音\n'
                f'  • {cancel} → 取消錄音\n\n'
                f'圖示會出現在系統匣 (右下角 ^)。\n'
                f'從那邊可以隨時打開設定、看歷史紀錄。\n\n'
                f'點「開始使用」進入主程式！'
            ),
            font=font(Tokens.FONT_MD),
            text_color=self.colors['text_secondary'],
            anchor='w', justify='left',
        )
        desc.grid(row=1, column=0, sticky='w')

        self.skip_btn.grid_remove()
        self.back_btn.grid_remove()
        self.next_btn.configure(text='開始使用 🚀', command=self._finish)

    def _prev(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.next_btn.configure(command=self._next)
            self.skip_btn.grid()
            self.back_btn.grid()
            self._render_step()

    def _next(self):
        self._do_next()

    def _do_next(self):
        if self.current_step < len(self.STEPS) - 1:
            self.current_step += 1
            self.next_btn.configure(command=self._next)
            self._render_step()
        else:
            self._finish()

    def _finish(self):
        self.config_mgr.set('first_run', False)
        self.config_mgr.save()
        cb = self.on_complete
        self.destroy()
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"onboarding callback failed: {e}")
