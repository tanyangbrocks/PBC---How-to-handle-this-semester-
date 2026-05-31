# ============================================================
#  tests/conftest.py — pytest 前置設定
#  在所有 test 模組 import 之前，把 ui / pygame 換成 stub，
#  讓 character.py / turn_engine.py 等邏輯模組能在沒有視窗的環境下被 import。
# ============================================================
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# ── 把專案根目錄加入 Python path ──────────────────────────────
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── 在 character / turn_engine 被 import 之前先佔位 ──────────
# pygame：部分模組在 import 時不用它，但防止意外報錯
_pygame_mock = MagicMock()
_pygame_mock.font.Font.return_value = MagicMock()
sys.modules.setdefault("pygame",             _pygame_mock)
sys.modules.setdefault("pygame.mixer",       _pygame_mock.mixer)
sys.modules.setdefault("pygame.font",        _pygame_mock.font)
sys.modules.setdefault("pygame.display",     _pygame_mock.display)
sys.modules.setdefault("pygame.draw",        _pygame_mock.draw)
sys.modules.setdefault("pygame.transform",   _pygame_mock.transform)

# ui：遊戲邏輯呼叫 notify / tell_story / show_action_result 等，
#    同步呼叫用 MagicMock，async def 用 AsyncMock（否則 asyncio.run 會炸）。
from unittest.mock import AsyncMock
_ui_mock = MagicMock()

_ASYNC_UI_FNS = [
    "ask_choice", "ask_subject_popup", "ask_withdrawal_popup", "ask_text",
    "ask_yn", "ask_ok", "ask_exam_start", "ask_exam_question",
    "run_shape_minigame", "tell_story", "wait_start", "wait_restart",
    "ask_skip_class_popup", "ask_cc_name", "ask_cc_portrait", "ask_cc_dept",
    "ask_cc_drawbacks", "ask_cc_stats", "ask_cc_de_level", "ask_cc_talent",
    "ask_cc_extra_events", "ask_cc_summary", "show_guide_modal",
    "show_extra_event_popup", "notify_timetable", "notify_grade_report",
    "open_shop_ui", "run_pregame_countdown",
]
for _fn in _ASYNC_UI_FNS:
    setattr(_ui_mock, _fn, AsyncMock())

sys.modules["ui"] = _ui_mock

# ui_const：character.py 不直接依賴它，但 turn_engine 間接會用到；
#           mock 掉以避免 pygame.init() 被觸發。
_ui_const_mock = MagicMock()
_ui_const_mock.WIN_W      = 1280
_ui_const_mock.WIN_H      = 720
_ui_const_mock.STATUS_H   = 175
sys.modules.setdefault("ui_const",  _ui_const_mock)
sys.modules.setdefault("ui_state",  MagicMock())
sys.modules.setdefault("ui_draw",   MagicMock())
