# ============================================================
#  ui_draw_fx.py -- Weather FX, click effects, ripple, BG, screens
#  by refactor_ui.py
# ============================================================
from __future__ import annotations
import pygame
import math
import random
import os

from ui_const import *
from ui_state  import *
from ui_draw_base import *
from ui_draw_hud import _draw_log

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
            pygame.draw.circle(ov, (255, 240, 210, alpha), (cx, cy), r, thick)
    surf.blit(ov, (0, 0))

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

def _draw_character_art(surf, rect):
    """
    人物立繪區：顯示玩家選擇的角色立繪（含淡入淡出轉場）。
    rect 為整個立繪區的 Rect（STATUS_H..STATUS_H+CHAR_H, 全寬）。
    """
    key = _get_portrait_key()
    _portrait_switch(key, rect.width, int(rect.height * PORTRAIT_DISPLAY_H_FACTOR))

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
        py = rect.y + PORTRAIT_TOP_PAD   # 頂部對齊，頭部距頂 15px
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

def _draw_start(surf, fm, fl, mpos):
    """
    開始畫面（全面改版）：
      - 封面背景圖
      - 櫻花天氣特效（懶初始化）
      - 字元輪色 + 描邊 + TV 訊號雜訊/掃描線扭曲標題（無副標）
      - 圓形開始按鈕 + 雙軌旋轉光環粒子
    回傳按鈕命中 Rect。
    """
    # ── 背景圖 ────────────────────────────────────────────────
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)

    ms = pygame.time.get_ticks()

    # ── 懶初始化：開始畫面固定使用「櫻花」天氣 ───────────────
    if _weather_type[0] is None:
        _weather_type[0] = "sakura"
        _weather_pts.clear()
        for _ in range(72):
            _weather_pts.append(_wx_leaf_new("sakura", full_screen=True))

    # ── 天氣特效（櫻花）────────────────────────────────────────
    _draw_weather(surf, ms)

    # ── 懸浮偏移（標題 + 按鈕同步）────────────────────────────
    _fy = _float_offset(amp=9, speed=0.00155)

    # ════════════════════════════════════════════════════════════
    #  ① Creative.ttc 字元輪色 + 弧形排列（Arch Up）+ 描邊標題
    # ════════════════════════════════════════════════════════════
    TITLE_TEXT  = "如何渡過這學期？"
    N           = len(TITLE_TEXT)
    GOLD        = (255, 185, 30)   # 活躍字元高亮色
    WHITE_T     = (255, 255, 255)
    OUTLINE_COL = (18,  8, 45)     # 深紫描邊
    OUTLINE_OFF = 2                # 描邊厚度（px）

    # — 字型：優先 Creative.ttc 84px 粗體，否則 fallback 到 fl —
    _CREATIVE_PATH = resource_path("asset", "fonts", "Creative.ttc")
    _ck = "creative_84b"
    if _ck not in _extra_fonts:
        try:
            _f = pygame.font.Font(_CREATIVE_PATH, 84)
            _f.set_bold(True)
            _extra_fonts[_ck] = _f
        except Exception:
            _extra_fonts[_ck] = fl
    fc = _extra_fonts[_ck]

    # 1 秒循環：每個字元依序亮 1000/N ms
    active_idx = int((ms % 1000) / 1000 * N)

    # ── 弧形參數（圓心在文字正下方，文字沿圓頂排列）──────────
    ARC_R          = 500                  # 圓弧半徑（越大越平緩）
    TOTAL_ARC_RAD  = math.radians(72)     # 整體弧度（字型放大後拉寬至 72°）
    LETTER_SPACING = 22                   # 每字額外間距（px）

    arc_top_y  = WIN_H // 3 - 20 + _fy   # 弧頂（中心字元）目標 y
    arc_cx     = WIN_W // 2
    arc_cy     = arc_top_y + ARC_R        # 圓心在標題正下方

    # 各字元弧角（字元寬度 + 間距 比例分配弧度，使字間距均勻拉開）
    ch_ws_fc   = [fc.size(ch)[0] for ch in TITLE_TEXT]
    ch_ws_sp   = [cw + LETTER_SPACING for cw in ch_ws_fc]   # 含間距的虛擬寬度
    total_w_fc = sum(ch_ws_sp)
    thetas = []
    acc = 0
    for cw in ch_ws_sp:
        t = TOTAL_ARC_RAD * (acc + cw / 2) / total_w_fc - TOTAL_ARC_RAD / 2
        thetas.append(t)
        acc += cw

    # 各字元中心在螢幕上的位置
    arc_positions = [
        (arc_cx + ARC_R * math.sin(t),
         arc_cy - ARC_R * math.cos(t))
        for t in thetas
    ]

    # ── 建立合成 Surface（包含所有弧形字元），用於後續 glitch ──
    char_h_fc = fc.get_height()
    pad_c     = int(char_h_fc * 0.9)      # 旋轉 bounding box 膨脹保護
    xs_c = [p[0] for p in arc_positions]
    ys_c = [p[1] for p in arc_positions]
    comp_x1 = max(0, int(min(xs_c)) - pad_c - int(max(ch_ws_fc)))
    comp_y1 = max(0, int(min(ys_c)) - pad_c)
    comp_x2 = min(WIN_W, int(max(xs_c)) + pad_c + int(max(ch_ws_fc)))
    comp_y2 = min(WIN_H, int(max(ys_c)) + pad_c + char_h_fc)
    comp_w  = max(1, comp_x2 - comp_x1)
    comp_h  = max(1, comp_y2 - comp_y1)

    comp = pygame.Surface((comp_w, comp_h), pygame.SRCALPHA)

    # — 描邊層（旋轉後 8 方向貼到合成 surf）—
    for i, ch in enumerate(TITLE_TEXT):
        theta   = thetas[i]
        px, py  = arc_positions[i]
        rot_deg = -math.degrees(theta)        # pygame 正角 = 逆時針
        out_rot = pygame.transform.rotate(fc.render(ch, True, OUTLINE_COL), rot_deg)
        ow, oh  = out_rot.get_size()
        bx = int(px) - ow // 2 - comp_x1
        by = int(py) - oh // 2 - comp_y1
        for ox, oy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
            comp.blit(out_rot, (bx + ox * OUTLINE_OFF, by + oy * OUTLINE_OFF))

    # — 主文字層（帶輪色）—
    for i, ch in enumerate(TITLE_TEXT):
        theta   = thetas[i]
        px, py  = arc_positions[i]
        rot_deg = -math.degrees(theta)
        col     = GOLD if i == active_idx else WHITE_T
        ch_rot  = pygame.transform.rotate(fc.render(ch, True, col), rot_deg)
        cw_, ch_ = ch_rot.get_size()
        bx = int(px) - cw_ // 2 - comp_x1
        by = int(py) - ch_ // 2 - comp_y1
        comp.blit(ch_rot, (bx, by))

    # ════════════════════════════════════════════════════════════
    #  ② TV 訊號雜訊 / 掃描線扭曲特效（作用在合成 Surface 上）
    # ════════════════════════════════════════════════════════════
    rng = random.Random(ms // 80)   # 每 80ms 換一組雜訊

    # 主合成 blit
    surf.blit(comp, (comp_x1, comp_y1))

    # 掃描線錯位（0–3 條隨機水平帶，以 x 偏移模擬訊號不穩）
    n_strips = rng.randint(0, 3)
    for _ in range(n_strips):
        sy   = rng.randint(0, max(1, comp_h - 3))
        sh_  = rng.randint(2, 5)
        dx   = rng.randint(-22, 22)
        avail = comp_h - sy
        if avail <= 0:
            continue
        ss = pygame.Surface((comp_w, min(sh_, avail)), pygame.SRCALPHA)
        ss.blit(comp, (0, 0), (0, sy, comp_w, sh_))
        surf.blit(ss, (comp_x1 + dx, comp_y1 + sy))

    # 色差爆裂（25% 機率，模擬瞬間訊號失真）
    if rng.random() < 0.25:
        ca_dx = rng.randint(4, 10)
        ca_sf = comp.copy()
        ca_sf.set_alpha(70)
        surf.blit(ca_sf, (comp_x1 + ca_dx, comp_y1))

    # ════════════════════════════════════════════════════════════
    #  ③ 圓形「開始 / 遊戲」按鈕 + 雙軌旋轉光環
    # ════════════════════════════════════════════════════════════
    BTN_R  = 54
    btn_cx = WIN_W // 2
    btn_cy = WIN_H // 2 + 90 + _fy

    # 圓形 hover 判定
    _bdx  = mpos[0] - btn_cx
    _bdy  = mpos[1] - btn_cy
    hover = (_bdx * _bdx + _bdy * _bdy) <= (BTN_R * BTN_R)

    # — 光環粒子（SRCALPHA surface，避免蓋住背景）—
    halo_sf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

    # 靜態光暈圈
    pygame.draw.circle(halo_sf, (*BTN_N, 40),  (btn_cx, btn_cy), BTN_R + 16, 14)
    pygame.draw.circle(halo_sf, (*BTN_N, 18),  (btn_cx, btn_cy), BTN_R + 32,  6)

    # 內軌粒子（順時針，1 圈/秒）
    _HALO_N1 = 20
    _HALO_R1 = BTN_R + 22
    _ang0    = (ms * 0.001) * math.tau
    for i in range(_HALO_N1):
        ang = _ang0 + i * math.tau / _HALO_N1
        px  = btn_cx + math.cos(ang) * _HALO_R1
        py  = btn_cy + math.sin(ang) * _HALO_R1
        pr  = max(1, 3 + int(1.5 * math.sin(ang * 3 + ms * 0.002)))
        alp = max(0, min(255, 185 + int(70 * math.sin(ang * 2 + ms * 0.0015))))
        pygame.draw.circle(halo_sf, (*BTN_N, alp), (int(px), int(py)), pr)

    # 外軌粒子（逆時針，約 0.45 圈/秒）
    _HALO_N2 = 11
    _HALO_R2 = BTN_R + 38
    _ang1    = -(ms * 0.00045) * math.tau
    for i in range(_HALO_N2):
        ang = _ang1 + i * math.tau / _HALO_N2
        px  = btn_cx + math.cos(ang) * _HALO_R2
        py  = btn_cy + math.sin(ang) * _HALO_R2
        alp = max(0, min(255, 105 + int(65 * math.sin(ang * 2))))
        pygame.draw.circle(halo_sf, (255, 215, 120, alp), (int(px), int(py)), 2)

    surf.blit(halo_sf, (0, 0))

    # — 按鈕主圓 —
    _soft_shadow_circle(surf, btn_cx, btn_cy, BTN_R, alpha=70)
    _premium_circle(surf, btn_cx, btn_cy, BTN_R, BTN_N, hover, key=("start_btn",))

    # — 文字（「開始」/ 「遊戲」各佔一行）—
    fb = _font_bold[0] or fm
    t1 = fb.render("開始", True, (255, 255, 255))
    t2 = fb.render("遊戲", True, (255, 255, 255))
    lh = t1.get_height()
    surf.blit(t1, (btn_cx - t1.get_width() // 2, btn_cy - lh - 2))
    surf.blit(t2, (btn_cx - t2.get_width() // 2, btn_cy + 2))

    # ── [DEV_BTN DISABLED] DEV 跳關按鈕（目前已隱藏）──────────
    # 還原：取消下方 7 行的 # 號，並把下面 return 中的 None 改回 dev_r，
    #       再將 main.py 的 DEBUG 改回 True。
    # fb      = _font_bold[0] or fm
    # DEV_W, DEV_H = 68, 26
    # dev_x   = WIN_W - DEV_W - 14
    # dev_y   = WIN_H - DEV_H - 14
    # dev_r   = pygame.Rect(dev_x, dev_y, DEV_W, DEV_H)
    # dev_hov = dev_r.collidepoint(mpos)
    # dev_bg  = (120, 60, 175) if dev_hov else (75, 38, 120)
    # pygame.draw.rect(surf, dev_bg, dev_r, border_radius=6)
    # dev_t   = fb.render("DEV", True, (220, 195, 255))
    # surf.blit(dev_t, (dev_x + (DEV_W - dev_t.get_width())  // 2,
    #                   dev_y + (DEV_H - dev_t.get_height()) // 2))

    # ── 遊戲說明按鈕（開始按鈕下方）──────────────────────────
    GD_W, GD_H = 100, 32
    gd_x   = btn_cx - GD_W // 2
    gd_y   = btn_cy + BTN_R + 18 + int(_fy)
    gd_r   = pygame.Rect(gd_x, gd_y, GD_W, GD_H)
    gd_hov = gd_r.collidepoint(mpos)
    gd_bg  = (100, 78, 160) if gd_hov else (58, 44, 100)
    pygame.draw.rect(surf, gd_bg, gd_r, border_radius=10)
    pygame.draw.rect(surf, (140, 110, 210), gd_r, 1, border_radius=10)
    gd_t   = fb.render("遊戲說明", True, (230, 215, 255))
    surf.blit(gd_t, (gd_x + (GD_W - gd_t.get_width())  // 2,
                     gd_y + (GD_H - gd_t.get_height()) // 2))

    # 回傳外接方形 Rect（供 collidepoint 命中判定使用）
    # [DEV_BTN DISABLED] 還原時將 None 改回 dev_r
    return (pygame.Rect(btn_cx - BTN_R, btn_cy - BTN_R, BTN_R * 2, BTN_R * 2),
            None, gd_r)

# ── 結算畫面計時常數 ──────────────────────────────────────────
_EFADE_MS   = 600    # 淡出 / 淡入各 600ms
_EANIM_MS   = 2000   # 過場動畫 2 秒
_ESTAMP_INT = 500    # 各成績項目間隔 ms
_EPOP_MS    = 280    # stamp pop 動畫時長 ms
_ECOMMENT   = 600    # 最後一項後延遲顯示評語
_EBTN_DELAY = 300    # 評語後延遲顯示按鈕

# 成績項目：(顯示標籤, 比例文字, grades dict 鍵)
_REPORT_ROWS = [
    ("參與度", "10%", "參與度"),
    ("作　業", "20%", "作業"),
    ("小　考", "10%", "小考"),
    ("期　中", "30%", "期中"),
    ("期　末", "30%", "期末"),
]
_N_STAMPS = len(_REPORT_ROWS) + 2   # 5 行 + 1 總分 + 1 自我滿意度 = 7 個 stamp

# 再來一次按鈕：米灰色
_END_BTN_COL = (196, 178, 155)


def _draw_end(surf, fm, fs, mpos):
    """
    結束畫面總控。
    sub-phases: fade_out_1 → fade_in_1 → anim → fade_out_2 → fade_in_2 → report
    """
    ms      = pygame.time.get_ticks()

    # ── Sub-phase 自動推進 ─────────────────────────────────────
    for _ in range(6):   # 最多連續推進 6 步（理論上每幀只推 1 步）
        sub     = _end_sub[0]
        elapsed = max(0, ms - _end_t0[0])
        if   sub == "fade_out_1" and elapsed >= _EFADE_MS:
            _end_sub[0] = "fade_in_1";  _end_t0[0] = ms
        elif sub == "fade_in_1"  and elapsed >= _EFADE_MS:
            _end_sub[0] = "anim";       _end_t0[0] = ms
            # 進入影片動畫前，將影片倒帶回第 0 幀
            if _end_player[0] is not None:
                _end_player[0].reset()
            _end_video_surf[0] = None
            _end_video_done[0] = False
        elif sub == "anim":
            # 影片播完 或 超過最長等待時間 → 推進至淡出
            _anim_max = _EANIM_MS if (_end_player[0] is None or not _end_player[0].loaded) else 30000
            if _end_video_done[0] or elapsed >= _anim_max:
                _end_sub[0] = "fade_out_2"; _end_t0[0] = ms
            else:
                break   # 影片仍在播放中，等待
        elif sub == "fade_out_2" and elapsed >= _EFADE_MS:
            _end_sub[0] = "fade_in_2";  _end_t0[0] = ms
        elif sub == "fade_in_2"  and elapsed >= _EFADE_MS:
            _end_sub[0] = "report";     _end_t0[0] = ms
            _request_bgm(None)   # 成績單出現時才淡出背景音樂
        else:
            break

    sub     = _end_sub[0]
    elapsed = max(0, ms - _end_t0[0])
    data    = _settlement_data[0]

    # ── 淡出 / 淡入白幕 ────────────────────────────────────────
    if sub in ("fade_out_1", "fade_in_1", "fade_out_2", "fade_in_2"):
        # fade_out_2 / fade_in_2：以影片最後一幀為底，讓白色淡出更流暢
        if sub in ("fade_out_2", "fade_in_2") and _end_video_surf[0] is not None:
            surf.blit(_end_video_surf[0], (0, 0))
        elif "start" in _grads:
            surf.blit(_grads["start"], (0, 0))
        else:
            surf.fill(BG)
        t = min(1.0, elapsed / _EFADE_MS)
        alpha = int(255 * t) if "out" in sub else int(255 * (1.0 - t))
        ov = pygame.Surface((WIN_W, WIN_H))
        ov.fill((255, 255, 255))
        ov.set_alpha(alpha)
        surf.blit(ov, (0, 0))
        return None

    # ── 過場動畫（佔位） ─────────────────────────────────────────
    if sub == "anim":
        _draw_end_anim(surf, fm, fs, elapsed)
        return None

    # ── 成績單 ───────────────────────────────────────────────────
    if sub == "report":
        return _draw_end_report(surf, fm, fs, mpos, data, ms, elapsed)

    return None


def _draw_end_anim(surf, fm, fs, elapsed):
    """過場動畫：播放結算過場影片（SpritePlayer）；影格資料夾缺失時退回轉圈動畫。"""
    player = _end_player[0]

    if player is not None and player.loaded:
        # ── 影片播放（SpritePlayer）──────────────────────────────
        now = pygame.time.get_ticks()
        if not _end_video_done[0]:
            _frame = player.get_surface(now, (WIN_W, WIN_H))
            if _frame is not None:
                _end_video_surf[0] = _frame
            if player.done:
                _end_video_done[0] = True

        # 繪製當前幀；影片尚未讀到第一幀時以白底填充
        if _end_video_surf[0] is not None:
            surf.blit(_end_video_surf[0], (0, 0))
        else:
            surf.fill((255, 255, 255))

    else:
        # ── 退回：旋轉光圈 + 文字「計算成績中」（cv2 未安裝或影片未載入）──
        if "start" in _grads:
            surf.blit(_grads["start"], (0, 0))
        else:
            surf.fill(BG)

        cx, cy = WIN_W // 2, WIN_H // 2
        fb     = _font_bold[0] or fm

        pulse  = 0.5 + 0.5 * math.sin(elapsed * 0.0025)
        halo_s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        pygame.draw.circle(halo_s, (*BTN_N, int(70 * pulse)),  (cx, cy), 80, 14)
        pygame.draw.circle(halo_s, (*BTN_N, int(35 * pulse)),  (cx, cy), 108, 5)
        surf.blit(halo_s, (0, 0))

        dot_s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        for i in range(8):
            ang = elapsed * 0.0025 + i * math.tau / 8
            px  = cx + int(math.cos(ang) * 52)
            py  = cy + int(math.sin(ang) * 52)
            alp = 90 + int(155 * (i / 8))
            pygame.draw.circle(dot_s, (*BTN_N, alp), (px, py), 6)
        surf.blit(dot_s, (0, 0))

        dots   = "．" * (int(elapsed / 500) % 4)
        text_s = fb.render("計算成績中" + dots, True, TITLE)
        surf.blit(text_s, (cx - text_s.get_width() // 2, cy + 72))


def _draw_end_report(surf, fm, fs, mpos, data, ms, elapsed):
    """成績單：stamp 動畫 + 評語 + 再來一次圓形按鈕。"""
    fb    = _font_bold[0]    or fm
    fb_lg = _font_bold_lg[0] or fm
    fb_xl = _font_bold_xl[0] or fm

    grades      = (data or {}).get("grades",      {})
    final_score = (data or {}).get("final_score",  0.0)
    comment     = (data or {}).get("comment",      "")

    comment_show_t = _N_STAMPS * _ESTAMP_INT + _ECOMMENT   # 評語出現時間點（提前計算供背景使用）

    # ── 新出現的 stamp → 觸發晃動 + 音效 ─────────────────────
    should_show = min(_N_STAMPS, int(elapsed // _ESTAMP_INT))
    if should_show > _end_stamps_shown[0]:
        _stamp_shake_t0[0] = ms
        _play_sfx("stamp_hit")
        _end_stamps_shown[0] = should_show

    # ── 背景（評語出現前：羊皮紙；出現後：漸變到結局影片）──────
    _FADE_BG_MS = 1200  # 背景淡入時間（ms）

    if elapsed >= comment_show_t and comment and _end_bg_fade_t0[0] == 0:
        if comment.startswith("平衡型結局"):
            _end_bg_key[0] = "best"
        elif comment.startswith("及格快樂結局"):
            _end_bg_key[0] = "next"
        elif comment.startswith("成績過了但身心崩潰"):
            _end_bg_key[0] = "break"
        else:
            _end_bg_key[0] = "lose"
        _end_bg_fade_t0[0] = ms

    if _end_bg_fade_t0[0] > 0:
        key    = _end_bg_key[0]
        player = _end_bg_players.get(key) if key else None
        if player is not None and player.loaded:
            _frame = player.get_surface(ms, (WIN_W, WIN_H))
            if _frame is not None:
                _end_bg_surf[0] = _frame

        if _end_bg_surf[0] is not None:
            surf.blit(_end_bg_surf[0], (0, 0))
            fade_elapsed = max(0, ms - _end_bg_fade_t0[0])
            t  = min(1.0, fade_elapsed / _FADE_BG_MS)
            ov = pygame.Surface((WIN_W, WIN_H))
            ov.fill((248, 238, 220))
            ov.set_alpha(int(255 * (1.0 - t)))
            surf.blit(ov, (0, 0))
        else:
            surf.fill((248, 238, 220))
    else:
        surf.fill((248, 238, 220))

    CARD_X, CARD_Y, CARD_W, CARD_H = 100, 12, 760, 590
    card_r = pygame.Rect(CARD_X, CARD_Y, CARD_W, CARD_H)
    card_s = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
    pygame.draw.rect(card_s, (255, 250, 240, 255), (0, 0, CARD_W, CARD_H), border_radius=14)
    surf.blit(card_s, card_r.topleft)
    pygame.draw.rect(surf, (165, 135, 95), card_r, 2, border_radius=14)

    cx = CARD_X + CARD_W // 2

    # ── 標題 ────────────────────────────────────────────────────
    title_s = fb_xl.render("成　績　單", True, TITLE)
    title_y = CARD_Y + 16
    surf.blit(title_s, (cx - title_s.get_width() // 2, title_y))

    sub_s = fs.render("本學期綜合成績", True, GRAY)
    sub_y = title_y + title_s.get_height() + 4
    surf.blit(sub_s, (cx - sub_s.get_width() // 2, sub_y))

    div_y = sub_y + sub_s.get_height() + 8
    pygame.draw.line(surf, (180, 148, 108),
                     (CARD_X + 20, div_y), (CARD_X + CARD_W - 20, div_y), 1)

    # ── 成績行 ─────────────────────────────────────────────────
    ROW_H  = 60
    row_y0 = div_y + 10
    lx     = CARD_X + 28
    rx     = CARD_X + CARD_W - 28

    for i, (label, pct, key) in enumerate(_REPORT_ROWS):
        if i >= should_show:
            break

        score  = grades.get(key, 0.0)
        age    = elapsed - i * _ESTAMP_INT
        row_cy = row_y0 + i * ROW_H + ROW_H // 2

        lbl_s   = fb.render(f"{label}  ({pct})", True, TITLE)
        score_s = fb_lg.render(f"{score:.1f}", True, TITLE)

        # Pop scale 1.35 → 1.0 over _EPOP_MS
        if 0 < age < _EPOP_MS:
            sc = 1.0 + 0.35 * (1.0 - age / _EPOP_MS)
            lbl_s   = pygame.transform.smoothscale(lbl_s,
                (max(1, int(lbl_s.get_width()   * sc)),
                 max(1, int(lbl_s.get_height()  * sc))))
            score_s = pygame.transform.smoothscale(score_s,
                (max(1, int(score_s.get_width() * sc)),
                 max(1, int(score_s.get_height()* sc))))

        surf.blit(lbl_s,   (lx, row_cy - lbl_s.get_height()   // 2))
        surf.blit(score_s, (rx - score_s.get_width(),
                             row_cy - score_s.get_height() // 2))

    # ── 總分行 ─────────────────────────────────────────────────
    total_div_y = row_y0 + len(_REPORT_ROWS) * ROW_H - 4
    total_cy    = row_y0 + len(_REPORT_ROWS) * ROW_H + ROW_H // 2

    if should_show >= len(_REPORT_ROWS) + 1:
        pygame.draw.line(surf, (180, 148, 108),
                         (CARD_X + 20, total_div_y),
                         (CARD_X + CARD_W - 20, total_div_y), 1)

        age_t      = elapsed - len(_REPORT_ROWS) * _ESTAMP_INT
        score_col  = GREEN if final_score >= 60 else RED
        lbl_t      = fb_lg.render("加權總分", True, TITLE)
        score_t    = fb_xl.render(f"{final_score:.1f} 分", True, score_col)

        if 0 < age_t < _EPOP_MS:
            sc = 1.0 + 0.35 * (1.0 - age_t / _EPOP_MS)
            lbl_t   = pygame.transform.smoothscale(lbl_t,
                (max(1, int(lbl_t.get_width()   * sc)),
                 max(1, int(lbl_t.get_height()  * sc))))
            score_t = pygame.transform.smoothscale(score_t,
                (max(1, int(score_t.get_width() * sc)),
                 max(1, int(score_t.get_height()* sc))))

        surf.blit(lbl_t,   (lx, total_cy - lbl_t.get_height()   // 2))
        surf.blit(score_t, (rx - score_t.get_width(),
                             total_cy - score_t.get_height() // 2))

    # ── 最終自我滿意度行 ────────────────────────────────────────
    sat_div_y = row_y0 + (len(_REPORT_ROWS) + 1) * ROW_H - 4
    sat_cy    = row_y0 + (len(_REPORT_ROWS) + 1) * ROW_H + ROW_H // 2
    satisfaction = int((data or {}).get("satisfaction", 0))

    if should_show >= _N_STAMPS:
        pygame.draw.line(surf, (180, 148, 108),
                         (CARD_X + 20, sat_div_y),
                         (CARD_X + CARD_W - 20, sat_div_y), 1)

        age_s     = elapsed - (len(_REPORT_ROWS) + 1) * _ESTAMP_INT
        sat_col   = GREEN if satisfaction >= 60 else RED
        lbl_s2    = fb.render("自我滿意度", True, TITLE)
        score_s2  = fb_lg.render(f"{satisfaction} 分", True, sat_col)

        if 0 < age_s < _EPOP_MS:
            sc = 1.0 + 0.35 * (1.0 - age_s / _EPOP_MS)
            lbl_s2  = pygame.transform.smoothscale(lbl_s2,
                (max(1, int(lbl_s2.get_width()  * sc)),
                 max(1, int(lbl_s2.get_height() * sc))))
            score_s2 = pygame.transform.smoothscale(score_s2,
                (max(1, int(score_s2.get_width()  * sc)),
                 max(1, int(score_s2.get_height() * sc))))

        surf.blit(lbl_s2,  (lx, sat_cy - lbl_s2.get_height()  // 2))
        surf.blit(score_s2, (rx - score_s2.get_width(),
                              sat_cy - score_s2.get_height() // 2))

    # ── 評語 ───────────────────────────────────────────────────
    if elapsed >= comment_show_t and comment:
        cmt_s = fb_lg.render(comment, True, TITLE)
        cmt_y = sat_cy + ROW_H // 2 + 6
        surf.blit(cmt_s, (cx - cmt_s.get_width() // 2, cmt_y))

        # ── 結局 BGM（評語出現的那幀，僅觸發一次）──────────────
        if not _ending_bgm_triggered[0]:
            _ending_bgm_triggered[0] = True
            if comment.startswith("平衡型結局"):
                _request_bgm("Music-Journeys_End.ogg")
            elif comment.startswith("及格快樂結局"):
                _request_bgm("Music-Contest_Winner.ogg")
            elif comment.startswith("成績過了但身心崩潰"):
                _request_bgm("blendertimer-the-last-echo-410567.ogg")
            else:
                _request_bgm("prettyjohn1-sad-background-music_29sec-489884.ogg")

    # ── 再來一次 圓形按鈕（米灰色，同開始畫面設計） ───────────────
    btn_rect = None
    btn_show_t = comment_show_t + _EBTN_DELAY

    if elapsed >= btn_show_t:
        BTN_R  = 50
        btn_cx = WIN_W // 2
        btn_cy = CARD_Y + CARD_H + (WIN_H - CARD_Y - CARD_H) // 2

        _bdx  = mpos[0] - btn_cx
        _bdy  = mpos[1] - btn_cy
        hover = (_bdx * _bdx + _bdy * _bdy) <= BTN_R * BTN_R

        # 光環
        halo_sf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        pygame.draw.circle(halo_sf, (*_END_BTN_COL, 40),  (btn_cx, btn_cy), BTN_R + 16, 14)
        pygame.draw.circle(halo_sf, (*_END_BTN_COL, 18),  (btn_cx, btn_cy), BTN_R + 32, 6)
        ang0 = (ms * 0.001) * math.tau
        for i in range(16):
            ang = ang0 + i * math.tau / 16
            px  = btn_cx + int(math.cos(ang) * (BTN_R + 22))
            py  = btn_cy + int(math.sin(ang) * (BTN_R + 22))
            alp = max(0, min(255, 155 + int(90 * math.sin(ang * 2 + ms * 0.0015))))
            pygame.draw.circle(halo_sf, (*_END_BTN_COL, alp), (px, py), 3)
        surf.blit(halo_sf, (0, 0))

        _soft_shadow_circle(surf, btn_cx, btn_cy, BTN_R, alpha=55)
        _premium_circle(surf, btn_cx, btn_cy, BTN_R, _END_BTN_COL, hover, key=("end_btn",))

        t1 = fb.render("再來", True, (255, 255, 255))
        t2 = fb.render("一次", True, (255, 255, 255))
        lh = t1.get_height()
        surf.blit(t1, (btn_cx - t1.get_width() // 2, btn_cy - lh - 2))
        surf.blit(t2, (btn_cx - t2.get_width() // 2, btn_cy + 2))

        btn_rect = pygame.Rect(btn_cx - BTN_R, btn_cy - BTN_R, BTN_R * 2, BTN_R * 2)

    return btn_rect


# ── Game Over 畫面 ──────────────────────────────────────────────────────────────
_GO_FADE_MS      = 600    # 淡出 / 淡入各 600ms
_GO_WAIT_BTN     = 1000   # 背景出現後幾 ms 才顯示按鈕
_GO_TEXT_FALL_MS = 2400   # 遺憾文字從頂端滑入所需時間（ms，cubic ease-out）

def _build_go_silhouette(p: pygame.Surface) -> "pygame.Surface | None":
    """將立繪 Surface 轉為純黑剪影（保留 alpha）。"""
    if p is None:
        return None
    sil = pygame.Surface(p.get_size(), pygame.SRCALPHA)
    sil.fill((0, 0, 0, 255))
    # BLEND_RGBA_MIN：RGB 取 min(0, src)=0（保持黑色）；Alpha 取 min(255, src.a)=src.a
    sil.blit(p, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return sil

def _draw_go_silhouette_with_noise(surf: pygame.Surface, rect: pygame.Rect) -> None:
    """繪製人物黑色剪影（原始比例、居中），並在剪影內部疊加細緻雜訊（靜電感）。"""
    key = _get_portrait_key()
    if not key:
        return

    # 使用原始立繪（非 2.2x 放大版），等比縮放至立繪區
    orig = _portrait_orig_load(key)
    if orig is None:
        return
    ow, oh = orig.get_size()
    scale  = min(rect.height / oh, rect.width / ow)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))

    # 快取剪影（尺寸變動時重建）
    sil = _go_silhouette[0]
    if sil is None or sil.get_size() != (nw, nh):
        p   = pygame.transform.smoothscale(orig, (nw, nh))
        sil = _build_go_silhouette(p)
        _go_silhouette[0] = sil
    if sil is None:
        return

    pw, ph = sil.get_width(), sil.get_height()
    # 水平 + 垂直居中
    blit_x = rect.x + (rect.width  - pw) // 2
    blit_y = rect.y + (rect.height - ph) // 2

    # 每幀重生雜訊（每 80ms 換一批 → 靜電閃動感）
    draw_sil = sil.copy()
    noise_ov = pygame.Surface((pw, ph))
    noise_ov.fill((0, 0, 0))
    rng = random.Random(pygame.time.get_ticks() // 80)
    for _ in range(1800):
        nx = rng.randint(0, pw - 1)
        ny = rng.randint(0, ph - 1)
        nc = rng.randint(8, 88)
        sz = rng.randint(1, 2)
        pygame.draw.rect(noise_ov, (nc, nc, nc), (nx, ny, sz, sz))
    # BLEND_RGB_ADD：將亮點疊加到黑色剪影上（不影響 alpha，剪影形狀保持）
    draw_sil.blit(noise_ov, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    surf.blit(draw_sil, (blit_x, blit_y))

def _draw_gameover(surf: pygame.Surface, fm, fs, mpos) -> "pygame.Rect | None":
    """
    提前 Game Over 畫面。
    Sub-phases：fade_out（漸黑） → fade_in（背景淡入）→ show（完整畫面）。
    回傳「再來一次」按鈕 Rect；尚未顯示時回傳 None。
    """
    ms      = pygame.time.get_ticks()
    sub     = _go_sub[0]
    elapsed = ms - _go_t0[0]

    # ── 自動推進子階段 ──────────────────────────────────────────────
    if sub == "fade_out" and elapsed >= _GO_FADE_MS:
        _go_sub[0] = "fade_in"
        _go_t0[0]  = ms
        elapsed    = 0
        sub        = "fade_in"
    elif sub == "fade_in" and elapsed >= _GO_FADE_MS:
        _go_sub[0] = "show"
        _go_t0[0]  = ms
        elapsed    = 0
        sub        = "show"

    go_bg = _grads.get("gameover")
    cr    = pygame.Rect(0, STATUS_H, WIN_W, CHAR_H)   # 立繪區（同遊戲主畫面）

    # ── fade_out：純黑畫面（遊戲內容已消失）─────────────────────────
    if sub == "fade_out":
        surf.fill((0, 0, 0))
        return None

    # ── 背景底圖 ──────────────────────────────────────────────────
    if go_bg:
        surf.blit(go_bg, (0, 0))
    else:
        surf.fill((30, 20, 15))

    # ── fade_in：黑色遮罩由不透明→透明，背景逐漸顯現 ────────────────
    if sub == "fade_in":
        overlay_alpha = int(255 * (1.0 - min(1.0, elapsed / _GO_FADE_MS)))
        ov = pygame.Surface((WIN_W, WIN_H))
        ov.fill((0, 0, 0))
        ov.set_alpha(overlay_alpha)
        surf.blit(ov, (0, 0))
        return None

    # ── show：完整 Game Over 畫面 ──────────────────────────────────
    # 人物黑色剪影 + 內部雜訊
    _draw_go_silhouette_with_noise(surf, cr)

    # ── 緩降標題文字「很遺憾，你沒能撐過這學期……」──────────────────
    _go_fb_xl  = _font_bold_xl[0] or fm
    _go_msg    = _go_fb_xl.render("很遺憾，你沒能撐過這學期……", True, PANEL)
    _go_msg_w  = _go_msg.get_width()
    _go_msg_h  = _go_msg.get_height()
    _go_tgt_y  = 68                                    # 最終停駐 y（距頂部）
    _go_tnorm  = min(1.0, elapsed / _GO_TEXT_FALL_MS)
    _go_eased  = 1.0 - (1.0 - _go_tnorm) ** 3        # cubic ease-out
    _go_text_y = int(-_go_msg_h + (_go_tgt_y + _go_msg_h) * _go_eased)
    surf.blit(_go_msg, ((WIN_W - _go_msg_w) // 2, _go_text_y))

    # 「再來一次」按鈕（3 秒後才出現）
    if elapsed < _GO_WAIT_BTN:
        return None

    BTN_R  = 54
    btn_cx = WIN_W  // 2
    btn_cy = WIN_H  - BTN_R - 48
    br     = pygame.Rect(btn_cx - BTN_R, btn_cy - BTN_R, BTN_R * 2, BTN_R * 2)
    hover  = br.collidepoint(mpos)
    _premium_circle(surf, btn_cx, btn_cy, BTN_R, _END_BTN_COL, hover)
    fb = _font_bold[0] or fm
    t  = fb.render("再來一次", True, PANEL)
    surf.blit(t, (btn_cx - t.get_width() // 2, btn_cy - t.get_height() // 2))
    return br


# ── 生病狀態邊緣光暈效果 ────────────────────────────────────────────────────────
_SICK_COLORS = [
    (220,  30,  30),   # 紅
    ( 40,  80, 220),   # 藍
    ( 40, 180,  60),   # 綠
]
_SICK_CYCLE_SEC = 1.5  # 每個顏色持續秒數

def _draw_sick_vignette(surf: pygame.Surface, player) -> None:
    """
    生病狀態：螢幕外框以紅→藍→綠循環發光（FPS 低血量邊緣暈光風格）。
    僅在 player.status_effects 含「生病」時作用。
    """
    if player is None or "生病" not in getattr(player, "status_effects", {}):
        return

    t = pygame.time.get_ticks() / 1000.0

    # ── 顏色循環 ────────────────────────────────────────────────
    idx = int(t / _SICK_CYCLE_SEC) % len(_SICK_COLORS)
    r, g, b = _SICK_COLORS[idx]

    # ── 脈動（呼吸感）────────────────────────────────────────────
    pulse = 0.50 + 0.50 * abs(math.sin(t * math.pi * 1.3))

    # ── 向內漸層光暈（多層半透明矩形，從邊緣向中心淡出）────────────
    LAYERS = 22
    DEPTH  = 88      # 向內最深 px
    MAX_A  = 175     # 最邊緣層的最大 alpha

    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    for i in range(LAYERS):
        ratio  = ((LAYERS - i) / LAYERS) ** 2.0   # 二次方淡出
        alpha  = int(MAX_A * pulse * ratio)
        if alpha < 2:
            break
        margin = int(DEPTH * i / LAYERS)
        w_line = max(1, DEPTH // LAYERS + 1)
        pygame.draw.rect(
            ov,
            (r, g, b, alpha),
            pygame.Rect(margin, margin, WIN_W - 2 * margin, WIN_H - 2 * margin),
            w_line,
        )

    surf.blit(ov, (0, 0))


# ── 低滿意度黑色暈圈遮罩 ─────────────────────────────────────────────────────────
_SAT_NOISE_INTERVAL = 80   # ms，雜訊每幾毫秒換一批

def _draw_low_sat_vignette(surf: pygame.Surface, player) -> None:
    """
    自我滿意度 < 60 時：螢幕外圍黑色漸層暈圈（中央橢圓最亮，外圍最暗）+ 雜訊特效。
    sat=60 → 最外層 alpha=30；每 -1 點 +0.5；sat=0 → alpha=60。
    與生病光暈（_draw_sick_vignette）獨立 blit，兩者不衝突。
    """
    if player is None:
        return
    sat = getattr(player, "satisfaction", 100)
    if sat >= 60:
        return

    max_alpha = min(60, int(30 + (60 - max(sat, 0)) * 0.5))

    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    cx, cy = WIN_W // 2, WIN_H // 2

    # ── 橢圓輪廓漸層（外暗內亮）────────────────────────────────
    LAYERS  = 32
    BASE_RX = cx + 100          # 最外層橢圓半徑（延伸到螢幕外）
    BASE_RY = cy + 80
    MIN_RX  = int(cx * 0.28)    # 最內層（中央亮區半徑）
    MIN_RY  = int(cy * 0.28)
    LINE_W  = max(3, (BASE_RX - MIN_RX) // LAYERS + 3)   # 略大於間距，確保無縫銜接

    for i in range(LAYERS):
        frac  = i / (LAYERS - 1)                    # 0 = 最外, 1 = 最內
        alpha = int(max_alpha * (1.0 - frac) ** 0.7)
        if alpha < 1:
            break
        rx = max(2, int(BASE_RX - (BASE_RX - MIN_RX) * frac))
        ry = max(2, int(BASE_RY - (BASE_RY - MIN_RY) * frac))
        pygame.draw.ellipse(
            ov,
            (0, 0, 0, alpha),
            pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2),
            LINE_W,
        )

    # ── 雜訊：隨機暗點（每 80ms 換一批 → 靜電感）───────────────
    now = pygame.time.get_ticks()
    rng = random.Random(now // _SAT_NOISE_INTERVAL)
    noise_max_a = max(6, max_alpha // 2)
    for _ in range(130):
        nx  = rng.randint(0, WIN_W - 2)
        ny  = rng.randint(0, WIN_H - 2)
        na  = rng.randint(4, noise_max_a)
        sz  = rng.randint(1, 2)
        pygame.draw.rect(ov, (0, 0, 0, na), (nx, ny, sz, sz))

    surf.blit(ov, (0, 0))


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
