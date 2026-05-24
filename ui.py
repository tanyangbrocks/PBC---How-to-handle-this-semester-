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

# ─────────────────────────────────────────
#  顏色（奶茶布丁色系）
# ─────────────────────────────────────────
WHITE     = (255, 253, 208)   # 奶油白 #FFFDD0 — 主要文字
BLACK     = ( 80,  45,  30)   # 深咖啡 — 輸入框文字
GRAY      = (180, 148, 110)   # 暖灰棕 — 次要邊框
DARK_GRAY = ( 58,  36,  20)   # 深暖棕 — 次要按鈕
BG        = ( 38,  22,  12)   # 濃縮咖啡底
PANEL     = ( 72,  48,  28)   # 暖棕面板
BTN_N     = (139,  90,  43)   # 焦糖棕按鈕
BTN_H     = (190, 140,  78)   # 淺焦糖 hover
GREEN     = (128, 175,  80)   # 抹茶綠
RED       = (192,  88,  68)   # 磚紅
YELLOW    = (230, 185,  75)   # 蜂蜜黃
CYAN      = (251, 206, 177)   # 杏色 #FBCEB1 — 邊框 / 強調
MILK      = (255, 248, 230)   # 牛奶白 — 文字輸入框背景

# ─────────────────────────────────────────
#  版面尺寸
# ─────────────────────────────────────────
WIN_W    = 960
WIN_H    = 720
STATUS_H = 155
INPUT_H  = 165
LOG_H    = WIN_H - STATUS_H - INPUT_H

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
_mode    = [None]   # "choices" | "yn" | "text" | None
_choices = []       # 選項標籤列表
_prompt  = [""]     # yn / text 提示文字
_tvalue  = [""]     # text 模式的目前輸入內容
_scroll    = [0]      # 訊息區往上捲動的行數
_composing = [""]   # IME 組字預覽（輸入法尚未確認的字）

# 畫面階段：start → 開始畫面，game → 遊戲中，end → 結束畫面
_phase         = ["start"]
_start_event   = threading.Event()   # 玩家點擊「開始遊戲」後被 set
_restart_event = threading.Event()   # 玩家點擊「再來一次」後被 set

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

def ask_yn(prompt: str) -> bool:
    """取代 y/N 型的 input()：顯示「是 / 否」按鈕，回傳 True / False。"""
    _cmd_q.put(("yn", prompt))
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

    surf.blit(fm.render(f"【{player.name}】 {player.department}", True, CYAN), (x, y))
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
    surf.blit(fs.render(f"滿足感 {player.satisfaction}%", True, WHITE),
              (x + bw + 8, y))
    y += bh + gap

    if player.status_effects:
        eff = "  ".join([f"[{k} {v}週]" for k, v in player.status_effects.items()])
        surf.blit(fs.render(eff, True, RED), (x, y))


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
        surf.blit(fs.render(line, True, color),
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

def _draw_start(surf, fm, fl, mpos):
    """開始畫面：遊戲標題 + 開始遊戲按鈕，回傳按鈕 Rect。"""
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)
    # 標題
    title = fl.render("如何渡過這學期？", True, CYAN)
    surf.blit(title, ((WIN_W - title.get_width()) // 2, WIN_H // 3 - 20))
    # 副標
    sub = fm.render("一款大學生存模擬遊戲", True, YELLOW)
    surf.blit(sub, ((WIN_W - sub.get_width()) // 2, WIN_H // 3 + 58))
    # 按鈕
    btn = pygame.Rect((WIN_W - 220) // 2, WIN_H // 2 + 50, 220, 56)
    hover = btn.collidepoint(mpos)
    pygame.draw.rect(surf, BTN_H if hover else BTN_N, btn, border_radius=16)
    pygame.draw.rect(surf, CYAN, btn, 2, border_radius=16)
    t = fm.render("開始遊戲", True, WHITE)
    surf.blit(t, (btn.x + (220 - t.get_width()) // 2,
                  btn.y + (56  - t.get_height()) // 2))
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
    title = fm.render("🎓 學期結束！感謝遊玩《如何渡過這學期？》", True, YELLOW)
    surf.blit(title, ((WIN_W - title.get_width()) // 2, ir.y + 14))
    # 按鈕
    btn = pygame.Rect((WIN_W - 220) // 2, ir.y + 60, 220, 50)
    hover = btn.collidepoint(mpos)
    pygame.draw.rect(surf, BTN_H if hover else BTN_N, btn, border_radius=16)
    pygame.draw.rect(surf, CYAN, btn, 2, border_radius=16)
    t = fm.render("再來一次", True, WHITE)
    surf.blit(t, (btn.x + (220 - t.get_width()) // 2,
                  btn.y + (50  - t.get_height()) // 2))
    return btn


# ─────────────────────────────────────────
#  pygame 主迴圈（在主執行緒中呼叫）
# ─────────────────────────────────────────

def run_ui():
    """啟動 pygame 視窗並進入主迴圈，直到視窗關閉。"""
    pygame.init()
    pygame.key.set_repeat(400, 50)  # 長按重複：400ms 後開始，每 50ms 一次（backspace 連刪）
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("如何渡過這學期？")
    clock  = pygame.time.Clock()

    fl = _get_font(40)   # 開始 / 結束畫面標題大字
    fm = _get_font(22)
    fs = _get_font(17)

    sr = pygame.Rect(0, 0, WIN_W, STATUS_H)
    lr = pygame.Rect(0, STATUS_H, WIN_W, LOG_H)
    ir = pygame.Rect(0, STATUS_H + LOG_H, WIN_W, INPUT_H)

    # 道具店快捷按鈕固定在狀態欄右下角
    shop_btn_rect = pygame.Rect(WIN_W - 120, STATUS_H - 46, 110, 36)

    # ── 預先計算漸層 Surface（只算一次，之後每幀 blit）────────
    _grads["bg"]     = _gradient_surf(WIN_W, WIN_H,    ( 48,  28,  14), ( 20,  10,   4))
    _grads["status"] = _gradient_surf(WIN_W, STATUS_H, ( 90,  60,  34), ( 62,  40,  22))
    _grads["input"]  = _gradient_surf(WIN_W, INPUT_H,  ( 62,  40,  22), ( 90,  60,  34))
    _grads["start"]  = _gradient_surf(WIN_W, WIN_H,    ( 62,  38,  18), ( 28,  14,   6))

    running = True
    while running:
        mpos = pygame.mouse.get_pos()
        # 道具店按鈕是否可點擊：只有在行動選單中且選項包含道具店時才亮起
        shop_active = (_mode[0] == "choices" and "🏪 前往道具店" in _choices)

        # ── 消化遊戲執行緒的命令 ─────────────────────────────
        while not _cmd_q.empty():
            cmd = _cmd_q.get_nowait()
            tag = cmd[0]
            if tag == "msg":
                _log.extend(_wrap(cmd[1], fs, lr.width - 12))
                _scroll[0] = 0          # 新訊息 → 自動滾到底
            elif tag == "player":
                _player[0] = cmd[1]
            elif tag == "choices":
                _choices.clear()
                _choices.extend(cmd[1])
                _mode[0] = "choices"
            elif tag == "yn":
                _prompt[0] = cmd[1]
                _mode[0] = "yn"
            elif tag == "text":
                _prompt[0] = cmd[1]
                _tvalue[0] = cmd[2] if len(cmd) > 2 else ""
                _mode[0] = "text"
                pygame.key.start_text_input()  # Windows IME 必須主動開啟
            elif tag == "phase":
                _phase[0] = cmd[1]
            elif tag == "reset":
                _log.clear()
                _player[0] = None
                _mode[0] = None
                _choices.clear()
                _prompt[0] = ""
                _tvalue[0] = ""
                _scroll[0] = 0
                _composing[0] = ""

        # ── 繪製（依畫面階段切換內容）────────────────────────
        btn_rects = []
        start_btn = None
        end_btn   = None

        if _phase[0] == "start":
            start_btn = _draw_start(screen, fm, fl, mpos)
        elif _phase[0] == "end":
            end_btn = _draw_end(screen, fm, fs, lr, mpos)
        else:   # "game"
            screen.blit(_grads["bg"], (0, 0))
            _draw_status(screen, fs, fm, _player[0], sr)
            _draw_log(screen, fs, _log, _scroll[0], lr)
            btn_rects = _draw_input(screen, fm, fs, _mode[0], _choices,
                                    _prompt, _tvalue, ir, mpos)

            # 道具店快捷按鈕（亮色 = 可點，暗色 = 目前不在行動選單）
            _shop_col = BTN_N if shop_active else DARK_GRAY
            pygame.draw.rect(screen, _shop_col, shop_btn_rect, border_radius=12)
            pygame.draw.rect(screen, CYAN, shop_btn_rect, 1, border_radius=12)
            _shop_txt = fs.render("🏪 道具店", True, WHITE if shop_active else GRAY)
            screen.blit(_shop_txt, (
                shop_btn_rect.x + (shop_btn_rect.width  - _shop_txt.get_width())  // 2,
                shop_btn_rect.y + (shop_btn_rect.height - _shop_txt.get_height()) // 2,
            ))

        pygame.display.flip()

        # ── pygame 事件 ───────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEWHEEL:
                lh     = fs.get_height() + 3
                vis    = lr.height // lh
                max_sc = max(0, len(_log) - vis)
                _scroll[0] = max(0, min(max_sc, _scroll[0] - ev.y))

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if _phase[0] == "start":
                    # ── 開始畫面 ──────────────────────────────
                    if start_btn and start_btn.collidepoint(ev.pos):
                        _phase[0] = "game"
                        _start_event.set()
                elif _phase[0] == "end":
                    # ── 結束畫面 ──────────────────────────────
                    if end_btn and end_btn.collidepoint(ev.pos):
                        _phase[0] = "start"
                        _restart_event.set()
                else:
                    # ── 遊戲中 ────────────────────────────────
                    # 道具店快捷按鈕
                    if shop_active and shop_btn_rect.collidepoint(ev.pos):
                        shop_idx = next(
                            (i + 1 for i, c in enumerate(_choices) if c == "🏪 前往道具店"),
                            None,
                        )
                        if shop_idx is not None:
                            _reply_val[0] = shop_idx
                            _mode[0] = None
                            _choices.clear()
                            _reply_event.set()
                    for (br, val) in btn_rects:
                        if br.collidepoint(ev.pos):
                            if _mode[0] == "text" and val == "__ok__":
                                _reply_val[0] = _tvalue[0]
                                _mode[0] = None
                                _composing[0] = ""
                                pygame.key.stop_text_input()
                                _reply_event.set()
                            elif _mode[0] in ("choices", "yn"):
                                _reply_val[0] = val
                                _mode[0] = None
                                _choices.clear()
                                _reply_event.set()

            elif ev.type == pygame.TEXTEDITING:
                # 輸入法組字中（例如注音還沒按確認）：只更新預覽，不寫入正文
                if _mode[0] == "text":
                    _composing[0] = ev.text

            elif ev.type == pygame.TEXTINPUT:
                # 輸入法確認（或直接打英數）：寫入正文，清除組字預覽
                if _mode[0] == "text":
                    _tvalue[0] += ev.text
                    _composing[0] = ""

            elif ev.type == pygame.KEYDOWN:
                if _mode[0] == "text":
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
