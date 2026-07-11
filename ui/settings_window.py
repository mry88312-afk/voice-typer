"""設定視窗 — 7 個 tabs: API Keys / 引擎 / 快捷鍵 / 辨識 / 情境 / 進階"""
import webbrowser
import threading
import keyboard
import customtkinter as ctk

from ui.theme import get_colors, font, Tokens, apply_font_to_descendants
from core.transcription import TRANSCRIBER_PROVIDERS, ENHANCER_PROVIDERS


# 4 個 provider 的 API Key 資訊
API_KEY_PROVIDERS = [
    {
        'name': 'OpenAI',
        'env': 'OPENAI_API_KEY',
        'prefix': 'sk-',
        'description': 'Whisper / GPT-4o',
        'url': 'https://platform.openai.com/api-keys',
        'required': True,
    },
    {
        'name': 'Anthropic',
        'env': 'ANTHROPIC_API_KEY',
        'prefix': 'sk-ant-',
        'description': 'Claude (潤色)',
        'url': 'https://console.anthropic.com/keys',
        'required': False,
    },
    {
        'name': 'Google',
        'env': 'GOOGLE_API_KEY',
        'prefix': '',
        'description': 'Gemini 2.5',
        'url': 'https://aistudio.google.com/apikey',
        'required': False,
    },
    {
        'name': 'Groq',
        'env': 'GROQ_API_KEY',
        'prefix': 'gsk_',
        'description': 'Whisper Turbo / Llama (極快)',
        'url': 'https://console.groq.com/keys',
        'required': False,
    },
]


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config_mgr, env_mgr,
                 profile_mgr=None, learned_mgr=None, on_save=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.env_mgr = env_mgr
        self.profile_mgr = profile_mgr
        self.learned_mgr = learned_mgr
        self.on_save = on_save
        self.colors = get_colors()

        self.title('Voice Typer 設定')
        self.geometry('820x680')
        self.minsize(760, 600)
        self.resizable(True, True)
        self.withdraw()
        self._center_on_screen()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.api_entries = {}     # {env_name: ctk.CTkEntry}
        self.api_show = {}        # {env_name: bool}
        self.api_status = {}      # {env_name: ctk.CTkLabel}
        self.profile_widgets = {} # 編輯中的 profile widgets

        self._build_header()
        self._build_tabs()
        self._build_footer()

        self.update_idletasks()
        apply_font_to_descendants(self)
        self.update_idletasks()

        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center_on_screen(self):
        self.update_idletasks()
        w, h = 820, 680
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f'{w}x{h}+{x}+{y}')

    # ---------- Header ----------
    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0,
                              fg_color=self.colors['bg_primary'], height=72)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            header, text='設定',
            font=font(Tokens.FONT_TITLE, 'bold'),
            text_color=self.colors['text_primary'],
        )
        title.grid(row=0, column=0, padx=Tokens.PAD_XL, pady=Tokens.PAD_LG, sticky='w')

        subtitle = ctk.CTkLabel(
            header, text='調整 API、引擎、情境、快捷鍵',
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
        )
        subtitle.grid(row=0, column=1, padx=(0, Tokens.PAD_XL), pady=Tokens.PAD_LG, sticky='w')

        sep = ctk.CTkFrame(self, height=1, fg_color=self.colors['border'])
        sep.grid(row=0, column=0, sticky='ews', pady=(71, 0))

    # ---------- Tabs ----------
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=0,
            fg_color=self.colors['bg_primary'],
            segmented_button_selected_color=self.colors['accent'],
            segmented_button_selected_hover_color=self.colors['accent_hover'],
        )
        self.tabview.grid(row=1, column=0, sticky='nsew', padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)

        for name in ['API Keys', '引擎', '情境', '辨識', '自學詞典', '快捷鍵', '進階']:
            self.tabview.add(name)

        self._build_api_tab(self.tabview.tab('API Keys'))
        self._build_engines_tab(self.tabview.tab('引擎'))
        self._build_profiles_tab(self.tabview.tab('情境'))
        self._build_recognition_tab(self.tabview.tab('辨識'))
        self._build_learned_tab(self.tabview.tab('自學詞典'))
        self._build_hotkey_tab(self.tabview.tab('快捷鍵'))
        self._build_advanced_tab(self.tabview.tab('進階'))

    # ---------- Footer ----------
    def _build_footer(self):
        footer = ctk.CTkFrame(self, corner_radius=0, fg_color='transparent', height=70)
        footer.grid(row=2, column=0, sticky='ew', padx=Tokens.PAD_XL, pady=Tokens.PAD_MD)
        footer.grid_columnconfigure(0, weight=1)

        self.footer_msg = ctk.CTkLabel(
            footer, text='',
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
        )
        self.footer_msg.grid(row=0, column=0, sticky='w')

        btn_frame = ctk.CTkFrame(footer, fg_color='transparent')
        btn_frame.grid(row=0, column=1, sticky='e')

        ctk.CTkButton(
            btn_frame, text='取消', width=88, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY),
            command=self.destroy,
        ).pack(side='right', padx=(Tokens.PAD_SM, 0))

        ctk.CTkButton(
            btn_frame, text='儲存', width=88, height=38,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_BODY, 'bold'),
            command=self._save_all,
        ).pack(side='right')

    # ---------- Helpers ----------
    def _label(self, parent, text, secondary=False):
        return ctk.CTkLabel(
            parent, text=text,
            font=font(
                Tokens.FONT_BODY_SM if secondary else Tokens.FONT_BODY,
                'normal' if secondary else 'bold',
            ),
            text_color=self.colors['text_secondary'] if secondary else self.colors['text_primary'],
            anchor='w',
        )

    def _section_title(self, parent, text):
        return ctk.CTkLabel(
            parent, text=text,
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        )

    def _entry(self, parent, show=None, placeholder=''):
        return ctk.CTkEntry(
            parent, height=Tokens.HEIGHT_INPUT,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            border_width=1,
            text_color=self.colors['text_primary'],
            placeholder_text=placeholder,
            placeholder_text_color=self.colors['text_tertiary'],
            show=show,
            font=font(Tokens.FONT_BODY),
        )

    def _link_button(self, parent, text, url):
        return ctk.CTkButton(
            parent, text=text,
            width=110, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['accent'],
            hover_color=self.colors['bg_hover'],
            border_width=0,
            font=font(Tokens.FONT_BODY_SM),
            command=lambda: webbrowser.open(url),
        )

    def _show_message(self, text, color_key='text_secondary'):
        self.footer_msg.configure(text=text, text_color=self.colors[color_key])
        self.after(4000, lambda: self.footer_msg.configure(text=''))

    # ---------- Tab: API Keys (4 providers) ----------
    def _build_api_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.colors['bg_primary'])
        scroll.grid(row=0, column=0, sticky='nsew', padx=0, pady=Tokens.PAD_MD)
        scroll.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        for idx, p in enumerate(API_KEY_PROVIDERS):
            self._build_api_card(scroll, p, idx)

    def _build_api_card(self, parent, p, idx):
        """緊湊卡片 — 三列容納完整一個 provider，可一畫面看到 2-3 個"""
        env = p['env']
        card = ctk.CTkFrame(
            parent,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'],
            border_width=1,
        )
        card.grid(row=idx, column=0, sticky='ew', padx=Tokens.PAD_SM, pady=4)
        card.grid_columnconfigure(0, weight=1)

        # 第 1 列：名稱 + 描述 + 狀態 (同一行)
        title_row = ctk.CTkFrame(card, fg_color='transparent')
        title_row.grid(row=0, column=0, sticky='ew',
                       padx=Tokens.PAD_MD, pady=(Tokens.PAD_SM, 2))
        title_row.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            title_row, text=p['name'],
            font=font(Tokens.FONT_BODY_LG, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=0, column=0, sticky='w')

        ctk.CTkLabel(
            title_row, text=f"  ·  {p['description']}",
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_tertiary'],
            anchor='w',
        ).grid(row=0, column=1, sticky='w')

        status = ctk.CTkLabel(
            title_row, text='', font=font(Tokens.FONT_BODY_SM), anchor='e',
        )
        status.grid(row=0, column=2, sticky='e')
        self.api_status[env] = status

        # 第 2 列：輸入框 + 眼睛
        input_row = ctk.CTkFrame(card, fg_color='transparent')
        input_row.grid(row=1, column=0, sticky='ew',
                       padx=Tokens.PAD_MD, pady=(0, 4))
        input_row.grid_columnconfigure(0, weight=1)

        entry = self._entry(input_row, show='•',
                            placeholder=p.get('prefix', '') + '...')
        entry.grid(row=0, column=0, sticky='ew')
        current = self.env_mgr.get(env) or ''
        if current and 'your-' not in current.lower():
            entry.insert(0, current)
        self.api_entries[env] = entry
        self.api_show[env] = False

        eye_btn = ctk.CTkButton(
            input_row, text='👁',
            width=40, height=Tokens.HEIGHT_INPUT,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_tertiary'],
            hover_color=self.colors['bg_hover'],
            text_color=self.colors['text_secondary'],
            border_width=1, border_color=self.colors['border'],
            command=lambda e=env: self._toggle_eye(e),
        )
        eye_btn.grid(row=0, column=1, padx=(4, 0))

        # 第 3 列：按鈕
        actions = ctk.CTkFrame(card, fg_color='transparent')
        actions.grid(row=2, column=0, sticky='w',
                     padx=Tokens.PAD_MD, pady=(0, Tokens.PAD_SM))

        ctk.CTkButton(
            actions, text='測試連線', width=90, height=28,
            corner_radius=Tokens.RADIUS_SM,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY_SM),
            command=lambda e=env: self._test_api(e),
        ).pack(side='left')

        self._link_button(actions, '取得 Key →', p['url']).pack(
            side='left', padx=(4, 0)
        )

        self._refresh_status(env)

    def _toggle_eye(self, env):
        self.api_show[env] = not self.api_show[env]
        self.api_entries[env].configure(show='' if self.api_show[env] else '•')

    def _refresh_status(self, env):
        ok = self.env_mgr.is_valid(env)
        status = self.api_status.get(env)
        if not status:
            return
        if ok:
            status.configure(text='● 已設定', text_color=self.colors['success'])
        else:
            status.configure(text='○ 未設定', text_color=self.colors['text_tertiary'])

    def _test_api(self, env):
        self._show_message(f'測試 {env} 連線中...', 'text_secondary')
        key = self.api_entries[env].get().strip()
        if not key:
            self._show_message('請先填入 Key', 'warning')
            return

        def run():
            try:
                if env == 'OPENAI_API_KEY':
                    from openai import OpenAI
                    OpenAI(api_key=key).models.list()
                elif env == 'ANTHROPIC_API_KEY':
                    from anthropic import Anthropic
                    Anthropic(api_key=key).messages.create(
                        model='claude-haiku-4-5-20251001',
                        max_tokens=8,
                        messages=[{'role': 'user', 'content': 'hi'}],
                    )
                elif env == 'GOOGLE_API_KEY':
                    from google import genai
                    client = genai.Client(api_key=key)
                    client.models.list()
                elif env == 'GROQ_API_KEY':
                    from groq import Groq
                    Groq(api_key=key).models.list()
                self.after(0, lambda: self._show_message(f'✓ {env} 連線成功', 'success'))
            except Exception as e:
                msg = f'✕ {env} 連線失敗: {str(e)[:60]}'
                self.after(0, lambda: self._show_message(msg, 'danger'))

        threading.Thread(target=run, daemon=True).start()

    # ---------- Tab: 引擎 ----------
    def _build_engines_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        # ── 語音辨識引擎 ──
        self._section_title(parent, '語音辨識引擎').grid(
            row=0, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, Tokens.PAD_SM)
        )
        self._label(
            parent, '把語音轉成文字。Whisper 穩定便宜，Groq 是 Whisper 但速度快 3 倍',
            secondary=True,
        ).grid(row=1, column=0, sticky='w', padx=Tokens.PAD_LG)

        tr_row = ctk.CTkFrame(parent, fg_color='transparent')
        tr_row.grid(row=2, column=0, sticky='ew',
                    padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)
        tr_row.grid_columnconfigure((0, 1), weight=1)

        # Provider 下拉
        tr_cfg = self.config_mgr.get('transcriber') or {'provider': 'openai', 'model': 'whisper-1'}

        self._label(tr_row, '提供商').grid(row=0, column=0, sticky='w')
        self.tr_provider_var = ctk.StringVar(value=tr_cfg.get('provider', 'openai'))
        tr_provider_menu = ctk.CTkOptionMenu(
            tr_row,
            values=list(TRANSCRIBER_PROVIDERS.keys()),
            variable=self.tr_provider_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
            command=self._on_tr_provider_change,
        )
        tr_provider_menu.grid(row=1, column=0, sticky='ew', padx=(0, Tokens.PAD_SM))

        self._label(tr_row, '模型').grid(row=0, column=1, sticky='w', padx=(Tokens.PAD_SM, 0))
        self.tr_model_var = ctk.StringVar(value=tr_cfg.get('model', 'whisper-1'))
        self.tr_model_menu = ctk.CTkOptionMenu(
            tr_row,
            values=[m['id'] for m in TRANSCRIBER_PROVIDERS.get(
                self.tr_provider_var.get(), {'models': []}
            )['models']],
            variable=self.tr_model_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
        )
        self.tr_model_menu.grid(row=1, column=1, sticky='ew', padx=(Tokens.PAD_SM, 0))

        # ── AI 潤色引擎 ──
        self._section_title(parent, 'AI 潤色引擎').grid(
            row=3, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_XL, Tokens.PAD_SM)
        )
        self._label(
            parent, '把轉錄結果改寫成更通順的文字。每個情境可有獨立的指令',
            secondary=True,
        ).grid(row=4, column=0, sticky='w', padx=Tokens.PAD_LG)

        en_cfg = self.config_mgr.get('enhancer') or {'provider': 'anthropic', 'model': 'claude-haiku-4-5-20251001'}

        en_row = ctk.CTkFrame(parent, fg_color='transparent')
        en_row.grid(row=5, column=0, sticky='ew',
                    padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)
        en_row.grid_columnconfigure((0, 1), weight=1)

        self._label(en_row, '提供商').grid(row=0, column=0, sticky='w')
        self.en_provider_var = ctk.StringVar(value=en_cfg.get('provider', 'anthropic'))
        ctk.CTkOptionMenu(
            en_row,
            values=list(ENHANCER_PROVIDERS.keys()),
            variable=self.en_provider_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
            command=self._on_en_provider_change,
        ).grid(row=1, column=0, sticky='ew', padx=(0, Tokens.PAD_SM))

        self._label(en_row, '模型').grid(row=0, column=1, sticky='w', padx=(Tokens.PAD_SM, 0))
        self.en_model_var = ctk.StringVar(value=en_cfg.get('model', 'claude-haiku-4-5-20251001'))
        self.en_model_menu = ctk.CTkOptionMenu(
            en_row,
            values=[m['id'] for m in ENHANCER_PROVIDERS.get(
                self.en_provider_var.get(), {'models': []}
            )['models']],
            variable=self.en_model_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
        )
        self.en_model_menu.grid(row=1, column=1, sticky='ew', padx=(Tokens.PAD_SM, 0))

    def _on_tr_provider_change(self, val):
        models = TRANSCRIBER_PROVIDERS.get(val, {'models': []})['models']
        ids = [m['id'] for m in models]
        if ids:
            self.tr_model_menu.configure(values=ids)
            self.tr_model_var.set(ids[0])

    def _on_en_provider_change(self, val):
        models = ENHANCER_PROVIDERS.get(val, {'models': []})['models']
        ids = [m['id'] for m in models]
        if ids:
            self.en_model_menu.configure(values=ids)
            self.en_model_var.set(ids[0])

    # ---------- Tab: 情境 (Profiles) ----------
    def _build_profiles_tab(self, parent):
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # 左側：profile 列表
        left = ctk.CTkFrame(parent, fg_color=self.colors['bg_secondary'],
                            corner_radius=Tokens.RADIUS_MD,
                            border_color=self.colors['border'], border_width=1,
                            width=180)
        left.grid(row=0, column=0, sticky='ns', padx=(Tokens.PAD_MD, Tokens.PAD_SM), pady=Tokens.PAD_MD)
        left.grid_columnconfigure(0, weight=1)
        left.grid_propagate(False)

        ctk.CTkLabel(
            left, text='情境列表',
            font=font(Tokens.FONT_BODY_SM, 'bold'),
            text_color=self.colors['text_secondary'],
            anchor='w',
        ).pack(anchor='w', padx=Tokens.PAD_MD, pady=(Tokens.PAD_MD, Tokens.PAD_SM))

        self.profile_list_frame = ctk.CTkScrollableFrame(left, fg_color=self.colors['bg_primary'])
        self.profile_list_frame.pack(fill='both', expand=True, padx=Tokens.PAD_XS, pady=(0, Tokens.PAD_SM))

        self.selected_profile_id = self.profile_mgr.active().get('id') if self.profile_mgr else 'default'

        # 右側：profile 編輯區
        self.profile_edit_area = ctk.CTkFrame(parent, fg_color='transparent')
        self.profile_edit_area.grid(row=0, column=1, sticky='nsew',
                                     padx=(Tokens.PAD_SM, Tokens.PAD_MD), pady=Tokens.PAD_MD)
        self.profile_edit_area.grid_columnconfigure(0, weight=1)
        self.profile_edit_area.grid_rowconfigure(99, weight=1)  # 留白

        self._render_profile_list()
        self._render_profile_edit(self.selected_profile_id)

    def _render_profile_list(self):
        if not self.profile_mgr:
            return
        for child in self.profile_list_frame.winfo_children():
            child.destroy()

        for p in self.profile_mgr.all():
            pid = p.get('id')
            is_active = pid == self.selected_profile_id
            row = ctk.CTkFrame(
                self.profile_list_frame,
                fg_color=self.colors['accent_subtle'] if is_active else 'transparent',
                corner_radius=Tokens.RADIUS_SM,
                height=44,
            )
            row.pack(fill='x', pady=2)

            btn = ctk.CTkButton(
                row, text=p.get('name', pid),
                anchor='w', height=40,
                corner_radius=Tokens.RADIUS_SM,
                fg_color='transparent',
                text_color=self.colors['accent'] if is_active else self.colors['text_primary'],
                hover_color=self.colors['bg_hover'],
                font=font(Tokens.FONT_BODY, 'bold' if is_active else 'normal'),
                command=lambda x=pid: self._select_profile(x),
            )
            btn.pack(fill='x', padx=4)

    def _select_profile(self, pid):
        # 儲存當前編輯中的內容
        self._capture_profile_edit()
        self.selected_profile_id = pid
        self._render_profile_list()
        self._render_profile_edit(pid)

    def _render_profile_edit(self, pid):
        for child in self.profile_edit_area.winfo_children():
            child.destroy()
        if not self.profile_mgr:
            return

        p = self.profile_mgr.get(pid)
        if not p:
            return

        # 標題
        ctk.CTkLabel(
            self.profile_edit_area, text=p.get('name', ''),
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=0, column=0, sticky='w', pady=(0, Tokens.PAD_XS))

        ctk.CTkLabel(
            self.profile_edit_area, text=p.get('description', ''),
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
            anchor='w',
        ).grid(row=1, column=0, sticky='w', pady=(0, Tokens.PAD_MD))

        # 啟用 AI 潤色
        enable_row = ctk.CTkFrame(self.profile_edit_area, fg_color='transparent')
        enable_row.grid(row=2, column=0, sticky='ew', pady=Tokens.PAD_SM)
        enable_row.grid_columnconfigure(0, weight=1)

        self._label(enable_row, '啟用 AI 潤色').grid(row=0, column=0, sticky='w')
        enable_sw = ctk.CTkSwitch(
            enable_row, text='',
            fg_color=self.colors['bg_tertiary'],
            progress_color=self.colors['accent'],
        )
        if p.get('enhance_enabled', False):
            enable_sw.select()
        enable_sw.grid(row=0, column=1, sticky='e')
        self.profile_widgets['enable_sw'] = enable_sw

        # AI 潤色指令
        self._label(self.profile_edit_area, '潤色指令 (Prompt)').grid(
            row=3, column=0, sticky='w', pady=(Tokens.PAD_MD, Tokens.PAD_XS)
        )

        prompt_text = ctk.CTkTextbox(
            self.profile_edit_area, height=180,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            border_width=1,
            text_color=self.colors['text_primary'],
            font=font(Tokens.FONT_BODY),
            wrap='word',
        )
        prompt_text.grid(row=4, column=0, sticky='ew')
        prompt_text.insert('0.0', p.get('enhance_prompt', ''))
        self.profile_widgets['prompt_text'] = prompt_text

        # 詞典
        self._label(self.profile_edit_area, '專屬詞彙 (用 , 或換行分隔)').grid(
            row=5, column=0, sticky='w', pady=(Tokens.PAD_MD, Tokens.PAD_XS)
        )

        vocab_text = ctk.CTkTextbox(
            self.profile_edit_area, height=80,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            border_width=1,
            text_color=self.colors['text_primary'],
            font=font(Tokens.FONT_BODY),
            wrap='word',
        )
        vocab_text.grid(row=6, column=0, sticky='ew')
        vocab_text.insert('0.0', ', '.join(p.get('vocabulary', []) or []))
        self.profile_widgets['vocab_text'] = vocab_text

    def _capture_profile_edit(self):
        """把右側編輯區的值寫回 profile (用 profile_mgr.update)"""
        if not self.profile_widgets or not self.profile_mgr:
            return
        pid = self.selected_profile_id
        if not pid:
            return
        try:
            enable = bool(self.profile_widgets['enable_sw'].get())
            prompt = self.profile_widgets['prompt_text'].get('0.0', 'end').strip()
            vocab_raw = self.profile_widgets['vocab_text'].get('0.0', 'end').strip()
            # 解析詞彙：支援逗號 / 換行 / 全形逗號
            vocab = []
            for token in vocab_raw.replace('，', ',').replace('\n', ',').split(','):
                t = token.strip()
                if t and t not in vocab:
                    vocab.append(t)
            self.profile_mgr.update(pid,
                enhance_enabled=enable,
                enhance_prompt=prompt,
                vocabulary=vocab,
            )
        except Exception as e:
            print(f"capture profile failed: {e}")

    # ---------- Tab: 辨識 ----------
    def _build_recognition_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self._section_title(parent, '辨識語言').grid(
            row=0, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, Tokens.PAD_SM)
        )
        self.language_var = ctk.StringVar(value=self.config_mgr.get('language', 'zh'))
        ctk.CTkOptionMenu(
            parent,
            values=['auto', 'zh', 'en', 'ja', 'ko'],
            variable=self.language_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
        ).grid(row=1, column=0, sticky='w', padx=Tokens.PAD_LG)

        self._label(
            parent, 'auto = 自動偵測，zh = 中文 (推薦)，en = 英文',
            secondary=True,
        ).grid(row=2, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(Tokens.PAD_XS, 0))

        self._section_title(parent, 'Whisper Prompt').grid(
            row=3, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_XL, Tokens.PAD_SM)
        )
        self._label(
            parent,
            '引導辨識風格的「樣本對話」，不要寫成指令。建議帶標點符號作示範',
            secondary=True,
        ).grid(row=4, column=0, sticky='w', padx=Tokens.PAD_LG)

        self.whisper_prompt_text = ctk.CTkTextbox(
            parent, height=100,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['bg_secondary'],
            border_color=self.colors['border'],
            border_width=1,
            text_color=self.colors['text_primary'],
            font=font(Tokens.FONT_BODY),
            wrap='word',
        )
        self.whisper_prompt_text.grid(
            row=5, column=0, sticky='ew', padx=Tokens.PAD_LG, pady=Tokens.PAD_SM
        )
        self.whisper_prompt_text.insert('0.0', self.config_mgr.get('whisper_prompt', ''))

        # ── 麥克風裝置 ──
        self._section_title(parent, '麥克風').grid(
            row=6, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_XL, Tokens.PAD_SM)
        )

        from core.recording import list_input_devices
        device_names = ['(系統預設)'] + [name for _, name in list_input_devices()]
        saved_device = self.config_mgr.get('input_device', '') or '(系統預設)'
        if saved_device not in device_names:
            device_names.append(saved_device)
        self.input_device_var = ctk.StringVar(value=saved_device)

        mic_row = ctk.CTkFrame(parent, fg_color='transparent')
        mic_row.grid(row=7, column=0, sticky='ew', padx=Tokens.PAD_LG)
        mic_row.grid_columnconfigure(0, weight=1)

        ctk.CTkOptionMenu(
            mic_row,
            values=device_names,
            variable=self.input_device_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
            dynamic_resizing=False,
            width=420,
        ).grid(row=0, column=0, sticky='w')

        ctk.CTkButton(
            mic_row, text='測試麥克風', width=110, height=32,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['accent'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY_SM),
            command=self._test_microphone,
        ).grid(row=0, column=1, sticky='e', padx=(Tokens.PAD_SM, 0))

        self.mic_test_result = self._label(parent, '', secondary=True)
        self.mic_test_result.grid(row=8, column=0, sticky='w',
                                  padx=Tokens.PAD_LG, pady=(Tokens.PAD_XS, Tokens.PAD_LG))

    def _test_microphone(self):
        """錄 1.5 秒回報音量 — 在背景 thread 跑避免卡 UI"""
        self.mic_test_result.configure(
            text='🎙 錄音中... 請對麥克風說話 (1.5 秒)',
            text_color=self.colors['text_secondary'],
        )

        def run():
            try:
                from core.recording import test_input_device
                name = self.input_device_var.get()
                device = '' if name == '(系統預設)' else name
                result = test_input_device(device)
                rms = result['rms']
                if result['ok']:
                    msg = f"✓ 收到聲音！音量 RMS={rms:.4f}  ·  裝置: {result['device_used'][:40]}"
                    color = self.colors['success']
                elif rms > 0.001:
                    msg = f"△ 有訊號但太小聲 (RMS={rms:.4f} < 0.005)。靠近一點或調高麥克風音量"
                    color = self.colors['warning']
                else:
                    msg = (f"✗ 完全靜音 (RMS={rms:.5f})。檢查 F4 靜音鍵 / "
                           f"Windows 麥克風權限 / 換一個裝置試試")
                    color = self.colors['danger']
            except Exception as e:
                msg = f'✗ 測試失敗: {e}'
                color = self.colors['danger']
            try:
                self.after(0, lambda: self.mic_test_result.configure(
                    text=msg, text_color=color))
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    # ---------- Tab: 快捷鍵 ----------
    def _make_record_button(self, parent, entry, row):
        """在 entry 右側（column 1）放一顆錄製鈕。"""
        btn = ctk.CTkButton(parent, text='🎯 錄製', width=76, height=Tokens.HEIGHT_INPUT)
        btn.configure(command=lambda e=entry, b=btn: self._record_hotkey_into(e, b))
        btn.grid(row=row, column=1, sticky='e', padx=(Tokens.PAD_XS, Tokens.PAD_LG))
        return btn

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

    def _build_hotkey_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0)

        self._section_title(parent, '全域快捷鍵').grid(
            row=0, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, Tokens.PAD_MD)
        )

        # 一般錄音
        self._label(parent, '開始 / 結束錄音').grid(
            row=1, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(Tokens.PAD_SM, Tokens.PAD_XS)
        )
        self._label(parent, '按一次開始錄音，再按結束並轉錄', secondary=True).grid(
            row=2, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS)
        )
        self.hotkey_entry = self._entry(parent, placeholder='ctrl+alt+z')
        self.hotkey_entry.insert(0, self.config_mgr.get('hotkey', 'ctrl+alt+z'))
        self.hotkey_entry.grid(row=3, column=0, sticky='ew', padx=(Tokens.PAD_LG, Tokens.PAD_XS))
        self._make_record_button(parent, self.hotkey_entry, 3)

        # Streaming 模式 (新)
        self._label(parent, 'Streaming 模式 (邊講邊出字)').grid(
            row=4, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, Tokens.PAD_XS)
        )
        self._label(
            parent,
            '長時間口述用 — 每停頓 0.7 秒自動切段送 Whisper，文字陸續貼出',
            secondary=True,
        ).grid(row=5, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS))
        self.streaming_hotkey_entry = self._entry(parent, placeholder='ctrl+shift+l')
        self.streaming_hotkey_entry.insert(
            0, self.config_mgr.get('streaming_hotkey', 'ctrl+shift+l')
        )
        self.streaming_hotkey_entry.grid(row=6, column=0, sticky='ew', padx=(Tokens.PAD_LG, Tokens.PAD_XS))
        self._make_record_button(parent, self.streaming_hotkey_entry, 6)

        # 取消
        self._label(parent, '取消錄音').grid(
            row=7, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, Tokens.PAD_XS)
        )
        self._label(
            parent, '丟棄當前錄音不送 API，省錢用',
            secondary=True,
        ).grid(row=8, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_XS))
        self.cancel_hotkey_entry = self._entry(parent, placeholder='ctrl+shift+x')
        self.cancel_hotkey_entry.insert(0, self.config_mgr.get('cancel_hotkey', 'ctrl+shift+x'))
        self.cancel_hotkey_entry.grid(row=9, column=0, sticky='ew', padx=(Tokens.PAD_LG, Tokens.PAD_XS))
        self._make_record_button(parent, self.cancel_hotkey_entry, 9)

        hint = self._label(
            parent,
            '格式: 用 + 分隔，例如 tab+`、ctrl+alt+space、alt+v\n'
            '可按「🎯 錄製」直接按鍵錄製。無修飾鍵的組合（如 tab+`）會自動吞鍵，'
            '不會把字打進游標。修改後需重啟程式才生效。',
            secondary=True,
        )
        hint.configure(justify='left')
        hint.grid(row=10, column=0, sticky='w', padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, 0))

    # ---------- Tab: 進階 ----------
    def _build_advanced_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self._section_title(parent, '行為').grid(
            row=0, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, Tokens.PAD_SM)
        )

        self.advanced_switches = {}
        switches = [
            ('auto_paste', '自動貼上', '辨識完直接 Ctrl+V 貼到游標位置'),
            ('play_sound', '提示音', '錄音開始/結束/取消時的嗶聲'),
            ('restore_clipboard', '還原剪貼簿', '貼上後自動還原原本的剪貼簿內容'),
            ('show_waveform', '錄音波形浮窗', '錄音時在螢幕底部顯示音量視覺化'),
            ('save_history', '儲存歷史紀錄', '保留最近 100 筆轉錄記錄供查閱'),
            ('use_speaker_diarization', '會議錄音 — 聲紋分離',
             '用 Google Gemini 辨識多人對話 ([Speaker 1] / [Speaker 2])，需 GOOGLE_API_KEY'),
        ]

        for i, (key, label, desc) in enumerate(switches):
            row = ctk.CTkFrame(parent, fg_color='transparent')
            row.grid(row=i + 1, column=0, sticky='ew',
                     padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)
            row.grid_columnconfigure(0, weight=1)

            text_box = ctk.CTkFrame(row, fg_color='transparent')
            text_box.grid(row=0, column=0, sticky='w')
            self._label(text_box, label).pack(anchor='w')
            self._label(text_box, desc, secondary=True).pack(anchor='w')

            sw = ctk.CTkSwitch(
                row, text='',
                fg_color=self.colors['bg_tertiary'],
                progress_color=self.colors['accent'],
            )
            if self.config_mgr.get(key, True):
                sw.select()
            sw.grid(row=0, column=1, sticky='e')
            self.advanced_switches[key] = sw

        self._section_title(parent, '外觀').grid(
            row=len(switches) + 1, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_XL, Tokens.PAD_SM)
        )
        self.theme_var = ctk.StringVar(value=self.config_mgr.get('theme', 'system'))
        ctk.CTkOptionMenu(
            parent,
            values=['system', 'light', 'dark'],
            variable=self.theme_var,
            fg_color=self.colors['bg_secondary'],
            button_color=self.colors['accent'],
            button_hover_color=self.colors['accent_hover'],
            corner_radius=Tokens.RADIUS_MD,
            font=font(Tokens.FONT_BODY),
        ).grid(row=len(switches) + 2, column=0, sticky='w', padx=Tokens.PAD_LG)

    # ---------- Tab: 自學詞典 ----------
    def _build_learned_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        self._section_title(parent, '自學詞典').grid(
            row=0, column=0, sticky='w',
            padx=Tokens.PAD_LG, pady=(Tokens.PAD_LG, Tokens.PAD_SM)
        )
        self._label(
            parent,
            '系統會偷偷觀察「Whisper 寫的」vs「Claude 改成的」差異，'
            '建議你把常被修正的詞加入當前情境詞典',
            secondary=True,
        ).grid(row=1, column=0, sticky='w', padx=Tokens.PAD_LG)

        # 列表
        list_frame = ctk.CTkFrame(
            parent,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'], border_width=1,
        )
        list_frame.grid(row=2, column=0, sticky='nsew',
                        padx=Tokens.PAD_LG, pady=Tokens.PAD_SM)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.learned_list = ctk.CTkScrollableFrame(list_frame, fg_color=self.colors['bg_primary'])
        self.learned_list.grid(row=0, column=0, sticky='nsew',
                                padx=Tokens.PAD_SM, pady=Tokens.PAD_SM)
        self.learned_list.grid_columnconfigure(0, weight=1)

        self._render_learned_list()

        # 工具列
        toolbar = ctk.CTkFrame(parent, fg_color='transparent')
        toolbar.grid(row=3, column=0, sticky='ew',
                     padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_SM))

        if self.learned_mgr:
            stats = self.learned_mgr.stats()
            ctk.CTkLabel(
                toolbar,
                text=f"累計觀察 {stats['suggestions_total']} 個詞，"
                     f"{stats['suggestions_ready']} 個達建議標準，"
                     f"已接受 {stats['accepted_total']}，已忽略 {stats['ignored_total']}",
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
            ).pack(side='left')

    def _render_learned_list(self):
        for child in self.learned_list.winfo_children():
            child.destroy()

        if not self.learned_mgr:
            ctk.CTkLabel(
                self.learned_list, text='(未啟用 learned_mgr)',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
            ).grid(row=0, column=0, pady=Tokens.PAD_LG)
            return

        suggestions = self.learned_mgr.top_suggestions(limit=50)
        if not suggestions:
            ctk.CTkLabel(
                self.learned_list,
                text='尚無建議\n多用幾次後，Claude 修正過的詞會出現在這裡',
                font=font(Tokens.FONT_BODY),
                text_color=self.colors['text_tertiary'],
                justify='center',
            ).grid(row=0, column=0, pady=Tokens.PAD_XL)
            return

        for i, s in enumerate(suggestions):
            row = ctk.CTkFrame(self.learned_list,
                                fg_color=self.colors['bg_primary'],
                                corner_radius=Tokens.RADIUS_SM,
                                border_color=self.colors['border'], border_width=1)
            row.grid(row=i, column=0, sticky='ew', pady=3, padx=2)
            row.grid_columnconfigure(1, weight=1)

            # 次數 badge
            badge = ctk.CTkLabel(
                row, text=f'×{s["count"]}',
                font=font(Tokens.FONT_BODY_SM, 'bold'),
                text_color=self.colors['accent'],
                fg_color=self.colors['accent_subtle'],
                corner_radius=Tokens.RADIUS_SM,
                padx=6, pady=2,
            )
            badge.grid(row=0, column=0, padx=Tokens.PAD_SM, pady=Tokens.PAD_SM, sticky='nw')

            # 詞 + Whisper 寫法
            text_box = ctk.CTkFrame(row, fg_color='transparent')
            text_box.grid(row=0, column=1, sticky='ew', pady=Tokens.PAD_SM)
            ctk.CTkLabel(
                text_box, text=s['word'],
                font=font(Tokens.FONT_BODY, 'bold'),
                text_color=self.colors['text_primary'],
                anchor='w',
            ).pack(anchor='w')
            ctk.CTkLabel(
                text_box, text=f'Whisper 寫成：{s["whisper_form"]}',
                font=font(Tokens.FONT_CAPTION),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).pack(anchor='w')

            # 動作按鈕
            btns = ctk.CTkFrame(row, fg_color='transparent')
            btns.grid(row=0, column=2, padx=Tokens.PAD_SM, pady=Tokens.PAD_SM, sticky='ne')

            ctk.CTkButton(
                btns, text='加入詞典', width=82, height=28,
                corner_radius=Tokens.RADIUS_SM,
                fg_color=self.colors['accent'],
                hover_color=self.colors['accent_hover'],
                font=font(Tokens.FONT_BODY_SM, 'bold'),
                command=lambda w=s['word']: self._accept_learned(w),
            ).pack(side='left')

            ctk.CTkButton(
                btns, text='忽略', width=56, height=28,
                corner_radius=Tokens.RADIUS_SM,
                fg_color='transparent',
                text_color=self.colors['text_tertiary'],
                hover_color=self.colors['bg_hover'],
                border_width=1, border_color=self.colors['border'],
                font=font(Tokens.FONT_BODY_SM),
                command=lambda w=s['word']: self._ignore_learned(w),
            ).pack(side='left', padx=(4, 0))

    def _accept_learned(self, word):
        """把詞加到當前 active profile 的 vocabulary"""
        if not self.learned_mgr or not self.profile_mgr:
            return
        profile = self.profile_mgr.active()
        pid = profile.get('id')
        vocab = list(profile.get('vocabulary') or [])
        if word not in vocab:
            vocab.append(word)
            self.profile_mgr.update(pid, vocabulary=vocab)
        self.learned_mgr.accept(word)
        self._render_learned_list()
        self._show_message(f'已加入「{word}」到「{profile.get("name")}」', 'success')

    def _ignore_learned(self, word):
        if not self.learned_mgr:
            return
        self.learned_mgr.ignore(word)
        self._render_learned_list()

    # ---------- Save ----------
    def _save_all(self):
        # 1. API Keys
        for env, entry in self.api_entries.items():
            key = entry.get().strip()
            if key:
                self.env_mgr.set(env, key)

        # 2. 引擎設定
        self.config_mgr.set('transcriber', {
            'provider': self.tr_provider_var.get(),
            'model': self.tr_model_var.get(),
        })
        self.config_mgr.set('enhancer', {
            'provider': self.en_provider_var.get(),
            'model': self.en_model_var.get(),
        })

        # 3. 情境 (先寫回當前編輯的)
        self._capture_profile_edit()

        # 4. 辨識
        self.config_mgr.set('language', self.language_var.get())
        self.config_mgr.set('whisper_prompt',
                            self.whisper_prompt_text.get('0.0', 'end').strip())

        # 5. 快捷鍵
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
        self.config_mgr.set('hotkey',
                            self.hotkey_entry.get().strip() or 'ctrl+alt+z')
        self.config_mgr.set('cancel_hotkey',
                            self.cancel_hotkey_entry.get().strip() or 'ctrl+alt+x')
        self.config_mgr.set('streaming_hotkey',
                            self.streaming_hotkey_entry.get().strip() or 'ctrl+shift+l')

        # 5.5 麥克風裝置
        device_choice = self.input_device_var.get()
        self.config_mgr.set('input_device',
                            '' if device_choice == '(系統預設)' else device_choice)

        # 6. 進階
        for key, sw in self.advanced_switches.items():
            self.config_mgr.set(key, bool(sw.get()))
        self.config_mgr.set('theme', self.theme_var.get())

        self.config_mgr.save()

        for env in self.api_entries:
            self._refresh_status(env)

        if self.on_save:
            try:
                self.on_save(self.config_mgr.all())
            except Exception as e:
                print(f"on_save failed: {e}")

        self._show_message('✓ 已儲存，所有設定立即生效', 'success')
        self.after(1500, self.destroy)
