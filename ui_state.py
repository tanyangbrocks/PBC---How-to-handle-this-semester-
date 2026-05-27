# ============================================================
#  ui_state.py -- Runtime mutable state
#  by refactor_ui.py
# ============================================================
import threading
import queue
import os
import pygame

from ui_const import *

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

_portrait_prefix   = [""]    # "b1" | "g1"，角色創建時選定

_portrait_curr_key = [""]    # 目前顯示的立繪 key（變更偵測用）

_portrait_curr     = [None]  # 目前顯示的立繪 Surface（已縮放）

_portrait_prev     = [None]  # 淡出中的前一張立繪 Surface

_portrait_fade_t0  = [0]     # 淡入開始時間戳（ms，0=無淡入中）

_portrait_orig:   dict = {}  # key -> 原始 Surface（未縮放，已快取）

_portrait_scl:    dict = {}  # (key,w,h) -> 縮放後 Surface（已快取）

_portrait_head_cache: dict = {}  # prefix -> 圓形頭像 Surface (84px，已快取)

_font_micro    = [None]   # 極小字型（週次輪盤數字用）

_font_bold     = [None]   # 粗體字型 size-17（行動按鈕標籤用）

_font_bold_lg  = [None]   # 粗體字型 size-22（標題 / 上方視窗用）

_font_bold_xl  = [None]   # 粗體字型 size-26（日曆週次大字用）

_extra_fonts: dict = {}   # 任意字型快取（key: 描述字串 → pygame.font.Font）

# ── 剩餘時間點震動特效 ──────────────────────────────────────────
_time_shake_t0 = [0]      # 震動觸發時間戳（ms，0 = 未啟用）

# ── 突發事件全螢幕震動 ──────────────────────────────────────────
_evt_shake_t0  = [0]      # 震動觸發時間戳（ms，0 = 未啟用）

# ── 點名警示便利貼 ──────────────────────────────────────────────
_roll_call_course    = [""]     # 當週點名科目（空字串 = 未啟用）

_roll_call_attended  = [False]  # 本週點名週次是否已執行「正常上課」

_roll_call_xed       = [False]  # 點名課被翹掉（顯示紅色大叉）

# ── 翹課選課彈出視窗 ──────────────────────────────────────────
_skip_popup_active   = [False]

_skip_popup_courses: list = []   # 全部課名清單

_skip_popup_skipped: set  = set()  # 本週已翹的課

_skip_popup_attended: set = set()  # 本週已上的課（正常上課選的科目）

_skip_popup_rects:   list = []

_skip_popup_event         = threading.Event()

_skip_popup_result        = [None]   # str (選定課名) 或 None (取消)

# ── 特殊行動停用狀態 ──────────────────────────────────────────
_special_disabled: dict = {}   # {行動名: 倒數格數} 停用中的特殊行動

# ── 行動成功白光閃爍 ────────────────────────────────────────────
_action_flash_t0 = [0]    # 閃爍觸發時間戳（ms，0 = 未啟用）

# ── 音效 ────────────────────────────────────────────────────
_sfx: dict = {}   # name -> pygame.mixer.Sound（run_ui 啟動後載入）

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

# ── 角色創建紫色螢光粒子 ─────────────────────────────────────────
_cc_ptcl:       list = []     # 粒子池（紫色光球 / 光絮）

_cc_ptcl_ready       = [False] # 是否已初始化

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

_shop_scroll_y   = [0]    # 商品格列表的垂直捲動偏移（px）

_shop_exit_event = threading.Event()

_shop_icon_cache: dict = {}   # (item_id, diameter) → SRCALPHA Surface（圓形裁切）

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

# ── 漣漪轉場效果（週次切換時） ───────────────────────────────
_ripple_t0       = [0]       # 觸發時間戳（ms，0 = 未啟用）

_ripple_np_cache : dict = {} # numpy 座標格快取（同解析度只建一次）

# ── 角色創建背景影片（WEBM 循環播放） ────────────────────────
_cc_video_cap    = [None]  # cv2.VideoCapture 物件（None 表示未載入）

_cc_video_fps    = [30.0]  # 影片 FPS

_cc_video_surf   = [None]  # 當前幀的 pygame.Surface

_cc_video_last   = [0]     # 上次更新幀的時間戳（ms）

_cc_overlay_surf = [None]  # 奶茶↔奶白漸層遮罩（75% 透明，懶初始化）

_bgm_dir       = [""]        # BGM 資料夾路徑（run_ui 啟動後設定）

_bgm_current   = [None]      # 目前播放的檔名（None = 靜音）

_bgm_pending   = [None]      # 淡出後待播的檔名（None = 靜音）

_bgm_switch_at = [0]         # 允許載入新曲的最早時間戳（ms）

_bg_surfs   : dict = {}   # filename → pygame.Surface（啟動時載入）

_bg_current = [None]      # 目前全額顯示的遊戲背景 Surface

_bg_target  = [None]      # crossfade 目標 Surface（None = 未在過渡）

_bg_fade_t0 = [0]         # crossfade 開始時間戳（ms）

# ── 道具店滑動轉場 ────────────────────────────────────────────
_shop_slide_dir = ["none"]   # "in" | "out" | "out_done" | "none"

_shop_slide_t0  = [0]        # 動畫開始時間（ms）

# ── 面板滑動轉場（劇情模式收起 / 行動模式展開）──────────────────
_panel_slide_dir = ["none"]   # "out" | "in" | "none"

_panel_slide_t0  = [0]        # 動畫開始時間（ms）

_panel_slide_val = [0.0]      # 0.0=完全展開, 1.0=完全收起

_weather_type  = [None]   # 目前天氣類型字串

_weather_pts   = []       # 粒子池（葉子 / 花瓣 / 雨滴 / 光塵 / 霧團）

_click_effects: list = []    # 進行中的特效清單

# 漸層 Surface 快取（由 run_ui() 初始化後填入）
_grads: dict = {}

# 繪製函式暫存按鈕 Rect，供事件處理使用（僅主執行緒存取）
_cc_btn_cache: dict = {}

_action_icon_srcs: dict = {}   # label -> pygame.Surface（懶載入原始圖）


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
