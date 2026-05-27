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
import math
import random

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
CYAN      = ( 93,  64,  55)   # #5D4037 深咖啡棕 — 強調邊框（取代舊藍色）
MILK      = (255, 253, 248)   # 純奶白 — 文字輸入框背景
TITLE     = ( 93,  64,  55)   # #5D4037 深棕 — 標題文字（取代各處藍色 CYAN 字）

# ── 智力等階常數（供狀態欄顯示，避免循環匯入 skill_system）────
_INTEL_THRESHOLDS_UI = [0, 20, 40, 60, 80]
_INTEL_NAMES_UI      = ["障礙", "困擾", "平均", "優秀", "聰明"]
_INTEL_ANNOT_COLS_UI = [
    (160,  40,  40),   # 障礙 — 暗紅
    ( 72,  38,  18),   # 困擾 — 深棕黑
    ( 60, 120, 200),   # 平均 — 藍色
    ( 60, 160,  75),   # 優秀 — 綠色
    (190, 140,   0),   # 聰明 — 金色
]

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
_yn_labels       = ["是", "否"]   # yn 模式的按鈕文字（可自定義）
_yn_show_ctx     = [True]         # yn 模式是否附帶 log 背景（預設 True）
_event_ok_text   = [""]           # event_ok 模式：彈窗全文（title\nbody）
_event_ok_popup_rects: list = []  # event_ok 模式：確認按鈕 rect 清單
_story_lines: list = []           # tell_story() 待顯示的劇情行
_story_index = [0]                # 當前顯示到第幾行
_tvalue  = [""]     # text 模式的目前輸入內容
_scroll    = [0]      # 訊息區往上捲動的行數（保留供 end 畫面使用）
_composing = [""]   # IME 組字預覽（輸入法尚未確認的字）
_time_units    = [0]      # 本週剩餘時間點（底部標籤列顯示用）
_is_fullscreen    = [False]  # 目前是否全螢幕
_week             = [0]      # 當前週次（1–16，0 表示尚未開始）
_exam_ready_label = [""]     # "準備期中考" | "準備期末考"（exam_ready 模式用）

# ── 人物立繪系統 ──────────────────────────────────────────────────────
_CHAR_ART_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "asset", "picture", "character")
_portrait_prefix   = [""]    # "b1" | "g1"，角色創建時選定
_portrait_curr_key = [""]    # 目前顯示的立繪 key（變更偵測用）
_portrait_curr     = [None]  # 目前顯示的立繪 Surface（已縮放）
_portrait_prev     = [None]  # 淡出中的前一張立繪 Surface
_portrait_fade_t0  = [0]     # 淡入開始時間戳（ms，0=無淡入中）
_PORTRAIT_FADE_MS  = 200     # 淡入總時長（ms）
_portrait_orig:   dict = {}  # key -> 原始 Surface（未縮放，已快取）
_portrait_scl:    dict = {}  # (key,w,h) -> 縮放後 Surface（已快取）
_portrait_head_cache: dict = {}  # prefix -> 圓形頭像 Surface (84px，已快取)
_font_micro    = [None]   # 極小字型（週次輪盤數字用）
_font_bold     = [None]   # 粗體字型 size-17（行動按鈕標籤用）
_font_bold_lg  = [None]   # 粗體字型 size-22（標題 / 上方視窗用）
_font_bold_xl  = [None]   # 粗體字型 size-26（日曆週次大字用）

# ── 剩餘時間點震動特效 ──────────────────────────────────────────
_time_shake_t0 = [0]      # 震動觸發時間戳（ms，0 = 未啟用）
_TIME_SHAKE_MS = 520      # 整段動畫時長（ms）

# ── 突發事件全螢幕震動 ──────────────────────────────────────────
_evt_shake_t0  = [0]      # 震動觸發時間戳（ms，0 = 未啟用）
_EVT_SHAKE_MS  = 480      # 震動總時長（ms）
_EVT_SHAKE_AMP = 14       # 最大震動幅度（px）

# ── 點名警示便利貼 ──────────────────────────────────────────────
_roll_call_course = [""]   # 當週點名科目（空字串 = 未啟用）

# ── 特殊行動停用狀態 ──────────────────────────────────────────
_special_disabled: dict = {}   # {行動名: 倒數格數} 停用中的特殊行動

# ── 行動成功白光閃爍 ────────────────────────────────────────────
_action_flash_t0 = [0]    # 閃爍觸發時間戳（ms，0 = 未啟用）
_ACTION_FLASH_MS = 300    # 整段閃爍時長（ms）

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
_cc_stat_base   = [30]          # 其中基礎點數（不含負面特質加成）
_cc_stat_talent   = [{}]        # 已選天賦字典（供能力點面板顯示加成用）
_cc_stat_de_level = [{}]        # 已選年級字典（供能力點面板顯示加成用）
_cc_active_stat = [None]        # 鍵盤焦點在哪個 stat（0|1|2|None）
_cc_stat_raw    = ["10","10","10"]  # 三個 stat 輸入框的原始字串

# ── 拉霸機天賦動畫狀態 ───────────────────────────────────────────
_SLOT_SPIN_MS    = 1500          # 每槽旋轉時長（ms）
_SLOT_DELAY_MS   = 300           # 上一槽停止到下一槽啟動的延遲（ms）
_SLOT_SPIN_NAMES = [             # 旋轉時快速輪播的名稱池
    "天選之人", "勤奮學霸", "勤奮學渣", "富二代",
    "社交達人", "夜貓子", "路痴", "抵抗力低下", "無天賦",
]
_CONFETTI_COLORS = [
    (255, 80, 80), (255, 160, 50), (255, 215, 0),
    (80, 200, 80), (80, 150, 255), (220, 80, 220),
]
_slot_results : list = [None, None, None]   # 各槽預定結果 talent dict
_slot_phase   : list = ["idle","idle","idle"]  # "idle"|"spinning"|"done"
_slot_stop_t  : list = [0, 0, 0]           # 各槽停止旋轉的 ticks
_slot_start_t : list = [0, 0, 0]           # 各槽開始旋轉的 ticks
_cc_confetti  : list = []                  # 彩帶粒子列表
_cc_shake_end  = [0]                       # 震動結束時刻（ticks）

# ── 額外事件選擇狀態 ─────────────────────────────────────────────
_cc_extra_data  : list = []   # EXTRA_EVENTS 完整資料
_cc_extra_sel   : list = []   # 已選的 event id 列表
_cc_extra_intel  = [0]        # 玩家當前智力（判斷家教資格用）
_cc_extra_warn   = [0]        # 互斥衝突警告觸發時間 ticks（0=無）

# ── event_ok 彩色邊框擴充 ─────────────────────────────────────────
_event_ok_border_color = [None]   # None = 預設棕色；或 (r,g,b) tuple

# ── 玩家資訊一覽（CC 最終確認 + 遊戲中查閱）─────────────────────
_cc_summary_data   = [{}]    # 傳給 _draw_cc_summary() 的 dict
_info_modal_active = [False] # 遊戲中「資訊一覽」modal 是否開啟
_info_btn_rect     = [None]  # 遊戲中「資訊一覽」按鈕 Rect（click handler 用）
_info_modal_close  = [None]  # modal 內「關閉」按鈕 Rect（每幀更新）

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

# ── 科目選擇彈出視窗狀態 ─────────────────────────────────────────
_subj_popup_active = [False]
_subj_popup_title:  list = [""]
_subj_popup_opts:   list = []    # 選項字串列表
_subj_popup_rects:  list = []    # [(rect, idx), ...] 每幀更新

# ── 通用選項彈出視窗（非標準 choices + yn）─────────────────────
_choice_popup_rects: list = []   # [(rect, val), ...] 每幀更新

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

# ── 遊戲背景 crossfade ─────────────────────────────────────────
BG_FADE_MS  = 800         # crossfade 時長（ms）
_bg_surfs   : dict = {}   # filename → pygame.Surface（啟動時載入）
_bg_current = [None]      # 目前全額顯示的遊戲背景 Surface
_bg_target  = [None]      # crossfade 目標 Surface（None = 未在過渡）
_bg_fade_t0 = [0]         # crossfade 開始時間戳（ms）

# 週次 → 背景圖檔名對照表（None = 待補圖，保持當前背景）
_WEEK_BG: dict = {
    1:  "1234_background.webp",
    2:  "1234_background.webp",
    3:  "34_background.webp",
    4:  "34_background.webp",
    5:  "56_background.webp",
    6:  "56_background.webp",
    7:  "7_background.webp",      # 待補
    8:  "mid_background.webp",    # 待補
    9:  "910_background.webp",
    10: "910_background.webp",
    11: "1112_background.webp",
    12: "1112_background.webp",
    13: "1314_background.webp",
    14: "1314_background.webp",
    15: "15_background.webp",     # 待補
    16: "fin_background.webp",    # 待補
}

# ── 道具店滑動轉場 ────────────────────────────────────────────
_shop_slide_dir = ["none"]   # "in" | "out" | "out_done" | "none"
_shop_slide_t0  = [0]        # 動畫開始時間（ms）
SHOP_SLIDE_MS   = 370        # 單向滑動時長（ms）

# ============================================================
#  動態天氣特效系統
# ============================================================
# 支援五種天氣，每週隨機切換：
#   "sun"           陽光灑落（光柱 + 漂浮光塵）
#   "leaves_green"  綠葉飄蕩
#   "leaves_orange" 橙色楓葉飄蕩
#   "sakura"        粉色櫻花飄落
#   "rain"          陰雨綿綿（深灰遮罩 + 雨滴）
# ============================================================

_WEATHER_TYPES = ["sun", "leaves_green", "leaves_orange", "sakura", "rain", "fog"]
_weather_type  = [None]   # 目前天氣類型字串
_weather_pts   = []       # 粒子池（葉子 / 花瓣 / 雨滴 / 光塵 / 霧團）

# 葉子 / 花瓣顏色組
_WX_LEAF_COLS = {
    "leaves_green":  [
        (52, 160, 54), (72, 180, 60), (40, 140, 45),
        (68, 170, 72), (55, 155, 58), (80, 190, 65),
    ],
    "leaves_orange": [
        (210, 75, 20), (225, 100, 30), (190, 60, 15),
        (215, 130, 35), (200, 88, 22), (230, 110, 40),
    ],
    "sakura": [
        (255, 180, 200), (255, 200, 215), (255, 210, 222),
        (250, 170, 192), (255, 185, 205), (255, 220, 230),
    ],
}


# ── 粒子工廠 ─────────────────────────────────────────────────

def _wx_leaf_new(wt: str, full_screen: bool = False) -> dict:
    """生成一片葉子 / 花瓣粒子。full_screen=True 時 y 散布全螢幕（初始化用）。"""
    is_sak = (wt == "sakura")
    cols   = _WX_LEAF_COLS.get(wt, [(200, 200, 200)])
    y0     = (random.uniform(-WIN_H, WIN_H) if full_screen
              else random.uniform(-80, -10))
    return {
        "wt":         wt,
        "x":          random.uniform(-40, WIN_W + 40),
        "y":          y0,
        "vx":         random.uniform(-0.55, 0.55),
        "vy":         random.uniform(0.45, 1.3) if is_sak else random.uniform(0.85, 2.3),
        "angle":      random.uniform(0.0, 360.0),
        "angle_v":    random.uniform(-2.0, 2.0),
        "wb_ph":      random.uniform(0.0, math.tau),
        "wb_sp":      random.uniform(0.016, 0.038),
        "wb_amp":     random.uniform(0.30, 1.05),
        "size":       random.uniform(4.0, 8.0) if is_sak else random.uniform(7.0, 14.0),
        "alpha":      random.randint(148, 228),
        "color":      random.choice(cols),
    }


def _wx_dust_new(full_screen: bool = False) -> dict:
    """生成一顆陽光光塵粒子。"""
    src_x = int(WIN_W * 0.42)
    y0    = (random.uniform(0, WIN_H) if full_screen
             else random.uniform(WIN_H * 0.6, WIN_H))
    return {
        "wt":       "dust",
        "x":        random.uniform(src_x - 280, src_x + 280),
        "y":        y0,
        "vx":       random.uniform(-0.12, 0.12),
        "vy":       random.uniform(-0.22, -0.55),
        "size":     random.uniform(2.0, 4.5),
        "alpha":    random.randint(22, 65),
        "pb_ph":    random.uniform(0.0, math.tau),
        "pb_sp":    random.uniform(0.02, 0.05),
    }


def _wx_rain_new(full_screen: bool = False) -> dict:
    """生成一滴雨粒子。"""
    y0 = (random.uniform(-WIN_H, WIN_H) if full_screen
          else random.uniform(-60, -10))
    return {
        "wt":     "rain",
        "x":      random.uniform(-20, WIN_W + 80),
        "y":      y0,
        "speed":  random.uniform(13.0, 22.0),
        "length": random.randint(10, 20),
        "alpha":  random.randint(100, 190),
    }


# 霧團顏色組（冷灰白系）
_WX_FOG_PALETTE = [
    (218, 224, 232),
    (228, 232, 238),
    (212, 220, 230),
    (225, 228, 235),
    (220, 226, 234),
]


def _wx_fog_new(full_screen: bool = False) -> dict:
    """生成一團霧粒子（大型半透明橢圓，緩慢飄移）。"""
    w = random.randint(180, 500)
    h = random.randint(55, 175)
    if full_screen:
        x0 = random.uniform(-w, WIN_W + w)
        y0 = random.uniform(-h * 0.5, WIN_H + h * 0.3)
    else:
        # 從左側螢幕外緣進入
        x0 = random.uniform(-w - 20, -w + 5)
        y0 = random.uniform(-h * 0.3, WIN_H + h * 0.2)
    return {
        "wt":       "fog",
        "x":        x0,
        "y":        y0,
        "vx":       random.uniform(0.10, 0.38),    # 緩慢向右飄
        "vy":       random.uniform(-0.06, 0.06),   # 微幅上下漂動
        "w":        w,
        "h":        h,
        "alpha":    random.randint(16, 44),         # 極淡
        "pulse_ph": random.uniform(0.0, math.tau),
        "pulse_sp": random.uniform(0.004, 0.012),
        "col":      random.choice(_WX_FOG_PALETTE),
    }


# ── 初始化 / 重置 ─────────────────────────────────────────────

def _weather_reset() -> None:
    """隨機挑選天氣並初始化粒子池（每週呼叫一次）。"""
    _weather_type[0] = random.choice(_WEATHER_TYPES)
    _weather_pts.clear()
    wt = _weather_type[0]

    if wt in ("leaves_green", "leaves_orange", "sakura"):
        cnt = 72 if wt == "sakura" else 52
        for _ in range(cnt):
            _weather_pts.append(_wx_leaf_new(wt, full_screen=True))

    elif wt == "sun":
        for _ in range(32):
            _weather_pts.append(_wx_dust_new(full_screen=True))

    elif wt == "rain":
        for _ in range(240):
            _weather_pts.append(_wx_rain_new(full_screen=True))

    elif wt == "fog":
        for _ in range(26):
            _weather_pts.append(_wx_fog_new(full_screen=True))


# ── 多邊形旋轉輔助 ───────────────────────────────────────────

def _wx_rotate(pts, angle_rad: float, cx: float, cy: float):
    """將點列表繞 (cx, cy) 旋轉 angle_rad，回傳新列表（避免 Surface 旋轉開銷）。"""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    result = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        result.append((cx + dx * cos_a - dy * sin_a,
                       cy + dx * sin_a + dy * cos_a))
    return result


# ── 每幀繪製入口 ─────────────────────────────────────────────

def _draw_weather(surf: pygame.Surface, ms: int) -> None:
    """
    繪製目前天氣特效並更新粒子位置。
    應在 _draw_game_bg() 之後、所有 UI 元件之前呼叫。
    """
    wt = _weather_type[0]
    if wt is None:
        return
    if wt == "sun":
        _wx_draw_sun(surf, ms)
    elif wt == "rain":
        _wx_draw_rain(surf)
    elif wt == "fog":
        _wx_draw_fog(surf)
    else:
        _wx_draw_leaves(surf)


# ── 陽光灑落 ─────────────────────────────────────────────────

def _wx_draw_sun(surf: pygame.Surface, ms: int) -> None:
    """陽光灑落：半透明光柱 + 漂浮光塵。"""
    t    = ms * 0.001
    sx   = int(WIN_W * 0.42)
    sy   = -55
    dist = WIN_W + WIN_H

    # ── 光柱（用單張 SRCALPHA 面，只建一次可接受）────────────
    ray_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    # (中心角度, 半角寬, 基礎透明度)
    RAY_DEFS = [
        (52,   7,  38),
        (68,  13,  50),
        (84,   8,  35),
        (100, 15,  52),
        (117,  9,  40),
        (134, 11,  44),
    ]
    for ang, hw, base_a in RAY_DEFS:
        pulse = 0.5 + 0.5 * math.sin(t * 0.55 + ang * 0.038)
        a     = int(base_a * (0.72 + 0.28 * pulse))
        a1    = math.radians(ang - hw)
        a2    = math.radians(ang + hw)
        p1    = (sx + math.cos(a1) * dist, sy + math.sin(a1) * dist)
        p2    = (sx + math.cos(a2) * dist, sy + math.sin(a2) * dist)
        pygame.draw.polygon(ray_surf, (255, 218, 100, a), [(sx, sy), p1, p2])
    surf.blit(ray_surf, (0, 0))

    # ── 光源暈圈 ─────────────────────────────────────────────
    halo = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    halo_cy = sy + 65
    for r in range(180, 0, -18):
        ha = int(18 * (1.0 - r / 180.0) * (0.85 + 0.15 * math.sin(t * 1.1)))
        if ha > 0:
            pygame.draw.circle(halo, (255, 240, 160, ha), (sx, halo_cy), r)
    surf.blit(halo, (0, 0))

    # ── 光塵粒子 ─────────────────────────────────────────────
    dust_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    for p in _weather_pts:
        p["x"]    += p["vx"]
        p["y"]    += p["vy"]
        p["pb_ph"] += p["pb_sp"]
        if p["y"] < -10:
            p.update(_wx_dust_new())
        pulse_a = 0.6 + 0.4 * math.sin(p["pb_ph"])
        a       = int(p["alpha"] * pulse_a)
        r       = max(1, int(p["size"]))
        pygame.draw.circle(dust_surf, (255, 245, 200, a),
                           (int(p["x"]), int(p["y"])), r)
    surf.blit(dust_surf, (0, 0))


# ── 葉子 / 花瓣飄落 ──────────────────────────────────────────

def _wx_draw_leaves(surf: pygame.Surface) -> None:
    """葉子 / 花瓣飄落：純多邊形旋轉，不建立額外 Surface。"""
    # 用一張共用 SRCALPHA Surface 支援透明度
    leaf_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

    for p in _weather_pts:
        # ── 更新位置 ─────────────────────────────────────────
        p["wb_ph"]  += p["wb_sp"]
        p["x"]      += p["vx"] + math.sin(p["wb_ph"]) * p["wb_amp"]
        p["y"]      += p["vy"]
        p["angle"]   = (p["angle"] + p["angle_v"]) % 360.0

        if p["y"] > WIN_H + 40:
            p.update(_wx_leaf_new(p["wt"]))
            continue

        # ── 繪製葉形多邊形 ───────────────────────────────────
        cx, cy = p["x"], p["y"]
        sz     = p["size"]
        col    = (*p["color"], p["alpha"])
        ar     = math.radians(p["angle"])
        wt     = p["wt"]

        if wt == "sakura":
            # 橢圓花瓣：四點鑽石形
            r1, r2 = sz, sz * 0.52
            base = [(cx, cy - r1), (cx + r2, cy), (cx, cy + r1), (cx - r2, cy)]
        else:
            # 葉形：頂端尖、底部稍圓的菱形
            base = [
                (cx,           cy - sz),
                (cx + sz*0.46, cy - sz*0.05),
                (cx + sz*0.30, cy + sz*0.65),
                (cx,           cy + sz*0.80),
                (cx - sz*0.30, cy + sz*0.65),
                (cx - sz*0.46, cy - sz*0.05),
            ]

        pts = _wx_rotate(base, ar, cx, cy)
        try:
            pygame.draw.polygon(leaf_surf, col, pts)
            # 葉脈（僅非花瓣）
            if wt != "sakura" and sz > 9:
                tip = _wx_rotate([(cx, cy - sz)], ar, cx, cy)[0]
                bot = _wx_rotate([(cx, cy + sz*0.80)], ar, cx, cy)[0]
                pygame.draw.line(leaf_surf,
                                 (min(255, p["color"][0]+25),
                                  min(255, p["color"][1]+25),
                                  min(255, p["color"][2]+25), p["alpha"]),
                                 (int(tip[0]), int(tip[1])),
                                 (int(bot[0]), int(bot[1])), 1)
        except Exception:
            pass

    surf.blit(leaf_surf, (0, 0))


# ── 濃霧繚繞 ─────────────────────────────────────────────────

def _wx_draw_fog(surf: pygame.Surface) -> None:
    """濃霧繚繞：大型半透明橢圓霧團緩慢漂移，疊加淡灰色氛圍遮罩。"""
    # 整體氛圍遮罩（輕描淡寫的冷灰調）
    atm = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    atm.fill((210, 215, 225, 30))
    surf.blit(atm, (0, 0))

    fog_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    for p in _weather_pts:
        p["x"]        += p["vx"]
        p["y"]        += p["vy"]
        p["pulse_ph"] += p["pulse_sp"]

        # 離開右邊界後從左側重入
        if p["x"] - p["w"] // 2 > WIN_W + 60:
            p.update(_wx_fog_new())
            continue

        # 脈動透明度（霧氣若隱若現）
        a = int(p["alpha"] * (0.70 + 0.30 * math.sin(p["pulse_ph"])))
        if a <= 0:
            continue

        rect = pygame.Rect(
            int(p["x"] - p["w"] // 2),
            int(p["y"] - p["h"] // 2),
            p["w"], p["h"],
        )
        # 主霧體
        pygame.draw.ellipse(fog_surf, (*p["col"], a), rect)
        # 霧心稍亮（增加立體感）
        inner = pygame.Rect(
            rect.x + rect.w // 4, rect.y + rect.h // 4,
            rect.w // 2, rect.h // 2,
        )
        pygame.draw.ellipse(fog_surf, (*p["col"], min(255, a + 12)), inner)

    surf.blit(fog_surf, (0, 0))

    # 底部地面霧（靜態漸層帶，增強霧氣厚重感）
    ground_fog = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    for row in range(60):
        layer_a = int(22 * (1.0 - row / 60.0) ** 1.6)
        y_row   = WIN_H - row * 3
        pygame.draw.line(ground_fog, (220, 225, 232, layer_a),
                         (0, y_row), (WIN_W, y_row))
    surf.blit(ground_fog, (0, 0))


# ── 陰雨綿綿 ─────────────────────────────────────────────────

def _wx_draw_rain(surf: pygame.Surface) -> None:
    """陰雨綿綿：深灰半透明遮罩 + 斜向雨滴線條。"""
    # 陰暗遮罩
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((45, 50, 65, 95))
    surf.blit(ov, (0, 0))

    # 雨滴
    rain_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    slant     = -0.32   # 斜度（偏左）
    for p in _weather_pts:
        p["y"] += p["speed"]
        p["x"] += p["speed"] * slant
        if p["y"] > WIN_H + 10 or p["x"] < -30:
            p.update(_wx_rain_new())
            continue
        le = p["length"]
        x0, y0 = int(p["x"]), int(p["y"])
        x1 = int(x0 + le * slant)
        y1 = int(y0 + le)
        pygame.draw.line(rain_surf,
                         (175, 195, 220, p["alpha"]),
                         (x0, y0), (x1, y1), 1)
    surf.blit(rain_surf, (0, 0))


# ============================================================
#  點擊波紋特效系統
# ============================================================
# 每次 MOUSEBUTTONDOWN 觸發：三層擴散光環 + 中心爆閃 + 十字光芒 +
# 8 顆外射星形光點，全程 650 ms，最多同時 6 個疊加。
# ============================================================

_click_effects: list = []    # 進行中的特效清單
_CLICK_MS       = 650        # 每個特效存活時間（ms）
_CLICK_MAX      = 6          # 最多同時存在幾個

_CLICK_SPARK_COLS = [
    (255, 240, 140),   # 暖金
    (255, 220,  90),   # 琥珀金
    (255, 255, 210),   # 淡黃白
    (255, 200, 120),   # 橙金
    (255, 250, 180),   # 奶黃
    (255, 235, 160),   # 柔金
]


def _click_spawn(x: int, y: int, ms: int) -> None:
    """在螢幕座標 (x, y) 處生成一個點擊特效。"""
    n      = 8
    sparks = []
    for i in range(n):
        angle = math.tau * i / n + random.uniform(-0.20, 0.20)
        sparks.append({
            "angle": angle,
            "dist":  random.uniform(48, 92),
            "sz":    random.uniform(2.5, 4.8),
            "col":   random.choice(_CLICK_SPARK_COLS),
        })
    _click_effects.append({"x": x, "y": y, "t0": ms, "sparks": sparks})
    # 超過上限時移除最舊的
    while len(_click_effects) > _CLICK_MAX:
        _click_effects.pop(0)


def _draw_click_effects(surf: pygame.Surface, ms: int) -> None:
    """
    繪製所有進行中的點擊波紋特效。
    應在 pygame.display.flip() 之前、所有其他繪製之後呼叫，
    確保特效顯示在最頂層。
    """
    if not _click_effects:
        return

    fx = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    dead: list = []

    for ef in _click_effects:
        elapsed = ms - ef["t0"]
        if elapsed >= _CLICK_MS:
            dead.append(ef)
            continue

        t  = elapsed / _CLICK_MS          # 0.0 → 1.0，進度比例
        cx = ef["x"]
        cy = ef["y"]

        # ── 中心爆閃（前 28% 時段）──────────────────────────
        if t < 0.28:
            bt = t / 0.28                               # 0→1 in first 28%
            br = int(15 * (1.0 - bt))
            ba = int(255 * (1.0 - bt) ** 1.3)
            if br > 0 and ba > 0:
                pygame.draw.circle(fx, (255, 255, 255, ba), (cx, cy), br)
                pygame.draw.circle(fx, (255, 240, 160, ba // 3), (cx, cy), br + 7)

        # ── 十字光芒（前 38% 時段，類鏡頭光暈）──────────────
        if t < 0.38:
            ct    = t / 0.38
            clen  = int(26 * (1.0 - ct ** 0.75))
            ca    = int(190 * (1.0 - ct) ** 1.5)
            if ca > 0 and clen > 0:
                w2 = 2
                for ddx, ddy in ((clen,0),(-clen,0),(0,clen),(0,-clen)):
                    pygame.draw.line(fx, (255, 255, 200, ca),
                                     (cx, cy), (cx + ddx, cy + ddy), w2)

        # ── Ring A：快速內環（ease-out-cubic）────────────────
        ease_a = 1.0 - (1.0 - t) ** 3
        r1     = int(ease_a * 88)
        a1     = int(220 * max(0.0, 1.0 - t * 2.3) ** 1.7)
        if r1 > 0 and a1 > 0:
            pygame.draw.circle(fx, (255, 248, 175, a1), (cx, cy), r1, 2)

        # ── Ring B：中速中環 ──────────────────────────────────
        ease_b = 1.0 - (1.0 - t) ** 2.4
        r2     = int(ease_b * 145)
        a2     = int(175 * max(0.0, 1.0 - t * 1.65) ** 1.9)
        if r2 > 0 and a2 > 0:
            pygame.draw.circle(fx, (255, 215, 105, a2), (cx, cy), r2, 2)
            # 內側加一圈更淡的輝光，讓環更有厚度感
            if r2 > 3:
                pygame.draw.circle(fx, (255, 230, 140, a2 // 3), (cx, cy), r2 - 3, 1)

        # ── Ring C：慢速外環（最薄，最遠）───────────────────
        ease_c = t ** 0.65
        r3     = int(ease_c * 210)
        a3     = int(135 * max(0.0, 1.0 - t * 1.25) ** 2.3)
        if r3 > 0 and a3 > 0:
            pygame.draw.circle(fx, (255, 240, 170, a3), (cx, cy), r3, 1)

        # ── 外射星形光點 ─────────────────────────────────────
        for spark in ef["sparks"]:
            sp_t   = min(t * 1.45, 1.0)
            ease_s = 1.0 - (1.0 - sp_t) ** 2.8   # ease-out
            dist   = spark["dist"] * ease_s
            sa     = int(245 * max(0.0, 1.0 - t * 1.55) ** 1.6)
            if sa <= 0:
                continue
            sx  = cx + math.cos(spark["angle"]) * dist
            sy  = cy + math.sin(spark["angle"]) * dist
            sz  = max(1, int(spark["sz"] * (1.0 - t * 0.68)))
            col = (*spark["col"], sa)
            pygame.draw.circle(fx, col, (int(sx), int(sy)), sz)
            # 每顆光點加小十字，做出星芒感
            if sz >= 2 and sa > 55:
                slen = sz + 2
                sa2  = sa // 3
                pygame.draw.line(fx, (255, 255, 255, sa2),
                                 (int(sx) - slen, int(sy)),
                                 (int(sx) + slen, int(sy)), 1)
                pygame.draw.line(fx, (255, 255, 255, sa2),
                                 (int(sx), int(sy) - slen),
                                 (int(sx), int(sy) + slen), 1)

    for ef in dead:
        _click_effects.remove(ef)

    surf.blit(fx, (0, 0))


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

def ask_subject_popup(title: str, options: list) -> int:
    """
    在畫面中央顯示科目選擇彈出視窗。
    options: 字串列表（或帶 'name' key 的 dict 列表）。
    回傳：1-based 選擇索引（不提供「返回」選項，玩家必須選一科）。
    """
    labels = [opt["name"] if isinstance(opt, dict) else str(opt) for opt in options]
    _cmd_q.put(("subj_popup", title, labels))
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
           no_label:  str = "否",
           show_ctx:  bool = True) -> bool:
    """取代 y/N 型的 input()：顯示自定義標籤按鈕，回傳 True / False。
    show_ctx=False 時不附帶 log 背景，只顯示 prompt 本身。"""
    _cmd_q.put(("yn", prompt, yes_label, no_label, show_ctx))
    _reply_event.clear()
    _reply_event.wait()
    return _reply_val[0]

def ask_ok(text: str) -> None:
    """顯示突發事件通知彈窗（單一「確認」按鈕），block 直到玩家確認。
    text 格式：「前綴：【事件名】\\n描述文字」"""
    _cmd_q.put(("event_ok", text))
    _reply_event.clear()
    _reply_event.wait()

def ask_exam_start(exam_name: str) -> None:
    """在底部行動面板顯示單一「準備期中考」/「準備期末考」大按鈕，
    阻塞直到玩家點擊後才繼續（進入考試流程）。"""
    _reply_event.clear()
    _cmd_q.put(("exam_ready", exam_name))
    _reply_event.wait()

def tell_story(lines: list) -> None:
    """顯示劇情對話框，每次點擊推進一行，全部結束後解除阻塞。
    lines: list of str 或 {"speaker": str, "text": str}。
    傳入 str 時自動偵測說話者：「開頭→我；X：開頭→X；其他→旁白。"""
    def _normalize(entry):
        if isinstance(entry, dict):
            return entry
        t = str(entry)
        if t.startswith("「") or t.startswith('"'):
            return {"speaker": "我", "text": t}
        colon_pos = t.find("：")
        if 0 < colon_pos <= 5:
            return {"speaker": t[:colon_pos], "text": t}
        return {"speaker": "旁白", "text": t}
    _cmd_q.put(("story", [_normalize(e) for e in lines]))
    _reply_event.clear()
    _reply_event.wait()

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

def trigger_time_overflow_warning():
    """
    觸發「時間不足」警告特效：
    剩餘時間點文字紅色閃動 + 左右震動，同時播放 damage6 音效。
    由 turn_engine 在玩家即將將時間扣成負數時呼叫。
    """
    _cmd_q.put(("time_overflow_warn", None))

def trigger_screen_shake() -> None:
    """觸發全螢幕短暫劇烈晃動效果（突發事件出現時）。非阻塞。"""
    _cmd_q.put(("screen_shake",))

def set_roll_call(course: str) -> None:
    """設定本週點名科目，在成績面板左側顯示警示便利貼。非阻塞。"""
    _cmd_q.put(("roll_call_set", course))

def clear_roll_call() -> None:
    """清除點名警示便利貼（週末結算後呼叫）。非阻塞。"""
    _cmd_q.put(("roll_call_clear",))

def set_special_disabled(names: dict) -> None:
    """更新特殊行動的停用狀態。names = {行動名: 倒數格數}（空 dict 表示清除全部）。"""
    _cmd_q.put(("special_disabled", dict(names)))

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

def ask_cc_portrait() -> str:
    """讓玩家選擇人物外觀（b1 / g1），回傳前綴字串。"""
    _cc_reply_event.clear()
    _cmd_q.put(("cc_portrait",))
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

def ask_cc_stats(total_pts: int, base_pts: int = 0, talent: dict = None, de_level: dict = None) -> tuple:
    """顯示能力點分配畫面，回傳 (stamina, intel, luck)。"""
    _cmd_q.put(("cc_stats", total_pts, base_pts, talent or {}, de_level or {}))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_de_level(levels: list) -> dict:
    """顯示年級卡片（單選），回傳選中的年級字典。"""
    _cmd_q.put(("cc_de_level", levels))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_talent(slot_results: list) -> None:
    """觸發拉霸機天賦動畫，3 個結果由呼叫方預先決定。阻塞直到玩家點繼續。"""
    _cmd_q.put(("cc_slot", list(slot_results)))
    _cc_reply_event.clear()
    _cc_reply_event.wait()

def ask_cc_extra_events(events_data: list, intel: int) -> list:
    """顯示額外事件選擇畫面，回傳選中的事件 ID 列表。"""
    _cmd_q.put(("cc_extra", list(events_data), intel))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def ask_cc_summary(data: dict) -> str:
    """顯示玩家資訊一覽卡片，回傳 'start' 或 'restart'。"""
    _cmd_q.put(("cc_summary", dict(data)))
    _cc_reply_event.clear()
    _cc_reply_event.wait()
    return _cc_reply_val[0]

def show_extra_event_popup(lines: list, title: str, border_color: tuple) -> None:
    """顯示帶彩色邊框的事件通知彈窗，阻塞直到玩家點確認。"""
    body = "\n".join(str(l) for l in lines if l)
    text = f"{title}\n{body}" if body else title
    _cmd_q.put(("event_ok_col", text, border_color))
    _reply_event.clear()
    _reply_event.wait()

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
    _popup_lines.extend(lines)   # 保留 tuple 型別（"multi" 多色行、(text,col) 標注行）
    _popup_title[0] = title
    _now = pygame.time.get_ticks()
    _popup_t0[0]        = _now
    _action_flash_t0[0] = _now   # 觸發全螢幕白光閃爍

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
    """優先微軟正黑體，再依序嘗試其他能渲染中文的系統字型。"""
    candidates = [
        "microsoft jhenghei", "microsoftjhenghei",   # 微軟正黑體（繁體）
        "microsoftyahei", "microsoft yahei",           # 微軟雅黑（簡體）
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


def _get_font_bold(size: int):
    """粗體版字型，優先微軟正黑體 Bold。"""
    candidates = [
        "microsoft jhenghei", "microsoftjhenghei",
        "microsoftyahei", "microsoft yahei",
        "simsun", "nsimsun",
        "arial unicode ms",
        "noto sans cjk tc", "noto sans tc",
    ]
    for name in candidates:
        try:
            f = pygame.font.SysFont(name, size, bold=True)
            f.render("測", True, WHITE)
            return f
        except Exception:
            pass
    return pygame.font.SysFont(None, size, bold=True)


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


def _request_week_bg(name: "str | None") -> None:
    """
    請求切換遊戲底圖（帶 crossfade）。
    name = None 或圖片不存在時：保持當前背景，不做任何切換。
    若有正在進行中的 fade，立即完成後再開始新 fade。
    """
    if name is None:
        return
    surf = _bg_surfs.get(name)
    if surf is None:
        return   # 待補圖片：保持現狀
    # 檢查目標是否已是當前（或進行中目標）
    effective = _bg_target[0] if _bg_target[0] is not None else _bg_current[0]
    if surf is effective:
        return
    # 強制完成任何進行中的 fade（重置 alpha）
    if _bg_target[0] is not None:
        _bg_target[0].set_alpha(255)
        _bg_current[0] = _bg_target[0]
        _bg_target[0]  = None
        _bg_fade_t0[0] = 0
    if surf is _bg_current[0]:
        return   # 完成舊 fade 後目標與 current 相同
    # 若目前完全沒有背景（遊戲剛啟動前），直接設定不淡入
    if _bg_current[0] is None:
        _bg_current[0] = surf
        return
    # 開始 crossfade
    _bg_target[0]  = surf
    surf.set_alpha(0)
    _bg_fade_t0[0] = pygame.time.get_ticks()


def _draw_game_bg(surf: pygame.Surface) -> None:
    """
    繪製遊戲底圖，處理 crossfade 過渡效果。
    - 無 fade 時：直接 blit 當前背景
    - fade 進行中：先畫 current，再把 target 以遞增 alpha 疊上
    - fade 結束：自動 swap current ← target
    """
    cur = _bg_current[0] if _bg_current[0] is not None else _grads.get("bg")
    if cur is None:
        surf.fill(BG)
    else:
        surf.blit(cur, (0, 0))

    if _bg_target[0] is None or _bg_fade_t0[0] == 0:
        return

    elapsed = pygame.time.get_ticks() - _bg_fade_t0[0]
    if elapsed >= BG_FADE_MS:
        # Fade 完成：還原 alpha，swap
        _bg_target[0].set_alpha(255)
        _bg_current[0] = _bg_target[0]
        _bg_target[0]  = None
        _bg_fade_t0[0] = 0
        surf.blit(_bg_current[0], (0, 0))
    else:
        alpha = int(255 * elapsed / BG_FADE_MS)
        _bg_target[0].set_alpha(alpha)
        surf.blit(_bg_target[0], (0, 0))


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

    _dn = player.de_level.get("name", "") if hasattr(player, "de_level") else ""
    surf.blit(fm.render(f"【{player.name}】 {player.department}{' ' + _dn if _dn else ''}", True, TITLE), (x, y))
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
    sc = YELLOW
    pygame.draw.rect(surf, DARK_GRAY, (x, y, bw, bh))
    pygame.draw.rect(surf, sc, (x, y, int(bw * sr), bh))
    surf.blit(fs.render(f"自我滿足度 {player.satisfaction}%", True, WHITE),
              (x + bw + 8, y))
    y += bh + gap

    if player.status_effects:
        eff = "  ".join(
            k if v == 0 else f"{k} {v}週"
            for k, v in player.status_effects.items()
        )
        surf.blit(fs.render(eff, True, RED), (x, y))


def _draw_icon_cart(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """購物車小圖示（純 pygame.draw，不使用外部資源）。"""
    # r 為半高基準；整體大小約 r*2.2 × r*1.8
    body_w = max(6, int(r * 1.8))
    body_h = max(4, int(r * 1.1))
    bx     = cx - body_w // 2
    by     = cy - body_h // 2 + max(1, r // 5)   # 略下移讓圖示視覺居中

    # 車身（圓角矩形）
    pygame.draw.rect(surf, (93, 64, 55), pygame.Rect(bx, by, body_w, body_h), border_radius=2)
    pygame.draw.rect(surf, (140, 100, 65), pygame.Rect(bx, by, body_w, body_h), 1, border_radius=2)

    # 車架柄（左斜線 → 上延伸）
    handle_rx = bx - max(2, r // 3)
    handle_ty = by - max(3, int(r * 0.8))
    pygame.draw.line(surf, (93, 64, 55), (bx, by), (handle_rx, handle_ty), max(1, r // 5))

    # 車輪（兩個小圓）
    whl_r = max(2, r // 3)
    whl_y = by + body_h + whl_r
    pygame.draw.circle(surf, (93, 64, 55),  (bx + body_w // 4,         whl_y), whl_r)
    pygame.draw.circle(surf, (93, 64, 55),  (bx + body_w * 3 // 4,     whl_y), whl_r)
    pygame.draw.circle(surf, (200, 170, 130),(bx + body_w // 4,         whl_y), max(1, whl_r - 1))
    pygame.draw.circle(surf, (200, 170, 130),(bx + body_w * 3 // 4,     whl_y), max(1, whl_r - 1))


def _draw_week_calendar(surf: pygame.Surface,
                        fm, cx: int, cy: int, week: int) -> None:
    """
    日曆式週次顯示器：以翻頁日曆造型大字呈現當前週次。
    頂部深紅標題列 + 裝訂環 + 主體白底大字。
    """
    fb_xl = _font_bold_xl[0] or fm
    fmic  = _font_micro[0]

    CAL_W  = 108   # 日曆卡片寬度
    CAL_H  = 112   # 日曆卡片高度
    HDR_H  = 28    # 頂部紅色標題列高度
    RADIUS = 8
    RING_R = 5     # 裝訂環半徑

    sx = cx - CAL_W // 2
    sy = cy - CAL_H // 2
    outer = pygame.Rect(sx, sy, CAL_W, CAL_H)

    cal = pygame.Surface((CAL_W, CAL_H), pygame.SRCALPHA)

    # ── 主體（米白）────────────────────────────────────────────
    pygame.draw.rect(cal, (255, 249, 237, 255),
                     pygame.Rect(0, 0, CAL_W, CAL_H), border_radius=RADIUS)

    # ── 頂部標題列（深紅，僅上方圓角）─────────────────────────
    pygame.draw.rect(cal, (188, 50, 40, 255),
                     pygame.Rect(0, 0, CAL_W, HDR_H), border_radius=RADIUS)
    # 蓋掉標題列下方多餘的圓角（讓下邊緣平整）
    pygame.draw.rect(cal, (188, 50, 40, 255),
                     pygame.Rect(0, RADIUS, CAL_W, HDR_H - RADIUS))

    # 標題文字「本週」
    if fmic is not None:
        hdr_t = fmic.render("本  週", True, (255, 215, 195))
        cal.blit(hdr_t, ((CAL_W - hdr_t.get_width()) // 2,
                         (HDR_H - hdr_t.get_height()) // 2))

    # ── 裝訂環（位於頂邊，橫跨標題列上緣）─────────────────────
    for ring_cx in [CAL_W // 3, CAL_W * 2 // 3]:
        ring_cy = RING_R + 1
        # 環柱（深棕色小矩形）
        pygame.draw.rect(cal, (70, 46, 25),
                         pygame.Rect(ring_cx - 3, 0, 6, ring_cy + RING_R))
        # 外環
        pygame.draw.circle(cal, (110, 78, 44), (ring_cx, ring_cy), RING_R)
        # 孔洞
        pygame.draw.circle(cal, (35, 20, 10), (ring_cx, ring_cy), max(2, RING_R - 2))

    # ── 週次大字（置中於主體區域）──────────────────────────────
    body_y = HDR_H
    body_h = CAL_H - HDR_H
    week_t = fb_xl.render(f"第{week}週", True, (72, 38, 18))
    # 若文字超寬則改用 fb_lg
    if week_t.get_width() > CAL_W - 8:
        _fb_lg = _font_bold_lg[0] or fm
        week_t = _fb_lg.render(f"第{week}週", True, (72, 38, 18))
    cal.blit(week_t, ((CAL_W - week_t.get_width()) // 2,
                      body_y + (body_h - week_t.get_height()) // 2 - 2))

    # ── 底部細線裝飾（模擬日曆頁格線）─────────────────────────
    deco_y = CAL_H - 9
    pygame.draw.line(cal, (210, 195, 175),
                     (12, deco_y), (CAL_W - 12, deco_y))

    # ── 卡片邊框 ────────────────────────────────────────────────
    pygame.draw.rect(cal, (148, 108, 70, 255),
                     pygame.Rect(0, 0, CAL_W, CAL_H), 1, border_radius=RADIUS)

    # ── 投影 + 貼圖 ─────────────────────────────────────────────
    _soft_shadow(surf, outer, radius=RADIUS, alpha=52, offset=(0, 5))
    surf.blit(cal, (sx, sy))


def _get_intel_level_ui(intel: int) -> int:
    """根據智力數值回傳等階索引（0–4），供狀態欄顯示用。"""
    for lvl in range(len(_INTEL_THRESHOLDS_UI) - 1, -1, -1):
        if intel >= _INTEL_THRESHOLDS_UI[lvl]:
            return lvl
    return 0


def _draw_action_flash(surf: pygame.Surface, ms: int) -> None:
    """
    行動成功後的全螢幕白光閃爍。
    alpha 快速衰退，模擬瞬間強光感。
    """
    if _action_flash_t0[0] == 0:
        return
    elapsed = ms - _action_flash_t0[0]
    if elapsed >= _ACTION_FLASH_MS:
        _action_flash_t0[0] = 0
        return
    t     = elapsed / _ACTION_FLASH_MS          # 0 → 1
    alpha = int(210 * (1.0 - t) ** 1.6)         # 快速指數衰退
    flash = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    flash.fill((255, 255, 255, alpha))
    surf.blit(flash, (0, 0))


# ============================================================
#  小圖示繪製函式（純 pygame.draw，無需外部素材）
# ============================================================

def _draw_icon_coin(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """金幣圖示：立體金圓＋高光。r 為外圓半徑。"""
    # 陰影（右下偏移 1px）
    pygame.draw.circle(surf, (140, 100, 10), (cx + 1, cy + 1), r)
    # 主體（深金）
    pygame.draw.circle(surf, (210, 158, 24), (cx, cy), r)
    # 亮面（較淺金，去掉外緣 2px）
    if r > 3:
        pygame.draw.circle(surf, (248, 210, 60), (cx, cy), r - 2)
    # 高光點（左上）
    if r >= 6:
        pygame.draw.circle(surf, (255, 245, 160),
                           (cx - max(1, r // 3), cy - max(1, r // 3)),
                           max(1, r // 4))
    # 邊框（深金色）
    pygame.draw.circle(surf, (160, 115, 15), (cx, cy), r, 1)
    # 內環裝飾線
    if r >= 5:
        pygame.draw.circle(surf, (185, 140, 22), (cx, cy), max(1, r - 3), 1)


def _draw_icon_clock(surf: pygame.Surface, cx: int, cy: int, r: int,
                     col: tuple = (93, 64, 55)) -> None:
    """時鐘圖示：錶盤＋時針＋分針。col 控制邊框與指針顏色（支援動畫色）。"""
    face = (255, 250, 236)
    # 錶盤
    pygame.draw.circle(surf, face, (cx, cy), r)
    pygame.draw.circle(surf, col,  (cx, cy), r, 1)
    # 時針（短，指向 10 點方向）
    ha  = math.radians(-60)   # 10 點 = -60° from 12
    hx  = cx + int(math.sin(ha) * r * 0.50)
    hy  = cy - int(math.cos(ha) * r * 0.50)
    pygame.draw.line(surf, col, (cx, cy), (hx, hy), max(1, r // 5))
    # 分針（長，指向 12 點方向）
    mx2 = cx
    my2 = cy - int(r * 0.78)
    pygame.draw.line(surf, col, (cx, cy), (mx2, my2), max(1, r // 6))
    # 中心點
    pygame.draw.circle(surf, col, (cx, cy), max(1, r // 5))


def _draw_icon_brain(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """大腦圖示：兩半球 + 中央縱溝 + 腦回折痕弧線 + 高光。"""
    pink  = (232, 148, 148)   # 腦組織粉紅
    dark  = (175,  78,  78)   # 深玫瑰（輪廓 / 折痕）
    light = (252, 208, 208)   # 高光粉

    _pad = 2
    sz   = (r + _pad) * 2
    bs   = pygame.Surface((sz, sz), pygame.SRCALPHA)
    bx = by = sz // 2

    hl  = max(3, int(r * 0.60))            # 半球半徑
    sep = max(1, int(r * 0.26))            # 半球圓心離中軸距離
    hcy = by - max(1, int(r * 0.12))       # 半球圓心略偏上
    lhx = bx - sep                         # 左半球圓心 x
    rhx = bx + sep                         # 右半球圓心 x

    # ── 填充：左右半球 + 底部連接（小腦區）──────────────────
    pygame.draw.circle(bs, pink, (lhx, hcy), hl)
    pygame.draw.circle(bs, pink, (rhx, hcy), hl)
    bot_rect = pygame.Rect(bx - int(r * 0.55), by - int(r * 0.05),
                           int(r * 1.1), int(r * 0.75))
    pygame.draw.ellipse(bs, pink, bot_rect)

    # ── 輪廓 ─────────────────────────────────────────────────
    pygame.draw.circle(bs, dark, (lhx, hcy), hl, 1)
    pygame.draw.circle(bs, dark, (rhx, hcy), hl, 1)
    pygame.draw.ellipse(bs, dark, bot_rect, 1)

    # ── 中央縱溝 ─────────────────────────────────────────────
    pygame.draw.line(bs, dark,
                     (bx, hcy - hl + max(1, int(r * 0.15))),
                     (bx, by  + int(r * 0.55)), 1)

    # ── 腦回折痕（向下開口弧線＝溝回）──────────────────────
    fw = max(4, int(r * 0.55))
    fh = max(3, int(r * 0.38))
    fy = hcy - int(r * 0.05)
    pygame.draw.arc(bs, dark,
                    pygame.Rect(lhx - fw // 2, fy, fw, fh),
                    math.pi, math.tau, 1)   # 左半球折痕
    pygame.draw.arc(bs, dark,
                    pygame.Rect(rhx - fw // 2, fy, fw, fh),
                    math.pi, math.tau, 1)   # 右半球折痕

    # ── 高光 ─────────────────────────────────────────────────
    if r >= 6:
        pygame.draw.circle(bs, light,
                           (lhx - max(1, int(r * 0.18)),
                            hcy - max(1, int(r * 0.22))),
                           max(1, int(r * 0.18)))

    surf.blit(bs, (cx - bx, cy - by))


def _draw_icon_clover(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """四葉幸運草圖示。r 為整體半徑。"""
    leaf_r  = max(2, int(r * 0.48))
    offset  = max(2, int(r * 0.44))
    green   = (68, 178, 82)
    dark_g  = (38, 125, 52)
    shadow  = (30, 100, 42)
    # 四葉（上下左右），先畫陰影再畫本色
    for dx, dy in [(0, -offset), (0, offset), (-offset, 0), (offset, 0)]:
        pygame.draw.circle(surf, shadow, (cx + dx + 1, cy + dy + 1), leaf_r)
        pygame.draw.circle(surf, green,  (cx + dx,     cy + dy),     leaf_r)
    # 葉脈（細線，各葉從中心往葉頂）
    for dx, dy in [(0, -offset), (0, offset), (-offset, 0), (offset, 0)]:
        pygame.draw.line(surf, dark_g, (cx, cy),
                         (cx + dx, cy + dy), 1)
    # 莖（往下延伸）
    pygame.draw.line(surf, dark_g, (cx, cy + leaf_r),
                     (cx, cy + r + 3), max(1, r // 5))
    # 中心蓋住葉脈交叉點
    pygame.draw.circle(surf, dark_g, (cx, cy), max(1, leaf_r // 2))


def _draw_status_v2(surf, fm, fs, player, rect, mpos):
    """
    新版狀態欄（浮動卡片）：
      左側：圓形頭像 → 名字/系級/體力條/滿足感條 → 智力/運氣小標籤
      右側：道具店按鈕 + 金錢（靠右對齊道具店右緣）
    回傳道具店按鈕 Rect。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22

    M  = 8
    pr = pygame.Rect(rect.x + M, rect.y + M,
                     rect.width - M * 2, rect.height - M * 2)

    # ── 投影 ──────────────────────────────────────────────────
    sh = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 52),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(sh, (pr.x + 4, pr.y + 4))

    # ── 卡片底色 ──────────────────────────────────────────────
    card = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 244, 228, 238),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(card, pr.topleft)
    pygame.draw.rect(surf, CYAN, pr, 2, border_radius=14)

    if player is None:
        t = fm.render("等待角色資料…", True, GRAY)
        surf.blit(t, (pr.x + 20, pr.y + pr.height // 2 - t.get_height() // 2))
        shop_r = pygame.Rect(pr.right - 122, pr.y + (pr.height - 40) // 2, 118, 40)
        pygame.draw.rect(surf, DARK_GRAY, shop_r, border_radius=14)
        return shop_r, None

    # ── 圓形頭像（立繪 _head，若無則顯示姓名首字）─────────────
    av_cx = pr.x + 52
    av_cy = pr.y + 58
    av_r  = 42
    _head = _portrait_head_load(_portrait_prefix[0]) if _portrait_prefix[0] else None
    if _head:
        surf.blit(_head, (av_cx - av_r, av_cy - av_r))
    else:
        pygame.draw.circle(surf, PANEL, (av_cx, av_cy), av_r)
        init_ch = player.name[0] if player.name else "？"
        init_t  = fb_lg.render(init_ch, True, TITLE)
        surf.blit(init_t, (av_cx - init_t.get_width() // 2,
                           av_cy - init_t.get_height() // 2))
    pygame.draw.circle(surf, CYAN, (av_cx, av_cy), av_r, 3)

    # ── 名字 + 系級 + 狀態效果（同一行，純文字，無外框）────
    info_x = pr.x + 106
    info_y = pr.y + 14
    _de_name = player.de_level.get("name", "") if hasattr(player, "de_level") else ""
    _base_str = f"{player.name}  {player.department}{' ' + _de_name if _de_name else ''}"
    name_t = fb_lg.render(_base_str, True, WHITE)
    surf.blit(name_t, (info_x, info_y))
    # 狀態效果（接在年級後，紅色，無括號；v=0 表示條件型，不顯示週數）
    if player.status_effects:
        _eff_str = "  " + "  ".join(
            k if v == 0 else f"{k} {v}週"
            for k, v in player.status_effects.items()
        )
        _eff_t   = fb_lg.render(_eff_str, True, RED)
        surf.blit(_eff_t, (info_x + name_t.get_width(), info_y))
    # 名字下細線
    line_y = info_y + name_t.get_height() + 2
    pygame.draw.line(surf, (210, 190, 165),
                     (info_x, line_y), (info_x + name_t.get_width(), line_y), 1)

    # ── 體力條 / 滿足感條 ────────────────────────────────────
    # 標籤在左側，數值置中顯示於條內；兩列標籤對齊同一 x
    bar_h  = 22                          # 加粗（原 14）
    bar_w  = 280                         # 略縮，讓左側標籤有空間
    bar_gap = 8                          # 標籤與條之間的間距

    # 預算標籤寬度（取最寬者做對齊基準）
    _lbl_stam = fb.render("體力", True, WHITE)
    _lbl_sat  = fb.render("自我滿足度", True, WHITE)
    lbl_col_w = max(_lbl_stam.get_width(), _lbl_sat.get_width())
    bar_x     = info_x + lbl_col_w + bar_gap   # 兩條共同左起點

    bar_y  = line_y + 7
    ratio  = player.stamina / max(player.stamina_max, 1)

    # 標籤（右對齊於標籤欄）
    surf.blit(_lbl_stam,
              (info_x + lbl_col_w - _lbl_stam.get_width(),
               bar_y + (bar_h - _lbl_stam.get_height()) // 2))
    # 進度條底 + 填充 + 邊框
    pygame.draw.rect(surf, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h), border_radius=9)
    _fill_w = max(0, int(bar_w * ratio))
    if _fill_w > 0:
        pygame.draw.rect(surf, GREEN, (bar_x, bar_y, _fill_w, bar_h), border_radius=9)
    pygame.draw.rect(surf, GRAY, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=9)
    # 數值置中於整條
    _sv = fb.render(f"{player.stamina}/{player.stamina_max}", True, PANEL)
    surf.blit(_sv, (bar_x + (bar_w - _sv.get_width()) // 2,
                    bar_y + (bar_h - _sv.get_height()) // 2))

    sat_y  = bar_y + bar_h + 7
    sr_val = player.satisfaction / 100
    sat_c  = YELLOW

    # 滿足感條
    surf.blit(_lbl_sat,
              (info_x + lbl_col_w - _lbl_sat.get_width(),
               sat_y + (bar_h - _lbl_sat.get_height()) // 2))
    pygame.draw.rect(surf, DARK_GRAY, (bar_x, sat_y, bar_w, bar_h), border_radius=9)
    _fill_sw = max(0, int(bar_w * sr_val))
    if _fill_sw > 0:
        pygame.draw.rect(surf, sat_c, (bar_x, sat_y, _fill_sw, bar_h), border_radius=9)
    pygame.draw.rect(surf, GRAY, (bar_x, sat_y, bar_w, bar_h), 1, border_radius=9)
    _satv = fb.render(f"{player.satisfaction}%", True, PANEL)
    surf.blit(_satv, (bar_x + (bar_w - _satv.get_width()) // 2,
                      sat_y + (bar_h - _satv.get_height()) // 2))
    sat_t = _lbl_sat   # 供下方 sat_right 計算使用（取標籤寬度作基準）

    # ── 智力 / 運氣 小標籤 + 資訊一覽按鈕（頭像正下方）─────
    chip_y = pr.bottom - 42

    # 「資訊一覽」按鈕（最左）
    info_btn_w = 78
    info_btn_r = pygame.Rect(pr.x + 6, chip_y, info_btn_w, 30)
    _ib_hover  = info_btn_r.collidepoint(mpos)
    _ib_bg     = (100, 68, 38) if _ib_hover else (78, 52, 28)
    pygame.draw.rect(surf, _ib_bg, info_btn_r, border_radius=8)
    pygame.draw.rect(surf, GRAY,   info_btn_r, 1, border_radius=8)
    _ib_t = fb.render("資訊一覽", True, PANEL)
    surf.blit(_ib_t, (info_btn_r.x + (info_btn_r.width  - _ib_t.get_width())  // 2,
                      info_btn_r.y + (info_btn_r.height - _ib_t.get_height()) // 2))

    # 智力 chip（接在按鈕右側）
    intel_lvl  = _get_intel_level_ui(player.intel)
    lvl_name   = _INTEL_NAMES_UI[intel_lvl]
    lvl_col    = _INTEL_ANNOT_COLS_UI[intel_lvl]
    base_s     = fb.render(f"智力: {player.intel}", True, WHITE)
    lvl_s      = fb.render(f"（{lvl_name}）", True, lvl_col)
    _CR = 8
    _ISPACE = _CR * 2 + 5
    intel_chip_w = _ISPACE + base_s.get_width() + lvl_s.get_width() + 18
    intel_chip_x = info_btn_r.right + 8
    intel_chip_r = pygame.Rect(intel_chip_x, chip_y, intel_chip_w, 30)
    _draw_icon_brain(surf,
                     intel_chip_r.x + 9 + _CR,
                     intel_chip_r.centery, _CR)
    bx = intel_chip_r.x + 9 + _ISPACE
    by = intel_chip_r.y + (intel_chip_r.height - base_s.get_height()) // 2
    surf.blit(base_s, (bx, by))
    surf.blit(lvl_s,  (bx + base_s.get_width(), by))

    # 運氣（緊接在智力右側，間距 8px）
    luck_chip_x = intel_chip_r.right + 8
    lt = fb.render(f"運氣: {player.luck}", True, WHITE)
    luck_chip_w = _ISPACE + lt.get_width() + 18
    luck_chip_r = pygame.Rect(luck_chip_x, chip_y, luck_chip_w, 30)
    _draw_icon_clover(surf,
                      luck_chip_r.x + 9 + _CR,
                      luck_chip_r.centery, _CR)
    lbx = luck_chip_r.x + 9 + _ISPACE
    lby = luck_chip_r.y + (luck_chip_r.height - lt.get_height()) // 2
    surf.blit(lt, (lbx, lby))

    # ── 道具店按鈕（先計算，供金錢靠右對齊使用）─────────────
    shop_r = pygame.Rect(pr.right - 150, pr.y + (pr.height - 40) // 2, 118, 40)
    hover  = shop_r.collidepoint(mpos)
    dr     = _premium_btn(surf, shop_r, BTN_N, hover, radius=14)
    st     = fb_lg.render("道具店", True, PANEL)
    _CART_R  = 7                                          # 購物車圖示半高
    _CART_SP = 6                                          # 圖示與文字間距
    _total_w = _CART_R * 2 + _CART_SP + st.get_width()   # 圖示 + 間距 + 文字
    _btn_cx  = dr.x + dr.width  // 2
    _btn_cy  = dr.y + dr.height // 2
    _cart_cx = _btn_cx - _total_w // 2 + _CART_R
    _text_x  = _btn_cx - _total_w // 2 + _CART_R * 2 + _CART_SP
    _draw_icon_cart(surf, _cart_cx, _btn_cy, _CART_R)
    surf.blit(st, (_text_x, _btn_cy - st.get_height() // 2))

    # ── 金錢（金幣圖示 + 數字，靠右對齊道具店按鈕右邊緣）────
    _COIN_R   = 11                          # 金幣圖示半徑
    money_t   = fb_lg.render(f"{player.money}", True, YELLOW)
    _mtotal_w = _COIN_R * 2 + 5 + money_t.get_width()
    _mx0      = shop_r.right - _mtotal_w   # 整組左起點
    _mcy      = pr.y + 14 + money_t.get_height() // 2
    _draw_icon_coin(surf, _mx0 + _COIN_R, _mcy, _COIN_R)
    surf.blit(money_t, (_mx0 + _COIN_R * 2 + 5, pr.y + 14))

    # ── 考試倒數提示（道具店按鈕正下方，靠右對齊）──────────────
    _w = _week[0]
    if fb and _w > 0:
        if _w < 8:
            _cdwn_txt      = f"距離期中考還有 {8 - _w} 週"
            _cdwn_base_col = WHITE
            _cdwn_bg       = (80, 40, 10, 140)
        elif _w == 8:
            _cdwn_txt      = "期中考週！"
            _cdwn_base_col = RED
            _cdwn_bg       = (160, 30, 20, 170)
        elif _w < 16:
            _cdwn_txt      = f"距離期末考還有 {16 - _w} 週"
            _cdwn_base_col = WHITE
            _cdwn_bg       = (80, 40, 10, 140)
        else:
            _cdwn_txt      = "期末考週！"
            _cdwn_base_col = RED
            _cdwn_bg       = (160, 30, 20, 170)
        # 第 7、15 週：每秒 4 次閃爍
        if _w in (7, 15):
            _cdwn_col = RED if (pygame.time.get_ticks() % 250) < 125 else WHITE
        else:
            _cdwn_col = _cdwn_base_col
        _cdwn_s  = fb.render(_cdwn_txt, True, _cdwn_col)
        _cdwn_px, _cdwn_py = 12, 5
        _cdwn_w  = _cdwn_s.get_width()  + _cdwn_px * 2
        _cdwn_h  = _cdwn_s.get_height() + _cdwn_py * 2
        _cdwn_rx = shop_r.right - _cdwn_w
        _cdwn_ry = shop_r.bottom + 16
        _cdwn_pill = pygame.Surface((_cdwn_w, _cdwn_h), pygame.SRCALPHA)
        pygame.draw.rect(_cdwn_pill, _cdwn_bg,
                         pygame.Rect(0, 0, _cdwn_w, _cdwn_h), border_radius=10)
        surf.blit(_cdwn_pill, (_cdwn_rx, _cdwn_ry))
        surf.blit(_cdwn_s,    (_cdwn_rx + _cdwn_px, _cdwn_ry + _cdwn_py))

    # ── 週次日曆（條右邊緣 ↔ 道具店左 中間空白）──────────────
    sat_right  = bar_x + bar_w + 12   # 條右邊緣 + 間距
    money_left = shop_r.x - 12
    CAL_W      = 108
    ticker_cx  = (sat_right + money_left) // 2
    ticker_cy  = pr.y + pr.height // 2
    if money_left - sat_right >= CAL_W + 8:
        _draw_week_calendar(surf, fm, ticker_cx, ticker_cy, _week[0])

    return shop_r, info_btn_r


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
    fb_lg = _font_bold_lg[0] or fm
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
    title = fb_lg.render("請輸入角色名字", True, TITLE)
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
    t     = fb_lg.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok


def _draw_cc_portrait(surf, fm, fs, mpos):
    """
    角色外觀選擇畫面（CC 第 1.5 步）。
    左：b1_1（男角），右：g1_1（女角）。
    回傳 [(card_rect, prefix_str), ...] 供 _handle_cc_action 使用。
    """
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)

    # ── 標題 ──────────────────────────────────────────────────
    title_y = (WIN_H - 480) // 2 - 20
    _draw_float_label_card(surf, fm, "選擇人物外觀",
                           WIN_W // 2, title_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=0.0)

    # ── 卡片尺寸與位置 ────────────────────────────────────────
    CARD_W, CARD_H = 260, 420
    GAP            = 60
    total_w        = CARD_W * 2 + GAP
    base_x         = (WIN_W - total_w) // 2
    base_y         = (WIN_H - CARD_H) // 2 + 20
    rects_out      = []

    for i, (prefix, label) in enumerate([("b1", "男角"), ("g1", "女角")]):
        cx     = base_x + i * (CARD_W + GAP)
        card_r = pygame.Rect(cx, base_y, CARD_W, CARD_H)
        hover  = card_r.collidepoint(mpos)

        # 投影
        _soft_shadow(surf, card_r, radius=16, alpha=50, offset=(0, 6))
        # 卡片底色
        bg_col = (240, 228, 210) if hover else PANEL
        pygame.draw.rect(surf, bg_col, card_r, border_radius=16)
        pygame.draw.rect(surf, CYAN,   card_r, 2, border_radius=16)

        # 立繪（縮放置入卡片，底部對齊）
        img_key = f"{prefix}_1"
        img     = _portrait_scaled_load(img_key, CARD_W - 16, CARD_H - 56)
        if img:
            iw, ih = img.get_size()
            img_x  = card_r.x + (CARD_W - iw) // 2
            img_y  = card_r.y + CARD_H - 50 - ih
            surf.blit(img, (img_x, img_y))

        # 標籤
        lt = fb_lg.render(label, True, WHITE if hover else GRAY)
        surf.blit(lt, (card_r.x + (CARD_W - lt.get_width()) // 2,
                       card_r.bottom - 44))

        rects_out.append((card_r, prefix))

    return rects_out


def _draw_cc_dept(surf, fm, fs, options, mpos):
    """學院格狀卡片（4 欄），回傳各卡 (Rect, 1-based idx) 列表。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 格狀版型參數 ───────────────────────────────────────────
    COLS      = 4
    cw, ch    = 196, 64
    gap_x     = 14
    gap_y     = 12
    n         = len(options)
    n_rows    = (n + COLS - 1) // COLS
    label_h   = fm.get_height() + 22   # pad_y=11 × 2
    TITLE_GAP = 24
    grid_h    = n_rows * ch + (n_rows - 1) * gap_y
    total_h   = label_h + TITLE_GAP + grid_h
    top_y     = (WIN_H - total_h) // 2
    grid_y    = top_y + label_h + TITLE_GAP
    _draw_float_label_card(surf, fm, "選擇學院", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=0.0)
    rects = []
    for i, opt in enumerate(options):
        row = i // COLS
        col = i %  COLS
        # 最後一行若不滿 COLS，整排置中
        row_start = row * COLS
        row_end   = min(row_start + COLS, n)
        row_cnt   = row_end - row_start
        row_w     = row_cnt * cw + (row_cnt - 1) * gap_x
        sx        = (WIN_W - row_w) // 2
        rx        = sx + col * (cw + gap_x)
        ry        = grid_y + row * (ch + gap_y)
        r         = pygame.Rect(rx, ry, cw, ch)
        hover     = r.collidepoint(mpos)
        dr        = _premium_btn(surf, r, BTN_N, hover, radius=14)
        t         = fb_lg.render(opt, True, WHITE)
        surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                      dr.y + (dr.height - t.get_height()) // 2))
        rects.append((r, i + 1))
    return rects


def _draw_cc_drawbacks(surf, fm, fs, drawbacks, sel_indices, max_sel, mpos):
    """負面特質切換卡片，回傳 (card_rects, confirm_btn_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
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
        nt = fb_lg.render(d["name"], True, YELLOW if selected else WHITE)
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
    t     = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return card_rects, ok


def _draw_cc_stats(surf, fm, fs, total, base, talent, vals, raw, active, mpos, de_level=None):
    """能力點分配畫面，回傳 (minus_rects, plus_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
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
    bonus = total - base
    pts_label = f"{base}(+{bonus})" if bonus > 0 else str(total)
    info_text = f"可用點數：{pts_label}   已用：{used}   剩餘：{rem}   初始金錢 +{rem * 10} 元"
    _draw_float_label_card(surf, fs, info_text, WIN_W // 2, sub_y,
                           text_col=YELLOW, bg=(30, 15, 0), bg_alpha=128,
                           pad_x=16, pad_y=6, amp=7, speed=0.00170, phase=1.0)

    labels      = ["體力", "智力", "運氣"]
    talent_keys = ["stamina", "intel", "luck"]
    cx          = WIN_W // 2
    minus_rects = []
    plus_rects  = []

    # 更新輸入框 Rect 快取（與事件處理對齊）
    _cc_btn_cache["stats_boxes"] = [pygame.Rect(cx - 82, ry, box_w, box_h) for ry in row_y]

    for i, (label, ry) in enumerate(zip(labels, row_y)):
        # label
        lt = fb_lg.render(label, True, WHITE)
        surf.blit(lt, (cx - 230, ry + (box_h - lt.get_height()) // 2))
        # [-]
        mr    = pygame.Rect(cx - 130, ry, btn_sz, btn_sz)
        hover = mr.collidepoint(mpos)
        mr_dr = _premium_btn(surf, mr, BTN_N, hover, radius=10)
        mt    = fb_lg.render("－", True, WHITE)
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
        pt    = fb_lg.render("＋", True, WHITE)
        surf.blit(pt, (pr_dr.x + (pr_dr.width  - pt.get_width())  // 2,
                       pr_dr.y + (pr_dr.height - pt.get_height()) // 2))
        plus_rects.append(pr)
        # 天賦 + 年級加成標注
        t_bonus  = (talent   or {}).get(talent_keys[i], 0)
        dl_bonus = (de_level or {}).get(talent_keys[i], 0)
        total_bonus = t_bonus + dl_bonus
        if total_bonus:
            parts = []
            if t_bonus:  parts.append(f"+{t_bonus} 天賦")
            if dl_bonus: parts.append(f"+{dl_bonus} 年級")
            final_val = vals[i] + total_bonus
            ann_txt   = "  ".join(parts) + f"  →  最終 {final_val}"
            ann_s     = fs.render(ann_txt, True, YELLOW)
            ann_x     = pr.right + 14
            ann_y     = ry + (box_h - ann_s.get_height()) // 2
            surf.blit(ann_s, (ann_x, ann_y))

    # 可用時間加成提示（天賦 + 年級合計）
    bt_talent = (talent   or {}).get("base_time", 0)
    bt_de     = (de_level or {}).get("base_time", 0)
    bt_parts  = []
    if bt_talent: bt_parts.append(f"天賦 {'+' if bt_talent > 0 else ''}{bt_talent}")
    if bt_de:     bt_parts.append(f"年級 +{bt_de}")
    if bt_parts:
        bt_total = bt_talent + bt_de
        bt_note  = f"可用時間：基礎 10 {'+' if bt_total >= 0 else ''}{bt_total}  （{'，'.join(bt_parts)}）"
        bt_txt   = fs.render(bt_note, True, GRAY)
        surf.blit(bt_txt, ((WIN_W - bt_txt.get_width()) // 2,
                            row_y[-1] + box_h + 8))

    # 確認
    ok          = pygame.Rect((WIN_W - 160) // 2, ok_y, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = rem >= 0
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fb_lg.render("確認分配", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return minus_rects, plus_rects, ok


def _draw_cc_talent(surf, fm, fs, candidates, sel_idx, mpos):
    """天賦卡片（單選），回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
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
        nt = fb_lg.render(t_data["name"], True, YELLOW if selected else WHITE)
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
    t           = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return card_rects, ok


def _draw_cc_de_level(surf, fm, fs, levels, sel_idx, mpos):
    """年級卡片（單選），回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch    = 180, 200
    gap       = 20
    title_h   = fm.get_height() + 22
    TITLE_GAP = 28
    CARD_BTN  = 30
    btn_h     = 48
    total_h   = title_h + TITLE_GAP + ch + CARD_BTN + btn_h
    top_y     = (WIN_H - total_h) // 2
    sy        = top_y + title_h + TITLE_GAP

    _draw_float_label_card(surf, fm, "選擇年級", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=2.0)

    total_w = len(levels) * cw + (len(levels) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    buff_labels = [
        ("可用時間加成", "base_time"),
        ("智力",         "intel"),
        ("運氣",         "luck"),
    ]
    for i, lv in enumerate(levels):
        selected = (i == sel_idx)
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        bg_col   = (110, 72, 36) if selected else BTN_N
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        # 年級名稱
        nt = fb_lg.render(lv["name"], True, YELLOW if selected else WHITE)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 18))
        # buff 列表
        by = dr.y + 60
        for bl, bk in buff_labels:
            val = lv.get(bk, 0)
            sign = "+" if val >= 0 else ""
            color = GREEN if val > 0 else (GRAY if val == 0 else (200, 80, 80))
            bt = fs.render(f"{bl} {sign}{val}", True, color)
            surf.blit(bt, (dr.x + (dr.width - bt.get_width()) // 2, by))
            by += fs.get_height() + 5
        card_rects.append((r, i))

    ok          = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = sel_idx is not None
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return card_rects, ok


def _draw_cc_extra_events(surf, fm, fs, mpos):
    """額外事件選擇卡片，回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    now = pygame.time.get_ticks()

    cw, ch         = 220, 200
    gap            = 22
    title_h        = fm.get_height() + 22
    TITLE_SUB_GAP  = 12
    sub_h          = fs.get_height() + 12
    SUB_CARD_GAP   = 18
    CARD_BTN_GAP   = 30
    btn_h          = 48
    total_h = title_h + TITLE_SUB_GAP + sub_h + SUB_CARD_GAP + ch + CARD_BTN_GAP + btn_h
    top_y = (WIN_H - total_h) // 2
    sub_y = top_y + title_h + TITLE_SUB_GAP
    sy    = sub_y + sub_h + SUB_CARD_GAP

    _draw_float_label_card(surf, fm, "選擇額外事件", WIN_W // 2, top_y,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=4.0)
    _draw_float_label_card(surf, fs, "（可複選社團；打工與家教只能擇一；不選可直接確認）",
                           WIN_W // 2, sub_y, text_col=GRAY,
                           bg=(30, 20, 8), bg_alpha=115,
                           pad_x=16, pad_y=6, amp=7, speed=0.00170, phase=4.0)

    events = _cc_extra_data or []
    intel  = _cc_extra_intel[0]
    total_w = len(events) * cw + (len(events) - 1) * gap
    sx      = (WIN_W - total_w) // 2
    card_rects = []

    for i, ev in enumerate(events):
        ev_id    = ev["id"]
        selected = ev_id in _cc_extra_sel
        disabled = ev.get("intel_req", 0) > intel
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected and not disabled
        bg_col   = (50, 35, 20) if disabled else ((230, 108, 58) if selected else BTN_N)
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        name_col = GRAY if disabled else (YELLOW if selected else WHITE)
        nt = fb_lg.render(ev["name"], True, name_col)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 14))
        tc = ev.get("time_cost", 0)
        tc_col = GRAY if disabled else (RED if tc > 0 else GREEN)
        tc_t = fs.render(f"每週時間 -{tc}" if tc > 0 else "不佔時間", True, tc_col)
        surf.blit(tc_t, (dr.x + (dr.width - tc_t.get_width()) // 2, dr.y + 60))
        md = ev.get("money_delta", 0)
        md_col = GRAY if disabled else (GREEN if md > 0 else RED)
        sign = "+" if md >= 0 else ""
        md_t = fs.render(f"每週金錢 {sign}{md}", True, md_col)
        surf.blit(md_t, (dr.x + (dr.width - md_t.get_width()) // 2, dr.y + 90))
        ir = ev.get("intel_req", 0)
        if ir > 0:
            req_col = GRAY if disabled else (GREEN if intel >= ir else RED)
            req_t = fs.render(f"需要智力 ≥ {ir}", True, req_col)
            surf.blit(req_t, (dr.x + (dr.width - req_t.get_width()) // 2, dr.y + 126))
        if not disabled:
            card_rects.append((r, ev_id))

    # ── 互斥警告（右側浮動提示）──────────────────────────────
    warn_elapsed = now - _cc_extra_warn[0]
    if _cc_extra_warn[0] > 0 and warn_elapsed < 2200:
        if warn_elapsed < 280:
            w_alpha = int(255 * warn_elapsed / 280)
        elif warn_elapsed > 1700:
            w_alpha = int(255 * (2200 - warn_elapsed) / 500)
        else:
            w_alpha = 255
        w_alpha = max(0, min(255, w_alpha))
        wt    = fs.render("打工和家教只能二擇一", True, (255, 215, 60))
        ww    = wt.get_width() + 24
        wh    = wt.get_height() + 14
        wx    = WIN_W - ww - 18
        wy    = WIN_H // 2 - wh // 2
        ws    = pygame.Surface((ww, wh), pygame.SRCALPHA)
        pygame.draw.rect(ws, (40, 18, 8, min(220, w_alpha)), (0, 0, ww, wh), border_radius=8)
        pygame.draw.rect(ws, (*[min(255, int(c * w_alpha / 255)) for c in (235, 130, 30)], w_alpha),
                         (0, 0, ww, wh), 2, border_radius=8)
        surf.blit(ws, (wx, wy))
        wt_s = pygame.Surface(wt.get_size(), pygame.SRCALPHA)
        wt_s.blit(wt, (0, 0))
        wt_s.set_alpha(w_alpha)
        surf.blit(wt_s, (wx + 12, wy + 7))

    ok    = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (dr.x + (dr.width - t.get_width()) // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return card_rects, ok


def _draw_cc_summary(surf, fm, fs, mpos, game_mode=False):
    """
    玩家資訊一覽卡片。
    game_mode=False: CC 結束確認，有「進入本學期」「重新創建角色」兩按鈕，
                     回傳 (start_btn_rect, restart_btn_rect)。
    game_mode=True : 遊戲中查閱，有「關閉」按鈕，回傳 (close_btn_rect, None)。
    """
    fb    = _font_bold[0]    or fs
    fb_lg = _font_bold_lg[0] or fm
    data  = _cc_summary_data[0]

    if game_mode:
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surf.blit(ov, (0, 0))
    else:
        _draw_cc_bg(surf)

    # ── 卡片外框 ─────────────────────────────────────────────────
    cw = 700; ch = 500
    cx = (WIN_W - cw) // 2; cy = (WIN_H - ch) // 2

    # 陰影
    sh = pygame.Surface((cw + 8, ch + 8), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 55), (0, 0, cw + 8, ch + 8), border_radius=20)
    surf.blit(sh, (cx + 4, cy + 4))

    card_s = pygame.Surface((cw, ch), pygame.SRCALPHA)
    pygame.draw.rect(card_s, (255, 245, 228, 248), (0, 0, cw, ch), border_radius=18)
    surf.blit(card_s, (cx, cy))
    pygame.draw.rect(surf, CYAN, pygame.Rect(cx, cy, cw, ch), 2, border_radius=18)

    # ── 內容 ────────────────────────────────────────────────────
    pad = 28
    px = cx + pad; pw = cw - pad * 2
    py = cy + 16

    # 標題
    title_s = fb_lg.render("玩家資訊一覽", True, TITLE)
    surf.blit(title_s, (cx + (cw - title_s.get_width()) // 2, py))
    py += title_s.get_height() + 8
    pygame.draw.line(surf, (210, 185, 155), (px, py), (px + pw, py), 1)
    py += 10

    # 基本資料
    de_name  = data.get("de_level", {}).get("name", "")
    info_str = f"姓名：{data.get('name', '')}　　學院：{data.get('department', '')}　　年級：{de_name}"
    surf.blit(fm.render(info_str, True, WHITE), (px, py))
    py += fm.get_height() + 12

    # 能力值
    surf.blit(fb.render("【能力值】", True, TITLE), (px, py))
    py += fb.get_height() + 5

    raw_sta = data.get("stamina", 0)
    raw_int = data.get("intel", 0)
    raw_lck = data.get("luck", 0)
    money   = data.get("money", 0)
    ct      = data.get("combined_talent", {})
    dl      = data.get("de_level", {})

    if not game_mode:
        t_sta = ct.get("stamina", 0)
        t_int = ct.get("intel", 0)
        t_lck = ct.get("luck", 0)
        d_int = dl.get("intel", 0)
        d_lck = dl.get("luck", 0)
        sta_f = raw_sta + t_sta
        int_f = raw_int + t_int + d_int
        lck_f = raw_lck + t_lck + d_lck

        def _bstr(raw, tb, db=0):
            parts = [f"分配 {raw}"]
            if tb: parts.append(f"天賦 {'+' if tb > 0 else ''}{tb}")
            if db: parts.append(f"年級 +{db}")
            return "（" + "，".join(parts) + "）" if len(parts) > 1 else ""

        sta_str = f"體力：{sta_f}{_bstr(raw_sta, t_sta)}"
        int_str = f"智力：{int_f}{_bstr(raw_int, t_int, d_int)}"
        lck_str = f"運氣：{lck_f}{_bstr(raw_lck, t_lck, d_lck)}"
    else:
        sta_str = f"體力：{raw_sta}"
        int_str = f"智力：{raw_int}"
        lck_str = f"運氣：{raw_lck}"

    half = pw // 2
    surf.blit(fs.render(sta_str, True, WHITE), (px, py))
    surf.blit(fs.render(int_str, True, WHITE), (px + half, py))
    py += fs.get_height() + 4
    surf.blit(fs.render(lck_str, True, WHITE), (px, py))
    surf.blit(fs.render(f"金錢：{money}", True, YELLOW), (px + half, py))
    py += fs.get_height() + 12

    # 天賦
    surf.blit(fb.render("【天賦】", True, TITLE), (px, py))
    py += fb.get_height() + 5

    slots = data.get("slot_results", [])
    for i, t in enumerate(slots):
        is_null = t.get("name") == "無天賦"
        col = GRAY if is_null else WHITE
        desc = t.get("desc", "")
        line = f"槽 {i + 1}：{t.get('name', '')}"
        if desc:
            line += f"  —  {desc}"
        surf.blit(fs.render(line, True, col), (px + 10, py))
        py += fs.get_height() + 3
    if not slots:
        surf.blit(fs.render("（無）", True, GRAY), (px + 10, py))
        py += fs.get_height() + 3
    py += 8

    # 負面特質
    surf.blit(fb.render("【負面特質】", True, TITLE), (px, py))
    py += fb.get_height() + 5

    drawbacks = data.get("drawbacks", [])
    if drawbacks:
        for db in drawbacks:
            surf.blit(fs.render(f"{db['name']}  —  {db['desc']}", True, RED),
                      (px + 10, py))
            py += fs.get_height() + 3
    else:
        surf.blit(fs.render("（無）", True, GRAY), (px + 10, py))
        py += fs.get_height() + 3
    py += 8

    # 額外事件
    surf.blit(fb.render("【額外事件】", True, TITLE), (px, py))
    py += fb.get_height() + 5

    ev_ids  = data.get("extra_ev_ids", [])
    ev_map  = {e["id"]: e for e in data.get("extra_ev_data", [])}
    if ev_ids:
        for eid in ev_ids:
            ev = ev_map.get(eid)
            if not ev:
                continue
            tc = ev.get("time_cost", 0)
            md = ev.get("money_delta", 0)
            parts = []
            if tc > 0: parts.append(f"每週時間 -{tc}")
            if md != 0: parts.append(f"每週金錢 {'+' if md >= 0 else ''}{md}")
            line = ev["name"]
            if parts:
                line += "  —  " + "，".join(parts)
            surf.blit(fs.render(line, True, WHITE), (px + 10, py))
            py += fs.get_height() + 3
    else:
        surf.blit(fs.render("（無）", True, GRAY), (px + 10, py))
        py += fs.get_height() + 3

    # ── 按鈕區 ────────────────────────────────────────────────
    btn_y = cy + ch - 68
    pygame.draw.line(surf, (210, 185, 155), (px, btn_y), (px + pw, btn_y), 1)
    btn_y += 14

    if game_mode:
        close_r = pygame.Rect(cx + cw - pad - 130, btn_y, 130, 40)
        hover   = close_r.collidepoint(mpos)
        dr      = _premium_btn(surf, close_r, BTN_N, hover, radius=12)
        ct_s    = fb_lg.render("關閉", True, PANEL)
        surf.blit(ct_s, (dr.x + (dr.width - ct_s.get_width()) // 2,
                         dr.y + (dr.height - ct_s.get_height()) // 2))
        return close_r, None
    else:
        start_r   = pygame.Rect(cx + cw - pad - 140, btn_y, 140, 40)
        restart_r = pygame.Rect(start_r.x - 18 - 160, btn_y, 160, 40)

        h_s = start_r.collidepoint(mpos)
        dr_s = _premium_btn(surf, start_r, BTN_N, h_s, radius=12)
        t_s  = fb_lg.render("進入本學期", True, PANEL)
        surf.blit(t_s, (dr_s.x + (dr_s.width - t_s.get_width()) // 2,
                        dr_s.y + (dr_s.height - t_s.get_height()) // 2))

        h_r = restart_r.collidepoint(mpos)
        dr_r = _premium_btn(surf, restart_r, (115, 75, 40), h_r, radius=12)
        t_r  = fb_lg.render("重新創建角色", True, PANEL)
        surf.blit(t_r, (dr_r.x + (dr_r.width - t_r.get_width()) // 2,
                        dr_r.y + (dr_r.height - t_r.get_height()) // 2))

        return start_r, restart_r


def _spawn_confetti():
    """在畫面上方噴射 80 顆彩帶粒子。"""
    for _ in range(80):
        _cc_confetti.append({
            "x":  random.uniform(0, WIN_W),
            "y":  random.uniform(-60, -5),
            "vx": random.uniform(-3.5, 3.5),
            "vy": random.uniform(-9, -3),
            "color": random.choice(_CONFETTI_COLORS),
            "life": random.randint(55, 110),
            "max_life": 110,
            "w": random.randint(6, 13),
            "h": random.randint(4, 8),
        })


def _update_confetti(surf):
    """更新並繪製所有彩帶粒子；自動清除已結束的粒子。"""
    keep = []
    for p in _cc_confetti:
        p["vy"] += 0.35
        p["x"]  += p["vx"]
        p["y"]  += p["vy"]
        p["life"] -= 1
        if p["life"] > 0 and p["y"] < WIN_H + 20:
            alpha = min(255, int(255 * p["life"] / p["max_life"]))
            ps = pygame.Surface((p["w"], p["h"]), pygame.SRCALPHA)
            ps.fill((*p["color"], alpha))
            surf.blit(ps, (int(p["x"]), int(p["y"])))
            keep.append(p)
    _cc_confetti[:] = keep


def _update_slot_state(now):
    """每幀推進拉霸機動畫狀態。"""
    for i in range(3):
        phase = _slot_phase[i]
        if phase == "idle":
            if i > 0 and _slot_phase[i - 1] == "done" \
                    and now - _slot_stop_t[i - 1] >= _SLOT_DELAY_MS:
                _slot_phase[i]   = "spinning"
                _slot_start_t[i] = now
        elif phase == "spinning":
            if now - _slot_start_t[i] >= _SLOT_SPIN_MS:
                _slot_phase[i]  = "done"
                _slot_stop_t[i] = now
                result = _slot_results[i]
                if result and result.get("name") != "無天賦":
                    _spawn_confetti()
                    _cc_shake_end[0] = now + 400


def _draw_cc_slot_machine(surf, fm, fs, mpos):
    """拉霸機天賦動畫畫面，回傳「繼續」按鈕 Rect 或 None（尚未完成時）。"""
    fb_lg = _font_bold_lg[0] or fm
    now   = pygame.time.get_ticks()
    _update_slot_state(now)
    _draw_cc_bg(surf)

    # ── 彩帶 ─────────────────────────────────────────────────
    _update_confetti(surf)

    # ── 震動偏移 ──────────────────────────────────────────────
    if now < _cc_shake_end[0]:
        t_rem    = _cc_shake_end[0] - now
        amp      = max(0, int(7 * t_rem / 400))
        shake_dx = random.randint(-amp, amp)
        shake_dy = random.randint(-amp // 2, amp // 2)
    else:
        shake_dx = shake_dy = 0

    # ── 佈局 ──────────────────────────────────────────────────
    cw, ch     = 210, 230
    gap        = 22
    title_h    = fm.get_height() + 22
    TITLE_GAP  = 28
    SLOT_BTN   = 32
    btn_h      = 48
    total_h    = title_h + TITLE_GAP + ch + SLOT_BTN + btn_h
    top_y      = (WIN_H - total_h) // 2
    sy         = top_y + title_h + TITLE_GAP
    total_w    = 3 * cw + 2 * gap
    sx         = (WIN_W - total_w) // 2

    _draw_float_label_card(surf, fm, "抽取天賦", WIN_W // 2 + shake_dx, top_y + shake_dy,
                           pad_x=26, pad_y=11, amp=7, speed=0.00170, phase=3.0)

    all_done = all(p == "done" for p in _slot_phase)

    for i in range(3):
        r     = pygame.Rect(sx + i * (cw + gap) + shake_dx, sy + shake_dy, cw, ch)
        phase = _slot_phase[i]

        if phase == "idle":
            dr = _premium_btn(surf, r, (60, 40, 20), False, radius=16)
            q  = fb_lg.render("?", True, GRAY)
            surf.blit(q, (dr.x + (dr.width - q.get_width()) // 2,
                          dr.y + (dr.height - q.get_height()) // 2))

        elif phase == "spinning":
            dr = _premium_btn(surf, r, (82, 52, 22), False, radius=16)
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
            elapsed = now - _slot_start_t[i]
            t_frac  = min(1.0, elapsed / _SLOT_SPIN_MS)
            # 後段減速：interval 從 70ms 拉長到 260ms
            interval = int(70 + t_frac ** 2 * 190) if t_frac < 0.75 else int(70 + 0.75 ** 2 * 190)
            name_idx = (elapsed // max(1, interval)) % len(_SLOT_SPIN_NAMES)
            nt = fb_lg.render(_SLOT_SPIN_NAMES[name_idx], True, WHITE)
            ny = dr.y + (dr.height - nt.get_height()) // 2
            surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, ny))
            # 速度感模糊條
            for off, alpha in ((-32, 30), (-16, 55), (16, 55), (32, 30)):
                ghost = pygame.Surface((cw - 16, fb_lg.get_height()), pygame.SRCALPHA)
                ghost.fill((255, 200, 100, alpha))
                surf.blit(ghost, (dr.x + 8, ny + off))

        elif phase == "done":
            result     = _slot_results[i]
            is_talent  = result and result.get("name") != "無天賦"
            bg_col     = (110, 72, 36) if is_talent else (48, 33, 18)
            dr         = _premium_btn(surf, r, bg_col, False, radius=16)
            if is_talent:
                pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
            name     = result.get("name", "無天賦") if result else "無天賦"
            name_col = YELLOW if is_talent else GRAY
            nt = fb_lg.render(name, True, name_col)
            surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 20))
            if is_talent:
                desc_lines = _wrap(result.get("desc", ""), fs, cw - 20)
                for li, dl in enumerate(desc_lines):
                    dt = fs.render(dl, True, WHITE)
                    surf.blit(dt, (dr.x + 10, dr.y + 62 + li * (fs.get_height() + 4)))

    # ── 繼續按鈕（全部完成後才出現）──────────────────────────────
    ok = pygame.Rect((WIN_W - 160) // 2, sy + ch + SLOT_BTN, 160, btn_h)
    if all_done:
        hover = ok.collidepoint(mpos)
        ok_dr = _premium_btn(surf, ok, BTN_N, hover, radius=14)
        t     = fb_lg.render("繼續", True, WHITE)
        surf.blit(t, (ok_dr.x + (ok_dr.width - t.get_width()) // 2,
                      ok_dr.y + (ok_dr.height - t.get_height()) // 2))
        return ok
    return None


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

    elif mode == "portrait":
        for (r, prefix) in (_cc_btn_cache.get("portrait_cards") or []):
            if r.collidepoint(ev_pos):
                _portrait_prefix[0] = prefix
                _cc_reply_val[0]    = prefix
                _cc_mode[0]         = ""
                _cc_reply_event.set()
                return

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

    elif mode == "extra":
        for (r, ev_id) in (_cc_btn_cache.get("extra_cards") or []):
            if r.collidepoint(ev_pos):
                ev_map = {e["id"]: e for e in _cc_extra_data}
                ev     = ev_map.get(ev_id)
                if not ev:
                    return
                if ev_id in _cc_extra_sel:
                    _cc_extra_sel.remove(ev_id)
                else:
                    excl = ev.get("exclusive", [])
                    if any(x in _cc_extra_sel for x in excl):
                        _cc_extra_warn[0] = pygame.time.get_ticks()
                        return
                    _cc_extra_sel.append(ev_id)
                return
        ok = _cc_btn_cache.get("extra_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = list(_cc_extra_sel)
            _cc_mode[0]      = ""
            _cc_extra_sel.clear()
            _cc_reply_event.set()

    elif mode == "slot":
        ok = _cc_btn_cache.get("slot_ok")
        if ok and ok.collidepoint(ev_pos) and all(p == "done" for p in _slot_phase):
            _cc_mode[0] = ""
            _cc_confetti.clear()
            _cc_reply_event.set()

    elif mode == "summary":
        start_r   = _cc_btn_cache.get("summary_start")
        restart_r = _cc_btn_cache.get("summary_restart")
        if start_r and start_r.collidepoint(ev_pos):
            _cc_reply_val[0] = "start"
            _cc_mode[0] = ""
            _cc_reply_event.set()
        elif restart_r and restart_r.collidepoint(ev_pos):
            _cc_reply_val[0] = "restart"
            _cc_mode[0] = ""
            _cc_reply_event.set()

    elif mode == "de_level":
        for (r, idx) in (_cc_btn_cache.get("de_level_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_sel.clear()
                _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("de_level_ok")
        if ok and ok.collidepoint(ev_pos):
            if _cc_sel:
                _cc_reply_val[0] = data[_cc_sel[0]]
                _cc_mode[0] = ""
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

# ── 特殊行動（凸起面板）常數 ──────────────────────────────────
_BUMP_H  = 88    # 凸起高度（向上突出面板頂邊）
_BUMP_W  = 310   # 凸起寬度
_BUMP_R  = 30    # 特殊按鈕半徑
_BUMP_SP = 105   # 特殊按鈕間距
_SPECIAL_ACTION_NAMES = ["熬夜", "翹課", "進食"]
_SPECIAL_ICONS = {"熬夜": "月", "翹課": "逃", "進食": "食"}

# 各行動的體力消耗說明 + 預期效果（用於 hover 提示列）
_ACTION_INFO = {
    "認真讀書": ("消耗體力 4", "課業熟練度 +8    自我滿足度 -5"),
    "正常上課": ("消耗體力 2", "課業熟練度 +4    課堂參與度 +5"),
    "社團活動": ("消耗體力 3", "自我滿足度 +10"),
    "打工賺錢": ("消耗體力 4", "金錢 +150    自我滿足度 +3"),
    "好好休息": ("恢復體力 6", "自我滿足度 +8"),
    "幫助朋友": ("消耗體力 2", "自我滿足度 +12"),
    # 特殊行動
    "熬夜": ("體力 -10, 時間 +2", "睡過頭機率 ↑10%    滿足感 -5"),
    "翹課": ("體力 +10, 時間 +1", "錯過小考/點名機率：(100-運氣)%"),
    "進食": ("金錢 -50, 體力 +10", "獲得飽腹狀態（3 個時間格）"),
}


def _draw_choice_popup(surf, fm, fs, mode, choices, log, prompt_text,
                       yn_labels, mpos):
    """
    畫面中央通用選項彈出視窗。
      mode == "choices"（非標準）→ 顯示題目（log 末尾）+ 選項按鈕（縱排）
      mode == "yn"               → 顯示 prompt + 是/否按鈕（橫排）
    回傳 [(rect, val), ...] 可點擊按鈕清單。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17（題目 / 按鈕文字）
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22（yn 按鈕）
    # ── 全螢幕遮罩 ────────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 155))
    surf.blit(ov, (0, 0))

    PAD_X   = 32   # 視窗左右內距
    PAD_TOP = 22
    PAD_BOT = 24
    BTN_PX  = 16   # 按鈕水平內距
    BTN_PY  = 10   # 按鈕垂直內距
    BTN_GAP = 8    # 按鈕間距
    SEP_H   = 14   # 題目與按鈕之間間距

    popup_w    = min(WIN_W - 40, 900)
    text_w     = popup_w - PAD_X * 2
    btn_text_w = text_w - BTN_PX * 2

    # ── 題目文字準備 ─────────────────────────────────────────
    _yn_ctx_count = 0   # yn 模式：紀錄「文案背景行數」，用於分色渲染
    if mode == "yn":
        raw = prompt_text or ""
        if _yn_show_ctx[0]:
            # 取最近幾條 log 純字串作為文案背景（最多 3 條）
            ctx_entries = [l for l in log if isinstance(l, str)][-3:]
            ctx_lines   = []
            for entry in ctx_entries:
                ctx_lines.extend(_wrap(entry, fb, text_w))
            _yn_ctx_count = len(ctx_lines)
            q_lines = ctx_lines + (_wrap(raw, fb, text_w) if raw else [])
        else:
            # 不附帶 log 背景，只顯示 prompt 本身
            q_lines = _wrap(raw, fb, text_w) if raw else []
    else:
        q_lines = list(log[-6:]) if log else []

    q_lh = fb.get_height() + 4
    q_h  = len(q_lines) * q_lh

    # ── 按鈕佈局計算 ─────────────────────────────────────────
    btn_layout = []   # [(wrapped_lines, btn_h, val), ...]
    if mode == "yn":
        yn_half_w = (text_w - BTN_GAP) // 2 - BTN_PX * 2
        for label, val in [(yn_labels[0], True), (yn_labels[1], False)]:
            lines = _wrap(label, fb_lg, yn_half_w)
            bh    = max(46, len(lines) * (fb_lg.get_height() + 3) + BTN_PY * 2)
            btn_layout.append((lines, bh, val))
        btns_h = max(bh for _, bh, _ in btn_layout)
    else:
        for i, label in enumerate(choices):
            lines = _wrap(_clean(label), fb, btn_text_w)
            bh    = max(46, len(lines) * (fb.get_height() + 3) + BTN_PY * 2)
            btn_layout.append((lines, bh, i + 1))
        btns_h = (sum(bh + BTN_GAP for _, bh, _ in btn_layout) - BTN_GAP
                  if btn_layout else 0)

    sep_actual = SEP_H if q_lines else 0
    total_h    = min(PAD_TOP + q_h + sep_actual + btns_h + PAD_BOT,
                     WIN_H - 60)
    px = (WIN_W - popup_w) // 2
    py = max(30, (WIN_H - total_h) // 2)

    # ── 投影 + 卡片 ──────────────────────────────────────────
    sh = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 55),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(sh, (px + 4, py + 4))
    card = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 248, 238, 248),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(card, (px, py))
    pygame.draw.rect(surf, CYAN,
                     pygame.Rect(px, py, popup_w, total_h), 2, border_radius=18)

    # ── 設定 clip 防溢出 ──────────────────────────────────────
    old_clip = surf.get_clip()
    inner    = pygame.Rect(px + 2, py + 2, popup_w - 4, total_h - 4)
    surf.set_clip(inner)

    # ── 題目文字 ─────────────────────────────────────────────
    # yn 模式：文案背景行（前 _yn_ctx_count 行）用暖棕灰色，
    # 問題本身（後段）用正常深棕色，形成視覺層次。
    cur_y = py + PAD_TOP
    for i, line in enumerate(q_lines):
        line_col = GRAY if (mode == "yn" and i < _yn_ctx_count) else WHITE
        lt = fb.render(line, True, line_col)
        surf.blit(lt, (px + PAD_X, cur_y))
        cur_y += q_lh

    if q_lines and sep_actual:
        mid_sep = cur_y + sep_actual // 2
        pygame.draw.line(surf, (210, 190, 165),
                         (px + PAD_X, mid_sep), (px + popup_w - PAD_X, mid_sep), 1)
        cur_y += sep_actual

    # ── 按鈕 ─────────────────────────────────────────────────
    btn_rects = []
    bx = px + PAD_X
    bw = text_w

    if mode == "yn":
        yw    = (bw - BTN_GAP) // 2
        yn_bh = max(bh for _, bh, _ in btn_layout)
        for j, (lines, _, val) in enumerate(btn_layout):
            br    = pygame.Rect(bx + j * (yw + BTN_GAP), cur_y, yw, yn_bh)
            col_b = BTN_N if val else DARK_GRAY
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, col_b, hover, radius=12)
            th    = len(lines) * (fb_lg.get_height() + 3)
            ty    = dr.y + (dr.height - th) // 2
            for line in lines:
                lt = fb_lg.render(line, True, PANEL)
                surf.blit(lt, (dr.x + (dr.width - lt.get_width()) // 2, ty))
                ty += fb_lg.get_height() + 3
            btn_rects.append((br, val))
    else:
        for lines, bh, val in btn_layout:
            br    = pygame.Rect(bx, cur_y, bw, bh)
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
            th    = len(lines) * (fb.get_height() + 3)
            ty    = dr.y + (dr.height - th) // 2
            for line in lines:
                lt = fb.render(line, True, PANEL)
                surf.blit(lt, (dr.x + (dr.width - lt.get_width()) // 2, ty))
                ty += fb.get_height() + 3
            btn_rects.append((br, val))
            cur_y += bh + BTN_GAP

    surf.set_clip(old_clip)
    return btn_rects


def _draw_event_ok_popup(surf: pygame.Surface, fm, fs, mpos) -> list:
    """
    突發事件通知彈窗（單一「確認」按鈕）。
    _event_ok_text[0] 格式：「前綴：【事件名】\\n描述文字」
    回傳 [(rect, True)] 確認按鈕 rect 清單。
    """
    fb    = _font_bold[0]    or fs
    fb_lg = _font_bold_lg[0] or fm

    # ── 解析文字 ─────────────────────────────────────────────
    raw   = _event_ok_text[0] or ""
    parts = raw.split("\n", 1)
    title = parts[0]
    body  = parts[1].strip() if len(parts) > 1 else ""

    # ── 版面常數 ─────────────────────────────────────────────
    popup_w = min(WIN_W - 80, 760)
    PAD_X   = 28
    PAD_TOP = 18
    PAD_BOT = 24
    HDR_H   = fb_lg.get_height() + 22
    SEP_H   = 14
    BTN_H   = 48
    BTN_W   = 180
    text_w  = popup_w - PAD_X * 2

    # ── 包裹文字 ─────────────────────────────────────────────
    title_lines = _wrap(title, fb_lg, text_w)
    body_lines  = _wrap(body, fb, text_w) if body else []
    q_lh_lg = fb_lg.get_height() + 4
    q_lh    = fb.get_height()    + 4
    body_h  = len(body_lines) * q_lh

    total_h = min(HDR_H + PAD_TOP + body_h + SEP_H + BTN_H + PAD_BOT,
                  WIN_H - 60)
    px = (WIN_W - popup_w) // 2
    py = max(30, (WIN_H - total_h) // 2)

    # ── 全螢幕遮罩 ────────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 165))
    surf.blit(ov, (0, 0))

    # ── 投影 ──────────────────────────────────────────────────
    sh = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 60),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(sh, (px + 4, py + 4))

    # ── 主體（米白）──────────────────────────────────────────
    card = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 248, 238, 252),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(card, (px, py))

    # ── 標題列（深橙棕，僅上方圓角）─────────────────────────
    _HDR_COL = (165, 88, 32)
    hdr = pygame.Surface((popup_w, HDR_H), pygame.SRCALPHA)
    pygame.draw.rect(hdr, (*_HDR_COL, 255),
                     pygame.Rect(0, 0, popup_w, HDR_H), border_radius=18)
    pygame.draw.rect(hdr, (*_HDR_COL, 255),
                     pygame.Rect(0, 14, popup_w, HDR_H - 14))
    surf.blit(hdr, (px, py))

    # 標題文字（居中，亮米色）
    hdr_ty = py + (HDR_H - len(title_lines) * q_lh_lg) // 2
    for line in title_lines:
        ts = fb_lg.render(line, True, (255, 232, 190))
        surf.blit(ts, (px + (popup_w - ts.get_width()) // 2, hdr_ty))
        hdr_ty += q_lh_lg

    # ── 邊框（可自定義顏色，用於額外事件彈窗）────────────────────
    _bdr = _event_ok_border_color[0] or (155, 100, 50)
    pygame.draw.rect(surf, _bdr,
                     pygame.Rect(px, py, popup_w, total_h), 3, border_radius=18)

    # ── clip ─────────────────────────────────────────────────
    old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(px + 2, py + 2, popup_w - 4, total_h - 4))

    # ── 描述文字 ──────────────────────────────────────────────
    cur_y = py + HDR_H + PAD_TOP
    for line in body_lines:
        ls = fb.render(line, True, WHITE)
        surf.blit(ls, (px + PAD_X, cur_y))
        cur_y += q_lh

    # ── 分隔線 ────────────────────────────────────────────────
    sep_y = py + total_h - PAD_BOT - BTN_H - SEP_H // 2
    pygame.draw.line(surf, (210, 190, 165),
                     (px + PAD_X, sep_y), (px + popup_w - PAD_X, sep_y), 1)

    # ── 確認按鈕（置中）──────────────────────────────────────
    btn_x = px + (popup_w - BTN_W) // 2
    btn_y = py + total_h - PAD_BOT - BTN_H
    br    = pygame.Rect(btn_x, btn_y, BTN_W, BTN_H)
    hover = br.collidepoint(mpos)
    dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
    ct    = fb_lg.render("確認", True, PANEL)
    surf.blit(ct, (dr.x + (dr.width  - ct.get_width())  // 2,
                   dr.y + (dr.height - ct.get_height()) // 2))

    surf.set_clip(old_clip)
    return [(br, True)]


def _draw_subj_popup(surf, fm, fs, mpos):
    """
    在畫面中央繪製「選擇科目」彈出視窗，並回傳按鈕清單 [(rect, idx), ...]。
    idx 為 1-based；玩家點擊後由事件迴圈負責解除 popup 並回傳結果。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17（按鈕文字）
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22（標題）
    # ── 半透明暗色遮罩 ────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 160))
    surf.blit(ov, (0, 0))

    n       = len(_subj_popup_opts)
    bw      = 300          # 按鈕寬度
    bh      = 46           # 按鈕高度
    gap     = 10           # 按鈕間距
    pad_x   = 40           # 左右內距
    pad_top = 20           # 頂部內距（標題上方）
    pad_mid = 14           # 標題與按鈕之間
    pad_bot = 24           # 最後按鈕到底部
    sep_h   = 1            # 標題下方分隔線高度

    total_w = bw + pad_x * 2
    title_h = fm.get_height()
    total_h = (pad_top + title_h + 6 + sep_h + pad_mid
               + n * bh + max(n - 1, 0) * gap
               + pad_bot)

    px = (WIN_W - total_w) // 2
    py = (WIN_H - total_h) // 2

    # ── 視窗背景 ──────────────────────────────────────────────
    box = pygame.Rect(px, py, total_w, total_h)
    pygame.draw.rect(surf, (38, 24, 14), box, border_radius=18)
    pygame.draw.rect(surf, CYAN,         box, 2, border_radius=18)

    # ── 標題 ──────────────────────────────────────────────────
    ttx = fb_lg.render(_subj_popup_title[0], True, PANEL)
    surf.blit(ttx, (px + (total_w - ttx.get_width()) // 2, py + pad_top))

    # 標題下分隔線
    line_y = py + pad_top + title_h + 6
    pygame.draw.line(surf, (CYAN[0], CYAN[1], CYAN[2]),
                     (px + 18, line_y), (px + total_w - 18, line_y), 1)

    # ── 選項按鈕 ──────────────────────────────────────────────
    bx  = px + pad_x
    by0 = line_y + sep_h + pad_mid
    btn_list = []
    for i, label in enumerate(_subj_popup_opts):
        br    = pygame.Rect(bx, by0 + i * (bh + gap), bw, bh)
        hover = br.collidepoint(mpos)
        dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
        lt    = fb.render(label, True, PANEL)
        surf.blit(lt, (dr.x + (dr.width  - lt.get_width())  // 2,
                       dr.y + (dr.height - lt.get_height()) // 2))
        btn_list.append((br, i + 1))

    return btn_list


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
        if isinstance(raw, tuple) and raw[0] == "multi":
            # ("multi", [(text, col), ...])：多色區段，單行渲染
            rows.append(("multi", raw[1]))
        elif isinstance(raw, tuple):
            # 舊式 2-tuple (text, color_rgb)：直接以指定顏色渲染
            _annot_text, _annot_col = raw
            rows.append((_annot_text, _annot_col))
        elif raw == "---":
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
    # "multi" 行的 r[0] == "multi"，不在 sep/warn_sep 中，正確算 lh ✓

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
        elif row[0] == "multi":
            # 多色區段：逐段橫向排列在同一行
            xoff = pop_r.x + 14
            for seg_text, seg_col in row[1]:
                seg_s = fs.render(seg_text, True, seg_col)
                surf.blit(seg_s, (xoff, ty))
                xoff += seg_s.get_width()
            ty += lh
        else:
            text, col = row
            lt = fs.render(text, True, col)
            surf.blit(lt, (pop_r.x + 14, ty))
            ty += lh

    # ── 恢復原始 clip（避免影響後續繪製）────────────────────
    surf.set_clip(_old_clip)


# ── 行動按鈕 Icon ──────────────────────────────────────────────
_ACTION_ICON_FILES = {
    "認真讀書": "study_icon.webp",
    "正常上課": "class_icon.webp",
    "社團活動": "club_icon.webp",
    "打工賺錢": "work_icon.webp",
    "好好休息": "rest_icon.webp",
    "幫助朋友": "friend_icon.webp",
}
_action_icon_srcs: dict = {}   # label -> pygame.Surface（懶載入原始圖）


def _draw_action_icon(surf: pygame.Surface, cx: int, cy: int, ar: int, label: str) -> None:
    """在圓形按鈕表面貼上滿版 icon（圓形裁切）。"""
    if label not in _ACTION_ICON_FILES:
        return
    # 懶載入原始圖（每個 label 只 load 一次）
    if label not in _action_icon_srcs:
        _icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "asset", "picture", "icon")
        path = os.path.join(_icon_dir, _ACTION_ICON_FILES[label])
        try:
            _action_icon_srcs[label] = pygame.image.load(path).convert_alpha()
        except Exception:
            _action_icon_srcs[label] = None
    src = _action_icon_srcs.get(label)
    if src is None:
        return
    d = ar * 2
    scaled = pygame.transform.smoothscale(src, (d, d))
    # 圓形遮罩：圓外 alpha→0
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.circle(mask, (255, 255, 255, 255), (ar, ar), ar)
    scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(scaled, (cx - ar, cy - ar))


def _draw_bump_bg(surf: pygame.Surface, pr: pygame.Rect) -> None:
    """
    在行動面板（pr）頂邊繪製向上凸起的特殊行動承載區。
    凸起底部延伸至 pr.y + 14，使面板卡片（同奶霜色）自然覆蓋接縫。
    """
    cx     = pr.x + pr.width // 2
    bx     = cx - _BUMP_W // 2
    top_y  = pr.y - _BUMP_H
    full_h = _BUMP_H + 14                    # 凸起 + 與面板的重疊部份

    # 陰影
    sh_sf = pygame.Surface((_BUMP_W + 8, full_h + 6), pygame.SRCALPHA)
    pygame.draw.rect(sh_sf, (0, 0, 0, 42),
                     pygame.Rect(0, 0, _BUMP_W + 8, full_h + 6), border_radius=14)
    surf.blit(sh_sf, (bx - 2, top_y + 5))

    # 凸起本體（奶霜底色 + 深棕邊框）
    pygame.draw.rect(surf, (255, 244, 228),
                     pygame.Rect(bx, top_y, _BUMP_W, full_h), border_radius=14)
    pygame.draw.rect(surf, CYAN,
                     pygame.Rect(bx, top_y, _BUMP_W, full_h), 2, border_radius=14)


def _draw_action_panel(surf, fm, fs, mode, choices, log, prompt, tvalue, rect, time_left, mpos):
    """
    新版底部面板（浮動卡片）。
    rect: 整個底部區域（含 TAB_H 標籤列）
    回傳 (content_rects, end_week_btn)
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22
    M  = 8
    pr = pygame.Rect(rect.x + M, rect.y + M,
                     rect.width - M * 2, rect.height - M * 2)

    # ── 判斷是否為標準行動模式（需在投影前確定，以便決定是否畫凸起）──
    is_std_action = (mode == "choices" and
                     all(c in _STANDARD_ACTIONS for c in choices))

    # ── 特殊行動凸起（標準行動模式才顯示，畫在面板投影之前）────────
    if is_std_action:
        _draw_bump_bg(surf, pr)

    # ── 投影 ──────────────────────────────────────────────────
    sh = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 52),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(sh, (pr.x + 4, pr.y + 4))

    # ── 卡片底色 ──────────────────────────────────────────────
    card = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 244, 228, 238),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(card, pr.topleft)
    pygame.draw.rect(surf, CYAN, pr, 2, border_radius=14)

    # ── 標籤列 ───────────────────────────────────────────────
    tab_rect    = pygame.Rect(pr.x, pr.y, pr.width, TAB_H)
    content_top = pr.y + TAB_H

    # ── 預先計算 hover 狀態（供標籤列 tooltip 使用）─────────
    hovered_action = None
    if is_std_action:
        action_choices_pre = [c for c in choices if c != "🏪 前往道具店"]
        n_pre    = len(action_choices_pre)
        r_pre    = 36
        sp_pre   = min(140, (pr.width - 40) // max(n_pre, 1))
        sx_pre   = pr.x + (pr.width - n_pre * sp_pre) // 2 + sp_pre // 2
        cy_pre   = content_top + r_pre + ((pr.height - TAB_H - r_pre * 2 - fs.get_height() - 8) // 2)
        for i, lbl in enumerate(action_choices_pre):
            cx_i = sx_pre + i * sp_pre
            if pygame.Rect(cx_i - r_pre - 8, cy_pre - r_pre - 8,
                           (r_pre + 8) * 2, (r_pre + 8) * 2).collidepoint(mpos):
                hovered_action = lbl
                break
        # ── 特殊按鈕 hover 偵測（主按鈕沒中才繼續）──────────────
        if hovered_action is None:
            _sp_cy_pre = pr.y - _BUMP_H // 2
            for _si_p, _sn_p in enumerate(_SPECIAL_ACTION_NAMES):
                _sp_cx_p = pr.x + pr.width // 2 + (_si_p - 1) * _BUMP_SP
                if (_sn_p not in _special_disabled and
                        pygame.Rect(_sp_cx_p - _BUMP_R - 8, _sp_cy_pre - _BUMP_R - 8,
                                    (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2).collidepoint(mpos)):
                    hovered_action = _sn_p
                    break

    # 左側：剩餘時間點（含震動 / 紅色閃動特效）
    _now_ms      = pygame.time.get_ticks()
    _shake_elapsed = _now_ms - _time_shake_t0[0] if _time_shake_t0[0] > 0 else _TIME_SHAKE_MS
    if _time_shake_t0[0] > 0 and _shake_elapsed < _TIME_SHAKE_MS:
        _t     = _shake_elapsed / _TIME_SHAKE_MS          # 0→1
        _decay = (1.0 - _t) ** 1.5
        _offset_x = int(math.sin(_t * math.pi * 5) * 10 * _decay)
        _mix   = _decay                                   # 1→0，紅色→正常色
        _time_col = (
            int(RED[0] * _mix + WHITE[0] * (1.0 - _mix)),
            int(RED[1] * _mix + WHITE[1] * (1.0 - _mix)),
            int(RED[2] * _mix + WHITE[2] * (1.0 - _mix)),
        )
    else:
        _offset_x = 0
        _time_col = WHITE
        if _time_shake_t0[0] > 0 and _shake_elapsed >= _TIME_SHAKE_MS:
            _time_shake_t0[0] = 0   # 動畫結束後重置
    # 時鐘圖示 + 時間文字（整組跟著震動偏移）
    _CLK_R   = 9                          # 時鐘圖示半徑
    _clk_x0  = tab_rect.x + 14 + _offset_x   # 整組左起點
    _clk_cy  = tab_rect.y + TAB_H // 2       # 垂直中心
    _draw_icon_clock(surf,
                     _clk_x0 + _CLK_R,        # 圖示圓心 x
                     _clk_cy, _CLK_R,
                     col=_time_col)            # 指針顏色跟著閃動色
    time_txt = fb.render(f"剩餘時間點：{time_left}", True, _time_col)
    surf.blit(time_txt, (_clk_x0 + _CLK_R * 2 + 5,
                         tab_rect.y + (TAB_H - time_txt.get_height()) // 2))

    # 中間：行動 hover 提示（體力消耗 + 預期效果）
    if hovered_action and hovered_action in _ACTION_INFO:
        cost_str, eff_str = _ACTION_INFO[hovered_action]
        is_restore = cost_str.startswith("恢復")
        cost_col   = GREEN if is_restore else RED
        tip_x = _clk_x0 + _CLK_R * 2 + 5 + time_txt.get_width() + 24
        tip_y = tab_rect.y + (TAB_H - fb.get_height()) // 2
        cost_t = fb.render(cost_str, True, cost_col)
        surf.blit(cost_t, (tip_x, tip_y))
        sep_x  = tip_x + cost_t.get_width() + 10
        sep_t  = fs.render("|", True, GRAY)
        surf.blit(sep_t, (sep_x, tip_y))
        eff_t  = fb.render(eff_str, True, YELLOW)
        surf.blit(eff_t, (sep_x + sep_t.get_width() + 10, tip_y))

    # 右側：結束本週按鈕（考試週隱藏）
    if mode != "exam_ready":
        ew_btn   = pygame.Rect(pr.right - 110, tab_rect.y + 4, 100, TAB_H - 8)
        ew_hover = ew_btn.collidepoint(mpos)
        ew_dr    = _premium_btn(surf, ew_btn, (200, 78, 58), ew_hover, radius=10)
        ew_t     = fb.render("結束本週", True, PANEL)
        surf.blit(ew_t, (ew_dr.x + (ew_dr.width  - ew_t.get_width())  // 2,
                         ew_dr.y + (ew_dr.height - ew_t.get_height()) // 2))
    else:
        ew_btn = None

    # 分隔線
    pygame.draw.line(surf, GRAY, (pr.x, content_top), (pr.right, content_top), 1)

    content_rect = pygame.Rect(pr.x, content_top, pr.width, pr.height - TAB_H)
    content_rects = []

    # ── 內容區：依模式切換 ────────────────────────────────────

    if mode == "choices" and is_std_action:
        # ── 圓形行動按鈕（縮小 + 標籤移至按鈕下方）─────────
        action_choices = [c for c in choices if c != "🏪 前往道具店"]
        n       = len(action_choices)
        r       = 36
        spacing = min(140, (pr.width - 40) // max(n, 1))
        total_w = n * spacing
        sx      = pr.x + (pr.width - total_w) // 2 + spacing // 2
        # 垂直：圓心上移，留空間給下方標籤
        fb      = _font_bold[0] or fs      # 粗體字型（行動標籤）
        lh      = fb.get_height()
        cy_btn  = content_top + r + ((content_rect.height - r * 2 - lh - 8) // 2)

        ms_now  = pygame.time.get_ticks()

        for i, label in enumerate(action_choices):
            cx_btn   = sx + i * spacing
            orig_idx = choices.index(label) + 1
            hover    = pygame.Rect(cx_btn - r - 8, cy_btn - r - 8,
                                   (r + 8) * 2, (r + 8) * 2).collidepoint(mpos)

            # ── 按鈕脈動：hover 時暫停，離開後自動與所有按鈕同步 ────
            # 因為全部按鈕都以 ms_now % cycle 計算，游標移開時自動銜接。
            _PULSE_CYCLE = 1000
            _PULSE_SPAN  = 500
            _t_p         = ms_now % _PULSE_CYCLE
            if hover:
                r_draw = r              # hover → 暫停脈動，固定自然大小
            elif _t_p < _PULSE_SPAN:
                _pulse_phase = (_t_p / _PULSE_SPAN) * math.tau
                r_draw = r + int(math.sin(_pulse_phase) * 3.0)
            else:
                r_draw = r              # 靜止段

            ar    = _premium_circle(surf, cx_btn, cy_btn, r_draw,
                                    BTN_N, hover, key=(cx_btn, cy_btn))
            _draw_action_icon(surf, cx_btn, cy_btn, ar, label)
            # icon 蓋住 _premium_circle 的邊框，補畫一圈
            _bdr = tuple(min(255, int(c * 1.20 + 30)) for c in BTN_N)
            pygame.draw.circle(surf, _bdr, (cx_btn, cy_btn), ar, 2)
            brect = pygame.Rect(cx_btn - r - 8, cy_btn - r - 8,
                                (r + 8) * 2, (r + 8) * 2)   # 點擊判定用原始 r

            # ── Hover 光暈：SRCALPHA 同心圓環，畫在按鈕邊框外側 ─────
            if hover:
                _glow_sz = (ar + 28) * 2
                _glow_sf = pygame.Surface((_glow_sz, _glow_sz), pygame.SRCALPHA)
                _gc      = _glow_sz // 2
                for _gr, _ga in [(ar + 24, 28), (ar + 16, 50), (ar + 8, 72)]:
                    pygame.draw.circle(_glow_sf, (160, 210, 255, _ga),
                                       (_gc, _gc), _gr, 4)
                surf.blit(_glow_sf, (cx_btn - _gc, cy_btn - _gc))

            # ── 波浪標籤：每 2 秒 1 次，hover 時靜止 ────────────────
            # 每 2000ms 週期：前 1000ms 播波浪（同速），後 1000ms 靜止；
            # 以 Hann 包絡 sin(π·t) 讓振幅平滑淡入淡出，避免首尾跳變。
            clean_label  = label.replace("🏪 ", "")
            _WAVE_CYCLE  = 2000
            _WAVE_SPAN   = 1000
            _t_w         = ms_now % _WAVE_CYCLE
            wave_amp     = 3.5    # 峰值振幅（像素）
            wave_step    = 0.9    # 相鄰字元相位差（弧度）

            ch_surfs  = [fb.render(ch, True, WHITE) for ch in clean_label]
            txt_total = sum(s.get_width() for s in ch_surfs)
            x_cur     = cx_btn - txt_total // 2
            label_y   = cy_btn + r + 12

            if hover:
                # hover → 標籤靜止，不做波浪
                for ch_s in ch_surfs:
                    surf.blit(ch_s, (x_cur, label_y))
                    x_cur += ch_s.get_width()
            elif _t_w < _WAVE_SPAN:
                _t_norm    = _t_w / _WAVE_SPAN          # 0.0 → 1.0
                _wave_base = _t_norm * math.tau          # 與原 1Hz 相同速度
                _env       = math.sin(_t_norm * math.pi) # Hann 包絡，首尾振幅→0
                for j, ch_s in enumerate(ch_surfs):
                    y_off = int(wave_amp * _env * math.sin(_wave_base - j * wave_step))
                    surf.blit(ch_s, (x_cur, label_y + y_off))
                    x_cur += ch_s.get_width()
            else:
                for ch_s in ch_surfs:                   # 靜止，全部 y_off=0
                    surf.blit(ch_s, (x_cur, label_y))
                    x_cur += ch_s.get_width()

            content_rects.append((brect, orig_idx))

        # ── 特殊行動按鈕（凸起區，畫在主按鈕之後）────────────────
        _sp_cy  = pr.y - _BUMP_H // 2
        _sp_cx0 = pr.x + pr.width // 2
        for _si, _sn in enumerate(_SPECIAL_ACTION_NAMES):
            _sp_cx    = _sp_cx0 + (_si - 1) * _BUMP_SP
            _disabled = _sn in _special_disabled
            _sp_hover = (not _disabled and
                         pygame.Rect(_sp_cx - _BUMP_R - 8, _sp_cy - _BUMP_R - 8,
                                     (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2).collidepoint(mpos))

            # 脈動（停用 / hover 時固定）
            _SP_PULSE_CYCLE = 1000
            _SP_PULSE_SPAN  = 500
            _sp_tp = ms_now % _SP_PULSE_CYCLE
            if _disabled or _sp_hover:
                _sp_r_draw = _BUMP_R
            elif _sp_tp < _SP_PULSE_SPAN:
                _sp_pulse_phase = (_sp_tp / _SP_PULSE_SPAN) * math.tau
                _sp_r_draw = _BUMP_R + int(math.sin(_sp_pulse_phase) * 3.0)
            else:
                _sp_r_draw = _BUMP_R

            # 按鈕本體顏色（停用時灰色）
            _sp_col = (105, 105, 115) if _disabled else BTN_N
            _sp_ar  = _premium_circle(surf, _sp_cx, _sp_cy, _sp_r_draw,
                                      _sp_col, _sp_hover and not _disabled,
                                      key=(_sp_cx, _sp_cy + 9000))  # 避免 key 衝突

            # 圖示文字（粗體字元放圓心）
            _sp_icon_str = _SPECIAL_ICONS.get(_sn, _sn[0])
            _sp_icon_col = (160, 160, 170) if _disabled else PANEL
            _sp_icon_s   = fb.render(_sp_icon_str, True, _sp_icon_col)
            surf.blit(_sp_icon_s, (_sp_cx - _sp_icon_s.get_width() // 2,
                                   _sp_cy - _sp_icon_s.get_height() // 2))

            # hover 光暈
            if _sp_hover:
                _glow_sz = (_sp_ar + 28) * 2
                _glow_sf = pygame.Surface((_glow_sz, _glow_sz), pygame.SRCALPHA)
                _gc2     = _glow_sz // 2
                for _gr2, _ga2 in [(_sp_ar + 24, 28), (_sp_ar + 16, 50), (_sp_ar + 8, 72)]:
                    pygame.draw.circle(_glow_sf, (160, 210, 255, _ga2),
                                       (_gc2, _gc2), _gr2, 4)
                surf.blit(_glow_sf, (_sp_cx - _gc2, _sp_cy - _gc2))

            # 停用倒數數字 overlay
            if _disabled:
                _cd_val  = _special_disabled[_sn]
                _cd_str  = str(_cd_val)
                _cd_s    = fb.render(_cd_str, True, (220, 100, 60))
                surf.blit(_cd_s, (_sp_cx + _sp_ar // 2 - _cd_s.get_width() // 2,
                                  _sp_cy + _sp_ar // 2 - _cd_s.get_height() // 2))

            # 波浪標籤（與主按鈕相同邏輯）
            _sp_clean   = _sn
            _SP_WAVE_CYCLE = 2000
            _SP_WAVE_SPAN  = 1000
            _sp_tw     = ms_now % _SP_WAVE_CYCLE
            _sp_wave_amp  = 3.5
            _sp_wave_step = 0.9
            _sp_ch_surfs  = [fb.render(ch, True, WHITE if not _disabled else (140, 140, 150))
                             for ch in _sp_clean]
            _sp_txt_total = sum(s.get_width() for s in _sp_ch_surfs)
            _sp_x_cur     = _sp_cx - _sp_txt_total // 2
            _sp_label_y   = _sp_cy + _BUMP_R + 8

            if _sp_hover:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()
            elif _disabled:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()
            elif _sp_tw < _SP_WAVE_SPAN:
                _sp_t_norm    = _sp_tw / _SP_WAVE_SPAN
                _sp_wave_base = _sp_t_norm * math.tau
                _sp_env       = math.sin(_sp_t_norm * math.pi)
                for j2, _ch_s in enumerate(_sp_ch_surfs):
                    _y_off2 = int(_sp_wave_amp * _sp_env * math.sin(_sp_wave_base - j2 * _sp_wave_step))
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y + _y_off2))
                    _sp_x_cur += _ch_s.get_width()
            else:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()

            # 點擊判定（停用時不加入）
            if not _disabled:
                _sp_brect = pygame.Rect(_sp_cx - _BUMP_R - 8, _sp_cy - _BUMP_R - 8,
                                        (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2)
                content_rects.append((_sp_brect, -(_si + 1)))

    elif mode == "choices" and not is_std_action:
        # ── 非標準選項：上方顯示最新 log（題目文字），下方按鈕作答 ──
        LOG_LINES = 3
        lh_log    = fs.get_height() + 4
        log_h     = LOG_LINES * lh_log + 6
        log_area  = pygame.Rect(content_rect.x, content_rect.y,
                                content_rect.width, log_h)
        _draw_panel_log(surf, fs, log, log_area, lines=LOG_LINES)

        # 按鈕區從 log 下方開始
        bw   = (pr.width - 36) // 2 - 6
        bh   = 40
        px   = pr.x + 12
        py   = content_top + log_h + 6
        for i, label in enumerate(choices):
            col = i % 2
            row = i // 2
            br    = pygame.Rect(px + col * (bw + 12), py + row * (bh + 8), bw, bh)
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
            lt    = fb.render(label, True, PANEL)
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
                surf.blit(pt, (pr.x + 14,
                               prompt_y - (len(_wrap(prompt[0], fs, content_rect.width - 28)) - 1 - j)
                               * (fs.get_height() + 3)))
        for i, (label, val) in enumerate([(_yn_labels[1], False), (_yn_labels[0], True)]):
            br    = pygame.Rect(pr.x + 14 + i * (BTN_W2 + BTN_SP), btn_y, BTN_W2, BTN_H2)
            hover = br.collidepoint(mpos)
            col_b = BTN_N if val else DARK_GRAY
            dr    = _premium_btn(surf, br, col_b, hover, radius=12)
            lt    = fb_lg.render(label, True, PANEL)
            surf.blit(lt, (dr.x + (dr.width  - lt.get_width())  // 2,
                           dr.y + (dr.height - lt.get_height()) // 2))
            content_rects.append((br, val))

    elif mode == "text":
        # ── 文字輸入框 ────────────────────────────────────────
        _draw_panel_log(surf, fs, log, content_rect, lines=2)
        surf.blit(fs.render(prompt[0], True, GRAY),
                  (pr.x + 14, content_top + content_rect.height - 88))
        ir2 = pygame.Rect(pr.x + 14, content_top + content_rect.height - 64, pr.width - 140, 36)
        pygame.draw.rect(surf, MILK, ir2, border_radius=10)
        t_done = fm.render(tvalue[0], True, BLACK)
        t_comp = fm.render(_composing[0], True, (150, 90, 180)) if _composing[0] else None
        t_cur  = fm.render("|", True, BLACK)
        xo = ir2.x + 8
        surf.blit(t_done, (xo, ir2.y + 5)); xo += t_done.get_width()
        if t_comp:
            surf.blit(t_comp, (xo, ir2.y + 5)); xo += t_comp.get_width()
        surf.blit(t_cur, (xo, ir2.y + 5))
        ok    = pygame.Rect(pr.right - 118, ir2.y, 104, 36)
        ok_dr = _premium_btn(surf, ok, BTN_N, ok.collidepoint(mpos), radius=12)
        ot    = fb_lg.render("確認", True, PANEL)
        surf.blit(ot, (ok_dr.x + (ok_dr.width  - ot.get_width())  // 2,
                       ok_dr.y + (ok_dr.height - ot.get_height()) // 2))
        content_rects.append((ok, "__ok__"))

    elif mode == "story":
        # ── 劇情對話框（VN 風格）────────────────────────────
        idx = _story_index[0]
        if 0 <= idx < len(_story_lines):
            entry   = _story_lines[idx]
            speaker = entry.get("speaker", "")
            text    = entry.get("text", "")
        else:
            speaker = ""
            text    = ""

        PAD      = 16
        text_top = content_rect.y + PAD

        # 說話者名稱框（左上角）
        if speaker:
            spk_surf = fb_lg.render(speaker, True, PANEL)
            spk_w    = spk_surf.get_width() + 20
            spk_h    = fb_lg.get_height() + 6
            spk_rect = pygame.Rect(content_rect.x + PAD,
                                   content_rect.y + 6, spk_w, spk_h)
            pygame.draw.rect(surf, BTN_N, spk_rect, border_radius=6)
            pygame.draw.rect(surf, CYAN,  spk_rect, 1, border_radius=6)
            surf.blit(spk_surf, (spk_rect.x + 10,
                                 spk_rect.y + (spk_h - spk_surf.get_height()) // 2))
            text_top = spk_rect.bottom + 8

        # 劇情文字（自動換行）
        wrapped = _wrap(text, fm, content_rect.width - PAD * 2)
        for ln in wrapped:
            surf.blit(fm.render(ln, True, WHITE),
                      (content_rect.x + PAD, text_top))
            text_top += fm.get_height() + 4

        # ▼ 點擊繼續（右下角，0.5 Hz 閃爍）
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            arr = fs.render("▼ 點擊繼續", True, BTN_N)
            surf.blit(arr, (content_rect.right - arr.get_width() - PAD,
                            content_rect.bottom - arr.get_height() - 6))

    elif mode == "exam_ready":
        # ── 考試開始按鈕（單一大按鈕，居中）────────────────────
        ex_label = _exam_ready_label[0]
        bw_ex    = min(320, content_rect.width - 48)
        bh_ex    = 56
        bx_ex    = content_rect.x + (content_rect.width - bw_ex) // 2
        by_ex    = content_rect.y + (content_rect.height - bh_ex) // 2
        br_ex    = pygame.Rect(bx_ex, by_ex, bw_ex, bh_ex)
        ex_hover = br_ex.collidepoint(mpos)
        _premium_btn(surf, br_ex, (180, 80, 30), ex_hover, radius=14)
        lt_ex = fb_lg.render(ex_label, True, PANEL)
        surf.blit(lt_ex, (br_ex.x + (br_ex.width  - lt_ex.get_width())  // 2,
                          br_ex.y + (br_ex.height - lt_ex.get_height()) // 2))
        content_rects.append((br_ex, 1))

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


# ── 側邊資訊面板常數 ──────────────────────────────────────────
_SIDE_PANEL_W = 148   # 左右面板各佔 148px
_SUBJ_SHORT_NAMES = {   # subject_exp 鍵值 → 面板顯示短名（最多 3 字）
    "商管程式設計": "商管程",
    "統計學":       "統計學",
    "經濟學":       "經濟學",
    "管理學":       "管理學",
    "會計學":       "會計學",
    "普通心理學":   "心理學",
    "總經原":       "總經原",
    "普通化學丙":   "普化丙",
}
_GRADE_ROWS = [       # (顯示名, grades 鍵值, 佔比)
    ("參與度", "參與度", "10%"),
    ("作  業", "作業",   "20%"),
    ("小  考", "小考",   "10%"),
    ("期  中", "期中",   "30%"),
    ("期  末", "期末",   "30%"),
]
_EXP_LVL_COLORS = [
    (148, 110, 72),   # 新手 — 暖沙
    ( 78, 172, 90),   # 普通 — 草綠
    ( 78, 165, 210),  # 熟練 — 晴天藍
    (190, 128, 12),   # 精通 — 琥珀金
]
_EXP_LVL_NAMES  = ["新手", "普通", "熟練", "精通"]
_EXP_LVL_THR    = [0, 30, 60, 90]


def _draw_exam_stress_fx(surf: pygame.Surface) -> None:
    """
    考前壓力視覺特效：
      距期中（第 8 週）或期末（第 16 週）剩 ≤ 2 週時
        → 各面板邊框套用紅色顫抖鬼影效果。
      距考試剩 1 週時
        → 額外在全畫面疊加微量紅色底色。
    """
    week = _week[0]
    if week <= 0:
        return

    # 計算距最近考試的週數
    dist_mid = 8  - week if week < 8  else 999
    dist_fin = 16 - week if week < 16 else 999
    dist     = min(dist_mid, dist_fin)

    if dist > 2 or dist <= 0:
        return

    # ── 各面板邊框 Rect（與 _draw_status_v2 / _side_panel_bg 對齊）──
    M  = 8
    PW = _SIDE_PANEL_W
    panels = [
        (pygame.Rect(M,             M,               WIN_W - M*2,  STATUS_H - M*2), 14),
        (pygame.Rect(M,             STATUS_H + M,    PW,           CHAR_H - M*2),   13),
        (pygame.Rect(WIN_W - M - PW, STATUS_H + M,  PW,           CHAR_H - M*2),   13),
        (pygame.Rect(M,             STATUS_H + CHAR_H + M, WIN_W - M*2, ACTION_H - M*2), 14),
    ]

    # 單張合併疊加 Surface → 只 blit 一次，效能最佳
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

    # dist == 1：全畫面底色微微泛紅
    if dist == 1:
        overlay.fill((200, 30, 20, 22))   # alpha ≈ 8.6%，極淡紅暈

    # 邊框顫抖：用時間種子亂數產生偏移，每 80 ms 換一次 → 顫抖感
    now = pygame.time.get_ticks()
    rng = random.Random(now // 80)
    amp = 3 if dist == 1 else 2           # 越近考試抖得越厲害
    red = (215, 68, 62)                   # 草莓紅（= RED 常數）

    for rect, brad in panels:
        for layer_i in range(3):
            alpha = 70 - layer_i * 20     # 70 → 50 → 30
            dx    = rng.randint(-amp, amp)
            dy    = rng.randint(-amp, amp)
            pygame.draw.rect(
                overlay,
                (*red, alpha),
                pygame.Rect(rect.x + dx, rect.y + dy, rect.width, rect.height),
                2, border_radius=brad,
            )

    surf.blit(overlay, (0, 0))


def _side_panel_bg(surf: pygame.Surface, x: int, y: int, w: int, h: int) -> None:
    """繪製白色筆記本卡片底色（陰影 + 奶白底 + 暖棕邊框）。"""
    # 投影
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 48), pygame.Rect(0, 0, w, h), border_radius=13)
    surf.blit(sh, (x + 3, y + 4))
    # 卡片底色
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (251, 248, 243, 242), pygame.Rect(0, 0, w, h), border_radius=13)
    surf.blit(bg, (x, y))
    # 邊框
    pygame.draw.rect(surf, (185, 163, 138), pygame.Rect(x, y, w, h), 1, border_radius=13)


def _draw_exp_panel(surf: pygame.Surface, fm, fmic, player) -> None:
    """左側：各科課業熟練度面板（動態，含加簽科目）。"""
    if player is None:
        return
    fb    = _font_bold[0]    or fmic   # size-17 bold（科目名 / 徽章）
    fb_lg = _font_bold_lg[0] or fm    # size-22 bold（標題）
    PW  = _SIDE_PANEL_W
    PAD = 9
    sx, sy = 8, STATUS_H + 8
    sh  = CHAR_H - 16

    _side_panel_bg(surf, sx, sy, PW, sh)

    # 標題
    title = fb_lg.render("課業熟練度", True, YELLOW)
    surf.blit(title, (sx + (PW - title.get_width()) // 2, sy + 7))
    div_y = sy + 7 + title.get_height() + 5
    pygame.draw.line(surf, (205, 188, 168),
                     (sx + PAD, div_y), (sx + PW - PAD, div_y))

    # 動態科目列表（排除輔助鍵 "綜合"）
    subjects = [(k, v) for k, v in player.subject_exp.items() if k != "綜合"]
    n     = max(len(subjects), 1)
    content_h = sy + sh - 6 - (div_y + 8)
    row_h = content_h // n
    bar_h = max(8, min(13, row_h - fb.get_height() - 5))
    bar_w = PW - PAD * 2
    row_y = div_y + 8

    for full, exp in subjects:
        short = _SUBJ_SHORT_NAMES.get(full, full[:3])
        # 計算等級
        lvl = 0
        for i, thr in enumerate(_EXP_LVL_THR):
            if exp >= thr:
                lvl = i
        col      = _EXP_LVL_COLORS[lvl]
        lvl_name = _EXP_LVL_NAMES[lvl]

        # 科目短名（左）+ 等級徽章（右）
        lbl   = fb.render(short, True, WHITE)
        badge = fmic.render(lvl_name, True, col)
        surf.blit(lbl,   (sx + PAD, row_y))
        surf.blit(badge, (sx + PW - PAD - badge.get_width(),
                          row_y + (fb.get_height() - badge.get_height()) // 2))

        # 進度條
        by = row_y + fb.get_height() + 2
        pygame.draw.rect(surf, (215, 204, 192),
                         pygame.Rect(sx + PAD, by, bar_w, bar_h), border_radius=4)
        fw = int(bar_w * exp / 100)
        if fw > 0:
            pygame.draw.rect(surf, col,
                             pygame.Rect(sx + PAD, by, fw, bar_h), border_radius=4)

        # exp 數字（置中於條內）
        val_lbl = fmic.render(f"{exp}/100", True, PANEL)
        surf.blit(val_lbl, (sx + PAD + (bar_w - val_lbl.get_width()) // 2,
                            by + (bar_h - val_lbl.get_height()) // 2))

        row_y += row_h


def _draw_grade_panel(surf: pygame.Surface, fm, fmic, player) -> None:
    """右側：已發生成績記錄面板（未公布項目顯示 ──）。"""
    if player is None:
        return
    fb_lg = _font_bold_lg[0] or fm   # 粗體 size-22（標題 / 科目名 / 分數）
    PW  = _SIDE_PANEL_W
    PAD = 9
    sx  = WIN_W - 8 - PW
    sy  = STATUS_H + 8
    sh  = CHAR_H - 16

    _side_panel_bg(surf, sx, sy, PW, sh)

    # 標題
    title = fb_lg.render("成績記錄", True, YELLOW)
    surf.blit(title, (sx + (PW - title.get_width()) // 2, sy + 7))
    div_y = sy + 7 + title.get_height() + 5
    pygame.draw.line(surf, (205, 188, 168),
                     (sx + PAD, div_y), (sx + PW - PAD, div_y))

    # 只顯示已公布且有分數的欄位
    _revealed = getattr(player, "revealed_grades", set())
    active_rows = [(label, key, weight)
                   for label, key, weight in _GRADE_ROWS
                   if key in _revealed and player.grades.get(key, 0.0) > 0.0]

    if not active_rows:
        hint = fmic.render("尚無成績記錄", True, GRAY)
        surf.blit(hint, (sx + (PW - hint.get_width()) // 2, div_y + 14))
        return

    content_h = sy + sh - 6 - (div_y + 8)
    row_h     = content_h // len(active_rows)
    row_y     = div_y + 8

    for label, key, weight in active_rows:
        val = player.grades.get(key, 0.0)

        # 科目名（左）+ 佔比（右）
        lbl_s = fb_lg.render(label, True, WHITE)        # 粗體科目名
        wt_s  = fmic.render(weight, True, (130, 90, 55))
        surf.blit(lbl_s, (sx + PAD, row_y))
        surf.blit(wt_s,  (sx + PW - PAD - wt_s.get_width(),
                           row_y + (fb_lg.get_height() - wt_s.get_height()) // 2))

        # 分數
        col       = GREEN if val >= 80 else (YELLOW if val >= 60 else RED)
        score_str = f"{val:.1f}"
        score_s   = fb_lg.render(score_str, True, col)
        surf.blit(score_s,
                  (sx + (PW - score_s.get_width()) // 2,
                   row_y + fb_lg.get_height() + 3))

        row_y += row_h


def _draw_roll_call_note(surf: pygame.Surface, fmic) -> None:
    """
    在成績記錄面板左側繪製點名警示便利貼。
    _roll_call_course[0] 為空字串時不顯示。
    """
    course = _roll_call_course[0]
    if not course:
        return

    fb = _font_bold[0] or fmic

    # ── 便利貼 Surface（100×68 px）────────────────────────────
    NW, NH = 100, 68
    note = pygame.Surface((NW, NH), pygame.SRCALPHA)

    # 主底色（亮黃便利貼）
    pygame.draw.rect(note, (255, 228, 52, 242),
                     pygame.Rect(0, 0, NW, NH), border_radius=4)

    # 折角（右下角）
    pygame.draw.polygon(note, (196, 162, 18, 230),
                        [(NW - 14, NH), (NW, NH - 14), (NW, NH)])
    pygame.draw.line(note, (155, 128, 8, 190),
                     (NW - 14, NH - 1), (NW, NH - 14), 1)

    # 頂部警示色帶（深橘紅）
    pygame.draw.rect(note, (210, 52, 42, 225),
                     pygame.Rect(0, 0, NW, 15), border_radius=4)

    # 色帶文字
    tape_s = fmic.render("點 名 通 知", True, (255, 240, 230))
    note.blit(tape_s, ((NW - tape_s.get_width()) // 2,
                        (15 - tape_s.get_height()) // 2))

    # 課程短名（粗體，置中）
    short = _SUBJ_SHORT_NAMES.get(course, course[:4])
    sub_s = fb.render(short, True, (80, 42, 10))
    note.blit(sub_s, ((NW - sub_s.get_width()) // 2, 20))

    # 提示小字（兩行）
    r1 = fmic.render("本週將點名", True, (120, 68, 18))
    r2 = fmic.render("記得出席！", True, (160, 78, 18))
    note.blit(r1, ((NW - r1.get_width()) // 2, 44))
    note.blit(r2, ((NW - r2.get_width()) // 2, 56))

    # ── 旋轉 -8°（便利貼略歪，增加手感）─────────────────────
    rotated = pygame.transform.rotate(note, -8)
    rw, rh  = rotated.get_size()

    # ── 定位：成績面板左邊緣偏左 24 px 為便利貼中心 ──────────
    PW = _SIDE_PANEL_W
    cx = WIN_W - 8 - PW - 24   # 804 - 24 = 780
    cy = STATUS_H + 8 + 130    # 175 + 8 + 130 = 313

    # 陰影（偏移 +5, +6 的半透明矩形）
    shad_sf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    pygame.draw.rect(shad_sf, (0, 0, 0, 55),
                     pygame.Rect(0, 0, rw, rh), border_radius=6)
    surf.blit(shad_sf, (cx - rw // 2 + 5, cy - rh // 2 + 6))

    # 便利貼本體
    surf.blit(rotated, (cx - rw // 2, cy - rh // 2))


# ═══════════════════════════════════════════════════════════════
#  人物立繪輔助函式
# ═══════════════════════════════════════════════════════════════

def _portrait_orig_load(key: str):
    """載入並快取原始立繪（未縮放）。"""
    if key in _portrait_orig:
        return _portrait_orig[key]
    path = os.path.join(_CHAR_ART_DIR, f"{key}.webp")
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
        if sat <= 60:
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


def _draw_character_art(surf, rect):
    """
    人物立繪區：顯示玩家選擇的角色立繪（含淡入淡出轉場）。
    rect 為整個立繪區的 Rect（STATUS_H..STATUS_H+CHAR_H, 全寬）。
    """
    key = _get_portrait_key()
    _portrait_switch(key, rect.width, rect.height)

    now = pygame.time.get_ticks()
    if _portrait_fade_t0[0] > 0:
        t = min((now - _portrait_fade_t0[0]) / _PORTRAIT_FADE_MS, 1.0)
    else:
        t = 1.0

    def _blit_p(p_surf, alpha):
        if p_surf is None:
            return
        pw = p_surf.get_width()
        ph = p_surf.get_height()
        px = rect.x + (rect.width - pw) // 2
        py = rect.y + rect.height - ph   # 底部對齊
        if alpha < 255:
            tmp = p_surf.copy()
            tmp.set_alpha(alpha)
            surf.blit(tmp, (px, py))
        else:
            surf.blit(p_surf, (px, py))

    # 淡出：前一張
    if _portrait_prev[0] is not None and t < 1.0:
        _blit_p(_portrait_prev[0], int(255 * (1.0 - t)))

    # 淡入：當前張
    if _portrait_curr[0] is not None:
        _blit_p(_portrait_curr[0], int(255 * t))
        if t >= 1.0:
            _portrait_prev[0]    = None
            _portrait_fade_t0[0] = 0


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
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22
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
        nt = fb_lg.render(item["name"], True, WHITE)
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
        # 購買按鈕：「購買 」+ 金幣圖示 + 「{price}」，整體置中
        _bc_r   = max(5, int(fb.get_height() * 0.38))   # 金幣半徑隨字型縮放
        _bc_col = PANEL if afford else GRAY
        pt_t    = fb.render(f"購買  ", True, _bc_col)
        pc_t    = fb.render(f" {item['price']}", True, _bc_col)
        _brow_w = pt_t.get_width() + _bc_r * 2 + pc_t.get_width()
        _brow_x = bdr_r.x + (bdr_r.width - _brow_w) // 2
        _brow_y = bdr_r.y + (bdr_r.height - pt_t.get_height()) // 2
        surf.blit(pt_t, (_brow_x, _brow_y))
        _draw_icon_coin(surf,
                        _brow_x + pt_t.get_width() + _bc_r,
                        bdr_r.centery, _bc_r)
        surf.blit(pc_t, (_brow_x + pt_t.get_width() + _bc_r * 2, _brow_y))

        buy_rects.append((buy_r, i))

    _shop_hover_idx[0] = hover_this

    # ── 右側說明面板 ─────────────────────────────────────────────
    rp = pygame.Rect(RP_X, 15, RP_W, WIN_H - 80)
    _soft_shadow(surf, rp, radius=16, alpha=55, offset=(3, 5), spread=6)
    pygame.draw.rect(surf, PANEL, rp, border_radius=16)
    _gloss_rect(surf, rp)
    pygame.draw.rect(surf, CYAN, rp, 2, border_radius=16)

    # 標題
    tt = fb_lg.render("效果說明", True, TITLE)
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
        hn = fb_lg.render(hi["name"], True, WHITE)
        surf.blit(hn, (rp.x + 14, desc_y))
        # 售價：「售價：」+ 金幣 + 「{price} 元」
        _hr    = 9
        _hl_t  = fb.render("售價：", True, YELLOW)
        _hn2_t = fb.render(f" {hi['price']} 元", True, YELLOW)
        _hy    = desc_y + fm.get_height() + 6
        _hcy   = _hy + _hl_t.get_height() // 2
        surf.blit(_hl_t, (rp.x + 14, _hy))
        _draw_icon_coin(surf, rp.x + 14 + _hl_t.get_width() + _hr, _hcy, _hr)
        surf.blit(_hn2_t, (rp.x + 14 + _hl_t.get_width() + _hr * 2, _hy))
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
    # 剩餘金錢：「剩餘金錢：」+ 金幣圖示 + 數字，水平置中
    mval   = player.money if player else 0
    _mr    = 11                                         # 金幣圖示半徑
    _ml_t  = fb_lg.render("剩餘金錢：", True, YELLOW)
    _mn_t  = fb_lg.render(f"{mval}", True, YELLOW)
    _mrow_w = _ml_t.get_width() + _mr * 2 + 4 + _mn_t.get_width()
    _mrow_x = rp.x + (rp.width - _mrow_w) // 2
    _mrow_y = rp.bottom - 94
    _mcy    = _mrow_y + _ml_t.get_height() // 2
    surf.blit(_ml_t, (_mrow_x, _mrow_y))
    _draw_icon_coin(surf, _mrow_x + _ml_t.get_width() + _mr, _mcy, _mr)
    surf.blit(_mn_t, (_mrow_x + _ml_t.get_width() + _mr * 2 + 4, _mrow_y))

    # 離開道具店按鈕
    eb   = pygame.Rect(rp.x + 14, WIN_H - 60, rp.width - 28, 44)
    ehov = eb.collidepoint(mpos)
    edr  = _premium_btn(surf, eb, (200, 78, 58), ehov, radius=14)
    et   = fb_lg.render("離開道具店", True, PANEL)
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
        _sfx["damage6"]     = _ld("damage6.wav")
    except Exception:
        pass

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("如何渡過這學期？")
    clock  = pygame.time.Clock()

    fl = _get_font(40)   # 開始 / 結束畫面標題大字
    fm = _get_font(22)
    fs = _get_font(17)
    _font_micro[0]   = _get_font(11)        # 週次輪盤小字
    _font_bold[0]    = _get_font_bold(17)   # 粗體 size-17（按鈕 / 小文字）
    _font_bold_lg[0] = _get_font_bold(22)   # 粗體 size-22（標題 / 上方視窗）
    _font_bold_xl[0] = _get_font_bold(26)   # 粗體 size-26（日曆週次大字）

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

    # ── 批次載入所有週次背景圖 ────────────────────────────────
    _unique_bg_files = sorted(set(v for v in _WEEK_BG.values() if v is not None))
    for _fn in _unique_bg_files:
        _img = _load_cover(os.path.join(_bg_dir, _fn), WIN_W, WIN_H)
        if _img is not None:
            _bg_surfs[_fn] = _img
    # 用第 1-2 週背景作初始底圖（無圖則保持漸層）
    _init_bg = _bg_surfs.get("1234_background.webp")
    if _init_bg is not None:
        _bg_current[0] = _init_bg
        _grads["bg"]   = _init_bg   # 保持 fallback 相容
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
                _prompt[0]      = cmd[1]
                _yn_labels[0]   = cmd[2] if len(cmd) > 2 else "是"
                _yn_labels[1]   = cmd[3] if len(cmd) > 3 else "否"
                _yn_show_ctx[0] = cmd[4] if len(cmd) > 4 else True
                _mode[0] = "yn"
            elif tag == "event_ok":
                _event_ok_text[0]         = cmd[1]
                _event_ok_border_color[0] = None
                _mode[0]                  = "event_ok"
            elif tag == "event_ok_col":
                _event_ok_text[0]         = cmd[1]
                _event_ok_border_color[0] = cmd[2]
                _mode[0]                  = "event_ok"
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
                elif cmd[1] == "game" and _weather_type[0] is None:
                    _weather_reset()   # 首次進入遊戲階段時確保天氣已初始化
            elif tag == "ripple":
                _ripple_t0[0] = pygame.time.get_ticks()
                _play_sfx("cc_click")
            elif tag == "bgm_week":
                _request_bgm(_WEEK_BGM.get(cmd[1]))
                _request_week_bg(_WEEK_BG.get(cmd[1]))
                _weather_reset()   # 每週隨機切換天氣
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
            elif tag == "cc_portrait":
                _cc_mode[0] = "portrait"
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
                _cc_stat_base[0]     = cmd[2] if len(cmd) > 2 else cmd[1]
                _cc_stat_talent[0]   = cmd[3] if len(cmd) > 3 else {}
                _cc_stat_de_level[0] = cmd[4] if len(cmd) > 4 else {}
                _cc_stat_vals[:]     = [10, 10, 10]
                _cc_stat_raw[:]      = ["10", "10", "10"]
                _cc_active_stat[0]   = None
            elif tag == "cc_extra":
                _cc_extra_data[:]  = cmd[1]
                _cc_extra_intel[0] = cmd[2]
                _cc_extra_sel.clear()
                _cc_extra_warn[0]  = 0
                _cc_mode[0]        = "extra"
            elif tag == "cc_slot":
                results = cmd[1]
                _slot_results[:] = results
                _slot_phase[:]   = ["idle", "idle", "idle"]
                _slot_stop_t[:]  = [0, 0, 0]
                _slot_start_t[:] = [0, 0, 0]
                _cc_confetti.clear()
                _cc_shake_end[0] = 0
                _cc_mode[0]      = "slot"
                # 第一槽立刻開始旋轉
                _slot_phase[0]    = "spinning"
                _slot_start_t[0]  = pygame.time.get_ticks()
            elif tag == "cc_summary":
                _cc_summary_data[0] = cmd[1]
                _cc_mode[0]         = "summary"
            elif tag == "cc_de_level":
                _cc_mode[0] = "de_level"
                _cc_data[0] = cmd[1]   # levels list
                _cc_sel.clear()
            elif tag == "cc_talent":
                _cc_mode[0] = "talent"
                _cc_data[0] = cmd[1]   # candidates list
                _cc_sel.clear()
            elif tag == "set_time":
                new_time = cmd[1]
                # 時間有減少 → 觸發震動特效（每次扣時都閃）
                if new_time < _time_units[0]:
                    _time_shake_t0[0] = pygame.time.get_ticks()
                _time_units[0] = new_time
            elif tag == "time_overflow_warn":
                # 時間即將變負 → 震動 + damage6 音效
                _time_shake_t0[0] = pygame.time.get_ticks()
                _play_sfx("damage6")
            elif tag == "screen_shake":
                _evt_shake_t0[0] = pygame.time.get_ticks()
                _play_sfx("damage6")
            elif tag == "roll_call_set":
                _roll_call_course[0] = cmd[1]
            elif tag == "roll_call_clear":
                _roll_call_course[0] = ""
            elif tag == "special_disabled":
                _special_disabled.clear()
                _special_disabled.update(cmd[1])
            elif tag == "subj_popup":
                _subj_popup_title[0] = cmd[1]
                _subj_popup_opts.clear()
                _subj_popup_opts.extend(cmd[2])
                _subj_popup_rects.clear()
                _subj_popup_active[0] = True
            elif tag == "timetable":
                _modal[0]      = "timetable"
                _modal_data[0] = cmd[1]   # courses list
            elif tag == "grade_report":
                _modal[0]      = "grade_report"
                _modal_data[0] = cmd[1]   # items list
            elif tag == "story":
                _story_lines.clear()
                _story_lines.extend(cmd[1])
                _story_index[0] = 0
                _mode[0] = "story"
            elif tag == "exam_ready":
                _exam_ready_label[0] = cmd[1]
                _mode[0] = "exam_ready"

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
        info_btn_rect  = None
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
                _draw_game_bg(screen)
                shop_buy_rects, shop_exit_btn = [], None
            elif _yoff != 0:
                # 動畫中：先畫遊戲底圖，再把道具店 Surface 蓋上並偏移
                _draw_game_bg(screen)
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
            elif cm == "portrait":
                pcards = _draw_cc_portrait(screen, fm, fs, mpos)
                _cc_btn_cache["portrait_cards"] = pcards
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
                    _cc_stat_total[0], _cc_stat_base[0], _cc_stat_talent[0],
                    _cc_stat_vals, _cc_stat_raw,
                    _cc_active_stat[0], mpos, _cc_stat_de_level[0])
                _cc_btn_cache["stats_minus"] = mr
                _cc_btn_cache["stats_plus"]  = pr
                _cc_btn_cache["stats_ok"]    = ok
            elif cm == "extra":
                crects, ok = _draw_cc_extra_events(screen, fm, fs, mpos)
                _cc_btn_cache["extra_cards"] = crects
                _cc_btn_cache["extra_ok"]    = ok
            elif cm == "slot":
                ok = _draw_cc_slot_machine(screen, fm, fs, mpos)
                _cc_btn_cache["slot_ok"] = ok
            elif cm == "summary":
                s_r, r_r = _draw_cc_summary(screen, fm, fs, mpos, game_mode=False)
                _cc_btn_cache["summary_start"]   = s_r
                _cc_btn_cache["summary_restart"] = r_r
            elif cm == "de_level":
                drects, ok = _draw_cc_de_level(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel[0] if _cc_sel else None, mpos)
                _cc_btn_cache["de_level_cards"] = drects
                _cc_btn_cache["de_level_ok"]    = ok
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
            _draw_game_bg(screen)
            # ── 動態天氣特效（背景圖與 UI 之間）────────────────────
            _draw_weather(screen, pygame.time.get_ticks())
            # 狀態欄（新版，含頭像 + 道具店 + 資訊一覽按鈕）
            shop_btn_rect, info_btn_rect = _draw_status_v2(screen, fm, fs, _player[0], sr, mpos)
            # 人物立繪區
            _draw_character_art(screen, cr)
            # 左側熟練度面板 / 右側成績記錄面板
            _draw_exp_panel(screen, fm, _font_micro[0], _player[0])
            _draw_grade_panel(screen, fm, _font_micro[0], _player[0])
            # 點名警示便利貼（疊在成績面板左側邊緣）
            _draw_roll_call_note(screen, _font_micro[0])
            # 非標準選項 / yn / event_ok → 需先計算，讓底部面板知道要不要留白
            _cp_active = (
                (_mode[0] == "choices" and bool(_choices)
                 and not all(c in _STANDARD_ACTIONS for c in _choices))
                or _mode[0] in ("yn", "event_ok")
            )
            # 底部行動面板：中央彈窗已啟用時改用空白選項，避免重複顯示
            _panel_mode    = "choices" if _cp_active else _mode[0]
            _panel_choices = []        if _cp_active else _choices
            btn_rects, end_week_btn = _draw_action_panel(
                screen, fm, fs, _panel_mode, _panel_choices, _log,
                _prompt, _tvalue, ar, _time_units[0], mpos)
            # 考前壓力特效（邊框顫抖 + 底色微微泛紅）：疊在所有面板之上、彈窗之下
            _draw_exam_stress_fx(screen)
            # 行動結果彈出視窗（右側由右而左滑入）
            _draw_action_popup(screen, fs)
            # 中央彈出視窗（yn / 非標準選項）
            _draw_cp = (
                (_mode[0] == "choices" and bool(_choices)
                 and not all(c in _STANDARD_ACTIONS for c in _choices))
                or _mode[0] == "yn"
            )
            if _draw_cp:
                _choice_popup_rects.clear()
                _choice_popup_rects.extend(
                    _draw_choice_popup(screen, fm, fs, _mode[0], _choices,
                                       _log, _prompt[0], _yn_labels, mpos))
            else:
                _choice_popup_rects.clear()
            # 突發事件通知彈窗（單按鈕，最上層）
            if _mode[0] == "event_ok":
                _event_ok_popup_rects.clear()
                _event_ok_popup_rects.extend(
                    _draw_event_ok_popup(screen, fm, fs, mpos))
            else:
                _event_ok_popup_rects.clear()
            # 科目選擇彈出視窗（中央 modal，蓋在所有遊戲 UI 之上）
            if _subj_popup_active[0]:
                _subj_popup_rects.clear()
                _subj_popup_rects.extend(
                    _draw_subj_popup(screen, fm, fs, mpos))

        # ── 玩家資訊一覽 modal（遊戲中查閱，浮在所有畫面之上）─────
        if _phase[0] == "game" and _info_modal_active[0]:
            _close_r, _ = _draw_cc_summary(screen, fm, fs, mpos, game_mode=True)
            _info_modal_close[0] = _close_r

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

        # ── 行動成功白光閃爍（漣漪之上，點擊波紋之下）──────────
        _draw_action_flash(screen, pygame.time.get_ticks())

        # ── 點擊波紋特效（最最頂層，覆蓋一切 UI）──────────────
        _draw_click_effects(screen, pygame.time.get_ticks())

        # ── 突發事件全螢幕震動（最後一步，copy+blit 整張畫面偏移）──
        _sdx, _sdy = _get_evt_shake_offset()
        if _sdx != 0 or _sdy != 0:
            _shk_copy = screen.copy()
            screen.fill((0, 0, 0))
            screen.blit(_shk_copy, (_sdx, _sdy))

        pygame.display.flip()

        # ── pygame 事件 ───────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # 點擊波紋特效（任何畫面均觸發，無條件生成）
                _click_spawn(ev.pos[0], ev.pos[1], pygame.time.get_ticks())

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

                # ── 遊戲中資訊一覽 modal 攔截 ────────────────────
                if _phase[0] == "game" and _info_modal_active[0]:
                    close_r = _info_modal_close[0]
                    if close_r and close_r.collidepoint(ev.pos):
                        _play_sfx("back")
                        _info_modal_active[0] = False
                    continue   # modal 開著時攔截所有點擊

                # ── 遊戲中「資訊一覽」按鈕開啟 modal ────────────
                if _phase[0] == "game" and info_btn_rect is not None \
                        and info_btn_rect.collidepoint(ev.pos):
                    _play_sfx("ui_click")
                    player = _player[0]
                    if player is not None:
                        from character import EXTRA_EVENTS as _EXTRA_EVTS
                        _cc_summary_data[0] = {
                            "name":            player.name,
                            "department":      player.department,
                            "de_level":        player.de_level,
                            "stamina":         player.stamina_max,
                            "intel":           player.intel,
                            "luck":            player.luck,
                            "money":           player.money,
                            "combined_talent": player.talent,
                            "slot_results":    getattr(player, "slot_results", []),
                            "drawbacks":       player.drawbacks,
                            "extra_ev_ids":    player.extra_events,
                            "extra_ev_data":   list(_EXTRA_EVTS),
                        }
                        _info_modal_active[0] = True
                    continue

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

                    # 劇情對話框：任意點擊推進（優先級次於突發事件彈窗）
                    if _mode[0] == "story":
                        _play_sfx("ui_click")
                        _story_index[0] += 1
                        if _story_index[0] >= len(_story_lines):
                            _mode[0] = None
                            _reply_event.set()
                        continue

                    # 突發事件彈窗優先攔截（最高優先）
                    if _mode[0] == "event_ok":
                        for (br, _) in _event_ok_popup_rects:
                            if br.collidepoint(ev.pos):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _reply_val[0] = True
                                _mode[0] = None
                                _event_ok_popup_rects.clear()
                                _event_ok_border_color[0] = None
                                _reply_event.set()
                                break
                        continue   # 彈窗開啟時阻擋所有點擊

                    # 非標準選項 / yn 中央彈窗優先攔截（最高優先）
                    _cp_now = (
                        (_mode[0] == "choices" and bool(_choices)
                         and not all(c in _STANDARD_ACTIONS for c in _choices))
                        or _mode[0] == "yn"
                    )
                    if _cp_now:
                        for (br, val) in _choice_popup_rects:
                            if br.collidepoint(ev.pos):
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                if _mode[0] == "choices":
                                    _play_sfx("ui_click")
                                    _reply_val[0] = val
                                    _mode[0] = None
                                    _choices.clear()
                                    _reply_event.set()
                                else:  # yn
                                    _play_sfx("ui_click" if val else "back")
                                    _reply_val[0] = val
                                    _mode[0] = None
                                    _reply_event.set()
                                break
                        continue   # 彈窗開啟時所有點擊都不透傳

                    # 科目選擇 popup 優先攔截所有點擊
                    if _subj_popup_active[0]:
                        for (br, val) in _subj_popup_rects:
                            if br.collidepoint(ev.pos):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _reply_val[0] = val
                                _subj_popup_active[0] = False
                                _subj_popup_opts.clear()
                                _subj_popup_rects.clear()
                                _reply_event.set()
                                break
                        continue   # 無論有沒有點中按鈕，都不透傳到下方邏輯

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
                            elif _mode[0] == "exam_ready":
                                _play_sfx("ui_click")
                                _reply_val[0] = val
                                _mode[0] = None
                                _exam_ready_label[0] = ""
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
