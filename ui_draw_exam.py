# ============================================================
#  ui_draw_exam.py -- 考試形狀小遊戲繪製
# ============================================================
import pygame
import random

from ui_state import *
from ui_const import *

SHAPE_COLORS = {
    "circle":   (100, 160, 255),
    "cross":    (255, 100, 100),
    "triangle": (255, 215, 60),
    "diamond":  (190, 100, 255),
}

ROUND_MS = 30_000   # 每回合 30 秒

# ── 形狀生成 ──────────────────────────────────────────────

def _spawn_shape(shape_type: str) -> dict:
    ms = pygame.time.get_ticks()
    elapsed_ratio = min((ms - _smg_t0[0]) / ROUND_MS, 1.0)
    speed = (2.5 + elapsed_ratio * 3.0) / 6.0   # px/ms（基礎速度）
    direction = _smg_direction[0]
    x = float(WIN_W + 60) if direction == -1 else float(-60)
    return {
        "type":      shape_type,
        "x":         x,
        "y":         float(random.randint(110, WIN_H - 120)),
        "speed":     speed,
        "direction": direction,
        "alive":     True,
    }

def _try_spawn(ms: int) -> None:
    """依計時器嘗試生成一個形狀（目標 / 三角 / 菱形混合）。"""
    if ms - _smg_last_spawn_t[0] < _smg_next_spawn_dt[0]:
        return

    # 決定要生成哪種形狀
    choices = []
    if _smg_spawn_budget[0] > 0:
        choices.append("target")
    if _smg_tri_budget[0] > 0:
        choices.append("triangle")
    if _smg_dia_budget[0] > 0:
        choices.append("diamond")
    if not choices:
        return

    # 若畫面上當前 phase 形狀為 0，強制補一個（無視計時器）
    phase_on_screen = sum(
        1 for s in _smg_shapes if s["alive"] and s["type"] == _smg_phase[0]
    )
    if phase_on_screen == 0 and _smg_spawn_budget[0] > 0:
        _smg_shapes.append(_spawn_shape(_smg_phase[0]))
        _smg_spawn_budget[0] -= 1
        _smg_last_spawn_t[0]  = ms
        _smg_next_spawn_dt[0] = random.randint(500, 800)
        return

    kind = random.choice(choices)
    if kind == "target":
        # 當前 phase 形狀 80%、另一種 20%
        other = "cross" if _smg_phase[0] == "circle" else "circle"
        shape_type = _smg_phase[0] if random.random() < 0.8 else other
        _smg_spawn_budget[0] -= 1
    elif kind == "triangle":
        shape_type = "triangle"
        _smg_tri_count[0]   += 1
        _smg_tri_budget[0]  -= 1
    else:
        shape_type = "diamond"
        _smg_dia_count[0]   += 1
        _smg_dia_budget[0]  -= 1

    _smg_shapes.append(_spawn_shape(shape_type))
    _smg_last_spawn_t[0]  = ms
    _smg_next_spawn_dt[0] = random.randint(700, 1100)

# ── 形狀繪製 ──────────────────────────────────────────────

def _draw_shape(surf: pygame.Surface, s: dict) -> None:
    x, y = int(s["x"]), int(s["y"])
    col = SHAPE_COLORS[s["type"]]
    t = s["type"]
    if t == "circle":
        pygame.draw.circle(surf, col, (x, y), 33, 4)
    elif t == "cross":
        pygame.draw.line(surf, col, (x - 27, y - 27), (x + 27, y + 27), 5)
        pygame.draw.line(surf, col, (x + 27, y - 27), (x - 27, y + 27), 5)
    elif t == "triangle":
        pts = [(x, y - 33), (x - 28, y + 21), (x + 28, y + 21)]
        pygame.draw.polygon(surf, col, pts, 4)
    elif t == "diamond":
        pts = [(x, y - 33), (x + 24, y), (x, y + 33), (x - 24, y)]
        pygame.draw.polygon(surf, col, pts, 4)

def shape_rect(s: dict) -> pygame.Rect:
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
    """每幀由 ui.py 呼叫；dt_ms 為上幀 tick 差。"""
    ms = pygame.time.get_ticks()
    elapsed = ms - _smg_t0[0]

    if _smg_q_active[0]:
        _draw_memory_question(surf, fm, fb, mpos)
        return

    # ── 更新形狀位置（依實際幀時間）──────────────────────
    for s in _smg_shapes:
        s["x"] += s["speed"] * s["direction"] * dt_ms
    _smg_shapes[:] = [
        s for s in _smg_shapes
        if s["alive"] and -90 < s["x"] < WIN_W + 90
    ]

    # ── 嘗試生成新形狀 ─────────────────────────────────
    _try_spawn(ms)

    # ── phase 切換檢查 ─────────────────────────────────
    if ms >= _smg_phase_end_t[0]:
        _smg_phase[0] = "cross" if _smg_phase[0] == "circle" else "circle"
        _smg_phase_end_t[0] = ms + random.randint(8000, 12000)
        _smg_phase_flash_t[0] = ms

    # ── 繪製黑紫深色背景 ────────────────────────────────
    surf.fill((18, 12, 35))

    # ── 繪製所有形狀 ────────────────────────────────────
    for s in _smg_shapes:
        _draw_shape(surf, s)

    # ── HUD：點擊目標文字 ──────────────────────────────
    target_name = "圓形 ○" if _smg_phase[0] == "circle" else "叉形 ×"
    inst_surf = fm.render(f"點擊：{target_name}", True, (255, 240, 180))
    surf.blit(inst_surf, (WIN_W // 2 - inst_surf.get_width() // 2, 14))

    # ── HUD：回合標示 ──────────────────────────────────
    round_surf = fs.render(f"回合 {_smg_round[0]} / 2", True, (160, 140, 200))
    surf.blit(round_surf, (WIN_W - round_surf.get_width() - 16, 14))

    # ── HUD：計時條 ────────────────────────────────────
    ratio = max(0.0, 1.0 - elapsed / ROUND_MS)
    bar_x, bar_y, bar_total_w, bar_h = 40, 50, WIN_W - 80, 10
    pygame.draw.rect(surf, (60, 55, 80),
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

    # ── HUD：分數預覽 ──────────────────────────────────
    pv = 70 / 20
    cs = max(0.0, _smg_correct_clicks[0] * pv - _smg_wrong_clicks[0] * pv)
    score_surf = fs.render(
        f"點擊 {_smg_correct_clicks[0]}✓  {_smg_wrong_clicks[0]}✗  "
        f"({cs:.0f}pt)",
        True, (180, 170, 210),
    )
    surf.blit(score_surf, (16, 14))

    # ── Phase 切換閃字 ─────────────────────────────────
    if _smg_phase_flash_t[0] and ms - _smg_phase_flash_t[0] < 1500:
        progress = (ms - _smg_phase_flash_t[0]) / 1500
        alpha = max(0, int(255 * (1.0 - progress)))
        flash_surf = fm.render(f"改按 {target_name}！", True, (255, 240, 120))
        flash_surf.set_alpha(alpha)
        surf.blit(
            flash_surf,
            (WIN_W // 2 - flash_surf.get_width() // 2,
             WIN_H // 2 - flash_surf.get_height() // 2),
        )

    # ── 回合結束 → 進入記憶問題 ────────────────────────
    if elapsed >= ROUND_MS:
        _smg_shapes.clear()
        q_shape = random.choice(["triangle", "diamond"])
        _smg_q_shape[0] = q_shape
        correct = _smg_tri_count[0] if q_shape == "triangle" else _smg_dia_count[0]
        _smg_q_correct[0] = correct

        raw_opts = sorted(set(max(0, correct + d) for d in (-3, -1, 0, 1)))
        # 補足到 4 個選項
        while len(raw_opts) < 4:
            raw_opts.append(raw_opts[-1] + 1)
        raw_opts = raw_opts[:4]
        random.shuffle(raw_opts)
        _smg_q_opts[:] = raw_opts
        _smg_q_rects.clear()
        _smg_q_active[0] = True

# ── 記憶問題畫面 ──────────────────────────────────────────

def _draw_memory_question(
    surf: pygame.Surface,
    fm: pygame.font.Font,
    fb: pygame.font.Font,
    mpos: tuple,
) -> None:
    surf.fill((18, 12, 35))

    shape_name = "三角形 △" if _smg_q_shape[0] == "triangle" else "菱形 ◇"
    q_surf = fm.render(f"剛才飛過幾個{shape_name}？", True, (255, 240, 180))
    surf.blit(q_surf, (WIN_W // 2 - q_surf.get_width() // 2, WIN_H // 2 - 120))

    _smg_q_rects.clear()
    for i, val in enumerate(_smg_q_opts):
        bx = WIN_W // 2 - 260 + i * 130
        by = WIN_H // 2 - 10
        br = pygame.Rect(bx, by, 110, 52)
        hov = br.collidepoint(mpos)
        pygame.draw.rect(
            surf,
            (80, 65, 130) if hov else (50, 42, 88),
            br, border_radius=12,
        )
        pygame.draw.rect(surf, (140, 110, 200), br, 2, border_radius=12)
        vt = fb.render(str(val), True, (255, 255, 255))
        surf.blit(
            vt,
            (br.x + (br.width  - vt.get_width())  // 2,
             br.y + (br.height - vt.get_height()) // 2),
        )
        _smg_q_rects.append((br, val))


# ── __all__ ───────────────────────────────────────────────
__all__ = [
    "_draw_shape_minigame",
    "_draw_memory_question",
    "shape_rect",
    "ROUND_MS",
    "SHAPE_COLORS",
]
