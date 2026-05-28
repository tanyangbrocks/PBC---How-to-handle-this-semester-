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
#    在測試中全部變成 no-op MagicMock 即可。
_ui_mock = MagicMock()
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
