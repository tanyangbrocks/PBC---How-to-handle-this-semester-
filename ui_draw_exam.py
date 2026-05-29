# ============================================================
#  ui_draw_exam.py -- 考試形狀小遊戲繪製
# ============================================================
import os
import pygame
import random

from ui_state import *
from ui_const import *
from ui_draw_base import _play_sfx

# ── 常數 ──────────────────────────────────────────────────

SHAPE_COLORS = {
    "circle":   (100, 160, 255),
    "cross":    (255, 100, 100),
    "triangle": (255, 215, 60),
    "diamond":  (190, 100, 255),
}

# 第一回合：各形狀對應的字母標籤
_SHAPE_LABELS = {
    "circle":   "Ａ",
    "cross":    "Ｂ",
    "diamond":  "Ｃ",
    "triangle": "Ｄ",
}

def _get_shape_label_font() -> pygame.font.Font:
    """取得（並快取）第一回合字母標籤用字型（48px 粗體）。"""
    ck = "smg_label_48b"
    if ck not in _extra_fonts:
        try:
            _extra_fonts[ck] = pygame.font.SysFont(
                "microsoftyahei,notosanscjktc,meiryobold", 48, bold=True
            )
        except Exception:
            _extra_fonts[ck] = pygame.font.SysFont(None, 48, bold=True)
    return _extra_fonts[ck]

ROUND_MS = 30_000   # 每回合 30 秒

# 第二回合可用背景清單
_SMG_BG_FILES = [
    "1234_background.webp",
    "34_background.webp",
    "56_background.webp",
    "910_background.webp",
    "1112_background.webp",
    "1314_background.webp",
]

# 第二回合形狀 → icon 檔名對應
_SMG_ICON_FILES = {
    "circle":   "class_icon.webp",
    "cross":    "club_icon.webp",
    "triangle": "work_icon.webp",
    "diamond":  "rest_icon.webp",
}

_BG_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "asset", "picture", "background")
_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "asset", "picture", "icon")

# ── 小遊戲共用色票（淺背景 × 深色文字）────────────────────
_SMG_BG      = (248, 243, 230)   # 奶油米色背景
_SMG_PRI     = ( 45,  30,  15)   # 深棕 — 主要文字
_SMG_SEC     = ( 75,  58,  38)   # 中棕 — 次要 / 說明文字
_SMG_ACC     = (130,  85,   5)   # 深琥珀 — 強調 / 分數
_SMG_FLS     = (155,  90,  10)   # 深橙棕 — phase 閃字
_SMG_BAR_TRK = (195, 180, 160)   # 淺棕灰 — 計時條軌道
_SMG_BTN_N   = ( 70,  55,  38)   # 深棕 — 按鈕常態
_SMG_BTN_H   = (105,  85,  58)   # 中棕 — 按鈕 hover
_SMG_BTN_BDR = ( 50,  38,  20)   # 極深棕 — 按鈕邊框
_SMG_BTN_TXT = (255, 248, 230)   # 奶白 — 按鈕文字（深底配淺字）

# ── 背景 / 圖示工具 ──────────────────────────────────────

def _load_smg_bg(filename: str) -> "pygame.Surface | None":
    try:
        surf = pygame.image.load(os.path.join(_BG_DIR, filename)).convert()
        return pygame.transform.scale(surf, (WIN_W, WIN_H))
    except Exception:
        return None

def _switch_smg_bg() -> None:
    """切換到與當前不同的第二回合背景。"""
    candidates = [f for f in _SMG_BG_FILES if f != _smg_bg_key[0]]
    if not candidates:
        candidates = _SMG_BG_FILES
    chosen = random.choice(candidates)
    _smg_bg_key[0]  = chosen
    _smg_bg_surf[0] = _load_smg_bg(chosen)

def _get_icon(shape_type: str, size: int) -> "pygame.Surface | None":
    """取得（並快取）指定形狀的 icon Surface。"""
    key = (shape_type, size)
    if key not in _smg_icon_cache:
        fn = _SMG_ICON_FILES.get(shape_type)
        if fn:
            try:
                raw = pygame.image.load(os.path.join(_ICON_DIR, fn)).convert_alpha()
                _smg_icon_cache[key] = pygame.transform.smoothscale(raw, (size, size))
            except Exception:
                _smg_icon_cache[key] = None
        else:
            _smg_icon_cache[key] = None
    return _smg_icon_cache.get(key)

def _make_text_icon_surf(
    font: pygame.font.Font,
    before: str,
    shape_type: str,
    after: str,
    text_color: tuple,
    icon_size: int = 0,
) -> pygame.Surface:
    """把「文字 + icon圖示 + 文字」橫向組合成一個 SRCALPHA Surface 並回傳。"""
    gap = 6
    fh  = font.get_height()
    sz  = icon_size if icon_size > 0 else fh

    t_b  = font.render(before, True, text_color) if before else None
    t_a  = font.render(after,  True, text_color) if after  else None
    icon = _get_icon(shape_type, sz) if _smg_round[0] == 2 else None

    parts: list[tuple] = []   # (surf, x)
    cursor = 0
    if t_b:
        parts.append((t_b, cursor))
        cursor += t_b.get_width() + gap
    if icon:
        parts.append((icon, cursor))
        cursor += sz + gap
    if t_a:
        parts.append((t_a, cursor))
        cursor += t_a.get_width()

    h   = max(fh, sz)
    out = pygame.Surface((max(cursor, 1), h), pygame.SRCALPHA)
    for part_surf, px in parts:
        py = (h - part_surf.get_height()) // 2
        out.blit(part_surf, (px, py))
    return out

# ── 形狀生成 ──────────────────────────────────────────────

def _spawn_shape(shape_type: str) -> dict:
    ms = pygame.time.get_ticks()
    elapsed_ratio = min((ms - _smg_t0[0]) / ROUND_MS, 1.0)
    speed     = (2.5 + elapsed_ratio * 3.0) / 6.0
    direction = _smg_direction[0]
    x         = float(WIN_W + 60) if direction == -1 else float(-60)

    # 期末：垂直漂移 + 一次性速度突變
    if _smg_exam_type[0] == "期末":
        vy             = random.uniform(-0.06, 0.06)   # px/ms 初始垂直速度
        ay             = random.uniform(-0.00015, 0.00015)  # px/ms² 垂直加速度
        speed_change_t = ms + random.randint(1000, 4000)    # 觸發時間戳
        speed_mult     = random.uniform(0.8, 1.2)           # 速度倍率
    else:
        vy             = 0.0
        ay             = 0.0
        speed_change_t = 0
        speed_mult     = 1.0

    return {
        "type":           shape_type,
        "x":              x,
        "y":              float(random.randint(110, WIN_H - 120)),
        "speed":          speed,
        "direction":      direction,
        "alive":          True,
        "vy":             vy,
        "ay":             ay,
        "speed_change_t": speed_change_t,
        "speed_mult":     speed_mult,
    }

def _try_spawn(ms: int) -> None:
    if _smg_phase_clearing[0]:
        return

    # 若畫面上當前 phase 形狀為 0，強制補一個（無視計時器，無 budget 限制）
    phase_on_screen = sum(
        1 for s in _smg_shapes if s["alive"] and s["type"] == _smg_phase[0]
    )
    if phase_on_screen == 0:
        _smg_shapes.append(_spawn_shape(_smg_phase[0]))
        _smg_last_spawn_t[0]  = ms
        _smg_next_spawn_dt[0] = random.randint(500, 800)
        return

    if ms - _smg_last_spawn_t[0] < _smg_next_spawn_dt[0]:
        return

    # 目標形狀（圓/叉）不設上限，三角/菱形維持 budget 限制
    choices = ["target"]
    if _smg_tri_budget[0] > 0:
        choices.append("triangle")
    if _smg_dia_budget[0] > 0:
        choices.append("diamond")

    kind = random.choice(choices)
    if kind == "target":
        other      = "cross" if _smg_phase[0] == "circle" else "circle"
        shape_type = _smg_phase[0] if random.random() < 0.5 else other
    elif kind == "triangle":
        shape_type = "triangle"
        _smg_tri_count[0]  += 1
        _smg_tri_budget[0] -= 1
    else:
        shape_type = "diamond"
        _smg_dia_count[0]  += 1
        _smg_dia_budget[0] -= 1

    _smg_shapes.append(_spawn_shape(shape_type))
    _smg_last_spawn_t[0]  = ms
    _smg_next_spawn_dt[0] = random.randint(700, 1100)

# ── 形狀繪製 ──────────────────────────────────────────────

def _draw_shape(surf: pygame.Surface, s: dict) -> None:
    x, y = int(s["x"]), int(s["y"])
    # 第二回合：用 icon 取代幾何圖形（90px，原 60px 的 150%）
    if _smg_round[0] == 2:
        icon = _get_icon(s["type"], 90)
        if icon:
            surf.blit(icon, (x - 45, y - 45))
            return
    # 第一回合：以彩色字母取代幾何圖形（顏色保持與原形狀一致）
    col = SHAPE_COLORS[s["type"]]
    lbl = _SHAPE_LABELS[s["type"]]
    fl  = _get_shape_label_font()
    ts  = fl.render(lbl, True, col)
    surf.blit(ts, (x - ts.get_width() // 2, y - ts.get_height() // 2))

def shape_rect(s: dict) -> pygame.Rect:
    # 第二回合 icon 為 90px；第一回合幾何圖形維持 72px 判定框
    if _smg_round[0] == 2:
        return pygame.Rect(int(s["x"]) - 45, int(s["y"]) - 45, 90, 90)
    return pygame.Rect(int(s["x"]) - 36, int(s["y"]) - 36, 72, 72)

# ── 主繪製函式 ────────────────────────────────────────────

def _draw_shape_minigame(
    surf: pygame.Surface,
    fm: pygame.font.Font,
    fs: pygame.font.Font,
    fb: pygame.font.Font,
    mpos: tuple,
    dt_ms: int,
) -> None:
    ms      = pygame.time.get_ticks()
    elapsed = ms - _smg_t0[0]

    # ── 粗體字型（優先使用 ui_state 粗體，保留原字型作 fallback）
    fb_lg = _font_bold_lg[0] or fm   # 粗體 size-22（HUD 主要文字）
    fb_s  = _font_bold[0]   or fs   # 粗體 size-17（HUD 次要文字）

    # ── 第二回合結束：顯示總分 + 確認按鈕 ──────────────────
    if _smg_final_score_t0[0] > 0:
        _draw_final_score(surf, fm, fs, fb, mpos, ms)
        return

    # ── 第一回合成績展示（2.5 秒後自動進入第二回合）──────
    if _smg_r1_score_t0[0] > 0:
        _draw_r1_score(surf, fm, fs)
        if ms - _smg_r1_score_t0[0] >= 2500:
            _start_round_2()
        return

    if _smg_q_active[0]:
        _draw_memory_question(surf, fm, fb, mpos)
        # ── 作答後 1.5 秒展示結果，再進行回合轉換 ────────────
        if _smg_q_answered[0] and ms - _smg_q_ans_t0[0] >= 1500:
            _smg_q_answered[0]  = False
            _smg_q_active[0]    = False
            if _smg_round[0] == 1:
                _smg_r1_score_t0[0] = ms
            else:
                _smg_final_score_t0[0] = ms   # 觸發總分展示，等玩家點確認
        return

    # ── 更新形狀位置 ──────────────────────────────────────
    for s in _smg_shapes:
        s["x"] += s["speed"] * s["direction"] * dt_ms
        # 期末專屬：垂直漂移 + 一次性速度突變
        if _smg_exam_type[0] == "期末":
            s["vy"] = max(-0.15, min(0.15, s["vy"] + s["ay"] * dt_ms))
            new_y   = s["y"] + s["vy"] * dt_ms
            if new_y < 80 or new_y > WIN_H - 100:
                s["vy"] = -s["vy"]
                new_y   = s["y"] + s["vy"] * dt_ms
            s["y"] = new_y
            if s["speed_change_t"] and ms >= s["speed_change_t"]:
                s["speed"]          *= s["speed_mult"]
                s["speed_change_t"]  = 0
    _smg_shapes[:] = [
        s for s in _smg_shapes
        if s["alive"] and -90 < s["x"] < WIN_W + 90
    ]

    # ── 嘗試生成新形狀 ────────────────────────────────────
    _try_spawn(ms)

    # ── phase 切換：先清場，場空後才換 ──────────────────────
    if not _smg_phase_clearing[0] and ms >= _smg_phase_end_t[0]:
        _smg_phase_clearing[0] = True

    if _smg_phase_clearing[0]:
        if not any(s["alive"] for s in _smg_shapes):
            _smg_phase[0]          = "cross" if _smg_phase[0] == "circle" else "circle"
            _smg_phase_end_t[0]    = ms + random.randint(8000, 12000)
            _smg_phase_flash_t[0]  = ms
            _smg_phase_clearing[0] = False
            if _smg_round[0] == 2:
                _switch_smg_bg()   # 第二回合每次 phase 切換同步換背景

    # ── 繪製背景 ─────────────────────────────────────────
    if _smg_round[0] == 2 and _smg_bg_surf[0] is not None:
        surf.blit(_smg_bg_surf[0], (0, 0))
        # 淡奶油遮罩：讓深色文字在任何背景圖上均可讀
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((*_SMG_BG, 160))
        surf.blit(ov, (0, 0))
    else:
        surf.fill(_SMG_BG)

    # ── 繪製所有形狀 ─────────────────────────────────────
    for s in _smg_shapes:
        _draw_shape(surf, s)

    # ── HUD：點擊目標（第一回合文字、第二回合文字＋icon）─
    r2 = (_smg_round[0] == 2)
    if r2:
        inst_surf = _make_text_icon_surf(
            fb_lg, "點擊：", _smg_phase[0], "", _SMG_PRI)
    else:
        target_name = "Ａ" if _smg_phase[0] == "circle" else "Ｂ"
        inst_surf   = fb_lg.render(f"點擊：{target_name}", True, _SMG_PRI)
    surf.blit(inst_surf, (WIN_W // 2 - inst_surf.get_width() // 2, 14))

    # ── HUD：回合標示 ─────────────────────────────────────
    round_surf = fb_s.render(f"回合 {_smg_round[0]} / 2", True, _SMG_SEC)
    surf.blit(round_surf, (WIN_W - round_surf.get_width() - 16, 14))

    # ── HUD：計時條 ──────────────────────────────────────
    ratio         = max(0.0, 1.0 - elapsed / ROUND_MS)
    bar_x, bar_y  = 40, 50
    bar_total_w   = WIN_W - 80
    bar_h         = 10
    pygame.draw.rect(surf, _SMG_BAR_TRK,
                     (bar_x, bar_y, bar_total_w, bar_h), border_radius=5)
    bar_col = (
        (100, 210, 120) if ratio > 0.4 else
        (255, 165, 50)  if ratio > 0.2 else
        (220, 60, 60)
    )
    bar_w = int(bar_total_w * ratio)
    if bar_w > 0:
        pygame.draw.rect(surf, bar_col,
                         (bar_x, bar_y, bar_w, bar_h), border_radius=5)

    # ── HUD：分數預覽 ─────────────────────────────────────
    pv = 80 / 20
    cs = max(0.0, _smg_correct_clicks[0] * pv - _smg_wrong_clicks[0] * pv)
    score_surf = fb_s.render(
        f"點擊 {_smg_correct_clicks[0]}✓  {_smg_wrong_clicks[0]}✗  ({cs:.0f}pt)",
        True, _SMG_SEC,
    )
    surf.blit(score_surf, (16, 14))

    # ── Phase 切換閃字（第二回合有 icon）────────────────────
    if _smg_phase_flash_t[0] and ms - _smg_phase_flash_t[0] < 1500:
        progress = (ms - _smg_phase_flash_t[0]) / 1500
        alpha    = max(0, int(255 * (1.0 - progress)))
        if r2:
            flash_surf = _make_text_icon_surf(
                fb_lg, "改按 ", _smg_phase[0], "！", _SMG_FLS)
        else:
            target_name = "Ａ" if _smg_phase[0] == "circle" else "Ｂ"
            flash_surf  = fb_lg.render(f"改按 {target_name}！", True, _SMG_FLS)
        flash_surf.set_alpha(alpha)
        surf.blit(flash_surf,
                  (WIN_W // 2 - flash_surf.get_width()  // 2,
                   WIN_H // 2 - flash_surf.get_height() // 2))

    # ── 回合結束 → 進入記憶問題 ──────────────────────────
    if elapsed >= ROUND_MS:
        _smg_shapes.clear()
        q_shape         = random.choice(["triangle", "diamond"])
        _smg_q_shape[0] = q_shape
        correct         = _smg_tri_count[0] if q_shape == "triangle" else _smg_dia_count[0]
        _smg_q_correct[0] = correct

        raw_opts = sorted(set(max(0, correct + d) for d in (-3, -1, 0, 1)))
        while len(raw_opts) < 4:
            raw_opts.append(raw_opts[-1] + 1)
        random.shuffle(raw_opts[:4])
        _smg_q_opts[:] = raw_opts[:4]
        _smg_q_rects.clear()
        _smg_q_active[0] = True

# ── 記憶問題畫面 ──────────────────────────────────────────

def _draw_memory_question(
    surf: pygame.Surface,
    fm: pygame.font.Font,
    fb: pygame.font.Font,
    mpos: tuple,
) -> None:
    # 粗體大字型
    fb_lg = _font_bold_lg[0] or fm

    # 背景：奶油色；第二回合延續背景圖 + 奶油遮罩
    if _smg_round[0] == 2 and _smg_bg_surf[0] is not None:
        surf.blit(_smg_bg_surf[0], (0, 0))
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((*_SMG_BG, 200))
        surf.blit(overlay, (0, 0))
    else:
        surf.fill(_SMG_BG)

    r2 = (_smg_round[0] == 2)
    if r2:
        q_surf = _make_text_icon_surf(
            fb_lg, "剛才飛過幾個", _smg_q_shape[0], "？",
            _SMG_PRI, icon_size=36)
    else:
        shape_name = "Ｄ" if _smg_q_shape[0] == "triangle" else "Ｃ"
        q_surf     = fb_lg.render(f"剛才飛過幾個{shape_name}？", True, _SMG_PRI)

    surf.blit(q_surf, (WIN_W // 2 - q_surf.get_width() // 2, WIN_H // 2 - 120))

    _smg_q_rects.clear()
    for i, val in enumerate(_smg_q_opts):
        bx = WIN_W // 2 - 260 + i * 130
        by = WIN_H // 2 - 10
        br = pygame.Rect(bx, by, 110, 52)
        hov = br.collidepoint(mpos)
        pygame.draw.rect(surf,
                         _SMG_BTN_H if hov else _SMG_BTN_N,
                         br, border_radius=12)
        pygame.draw.rect(surf, _SMG_BTN_BDR, br, 2, border_radius=12)
        vt = fb.render(str(val), True, _SMG_BTN_TXT)
        surf.blit(vt, (br.x + (br.width  - vt.get_width())  // 2,
                       br.y + (br.height - vt.get_height()) // 2))
        _smg_q_rects.append((br, val))

    # ── 作答後顯示對錯結果 ────────────────────────────────
    if _smg_q_answered[0]:
        if _smg_q_ans_correct[0]:
            result_text  = "答對了！"
            result_color = (20, 140, 50)    # 深綠
        else:
            result_text  = "答錯了……"
            result_color = (185, 35, 35)    # 深紅
        result_surf = fb_lg.render(result_text, True, result_color)
        rx = WIN_W // 2 - result_surf.get_width()  // 2
        ry = WIN_H // 2 + 60
        # 半透明底板提升可讀性
        pad = 14
        bg_rect = pygame.Rect(rx - pad, ry - pad // 2,
                              result_surf.get_width() + pad * 2,
                              result_surf.get_height() + pad)
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surf.fill((240, 235, 220, 220))
        surf.blit(bg_surf, (bg_rect.x, bg_rect.y))
        surf.blit(result_surf, (rx, ry))

# ── 第二回合結束：總分展示 ────────────────────────────────

def _draw_final_score(
    surf: pygame.Surface,
    fm: pygame.font.Font,
    fs: pygame.font.Font,
    fb: pygame.font.Font,
    mpos: tuple,
    ms: int,
) -> None:
    surf.fill(_SMG_BG)

    # 粗體字型
    fb_lg = _font_bold_lg[0] or fm
    fb_s  = _font_bold[0]   or fs

    r1    = _smg_round_scores[0]
    r2    = _smg_round_scores[1]
    total = r1 + r2

    cy         = WIN_H // 2
    title      = fb_lg.render("小遊戲結束！",          True, _SMG_PRI)
    line1      = fb_s.render( f"第一回合：{r1} / 100", True, _SMG_SEC)
    line2      = fb_s.render( f"第二回合：{r2} / 100", True, _SMG_SEC)
    total_surf = fb_lg.render(f"總分：{total} / 200",  True, _SMG_ACC)

    surf.blit(title,      (WIN_W // 2 - title.get_width()      // 2, cy - 140))
    surf.blit(line1,      (WIN_W // 2 - line1.get_width()      // 2, cy -  70))
    surf.blit(line2,      (WIN_W // 2 - line2.get_width()      // 2, cy -  30))
    surf.blit(total_surf, (WIN_W // 2 - total_surf.get_width() // 2, cy +  30))

    # 1 秒後才顯示確認按鈕
    _smg_final_ok_rect[0] = None
    if ms - _smg_final_score_t0[0] >= 1000:
        bw, bh = 160, 52
        bx = WIN_W // 2 - bw // 2
        by = cy + 110
        br = pygame.Rect(bx, by, bw, bh)
        hov = br.collidepoint(mpos)
        pygame.draw.rect(surf, _SMG_BTN_H if hov else _SMG_BTN_N, br, border_radius=12)
        pygame.draw.rect(surf, _SMG_BTN_BDR, br, 2, border_radius=12)
        bt = fb.render("確認", True, _SMG_BTN_TXT)
        surf.blit(bt, (br.x + (br.width  - bt.get_width())  // 2,
                       br.y + (br.height - bt.get_height()) // 2))
        _smg_final_ok_rect[0] = br

# ── 第一回合成績展示 ──────────────────────────────────────

def _draw_r1_score(
    surf: pygame.Surface,
    fm: pygame.font.Font,
    fs: pygame.font.Font,
) -> None:
    surf.fill(_SMG_BG)

    # 粗體字型
    fb_lg = _font_bold_lg[0] or fm
    fb_s  = _font_bold[0]   or fs

    score = _smg_round_scores[0]
    t1   = fb_lg.render("第一回合結束！",       True, _SMG_PRI)
    t2   = fb_lg.render(f"{score} / 100",       True, _SMG_ACC)
    hint = fb_s.render( "第二回合即將開始……", True, _SMG_SEC)
    surf.blit(t1,   (WIN_W // 2 - t1.get_width()   // 2, WIN_H // 2 - 80))
    surf.blit(t2,   (WIN_W // 2 - t2.get_width()   // 2, WIN_H // 2))
    surf.blit(hint, (WIN_W // 2 - hint.get_width() // 2, WIN_H // 2 + 80))

# ── 第二回合初始化 ────────────────────────────────────────

def _start_round_2() -> None:
    ms = pygame.time.get_ticks()
    _switch_smg_bg()               # 進入第二回合時載入背景
    _smg_round[0]          = 2
    _smg_direction[0]      = 1
    _smg_t0[0]             = ms
    _smg_phase[0]          = random.choice(["circle", "cross"])
    _smg_phase_end_t[0]    = ms + random.randint(8000, 12000)
    _smg_phase_flash_t[0]  = 0
    _smg_phase_clearing[0] = False
    _smg_shapes.clear()
    _smg_tri_count[0]      = 0
    _smg_dia_count[0]      = 0
    _smg_correct_clicks[0] = 0
    _smg_wrong_clicks[0]   = 0
    _smg_spawn_budget[0]   = 20
    _smg_tri_budget[0]     = random.randint(7, 12)
    _smg_dia_budget[0]     = random.randint(7, 12)
    _smg_last_spawn_t[0]   = ms
    _smg_next_spawn_dt[0]  = random.randint(700, 1100)
    _smg_r1_score_t0[0]    = 0

# ──────────────────────────────────────────────────────────────────
# 考場倒數動畫（形狀小遊戲之前的預備儀式）
# ──────────────────────────────────────────────────────────────────
_PCD_MSG_MS   = 1200   # "準備進行考場壓力小遊戲！" 顯示時長 (ms)
_PCD_DIG_SHOW = 500    # 每個數字完整顯示時長 (ms)
_PCD_DIG_FADE = 450    # 每個數字淡出時長 (ms)
_PCD_GO_SHOW  = 700    # "開始！" 完整顯示時長 (ms)
_PCD_GO_FADE  = 500    # "開始！" 淡出時長 (ms)

def _draw_pregame_countdown(surf: "pygame.Surface", fm, ms: int) -> bool:
    """
    在形狀小遊戲之前播放倒數動畫。
    動畫序列：「準備進行考場壓力小遊戲！」→ 3 → 2 → 1 → 開始！
    回傳 True 代表動畫已結束，呼叫端應立即觸發 _reply_event.set()。
    """
    if not _pcd_active[0]:
        return False

    phase   = _pcd_phase[0]
    elapsed = ms - _pcd_t0[0]

    # 深色半透明遮罩（疊在所有遊戲 UI 之上）
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 165))
    surf.blit(ov, (0, 0))

    cx, cy   = WIN_W // 2, WIN_H // 2
    fc_big   = _extra_fonts.get("creative_84b") or fm   # 大號倒數數字
    fc_label = _font_bold_xl[0] or fm                    # "準備進行..." 提示文字

    # ── "準備進行考場壓力小遊戲！" ──────────────────────────────
    if phase == "msg":
        t_in  = min(1.0, elapsed / 300)     # 前 300ms 淡入
        alpha = int(255 * t_in)
        txt   = fc_label.render("準備進行考場壓力小遊戲！", True, (255, 240, 180))
        tmp   = txt.copy()
        tmp.set_alpha(alpha)
        surf.blit(tmp, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
        if elapsed >= _PCD_MSG_MS:
            _pcd_phase[0] = "3"
            _pcd_t0[0]    = ms
            _play_sfx("pcd_3")

    # ── 3 / 2 / 1 ──────────────────────────────────────────────
    elif phase in ("3", "2", "1"):
        total = _PCD_DIG_SHOW + _PCD_DIG_FADE
        if elapsed < _PCD_DIG_SHOW:
            t_shrink = elapsed / _PCD_DIG_SHOW
            scale    = 1.45 - 0.45 * t_shrink   # 1.45x → 1.0x 衝入感
            alpha    = 255
        elif elapsed < total:
            scale  = 1.0
            t_fade = (elapsed - _PCD_DIG_SHOW) / _PCD_DIG_FADE
            alpha  = int(255 * (1.0 - t_fade))
        else:
            # 推進到下一階段
            nxt = {"3": "2", "2": "1", "1": "go"}[phase]
            _pcd_phase[0] = nxt
            _pcd_t0[0]    = ms
            if nxt != "go":
                _play_sfx("pcd_3")    # 2 和 1 使用同一個提示音
            else:
                _play_sfx("pcd_go")   # 開始！音效
            return False

        digit_s = fc_big.render(phase, True, (255, 255, 255))
        if scale != 1.0:
            nw = max(1, int(digit_s.get_width()  * scale))
            nh = max(1, int(digit_s.get_height() * scale))
            digit_s = pygame.transform.smoothscale(digit_s, (nw, nh))
        tmp = digit_s.copy()
        tmp.set_alpha(alpha)
        surf.blit(tmp, (cx - digit_s.get_width()  // 2,
                        cy - digit_s.get_height() // 2))

    # ── 開始！──────────────────────────────────────────────────
    elif phase == "go":
        total = _PCD_GO_SHOW + _PCD_GO_FADE
        if elapsed < _PCD_GO_SHOW:
            alpha = 255
        elif elapsed < total:
            t_fade = (elapsed - _PCD_GO_SHOW) / _PCD_GO_FADE
            alpha  = int(255 * (1.0 - t_fade))
        else:
            # 動畫全部結束，重置並通知呼叫端
            _pcd_active[0] = False
            _pcd_phase[0]  = "msg"
            return True

        go_s = fc_big.render("開始！", True, (255, 215, 60))
        tmp  = go_s.copy()
        tmp.set_alpha(alpha)
        surf.blit(tmp, (cx - go_s.get_width()  // 2,
                        cy - go_s.get_height() // 2))

    return False

# ── __all__ ───────────────────────────────────────────────
__all__ = [
    "_draw_shape_minigame",
    "_draw_memory_question",
    "_draw_pregame_countdown",
    "shape_rect",
    "ROUND_MS",
    "SHAPE_COLORS",
]
