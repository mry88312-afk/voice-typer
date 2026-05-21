"""錄音時的小型波形浮窗 — 平滑動畫、無閃爍、視覺有趣

設計：
- 頂部：脈動紅點 + 計時器 mm:ss + 「錄音中」
- 中央：32 個圓角音量條，按高度漸層顏色（綠 → 黃 → 紅）
- 底部 hint：操作提示
- 處理中：bars 變橘色波浪
"""
import math
import time
import numpy as np
import customtkinter as ctk

from ui.theme import get_colors, font, Tokens


class WaveformOverlay(ctk.CTkToplevel):
    BAR_COUNT = 32
    HEIGHT = 110
    WIDTH = 400

    def __init__(self, parent):
        super().__init__(parent)
        self.colors = get_colors()

        # 視窗外觀
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        try:
            self.attributes('-alpha', 0.96)
        except Exception:
            pass
        self.configure(fg_color=self.colors['bg_primary'])

        # 大小與位置 (螢幕底部居中) — 用 minsize/maxsize 雙重鎖死
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = sh - self.HEIGHT - 100
        self.geometry(f'{self.WIDTH}x{self.HEIGHT}+{x}+{y}')
        self.minsize(self.WIDTH, self.HEIGHT)
        self.maxsize(self.WIDTH, self.HEIGHT)
        self.resizable(False, False)

        # 拖曳支援 (因為 overrideredirect 拿掉了 titlebar)
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._dragging = False
        self.bind('<ButtonPress-1>', self._start_drag)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._end_drag)

        # 監聽尺寸變化 → 任何 source 改大都立刻彈回
        self._size_snap_active = True
        self.bind('<Configure>', self._on_configure_snap)
        self.bind('<Map>', lambda e: self.after(10, self._enforce_size))

        # 波形狀態
        self._target_levels = [0.05] * self.BAR_COUNT
        self._current_levels = [0.05] * self.BAR_COUNT
        self._bar_ids = []
        self._running = False
        self._mode = 'recording'
        self._processing_phase = 0.0
        self._pulse_phase = 0.0
        self._start_time = None

        self._build()
        self.withdraw()
        self.after(50, self._init_bars)
        # 防呆：建好 100ms 後再 assert 一次尺寸（CTk + overrideredirect 偶爾忽略 geometry）
        self.after(100, self._enforce_size)

    # ---------- UI 結構 ----------
    def _build(self):
        # 主框 (圓角)
        self.frame = ctk.CTkFrame(
            self,
            corner_radius=Tokens.RADIUS_XL,
            fg_color=self.colors['bg_primary'],
            border_color=self.colors['border'],
            border_width=1,
        )
        self.frame.pack(fill='both', expand=True, padx=3, pady=3)

        # 頂部資訊列
        top = ctk.CTkFrame(self.frame, fg_color='transparent', height=24)
        top.pack(fill='x', padx=Tokens.PAD_LG, pady=(Tokens.PAD_SM, 0))
        top.pack_propagate(False)

        # 脈動紅點 (用 canvas 畫，比 label emoji 平滑)
        self.dot_canvas = ctk.CTkCanvas(
            top, width=18, height=18,
            bg=self.colors['bg_primary'],
            highlightthickness=0,
        )
        self.dot_canvas.pack(side='left')
        self._dot_id = self.dot_canvas.create_oval(
            4, 4, 14, 14,
            fill=self.colors['danger'], outline='',
        )

        # 狀態文字
        self.label = ctk.CTkLabel(
            top, text='錄音中',
            font=font(Tokens.FONT_BODY_SM, 'bold'),
            text_color=self.colors['text_primary'],
        )
        self.label.pack(side='left', padx=(6, 0))

        # 計時器 (置中)
        self.timer_lbl = ctk.CTkLabel(
            top, text='0:00',
            font=font(Tokens.FONT_BODY, 'bold'),
            text_color=self.colors['text_primary'],
        )
        self.timer_lbl.pack(side='left', padx=(Tokens.PAD_MD, 0))

        # 提示 (右)
        self.hint = ctk.CTkLabel(
            top,
            text='再按一次結束  ·  拖曳移動',
            font=font(Tokens.FONT_CAPTION),
            text_color=self.colors['text_tertiary'],
        )
        self.hint.pack(side='right')

        # 音量波形 canvas
        self.canvas = ctk.CTkCanvas(
            self.frame, height=56,
            highlightthickness=0,
            bg=self.colors['bg_primary'],
        )
        self.canvas.pack(fill='both', expand=True,
                         padx=Tokens.PAD_LG, pady=(Tokens.PAD_SM, Tokens.PAD_MD))

        # 拖曳：把 handler bind 到所有子元件 (不然點 canvas/label 不會觸發)
        for widget in (self.frame, top, self.canvas, self.label,
                       self.timer_lbl, self.hint, self.dot_canvas):
            widget.bind('<ButtonPress-1>', self._start_drag)
            widget.bind('<B1-Motion>', self._on_drag)

    def _init_bars(self):
        """預先建好 32 個線段 (用 capstyle round 模擬膠囊形)"""
        try:
            self.update_idletasks()
            self.canvas.delete('all')
            self._bar_ids = []
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            cy = h / 2

            # 計算 bar 寬度 + gap
            gap = 3
            bar_w = max(3, (w - gap * (self.BAR_COUNT - 1)) / self.BAR_COUNT)

            for i in range(self.BAR_COUNT):
                x_center = (bar_w / 2) + i * (bar_w + gap)
                # 初始極短
                line_id = self.canvas.create_line(
                    x_center, cy - 2,
                    x_center, cy + 2,
                    fill=self.colors['accent'],
                    width=bar_w,
                    capstyle='round',  # 圓角！
                )
                self._bar_ids.append(line_id)
        except Exception as e:
            print(f'init_bars failed: {e}')

    # ---------- 公開 API ----------
    def update_volume(self, audio_chunk):
        if not self._running or self._mode != 'recording':
            return
        try:
            arr = np.asarray(audio_chunk).flatten()
            if len(arr) == 0:
                return
            rms = float(np.sqrt(np.mean(arr ** 2)))
            # 對數壓縮，讓小聲也看得到
            level = min(1.0, max(0.03, (rms ** 0.5) / 0.4))
            self._target_levels = self._target_levels[1:] + [level]
        except Exception:
            pass

    def show_recording(self, mode_label: str = '錄音中', hint_text: str = None):
        self._mode = 'recording'
        self.label.configure(text=mode_label)
        self.hint.configure(
            text=hint_text or '再按一次結束  ·  拖曳移動'
        )
        self._target_levels = [0.04] * self.BAR_COUNT
        self._current_levels = [0.04] * self.BAR_COUNT
        self._running = True
        self._start_time = time.time()
        try:
            self._enforce_size()
            self.update_idletasks()
            self.deiconify()
            self.lift()
            # deiconify 後 CTk 偶爾還會 resize，再強鎖一次
            self.after(20, self._enforce_size)
        except Exception:
            pass
        self._animate()
        self._pulse()
        self._tick_timer()

    def show_processing(self):
        self._mode = 'processing'
        self.label.configure(text='辨識中')
        self.hint.configure(text='Whisper 上傳 + Claude 潤色中...')
        self._processing_phase = 0.0
        self._running = True
        try:
            self.dot_canvas.itemconfig(self._dot_id, fill=self.colors['warning'])
        except Exception:
            pass
        try:
            self._enforce_size()
            self.update_idletasks()
            self.deiconify()
            self.lift()
            self.after(20, self._enforce_size)
        except Exception:
            pass
        self._animate()

    def hide(self):
        self._running = False
        try:
            self.withdraw()
        except Exception:
            pass

    # ---------- 尺寸鎖死 + 拖曳 ----------
    def _enforce_size(self):
        """強制把視窗壓回固定尺寸（CTk + overrideredirect 偶爾會放大）"""
        try:
            current = self.geometry()  # 'WxH+X+Y'
            # 保留現有 X+Y，只 reset W+H
            if '+' in current:
                pos = current.split('x', 1)[1]
                if '+' in pos:
                    _, rest = pos.split('+', 1)
                    self.geometry(f'{self.WIDTH}x{self.HEIGHT}+{rest}')
                    return
            # fallback：放回螢幕底部中央
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - self.WIDTH) // 2
            y = sh - self.HEIGHT - 100
            self.geometry(f'{self.WIDTH}x{self.HEIGHT}+{x}+{y}')
        except Exception:
            pass

    def _start_drag(self, event):
        try:
            self._drag_offset_x = event.x_root - self.winfo_x()
            self._drag_offset_y = event.y_root - self.winfo_y()
            self._dragging = True
        except Exception:
            pass

    def _on_drag(self, event):
        try:
            new_x = event.x_root - self._drag_offset_x
            new_y = event.y_root - self._drag_offset_y
            self.geometry(f'{self.WIDTH}x{self.HEIGHT}+{new_x}+{new_y}')
        except Exception:
            pass

    def _end_drag(self, event):
        self._dragging = False

    def _on_configure_snap(self, event):
        """視窗一被改大 → 立刻彈回。拖曳中不觸發 (避免回彈)"""
        if not self._size_snap_active or self._dragging:
            return
        # 只在 toplevel 自己的 configure 事件處理 (不要每個子 widget 都觸發)
        if event.widget is not self:
            return
        try:
            w = event.width
            h = event.height
            if w != self.WIDTH or h != self.HEIGHT:
                # 暫停 snap 避免遞迴觸發
                self._size_snap_active = False
                self._enforce_size()
                self.after(50, lambda: setattr(self, '_size_snap_active', True))
        except Exception:
            pass

    # ---------- 動畫 tick ----------
    def _animate(self):
        if not self._running:
            return
        try:
            if self._mode == 'recording':
                self._tick_recording()
            else:
                self._tick_processing()
        except Exception as e:
            pass
        self.after(35, self._animate)

    def _tick_recording(self):
        """平滑緩動到 target levels"""
        smoothing = 0.32
        for i, target in enumerate(self._target_levels):
            self._current_levels[i] += (target - self._current_levels[i]) * smoothing
        self._draw_bars(self._current_levels, gradient=True)

    def _tick_processing(self):
        """處理中：跑馬燈式正弦波，固定橘色"""
        self._processing_phase += 0.16
        levels = []
        for i in range(self.BAR_COUNT):
            v = 0.30 + 0.32 * abs(math.sin(self._processing_phase + i * 0.32))
            v += 0.08 * math.sin(self._processing_phase * 1.7 + i * 0.2)
            levels.append(max(0.06, min(1.0, v)))
        self._current_levels = levels
        self._draw_bars(levels, color=self.colors['warning'])

    def _pulse(self):
        """錄音中紅點呼吸式縮放 + 變亮"""
        if not self._running or self._mode != 'recording':
            return
        self._pulse_phase += 0.18
        try:
            # 呼吸感 0~1
            t = (math.sin(self._pulse_phase) + 1) / 2  # 0~1
            # 圓的大小: 半徑 4~6
            r = 3.5 + t * 2.5
            cx, cy = 9, 9
            self.dot_canvas.coords(
                self._dot_id,
                cx - r, cy - r, cx + r, cy + r,
            )
        except Exception:
            pass
        self.after(60, self._pulse)

    def _tick_timer(self):
        if not self._running or self._mode != 'recording':
            return
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            try:
                self.timer_lbl.configure(text=f'{mins}:{secs:02d}')
            except Exception:
                pass
        self.after(500, self._tick_timer)

    # ---------- 繪製 ----------
    def _draw_bars(self, levels, color=None, gradient=False):
        """更新 bar 高度。gradient=True 時依高度漸層 (綠→黃→紅)"""
        if not self._bar_ids or len(self._bar_ids) != self.BAR_COUNT:
            self._init_bars()
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 0 or h <= 0:
            return
        gap = 3
        bar_w = max(3, (w - gap * (self.BAR_COUNT - 1)) / self.BAR_COUNT)
        cy = h / 2

        for i, level in enumerate(levels):
            # 高度: 最小 6px (避免完全消失) ~ 最大 90%
            bh = max(6, level * h * 0.92)
            x_center = (bar_w / 2) + i * (bar_w + gap)
            y0 = cy - bh / 2
            y1 = cy + bh / 2

            # 顏色
            if color:
                fill = color
            elif gradient:
                fill = self._level_to_color(level)
            else:
                fill = self.colors['accent']

            try:
                self.canvas.coords(self._bar_ids[i], x_center, y0, x_center, y1)
                self.canvas.itemconfig(self._bar_ids[i], fill=fill, width=bar_w)
            except Exception:
                pass

    def _level_to_color(self, level: float) -> str:
        """音量 → 顏色漸層: 低 → 主色 (藍紫)，中 → 綠，高 → 紅"""
        # 階段：
        #   0.0 ~ 0.3: 暗的 accent
        #   0.3 ~ 0.6: accent → success (綠)
        #   0.6 ~ 0.85: success → warning (橘)
        #   0.85 ~ 1.0: warning → danger (紅)
        if level < 0.3:
            return self._fade_color(self.colors['accent'], self.colors['text_tertiary'], (0.3 - level) / 0.3)
        if level < 0.6:
            return self._lerp(self.colors['accent'], self.colors['success'], (level - 0.3) / 0.3)
        if level < 0.85:
            return self._lerp(self.colors['success'], self.colors['warning'], (level - 0.6) / 0.25)
        return self._lerp(self.colors['warning'], self.colors['danger'], (level - 0.85) / 0.15)

    @staticmethod
    def _hex_to_rgb(hex_str: str):
        h = hex_str.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return '#{:02X}{:02X}{:02X}'.format(*[int(max(0, min(255, c))) for c in rgb])

    def _lerp(self, c1: str, c2: str, t: float) -> str:
        t = max(0, min(1, t))
        r1 = self._hex_to_rgb(c1)
        r2 = self._hex_to_rgb(c2)
        return self._rgb_to_hex(tuple(r1[i] + (r2[i] - r1[i]) * t for i in range(3)))

    def _fade_color(self, c1: str, c2: str, t: float) -> str:
        return self._lerp(c1, c2, t)
