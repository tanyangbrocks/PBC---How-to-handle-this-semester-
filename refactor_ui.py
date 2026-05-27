#!/usr/bin/env python3
# coding: utf-8
"""
refactor_ui.py — ui.py 模組拆分工具
====================================
用法：
  python refactor_ui.py --analyze      # 乾跑：列印分類計畫，不寫入任何檔案
  python refactor_ui.py                # 執行拆分，輸出九個新檔案（不覆蓋 ui.py）

輸出檔案：
  ui_const.py       — 純常數（顏色 / 尺寸 / 設定值）
  ui_state.py       — 執行期可變狀態（Queue / Event / list / dict 等）
  ui_draw_base.py   — 穩定的低階繪圖輔助（字型、陰影、按鈕、緩動等）
  ui_draw_fx.py     — 天氣特效、點擊特效、Ripple、背景、立繪
  ui_draw_hud.py    — HUD 元素（status bar、圖示、log 區、週曆）
  ui_draw_cc.py     — 角色創建畫面（CC 全部 draw 函式）
  ui_draw_pop.py    — 彈出視窗、Modal、道具店
  ui_draw_ap.py     — 行動面板、成績面板、側邊面板（最常被修改）
  ui_new.py         — 公開 API + run_ui 主迴圈（確認無誤後更名為 ui.py）
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).with_name("ui.py")

# ──────────────────────────────────────────────────────────────────────────────
#  常數分類規則（不變）
# ──────────────────────────────────────────────────────────────────────────────

_CONST_EXACT = frozenset({
    "WHITE", "BLACK", "GRAY", "DARK_GRAY", "BG", "PANEL",
    "BTN_N", "BTN_H", "GREEN", "RED", "YELLOW", "CYAN", "MILK", "TITLE",
    "WIN_W", "WIN_H", "STATUS_H", "ACTION_H", "TAB_H", "CHAR_H",
})

_CONST_STARTS = (
    "_SHOP_ITEM_ICON",
    "_WEEK_BGM",
    "_INTEL_",
    "_WEEK_BG",
    "_WX_LEAF_COLS",
    "_WX_FOG_PALETTE",
    "_WEATHER_TYPES",
    "_STANDARD_ACTIONS",
    "_ACTION_INFO",
    "_ACTION_ICON_FILES",
    "_GRADE_ROWS",
    "_SPECIAL_ACTION",
    "_SPECIAL_ICONS",
    "_SLOT_SPIN_MS",
    "_SLOT_DELAY_MS",
    "_SLOT_SPIN_NAMES",
    "_CONFETTI_COLORS",
    "_CC_PTCL_COLORS",
    "_CHAR_ART_DIR",
    "_SHOP_ICON_DIR",
    "_SIDE_PANEL_W",
    "_SUBJ_SHORT_NAMES",
    "_PORTRAIT_FADE_MS",
    "_TIME_SHAKE_MS",
    "_EVT_SHAKE_MS",
    "_EVT_SHAKE_AMP",
    "_ACTION_FLASH_MS",
    "_CLICK_MS",
    "_CLICK_MAX",
    "_CLICK_SPARK_COLS",
    "_EXP_LVL_",
    "_BUMP_",
    "_SP_AREA",
    "POPUP_",
    "RIPPLE_",
    "SHOP_SLIDE",
    "PANEL_SLIDE",
    "BGM_FADE",
    "BG_FADE_MS",
)

# ──────────────────────────────────────────────────────────────────────────────
#  繪圖函式 → 子模組對照表
#  每個函式都明確指定目標；若未列出的 _draw_* 函式，預設歸 ui_draw_ap
# ──────────────────────────────────────────────────────────────────────────────

_DRAW_DEST: dict[str, str] = {}

def _reg(dest: str, *names: str) -> None:
    for n in names:
        _DRAW_DEST[n] = dest

# ── ui_draw_base：穩定低階輔助（極少修改）─────────────────────────────────
_reg("ui_draw_base",
    # 音效 / BGM
    "_play_sfx", "_request_bgm",
    # 字型 / 文字
    "_get_font", "_get_font_bold", "_clean", "_wrap",
    # 緩動
    "_ease_in_cubic", "_ease_out_quart", "_ease_out_back",
    # 紋理 / 圖片載入
    "_gradient_surf", "_load_cover",
    # 陰影 / 光澤
    "_soft_shadow", "_soft_shadow_circle",
    "_gloss_rect", "_gloss_circle", "_panel_top_shadow",
    # Hover / 幾何
    "_advance_hover", "_scaled_rect", "_float_offset",
    # 進階按鈕
    "_draw_float_label_card", "_premium_btn", "_premium_circle",
    # 震動偏移
    "_get_evt_shake_offset",
    # 道具店輔助（穩定）
    "_item_icon_color", "_get_shop_icon", "_apply_shop_purchase",
    # 立繪管理
    "_portrait_orig_load", "_portrait_scaled_load",
    "_portrait_head_load", "_get_portrait_key", "_portrait_switch",
)

# ── ui_draw_fx：天氣、特效、動畫、開始/結束畫面 ───────────────────────────
_reg("ui_draw_fx",
    # 天氣粒子工廠
    "_wx_leaf_new", "_wx_dust_new", "_wx_rain_new", "_wx_fog_new",
    "_wx_rotate", "_weather_reset",
    # 天氣繪製
    "_draw_weather", "_wx_draw_sun", "_wx_draw_leaves",
    "_wx_draw_fog", "_wx_draw_rain",
    # 點擊特效
    "_click_spawn", "_draw_click_effects",
    # Ripple 轉場
    "_draw_ripple_overlay", "_ripple_warp", "_ripple_rings",
    # 遊戲背景
    "_draw_game_bg", "_request_week_bg",
    # 行動閃爍
    "_draw_action_flash",
    # 立繪繪製
    "_draw_character_art",
    # 開始 / 結束畫面
    "_draw_start", "_draw_end",
)

# ── ui_draw_hud：狀態列、圖示、log、週曆 ──────────────────────────────────
_reg("ui_draw_hud",
    # 狀態列
    "_draw_status", "_draw_status_v2",
    # 圖示
    "_draw_icon_cart", "_draw_icon_coin", "_draw_icon_clock",
    "_draw_icon_brain", "_draw_icon_clover",
    # 週曆
    "_draw_week_calendar",
    # 智力等級
    "_get_intel_level_ui",
    # Log / 輸入框 / 基礎面板
    "_draw_log", "_draw_input", "_draw_panel",
)

# ── ui_draw_cc：角色創建畫面（CC）─────────────────────────────────────────
_reg("ui_draw_cc",
    "_cc_ptcl_new",
    "_draw_cc_particles", "_draw_cc_bg",
    "_draw_cc_name", "_draw_cc_portrait", "_draw_cc_dept",
    "_draw_cc_drawbacks", "_draw_cc_stats", "_draw_cc_talent",
    "_draw_cc_de_level", "_draw_cc_extra_events", "_draw_cc_summary",
    "_spawn_confetti", "_update_confetti", "_update_slot_state",
    "_draw_cc_slot_machine",
)

# ── ui_draw_pop：彈出視窗、Modal、道具店 ──────────────────────────────────
_reg("ui_draw_pop",
    "_draw_choice_popup", "_draw_event_ok_popup",
    "_draw_subj_popup", "_draw_skip_class_popup", "_draw_action_popup",
    "_draw_modal_overlay", "_draw_modal_timetable", "_draw_modal_grade",
    "_draw_shop",
)

# ── ui_draw_ap：行動面板、成績面板、側邊面板（最常被修改）──────────────────
_reg("ui_draw_ap",
    "_draw_action_panel", "_draw_bump_bg", "_draw_action_icon", "_draw_panel_log",
    "_draw_exam_stress_fx", "_side_panel_bg",
    "_draw_exp_panel", "_draw_grade_panel", "_draw_roll_call_note",
)


def classify(name: str, node: ast.AST) -> str:
    is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))

    # ── 函式 ──────────────────────────────────────────────────
    if is_func:
        # 1. 明確對照表
        if name in _DRAW_DEST:
            return _DRAW_DEST[name]
        # 2. _draw_ / _wx_draw_ 前綴但未列出 → 歸 ui_draw_ap（catch-all）
        if name.startswith("_draw_") or name.startswith("_wx_draw_"):
            return "ui_draw_ap"
        return "ui"

    # ── 變數 ──────────────────────────────────────────────────
    if name in _CONST_EXACT:
        return "ui_const"

    bare = name.lstrip("_")
    if bare and bare.replace("_", "").isalpha() and bare.replace("_", "").isupper():
        return "ui_const"

    for prefix in _CONST_STARTS:
        if name.startswith(prefix):
            return "ui_const"

    if name.startswith("_"):
        return "ui_state"

    return "ui"


# ──────────────────────────────────────────────────────────────────────────────
#  解析 ui.py（不變）
# ──────────────────────────────────────────────────────────────────────────────

def get_entries(src: str):
    lines = src.splitlines(keepends=True)
    tree  = ast.parse(src)
    raw   = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign):
            tgts = [t for t in node.targets if isinstance(t, ast.Name)]
            if not tgts:
                continue
            name = tgts[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        else:
            continue

        dest = classify(name, node)

        cs = node.lineno - 1
        i  = node.lineno - 2
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("#"):
                cs = i
                i -= 1
            else:
                break

        ce = node.end_lineno - 1
        raw.append((name, dest, cs, ce))

    raw.sort(key=lambda e: e[2])

    entries: list[tuple] = []
    prev_end = -1
    for name, dest, cs, ce in raw:
        cs = max(cs, prev_end + 1)
        if cs > ce:
            cs = ce
        entries.append((name, dest, cs, ce))
        prev_end = ce

    return entries, lines


# ──────────────────────────────────────────────────────────────────────────────
#  新檔案 Header
# ──────────────────────────────────────────────────────────────────────────────

_B = "from ui_const import *\nfrom ui_state  import *\n"   # 通用底層

_HEADER: dict[str, str] = {

    "ui_const": (
        "# ============================================================\n"
        "#  ui_const.py -- jPure constants\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import os\n\n"
    ),

    "ui_state": (
        "# ============================================================\n"
        "#  ui_state.py -- Runtime mutable state\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import threading\nimport queue\nimport os\nimport pygame\n\n"
        "from ui_const import *\n\n"   # ui_state 自身不可 import ui_state（避免自循環）
    ),

    "ui_draw_base": (
        "# ============================================================\n"
        "#  ui_draw_base.py -- Low-level drawing primitives (rarely changed)\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B + "\n"
    ),

    "ui_draw_fx": (
        "# ============================================================\n"
        "#  ui_draw_fx.py -- Weather FX, click effects, ripple, BG, screens\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B
        + "from ui_draw_base import *\n\n"
    ),

    "ui_draw_hud": (
        "# ============================================================\n"
        "#  ui_draw_hud.py -- Status bar, icons, log area, week calendar\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B
        + "from ui_draw_base import *\n\n"
    ),

    "ui_draw_cc": (
        "# ============================================================\n"
        "#  ui_draw_cc.py -- Character creation UI\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B
        + "from ui_draw_base import *\n\n"
    ),

    "ui_draw_pop": (
        "# ============================================================\n"
        "#  ui_draw_pop.py -- Popups, modals, shop\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B
        + "from ui_draw_base import *\n\n"
    ),

    "ui_draw_ap": (
        "# ============================================================\n"
        "#  ui_draw_ap.py -- Action panel, grade/exp panels  [most edited]\n"
        "#  by refactor_ui.py\n"
        "# ============================================================\n"
        "import pygame\nimport math\nimport random\nimport os\n\n"
        + _B
        + "from ui_draw_base import *\n"
        + "from ui_draw_hud  import *\n\n"
    ),

    "ui": (
        "# ============================================================\n"
        "#  ui_new.py -- Public API + run_ui main loop\n"
        "#  by refactor_ui.py  --  rename to ui.py when verified\n"
        "# ============================================================\n"
        "import pygame\nimport threading\nimport queue\n"
        "import sys\nimport os\nimport math\nimport random\n\n"
        + _B
        + "from ui_draw_base import *\n"
        + "from ui_draw_fx   import *\n"
        + "from ui_draw_hud  import *\n"
        + "from ui_draw_cc   import *\n"
        + "from ui_draw_pop  import *\n"
        + "from ui_draw_ap   import *\n\n"
    ),
}

DEST_ORDER = [
    "ui_const", "ui_state",
    "ui_draw_base", "ui_draw_fx", "ui_draw_hud",
    "ui_draw_cc", "ui_draw_pop", "ui_draw_ap",
    "ui",
]

_DEST_FILE: dict[str, str] = {
    "ui_const":    "ui_const.py",
    "ui_state":    "ui_state.py",
    "ui_draw_base":"ui_draw_base.py",
    "ui_draw_fx":  "ui_draw_fx.py",
    "ui_draw_hud": "ui_draw_hud.py",
    "ui_draw_cc":  "ui_draw_cc.py",
    "ui_draw_pop": "ui_draw_pop.py",
    "ui_draw_ap":  "ui_draw_ap.py",
    "ui":          "ui_new.py",
}

# ANSI color per destination (terminal display only)
_COL = {
    "ui_const":    "33",
    "ui_state":    "34",
    "ui_draw_base":"90",
    "ui_draw_fx":  "36",
    "ui_draw_hud": "32",
    "ui_draw_cc":  "35",
    "ui_draw_pop": "33",
    "ui_draw_ap":  "31",
    "ui":          "37",
}


# ──────────────────────────────────────────────────────────────────────────────
#  --analyze 模式
# ──────────────────────────────────────────────────────────────────────────────

def cmd_analyze() -> None:
    src = SRC.read_text(encoding="utf-8")
    entries, lines = get_entries(src)

    totals: dict[str, int] = {d: 0 for d in DEST_ORDER}
    counts: dict[str, int] = {d: 0 for d in DEST_ORDER}
    RESET = "\033[0m"

    print(f"\n{'name':<42} {'dest':<16} {'lines':>5}  source-range")
    print("-" * 74)

    for name, dest, cs, ce in entries:
        lc = ce - cs + 1
        totals[dest] += lc
        counts[dest] += 1
        color  = f"\033[{_COL[dest]}m"
        fname  = _DEST_FILE[dest]
        print(f"  {color}{name:<40}{RESET}  {fname:<18} {lc:>4}  "
              f"L{cs+1}-{ce+1}")

    uncaptured = len(lines) - sum(ce - cs + 1 for _, _, cs, ce in entries)

    print()
    print("-- module summary (incl. header) " + "-" * 40)
    for dest in DEST_ORDER:
        hdr_lines = len(_HEADER[dest].splitlines())
        color = f"\033[{_COL[dest]}m"
        RESET = "\033[0m"
        print(f"  {color}{_DEST_FILE[dest]:<22}{RESET}  "
              f"{counts[dest]:>3} defs   ~{totals[dest] + hdr_lines:>5} lines")
    print()
    print(f"  original ui.py          {len(lines):>5} lines")
    print(f"  classified              {sum(totals.values()):>5} lines"
          f"  (unassigned: {uncaptured} — imports/file header)")
    print()


# ──────────────────────────────────────────────────────────────────────────────
#  split 模式（預設）
# ──────────────────────────────────────────────────────────────────────────────

def cmd_split() -> None:
    src = SRC.read_text(encoding="utf-8")
    entries, lines = get_entries(src)

    buckets: dict[str, list[str]] = {d: [] for d in DEST_ORDER}

    for name, dest, cs, ce in entries:
        chunk = "".join(lines[cs: ce + 1])
        chunk = chunk.rstrip("\n") + "\n\n"
        buckets[dest].append(chunk)

    base    = SRC.parent
    written: list[Path] = []

    for dest in DEST_ORDER:
        fname    = _DEST_FILE[dest]
        out_path = base / fname
        # __all__ 宣告：讓 import * 也能匯出 _ 前綴的私有名稱
        _ALL_FOOTER = (
            "\n# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）\n"
            "__all__ = [_n for _n in vars() if not _n.startswith('__')]\n"
        )
        content  = _HEADER[dest] + "".join(buckets[dest]) + _ALL_FOOTER
        out_path.write_text(content, encoding="utf-8")
        kb = out_path.stat().st_size // 1024
        written.append(out_path)
        print(f"  [OK]  {fname:<24}  {kb:>4} KB  "
              f"({len(buckets[dest])} defs)")

    print()
    print("-- next steps " + "-" * 60)
    print("  1. syntax check:")
    for p in written:
        print(f"       python -m py_compile {p.name}")
    print()
    print("  2. rename main module (Windows):")
    print("       rename ui_new.py ui.py")
    print()
    print("  3. turn_engine.py: no import changes needed")
    print("     (ui_new.py re-exports everything via from ... import *)")
    print()


# ──────────────────────────────────────────────────────────────────────────────
#  entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--analyze" in sys.argv:
        cmd_analyze()
    else:
        print("\n[ split ]  splitting ui.py ...\n")
        cmd_split()
        print("[ done ]")
