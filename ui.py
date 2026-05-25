# ============================================================
#  模組：ui.py — pygame 圖形介面
# ============================================================
# 架構：遊戲邏輯跑在背景執行緒，pygame 主迴圈跑在主執行緒。
# 兩者透過 Queue 與 threading.Event 通訊：
#   遊戲 → UI：把命令放入 _cmd_q（notify / ask_choice 等）
#   UI → 遊戲：玩家點擊後設定 _reply_event，遊戲執行緒繼續
# ============================================================

import pygame
import threading
import queue
import sys
import os

# ─────────────────────────────────────────
#  顏色（陽光少女色系）
# ─────────────────────────────────────────
# 整體為淺色主題：淺暖底色 + 深棕文字 + 珊瑚橘按鈕 + 晴天藍強調
WHITE     = ( 72,  38,  18)   # 深可可棕 — 主要文字（淺色底用深色字）
BLACK     = ( 72,  38,  18)   # 輸入框文字（同上）
GRAY      = (158, 120,  88)   # 暖沙棕 — 次要文字 / 邊框
DARK_GRAY = (212, 182, 148)   # 淺暖沙 — 暗按鈕 / 進度條底色
BG        = (255, 240, 215)   # 暖杏黃 — log 區 / 主背景
PANEL     = (255, 250, 236)   # 奶霜白 — 面板底色
BTN_N     = (255, 148,  95)   # 珊瑚橘 — 一般按鈕
BTN_H     = (255, 195, 145)   # 淡珊瑚 — hover 按鈕
GREEN     = ( 78, 172,  90)   # 嫩草綠
RED       = (215,  68,  62)   # 草莓紅
YELLOW    = (190, 128,  12)   # 琥珀金（深色，在淺底可見）
CYAN      = ( 78, 165, 210)   # 晴天藍 — 強調邊框（僅用於框線）
MILK      = (255, 253, 248)   # 純奶白 — 文字輸入框背景
TITLE     = ( 93,  64,  55)   # #5D4037 深棕 — 標題文字（取代各處藍色 CYAN 字）

# ─────────────────────────────────────────
#  版面尺寸
# ─────────────────────────────────────────
WIN_W    = 960
WIN_H    = 720
STATUS_H = 175                            # 狀態欄（頭像 + 智力/運氣列）
ACTION_H = 210                            # 底部行動/敘述面板
TAB_H    = 36                             # 行動面板頂部標籤列
CHAR_H   = WIN_H - STATUS_H - ACTION_H   # 人物立繪區 = 335px

# ─────────────────────────────────────────
#  執行緒通訊
# ─────────────────────────────────────────
_cmd_q       = queue.Queue()    # 遊戲執行緒 → pygame 主執行緒
_reply_event = threading.Event()
_reply_val   = [None]           # 用 list 讓內層函式可修改

# ─────────────────────────────────────────
#  UI 狀態（僅主執行緒讀寫）
# ─────────────────────────────────────────
_log     = []       # 所有已換行的訊息字串
_player  = [None]   # 角色物件參照
_mode      = [None]   # "choices" | "yn" | "text" | None
_choices   = []       # 選項標籤列表
_prompt    = [""]     # yn / text 提示文字
_yn_labels = ["是", "否"]   # yn 模式的按鈕文字（可自定義）
_tvalue  = [""]     # text 模式的目前輸入內容
_scroll    = [0]      # 訊息區往上捲動的行數（保留供 end 畫面使用）
_composing = [""]   # IME 組字預覽（輸入法尚未確認的字）
_time_units    = [0]      # 本週剩餘時間點（底部標籤列顯示用）
_is_fullscreen = [False]  # 目前是否全螢幕
_week          = [0]      # 當前週次（1–16，0 表示尚未開始）
_font_micro    = [None]   # 極小字型（週次輪盤數字用）

# ── 音效 ────────────────────────────────────────────────────
_sfx: dict = {}   # name -> pygame.mixer.Sound（run_ui 啟動後載入）

def _play_sfx(name: str) -> None:
    """播放指定音效；若未載入或發生錯誤則靜默跳過。"""
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
            pygame.mixer.music.fadeout(BGM_FADE_MS)
        except Exception:
            pass

# ── 動畫 / 視覺特效狀態 ────────────────────────────────────────
_anim_hover:   dict = {}   # (cx,cy) -> float 0..1  hover 進度
_click_reg:    dict = {}   # (cx,cy) -> ticks_ms   點擊時間戳
_shadow_cache: dict = {}   # 陰影 Surface 快取
_gloss_cache:  dict = {}   # 光澤 Surface 快取

# 畫面階段：start → 開始畫面，game → 遊戲中，end → 結束畫面
_phase         = ["start"]
_start_event   = threading.Event()   # 玩家點擊「開始遊戲」後被 set
_restart_event = threading.Event()   # 玩家點擊「再來一次」後被 set

# ── 角色創建專屬狀態（_phase == "char_create" 時使用）────────
_cc_mode        = [""]          # "name"|"dept"|"drawbacks"|"stats"|"talent"
_cc_data        = [None]        # 當前步驟資料（選項列表等）
_cc_sel         = []            # 已選取的索引（drawbacks 複選、talent 單選）
_cc_tvalue      = [""]          # name 輸入框文字
_cc_composing   = [""]          # name 輸入法組字預覽
_cc_stat_vals   = [10, 10, 10]  # [體力, 智力, 運氣]
_cc_stat_total  = [30]          # 本次可分配總點數
_cc_active_stat = [None]        # 鍵盤焦點在哪個 stat（0|1|2|None）
_cc_stat_raw    = ["10","10","10"]  # 三個 stat 輸入框的原始字串
_cc_reply_event = threading.Event()
_cc_reply_val   = [None]

# ── Modal 彈出畫面狀態（課表 / 成績公告）────────────────────
_modal       = [None]   # "timetable" | "grade_report" | None
_modal_data  = [None]   # modal 要顯示的資料
_modal_event = threading.Event()

# ── 道具店 UI 狀態 ───────────────────────────────────────────
_shop_items      = []     # 商品列表（由 open_shop_ui 填入）
_shop_hover_idx  = [-1]   # 目前被 hover 的商品索引（-1 = 無）
_shop_msg        = [""]   # 購買結果訊息
_shop_msg_time   = [0]    # 訊息顯示的時間戳（ms）
_shop_exit_event = threading.Event()

# ── 行動結果彈出視窗 ─────────────────────────────────────────
_popup_lines   = []    # 結果文字行列表
_popup_title   = ["行動結果"]  # 彈出視窗標題（行動名稱）
_popup_t0      = [0]   # 觸發時間戳（ms，0 = 未啟用）
POPUP_DURATION = 3400  # 整體顯示時長（ms）
POPUP_IN_MS    = 320   # 滑入動畫時長（ms）
POPUP_OUT_MS   = 280   # 滑出動畫時長（ms）

# ── 漣漪轉場效果（週次切換時） ───────────────────────────────
_ripple_t0       = [0]       # 觸發時間戳（ms，0 = 未啟用）
RIPPLE_DURATION  = 900       # 總時長（ms）
_ripple_np_cache : dict = {} # numpy 座標格快取（同解析度只建一次）

# ── 角色創建背景影片（WEBM 循環播放） ────────────────────────
_cc_video_cap    = [None]  # cv2.VideoCapture 物件（None 表示未載入）
_cc_video_fps    = [30.0]  # 影片 FPS
_cc_video_surf   = [None]  # 當前幀的 pygame.Surface
_cc_video_last   = [0]     # 上次更新幀的時間戳（ms）
_cc_overlay_surf = [None]  # 奶茶↔奶白漸層遮罩（75% 透明，懶初始化）

# ── BGM 狀態（非阻塞淡入淡出） ───────────────────────────────
BGM_FADE_MS    = 1500        # 淡出 / 淡入各 1.5 秒
_bgm_dir       = [""]        # BGM 資料夾路徑（run_ui 啟動後設定）
_bgm_current   = [None]      # 目前播放的檔名（None = 靜音）
_bgm_pending   = [None]      # 淡出後待播的檔名（None = 靜音）
_bgm_switch_at = [0]         # 允許載入新曲的最早時間戳（ms）

# 週次 → BGM 對照表（None = 待定，播放時靜音）
_WEEK_BGM: dict = {
    1:  "Music-Town_Day.mp3",
    2:  "Music-Town_Day.mp3",
    3:  "Music-Ocean_Day.mp3",
    4:  "Music-Ocean_Day.mp3",
    5:  "Music-Skeletron.mp3",
    6:  "Music-Skeletron.mp3",
    7:  "Music-Deerclops.mp3",
    8:  "Music-Rainbow_Boulder_(loop).mp3",
    9:  "Music-Forest_Day_(Otherworldly).mp3",
    10: "Music-Forest_Day_(Otherworldly).mp3",
    11: "Music-Storm.mp3",
    12: "Music-Storm.mp3",
    13: None,   # 待定
    14: None,   # 待定
    15: None,   # 待定
    16: None,   # 待定
}

# ── 道具店滑動轉場 ────────────────────────────────────────────
_shop_slide_dir = ["none"]   # "in" | "out" | "out_done" | "none"
_shop_slide_t0  = [0]        # 動畫開始時間（ms）
SHOP_SLIDE_MS   = 370        # 單向滑動時長（ms）

# ─────────────────────────────────────────
#  供其他模組呼叫的 API
# ─────────────────────────────────────────

def notify(msg: str):
    """取代 print()：把訊息推入 UI 訊息區。"""
    _cmd_q.put(("msg", str(msg)))

def set_player(player):
    """把角色物件傳給 UI，讓狀態欄即時更新。"""
    _cmd_q.put(("player", player))

def ask_choice(options) -> int:
    """
    取代 get_player_choice()。
    options: 字串列表 或 帶 'name' key 的字典列表。
    回傳：0 = 返回/結束，1..n = 玩家選擇的編號（1-based）。
    """
    labels = [opt["name"] if isinstance(opt, dict) else str(opt) for opt in options]
    _cmd_q.put(("choices", labels))
    _reply_event.clear()
    _reply_event.wait()
    return _reply_val[0]

def ask_text(prompt: str, default: str = "") -> str:
    """取代自由文字輸入的 input()：顯示輸入框，確認後回傳字串。"""
    _cmd_q.put(("text", prompt, default))
    _reply_event.clear()
    _reply_event.wait()
    return _reply_val[0]

def ask_yn(prompt: str,
           yes_label: str = "是",
           no_label:  str = "否") -> bool:
    """取代 y/N 型的 input()：顯示自定義標籤按鈕，回傳 True / False。"""
    _cmd_q.put(("yn", prompt, yes_label, no_label))
    _reply_event.clear()
    _reply_event.wait()
    return _reply_val[0]

def wait_start():
    """遊戲執行緒呼叫：阻塞直到玩家點擊「開始遊戲」。"""
    _start_event.clear()
    _start_event.wait()

def notify_end():
    """遊戲結束後呼叫：切換到結束畫面。"""
    _cmd_q.put(("phase", "end"))

def wait_restart():
    """阻塞直到玩家點擊「再來一次」。"""
    _restart_event.clear()
    _restart_event.wait()

def reset_ui():
    """清除上一局的 log 與狀態，供下一局使用。"""
    _cmd_q.put(("reset", None))

def set_time(n: int):
    """更新底部標籤列的剩餘時間點數字。"""
    _cmd_q.put(("set_time", n))

def set_week(w: int):
    """由遊戲執行緒呼叫，更新週次輪盤顯示並觸發對應 BGM。"""
    _week[0] = w
    _cmd_q.put(("bgm_week", w))

# ── 角色創建 API ─────────────────────────────────────────────

def begin_char_create():
    """切換到角色創建畫面（隱藏一般遊戲 UI）。"""
    _cmd_q.put(("phase", "char_create"))

def end_char_create():
    """角色創建完成，切回遊戲畫面。"""
    _cmd_q.put(("phase", "game"))

def ask_cc_name(prompt: str) -> str:
    """顯示姓名輸入 modal，回傳玩家輸入的字串。"""
    _cmd_q.put(("cc_name", prompt))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_dept(options: list) -> int:
    """顯示系級橫向卡片，回傳 1-based 選擇編號。"""
    _cmd_q.put(("cc_dept", options))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_drawbacks(drawbacks: list, max_sel: int = 2) -> list:
    """顯示負面特質切換卡片（最多 max_sel 個），回傳已選字典列表。"""
    _cmd_q.put(("cc_drawbacks", drawbacks, max_sel))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_stats(total_pts: int) -> tuple:
    """顯示能力點分配畫面，回傳 (stamina, intel, luck)。"""
    _cmd_q.put(("cc_stats", total_pts))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_talent(candidates: list) -> dict:
    """顯示天賦卡片（單選），回傳選中的天賦字典。"""
    _cmd_q.put(("cc_talent", candidates))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def notify_timetable(courses: list):
    """
    顯示課表彈出畫面，阻塞直到玩家點確認。
    courses: [{"name": "統計學", "day": "週一", "time": "08:10", "credits": 3}, ...]
    """
    _cmd_q.put(("timetable", courses))
    _modal_event.clear()
    _modal_event.wait()

def notify_grade_report(items: list):
    """
    顯示成績公告彈出畫面，阻塞直到玩家點確認。
    items: [{"name": "小考一", "score": 75}, ...]
    """
    _cmd_q.put(("grade_report", items))
    _modal_event.clear()
    _modal_event.wait()

def open_shop_ui(items: list) -> None:
    """
    開啟道具店圖形化介面，阻塞遊戲執行緒直到玩家離開商店。
    購買邏輯由 pygame 主執行緒的事件處理器直接套用（遊戲執行緒此時已暫停）。
    """
    _shop_items.clear()
    _shop_items.extend(items)
    _shop_hover_idx[0] = -1
    _shop_msg[0]       = ""
    _shop_msg_time[0]  = 0
    _shop_exit_event.clear()
    _cmd_q.put(("phase", "shop"))
    _shop_exit_event.wait()
    _cmd_q.put(("phase", "game"))


def trigger_ripple() -> None:
    """觸發漣漪轉場效果；由遊戲執行緒在週次切換時呼叫。"""
    _cmd_q.put(("ripple",))


def show_action_result(lines: list, title: str = "行動結果") -> None:
    """
    由遊戲執行緒呼叫，觸發畫面右側由右而左滑入的行動結果視窗。
    lines: 要顯示的結果文字列表（如「體力 -4」、「金錢 +150」）。
    title: 彈出視窗的標題，通常傳入行動名稱（如「認真讀書」）。
    """
    _popup_lines.clear()
    _popup_lines.extend(str(l) for l in lines)
    _popup_title[0] = title
    _popup_t0[0] = pygame.time.get_ticks()

# ─────────────────────────────────────────
#  相容舊有介面（讓尚未修改的模組繼續可匯入）
# ─────────────────────────────────────────

def display_status(player):
    set_player(player)

def display_menu(options, title="請選擇行動"):
    notify(f"--- {title} ---")
    for i, opt in enumerate(options, start=1):
        name = opt["name"] if isinstance(opt, dict) else opt
        desc = f" - {opt['desc']}" if isinstance(opt, dict) and "desc" in opt else ""
        notify(f"  {i}. {name}{desc}")
    notify("  0. 返回 / 結束")

def get_player_choice(options) -> int:
    return ask_choice(options)

# ─────────────────────────────────────────
#  pygame 繪製工具（私有）
# ─────────────────────────────────────────

def _get_font(size: int):
    """找第一個能渲染中文的系統字型。"""
    candidates = [
        "microsoftyahei", "microsoft yahei",
        "simsun", "nsimsun",
        "arial unicode ms",
        "noto sans cjk tc", "noto sans tc",
    ]
    for name in candidates:
        try:
            f = pygame.font.SysFont(name, size)
            f.render("測", True, WHITE)
            return f
        except Exception:
            pass
    return pygame.font.SysFont(None, size)


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


# 漸層 Surface 快取（由 run_ui() 初始化後填入）
_grads: dict = {}


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
    except Exception:
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


# ─────────────────────────────────────────
#  視覺特效輔助（陰影 / 光澤 / 彈跳動畫）
# ─────────────────────────────────────────

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


def _draw_ripple_overlay(surf: pygame.Surface) -> None:
    """
    全螢幕像素扭曲漣漪效果（週次切換時，取代同心圓環）。
    優先使用 numpy surfarray 做向量化徑向位移，
    若 numpy 不可用則退回同心環版本。
    """
    if _ripple_t0[0] == 0:
        return
    elapsed = pygame.time.get_ticks() - _ripple_t0[0]
    if elapsed >= RIPPLE_DURATION:
        _ripple_t0[0] = 0
        return
    try:
        _ripple_warp(surf, elapsed)
    except Exception:
        _ripple_rings(surf, elapsed)


def _ripple_warp(surf: pygame.Surface, elapsed: int) -> None:
    """
    numpy 向量化版漣漪：
    1. 擷取當前幀（半解析度縮小以節省計算量）
    2. 以「擴散波前 + 高斯包絡 × 正弦函數」計算各像素的徑向位移
    3. 用 fancy indexing 取樣後放大貼回全解析度
    計算量：480×360 ≈ 172,800 像素，座標格快取後約 15–25 ms/frame。
    """
    import numpy as np

    t = elapsed / RIPPLE_DURATION

    # ── 振幅包絡：快速起（0–12%）、緩慢衰（12–100%）──────────
    if t < 0.12:
        amp_env = (t / 0.12) ** 0.55
    else:
        amp_env = ((1.0 - t) / 0.88) ** 0.80
    amp_max = 20.0 * amp_env
    if amp_max < 0.5:
        return

    W, H   = WIN_W, WIN_H
    SW, SH = W // 2, H // 2     # 半解析度尺寸
    hcx    = SW // 2             # 半解析度中心 x
    hcy    = SH // 2             # 半解析度中心 y

    # ── 座標格快取（同解析度只算一次）──────────────────────────
    ckey = (SW, SH)
    if ckey not in _ripple_np_cache:
        _gx, _gy = np.meshgrid(np.arange(SW, dtype=np.float32),
                                np.arange(SH, dtype=np.float32), indexing='ij')
        _dx   = (_gx - hcx).astype(np.float32)
        _dy   = (_gy - hcy).astype(np.float32)
        _dist = np.hypot(_dx, _dy)
        _dist = np.maximum(_dist, 1.0)
        _mdh  = float(np.hypot(hcx, hcy))   # 半解析度對角半距
        _ripple_np_cache[ckey] = (_gx, _gy, _dx, _dy, _dist, _mdh)
    gx, gy, dx, dy, dist, max_dist_h = _ripple_np_cache[ckey]

    # ── 擷取當前幀，縮至半解析度 ────────────────────────────────
    src_arr = pygame.surfarray.array3d(
        pygame.transform.scale(surf.copy(), (SW, SH)))

    # ── 漣漪波前：從中心往外擴散，速度使其在 ~85% 時程內越過角落 ─
    wave_front   = max_dist_h * t * (1.0 / 0.85)
    wave_dist    = dist - wave_front   # 負值 = 波前已過；正值 = 尚未抵達

    # ── 高斯包絡 × 正弦位移（在波前附近形成局部擾動波包）───────
    sigma       = 38.0                            # 包絡寬（半解析度像素）
    wave_len_h  = 52.0                            # 波長（半解析度像素）≈ 104 全解析度像素
    freq        = 2.0 * np.pi / wave_len_h
    envelope    = np.exp(-(wave_dist ** 2) / (2.0 * sigma * sigma))
    displacement = amp_max * envelope * np.sin(wave_dist * freq)

    # ── 徑向分量位移（x / y 各自按方向比例分配）──────────────────
    disp_x = (displacement * dx / dist).astype(np.int32)
    disp_y = (displacement * dy / dist).astype(np.int32)

    # ── 採樣來源座標，clamp 至邊界 ──────────────────────────────
    src_x = np.clip(gx.astype(np.int32) + disp_x, 0, SW - 1)
    src_y = np.clip(gy.astype(np.int32) + disp_y, 0, SH - 1)

    # ── fancy indexing 取樣 → 放大 → 貼回全解析度 ───────────────
    distorted = src_arr[src_x, src_y]
    surf.blit(
        pygame.transform.scale(
            pygame.surfarray.make_surface(distorted), (W, H)),
        (0, 0))

    # ── 最初的白色閃光（模擬石頭落水的瞬間衝擊）────────────────
    if t < 0.10:
        flash_a = int(210 * (1.0 - t / 0.10) ** 2.2)
        _fl = pygame.Surface((W, H), pygame.SRCALPHA)
        _fl.fill((255, 255, 255, flash_a))
        surf.blit(_fl, (0, 0))


def _ripple_rings(surf: pygame.Surface, elapsed: int) -> None:
    """退回版：numpy 不可用時，退回同心擴散環效果。"""
    t  = elapsed / RIPPLE_DURATION
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    if t < 0.13:
        ft = t / 0.13
        ov.fill((255, 255, 255, int(125 * (1.0 - ft) ** 2)))
    cx, cy = WIN_W // 2, WIN_H // 2
    diag   = int((WIN_W ** 2 + WIN_H ** 2) ** 0.5 // 2 + 32)
    for i in range(3):
        delay = i * 0.26
        lt    = (t - delay) / max(1.0 - delay, 0.001)
        if lt <= 0.0 or lt > 1.0:
            continue
        lt_e  = 1.0 - (1.0 - lt) ** 2.4
        r     = int(diag * lt_e)
        alpha = int(215 * (1.0 - lt_e) ** 1.7)
        thick = max(2, int(26 * (1.0 - lt_e) + 2))
        if r > 0 and alpha > 4:
            pygame.draw.circle(ov, (190, 225, 255, alpha), (cx, cy), r, thick)
    surf.blit(ov, (0, 0))


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
    card_s = pygame.Surface((cw, ch), pygame.SRCALPHA)
    card_s.fill((*bg, bg_alpha))
    surf.blit(card_s, (cx, cy))
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


def _draw_status(surf, fs, fm, player, rect):
    """上方狀態欄。"""
    if "status" in _grads:
        surf.blit(_grads["status"], rect.topleft)
    else:
        pygame.draw.rect(surf, PANEL, rect)
    pygame.draw.rect(surf, CYAN, rect, 2, border_radius=10)
    x, y = rect.x + 12, rect.y + 8
    gap = 5

    if player is None:
        surf.blit(fm.render("等待角色資料…", True, GRAY), (x, y))
        return

    surf.blit(fm.render(f"【{player.name}】 {player.department}", True, TITLE), (x, y))
    y += fm.get_height() + gap

    bw, bh = 220, 14

    # 體力條
    ratio = player.stamina / max(1, player.stamina_max)
    pygame.draw.rect(surf, DARK_GRAY, (x, y, bw, bh))
    pygame.draw.rect(surf, GREEN, (x, y, int(bw * ratio), bh))
    surf.blit(fs.render(f"體力 {player.stamina}/{player.stamina_max}", True, WHITE),
              (x + bw + 8, y))
    y += bh + gap

    surf.blit(fs.render(
        f"智力: {player.intel}    運氣: {player.luck}    金錢: ${player.money}",
        True, YELLOW), (x, y))
    y += fs.get_height() + gap

    # 滿足感條
    sr = player.satisfaction / 100
    sc = GREEN if sr > 0.6 else (YELLOW if sr > 0.3 else RED)
    pygame.draw.rect(surf, DARK_GRAY, (x, y, bw, bh))
    pygame.draw.rect(surf, sc, (x, y, int(bw * sr), bh))
    surf.blit(fs.render(f"自我滿足度 {player.satisfaction}%", True, WHITE),
              (x + bw + 8, y))
    y += bh + gap

    if player.status_effects:
        eff = "  ".join([f"[{k} {v}週]" for k, v in player.status_effects.items()])
        surf.blit(fs.render(eff, True, RED), (x, y))


def _draw_week_ticker(surf: pygame.Surface,
                      fm,
                      cx: int, cy: int, week: int) -> None:
    """
    橫長條滾輪式週次計數器（取代圓形指針輪盤）。
    三格：左（上週，暗）｜中（本週，高亮）｜右（下週，暗）。
    使用 BLEND_RGB_MULT 做圓柱曲面漸層，不影響透明角落像素。
    """
    fmic = _font_micro[0]
    if fmic is None:
        return

    # ── 版面常數 ──────────────────────────────────────────────
    SIDE_W  = 46    # 左右欄寬（px）
    CTR_W   = 82    # 中央欄寬
    DIV_W   = 2     # 分隔線寬
    H       = 58    # 總高
    TOTAL_W = SIDE_W * 2 + CTR_W + DIV_W * 2   # = 178
    RADIUS  = 10

    sx = cx - TOTAL_W // 2
    sy = cy - H // 2
    outer = pygame.Rect(sx, sy, TOTAL_W, H)

    # ── 在 SRCALPHA Surface 上合成（圓角乾淨，透明角落不受影響）
    ticker = pygame.Surface((TOTAL_W, H), pygame.SRCALPHA)

    # 深色底板（滾輪鼓面）
    pygame.draw.rect(ticker, (35, 20, 8, 252),
                     pygame.Rect(0, 0, TOTAL_W, H), border_radius=RADIUS)

    # 欄位 x 座標
    div1_x = SIDE_W           # 左分隔線起點
    ctr_x  = div1_x + DIV_W  # 中央欄起點
    div2_x = ctr_x  + CTR_W  # 右分隔線起點

    # 中央 aperture 高亮（金黃暈光）
    pygame.draw.rect(ticker, (255, 195, 90, 30),
                     pygame.Rect(ctr_x, 4, CTR_W, H - 8), border_radius=6)

    # ── 三格文字 ──────────────────────────────────────────────
    prev_w = week - 1 if week > 1  else None
    next_w = week + 1 if week < 16 else None

    # 左：上週（fmic 小字，暗棕）
    if prev_w is not None:
        pt = fmic.render(str(prev_w), True, (148, 105, 68))
        ticker.blit(pt, ((SIDE_W - pt.get_width()) // 2,
                          (H      - pt.get_height()) // 2))

    # 中：本週（fm 大字，琥珀金 YELLOW）
    ct = fm.render(f"第{week}週", True, YELLOW)
    ticker.blit(ct, (ctr_x + (CTR_W - ct.get_width()) // 2,
                     (H     - ct.get_height()) // 2))

    # 右：下週（fmic 小字，暗棕）
    if next_w is not None:
        nt = fmic.render(str(next_w), True, (148, 105, 68))
        ticker.blit(nt, (div2_x + DIV_W + (SIDE_W - nt.get_width()) // 2,
                          (H               - nt.get_height()) // 2))

    # 分隔線（文字之後繪製確保清晰）
    pygame.draw.rect(ticker, (90, 60, 34, 255),
                     pygame.Rect(div1_x, 8, DIV_W, H - 16))
    pygame.draw.rect(ticker, (90, 60, 34, 255),
                     pygame.Rect(div2_x, 8, DIV_W, H - 16))

    # ── 圓柱曲面漸層（BLEND_RGB_MULT：暗化上下邊緣，透明角落 RGB=0 不受影響）
    _curve = pygame.Surface((TOTAL_W, H))   # RGB only，無 SRCALPHA
    _curve.fill((255, 255, 255))
    _band = H // 3
    for _i in range(_band):
        _t    = (1.0 - _i / _band) ** 2.3
        _gray = int(255 - 92 * _t)
        pygame.draw.line(_curve, (_gray, _gray, _gray),
                         (0, _i),         (TOTAL_W - 1, _i))
        pygame.draw.line(_curve, (_gray, _gray, _gray),
                         (0, H - 1 - _i), (TOTAL_W - 1, H - 1 - _i))
    ticker.blit(_curve, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # ── 頂部光澤（起點避開圓角透明區）────────────────────────
    _gh = max(3, int(H * 0.28))
    for _i in range(_gh):
        _a = int(62 * (1 - _i / _gh) ** 1.9)
        pygame.draw.line(ticker, (255, 255, 255, _a),
                         (RADIUS, _i), (TOTAL_W - 1 - RADIUS, _i))

    # ── 邊框 ─────────────────────────────────────────────────
    pygame.draw.rect(ticker, (92, 64, 38, 255),
                     pygame.Rect(0, 0, TOTAL_W, H), 2, border_radius=RADIUS)

    # ── 陰影 → 貼圖 ──────────────────────────────────────────
    _soft_shadow(surf, outer, radius=RADIUS, alpha=52, offset=(0, 5))
    surf.blit(ticker, (sx, sy))


def _draw_status_v2(surf, fm, fs, player, rect, mpos):
    """
    新版狀態欄：
      左側：圓形頭像 → 名字/系級/體力條/滿足感條 → 智力/運氣小標籤
      右側：金錢顯示 + 道具店按鈕
    回傳道具店按鈕 Rect。
    """
    # 漸層背景
    if "status" in _grads:
        surf.blit(_grads["status"], rect.topleft)
    else:
        pygame.draw.rect(surf, PANEL, rect)
    pygame.draw.rect(surf, CYAN, rect, 2, border_radius=0)

    if player is None:
        t = fm.render("等待角色資料…", True, GRAY)
        surf.blit(t, (rect.x + 20, rect.y + rect.height // 2 - t.get_height() // 2))
        # 空的道具店按鈕占位
        shop_r = pygame.Rect(rect.right - 130, rect.y + 12, 118, 38)
        pygame.draw.rect(surf, DARK_GRAY, shop_r, border_radius=14)
        return shop_r

    # ── 圓形頭像 ──────────────────────────────────────────────
    av_cx = rect.x + 52
    av_cy = rect.y + 58
    av_r  = 42
    pygame.draw.circle(surf, PANEL, (av_cx, av_cy), av_r)
    pygame.draw.circle(surf, CYAN,  (av_cx, av_cy), av_r, 3)
    init_ch = player.name[0] if player.name else "？"
    init_t  = fm.render(init_ch, True, TITLE)
    surf.blit(init_t, (av_cx - init_t.get_width() // 2,
                       av_cy - init_t.get_height() // 2))

    # ── 名字 + 系級（帶懸浮半透明名字卡）────────────────────
    info_x = rect.x + 106
    info_y = rect.y + 14
    name_t = fm.render(f"【{player.name}】 {player.department}", True, WHITE)
    _fy_nc = _float_offset(amp=3, speed=0.00195, phase=0.8)
    nc_px, nc_py = 10, 5
    nc_r = pygame.Rect(info_x - nc_px,
                       info_y + _fy_nc - nc_py,
                       name_t.get_width() + nc_px * 2,
                       name_t.get_height() + nc_py * 2)
    nc_s = pygame.Surface((nc_r.width, nc_r.height), pygame.SRCALPHA)
    nc_s.fill((255, 255, 255, 68))
    surf.blit(nc_s, nc_r.topleft)
    pygame.draw.rect(surf, CYAN, nc_r, 1, border_radius=8)
    surf.blit(name_t, (info_x, info_y + _fy_nc))

    # ── 體力條 ────────────────────────────────────────────────
    bar_y  = info_y + fm.get_height() + 6
    bar_w  = 300
    bar_h  = 14
    ratio  = player.stamina / max(player.stamina_max, 1)
    pygame.draw.rect(surf, DARK_GRAY, (info_x, bar_y, bar_w, bar_h), border_radius=7)
    pygame.draw.rect(surf, GREEN,     (info_x, bar_y, int(bar_w * ratio), bar_h), border_radius=7)
    pygame.draw.rect(surf, GRAY,      (info_x, bar_y, bar_w, bar_h), 1, border_radius=7)
    stam_t = fs.render(f"體力  {player.stamina}/{player.stamina_max}", True, WHITE)
    surf.blit(stam_t, (info_x + bar_w + 10, bar_y))

    # ── 滿足感條 ──────────────────────────────────────────────
    sat_y  = bar_y + bar_h + 7
    sr_val = player.satisfaction / 100
    sat_c  = GREEN if sr_val > 0.6 else (YELLOW if sr_val > 0.3 else RED)
    pygame.draw.rect(surf, DARK_GRAY, (info_x, sat_y, bar_w, bar_h), border_radius=7)
    pygame.draw.rect(surf, sat_c,     (info_x, sat_y, int(bar_w * sr_val), bar_h), border_radius=7)
    pygame.draw.rect(surf, GRAY,      (info_x, sat_y, bar_w, bar_h), 1, border_radius=7)
    sat_t = fs.render(f"自我滿足度  {player.satisfaction}%", True, WHITE)
    surf.blit(sat_t, (info_x + bar_w + 10, sat_y))

    # ── 狀態效果（若有）───────────────────────────────────────
    eff_y = sat_y + bar_h + 7
    if player.status_effects:
        eff_str = "  ".join(f"[{k} {v}週]" for k, v in player.status_effects.items())
        surf.blit(fs.render(eff_str, True, RED), (info_x, eff_y))

    # ── 智力 / 運氣 小標籤（頭像正下方）─────────────────────
    chip_y = rect.y + 118
    for i, (label, val) in enumerate([("智力", player.intel), ("運氣", player.luck)]):
        chip_x = rect.x + 10 + i * 100
        chip_r = pygame.Rect(chip_x, chip_y, 88, 30)
        pygame.draw.rect(surf, PANEL, chip_r, border_radius=10)
        pygame.draw.rect(surf, CYAN,  chip_r, 1,  border_radius=10)
        ct = fs.render(f"{label}: {val}", True, WHITE)
        surf.blit(ct, (chip_r.x + (chip_r.width  - ct.get_width())  // 2,
                       chip_r.y + (chip_r.height - ct.get_height()) // 2))

    # ── 金錢 + 道具店按鈕（右側）─────────────────────────────
    money_t = fm.render(f"$ {player.money}", True, YELLOW)
    surf.blit(money_t, (rect.right - 140 - money_t.get_width(), rect.y + 18))

    # ── 週次計數器（自我滿足度文字右側 ↔ 金錢左側的空白區域）─
    sat_right   = info_x + bar_w + 10 + sat_t.get_width() + 12
    money_left  = rect.right - 140 - money_t.get_width() - 12
    TICKER_W    = 178          # 與 _draw_week_ticker 中 TOTAL_W 一致
    ticker_cx   = (sat_right + money_left) // 2
    ticker_cy   = rect.y + STATUS_H // 2
    if money_left - sat_right >= TICKER_W + 8:   # 空間夠才畫
        _draw_week_ticker(surf, fm, ticker_cx, ticker_cy, _week[0])

    shop_r = pygame.Rect(rect.right - 130, rect.y + 58, 118, 40)
    hover  = shop_r.collidepoint(mpos)
    dr     = _premium_btn(surf, shop_r, BTN_N, hover, radius=14)
    st     = fm.render("道具店", True, PANEL)
    surf.blit(st, (dr.x + (dr.width  - st.get_width())  // 2,
                   dr.y + (dr.height - st.get_height()) // 2))
    return shop_r


def _draw_log(surf, fs, log, scroll, rect):
    """中間訊息紀錄區。"""
    pygame.draw.rect(surf, BG, rect)
    pygame.draw.rect(surf, GRAY, rect, 1, border_radius=6)

    lh  = fs.get_height() + 3
    vis = rect.height // lh
    end   = max(0, len(log) - scroll)
    start = max(0, end - vis)

    clip = surf.get_clip()
    surf.set_clip(rect)
    for i, line in enumerate(log[start:end]):
        if line.startswith(("⚡", "💥", "📅", "📋", "🎓", "✍")):
            color = YELLOW
        elif line.startswith(("❌", "💀", "😞", "⚠", "💔", "📉")):
            color = RED
        elif line.startswith(("✅", "🌟", "🎉", "✨", "💰", "📚")):
            color = GREEN
        else:
            color = WHITE
        surf.blit(fs.render(_clean(line), True, color),
                  (rect.x + 6, rect.y + i * lh + 4))
    surf.set_clip(clip)


def _draw_input(surf, fm, fs, mode, choices, prompt, tvalue, rect, mpos):
    """下方輸入區：依 mode 顯示按鈕或文字輸入框。"""
    if "input" in _grads:
        surf.blit(_grads["input"], rect.topleft)
    else:
        pygame.draw.rect(surf, PANEL, rect)
    pygame.draw.rect(surf, CYAN, rect, 2, border_radius=10)
    rects = []

    if mode == "choices":
        all_labels = ["0. 返回 / 結束"] + [f"{i+1}. {c}" for i, c in enumerate(choices)]
        cols = 2
        bw   = (rect.width - 20) // cols - 6
        bh   = 36
        px, py = rect.x + 10, rect.y + 10

        for idx, label in enumerate(all_labels):
            c  = idx % cols
            r  = idx // cols
            br = pygame.Rect(px + c * (bw + 6), py + r * (bh + 6), bw, bh)
            rects.append((br, idx))   # 0 = 返回，1..n = 1-based 選擇
            hover = br.collidepoint(mpos)
            col   = BTN_H if hover else (DARK_GRAY if idx == 0 else BTN_N)
            pygame.draw.rect(surf, col, br, border_radius=12)
            pygame.draw.rect(surf, GRAY, br, 1, border_radius=12)
            t = fs.render(label, True, WHITE)
            surf.blit(t, (br.x + (bw - t.get_width()) // 2,
                          br.y + (bh - t.get_height()) // 2))

    elif mode == "yn":
        surf.blit(fm.render(prompt[0], True, WHITE), (rect.x + 10, rect.y + 14))
        for i, (label, val) in enumerate([("是", True), ("否", False)]):
            br = pygame.Rect(rect.x + 10 + i * 130, rect.y + 62, 110, 44)
            rects.append((br, val))
            hover = br.collidepoint(mpos)
            pygame.draw.rect(surf, BTN_H if hover else BTN_N, br, border_radius=12)
            t = fm.render(label, True, WHITE)
            surf.blit(t, (br.x + (110 - t.get_width()) // 2,
                          br.y + (44 - t.get_height()) // 2))

    elif mode == "text":
        surf.blit(fs.render(prompt[0], True, WHITE), (rect.x + 10, rect.y + 12))
        ir = pygame.Rect(rect.x + 10, rect.y + 44, rect.width - 20, 36)
        pygame.draw.rect(surf, MILK, ir, border_radius=10)
        # 已確認文字（深咖啡）+ 組字預覽（暖紫）+ 游標
        t_done = fm.render(tvalue[0], True, BLACK)
        t_comp = fm.render(_composing[0], True, (150, 90, 180)) if _composing[0] else None
        t_cur  = fm.render("|", True, BLACK)
        x_off  = ir.x + 6
        surf.blit(t_done, (x_off, ir.y + 5))
        x_off += t_done.get_width()
        if t_comp:
            surf.blit(t_comp, (x_off, ir.y + 5))
            x_off += t_comp.get_width()
        surf.blit(t_cur, (x_off, ir.y + 5))
        ok = pygame.Rect(rect.x + 10, rect.y + 96, 100, 36)
        hover = ok.collidepoint(mpos)
        pygame.draw.rect(surf, BTN_H if hover else BTN_N, ok, border_radius=12)
        t = fm.render("確認", True, WHITE)
        surf.blit(t, (ok.x + (100 - t.get_width()) // 2,
                      ok.y + (36 - t.get_height()) // 2))
        rects.append((ok, "__ok__"))

    return rects

def _draw_panel(surf, rect, border=CYAN):
    """畫一個帶漸層+圓角框的面板。"""
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)
    pygame.draw.rect(surf, PANEL, rect, border_radius=18)
    pygame.draw.rect(surf, border, rect, 2, border_radius=18)


def _draw_cc_bg(surf: pygame.Surface) -> None:
    """
    在 surf 上繪製角色創建畫面的背景：
      1. 底層：WEBM 影片當前幀（按 FPS 推進，到尾自動回繞）；
         若影片未載入則退回靜態漸層。
      2. 上層：75% 不透明奶茶色→奶白色縱向漸層遮罩，
         讓 UI 卡片在影片上仍保有良好對比。
    """
    # ── 底層：影片 or 靜態漸層 ───────────────────────────────
    cap = _cc_video_cap[0]
    if cap is not None:
        import cv2
        now = pygame.time.get_ticks()
        ms_per_frame = 1000.0 / max(_cc_video_fps[0], 1.0)
        if _cc_video_surf[0] is None or now - _cc_video_last[0] >= ms_per_frame:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fh, fw = frame_rgb.shape[:2]
                vsf = pygame.surfarray.make_surface(
                    frame_rgb.transpose(1, 0, 2))
                if fw != WIN_W or fh != WIN_H:
                    vsf = pygame.transform.scale(vsf, (WIN_W, WIN_H))
                _cc_video_surf[0] = vsf
                _cc_video_last[0] = now
    if _cc_video_surf[0] is not None:
        surf.blit(_cc_video_surf[0], (0, 0))
    elif "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)

    # ── 上層：奶茶↔奶白漸層遮罩（75% 不透明，懶初始化快取）──
    if _cc_overlay_surf[0] is None:
        # 奶茶色 (210,170,128) → 奶白色 (255,250,238)，alpha=191（75%）
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        top_c  = (210, 170, 128, 191)
        bot_c  = (255, 250, 238, 191)
        for _i in range(WIN_H):
            _t = _i / max(WIN_H - 1, 1)
            _r = int(top_c[0] + (bot_c[0] - top_c[0]) * _t)
            _g = int(top_c[1] + (bot_c[1] - top_c[1]) * _t)
            _b = int(top_c[2] + (bot_c[2] - top_c[2]) * _t)
            _a = int(top_c[3] + (bot_c[3] - top_c[3]) * _t)
            pygame.draw.line(ov, (_r, _g, _b, _a), (0, _i), (WIN_W - 1, _i))
        _cc_overlay_surf[0] = ov
    surf.blit(_cc_overlay_surf[0], (0, 0))


def _draw_cc_name(surf, fm, fs, mpos):
    """姓名輸入 modal 卡片，回傳「確認」按鈕 Rect。"""
    _draw_cc_bg(surf)
    # modal card（整張卡緩慢懸浮）
    _fy = _float_offset(amp=7, speed=0.00170, phase=0.3)
    cw, ch = 520, 250
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2 + _fy
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=20, alpha=50, offset=(0, 8))
    pygame.draw.rect(surf, PANEL, card, border_radius=20)
    pygame.draw.rect(surf, CYAN, card, 2, border_radius=20)
    # 標題
    title = fm.render("請輸入角色名字", True, TITLE)
    surf.blit(title, (cx + (cw - title.get_width()) // 2, cy + 24))
    # 輸入框
    ir = pygame.Rect(cx + 30, cy + 80, cw - 60, 42)
    pygame.draw.rect(surf, MILK, ir, border_radius=10)
    t_done = fm.render(_cc_tvalue[0], True, BLACK)
    t_comp = fm.render(_cc_composing[0], True, (150, 90, 180)) if _cc_composing[0] else None
    t_cur  = fm.render("|", True, BLACK)
    xo = ir.x + 8
    surf.blit(t_done, (xo, ir.y + 6)); xo += t_done.get_width()
    if t_comp:
        surf.blit(t_comp, (xo, ir.y + 6)); xo += t_comp.get_width()
    surf.blit(t_cur, (xo, ir.y + 6))
    # 提示
    hint = fs.render("（留空則為「無名大學生」）", True, GRAY)
    surf.blit(hint, (cx + (cw - hint.get_width()) // 2, cy + 138))
    # 確認按鈕
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + 180, 140, 46)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok


def _draw_cc_dept(surf, fm, fs, options, mpos):
    """系級橫向卡片，回傳各卡 (Rect, 1-based idx) 列表。"""
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch = 180, 120
    gap         = 20
    label_h     = fm.get_height() + 22   # pad_y=11 × 2
    TITLE_GAP   = 28
    total_h     = label_h + TITLE_GAP + ch
    top_y       = (WIN_H - total_h) // 2
    sy          = top_y + label_h + TITLE_GAP
    _draw_float_label_card(surf, fm, "選擇系級", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=0.0)
    total_w = len(options) * cw + (len(options) - 1) * gap
    sx = (WIN_W - total_w) // 2
    rects = []
    for i, opt in enumerate(options):
        r     = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover = r.collidepoint(mpos)
        dr    = _premium_btn(surf, r, BTN_N, hover, radius=16)
        t     = fm.render(opt, True, WHITE)
        surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                      dr.y + (dr.height - t.get_height()) // 2))
        rects.append((r, i + 1))
    return rects


def _draw_cc_drawbacks(surf, fm, fs, drawbacks, sel_indices, max_sel, mpos):
    """負面特質切換卡片，回傳 (card_rects, confirm_btn_rect)。"""
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch = 250, 190
    gap           = 24
    title_h       = fm.get_height() + 22   # pad_y=11 × 2
    sub_h         = fs.get_height() + 12   # pad_y=6 × 2
    TITLE_SUB_GAP = 12
    SUB_CARD_GAP  = 18
    CARD_BTN_GAP  = 30
    btn_h         = 48
    total_h       = title_h + TITLE_SUB_GAP + sub_h + SUB_CARD_GAP + ch + CARD_BTN_GAP + btn_h
    top_y         = (WIN_H - total_h) // 2
    sub_y         = top_y + title_h + TITLE_SUB_GAP
    sy            = sub_y + sub_h + SUB_CARD_GAP

    _draw_float_label_card(surf, fm, "選擇負面特質", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=0.5)
    sub_text = f"（最多選 {max_sel} 個，選取可獲得額外點數）"
    _draw_float_label_card(surf, fs, sub_text, WIN_W // 2, sub_y,
                           text_col=GRAY, bg=(30, 20, 8), bg_alpha=115,
                           pad_x=16, pad_y=6, amp=7, speed=0.00170, phase=0.5)

    total_w = len(drawbacks) * cw + (len(drawbacks) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    for i, d in enumerate(drawbacks):
        selected = i in sel_indices
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        bg_col   = (230, 108, 58) if selected else BTN_N
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        # 已選：加黃色外框強調
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        # name
        nt = fm.render(d["name"], True, YELLOW if selected else WHITE)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 14))
        # desc (wrap)
        desc_lines = _wrap(d["desc"], fs, cw - 20)
        for li, dl in enumerate(desc_lines):
            dt = fs.render(dl, True, WHITE)
            surf.blit(dt, (dr.x + 10, dr.y + 52 + li * (fs.get_height() + 3)))
        # bonus pts
        pt = fs.render(f"＋{d['bonus_pts']} 點", True, GREEN)
        surf.blit(pt, (dr.x + (dr.width - pt.get_width()) // 2, dr.y + ch - 38))
        card_rects.append((r, i))
    # 確認按鈕
    ok    = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認選擇", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return card_rects, ok


def _draw_cc_stats(surf, fm, fs, total, vals, raw, active, mpos):
    """能力點分配畫面，回傳 (minus_rects, plus_rects, confirm_rect)。"""
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    btn_sz       = 38
    box_w, box_h = 90, 38
    title_h      = fm.get_height() + 22   # pad_y=11 × 2
    sub_h        = fs.get_height() + 12   # pad_y=6 × 2
    TITLE_SUB_GAP = 12
    SUB_ROW_GAP  = 22
    ROW_GAP      = 14
    ROWS_BTN_GAP = 26
    btn_h        = 48
    n_rows       = 3
    rows_h       = n_rows * box_h + (n_rows - 1) * ROW_GAP
    total_h      = title_h + TITLE_SUB_GAP + sub_h + SUB_ROW_GAP + rows_h + ROWS_BTN_GAP + btn_h
    top_y        = (WIN_H - total_h) // 2
    sub_y        = top_y + title_h + TITLE_SUB_GAP
    row_start_y  = sub_y + sub_h + SUB_ROW_GAP
    row_y        = [row_start_y + i * (box_h + ROW_GAP) for i in range(n_rows)]
    ok_y         = row_y[-1] + box_h + ROWS_BTN_GAP

    used = sum(vals)
    rem  = total - used
    _draw_float_label_card(surf, fm, "分配能力點", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=1.0)
    info_text = f"可用點數：{total}   已用：{used}   剩餘：{rem}   初始金錢 +{rem * 10} 元"
    _draw_float_label_card(surf, fs, info_text, WIN_W // 2, sub_y,
                           text_col=YELLOW, bg=(30, 15, 0), bg_alpha=128,
                           pad_x=16, pad_y=6, amp=7, speed=0.00170, phase=1.0)

    labels = ["體力", "智力", "運氣"]
    cx     = WIN_W // 2
    minus_rects = []
    plus_rects  = []

    # 更新輸入框 Rect 快取（與事件處理對齊）
    _cc_btn_cache["stats_boxes"] = [pygame.Rect(cx - 82, ry, box_w, box_h) for ry in row_y]

    for i, (label, ry) in enumerate(zip(labels, row_y)):
        # label
        lt = fm.render(label, True, WHITE)
        surf.blit(lt, (cx - 230, ry + (box_h - lt.get_height()) // 2))
        # [-]
        mr    = pygame.Rect(cx - 130, ry, btn_sz, btn_sz)
        hover = mr.collidepoint(mpos)
        mr_dr = _premium_btn(surf, mr, BTN_N, hover, radius=10)
        mt    = fm.render("－", True, WHITE)
        surf.blit(mt, (mr_dr.x + (mr_dr.width  - mt.get_width())  // 2,
                       mr_dr.y + (mr_dr.height - mt.get_height()) // 2))
        minus_rects.append(mr)
        # input box（帶焦點高光陰影）
        bdr_col = YELLOW if active == i else CYAN
        ir      = pygame.Rect(cx - 82, ry, box_w, box_h)
        if active == i:
            _soft_shadow(surf, ir, radius=10, alpha=35, offset=(1, 2), spread=3)
        pygame.draw.rect(surf, MILK, ir, border_radius=10)
        pygame.draw.rect(surf, bdr_col, ir, 2, border_radius=10)
        display = raw[i] if active == i else str(vals[i])
        vt = fm.render(display, True, BLACK)
        surf.blit(vt, (ir.x + (box_w - vt.get_width()) // 2, ir.y + (box_h - vt.get_height()) // 2))
        # [+]
        pr    = pygame.Rect(cx + 20, ry, btn_sz, btn_sz)
        hover = pr.collidepoint(mpos)
        pr_dr = _premium_btn(surf, pr, BTN_N, hover, radius=10)
        pt    = fm.render("＋", True, WHITE)
        surf.blit(pt, (pr_dr.x + (pr_dr.width  - pt.get_width())  // 2,
                       pr_dr.y + (pr_dr.height - pt.get_height()) // 2))
        plus_rects.append(pr)

    # 確認
    ok          = pygame.Rect((WIN_W - 160) // 2, ok_y, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = rem >= 0
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fm.render("確認分配", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return minus_rects, plus_rects, ok


def _draw_cc_talent(surf, fm, fs, candidates, sel_idx, mpos):
    """天賦卡片（單選），回傳 (card_rects, confirm_rect)。"""
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch = 250, 200
    gap          = 24
    label_h      = fm.get_height() + 22   # pad_y=11 × 2
    TITLE_GAP    = 28
    CARD_BTN_GAP = 30
    btn_h        = 48
    total_h      = label_h + TITLE_GAP + ch + CARD_BTN_GAP + btn_h
    top_y        = (WIN_H - total_h) // 2
    sy           = top_y + label_h + TITLE_GAP

    _draw_float_label_card(surf, fm, "選擇天賦", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=1.5)

    total_w = len(candidates) * cw + (len(candidates) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    for i, t_data in enumerate(candidates):
        selected = (i == sel_idx)
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        bg_col   = (110, 72, 36) if selected else BTN_N
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        nt = fm.render(t_data["name"], True, YELLOW if selected else WHITE)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 18))
        desc_lines = _wrap(t_data["desc"], fs, cw - 20)
        for li, dl in enumerate(desc_lines):
            dt = fs.render(dl, True, WHITE)
            surf.blit(dt, (dr.x + 10, dr.y + 60 + li * (fs.get_height() + 4)))
        card_rects.append((r, i))
    # 確認按鈕
    ok          = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = sel_idx is not None
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fm.render("確認選擇", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return card_rects, ok


def _handle_cc_action(ev_pos):
    """
    處理 char_create 階段的滑鼠點擊事件。
    修改全域 _cc_* 狀態；若步驟完成則呼叫 _cc_reply_event.set()。
    """
    mode = _cc_mode[0]
    data = _cc_data[0]

    if mode == "name":
        # 依賴 _cc_btn_cache 中暫存的按鈕 Rect（由繪製函式寫入）
        ok = _cc_btn_cache.get("name_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = _cc_tvalue[0]
            _cc_mode[0] = ""
            pygame.key.stop_text_input()
            _cc_reply_event.set()

    elif mode == "dept":
        for (r, idx) in (_cc_btn_cache.get("dept_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_reply_val[0] = idx
                _cc_mode[0] = ""
                _cc_reply_event.set()
                return

    elif mode == "drawbacks":
        max_sel = _cc_btn_cache.get("drawbacks_max", 2)
        for (r, idx) in (_cc_btn_cache.get("drawback_cards") or []):
            if r.collidepoint(ev_pos):
                if idx in _cc_sel:
                    _cc_sel.remove(idx)
                elif len(_cc_sel) < max_sel:
                    _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("drawbacks_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = [data[i] for i in _cc_sel]
            _cc_mode[0] = ""
            _cc_reply_event.set()

    elif mode == "stats":
        total = _cc_stat_total[0]
        # [-] 按鈕
        for i, r in enumerate(_cc_btn_cache.get("stats_minus") or []):
            if r.collidepoint(ev_pos):
                if _cc_stat_vals[i] > 0:
                    _cc_stat_vals[i] -= 1
                    _cc_stat_raw[i] = str(_cc_stat_vals[i])
                _cc_active_stat[0] = None
                return
        # [+] 按鈕
        for i, r in enumerate(_cc_btn_cache.get("stats_plus") or []):
            if r.collidepoint(ev_pos):
                if sum(_cc_stat_vals) < total:
                    _cc_stat_vals[i] += 1
                    _cc_stat_raw[i] = str(_cc_stat_vals[i])
                _cc_active_stat[0] = None
                return
        # 輸入框焦點（依位置判斷）
        for i, r in enumerate(_cc_btn_cache.get("stats_boxes") or []):
            if r.collidepoint(ev_pos):
                _cc_active_stat[0] = i
                _cc_stat_raw[i] = ""
                return
        # 確認按鈕
        ok = _cc_btn_cache.get("stats_ok")
        if ok and ok.collidepoint(ev_pos):
            if sum(_cc_stat_vals) <= total:
                _cc_reply_val[0] = tuple(_cc_stat_vals)
                _cc_mode[0] = ""
                _cc_active_stat[0] = None
                _cc_reply_event.set()

    elif mode == "talent":
        for (r, idx) in (_cc_btn_cache.get("talent_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_sel.clear()
                _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("talent_ok")
        if ok and ok.collidepoint(ev_pos):
            if _cc_sel:
                _cc_reply_val[0] = data[_cc_sel[0]]
                _cc_mode[0] = ""
                _cc_reply_event.set()


# 繪製函式暫存按鈕 Rect，供事件處理使用（僅主執行緒存取）
_cc_btn_cache: dict = {}


# 標準行動名稱集合（用來判斷是否顯示圓形按鈕）
_STANDARD_ACTIONS = {"認真讀書", "正常上課", "社團活動", "打工賺錢",
                     "好好休息", "幫助朋友", "🏪 前往道具店"}

# 各行動的體力消耗說明 + 預期效果（用於 hover 提示列）
_ACTION_INFO = {
    "認真讀書": ("消耗體力 4", "課業熟練度 +8    自我滿足度 -5"),
    "正常上課": ("消耗體力 2", "課業熟練度 +4    課堂參與度 +5"),
    "社團活動": ("消耗體力 3", "自我滿足度 +10"),
    "打工賺錢": ("消耗體力 4", "金錢 +150    自我滿足度 +3"),
    "好好休息": ("恢復體力 6", "自我滿足度 +8"),
    "幫助朋友": ("消耗體力 2", "自我滿足度 +12"),
}


def _draw_action_popup(surf, fs):
    """
    在遊戲畫面右側繪製由右而左滑入的行動結果視窗。
    特殊前綴：
      "! " → 警示行（紅色，加上小分隔線）
      "---" → 分隔線
    使用 _popup_t0[0] 與 _popup_lines 驅動動畫，由 run_ui 每幀呼叫。

    注意：繪製前設定 clip 至遊戲邊界 (WIN_W, WIN_H)，防止全螢幕模式下
    Surface 尺寸大於邏輯解析度時，動畫滑出位置超過右邊界並殘留上幀像素。
    """
    if _popup_t0[0] == 0 or not _popup_lines:
        return

    elapsed = pygame.time.get_ticks() - _popup_t0[0]
    if elapsed >= POPUP_DURATION:
        _popup_t0[0] = 0
        return

    # ── 限制繪製區域於遊戲邊界內（全螢幕 bug 防護）──────────
    _old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(0, 0, WIN_W, WIN_H))

    POPUP_W = 250
    lh      = fs.get_height() + 5
    SEP_H   = 10   # 分隔線高度（含上下空隙）

    # ── 預先展開所有行（支援自動換行）以計算總高度 ──────────
    title_h = fs.get_height() + 10
    rows    = []   # list of ("text", color) | ("sep",) | ("warn_sep",)
    for raw in _popup_lines:
        if raw == "---":
            rows.append(("sep",))
        elif raw.startswith("! "):
            display = raw[2:]
            rows.append(("warn_sep",))
            for wl in _wrap(display, fs, POPUP_W - 28):
                rows.append((wl, RED))
        else:
            if "+" in raw:
                col = GREEN
            elif "-" in raw:
                col = RED
            else:
                col = WHITE
            for wl in _wrap(raw, fs, POPUP_W - 28):
                rows.append((wl, col))

    ph = (title_h + 4
          + sum(SEP_H if r[0] in ("sep", "warn_sep") else lh for r in rows)
          + 14)

    # ── x 位置動畫 ─────────────────────────────────────────
    target_x = WIN_W - POPUP_W - 16
    if elapsed < POPUP_IN_MS:
        t  = elapsed / POPUP_IN_MS
        t2 = 1 - (1 - t) ** 3
        x  = WIN_W - int(t2 * (POPUP_W + 16))
    elif elapsed > POPUP_DURATION - POPUP_OUT_MS:
        t  = (elapsed - (POPUP_DURATION - POPUP_OUT_MS)) / POPUP_OUT_MS
        t2 = t * t
        x  = target_x + int(t2 * (POPUP_W + 32))
    else:
        x  = target_x

    y     = STATUS_H + (CHAR_H - ph) // 2
    pop_r = pygame.Rect(x, y, POPUP_W, ph)

    # ── 繪製面板 ───────────────────────────────────────────
    _soft_shadow(surf, pop_r, radius=12, alpha=60, offset=(4, 6), spread=5)
    pygame.draw.rect(surf, PANEL, pop_r, border_radius=12)
    pygame.draw.rect(surf, CYAN,  pop_r, 2, border_radius=12)
    _gloss_rect(surf, pop_r)

    # 標題列
    ty = pop_r.y + 8
    title_t = fs.render(_popup_title[0], True, TITLE)
    surf.blit(title_t, (pop_r.x + (POPUP_W - title_t.get_width()) // 2, ty))
    ty += title_t.get_height() + 4
    pygame.draw.line(surf, DARK_GRAY,
                     (pop_r.x + 12, ty), (pop_r.right - 12, ty), 1)
    ty += 6

    # 結果行
    for row in rows:
        if row[0] in ("sep", "warn_sep"):
            ty += SEP_H // 2
            pygame.draw.line(surf, DARK_GRAY,
                             (pop_r.x + 12, ty), (pop_r.right - 12, ty), 1)
            ty += SEP_H // 2
        else:
            text, col = row
            lt = fs.render(text, True, col)
            surf.blit(lt, (pop_r.x + 14, ty))
            ty += lh

    # ── 恢復原始 clip（避免影響後續繪製）────────────────────
    surf.set_clip(_old_clip)


def _draw_action_panel(surf, fm, fs, mode, choices, log, prompt, tvalue, rect, time_left, mpos):
    """
    新版底部面板。
    rect: 整個底部區域（含 TAB_H 標籤列）
    回傳 (content_rects, end_week_btn)
    """
    # ── 面板背景 ─────────────────────────────────────────────
    if "input" in _grads:
        surf.blit(_grads["input"], rect.topleft)
    else:
        pygame.draw.rect(surf, PANEL, rect)
    pygame.draw.rect(surf, CYAN, rect, 2, border_radius=0)

    # ── 標籤列 ───────────────────────────────────────────────
    tab_rect    = pygame.Rect(rect.x, rect.y, rect.width, TAB_H)
    content_top = rect.y + TAB_H

    # ── 預先計算 hover 狀態（供標籤列 tooltip 使用）─────────
    is_std_action = (mode == "choices" and
                     all(c in _STANDARD_ACTIONS for c in choices))
    hovered_action = None
    if is_std_action:
        action_choices_pre = [c for c in choices if c != "🏪 前往道具店"]
        n_pre    = len(action_choices_pre)
        r_pre    = 36
        sp_pre   = min(140, (rect.width - 40) // max(n_pre, 1))
        sx_pre   = rect.x + (rect.width - n_pre * sp_pre) // 2 + sp_pre // 2
        cy_pre   = content_top + r_pre + ((rect.height - TAB_H - r_pre * 2 - fs.get_height() - 8) // 2)
        for i, lbl in enumerate(action_choices_pre):
            cx_i = sx_pre + i * sp_pre
            if pygame.Rect(cx_i - r_pre - 8, cy_pre - r_pre - 8,
                           (r_pre + 8) * 2, (r_pre + 8) * 2).collidepoint(mpos):
                hovered_action = lbl
                break

    # 左側：剩餘時間點
    time_txt = fs.render(f"剩餘時間點：{time_left}", True, WHITE)
    surf.blit(time_txt, (tab_rect.x + 14, tab_rect.y + (TAB_H - time_txt.get_height()) // 2))

    # 中間：行動 hover 提示（體力消耗 + 預期效果）
    if hovered_action and hovered_action in _ACTION_INFO:
        cost_str, eff_str = _ACTION_INFO[hovered_action]
        is_restore = cost_str.startswith("恢復")
        cost_col   = GREEN if is_restore else RED
        tip_x = tab_rect.x + 14 + time_txt.get_width() + 24
        tip_y = tab_rect.y + (TAB_H - fs.get_height()) // 2
        cost_t = fs.render(cost_str, True, cost_col)
        surf.blit(cost_t, (tip_x, tip_y))
        sep_x  = tip_x + cost_t.get_width() + 10
        sep_t  = fs.render("|", True, GRAY)
        surf.blit(sep_t, (sep_x, tip_y))
        eff_t  = fs.render(eff_str, True, YELLOW)
        surf.blit(eff_t, (sep_x + sep_t.get_width() + 10, tip_y))

    # 右側：結束本週按鈕
    ew_btn   = pygame.Rect(rect.right - 110, tab_rect.y + 4, 100, TAB_H - 8)
    ew_hover = ew_btn.collidepoint(mpos)
    ew_dr    = _premium_btn(surf, ew_btn, DARK_GRAY, ew_hover, radius=10)
    ew_t     = fs.render("結束本週", True, WHITE)
    surf.blit(ew_t, (ew_dr.x + (ew_dr.width  - ew_t.get_width())  // 2,
                     ew_dr.y + (ew_dr.height - ew_t.get_height()) // 2))

    # 分隔線
    pygame.draw.line(surf, GRAY, (rect.x, content_top), (rect.right, content_top), 1)

    content_rect = pygame.Rect(rect.x, content_top, rect.width, rect.height - TAB_H)
    content_rects = []

    # ── 內容區：依模式切換 ────────────────────────────────────

    if mode == "choices" and is_std_action:
        # ── 圓形行動按鈕（縮小 + 標籤移至按鈕下方）─────────
        action_choices = [c for c in choices if c != "🏪 前往道具店"]
        n       = len(action_choices)
        r       = 36
        spacing = min(140, (rect.width - 40) // max(n, 1))
        total_w = n * spacing
        sx      = rect.x + (rect.width - total_w) // 2 + spacing // 2
        # 垂直：圓心上移，留空間給下方標籤
        lh      = fs.get_height()
        cy_btn  = content_top + r + ((content_rect.height - r * 2 - lh - 8) // 2)

        for i, label in enumerate(action_choices):
            cx_btn   = sx + i * spacing
            orig_idx = choices.index(label) + 1
            hover    = pygame.Rect(cx_btn - r - 8, cy_btn - r - 8,
                                   (r + 8) * 2, (r + 8) * 2).collidepoint(mpos)
            ar       = _premium_circle(surf, cx_btn, cy_btn, r,
                                       BTN_N, hover, key=(cx_btn, cy_btn))
            brect    = pygame.Rect(cx_btn - ar, cy_btn - ar, ar * 2, ar * 2)
            # 標籤顯示在按鈕正下方（文字移出按鈕外）
            clean_label = label.replace("🏪 ", "")
            lt = fs.render(clean_label, True, WHITE)
            surf.blit(lt, (cx_btn - lt.get_width() // 2, cy_btn + r + 6))
            content_rects.append((brect, orig_idx))

    elif mode == "choices" and not is_std_action:
        # ── 非標準選項：上方顯示最新 log（題目文字），下方按鈕作答 ──
        LOG_LINES = 3
        lh_log    = fs.get_height() + 4
        log_h     = LOG_LINES * lh_log + 6
        log_area  = pygame.Rect(content_rect.x, content_rect.y,
                                content_rect.width, log_h)
        _draw_panel_log(surf, fs, log, log_area, lines=LOG_LINES)

        # 按鈕區從 log 下方開始
        bw   = (rect.width - 36) // 2 - 6
        bh   = 40
        px   = rect.x + 12
        py   = content_top + log_h + 6
        for i, label in enumerate(choices):
            col = i % 2
            row = i // 2
            br    = pygame.Rect(px + col * (bw + 12), py + row * (bh + 8), bw, bh)
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
            lt    = fs.render(label, True, PANEL)
            surf.blit(lt, (dr.x + (dr.width  - lt.get_width())  // 2,
                           dr.y + (dr.height - lt.get_height()) // 2))
            content_rects.append((br, i + 1))

    elif mode == "yn":
        # ── prompt 提示 + 是 / 否 按鈕 + 最新 log ────────────
        BTN_H2, BTN_W2, BTN_SP = 44, 128, 14
        btn_y   = content_top + content_rect.height - BTN_H2 - 8
        prompt_y = btn_y - fs.get_height() - 8
        _draw_panel_log(surf, fs, log, content_rect, lines=2)
        # prompt 文字（紅色，顯示於按鈕正上方）
        if prompt[0]:
            for j, pln in enumerate(_wrap(prompt[0], fs, content_rect.width - 28)):
                pt = fs.render(pln, True, RED)
                surf.blit(pt, (rect.x + 14,
                               prompt_y - (len(_wrap(prompt[0], fs, content_rect.width - 28)) - 1 - j)
                               * (fs.get_height() + 3)))
        for i, (label, val) in enumerate([(_yn_labels[1], False), (_yn_labels[0], True)]):
            br    = pygame.Rect(rect.x + 14 + i * (BTN_W2 + BTN_SP), btn_y, BTN_W2, BTN_H2)
            hover = br.collidepoint(mpos)
            col_b = BTN_N if val else DARK_GRAY
            dr    = _premium_btn(surf, br, col_b, hover, radius=12)
            lt    = fm.render(label, True, PANEL)
            surf.blit(lt, (dr.x + (dr.width  - lt.get_width())  // 2,
                           dr.y + (dr.height - lt.get_height()) // 2))
            content_rects.append((br, val))

    elif mode == "text":
        # ── 文字輸入框 ────────────────────────────────────────
        _draw_panel_log(surf, fs, log, content_rect, lines=2)
        surf.blit(fs.render(prompt[0], True, GRAY),
                  (rect.x + 14, content_top + content_rect.height - 88))
        ir2 = pygame.Rect(rect.x + 14, content_top + content_rect.height - 64, rect.width - 140, 36)
        pygame.draw.rect(surf, MILK, ir2, border_radius=10)
        t_done = fm.render(tvalue[0], True, BLACK)
        t_comp = fm.render(_composing[0], True, (150, 90, 180)) if _composing[0] else None
        t_cur  = fm.render("|", True, BLACK)
        xo = ir2.x + 8
        surf.blit(t_done, (xo, ir2.y + 5)); xo += t_done.get_width()
        if t_comp:
            surf.blit(t_comp, (xo, ir2.y + 5)); xo += t_comp.get_width()
        surf.blit(t_cur, (xo, ir2.y + 5))
        ok    = pygame.Rect(rect.right - 118, ir2.y, 104, 36)
        ok_dr = _premium_btn(surf, ok, BTN_N, ok.collidepoint(mpos), radius=12)
        ot    = fm.render("確認", True, PANEL)
        surf.blit(ot, (ok_dr.x + (ok_dr.width  - ot.get_width())  // 2,
                       ok_dr.y + (ok_dr.height - ot.get_height()) // 2))
        content_rects.append((ok, "__ok__"))

    else:
        # ── 敘述模式（mode == None）：顯示最新 log ────────────
        _draw_panel_log(surf, fs, log, content_rect, lines=6)

    return content_rects, ew_btn


def _draw_panel_log(surf, fs, log, rect, lines=5):
    """在 rect 內顯示 log 最後 N 行（敘述模式輔助函式）。"""
    lh   = fs.get_height() + 4
    show = log[-(lines):]
    for i, line in enumerate(show):
        if line.startswith(("⚡", "💥", "📅", "📋", "🎓", "✍")):
            col = YELLOW
        elif line.startswith(("❌", "💀", "😞", "⚠", "💔", "📉")):
            col = RED
        elif line.startswith(("✅", "🌟", "🎉", "✨", "💰", "📚")):
            col = GREEN
        else:
            col = WHITE
        surf.blit(fs.render(_clean(line), True, col),
                  (rect.x + 14, rect.y + 8 + i * lh))


def _draw_character_art(surf, rect):
    """
    人物立繪占位（純幾何圖形，之後可替換為圖片）。
    在 rect 區域內繪製一個可愛的簡單角色。
    """
    cx = rect.centerx
    # 陰影橢圓（地面感）
    pygame.draw.ellipse(surf, (220, 200, 175),
                        (cx - 55, rect.bottom - 22, 110, 18))

    # ── 身體（裙子：梯形用 polygon）─────────────────────────
    body_top_y  = rect.y + 148
    body_bot_y  = rect.bottom - 22
    skirt_t_w   = 54
    skirt_b_w   = 110
    skirt_pts   = [
        (cx - skirt_t_w // 2, body_top_y),
        (cx + skirt_t_w // 2, body_top_y),
        (cx + skirt_b_w // 2, body_bot_y),
        (cx - skirt_b_w // 2, body_bot_y),
    ]
    pygame.draw.polygon(surf, BTN_H, skirt_pts)
    pygame.draw.polygon(surf, CYAN,  skirt_pts, 2)

    # 裙子腰帶
    waist_r = pygame.Rect(cx - 30, body_top_y - 6, 60, 14)
    pygame.draw.rect(surf, BTN_N, waist_r, border_radius=7)

    # 上衣（圓角矩形）
    top_r = pygame.Rect(cx - 28, rect.y + 100, 56, 52)
    pygame.draw.rect(surf, MILK, top_r, border_radius=8)
    pygame.draw.rect(surf, CYAN, top_r, 2, border_radius=8)

    # 衣領小V
    collar_pts = [(cx, rect.y + 108), (cx - 10, rect.y + 100), (cx + 10, rect.y + 100)]
    pygame.draw.polygon(surf, BTN_H, collar_pts)

    # 手臂（左右各一個小圓角矩形）
    for side in (-1, 1):
        arm_r = pygame.Rect(cx + side * 32 - 10, rect.y + 105, 18, 44)
        pygame.draw.rect(surf, MILK, arm_r, border_radius=9)
        pygame.draw.rect(surf, CYAN, arm_r, 1, border_radius=9)

    # ── 頸部 ─────────────────────────────────────────────────
    pygame.draw.rect(surf, MILK, (cx - 9, rect.y + 74, 18, 28), border_radius=5)

    # ── 頭部（圓形）─────────────────────────────────────────
    head_cx, head_cy, head_r = cx, rect.y + 62, 42
    pygame.draw.circle(surf, MILK, (head_cx, head_cy), head_r)
    pygame.draw.circle(surf, CYAN, (head_cx, head_cy), head_r, 2)

    # ── 頭髮（深棕弧形蓋在頭上）─────────────────────────────
    hair_col = (140, 88, 40)
    # 後髮（先畫，在頭後面）
    pygame.draw.ellipse(surf, hair_col,
                        (head_cx - 46, head_cy - head_r - 2, 92, 54))
    # 前劉海（蓋在頭前）
    pygame.draw.ellipse(surf, hair_col,
                        (head_cx - 40, head_cy - head_r - 4, 80, 36))
    # 兩側長髮（細長橢圓）
    for side in (-1, 1):
        pygame.draw.ellipse(surf, hair_col,
                            (head_cx + side * 30, head_cy - 10, 20, 68))

    # ── 臉部 ─────────────────────────────────────────────────
    # 眼睛（橢圓）
    for ex in (head_cx - 14, head_cx + 14):
        pygame.draw.ellipse(surf, WHITE, (ex - 7, head_cy - 8, 14, 10))
        pygame.draw.ellipse(surf, (50, 30, 10), (ex - 4, head_cy - 6, 8, 7))  # 瞳孔
    # 腮紅
    for ex in (head_cx - 18, head_cx + 12):
        blush = pygame.Surface((18, 10), pygame.SRCALPHA)
        blush.fill((255, 180, 160, 100))
        surf.blit(blush, (ex, head_cy + 2))
    # 微笑嘴巴
    pygame.draw.arc(surf, (210, 120, 100),
                    (head_cx - 10, head_cy + 6, 20, 12),
                    3.14, 0, 2)

    # ── 裝飾：頭上小蝴蝶結 ─────────────────────────────────
    bow_cx, bow_cy = head_cx + 24, head_cy - head_r + 4
    for dx in (-10, 10):
        bow_pts = [
            (bow_cx,      bow_cy),
            (bow_cx + dx, bow_cy - 8),
            (bow_cx + dx, bow_cy + 8),
        ]
        pygame.draw.polygon(surf, RED, bow_pts)
    pygame.draw.circle(surf, YELLOW, (bow_cx, bow_cy), 5)


def _draw_modal_overlay(surf):
    """在畫面上覆蓋一層半透明暗幕，突顯 modal。"""
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill((80, 50, 20, 110))   # 暖棕半透明遮罩（比純黑更有溫度）
    surf.blit(overlay, (0, 0))


def _draw_modal_timetable(surf, fm, fs, courses, mpos):
    """
    課表彈出 modal。
    courses: [{"name":str, "day":str, "time":str, "credits":int}, ...]
    回傳「確認」按鈕 Rect。
    """
    _draw_modal_overlay(surf)
    cw, ch = 560, min(120 + len(courses) * 34 + 70, WIN_H - 80)
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=20, alpha=80, offset=(4, 8), spread=8)
    pygame.draw.rect(surf, PANEL, card, border_radius=20)
    pygame.draw.rect(surf, CYAN, card, 2, border_radius=20)

    # 標題
    title = fm.render("本週課表", True, TITLE)
    surf.blit(title, (cx + (cw - title.get_width()) // 2, cy + 18))

    # 分隔線
    pygame.draw.line(surf, GRAY,
                     (cx + 20, cy + 52), (cx + cw - 20, cy + 52), 1)

    # 欄位標頭
    col_x = [cx + 20, cx + 100, cx + 210, cx + 330, cx + 430]
    headers = ["", "課程名稱", "時間", "學分", ""]
    # 簡化為三欄：星期 / 課名 / 時間+學分
    col_x2 = [cx + 20, cx + 90, cx + 280, cx + 420]
    hdr_labels = ["星期", "課程名稱", "上課時間", "學分"]
    for i, h in enumerate(hdr_labels):
        ht = fs.render(h, True, YELLOW)
        surf.blit(ht, (col_x2[i], cy + 58))

    # 課程列表
    row_y = cy + 82
    for course in courses:
        day_t  = fs.render(course.get("day", ""), True, WHITE)
        name_t = fs.render(course.get("name", ""), True, WHITE)
        time_t = fs.render(course.get("time", ""), True, GRAY)
        cred_t = fs.render(str(course.get("credits", "")), True, GREEN)
        surf.blit(day_t,  (col_x2[0], row_y))
        surf.blit(name_t, (col_x2[1], row_y))
        surf.blit(time_t, (col_x2[2], row_y))
        surf.blit(cred_t, (col_x2[3], row_y))
        row_y += 34

    # 確認按鈕
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + ch - 56, 140, 44)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok


def _draw_modal_grade(surf, fm, fl, fs, items, mpos):
    """
    成績公告彈出 modal。
    items: [{"name":str, "score": int|float}, ...]
    回傳「確認」按鈕 Rect。
    """
    _draw_modal_overlay(surf)
    cw, ch = 420, 100 + len(items) * 80 + 80
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=20, alpha=80, offset=(4, 8), spread=8)
    pygame.draw.rect(surf, PANEL, card, border_radius=20)
    pygame.draw.rect(surf, YELLOW, card, 2, border_radius=20)

    # 標題
    title = fm.render("成績公告", True, YELLOW)
    surf.blit(title, (cx + (cw - title.get_width()) // 2, cy + 18))
    pygame.draw.line(surf, GRAY,
                     (cx + 20, cy + 52), (cx + cw - 20, cy + 52), 1)

    row_y = cy + 66
    for item in items:
        score = item["score"]
        score_str = f"{score:.0f} 分" if isinstance(score, float) else f"{score} 分"
        # 分數顏色
        if isinstance(score, (int, float)) and score >= 80:
            sc = GREEN
        elif isinstance(score, (int, float)) and score >= 60:
            sc = YELLOW
        else:
            sc = RED
        name_t  = fm.render(item["name"], True, WHITE)
        score_t = fl.render(score_str, True, sc)
        surf.blit(name_t,  (cx + 30, row_y))
        surf.blit(score_t, (cx + cw - score_t.get_width() - 30, row_y - 6))
        pygame.draw.line(surf, DARK_GRAY,
                         (cx + 20, row_y + 60), (cx + cw - 20, row_y + 60), 1)
        row_y += 80

    # 確認按鈕
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + ch - 56, 140, 44)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok


def _draw_start(surf, fm, fl, mpos):
    """開始畫面：遊戲標題 + 開始遊戲按鈕，回傳按鈕 Rect。"""
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)

    # ── 懸浮偏移（標題卡 + 按鈕同步浮動）────────────────────
    _fy = _float_offset(amp=9, speed=0.00155)

    # ── 標題區半透明底板（確保圖片背景上文字可讀）─────────
    card_w, card_h = 520, 190
    card_x = (WIN_W - card_w) // 2
    card_y = WIN_H // 3 - 40 + _fy
    _soft_shadow(surf, pygame.Rect(card_x, card_y, card_w, card_h),
                 radius=18, alpha=55, offset=(0, 8))
    card_s = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
    card_s.fill((20, 10, 5, 148))   # 深棕半透明
    surf.blit(card_s, (card_x, card_y))
    pygame.draw.rect(surf, CYAN, (card_x, card_y, card_w, card_h),
                     2, border_radius=18)
    _gloss_rect(surf, pygame.Rect(card_x, card_y, card_w, card_h))

    # 標題
    title = fl.render("如何渡過這學期？", True, (255, 255, 255))
    surf.blit(title, ((WIN_W - title.get_width()) // 2, card_y + 24))
    # 副標
    sub = fm.render("一款大學生存模擬遊戲", True, (255, 230, 140))
    surf.blit(sub, ((WIN_W - sub.get_width()) // 2,
                    card_y + 24 + fl.get_height() + 16))

    # ── 按鈕（與標題卡同步浮動）──────────────────────────
    btn   = pygame.Rect((WIN_W - 220) // 2, WIN_H // 2 + 68 + _fy, 220, 56)
    hover = btn.collidepoint(mpos)
    dr    = _premium_btn(surf, btn, BTN_N, hover, radius=16)
    t     = fm.render("開始遊戲", True, (255, 255, 255))
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return btn


def _draw_end(surf, fm, fs, lr, mpos):
    """結束畫面：保留 log（可看最終成績）+ 再來一次按鈕。"""
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)
    # 沿用 log 區，讓玩家還能看到最終成績
    _draw_log(surf, fs, _log, _scroll[0], lr)
    # 下方面板
    ir = pygame.Rect(0, lr.y + lr.height, WIN_W, WIN_H - lr.y - lr.height)
    if "input" in _grads:
        surf.blit(_grads["input"], ir.topleft)
    else:
        pygame.draw.rect(surf, PANEL, ir)
    pygame.draw.rect(surf, CYAN, ir, 2, border_radius=10)
    title = fm.render("學期結束！感謝遊玩《如何渡過這學期？》", True, YELLOW)
    surf.blit(title, ((WIN_W - title.get_width()) // 2, ir.y + 14))
    # 按鈕
    btn   = pygame.Rect((WIN_W - 220) // 2, ir.y + 60, 220, 50)
    hover = btn.collidepoint(mpos)
    dr    = _premium_btn(surf, btn, BTN_N, hover, radius=16)
    t     = fm.render("再來一次", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return btn


# ─────────────────────────────────────────
#  道具店：輔助函式 + 繪製
# ─────────────────────────────────────────

def _item_icon_color(item: dict) -> tuple:
    """依道具效果類型回傳圖示圓形底色。"""
    if "stamina_restore"   in item: return GREEN
    if "intel_gain"        in item: return CYAN
    if "luck_gain"         in item: return YELLOW
    if "satisfaction_gain" in item: return (220, 100, 155)
    return BTN_N


def _apply_shop_purchase(idx: int) -> None:
    """
    pygame 主執行緒直接套用購買效果。
    遊戲執行緒此時阻塞於 _shop_exit_event，無競爭讀寫風險。
    """
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
        notify(f"  ✨ 恢復了 {item['stamina_restore']} 點體力！")
    if "intel_gain" in item:
        player.intel += item["intel_gain"]
        notify(f"  📖 智力提升了 {item['intel_gain']} 點！")
    if "satisfaction_gain" in item:
        player.satisfaction = max(0, min(100,
            player.satisfaction + item["satisfaction_gain"]))
        notify(f"  🎮 滿足感提升了 {item['satisfaction_gain']} 點！")
    if "luck_gain" in item:
        player.luck += item["luck_gain"]
        notify(f"  🍀 運氣提升了 {item['luck_gain']} 點！")
    if "status" in item:
        player.status_effects[item["status"]] = item["duration"]
        notify(f"  ➕ 獲得狀態：【{item['status']}】（持續 {item['duration']} 週）")

    _shop_msg[0]      = f"✅ 購買了【{item['name']}】！剩餘 ${player.money} 元"
    _shop_msg_time[0] = pygame.time.get_ticks()


def _draw_shop(surf: pygame.Surface,
               fm, fs, fl,
               items:  list,
               player,
               mpos:   tuple):
    """
    道具店全螢幕介面。
    左側：2欄×5列商品卡（圖示 + 名稱 + 簡述 + 購買按鈕）
    右側：效果說明面板 + 剩餘金錢 + 離開按鈕
    回傳 (buy_rects[(Rect, idx)...], exit_btn_rect)
    """
    # 背景
    surf.blit(_grads.get("bg", pygame.Surface((WIN_W, WIN_H))), (0, 0))
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((255, 238, 200, 55))
    surf.blit(ov, (0, 0))

    # ── 版面常數 ───────────────────────────────────────────────
    COLS   = 2
    ITEM_W = 305
    ITEM_H = 118
    GAP_X  = 10
    GAP_Y  = 8
    GX     = 15
    GY     = 15
    RP_X   = GX + COLS * (ITEM_W + GAP_X)   # 645
    RP_W   = WIN_W - RP_X - 15              # 300

    buy_rects  = []
    hover_this = -1

    # ── 預先判斷 hover ──────────────────────────────────────────
    for i in range(len(items)):
        col = i % COLS
        row = i // COLS
        bx  = GX + col * (ITEM_W + GAP_X)
        by  = GY + row * (ITEM_H + GAP_Y)
        if pygame.Rect(bx, by, ITEM_W, ITEM_H).collidepoint(mpos):
            hover_this = i
            break

    # ── 繪製商品卡（先畫非 hover，再畫 hover 確保在最上層）──────
    draw_order = [i for i in range(len(items)) if i != hover_this]
    if hover_this >= 0:
        draw_order.append(hover_this)

    for i in draw_order:
        item = items[i]
        col  = i % COLS
        row  = i // COLS
        bx   = GX + col * (ITEM_W + GAP_X)
        by   = GY + row * (ITEM_H + GAP_Y)
        base = pygame.Rect(bx, by, ITEM_W, ITEM_H)
        is_hov = (i == hover_this)

        # 卡片 hover 動畫（獨立 key，不與按鈕動畫混用）
        ckey = ("sc", i)
        t    = _anim_hover.get(ckey, 0.0)
        t    = min(1.0, t + 0.12) if is_hov else max(0.0, t - 0.12)
        _anim_hover[ckey] = t
        scale = 1.0 + _ease_out_back(t) * 0.042 if t > 0 else 1.0

        dr = _scaled_rect(base, scale)

        # 卡片背景
        _soft_shadow(surf, dr, radius=14,
                     alpha=60 if is_hov else 38,
                     offset=(3, 5) if is_hov else (2, 3),
                     spread=6 if is_hov else 3)
        pygame.draw.rect(surf, PANEL, dr, border_radius=14)
        # 頂部光澤條
        _gloss_rect(surf, dr)
        # 邊框
        pygame.draw.rect(surf, CYAN if is_hov else DARK_GRAY, dr, 2,
                         border_radius=14)

        # ── 道具圖示圓形 ─────────────────────────────────────────
        icon_r  = int(30 * scale)
        icon_cx = dr.x + int(50 * scale)
        icon_cy = dr.centery
        ic_col  = _item_icon_color(item)

        _soft_shadow_circle(surf, icon_cx, icon_cy, icon_r, alpha=38)
        dark_ic = tuple(max(0, int(c * 0.70)) for c in ic_col)
        pygame.draw.circle(surf, dark_ic, (icon_cx, icon_cy + int(3 * scale)), icon_r)
        pygame.draw.circle(surf, ic_col,  (icon_cx, icon_cy), icon_r)
        _gloss_circle(surf, icon_cx, icon_cy, icon_r)
        bdr_ic = tuple(min(255, int(c * 1.20 + 28)) for c in ic_col)
        pygame.draw.circle(surf, bdr_ic, (icon_cx, icon_cy), icon_r, 2)
        # 圖示首字
        il = fs.render(item["name"][0], True, PANEL)
        surf.blit(il, (icon_cx - il.get_width()  // 2,
                       icon_cy - il.get_height() // 2))

        # ── 文字區 ───────────────────────────────────────────────
        info_x = dr.x + int(90 * scale)
        info_w = dr.right - info_x - int(8 * scale)

        # 道具名稱
        nt = fm.render(item["name"], True, WHITE)
        surf.blit(nt, (info_x, dr.y + int(10 * scale)))

        # 效果簡述（1 行截斷）
        desc_s = item.get("desc", "")
        while desc_s and fs.size(desc_s + "…")[0] > info_w:
            desc_s = desc_s[:-1]
        if desc_s != item.get("desc", ""):
            desc_s += "…"
        dt = fs.render(desc_s, True, GRAY)
        surf.blit(dt, (info_x, dr.y + int(38 * scale)))

        # ── 購買按鈕 ─────────────────────────────────────────────
        buy_h  = int(32 * scale)
        buy_y  = dr.bottom - buy_h - int(9 * scale)
        buy_r  = pygame.Rect(info_x, buy_y, info_w, buy_h)
        bhov   = buy_r.collidepoint(mpos)
        afford = (player is not None and player.money >= item["price"])
        b_col  = BTN_N if afford else DARK_GRAY
        bdr_r  = _premium_btn(surf, buy_r, b_col,
                               bhov and afford, radius=int(9 * scale))
        pt_t   = fs.render(f"購買  $ {item['price']}", True,
                            PANEL if afford else GRAY)
        surf.blit(pt_t, (bdr_r.x + (bdr_r.width  - pt_t.get_width())  // 2,
                          bdr_r.y + (bdr_r.height - pt_t.get_height()) // 2))

        buy_rects.append((buy_r, i))

    _shop_hover_idx[0] = hover_this

    # ── 右側說明面板 ─────────────────────────────────────────────
    rp = pygame.Rect(RP_X, 15, RP_W, WIN_H - 80)
    _soft_shadow(surf, rp, radius=16, alpha=55, offset=(3, 5), spread=6)
    pygame.draw.rect(surf, PANEL, rp, border_radius=16)
    _gloss_rect(surf, rp)
    pygame.draw.rect(surf, CYAN, rp, 2, border_radius=16)

    # 標題
    tt = fm.render("效果說明", True, TITLE)
    surf.blit(tt, (rp.x + (rp.width - tt.get_width()) // 2, rp.y + 16))
    pygame.draw.line(surf, GRAY,
                     (rp.x + 14, rp.y + 50), (rp.right - 14, rp.y + 50), 1)

    # 說明內容
    desc_y    = rp.y + 62
    msg_valid = (_shop_msg[0] and
                 pygame.time.get_ticks() - _shop_msg_time[0] < 2500)

    if msg_valid:
        mc = GREEN if _shop_msg[0].startswith("✅") else RED
        for j, ln in enumerate(_wrap(_shop_msg[0], fs, rp.width - 28)):
            mt = fs.render(_clean(ln), True, mc)
            surf.blit(mt, (rp.x + 14, desc_y + j * (fs.get_height() + 4)))
    elif hover_this >= 0 and hover_this < len(items):
        hi = items[hover_this]
        hn = fm.render(hi["name"], True, WHITE)
        surf.blit(hn, (rp.x + 14, desc_y))
        hp = fs.render(f"售價：${hi['price']} 元", True, YELLOW)
        surf.blit(hp, (rp.x + 14, desc_y + fm.get_height() + 6))
        dy2 = desc_y + fm.get_height() + fs.get_height() + 18
        for j, ln in enumerate(_wrap(hi.get("desc", ""), fs, rp.width - 28)):
            surf.blit(fs.render(ln, True, GRAY),
                      (rp.x + 14, dy2 + j * (fs.get_height() + 5)))
    else:
        for j, hint in enumerate(["將游標移至道具", "查看效果說明"]):
            ht = fs.render(hint, True, GRAY)
            surf.blit(ht, (rp.x + (rp.width - ht.get_width()) // 2,
                           desc_y + 24 + j * (fs.get_height() + 6)))

    # 分隔線 + 金錢
    pygame.draw.line(surf, GRAY,
                     (rp.x + 14, rp.bottom - 108),
                     (rp.right - 14, rp.bottom - 108), 1)
    mval = player.money if player else 0
    mt   = fm.render(f"剩餘金錢：${mval}", True, YELLOW)
    surf.blit(mt, (rp.x + (rp.width - mt.get_width()) // 2, rp.bottom - 94))

    # 離開道具店按鈕
    eb   = pygame.Rect(rp.x + 14, WIN_H - 60, rp.width - 28, 44)
    ehov = eb.collidepoint(mpos)
    edr  = _premium_btn(surf, eb, (200, 78, 58), ehov, radius=14)
    et   = fm.render("離開道具店", True, PANEL)
    surf.blit(et, (edr.x + (edr.width  - et.get_width())  // 2,
                   edr.y + (edr.height - et.get_height()) // 2))

    return buy_rects, eb


# ─────────────────────────────────────────
#  pygame 主迴圈（在主執行緒中呼叫）
# ─────────────────────────────────────────

def run_ui():
    """啟動 pygame 視窗並進入主迴圈，直到視窗關閉。"""
    pygame.init()
    pygame.key.set_repeat(400, 50)  # 長按重複：400ms 後開始，每 50ms 一次（backspace 連刪）

    # ── 初始化音效 ────────────────────────────────────────────
    try:
        pygame.mixer.init()
        _se_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "asset", "audio", "se")
        def _ld(fn):
            try:
                return pygame.mixer.Sound(os.path.join(_se_dir, fn))
            except Exception:
                return None
        _sfx["start_click"] = _ld("soundreality-interface-6-204504.mp3")
        _sfx["cc_click"]    = _ld("dropping (mp3cut.net).wav")
        _sfx["action"]      = _ld("attack1.mp3")
        _sfx["ui_click"]    = _ld("poka.mp3")
        _sfx["back"]        = _ld("universfield-interface-03-277552.mp3")
    except Exception:
        pass

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("如何渡過這學期？")
    clock  = pygame.time.Clock()

    fl = _get_font(40)   # 開始 / 結束畫面標題大字
    fm = _get_font(22)
    fs = _get_font(17)
    _font_micro[0] = _get_font(11)   # 週次輪盤小字

    # 版面 Rect
    sr = pygame.Rect(0, 0,           WIN_W, STATUS_H)   # 狀態欄
    cr = pygame.Rect(0, STATUS_H,    WIN_W, CHAR_H)      # 人物立繪區
    ar = pygame.Rect(0, STATUS_H + CHAR_H, WIN_W, ACTION_H)  # 底部行動面板
    # 結束畫面的 log 用人物區的 Rect
    lr = cr

    # ── 預先計算漸層 Surface ──────────────────────────────────
    _grads["bg"]     = _gradient_surf(WIN_W, WIN_H,    (255, 245, 222), (252, 232, 200))
    _grads["status"] = _gradient_surf(WIN_W, STATUS_H, (255, 226, 190), (255, 242, 214))
    _grads["input"]  = _gradient_surf(WIN_W, ACTION_H, (255, 242, 214), (255, 226, 190))
    _grads["start"]  = _gradient_surf(WIN_W, WIN_H,    (255, 248, 226), (255, 228, 192))

    # ── 匯入背景圖片（cover 縮放，失敗時保留漸層）───────────
    _bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "asset", "picture", "background")
    _title_img = _load_cover(
        os.path.join(_bg_dir, "title_background.webp"), WIN_W, WIN_H)
    if _title_img is not None:
        _grads["start"] = _title_img

    _game_img = _load_cover(
        os.path.join(_bg_dir, "1234_background.webp"), WIN_W, WIN_H)
    if _game_img is not None:
        _grads["bg"] = _game_img
        # 圖片背景時，狀態欄與行動面板改為半透明疊層，讓建築圖透出
        _st_ov = pygame.Surface((WIN_W, STATUS_H), pygame.SRCALPHA)
        _st_ov.fill((255, 238, 212, 215))
        _grads["status"] = _st_ov
        _in_ov = pygame.Surface((WIN_W, ACTION_H), pygame.SRCALPHA)
        _in_ov.fill((255, 238, 212, 215))
        _grads["input"] = _in_ov

    # ── BGM 初始化（設定資料夾，播放標題音樂）──────────────────
    _bgm_dir[0] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "asset", "audio", "bgm")
    _request_bgm("Music-Morning_Rain.mp3")

    # ── 角色創建背景影片（WEBM）────────────────────────────────
    _cc_webm_path = os.path.join(_bg_dir, "skill_background.webm")
    try:
        import cv2 as _cv2_init
        _cap = _cv2_init.VideoCapture(_cc_webm_path)
        if _cap.isOpened():
            _cc_video_cap[0] = _cap
            _fps = _cap.get(_cv2_init.CAP_PROP_FPS)
            _cc_video_fps[0] = float(_fps) if _fps and _fps > 0 else 30.0
        else:
            _cap.release()
    except Exception:
        pass

    # 全螢幕切換按鈕固定 Rect（右下角，各畫面常駐）
    fs_btn = pygame.Rect(WIN_W - 46, WIN_H - 46, 40, 40)

    running = True
    while running:
        mpos = pygame.mouse.get_pos()
        # 道具店按鈕是否可點擊：只有在行動選單中且選項包含道具店時才亮起
        shop_active = (_mode[0] == "choices" and "🏪 前往道具店" in _choices)

        # ── BGM 非阻塞切換 tick ───────────────────────────────
        if (_bgm_pending[0] is not None
                and pygame.time.get_ticks() >= _bgm_switch_at[0]):
            _next_bgm      = _bgm_pending[0]
            _bgm_pending[0] = None
            _bgm_current[0] = _next_bgm
            if _next_bgm is not None:
                _bpath = os.path.join(_bgm_dir[0], _next_bgm)
                if os.path.isfile(_bpath):
                    try:
                        pygame.mixer.music.load(_bpath)
                        pygame.mixer.music.play(-1, fade_ms=BGM_FADE_MS)
                    except Exception:
                        pass

        # ── 消化遊戲執行緒的命令 ─────────────────────────────
        while not _cmd_q.empty():
            cmd = _cmd_q.get_nowait()
            tag = cmd[0]
            if tag == "msg":
                _log.extend(_wrap(cmd[1], fs, WIN_W - 28))
                _scroll[0] = 0
            elif tag == "player":
                _player[0] = cmd[1]
            elif tag == "choices":
                _choices.clear()
                _choices.extend(cmd[1])
                _mode[0] = "choices"
            elif tag == "yn":
                _prompt[0]    = cmd[1]
                _yn_labels[0] = cmd[2] if len(cmd) > 2 else "是"
                _yn_labels[1] = cmd[3] if len(cmd) > 3 else "否"
                _mode[0] = "yn"
            elif tag == "text":
                _prompt[0] = cmd[1]
                _tvalue[0] = cmd[2] if len(cmd) > 2 else ""
                _mode[0] = "text"
                pygame.key.start_text_input()  # Windows IME 必須主動開啟
            elif tag == "phase":
                _phase[0] = cmd[1]
                if cmd[1] == "shop":          # 道具店：觸發由上而下滑入
                    _shop_slide_dir[0] = "in"
                    _shop_slide_t0[0]  = pygame.time.get_ticks()
                elif cmd[1] == "char_create":
                    _request_bgm("Music-Aether.mp3")
                elif cmd[1] == "end":
                    _request_bgm(None)
            elif tag == "ripple":
                _ripple_t0[0] = pygame.time.get_ticks()
                _play_sfx("cc_click")
            elif tag == "bgm_week":
                _request_bgm(_WEEK_BGM.get(cmd[1]))
            elif tag == "reset":
                _log.clear()
                _player[0] = None
                _mode[0] = None
                _choices.clear()
                _prompt[0] = ""
                _tvalue[0] = ""
                _scroll[0] = 0
                _composing[0] = ""
                _request_bgm("Music-Morning_Rain.mp3")
            elif tag == "cc_name":
                _cc_mode[0]      = "name"
                _cc_data[0]      = tag
                _cc_tvalue[0]    = ""
                _cc_composing[0] = ""
                pygame.key.start_text_input()
            elif tag == "cc_dept":
                _cc_mode[0] = "dept"
                _cc_data[0] = cmd[1]   # options list
            elif tag == "cc_drawbacks":
                _cc_mode[0] = "drawbacks"
                _cc_data[0] = cmd[1]   # drawbacks list
                _cc_sel.clear()
                _cc_btn_cache["drawbacks_max"] = cmd[2]
            elif tag == "cc_stats":
                _cc_mode[0]          = "stats"
                _cc_stat_total[0]    = cmd[1]
                _cc_stat_vals[:]     = [10, 10, 10]
                _cc_stat_raw[:]      = ["10", "10", "10"]
                _cc_active_stat[0]   = None
            elif tag == "cc_talent":
                _cc_mode[0] = "talent"
                _cc_data[0] = cmd[1]   # candidates list
                _cc_sel.clear()
            elif tag == "set_time":
                _time_units[0] = cmd[1]
            elif tag == "timetable":
                _modal[0]      = "timetable"
                _modal_data[0] = cmd[1]   # courses list
            elif tag == "grade_report":
                _modal[0]      = "grade_report"
                _modal_data[0] = cmd[1]   # items list

        # ── 繪製（依畫面階段切換內容）────────────────────────
        # 全螢幕 fallback（無 SCALED）時 Surface 可能大於 WIN_W×WIN_H；
        # 先把遊戲邊界外的區域填黑，防止上幀殘留像素堆疊成視覺垃圾。
        _sw, _sh = screen.get_size()
        if _sw > WIN_W:
            screen.fill((0, 0, 0), pygame.Rect(WIN_W, 0, _sw - WIN_W, _sh))
        if _sh > WIN_H:
            screen.fill((0, 0, 0), pygame.Rect(0, WIN_H, _sw, _sh - WIN_H))

        btn_rects      = []
        start_btn      = None
        end_btn        = None
        end_week_btn   = None
        shop_btn_rect  = None
        shop_buy_rects = []
        shop_exit_btn  = None

        if _phase[0] == "start":
            start_btn = _draw_start(screen, fm, fl, mpos)
        elif _phase[0] == "shop":
            # ── 計算道具店滑動偏移 ──────────────────────────────
            _sdir = _shop_slide_dir[0]
            _sel  = max(pygame.time.get_ticks() - _shop_slide_t0[0], 0)
            if _sdir == "in":
                _rt  = min(_sel / SHOP_SLIDE_MS, 1.0)
                _yoff = int(-WIN_H * (1.0 - _ease_out_quart(_rt)))
                if _rt >= 1.0:
                    _shop_slide_dir[0] = "none"
                    _yoff = 0
            elif _sdir == "out":
                _rt  = min(_sel / SHOP_SLIDE_MS, 1.0)
                _yoff = int(-WIN_H * _ease_in_cubic(_rt))
                if _rt >= 1.0:
                    _shop_slide_dir[0] = "out_done"
                    _shop_exit_event.set()
            elif _sdir == "out_done":
                _yoff = -WIN_H   # 完全滑走，等待 phase 切換
            else:
                _yoff = 0

            if _sdir == "out_done":
                # 顯示遊戲底圖，等待相位切換為 "game"
                screen.blit(_grads["bg"], (0, 0))
                shop_buy_rects, shop_exit_btn = [], None
            elif _yoff != 0:
                # 動畫中：先畫遊戲底圖，再把道具店 Surface 蓋上並偏移
                screen.blit(_grads["bg"], (0, 0))
                _shop_tmp = pygame.Surface((WIN_W, WIN_H))
                shop_buy_rects, shop_exit_btn = _draw_shop(
                    _shop_tmp, fm, fs, fl, _shop_items, _player[0], (-1, -1))
                screen.blit(_shop_tmp, (0, _yoff))
            else:
                shop_buy_rects, shop_exit_btn = _draw_shop(
                    screen, fm, fs, fl, _shop_items, _player[0], mpos)
        elif _phase[0] == "end":
            end_btn = _draw_end(screen, fm, fs, lr, mpos)
        elif _phase[0] == "char_create":
            cm = _cc_mode[0]
            if cm == "name":
                ok = _draw_cc_name(screen, fm, fs, mpos)
                _cc_btn_cache["name_ok"] = ok
            elif cm == "dept":
                drects = _draw_cc_dept(screen, fm, fs, _cc_data[0] or [], mpos)
                _cc_btn_cache["dept_cards"] = drects
            elif cm == "drawbacks":
                crects, ok = _draw_cc_drawbacks(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel,
                    _cc_btn_cache.get("drawbacks_max", 2), mpos)
                _cc_btn_cache["drawback_cards"] = crects
                _cc_btn_cache["drawbacks_ok"]   = ok
            elif cm == "stats":
                mr, pr, ok = _draw_cc_stats(
                    screen, fm, fs,
                    _cc_stat_total[0], _cc_stat_vals, _cc_stat_raw,
                    _cc_active_stat[0], mpos)
                _cc_btn_cache["stats_minus"] = mr
                _cc_btn_cache["stats_plus"]  = pr
                _cc_btn_cache["stats_ok"]    = ok
            elif cm == "talent":
                trects, ok = _draw_cc_talent(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel[0] if _cc_sel else None, mpos)
                _cc_btn_cache["talent_cards"] = trects
                _cc_btn_cache["talent_ok"]    = ok
            else:
                # 切換中的空白幀
                _draw_cc_bg(screen)
        else:   # "game"
            screen.blit(_grads["bg"], (0, 0))
            # 狀態欄（新版，含頭像 + 道具店按鈕，回傳 shop_btn_rect）
            shop_btn_rect = _draw_status_v2(screen, fm, fs, _player[0], sr, mpos)
            # 狀態欄底部陰影（增加與人物區的層次感）
            _panel_top_shadow(screen, sr.x, sr.bottom, sr.width, alpha=38, h=14)
            # 人物立繪區
            _draw_character_art(screen, cr)
            # 行動面板頂部陰影
            _panel_top_shadow(screen, ar.x, ar.y, ar.width, alpha=32, h=12)
            # 底部行動面板（含圓形按鈕 / 敘述文字 / yn / text）
            btn_rects, end_week_btn = _draw_action_panel(
                screen, fm, fs, _mode[0], _choices, _log,
                _prompt, _tvalue, ar, _time_units[0], mpos)
            # 行動結果彈出視窗（右側由右而左滑入）
            _draw_action_popup(screen, fs)

        # ── Modal 疊加（課表 / 成績公告，浮在所有畫面之上）────────
        _modal_ok_btn = None
        if _modal[0] == "timetable":
            _modal_ok_btn = _draw_modal_timetable(
                screen, fm, fs, _modal_data[0] or [], mpos)
        elif _modal[0] == "grade_report":
            _modal_ok_btn = _draw_modal_grade(
                screen, fm, fl, fs, _modal_data[0] or [], mpos)

        # ── 全螢幕切換按鈕（右下角，常駐顯示）──────────────────
        _fs_hover = fs_btn.collidepoint(mpos)
        _fs_bg    = (110, 80, 50) if _fs_hover else (70, 50, 32)
        pygame.draw.rect(screen, _fs_bg, fs_btn, border_radius=8)
        pygame.draw.rect(screen, CYAN, fs_btn, 1, border_radius=8)
        # 繪製展開 / 收縮圖示（四角 L 形括號）
        _ix = fs_btn.x + 7
        _iy = fs_btn.y + 7
        _iw = fs_btn.width  - 14
        _ih = fs_btn.height - 14
        _a  = 7
        _ic = PANEL
        if _is_fullscreen[0]:
            # 收縮圖示：L 形箭頭指向內側
            pygame.draw.line(screen, _ic, (_ix+_a,      _iy),        (_ix+_a,      _iy+_a),        2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_a),     (_ix+_a,      _iy+_a),        2)
            pygame.draw.line(screen, _ic, (_ix+_iw-_a,  _iy),        (_ix+_iw-_a,  _iy+_a),        2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_a),     (_ix+_iw-_a,  _iy+_a),        2)
            pygame.draw.line(screen, _ic, (_ix+_a,      _iy+_ih),    (_ix+_a,      _iy+_ih-_a),    2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_ih-_a), (_ix+_a,      _iy+_ih-_a),    2)
            pygame.draw.line(screen, _ic, (_ix+_iw-_a,  _iy+_ih),    (_ix+_iw-_a,  _iy+_ih-_a),   2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_ih-_a), (_ix+_iw-_a,  _iy+_ih-_a),   2)
        else:
            # 展開圖示：L 形箭頭指向四角外側
            pygame.draw.line(screen, _ic, (_ix,         _iy),        (_ix+_a,      _iy),            2)
            pygame.draw.line(screen, _ic, (_ix,         _iy),        (_ix,         _iy+_a),         2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy),        (_ix+_iw-_a,  _iy),            2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy),        (_ix+_iw,     _iy+_a),         2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_ih),    (_ix+_a,      _iy+_ih),        2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_ih),    (_ix,         _iy+_ih-_a),     2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_ih),    (_ix+_iw-_a,  _iy+_ih),       2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_ih),    (_ix+_iw,     _iy+_ih-_a),    2)

        # ── 漣漪轉場覆蓋層（最頂層，疊在所有內容之上）──────────
        _draw_ripple_overlay(screen)

        pygame.display.flip()

        # ── pygame 事件 ───────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # 全螢幕切換按鈕（最高優先，任何畫面均有效）
                if fs_btn.collidepoint(ev.pos):
                    if _is_fullscreen[0]:
                        screen = pygame.display.set_mode((WIN_W, WIN_H))
                        _is_fullscreen[0] = False
                    else:
                        try:
                            _fs_flags = pygame.FULLSCREEN | getattr(pygame, "SCALED", 0)
                            screen = pygame.display.set_mode((WIN_W, WIN_H), _fs_flags)
                        except Exception:
                            screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.FULLSCREEN)
                        _is_fullscreen[0] = True
                    continue

                # ── Modal 優先攔截（課表 / 成績公告）────────────
                if _modal[0] is not None:
                    if _modal_ok_btn and _modal_ok_btn.collidepoint(ev.pos):
                        _modal[0]      = None
                        _modal_data[0] = None
                        _modal_event.set()
                    continue   # modal 開著時不處理底層按鈕

                if _phase[0] == "start":
                    if start_btn and start_btn.collidepoint(ev.pos):
                        _play_sfx("start_click")
                        _click_reg[(start_btn.centerx, start_btn.centery)] = pygame.time.get_ticks()
                        _phase[0] = "game"
                        _start_event.set()
                elif _phase[0] == "shop":
                    # 離開按鈕：僅在靜止狀態（非動畫中）才響應
                    if (shop_exit_btn and shop_exit_btn.collidepoint(ev.pos)
                            and _shop_slide_dir[0] == "none"):
                        _play_sfx("back")
                        _click_reg[(shop_exit_btn.centerx, shop_exit_btn.centery)] = pygame.time.get_ticks()
                        # 觸發由下而上滑出動畫，動畫結束後才設定 exit event
                        _shop_slide_dir[0] = "out"
                        _shop_slide_t0[0]  = pygame.time.get_ticks()
                    else:
                        # 購買按鈕
                        for (br, idx) in shop_buy_rects:
                            if br.collidepoint(ev.pos):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _apply_shop_purchase(idx)
                                break
                elif _phase[0] == "char_create":
                    # 能力點 +/- 按鈕使用 poka 音效；其他創角操作使用 cc_click
                    if _cc_mode[0] == "stats":
                        _is_stat_btn = False
                        for _sr in (_cc_btn_cache.get("stats_minus") or []):
                            if _sr.collidepoint(ev.pos):
                                _is_stat_btn = True; break
                        if not _is_stat_btn:
                            for _sr in (_cc_btn_cache.get("stats_plus") or []):
                                if _sr.collidepoint(ev.pos):
                                    _is_stat_btn = True; break
                        _play_sfx("ui_click" if _is_stat_btn else "cc_click")
                    else:
                        _play_sfx("cc_click")
                    _handle_cc_action(ev.pos)
                elif _phase[0] == "end":
                    if end_btn and end_btn.collidepoint(ev.pos):
                        _play_sfx("ui_click")
                        _click_reg[(end_btn.centerx, end_btn.centery)] = pygame.time.get_ticks()
                        _phase[0] = "start"
                        _request_bgm("Music-Morning_Rain.mp3")
                        _restart_event.set()
                else:
                    # ── 遊戲中 ────────────────────────────────
                    # 狀態欄道具店按鈕（僅在行動選單時有效）
                    if (shop_active
                            and shop_btn_rect is not None
                            and shop_btn_rect.collidepoint(ev.pos)):
                        _play_sfx("ui_click")
                        _click_reg[(shop_btn_rect.centerx, shop_btn_rect.centery)] = pygame.time.get_ticks()
                        shop_idx = next(
                            (i + 1 for i, c in enumerate(_choices)
                             if c == "🏪 前往道具店"), None)
                        if shop_idx is not None:
                            _reply_val[0] = shop_idx
                            _mode[0] = None
                            _choices.clear()
                            _reply_event.set()
                        continue

                    # 結束本週按鈕（回傳 0）
                    if (_mode[0] == "choices"
                            and end_week_btn is not None
                            and end_week_btn.collidepoint(ev.pos)):
                        _play_sfx("back")
                        _click_reg[(end_week_btn.centerx, end_week_btn.centery)] = pygame.time.get_ticks()
                        _reply_val[0] = 0
                        _mode[0] = None
                        _choices.clear()
                        _time_units[0] = 0
                        _reply_event.set()
                        continue

                    # 行動按鈕 / yn / text 確認
                    for (br, val) in btn_rects:
                        if br.collidepoint(ev.pos):
                            _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                            if _mode[0] == "text" and val == "__ok__":
                                _play_sfx("ui_click")
                                _reply_val[0] = _tvalue[0]
                                _mode[0] = None
                                _composing[0] = ""
                                pygame.key.stop_text_input()
                                _reply_event.set()
                            elif _mode[0] in ("choices", "yn"):
                                # 決定音效
                                if _mode[0] == "choices":
                                    _cname = (_choices[val - 1]
                                              if isinstance(val, int) and 1 <= val <= len(_choices)
                                              else "")
                                    _play_sfx("action" if _cname in _STANDARD_ACTIONS
                                                          and _cname != "🏪 前往道具店"
                                              else "ui_click")
                                else:  # yn
                                    _play_sfx("ui_click" if val else "back")
                                _reply_val[0] = val
                                _mode[0] = None
                                _choices.clear()
                                _reply_event.set()

            elif ev.type == pygame.TEXTEDITING:
                # 輸入法組字中（例如注音還沒按確認）：只更新預覽，不寫入正文
                if _phase[0] == "char_create" and _cc_mode[0] == "name":
                    _cc_composing[0] = ev.text
                elif _mode[0] == "text":
                    _composing[0] = ev.text

            elif ev.type == pygame.TEXTINPUT:
                # 輸入法確認（或直接打英數）：寫入正文，清除組字預覽
                if _phase[0] == "char_create" and _cc_mode[0] == "name":
                    _cc_tvalue[0] += ev.text
                    _cc_composing[0] = ""
                elif _mode[0] == "text":
                    _tvalue[0] += ev.text
                    _composing[0] = ""

            elif ev.type == pygame.KEYDOWN:
                if _phase[0] == "char_create":
                    if _cc_mode[0] == "name":
                        if ev.key == pygame.K_RETURN:
                            _cc_reply_val[0] = _cc_tvalue[0]
                            _cc_mode[0] = ""
                            pygame.key.stop_text_input()
                            _cc_reply_event.set()
                        elif ev.key == pygame.K_BACKSPACE:
                            if _cc_composing[0]:
                                _cc_composing[0] = ""
                            else:
                                _cc_tvalue[0] = _cc_tvalue[0][:-1]
                    elif _cc_mode[0] == "stats":
                        ai = _cc_active_stat[0]
                        if ai is not None:
                            digit = None
                            if pygame.K_0 <= ev.key <= pygame.K_9:
                                digit = ev.key - pygame.K_0
                            elif pygame.K_KP0 <= ev.key <= pygame.K_KP9:
                                digit = ev.key - pygame.K_KP0
                            if digit is not None:
                                new_raw = _cc_stat_raw[ai] + str(digit)
                                try:
                                    v = int(new_raw)
                                    other = sum(_cc_stat_vals) - _cc_stat_vals[ai]
                                    if 0 <= v <= _cc_stat_total[0] - other:
                                        _cc_stat_vals[ai] = v
                                        _cc_stat_raw[ai]  = new_raw
                                except ValueError:
                                    pass
                            elif ev.key == pygame.K_BACKSPACE:
                                new_raw = _cc_stat_raw[ai][:-1]
                                _cc_stat_raw[ai] = new_raw
                                try:
                                    _cc_stat_vals[ai] = int(new_raw) if new_raw else 0
                                except ValueError:
                                    _cc_stat_vals[ai] = 0
                elif _mode[0] == "text":
                    if ev.key == pygame.K_RETURN:
                        _reply_val[0] = _tvalue[0]
                        _mode[0] = None
                        _composing[0] = ""
                        pygame.key.stop_text_input()
                        _reply_event.set()
                    elif ev.key == pygame.K_BACKSPACE:
                        if _composing[0]:
                            _composing[0] = ""  # 先清組字預覽
                        else:
                            _tvalue[0] = _tvalue[0][:-1]

        clock.tick(30)

    pygame.quit()
    sys.exit()
