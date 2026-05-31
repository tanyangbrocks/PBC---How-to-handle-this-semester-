# ============================================================
#  ui_draw_base.py -- Low-level drawing primitives (rarely changed)
#  by refactor_ui.py
# ============================================================
from __future__ import annotations
import pygame
import math
import random
import os

from ui_const import *
from ui_state  import *

# ── WASM 記憶體安全：共用 Surface 快取（所有 draw 模組共用）─────────────────
# 全螢幕遮罩：用 set_alpha 代替 SRCALPHA，避免每幀分配 3.7 MB
_ov_cache: dict = {}
def _blit_ov(surf: pygame.Surface, r: int, g: int, b: int, a: int) -> None:
    """全螢幕遮罩（快取重用），比 SRCALPHA 省記憶體，任何 draw 模組皆可呼叫。"""
    key = (r, g, b, a)
    if key not in _ov_cache:
        s = pygame.Surface((WIN_W, WIN_H))
        s.fill((r, g, b))
        s.set_alpha(a)
        _ov_cache[key] = s
    surf.blit(_ov_cache[key], (0, 0))

# 可重用的 WIN_W×WIN_H SRCALPHA Surface 池（天氣/FX 等動畫使用）
# 模式：_get_sfx_surf(name) → 清空後重用，每個名稱只建立一次
_sfx_pool: dict = {}
def _get_sfx_surf(name: str) -> pygame.Surface:
    """取得具名的可重用 SRCALPHA Surface（首次建立，後續 fill 清空重用）。"""
    if name not in _sfx_pool:
        _sfx_pool[name] = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    s = _sfx_pool[name]
    s.fill((0, 0, 0, 0))
    return s

# 彈窗圓角投影陰影快取
_popup_sh_cache: dict = {}
def _get_popup_sh(w: int, h: int, alpha: int) -> pygame.Surface:
    """圓角 drop-shadow Surface，按 (w,h,alpha) 快取，同尺寸只建立一次。"""
    key = (w, h, alpha)
    if key not in _popup_sh_cache:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, alpha), pygame.Rect(0, 0, w, h), border_radius=18)
        _popup_sh_cache[key] = s
    return _popup_sh_cache[key]

def _play_sfx(name: str) -> None:
    """播放指定音效；key 不在 _sfx 時嘗試以 name 當檔名自動載入（.ogg / .wav）。"""
    if name not in _sfx:
        # ── 按需自動載入：把 name 當作 asset/audio/se/ 內的檔名（無副檔名）────
        _se_base = resource_path("asset", "audio", "se")
        _loaded = None
        for _ext in (".ogg", ".wav"):
            _fp = os.path.join(_se_base, name + _ext)
            if os.path.isfile(_fp):
                try:
                    _loaded = pygame.mixer.Sound(_fp)
                except Exception:
                    pass
                break
        _sfx[name] = _loaded   # None 也寫入，避免下次再嘗試
    snd = _sfx.get(name)
    if snd:
        try:
            snd.play()
        except Exception:
            pass

def _request_bgm(name: "str | None") -> None:
    """
    非阻塞 BGM 切換。
    - 若目標與當前（或進行中切換目標）相同：不動作。
    - 若目前無曲目在播：立即排程（下一幀載入），無淡出等待。
    - 否則：fadeout 舊曲，等 BGM_FADE_MS ms 後主迴圈自動載入新曲。

    實作說明：改用 pygame.mixer.Sound + 專用 Channel（_bgm_ch_obj）。
    pygame.mixer.music（串流）在 emscripten WASM SDL2_mixer 無聲音輸出，
    pygame.mixer.Sound（取樣）與 SFX 同一套 Web Audio 路徑，可正常發聲。
    """
    target = _bgm_pending[0] if _bgm_pending[0] is not None else _bgm_current[0]
    if name == target:
        return
    _bgm_pending[0] = name
    if _bgm_current[0] is None:
        # 目前沒有在播的曲目，不需要等待淡出
        _bgm_switch_at[0] = pygame.time.get_ticks()
    else:
        _bgm_switch_at[0] = pygame.time.get_ticks() + BGM_FADE_MS
        try:
            ch = _bgm_ch_obj[0]
            if ch is not None:
                ch.fadeout(BGM_FADE_MS)
            elif _bgm_snd_obj[0] is not None:
                # Channel 尚未初始化（run_ui 前被呼叫）→ 直接 stop Sound
                _bgm_snd_obj[0].stop()
        except Exception:
            pass

def _get_evt_shake_offset() -> tuple:
    """回傳突發事件全螢幕震動的 (dx, dy) 位移量（px）。震動結束後自動清除。"""
    t0 = _evt_shake_t0[0]
    if t0 == 0:
        return 0, 0
    elapsed = pygame.time.get_ticks() - t0
    if elapsed >= _EVT_SHAKE_MS:
        _evt_shake_t0[0] = 0
        return 0, 0
    decay = (1.0 - elapsed / _EVT_SHAKE_MS) ** 1.5
    amp   = int(_EVT_SHAKE_AMP * decay)
    if amp < 1:
        _evt_shake_t0[0] = 0
        return 0, 0
    rng = random.Random(elapsed // 14)   # ~70fps 下每幀不同
    return rng.randint(-amp, amp), rng.randint(-amp, amp)

def _get_stamp_shake_offset() -> tuple:
    """回傳印章晃動的 (dx, dy) 位移量（px）。輕柔短暫，結束後自動清除。"""
    t0 = _stamp_shake_t0[0]
    if t0 == 0:
        return 0, 0
    elapsed = pygame.time.get_ticks() - t0
    if elapsed >= _STAMP_SHAKE_MS:
        _stamp_shake_t0[0] = 0
        return 0, 0
    decay = (1.0 - elapsed / _STAMP_SHAKE_MS) ** 1.5
    amp   = int(_STAMP_SHAKE_AMP * decay)
    if amp < 1:
        _stamp_shake_t0[0] = 0
        return 0, 0
    rng = random.Random(elapsed // 14)
    return rng.randint(-amp, amp), rng.randint(-amp, amp)

def _get_font(size: int):
    """載入內建 Noto Sans TC Regular；失敗時退回 pygame 內建字型（WebAssembly 安全）。"""
    _path = resource_path("asset", "fonts", "Noto_Sans_TC", "static", "NotoSansTC-Regular.ttf")
    try:
        return pygame.font.Font(_path, size)
    except Exception:
        return pygame.font.Font(None, size)

def _get_font_bold(size: int):
    """載入內建 Noto Sans TC Bold；失敗時退回 pygame 內建字型（WebAssembly 安全）。"""
    _path = resource_path("asset", "fonts", "Noto_Sans_TC", "static", "NotoSansTC-Bold.ttf")
    try:
        return pygame.font.Font(_path, size)
    except Exception:
        return pygame.font.Font(None, size)

def _clean(text: str) -> str:
    """
    移除 CJK 字型不支援的 Emoji 與雜項符號，避免渲染成 □。
    保留：ASCII / Latin / 標準標點 / CJK 全字集 / 全形字符。
    剝除：Miscellaneous Technical (2300-23FF), Miscellaneous Symbols (2600-26FF),
          Dingbats (2700-27BF), 及整個補充多語言平面 (>FFFF) 的 Emoji。
    """
    out = []
    for ch in text:
        cp = ord(ch)
        if   cp <= 0x02FF:              # ASCII + Latin
            out.append(ch)
        elif 0x2000 <= cp <= 0x206F:    # 一般標點（…—''""）
            out.append(ch)
        elif 0x2E00 <= cp <= 0x2E7F:    # 補充標點
            out.append(ch)
        elif 0x3000 <= cp <= 0x9FFF:    # CJK 標點 + 統一表意文字
            out.append(ch)
        elif 0xA000 <= cp <= 0xFAFF:    # CJK 延伸 A/B
            out.append(ch)
        elif 0xFF00 <= cp <= 0xFFEF:    # 全形 / 半形
            out.append(ch)
        # 其餘（2300-23FF 雜項技術、2600-27FF 符號/Dingbats、>FFFF Emoji）全部略過
    # 移除因去掉前置 Emoji 而殘留的空白
    return "".join(out).lstrip()

# ── Emoji 備用字型（優先內建 Noto Emoji，Windows 上另備 Segoe UI Emoji）──
_EMOJI_FONT_PATH = resource_path("asset", "fonts", "Noto_Emoji", "static", "NotoEmoji-Regular.ttf")
_EMOJI_FONT_PATH_FALLBACK = r"C:\Windows\Fonts\seguiemj.ttf"
_emoji_font_cache: dict = {}

def _get_emoji_font(size: int):
    """載入並快取 Noto Emoji（無法載入時嘗試 Segoe UI Emoji），失敗回傳 None。"""
    if size not in _emoji_font_cache:
        loaded = None
        for _p in (_EMOJI_FONT_PATH, _EMOJI_FONT_PATH_FALLBACK):
            try:
                loaded = pygame.font.Font(_p, size)
                break
            except Exception:
                pass
        _emoji_font_cache[size] = loaded
    return _emoji_font_cache[size]

def _is_emoji_char(ch: str) -> bool:
    """判斷字元是否為主字型（CJK）無法渲染、需用 Emoji 字型補渲的符號。"""
    cp = ord(ch)
    if cp <= 0x02FF:            return False   # ASCII + Latin
    if 0x2000 <= cp <= 0x206F:  return False   # 一般標點
    if 0x2190 <= cp <= 0x21FF:  return False   # 箭頭（NotoSansTC 有）
    if 0x2200 <= cp <= 0x22FF:  return False   # 數學運算符（NotoSansTC 有）
    if 0x2400 <= cp <= 0x24FF:  return False   # 控制圖片 + 帶圓圈數字 ①②③（NotoSansTC 有）
    if 0x2500 <= cp <= 0x259F:  return False   # 方塊繪圖 ─═╯╰ + 區塊元素（NotoSansTC 有）
    if 0x25A0 <= cp <= 0x25FF:  return False   # 幾何形狀 □▸ 等（NotoSansTC 有）
    if 0x2E00 <= cp <= 0x2E7F:  return False   # 補充標點
    if 0x3000 <= cp <= 0x9FFF:  return False   # CJK 標點 + 統一表意文字
    if 0xA000 <= cp <= 0xFAFF:  return False   # CJK 延伸
    if 0xFF00 <= cp <= 0xFFEF:  return False   # 全形 / 半形
    return True                                # 其餘視為 Emoji / 符號

# ── Emoji 個別著色表（NotoEmoji 單色字型的近似原色）────────────
_EMOJI_COLORS: dict = {
    # ── 原有條目 ──────────────────────────────────────────────
    "💰": (220, 180,  30),  "🏪": (255, 165,  50),  "👋": (220, 170, 110),
    "📖": (100, 160, 220),  "📚": (100, 160, 220),  "🎓": (220, 180,  30),
    "✍":  (130, 100,  60),  "📋": (100, 160, 220),  "📅": (100, 160, 220),
    "🍀": ( 70, 200,  90),  "✨": (255, 215,  60),  "🌟": (255, 215,  60),
    "🎉": (255, 180,  50),  "✅": ( 70, 200,  90),  "😊": (255, 215,  60),
    "💪": (255, 130,  50),  "⚡": (255, 220,  30),  "🔥": (255, 100,  30),
    "🏃": ( 80, 180, 230),  "🎮": (130, 100, 210),
    "❌": (215,  68,  62),  "💀": (140, 130, 130),  "💔": (215,  68,  62),
    "📉": (215,  68,  62),  "😞": (160, 148, 132),  "😔": (160, 148, 132),
    "🤒": (130, 210, 235),  "⚠":  (255, 180,  30),  "💥": (255, 100,  30),
    "😤": (255, 130,  50),  "😴": ( 80, 180, 230),  "❓": (160, 148, 132),
    # ── 補充：遊戲中使用但缺少著色的 emoji ────────────────────
    "⏳": (255, 200,  50),   # 沙漏 — 金黃
    "✔":  ( 70, 200,  90),   # 打勾（重量）— 綠色
    "🍃": ( 80, 190,  80),   # 葉子 — 綠色
    "🍱": (210, 170, 110),   # 便當盒 — 淺棕
    "🍺": (220, 170,  30),   # 啤酒 — 金黃
    "🎬": ( 50,  50,  50),   # 場記板 — 深灰
    "🎯": (210,  50,  50),   # 靶心 — 紅色
    "💤": (160, 200, 240),   # ZZZ 睡眠 — 淡藍
    "💭": (180, 200, 230),   # 思考泡泡 — 淡藍灰
    "📊": ( 80, 160, 220),   # 長條圖 — 藍色
    "📕": (210,  60,  60),   # 紅色書 — 紅色
    "📝": (255, 215,  60),   # 備忘錄 — 黃色
    "🔧": (150, 150, 160),   # 扳手 — 灰色
    "🔻": (215,  68,  62),   # 紅色向下三角 — 紅色
    "😐": (220, 190,  80),   # 面無表情 — 黃色
    "😩": (220, 160,  50),   # 疲憊 — 橘黃
    "😰": (100, 180, 230),   # 冷汗 — 藍色
    "😶": (210, 190,  80),   # 無嘴臉 — 黃色
    "🚪": (170, 120,  70),   # 門 — 棕色
    "🛏": (180, 160, 200),   # 床 — 淡紫灰
    "🤝": (210, 170, 110),   # 握手 — 膚色
    "🤢": (100, 200, 110),   # 噁心臉 — 綠色
}

def _render_mixed(surf: pygame.Surface,
                  main_font, text: str, color: tuple,
                  x: int, y: int) -> int:
    """
    逐段渲染文字：
    - 無 emoji 的行走快速路徑（單次 render，效能與舊版相同）
    - 有 emoji 的行逐字分段，emoji 以 _EMOJI_COLORS 著色
    回傳渲染後的總像素寬度。
    """
    if not text:
        return 0

    # ── 快速路徑：無 emoji 字元 ──────────────────────────────────
    has_emoji = any(_is_emoji_char(ch) for ch in text if ord(ch) != 0xFE0F)
    if not has_emoji:
        cleaned = _clean(text)
        s = main_font.render(cleaned, True, color)
        surf.blit(s, (x, y))
        return s.get_width()

    # ── 逐字路徑：含 emoji ────────────────────────────────────────
    em_f = _get_emoji_font(main_font.get_height())
    fh   = main_font.get_height()
    cx   = x
    seg  = []

    def _flush():
        nonlocal cx
        if not seg:
            return
        s = main_font.render("".join(seg), True, color)
        surf.blit(s, (cx, y))
        cx += s.get_width()
        seg.clear()

    for ch in text:
        cp = ord(ch)
        if cp == 0xFE0F:
            continue
        if _is_emoji_char(ch):
            if em_f is not None:
                _flush()
                em_col = _EMOJI_COLORS.get(ch, color)
                try:
                    es = em_f.render(ch, True, em_col)
                    surf.blit(es, (cx, y + (fh - es.get_height()) // 2))
                    cx += es.get_width()
                except Exception:
                    pass
            # else: emoji font not available → skip char silently (no square box)
        else:
            seg.append(ch)
    _flush()
    return cx - x

def _measure_mixed(main_font, text: str) -> int:
    """估算文字渲染寬度（含 emoji 佔位），用於置中計算。"""
    em_f = _get_emoji_font(main_font.get_height())
    w = 0
    seg = []
    def _flush():
        nonlocal w
        if seg:
            w += main_font.size("".join(seg))[0]
            seg.clear()
    for ch in text:
        cp = ord(ch)
        if cp == 0xFE0F:
            continue
        if _is_emoji_char(ch) and em_f is not None:
            _flush()
            try:
                w += em_f.size(ch)[0]
            except Exception:
                pass
        else:
            seg.append(ch)
    _flush()
    return w


def _wrap(text: str, font, max_w: int) -> list:
    """依寬度切行，支援 \\n 換段。"""
    lines = []
    for para in text.replace("\r", "").split("\n"):
        if font.size(para)[0] <= max_w:
            lines.append(para)
            continue
        buf = ""
        for ch in para:
            if font.size(buf + ch)[0] > max_w:
                lines.append(buf)
                buf = ch
            else:
                buf += ch
        if buf:
            lines.append(buf)
    return lines

def _gradient_surf(w: int, h: int, c1: tuple, c2: tuple) -> pygame.Surface:
    """縱向漸層 Surface（c1 在上，c2 在下）。純 Python，不依賴第三方套件。"""
    surf = pygame.Surface((w, h))
    for i in range(h):
        t   = i / max(h - 1, 1)
        col = tuple(int(c1[j] + (c2[j] - c1[j]) * t) for j in range(3))
        pygame.draw.line(surf, col, (0, i), (w - 1, i))
    return surf

def _load_cover(path: str, w: int, h: int) -> "pygame.Surface | None":
    """
    載入圖片並以 cover 模式縮放（保持比例填滿目標尺寸，置中裁切）。
    失敗時回傳 None，讓呼叫端 fallback 到漸層背景。
    """
    try:
        img = pygame.image.load(path).convert()
        import os as _os
        print(f"[圖片診斷] 載入成功: {_os.path.basename(path)}")
    except Exception as _e:
        import os as _os
        _exists = _os.path.exists(path)
        _size   = _os.path.getsize(path) if _exists else -1
        print(f"[圖片診斷] 載入失敗: {_os.path.basename(path)}")
        print(f"[圖片診斷]   存在:{_exists}  大小:{_size} bytes  錯誤:{_e}")
        return None
    iw, ih = img.get_size()
    scale  = max(w / iw, h / ih)
    nw     = int(iw * scale)
    nh     = int(ih * scale)
    img    = pygame.transform.smoothscale(img, (nw, nh))
    # 置中裁切到目標尺寸
    out = pygame.Surface((w, h))
    out.blit(img, (-((nw - w) // 2), -((nh - h) // 2)))
    return out

def _ease_out_back(t: float, ov: float = 1.55) -> float:
    """帶超出再回彈的緩動函式，用於按鈕彈跳感。"""
    t -= 1
    return t * t * ((ov + 1) * t + ov) + 1

def _ease_out_quart(t: float) -> float:
    """快速滑入、末端柔和停駐（道具店滑入）。"""
    return 1.0 - (1.0 - t) ** 4

def _ease_in_cubic(t: float) -> float:
    """緩慢起步、快速離場（道具店滑出）。"""
    return t ** 3

def _soft_shadow(surf: pygame.Surface,
                 rect:   pygame.Rect,
                 radius: int   = 12,
                 alpha:  int   = 50,
                 offset: tuple = (3, 5),
                 spread: int   = 4) -> None:
    """柔邊陰影（多層漸層 SRCALPHA，帶快取避免每幀重建）。"""
    ckey = (rect.width, rect.height, radius, alpha)
    if ckey not in _shadow_cache:
        sw  = rect.width  + spread * 2
        sh  = rect.height + spread * 2
        shd = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for i in range(spread, 0, -1):
            a  = int(alpha * (i / spread) ** 1.6)
            r2 = min(radius + i, min(sw, sh) // 2)
            pygame.draw.rect(shd, (20, 12, 5, a),
                             pygame.Rect(spread - i, spread - i,
                                         rect.width  + i * 2,
                                         rect.height + i * 2),
                             border_radius=r2)
        _shadow_cache[ckey] = shd
    surf.blit(_shadow_cache[ckey],
              (rect.x - spread + offset[0], rect.y - spread + offset[1]))

def _soft_shadow_circle(surf: pygame.Surface,
                        cx: int, cy: int, r: int,
                        alpha: int = 55) -> None:
    """圓形柔邊陰影（帶快取）。"""
    ckey = ("cs", r, alpha)
    if ckey not in _shadow_cache:
        sz  = r * 2 + 16
        ss  = pygame.Surface((sz, sz), pygame.SRCALPHA)
        hc  = sz // 2
        for i in range(5, 0, -1):
            a = int(alpha * (i / 5) ** 1.6)
            pygame.draw.circle(ss, (20, 12, 5, a), (hc, hc + i), r + i)
        _shadow_cache[ckey] = ss
    shd = _shadow_cache[ckey]
    surf.blit(shd, (cx - r - 8, cy - r - 8 + 5))

def _gloss_rect(surf: pygame.Surface, rect: pygame.Rect) -> None:
    """矩形按鈕上半部白色漸層光澤（帶快取）。"""
    ckey = ("gr", rect.width, rect.height)
    if ckey not in _gloss_cache:
        gh = max(4, int(rect.height * 0.44))
        gs = pygame.Surface((rect.width, gh), pygame.SRCALPHA)
        for i in range(gh):
            a = int(95 * (1 - i / gh) ** 1.9)
            pygame.draw.line(gs, (255, 255, 255, a), (2, i), (rect.width - 3, i))
        _gloss_cache[ckey] = gs
    surf.blit(_gloss_cache[ckey], rect.topleft)

def _gloss_circle(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """圓形按鈕上半部鏡片光澤（帶快取）。"""
    ckey = ("gc", r)
    if ckey not in _gloss_cache:
        gw = r
        gh = int(r * 0.58)
        gs = pygame.Surface((gw * 2, gh * 2), pygame.SRCALPHA)
        for i in range(gh):
            t  = 1 - i / gh
            hw = int(gw * t ** 0.55)
            a  = int(80 * t ** 1.85)
            if hw > 0:
                pygame.draw.line(gs, (255, 255, 255, a),
                                 (gw - hw, i), (gw + hw - 1, i))
        _gloss_cache[ckey] = gs
    surf.blit(_gloss_cache[ckey], (cx - r, cy - r + 5))

def _panel_top_shadow(surf: pygame.Surface,
                      x: int, y: int, w: int,
                      alpha: int = 40, h: int = 12) -> None:
    """面板頂部向下的陰影條（用於行動面板頂緣增加層次感）。"""
    ckey = ("pts", w, alpha, h)
    if ckey not in _shadow_cache:
        ss = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(h):
            a = int(alpha * (1 - i / h) ** 1.5)
            pygame.draw.line(ss, (20, 12, 5, a), (0, i), (w - 1, i))
        _shadow_cache[ckey] = ss
    surf.blit(_shadow_cache[ckey], (x, y))

def _advance_hover(key: tuple, is_hover: bool) -> float:
    """更新 hover 動畫進度，回傳合成縮放比（含點擊彈跳）。"""
    t = _anim_hover.get(key, 0.0)
    t = min(1.0, t + 0.14) if is_hover else max(0.0, t - 0.14)
    _anim_hover[key] = t

    # 點擊壓縮後回彈
    c_s = 1.0
    if key in _click_reg:
        el = pygame.time.get_ticks() - _click_reg[key]
        if el < 190:
            ct = el / 190.0
            c_s = (1.0 - 0.08 * (ct / 0.35)) if ct < 0.35 \
                  else (0.92 + 0.08 * ((ct - 0.35) / 0.65))
        else:
            del _click_reg[key]

    h_s = (1.0 + _ease_out_back(t) * 0.046) if t > 0 else 1.0
    return h_s * c_s

def _scaled_rect(base: pygame.Rect, scale: float) -> pygame.Rect:
    dw = int(base.width  * (scale - 1))
    dh = int(base.height * (scale - 1))
    return pygame.Rect(base.x - dw // 2, base.y - dh // 2,
                       base.width + dw, base.height + dh)

def _float_offset(amp: int = 7, speed: float = 0.00180, phase: float = 0.0) -> int:
    """
    回傳緩慢正弦浮動的垂直偏移（像素）。
    amp   : 振幅（像素），speed : 角速度（rad/ms），phase : 初始相位（rad）。
    """
    import math
    return int(math.sin(pygame.time.get_ticks() * speed + phase) * amp)

def _draw_float_label_card(surf, font, text, x_center, base_y,
                           text_col=None,
                           bg=(20, 10, 5), bg_alpha=135,
                           pad_x=18, pad_y=8,
                           amp=6, speed=0.00175, phase=0.0,
                           radius=12):
    """
    在 (x_center, base_y) 處繪製帶半透明底色的浮動標籤卡片：
      • 陰影 → 半透明底板（SRCALPHA） → CYAN 邊框 → 文字
    回傳 (card_rect, float_y_offset)，供呼叫者對齊其他元素。
    """
    fy     = _float_offset(amp, speed, phase)
    col    = text_col if text_col is not None else PANEL
    t_surf = font.render(text, True, col)
    tw, th = t_surf.get_width(), t_surf.get_height()
    cw     = tw + pad_x * 2
    ch     = th + pad_y * 2
    cx     = x_center - cw // 2
    cy     = base_y + fy
    card_r = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card_r, radius=radius, alpha=36, offset=(0, 5))
    # 按 (尺寸+顏色) 快取，避免每幀重建 SRCALPHA Surface
    _fc_key = ("fc", cw, ch, bg, bg_alpha)
    if _fc_key not in _shadow_cache:
        _fs = pygame.Surface((cw, ch), pygame.SRCALPHA)
        _fs.fill((*bg, bg_alpha))
        _shadow_cache[_fc_key] = _fs
    surf.blit(_shadow_cache[_fc_key], (cx, cy))
    pygame.draw.rect(surf, CYAN, card_r, 1, border_radius=radius)
    surf.blit(t_surf, (x_center - tw // 2, cy + pad_y))
    return card_r, fy

def _premium_btn(surf: pygame.Surface,
                 base:     pygame.Rect,
                 col:      tuple,
                 is_hover: bool,
                 radius:   int = 14) -> pygame.Rect:
    """
    高質感矩形按鈕：柔邊陰影 + 3D 底邊厚度 + 主色 + 光澤 + 高光邊框。
    回傳實際繪製的 Rect（動畫後），供呼叫者定位按鈕上的文字。
    """
    key = (base.centerx, base.centery)
    sc  = _advance_hover(key, is_hover)
    dr  = _scaled_rect(base, sc)

    _soft_shadow(surf, dr, radius,
                 alpha=65 if is_hover else 46,
                 offset=(2, 3) if is_hover else (3, 6))

    dark = tuple(max(0, int(c * 0.70)) for c in col)
    pygame.draw.rect(surf, dark,
                     pygame.Rect(dr.x, dr.y + 4, dr.width, dr.height),
                     border_radius=radius)

    pygame.draw.rect(surf, col, dr, border_radius=radius)
    _gloss_rect(surf, dr)

    bdr = tuple(min(255, int(c * 1.20 + 30)) for c in col)
    pygame.draw.rect(surf, bdr, dr, 1, border_radius=radius)

    return dr

def _premium_circle(surf: pygame.Surface,
                    cx: int, cy: int, r: int,
                    col:      tuple,
                    is_hover: bool,
                    key:      tuple = None) -> int:
    """
    高質感圓形按鈕：圓形陰影 + 3D 底圓 + 主色 + 光澤 + 高光圓環。
    回傳實際繪製半徑（動畫後）。
    """
    if key is None:
        key = (cx, cy)

    t   = _anim_hover.get(key, 0.0)
    t   = min(1.0, t + 0.14) if is_hover else max(0.0, t - 0.14)
    _anim_hover[key] = t
    h_s = (1.0 + _ease_out_back(t) * 0.052) if t > 0 else 1.0

    c_s = 1.0
    if key in _click_reg:
        el = pygame.time.get_ticks() - _click_reg[key]
        if el < 190:
            ct = el / 190.0
            c_s = (1.0 - 0.08 * (ct / 0.35)) if ct < 0.35 \
                  else (0.92 + 0.08 * ((ct - 0.35) / 0.65))
        else:
            del _click_reg[key]

    ar = max(1, int(r * h_s * c_s))

    _soft_shadow_circle(surf, cx, cy, ar)

    dark = tuple(max(0, int(c * 0.70)) for c in col)
    pygame.draw.circle(surf, dark, (cx, cy + 4), ar)
    pygame.draw.circle(surf, col,  (cx, cy),     ar)
    _gloss_circle(surf, cx, cy, ar)

    bdr = tuple(min(255, int(c * 1.20 + 30)) for c in col)
    pygame.draw.circle(surf, bdr, (cx, cy), ar, 2)

    return ar

def _portrait_orig_load(key: str):
    """載入並快取原始立繪（未縮放）。"""
    if key in _portrait_orig:
        return _portrait_orig[key]
    path = os.path.join(_CHAR_ART_DIR, f"{key}.png")
    if not os.path.isfile(path):
        return None
    try:
        surf = pygame.image.load(path).convert_alpha()
        _portrait_orig[key] = surf
        return surf
    except Exception:
        return None

def _portrait_scaled_load(key: str, w: int, h: int):
    """取得縮放至 (w, h) 的立繪（等比填滿高度，水平置中，不拉伸）。"""
    ck = (key, w, h)
    if ck in _portrait_scl:
        return _portrait_scl[ck]
    orig = _portrait_orig_load(key)
    if orig is None:
        return None
    ow, oh = orig.get_size()
    scale = h / oh
    nw, nh = int(ow * scale), h
    if nw > w:
        scale = w / ow
        nw, nh = w, int(oh * scale)
    scaled = pygame.transform.smoothscale(orig, (nw, nh))
    _portrait_scl[ck] = scaled
    return scaled

def _portrait_head_load(prefix: str):
    """取得圓形頭像 Surface（直徑 84px，SRCALPHA，已快取）。"""
    if prefix in _portrait_head_cache:
        return _portrait_head_cache[prefix]
    key  = f"{prefix}_head"
    orig = _portrait_orig_load(key)
    if orig is None:
        return None
    D      = 84
    scaled = pygame.transform.smoothscale(orig, (D, D))
    mask   = pygame.Surface((D, D), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.circle(mask, (255, 255, 255, 255), (D // 2, D // 2), D // 2)
    result = scaled.copy()
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _portrait_head_cache[prefix] = result
    return result

def _get_portrait_key() -> str:
    """根據當前遊戲狀態決定應顯示哪張立繪的 key。"""
    # ── 強制覆寫（考前儀式等特定場景優先）─────────────────────
    if _portrait_override_key[0] is not None:
        return _portrait_override_key[0]
    prefix = _portrait_prefix[0]
    if not prefix:
        return ""
    week   = _week[0]
    mode   = _mode[0]
    player = _player[0]

    # ── 基礎 key（依週次距考試距離）──────────────────────────
    if week in (8, 16):
        base = f"{prefix}_8"
    elif week > 0:
        dist_mid = (8  - week) if week < 8  else 999
        dist_fin = (16 - week) if week < 16 else 999
        dist = min(dist_mid, dist_fin)
        base = f"{prefix}_6" if 0 < dist <= 3 else f"{prefix}_1"
    else:
        base = f"{prefix}_1"

    # ── 覆蓋：成績公告 modal → _4 ───────────────────────────
    if _modal[0] == "grade_report":
        return f"{prefix}_4"

    # ── 覆蓋：突發事件彈窗 → _4 ─────────────────────────────
    if mode == "event_ok":
        return f"{prefix}_4"

    # ── 覆蓋：劇情對話 / yn / 非標準選項 → _3 ───────────────
    if mode in ("story", "yn"):
        return f"{prefix}_3"
    if (mode == "choices" and _choices
            and not all(c in _STANDARD_ACTIONS for c in _choices)):
        return f"{prefix}_3"

    # ── 覆蓋：行動後狀態（體力 / 滿足感）──────────────────────
    if player is not None:
        sat   = player.satisfaction
        ratio = player.stamina / max(player.stamina_max, 1)
        if sat < 50:
            return f"{prefix}_5"
        if ratio < 1 / 3:
            return f"{prefix}_0"
        if ratio >= 0.5 and sat >= 80:
            return f"{prefix}_2"

    return base

def _portrait_switch(new_key: str, rect_w: int, rect_h: int) -> None:
    """若目標 key 與當前不同，啟動淡入淡出轉場。"""
    if new_key == _portrait_curr_key[0]:
        return
    new_surf = _portrait_scaled_load(new_key, rect_w, rect_h) if new_key else None
    _portrait_prev[0]     = _portrait_curr[0]
    _portrait_curr[0]     = new_surf
    _portrait_curr_key[0] = new_key
    _portrait_fade_t0[0]  = pygame.time.get_ticks() if new_surf is not None else 0

def _item_icon_color(item: dict) -> tuple:
    """依道具效果類型回傳圖示圓形底色。"""
    if "stamina_restore"   in item: return GREEN
    if "intel_gain"        in item: return CYAN
    if "luck_gain"         in item: return YELLOW
    if "satisfaction_gain" in item: return (220, 100, 155)
    return BTN_N

def _get_shop_icon(item_id: str, diameter: int):
    """
    回傳指定 item_id 的圓形裁切小圖示 Surface（SRCALPHA）。
    未找到對應圖或載入失敗時回傳 None（呼叫端可退回顯示文字）。
    快取於 _shop_icon_cache[(item_id, diameter)]。
    """
    key = (item_id, diameter)
    if key in _shop_icon_cache:
        return _shop_icon_cache[key]
    fname = _SHOP_ITEM_ICON_MAP.get(item_id)
    if not fname:
        _shop_icon_cache[key] = None
        return None
    path = os.path.join(_SHOP_ICON_DIR, fname + ".png")
    try:
        raw = pygame.image.load(path).convert_alpha()
    except Exception:
        _shop_icon_cache[key] = None
        return None
    scaled = pygame.transform.smoothscale(raw, (diameter, diameter))
    # 圓形遮罩：圓外透明
    mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.circle(mask, (255, 255, 255, 255),
                       (diameter // 2, diameter // 2), diameter // 2)
    scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    _shop_icon_cache[key] = scaled
    return scaled

def _apply_shop_purchase(idx: int) -> None:
    """
    pygame 主執行緒直接套用購買效果。
    遊戲執行緒此時阻塞於 _shop_exit_event，無競爭讀寫風險。
    注意：此模組沒有 import notify()，改用 _cmd_q.append 直接推訊息。
    """
    def _msg(text: str):
        _cmd_q.append(("msg", text))

    item   = _shop_items[idx]
    player = _player[0]
    if player is None:
        return
    if player.money < item["price"]:
        _shop_msg[0]      = f"❌ 金錢不足！需要 ${item['price']} 元"
        _shop_msg_time[0] = pygame.time.get_ticks()
        return

    player.money -= item["price"]

    if "stamina_restore" in item:
        player.restore_stamina(item["stamina_restore"])
        _msg(f"  ✨ 恢復了 {item['stamina_restore']} 點體力！")
    if "intel_gain" in item:
        player.intel += item["intel_gain"]
        _msg(f"  📖 智力提升了 {item['intel_gain']} 點！")
    if "satisfaction_gain" in item:
        if item.get("id") == "snack":
            # 運氣影響滿足感機率：70% + (luck - 40)%，範圍 [0, 100]
            _sat_prob = max(0.0, min(1.0, 0.70 + (player.luck - 40) * 0.01))
            if random.random() < _sat_prob:
                player.satisfaction = max(0, min(100,
                    player.satisfaction + item["satisfaction_gain"]))
                _msg(f"  🎮 滿足感提升了 {item['satisfaction_gain']} 點！")
            else:
                _msg("  😐 吃了點心但心情沒什麼起色……（滿足感未提升）")
        else:
            player.satisfaction = max(0, min(100,
                player.satisfaction + item["satisfaction_gain"]))
            _msg(f"  🎮 滿足感提升了 {item['satisfaction_gain']} 點！")
    if "luck_gain" in item:
        player.luck += item["luck_gain"]
        _msg(f"  🍀 運氣提升了 {item['luck_gain']} 點！")
    if "status" in item:
        player.status_effects[item["status"]] = item["duration"]
        _msg(f"  ➕ 獲得狀態：【{item['status']}】（持續 {item['duration']} 週）")
    if "allnighter_risk" in item:
        es = _shop_event_sys[0]
        if es is not None:
            es.set_allnighter_risk(item["allnighter_risk"])
            _msg(f"  ⚠️ 睡過頭觸發機率增加 {int(item['allnighter_risk'] * 100)}%！")

    _play_sfx("cash")
    _shop_msg[0]      = f"✅ 購買了【{item['name']}】！剩餘 ${player.money} 元"
    _shop_msg_time[0] = pygame.time.get_ticks()


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
