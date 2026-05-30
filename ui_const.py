# ============================================================
#  ui_const.py -- jPure constants
#  by refactor_ui.py
# ============================================================
import os
import sys

def resource_path(*parts: str) -> str:
    """
    回傳資源檔案的絕對路徑。
    - 開發環境：相對於本檔案所在目錄（專案根目錄）
    - PyInstaller --onefile：相對於 sys._MEIPASS 解壓目錄
    - pygbag（WebAssembly）：相對於專案根目錄
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)

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

# ── 人物立繪系統 ──────────────────────────────────────────────────────
_CHAR_ART_DIR      = resource_path("asset", "picture", "character")

_PORTRAIT_FADE_MS        = 200   # 淡入總時長（ms）
PORTRAIT_DISPLAY_H_FACTOR = 2.2  # 立繪縱向放大倍率（腰部以上可見，約 45% 顯示）
PORTRAIT_TOP_PAD          = 15   # 頭部距立繪區頂部的留白（px）

_TIME_SHAKE_MS = 520      # 整段動畫時長（ms）

_EVT_SHAKE_MS  = 480      # 震動總時長（ms）

_EVT_SHAKE_AMP = 14       # 最大震動幅度（px）

_STAMP_SHAKE_MS  = 180    # 印章晃動時長（ms）

_STAMP_SHAKE_AMP = 6      # 印章晃動幅度（px）

_ACTION_FLASH_MS = 300    # 整段閃爍時長（ms）

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

# ── 道具店小圖示 ──────────────────────────────────────────────
_SHOP_ICON_DIR = resource_path("asset", "picture", "small_object")

_SHOP_ITEM_ICON_MAP: dict = {
    "coffee":               "i_coffee",
    "snack":                "i_cake",
    "energy_drink_monster": "i_mdrink",
    "energy_drink_bplus":   "i_bdrink",
    "textbook_ref":         "i_note",
    "memory_toast":         "i_toast",
    "game_console":         "i_game",
    "idol_photo":           "i_photo",
    "exam_pencil":          "i_pencil",
    "temple_amulet":        "i_peace",
    "lucky_omamori":        "i_yuso",
}

POPUP_DURATION = 3400  # 整體顯示時長（ms）

POPUP_IN_MS    = 320   # 滑入動畫時長（ms）

POPUP_OUT_MS   = 280   # 滑出動畫時長（ms）

RIPPLE_DURATION  = 900       # 總時長（ms）

# ── BGM 狀態（非阻塞淡入淡出） ───────────────────────────────
BGM_FADE_MS    = 1500        # 淡出 / 淡入各 1.5 秒

# 週次 → BGM 對照表（None = 待定，播放時靜音）
_WEEK_BGM: dict = {
    1:  "Music-Town_Day.ogg",
    2:  "Music-Town_Day.ogg",
    3:  "Music-Ocean_Day.ogg",
    4:  "Music-Ocean_Day.ogg",
    5:  "Music-Skeletron.ogg",
    6:  "Music-Skeletron.ogg",
    7:  "Music-Deerclops.ogg",
    8:  "Music-Rainbow_Boulder_loop.ogg",
    9:  "Music-Forest_Day_Otherworldly.ogg",
    10: "Music-Forest_Day_Otherworldly.ogg",
    11: "Music-Ice_biome.ogg",
    12: "Music-Ice_biome.ogg",
    13: "Music-Storm.ogg",
    14: "Music-Storm.ogg",
    15: "Music-Lunar_Boss.ogg",
    16: "final_bgm.ogg",
}

# ── 遊戲背景 crossfade ─────────────────────────────────────────
BG_FADE_MS  = 800         # crossfade 時長（ms）

# 週次 → 背景圖檔名對照表（None = 待補圖，保持當前背景）
_WEEK_BG: dict = {
    1:  "1234_background.jpg",
    2:  "1234_background.jpg",
    3:  "34_background.jpg",
    4:  "34_background.jpg",
    5:  "56_background.jpg",
    6:  "56_background.jpg",
    7:  "7_background.jpg",
    8:  "7_background.jpg",
    9:  "910_background.jpg",
    10: "910_background.jpg",
    11: "1112_background.jpg",
    12: "1112_background.jpg",
    13: "1314_background.jpg",
    14: "1314_background.jpg",
    15: "15_background.jpg",
    16: "15_background.jpg",
}

SHOP_SLIDE_MS   = 370        # 單向滑動時長（ms）

PANEL_SLIDE_MS   = 280        # 單向滑動時長（ms）

_WEATHER_TYPES = ["sun", "leaves_green", "leaves_orange", "sakura", "rain", "fog"]

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

# 霧團顏色組（冷灰白系）
_WX_FOG_PALETTE = [
    (218, 224, 232),
    (228, 232, 238),
    (212, 220, 230),
    (225, 228, 235),
    (220, 226, 234),
]

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

_CC_PTCL_COLORS = [
    (180,  80, 255),
    (210, 100, 255),
    (140,  60, 230),
    (200, 120, 255),
    (160,  70, 240),
    (220,  90, 255),
    (170, 110, 248),
    (230, 140, 255),
]

# 標準行動名稱集合（用來判斷是否顯示圓形按鈕）
_STANDARD_ACTIONS = {"認真讀書", "正常上課", "社團活動", "打工賺錢",
                     "好好休息", "幫助朋友", "🏪 前往道具店"}

# ── 特殊行動（面板右側）常數 ──────────────────────────────────
_BUMP_H  = 68    # 凸起從面板頂邊往上延伸的高度（px）

_BUMP_W  = 240   # 凸起寬度（px）

_BUMP_R  = 26    # 特殊行動按鈕半徑

_BUMP_SP = 74    # 凸起內三顆按鈕水平間距

_BUMP_IR = 12    # 凸起與面板交接處的內凹弧半徑

# ── 底部行動面板折疊 toggle ────────────────────────────────────
AP_COLLAPSE_MS = 280   # 折疊/展開動畫時長（ms）
_AP_TOGGLE_W   = 80    # toggle 按鈕寬（px）
_AP_TOGGLE_H   = 22    # toggle 按鈕高（px）

_SPECIAL_ACTION_NAMES = ["熬夜", "翹課", "進食"]

_SPECIAL_ICONS = {"熬夜": "月", "翹課": "逃", "進食": "食"}

# 各行動的體力消耗說明 + 預期效果（用於 hover 提示列）
_ACTION_INFO = {
    "認真讀書": ("消耗體力 4", "課業熟練度 +8    自我滿足度 -5"),
    "正常上課": ("消耗體力 2", "課業熟練度 +4    課堂參與度 +5"),
    "社團活動": ("體力-3，30%免", "滿足度+10~15"),
    "打工賺錢": ("消耗體力 4", "金錢 +150    自我滿足度 +3"),
    "好好休息": ("恢復體力 6", "自我滿足度 +8"),
    "幫助朋友": ("消耗體力 2", "自我滿足度 +12"),
    # 特殊行動
    "熬夜": ("體力 -10, 時間 +2", "更容易睡過頭    滿足感 -5"),
    "翹課": ("體力 +10, 時間 +1", "可能會有不好的影響"),
    "進食": ("金錢 -50, 體力 +10", "獲得飽腹狀態"),
}

# ── 行動按鈕 Icon ──────────────────────────────────────────────
_ACTION_ICON_FILES = {
    "認真讀書": "study_icon.png",
    "正常上課": "class_icon.png",
    "社團活動": "club_icon.png",
    "打工賺錢": "work_icon.png",
    "好好休息": "rest_icon.png",
    "幫助朋友": "friend_icon.png",
    "熬夜":     "night_icon.png",
    "翹課":     "escape_icon.png",
    "進食":     "eat_icon.png",
}

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


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
