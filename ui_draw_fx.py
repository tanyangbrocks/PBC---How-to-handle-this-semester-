# ============================================================
#  ui_draw_fx.py -- Weather FX, click effects, ripple, BG, screens
#  by refactor_ui.py
# ============================================================
import pygame
import math
import random
import os

from ui_const import *
from ui_state  import *
from ui_draw_base import *

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
            pygame.draw.circle(ov, (190, 225, 255, alpha), (cx, cy), r, thick)
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
    _CREATIVE_PATH = r"C:\Users\譚揚勳\AppData\Local\Microsoft\Windows\Fonts\Creative.ttc"
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

    # 回傳外接方形 Rect（供 collidepoint 命中判定使用）
    return pygame.Rect(btn_cx - BTN_R, btn_cy - BTN_R, BTN_R * 2, BTN_R * 2)

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


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
