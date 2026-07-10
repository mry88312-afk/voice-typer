"""用量統計視窗 — 支援 4 個 provider 細分"""
import datetime
from pathlib import Path
import customtkinter as ctk

from ui.theme import get_colors, font, Tokens, apply_font_to_descendants
from data.usage import PROVIDER_DISPLAY, PROVIDER_COLORS


# 模型名稱簡稱
def short_model(model: str) -> str:
    if not model:
        return ''
    if 'whisper-large-v3-turbo' in model: return 'v3-turbo'
    if 'whisper-large-v3' in model: return 'v3'
    if 'whisper' in model: return 'Whisper'
    if 'gpt-4o-mini' in model: return '4o-mini'
    if 'gpt-4o' in model: return '4o'
    if 'gpt-4.1' in model: return '4.1'
    if 'claude-haiku-4-5' in model: return 'Haiku 4.5'
    if 'claude-sonnet-4-6' in model: return 'Sonnet 4.6'
    if 'claude-opus-4-7' in model: return 'Opus 4.7'
    if 'gemini-2.5-flash' in model: return '2.5 Flash'
    if 'gemini-2.5-pro' in model: return '2.5 Pro'
    if 'llama-3.3-70b' in model: return 'Llama 70B'
    if 'llama-3.1-8b' in model: return 'Llama 8B'
    return model


class UsageWindow(ctk.CTkToplevel):
    def __init__(self, parent, usage_mgr, base_dir: Path):
        super().__init__(parent)
        self.usage_mgr = usage_mgr
        self.base_dir = base_dir
        self.colors = get_colors()

        self.title('Voice Typer - 用量統計')
        self.geometry('820x760')
        self.minsize(720, 600)
        self.resizable(True, True)
        self.withdraw()
        self._center()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

        self.update_idletasks()
        apply_font_to_descendants(self)
        self.deiconify()
        self.after(50, self.lift)
        self.after(50, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 820, 760
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0,
                              fg_color=self.colors['bg_primary'], height=84)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text='用量統計',
            font=font(Tokens.FONT_TITLE, 'bold'),
            text_color=self.colors['text_primary'],
        ).grid(row=0, column=0, sticky='w',
                padx=Tokens.PAD_XL, pady=(Tokens.PAD_LG, 0))

        ctk.CTkLabel(
            header, text='本地估算 · 含 OpenAI / Anthropic / Google / Groq',
            font=font(Tokens.FONT_BODY_SM),
            text_color=self.colors['text_secondary'],
        ).grid(row=1, column=0, sticky='w',
                padx=Tokens.PAD_XL, pady=(2, Tokens.PAD_LG))

        sep = ctk.CTkFrame(self, height=1, fg_color=self.colors['border'])
        sep.grid(row=0, column=0, sticky='ews', pady=(83, 0))

    def _build_body(self):
        body = ctk.CTkScrollableFrame(self, fg_color=self.colors['bg_primary'])
        body.grid(row=1, column=0, sticky='nsew',
                  padx=Tokens.PAD_XL, pady=Tokens.PAD_LG)
        body.grid_columnconfigure((0, 1, 2), weight=1)

        summary = self.usage_mgr.summary()

        # 三張總覽卡
        self._build_top_card(body, '今日', summary['today']['total'], 0, accent=True)
        self._build_top_card(body, '本月', summary['month']['total'], 1)
        self._build_top_card(body, '累計', summary['total']['total'], 2)

        ctk.CTkFrame(body, height=1, fg_color=self.colors['border']).grid(
            row=1, column=0, columnspan=3, sticky='ew', pady=Tokens.PAD_XL
        )

        # 轉錄區
        ctk.CTkLabel(
            body, text='語音辨識',
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, Tokens.PAD_SM))

        row = 3
        row = self._render_kind_section(body, 'transcribe', summary, row)

        # 潤色區
        ctk.CTkLabel(
            body, text='AI 潤色',
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=row, column=0, columnspan=3, sticky='w', pady=(Tokens.PAD_XL, Tokens.PAD_SM))
        row += 1
        row = self._render_kind_section(body, 'enhance', summary, row)

        # 趨勢長條
        ctk.CTkLabel(
            body, text='最近 7 日',
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
            anchor='w',
        ).grid(row=row, column=0, columnspan=3, sticky='w', pady=(Tokens.PAD_XL, Tokens.PAD_MD))
        row += 1
        self._build_trend_chart(body, row=row)

    def _build_top_card(self, parent, label, cost, col, accent=False):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.colors['accent_subtle'] if accent else self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['accent'] if accent else self.colors['border'],
            border_width=1,
        )
        card.grid(row=0, column=col, sticky='nsew',
                  padx=(0 if col == 0 else Tokens.PAD_SM, 0))

        ctk.CTkLabel(
            card, text=label,
            font=font(Tokens.FONT_BODY_SM, 'bold'),
            text_color=self.colors['text_secondary'],
        ).pack(anchor='w', padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, 0))

        ctk.CTkLabel(
            card, text=f'${cost:.4f}',
            font=font(Tokens.FONT_DISPLAY, 'bold'),
            text_color=self.colors['accent'] if accent else self.colors['text_primary'],
        ).pack(anchor='w', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))

    def _render_kind_section(self, parent, kind, summary, start_row):
        """渲染 transcribe 或 enhance 區塊 — 列出每個 provider 與其 model 細項"""
        # 找出 該 kind 在 today/month/total 中出現的 provider
        all_providers = set()
        for period in ['today', 'month', 'total']:
            for p in summary[period][kind].keys():
                all_providers.add(p)
        if not all_providers:
            ctk.CTkLabel(
                parent, text='— 尚無紀錄',
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).grid(row=start_row, column=0, columnspan=3, sticky='w', pady=Tokens.PAD_SM)
            return start_row + 1

        row = start_row
        for provider in sorted(all_providers):
            card = self._render_provider_card(parent, kind, provider, summary)
            card.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(0, Tokens.PAD_SM))
            row += 1
        return row

    def _render_provider_card(self, parent, kind, provider, summary):
        color = PROVIDER_COLORS.get(provider, self.colors['text_primary'])
        display_name = PROVIDER_DISPLAY.get(provider, provider)

        card = ctk.CTkFrame(
            parent,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'],
            border_width=1,
        )
        card.grid_columnconfigure((0, 1, 2), weight=1)

        # 標題
        title_row = ctk.CTkFrame(card, fg_color='transparent')
        title_row.grid(row=0, column=0, columnspan=3, sticky='w',
                       padx=Tokens.PAD_LG, pady=(Tokens.PAD_MD, Tokens.PAD_SM))

        # 色點
        ctk.CTkLabel(
            title_row, text='●',
            font=font(Tokens.FONT_BODY_LG),
            text_color=color,
        ).pack(side='left')

        ctk.CTkLabel(
            title_row, text=display_name,
            font=font(Tokens.FONT_HEADING, 'bold'),
            text_color=self.colors['text_primary'],
        ).pack(side='left', padx=(4, 0))

        # 列出該 provider 用過的 model 數
        all_models = set()
        for period in ['today', 'month', 'total']:
            data = summary[period][kind].get(provider)
            if data:
                all_models.update(data.get('models', {}).keys())
        if all_models:
            ctk.CTkLabel(
                title_row, text=f'  · {len(all_models)} 個模型',
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
            ).pack(side='left')

        # 3 欄資料 (今日/本月/累計)
        for col, period_key in enumerate(['today', 'month', 'total']):
            period_label = {'today': '今日', 'month': '本月', 'total': '累計'}[period_key]
            data = summary[period_key][kind].get(provider, {'cost': 0, 'count': 0,
                                                              'audio_seconds': 0,
                                                              'input_tokens': 0,
                                                              'output_tokens': 0})
            cell = ctk.CTkFrame(card, fg_color='transparent')
            cell.grid(row=1, column=col, sticky='ew',
                      padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))

            ctk.CTkLabel(
                cell, text=period_label,
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).pack(anchor='w')

            ctk.CTkLabel(
                cell, text=f"${data['cost']:.4f}",
                font=font(Tokens.FONT_TITLE, 'bold'),
                text_color=color,
                anchor='w',
            ).pack(anchor='w')

            # meta
            if kind == 'transcribe':
                mins = data.get('audio_seconds', 0) / 60.0
                meta = f"{mins:.1f} 分鐘 · {data['count']} 次"
            else:
                total_tok = data.get('input_tokens', 0) + data.get('output_tokens', 0)
                meta = f"{total_tok:,} tokens · {data['count']} 次"
            ctk.CTkLabel(
                cell, text=meta,
                font=font(Tokens.FONT_CAPTION),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).pack(anchor='w', pady=(2, 0))

        # 累計區用了哪些 model
        total_models = summary['total'][kind].get(provider, {}).get('models', {})
        if total_models:
            models_text = '  ·  '.join(
                f"{short_model(m)} ({d['count']})"
                for m, d in total_models.items() if d['count'] > 0
            )
            ctk.CTkLabel(
                card, text=models_text,
                font=font(Tokens.FONT_CAPTION),
                text_color=self.colors['text_tertiary'],
                anchor='w',
            ).grid(row=2, column=0, columnspan=3, sticky='w',
                   padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_MD))

        return card

    def _build_trend_chart(self, parent, row):
        wrap = ctk.CTkFrame(
            parent,
            fg_color=self.colors['bg_secondary'],
            corner_radius=Tokens.RADIUS_MD,
            border_color=self.colors['border'],
            border_width=1,
        )
        wrap.grid(row=row, column=0, columnspan=3, sticky='ew')
        wrap.grid_columnconfigure(0, weight=1)

        data = self.usage_mgr.daily_trend(7)
        max_cost = max((d['total'] for d in data), default=0.0)
        if max_cost <= 0:
            max_cost = 0.01

        canvas = ctk.CTkCanvas(
            wrap, height=160,
            bg=self.colors['bg_secondary'],
            highlightthickness=0,
        )
        canvas.pack(fill='both', expand=True, padx=Tokens.PAD_LG, pady=Tokens.PAD_MD)

        # 圖例
        legend = ctk.CTkFrame(wrap, fg_color='transparent')
        legend.pack(fill='x', padx=Tokens.PAD_LG, pady=(0, Tokens.PAD_SM))

        for label, color in [('辨識', self.colors['accent']), ('潤色', '#B179DE')]:
            chip = ctk.CTkFrame(legend, fg_color='transparent')
            chip.pack(side='left', padx=(0, Tokens.PAD_MD))
            ctk.CTkLabel(
                chip, text='■',
                font=font(Tokens.FONT_BODY_SM),
                text_color=color,
            ).pack(side='left')
            ctk.CTkLabel(
                chip, text=label,
                font=font(Tokens.FONT_BODY_SM),
                text_color=self.colors['text_secondary'],
            ).pack(side='left', padx=(2, 0))

        self.after(100, lambda: self._draw_trend(canvas, data, max_cost))

    def _draw_trend(self, canvas, data, max_cost):
        try:
            canvas.update_idletasks()
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 10:
                return
            n = len(data)
            gap = 16
            bar_w = (w - gap * (n + 1)) / n
            base_y = h - 28
            max_h = base_y - 10

            for i, d in enumerate(data):
                x0 = gap + i * (bar_w + gap)
                tr = d['transcribe']
                en = d['enhance']

                if tr > 0:
                    bh = (tr / max_cost) * max_h
                    canvas.create_rectangle(
                        x0, base_y - bh, x0 + bar_w, base_y,
                        fill=self.colors['accent'], outline='',
                    )
                if en > 0:
                    eh = (en / max_cost) * max_h
                    tr_h = (tr / max_cost) * max_h
                    canvas.create_rectangle(
                        x0, base_y - tr_h - eh,
                        x0 + bar_w, base_y - tr_h,
                        fill='#B179DE', outline='',
                    )

                canvas.create_text(
                    x0 + bar_w / 2, base_y + 14,
                    text=d['date'],
                    fill=self.colors['text_tertiary'],
                    font=(font()[0], Tokens.FONT_CAPTION),
                )

                total = tr + en
                if total > 0:
                    y_top = base_y - (total / max_cost) * max_h - 8
                    canvas.create_text(
                        x0 + bar_w / 2, y_top,
                        text=f'${total:.3f}',
                        fill=self.colors['text_secondary'],
                        font=(font()[0], Tokens.FONT_CAPTION),
                    )
        except Exception as e:
            print(f"draw trend failed: {e}")

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color='transparent', height=64)
        footer.grid(row=2, column=0, sticky='ew',
                    padx=Tokens.PAD_XL, pady=Tokens.PAD_MD)
        footer.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(footer, fg_color='transparent')
        left.grid(row=0, column=0, sticky='w')

        ctk.CTkButton(
            left, text='匯出 CSV', width=110, height=36,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['text_primary'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY),
            command=self._export_csv,
        ).pack(side='left')

        ctk.CTkButton(
            left, text='清空紀錄', width=110, height=36,
            corner_radius=Tokens.RADIUS_MD,
            fg_color='transparent',
            text_color=self.colors['danger'],
            hover_color=self.colors['bg_hover'],
            border_width=1, border_color=self.colors['border'],
            font=font(Tokens.FONT_BODY),
            command=self._clear_data,
        ).pack(side='left', padx=(Tokens.PAD_SM, 0))

        ctk.CTkButton(
            footer, text='關閉', width=110, height=36,
            corner_radius=Tokens.RADIUS_MD,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            font=font(Tokens.FONT_BODY, 'bold'),
            command=self.destroy,
        ).grid(row=0, column=1, sticky='e')

    def _export_csv(self):
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                title='匯出用量 CSV',
                defaultextension='.csv',
                initialfile=f'voice-typer-usage-{datetime.date.today()}.csv',
                filetypes=[('CSV', '*.csv')],
            )
            if path:
                self.usage_mgr.export_csv(Path(path))
        except Exception as e:
            print(f"export failed: {e}")

    def _clear_data(self):
        import ctypes
        result = ctypes.windll.user32.MessageBoxW(
            0,
            '確定要清空所有用量紀錄嗎？\n此動作無法復原。',
            'Voice Typer',
            0x4 | 0x30 | 0x40000,
        )
        if result == 6:
            self.usage_mgr.clear()
            for child in self.winfo_children():
                child.destroy()
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            self._build_header()
            self._build_body()
            self._build_footer()
