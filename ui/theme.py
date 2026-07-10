"""Design system - 中文字型 (Microsoft JhengHei UI) + Linear-inspired tokens

設計原則 (參考 UI/UX Pro Max skill):
- 4.5:1 對比度
- 8px 網格
- 不依賴裝飾性 emoji
- 字型階層清晰 (display / heading / body / caption)
"""
import customtkinter as ctk


# ---------- 字型偵測 ----------
_font_family_cache = None


def get_font_family():
    """偵測系統可用的最佳中文字型 (按優先順序)"""
    global _font_family_cache
    if _font_family_cache:
        return _font_family_cache

    try:
        import tkinter.font as tkfont
        families = set(tkfont.families())   # 需要已存在的 Tk root
    except Exception:
        families = set()                    # 沒有 root / 任何錯誤 → 直接用預設字型，絕不自建 Tk

    for candidate in [
        'Microsoft JhengHei UI',   # Win7+ 內建，中文 UI 字型
        'Microsoft JhengHei',       # Win Vista+ 內建
        'PingFang TC',              # macOS
        'Noto Sans TC',
        'Segoe UI',                 # 純英文 fallback
        'Arial',
    ]:
        if candidate in families:
            _font_family_cache = candidate
            return candidate

    _font_family_cache = 'Microsoft JhengHei'
    return _font_family_cache


# ---------- 顏色 Token ----------
class Colors:
    LIGHT = {
        'bg_primary':    '#FFFFFF',
        'bg_secondary':  '#FAFBFC',  # 卡片底色 (更白)
        'bg_tertiary':   '#F3F4F6',  # 區塊分隔
        'bg_hover':      '#F0F1F3',
        'bg_pressed':    '#E5E7EB',
        'text_primary':  '#0E0E10',  # 主要文字 (更深，對比更高)
        'text_secondary':'#5C6068',
        'text_tertiary': '#8B8F96',
        'text_disabled': '#BFC3CA',
        'accent':        '#5E6AD2',  # Linear 藍紫
        'accent_hover':  '#4F58B8',
        'accent_pressed':'#404696',
        'accent_subtle': '#EEEFFB',  # accent 淺背景
        'success':       '#1B9A75',
        'success_subtle':'#E3F5EE',
        'warning':       '#D17A00',
        'warning_subtle':'#FCF1DE',
        'danger':        '#D9342B',
        'danger_subtle': '#FCEAE9',
        'border':        '#E5E7EB',
        'border_strong': '#D1D5DB',
        'shadow':        '#0000000A',
    }

    DARK = {
        'bg_primary':    '#0C0D0F',
        'bg_secondary':  '#16181C',
        'bg_tertiary':   '#1F2128',
        'bg_hover':      '#1C1E23',
        'bg_pressed':    '#26282E',
        'text_primary':  '#F4F5F7',
        'text_secondary':'#A8ACB5',
        'text_tertiary': '#75797F',
        'text_disabled': '#4A4D54',
        'accent':        '#7A85FF',
        'accent_hover':  '#6B75E8',
        'accent_pressed':'#5E68CC',
        'accent_subtle': '#1F2240',
        'success':       '#3DD68C',
        'success_subtle':'#0F2A1F',
        'warning':       '#F2994A',
        'warning_subtle':'#2A1F0F',
        'danger':        '#F87171',
        'danger_subtle': '#2A1313',
        'border':        '#22252A',
        'border_strong': '#2F3338',
        'shadow':        '#00000033',
    }


class Tokens:
    """設計 token: 字型階層、間距、圓角"""

    # 8px 網格
    PAD_2XS = 2
    PAD_XS  = 4
    PAD_SM  = 8
    PAD_MD  = 12
    PAD_LG  = 16
    PAD_XL  = 24
    PAD_2XL = 32
    PAD_3XL = 48

    # 圓角
    RADIUS_SM = 6
    RADIUS_MD = 8
    RADIUS_LG = 12
    RADIUS_XL = 16

    # 字型階層 (像素值，比之前大)
    FONT_CAPTION  = 12   # 輔助說明、時間戳
    FONT_BODY_SM  = 13
    FONT_BODY     = 14   # 預設內文
    FONT_LABEL    = 14   # 標籤
    FONT_BODY_LG  = 16
    FONT_HEADING  = 18   # section title
    FONT_TITLE    = 22   # 視窗標題
    FONT_DISPLAY  = 28   # 大標 (歡迎、完成)

    # 元件高度
    HEIGHT_INPUT  = 40
    HEIGHT_BUTTON = 40
    HEIGHT_BUTTON_SM = 32

    # 向後相容 alias (舊命名)
    FONT_XS  = FONT_CAPTION
    FONT_SM  = FONT_BODY_SM
    FONT_MD  = FONT_BODY
    FONT_LG  = FONT_BODY_LG
    FONT_XL  = FONT_TITLE
    FONT_XXL = FONT_DISPLAY
    FONT_FAMILY = 'Microsoft JhengHei UI'
    FONT_FAMILY_FALLBACK = 'Microsoft JhengHei'


# ---------- 主題管理 ----------
_current_theme = None


def _detect_dark_mode():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
        )
        value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False


def get_colors():
    global _current_theme
    if _current_theme is None:
        _current_theme = 'dark' if _detect_dark_mode() else 'light'
    return Colors.DARK if _current_theme == 'dark' else Colors.LIGHT


def set_theme(mode: str):
    global _current_theme
    if mode == 'system':
        _current_theme = 'dark' if _detect_dark_mode() else 'light'
    else:
        _current_theme = mode
    ctk.set_appearance_mode(_current_theme)


def init_app_theme():
    """只設外觀模式/色系（不碰字型、不需要 root）。字型偵測改由 root 建立後呼叫
    init_ctk_default_font()，避免在登入瞬間無 root 時自建臨時 Tk 造成卡死。"""
    ctk.set_appearance_mode('system')
    ctk.set_default_color_theme('blue')


def font(size=None, weight='normal'):
    """產生字型物件 — 自動使用最佳中文字型"""
    if size is None:
        size = Tokens.FONT_BODY
    return (get_font_family(), size, weight)


def fix_internal_widget_fonts(widget, default_font=None):
    """只修「customtkinter 內部 widget」的字型 (例如 CTkTabview 的 tab 按鈕)

    這些內部 widget 預設用 Calibri/Roboto，中文 fallback 細明體 → 醜
    不會碰被明確設過 font 的外層 widget
    """
    if default_font is None:
        default_font = font(Tokens.FONT_BODY, 'bold')
    try:
        # CTkTabview 的 segmented button (tab 按鈕)
        for attr in ['_segmented_button']:
            inner = getattr(widget, attr, None)
            if inner is not None:
                try:
                    inner.configure(font=default_font)
                except Exception:
                    pass
                # 也設 segmented button 內部的 buttons
                for btn in inner.winfo_children():
                    try:
                        btn.configure(font=default_font)
                    except Exception:
                        pass
        # 遞迴 (處理嵌套 tabview / 其他)
        for child in widget.winfo_children():
            fix_internal_widget_fonts(child, default_font)
    except Exception:
        pass


# 向後相容 alias
apply_font_to_descendants = fix_internal_widget_fonts


def init_ctk_default_font():
    """設定 customtkinter 的全域預設字型"""
    try:
        # customtkinter 預設 font 是 'Calibri'/'Roboto'，這裡換掉
        import customtkinter
        family = get_font_family()
        # 透過 patch ThemeManager 的 theme dict
        try:
            customtkinter.ThemeManager.theme['CTkFont']['family'] = family
            customtkinter.ThemeManager.theme['CTkFont']['size'] = Tokens.FONT_BODY
        except Exception:
            pass
    except Exception:
        pass
