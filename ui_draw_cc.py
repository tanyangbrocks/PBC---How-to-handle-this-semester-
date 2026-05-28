# ============================================================
#  ui_draw_cc.py -- Character creation UI
#  by refactor_ui.py
# ============================================================
import pygame
import math
import random
import os

from ui_const import *
from ui_state  import *
from ui_draw_base import *

# 拉霸機每格高度（同 _draw_cc_slot_machine 內的 TILE_H，此處提出供 _update_slot_state 使用）
_SLOT_TILE_H = 62

def _cc_ptcl_new(full_screen: bool = False) -> dict:
    """生成一顆紫色螢光粒子（orb 光球 或 wisp 光絮）。"""
    kind = "orb" if random.random() < 0.55 else "wisp"
    if full_screen:
        y0 = random.uniform(-20, WIN_H + 20)
    else:
        y0 = random.uniform(WIN_H + 10, WIN_H + 80)
    # wisp 獨有：初始角度 + 每幀角速度（±0.08–0.28 deg/frame，方向隨機）
    if kind == "wisp":
        w_angle = random.uniform(0.0, 360.0)
        w_va    = random.uniform(0.08, 0.28) * random.choice((-1, 1))
    else:
        w_angle = 0.0
        w_va    = 0.0
    return {
        "kind":     kind,
        "x":        random.uniform(-30, WIN_W + 30),
        "y":        y0,
        "vx":       random.uniform(-0.20, 0.20),
        "vy":       random.uniform(-0.58, -0.18),   # 向上飄
        "r":        (random.uniform(3.0, 6.5) if kind == "orb"
                     else random.uniform(1.5, 3.2)),
        "alpha":    random.randint(140, 225),
        "color":    random.choice(_CC_PTCL_COLORS),
        "pulse_ph": random.uniform(0, math.tau),
        "pulse_sp": random.uniform(0.018, 0.055),
        "wb_ph":    random.uniform(0, math.tau),
        "wb_sp":    random.uniform(0.008, 0.022),
        "wb_amp":   random.uniform(0.5, 1.4),
        "angle":    w_angle,   # 當前旋轉角（度）
        "va":       w_va,      # 每幀旋轉速率（度，正 = 逆時針）
    }

def _draw_cc_particles(surf: pygame.Surface, ms: int) -> None:
    """
    繪製並更新角色創建畫面的紫色螢光粒子效果。
    應在 _draw_cc_bg() 的最後（overlay 之後）呼叫。
    """
    # ── 懶初始化 ─────────────────────────────────────────────────
    if not _cc_ptcl_ready[0]:
        _cc_ptcl.clear()
        for _ in range(58):
            _cc_ptcl.append(_cc_ptcl_new(full_screen=True))
        _cc_ptcl_ready[0] = True

    # ── 每幀繪製到 SRCALPHA Surface 再合成 ───────────────────────
    pt_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

    survived: list = []
    for p in _cc_ptcl:
        # 脈動：振幅調整 alpha 與半徑
        pulse     = math.sin(ms * p["pulse_sp"] + p["pulse_ph"])
        r_draw    = max(1.0, p["r"] * (1.0 + 0.30 * pulse))
        alp       = int(p["alpha"] * (0.68 + 0.32 * (pulse + 1.0) * 0.5))
        alp       = max(0, min(255, alp))
        # 橫向飄動
        wb        = math.sin(ms * p["wb_sp"] + p["wb_ph"]) * p["wb_amp"]
        px        = int(p["x"] + wb)
        py        = int(p["y"])
        col       = p["color"]

        if p["kind"] == "orb":
            # 外層柔暈（兩圈）
            h1r = max(2, int(r_draw * 2.4))
            h2r = max(2, int(r_draw * 1.7))
            pygame.draw.circle(pt_surf, (*col, max(0, alp //  6)), (px, py), h1r)
            pygame.draw.circle(pt_surf, (*col, max(0, alp //  4)), (px, py), h2r)
            # 主光球
            pygame.draw.circle(pt_surf, (*col, alp),               (px, py), max(1, int(r_draw)))
            # 內芯白光
            core_r = max(1, int(r_draw * 0.40))
            pygame.draw.circle(pt_surf, (255, 255, 255, min(255, alp + 55)),
                               (px, py), core_r)
        else:  # wisp 光絮：細長橢圓（帶旋轉）
            ew = max(2, int(r_draw * 3))
            eh = max(4, int(r_draw * 9))
            ws = pygame.Surface((ew + 2, eh + 2), pygame.SRCALPHA)
            outer_col = (*col, max(0, alp // 3))
            inner_col = (*col, alp)
            pygame.draw.ellipse(ws, outer_col, ws.get_rect())
            ir = ws.get_rect().inflate(-2, -4)
            if ir.width > 0 and ir.height > 0:
                pygame.draw.ellipse(ws, inner_col, ir)
            # 旋轉橢圓（使用粒子本身的 angle；舊粒子無此欄位時 fallback 0）
            angle = p.get("angle", 0.0)
            if angle % 360 != 0.0:
                ws = pygame.transform.rotate(ws, angle)
            rw, rh = ws.get_size()
            pt_surf.blit(ws, (px - rw // 2, py - rh // 2))

        # ── 更新位置 + 旋轉角 ─────────────────────────────────────
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        if p["kind"] == "wisp":
            p["angle"] = (p.get("angle", 0.0) + p.get("va", 0.0)) % 360

        # 飄出螢幕（頂部 / 兩側）則丟棄
        if p["y"] < -25 or p["x"] < -55 or p["x"] > WIN_W + 55:
            survived.append(_cc_ptcl_new(full_screen=False))
        else:
            survived.append(p)

    _cc_ptcl[:] = survived
    # 補充至目標數量
    while len(_cc_ptcl) < 58:
        _cc_ptcl.append(_cc_ptcl_new(full_screen=False))

    surf.blit(pt_surf, (0, 0))

def _draw_cc_bg(surf: pygame.Surface) -> None:
    """
    在 surf 上繪製角色創建畫面的背景：
      1. 底層：WEBM 影片當前幀（按 FPS 推進，到尾自動回繞）；
         若影片未載入則退回靜態漸層。
      2. 上層：75% 不透明奶茶色→奶白色縱向漸層遮罩，
         讓 UI 卡片在影片上仍保有良好對比。
      3. 最上層：紫色螢光粒子特效（光球 + 光絮飄盪）。
    """
    # ── 底層：影片 or 靜態漸層 ───────────────────────────────
    cap = _cc_video_cap[0]
    if cap is not None:
        import cv2
        now = pygame.time.get_ticks()
        ms_per_frame = 1000.0 / max(_cc_video_fps[0], 1.0)
        if _cc_video_surf[0] is None or now - _cc_video_last[0] >= ms_per_frame:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fh, fw = frame_rgb.shape[:2]
                vsf = pygame.surfarray.make_surface(
                    frame_rgb.transpose(1, 0, 2))
                if fw != WIN_W or fh != WIN_H:
                    vsf = pygame.transform.scale(vsf, (WIN_W, WIN_H))
                _cc_video_surf[0] = vsf
                _cc_video_last[0] = now
    if _cc_video_surf[0] is not None:
        surf.blit(_cc_video_surf[0], (0, 0))
    elif "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)

    # ── 上層：奶茶↔奶白漸層遮罩（75% 不透明，懶初始化快取）──
    if _cc_overlay_surf[0] is None:
        # 奶茶色 (210,170,128) → 奶白色 (255,250,238)，alpha=191（75%）
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        top_c  = (210, 170, 128, 191)
        bot_c  = (255, 250, 238, 191)
        for _i in range(WIN_H):
            _t = _i / max(WIN_H - 1, 1)
            _r = int(top_c[0] + (bot_c[0] - top_c[0]) * _t)
            _g = int(top_c[1] + (bot_c[1] - top_c[1]) * _t)
            _b = int(top_c[2] + (bot_c[2] - top_c[2]) * _t)
            _a = int(top_c[3] + (bot_c[3] - top_c[3]) * _t)
            pygame.draw.line(ov, (_r, _g, _b, _a), (0, _i), (WIN_W - 1, _i))
        _cc_overlay_surf[0] = ov
    surf.blit(_cc_overlay_surf[0], (0, 0))

    # ── 最上層：紫色螢光粒子（疊在遮罩上、在 UI 卡片之下）──────
    _draw_cc_particles(surf, pygame.time.get_ticks())

def _draw_cc_title(surf: pygame.Surface, text: str,
                   x_center: int, base_y: int,
                   phase: float = 0.0) -> None:
    """CC 各步驟標題：Creative.ttc 34px 粗體 + 循環換色 + TV 掃描線雜訊特效。"""
    ms = pygame.time.get_ticks()
    GOLD        = (255, 185, 30)
    WHITE_T     = (255, 255, 255)
    OUTLINE_COL = (18,  8, 45)
    OUTLINE_OFF = 2

    _CREATIVE_PATH = os.path.join(os.path.dirname(__file__), "asset", "fonts", "Creative.ttc")
    _ck = "creative_34b"
    if _ck not in _extra_fonts:
        try:
            _f = pygame.font.Font(_CREATIVE_PATH, 34)
            _f.set_bold(True)
            _extra_fonts[_ck] = _f
        except Exception:
            _extra_fonts[_ck] = None
    fc = _extra_fonts.get(_ck)
    if fc is None:
        return

    N          = len(text)
    active_idx = int((ms % 1000) / 1000 * N)
    fy         = _float_offset(7, 0.00170, phase)

    ch_ws   = [fc.size(ch)[0] for ch in text]
    total_w = sum(ch_ws)
    th      = fc.get_height()

    comp = pygame.Surface((total_w + OUTLINE_OFF * 2 + 4,
                           th + OUTLINE_OFF * 2 + 4), pygame.SRCALPHA)

    # 描邊層（8 方向深紫）
    x_cur = OUTLINE_OFF + 2
    for ch, cw in zip(text, ch_ws):
        out_s = fc.render(ch, True, OUTLINE_COL)
        for ox, oy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
            comp.blit(out_s, (x_cur + ox * OUTLINE_OFF,
                              OUTLINE_OFF + 2 + oy * OUTLINE_OFF))
        x_cur += cw

    # 主文字層（循環亮金）
    x_cur = OUTLINE_OFF + 2
    for i, (ch, cw) in enumerate(zip(text, ch_ws)):
        col = GOLD if i == active_idx else WHITE_T
        comp.blit(fc.render(ch, True, col), (x_cur, OUTLINE_OFF + 2))
        x_cur += cw

    # TV 掃描線 / 色差雜訊
    rng      = random.Random(ms // 80)
    cw_, ch_ = comp.get_size()
    blit_x   = x_center - cw_ // 2
    blit_y   = int(base_y + fy)
    surf.blit(comp, (blit_x, blit_y))

    n_strips = rng.randint(0, 2)
    for _ in range(n_strips):
        sy    = rng.randint(0, max(1, ch_ - 2))
        sh_   = rng.randint(1, 3)
        dx    = rng.randint(-12, 12)
        avail = ch_ - sy
        if avail <= 0:
            continue
        ss = pygame.Surface((cw_, min(sh_, avail)), pygame.SRCALPHA)
        ss.blit(comp, (0, 0), (0, sy, cw_, sh_))
        surf.blit(ss, (blit_x + dx, blit_y + sy))

    if rng.random() < 0.25:
        ca_sf = comp.copy()
        ca_sf.set_alpha(70)
        surf.blit(ca_sf, (blit_x + rng.randint(3, 7), blit_y))


def _draw_cc_name(surf, fm, fs, mpos):
    """姓名輸入 modal 卡片，回傳「確認」按鈕 Rect。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # modal card（整張卡緩慢懸浮）
    _fy = _float_offset(amp=7, speed=0.00170, phase=0.3)
    cw, ch = 520, 250
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2 + _fy
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=20, alpha=50, offset=(0, 8))
    pygame.draw.rect(surf, PANEL, card, border_radius=20)
    pygame.draw.rect(surf, CYAN, card, 2, border_radius=20)
    # 標題
    title = fb_lg.render("請輸入角色名字", True, TITLE)
    surf.blit(title, (cx + (cw - title.get_width()) // 2, cy + 24))
    # 輸入框
    ir = pygame.Rect(cx + 30, cy + 80, cw - 60, 42)
    pygame.draw.rect(surf, MILK, ir, border_radius=10)
    t_done = fm.render(_cc_tvalue[0], True, BLACK)
    t_comp = fm.render(_cc_composing[0], True, (150, 90, 180)) if _cc_composing[0] else None
    t_cur  = fm.render("|", True, BLACK)
    xo = ir.x + 8
    surf.blit(t_done, (xo, ir.y + 6)); xo += t_done.get_width()
    if t_comp:
        surf.blit(t_comp, (xo, ir.y + 6)); xo += t_comp.get_width()
    surf.blit(t_cur, (xo, ir.y + 6))
    # 提示
    hint = fs.render("（留空則為「無名大學生」）", True, GRAY)
    surf.blit(hint, (cx + (cw - hint.get_width()) // 2, cy + 138))
    # 確認按鈕
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + 180, 140, 46)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fb_lg.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok

def _draw_cc_portrait(surf, fm, fs, mpos):
    """
    角色外觀選擇畫面（CC 第 1.5 步）。
    左：b1_1（男角），右：g1_1（女角）。
    每張卡片具備輕微懸浮動畫（相位不同）及游標滑入時流暢放大效果。
    回傳 [(base_card_rect, prefix_str), ...] 供 _handle_cc_action 使用。
    """
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)

    # ── 標題 ──────────────────────────────────────────────────
    title_y = (WIN_H - 480) // 2 - 20
    _draw_cc_title(surf, "選擇人物外觀", WIN_W // 2, title_y, phase=0.0)

    # ── 卡片基準尺寸與位置 ────────────────────────────────────
    CARD_W, CARD_H = 260, 420
    GAP            = 60
    total_w        = CARD_W * 2 + GAP
    base_x         = (WIN_W - total_w) // 2
    base_y         = (WIN_H - CARD_H) // 2 + 20
    rects_out      = []

    for i, prefix in enumerate(["b1", "g1"]):
        # ── 懸浮偏移（兩張卡相位差 1.3 rad，各自獨立飄動）────
        fy = _float_offset(amp=6, speed=0.00155, phase=i * 1.3)

        # ── 基準 Rect（用於碰撞判斷與回傳）─────────────────────
        cx     = base_x + i * (CARD_W + GAP)
        card_r = pygame.Rect(cx, base_y + fy, CARD_W, CARD_H)
        hover  = card_r.collidepoint(mpos)

        # ── 平滑 hover 縮放（_anim_hover 自動插值 0→1）──────────
        hkey   = ("cc_p", i)
        ht     = _anim_hover.get(hkey, 0.0)
        ht     = min(1.0, ht + 0.10) if hover else max(0.0, ht - 0.10)
        _anim_hover[hkey] = ht
        scale  = 1.0 + _ease_out_back(ht) * 0.055 if ht > 0 else 1.0
        dr     = _scaled_rect(card_r, scale)   # 實際繪製用 Rect

        # 投影（用放大後的 Rect）
        _soft_shadow(surf, dr, radius=18, alpha=55, offset=(0, 7))
        # 卡片底色
        bg_col = (240, 228, 210) if hover else PANEL
        pygame.draw.rect(surf, bg_col, dr, border_radius=16)
        # hover 時紫色邊框輝光（強調選中感）
        border_col = (190, 100, 255) if hover else CYAN
        border_w   = 3 if hover else 2
        pygame.draw.rect(surf, border_col, dr, border_w, border_radius=16)
        if hover and ht > 0.3:
            # 額外暈光邊框
            glow_sf = pygame.Surface((dr.width + 12, dr.height + 12), pygame.SRCALPHA)
            glow_a  = int(60 * ht)
            pygame.draw.rect(glow_sf, (190, 100, 255, glow_a),
                             glow_sf.get_rect(), border_radius=20)
            surf.blit(glow_sf, (dr.x - 6, dr.y - 6))

        # 立繪（依放大 Rect 等比縮放後底部對齊）
        img_key = f"{prefix}_1"
        img     = _portrait_scaled_load(img_key, dr.width - 16, dr.height - 20)
        if img:
            iw, ih = img.get_size()
            img_x  = dr.x + (dr.width  - iw) // 2
            img_y  = dr.y +  dr.height - 14 - ih
            surf.blit(img, (img_x, img_y))

        rects_out.append((card_r, prefix))   # 回傳基準 Rect（邏輯碰撞用）

    return rects_out

def _draw_cc_dept(surf, fm, fs, options, mpos):
    """學院格狀卡片（4 欄），回傳各卡 (Rect, 1-based idx) 列表。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 格狀版型參數 ───────────────────────────────────────────
    COLS      = 4
    cw, ch    = 196, 64
    gap_x     = 14
    gap_y     = 12
    n         = len(options)
    n_rows    = (n + COLS - 1) // COLS
    label_h   = fm.get_height() + 22   # pad_y=11 × 2
    TITLE_GAP = 24
    grid_h    = n_rows * ch + (n_rows - 1) * gap_y
    total_h   = label_h + TITLE_GAP + grid_h
    top_y     = (WIN_H - total_h) // 2
    grid_y    = top_y + label_h + TITLE_GAP
    _draw_cc_title(surf, "選擇學院", WIN_W // 2, top_y, phase=0.0)
    rects = []
    for i, opt in enumerate(options):
        row = i // COLS
        col = i %  COLS
        # 最後一行若不滿 COLS，整排置中
        row_start = row * COLS
        row_end   = min(row_start + COLS, n)
        row_cnt   = row_end - row_start
        row_w     = row_cnt * cw + (row_cnt - 1) * gap_x
        sx        = (WIN_W - row_w) // 2
        rx        = sx + col * (cw + gap_x)
        ry        = grid_y + row * (ch + gap_y)
        r         = pygame.Rect(rx, ry, cw, ch)
        hover     = r.collidepoint(mpos)
        dr        = _premium_btn(surf, r, (255, 248, 238), hover, radius=16)
        t         = fb_lg.render(opt, True, WHITE)
        surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                      dr.y + (dr.height - t.get_height()) // 2))
        rects.append((r, i + 1))
    return rects

def _draw_cc_drawbacks(surf, fm, fs, drawbacks, sel_indices, max_sel, mpos):
    """負面特質切換卡片，回傳 (card_rects, confirm_btn_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch = 250, 190
    gap           = 24
    title_h       = fm.get_height() + 22   # pad_y=11 × 2
    sub_h         = fs.get_height() + 12   # pad_y=6 × 2
    TITLE_SUB_GAP = 12
    SUB_CARD_GAP  = 18
    CARD_BTN_GAP  = 30
    btn_h         = 48
    total_h       = title_h + TITLE_SUB_GAP + sub_h + SUB_CARD_GAP + ch + CARD_BTN_GAP + btn_h
    top_y         = (WIN_H - total_h) // 2
    sub_y         = top_y + title_h + TITLE_SUB_GAP
    sy            = sub_y + sub_h + SUB_CARD_GAP

    _draw_cc_title(surf, "選擇負面特質", WIN_W // 2, top_y, phase=0.5)
    sub_text  = f"（最多選 {max_sel} 個，選取可獲得額外點數）"
    _fy_sub   = _float_offset(7, 0.00170, 0.5)
    sub_s     = fs.render(sub_text, True, WHITE)
    surf.blit(sub_s, (WIN_W // 2 - sub_s.get_width() // 2,
                      sub_y + _fy_sub + (sub_h - sub_s.get_height()) // 2))

    total_w = len(drawbacks) * cw + (len(drawbacks) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    for i, d in enumerate(drawbacks):
        selected = i in sel_indices
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        # 底色：選中用暖羊皮紙（比米白深一點但仍是淺色），未選中用對話框主體米白
        bg_col   = (238, 210, 170) if selected else (255, 248, 238)
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        # 已選：加琥珀外框強調
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        # name（深棕文字在淺底上高對比，選中/未選中一致）
        nt = fb_lg.render(d["name"], True, WHITE)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 14))
        # desc (wrap)
        desc_lines = _wrap(d["desc"], fs, cw - 20)
        for li, dl in enumerate(desc_lines):
            dt = fs.render(dl, True, WHITE)
            surf.blit(dt, (dr.x + 10, dr.y + 52 + li * (fs.get_height() + 3)))
        # bonus pts
        pt = fs.render(f"＋{d['bonus_pts']} 點", True, GREEN)
        surf.blit(pt, (dr.x + (dr.width - pt.get_width()) // 2, dr.y + ch - 38))
        card_rects.append((r, i))
    # 確認按鈕
    ok    = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return card_rects, ok

def _draw_cc_stats(surf, fm, fs, total, base, talent, vals, raw, active, mpos, de_level=None):
    """能力點分配畫面，回傳 (minus_rects, plus_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    btn_sz       = 38
    box_w, box_h = 90, 38
    title_h      = fm.get_height() + 22   # pad_y=11 × 2
    sub_h        = fs.get_height() + 12   # pad_y=6 × 2
    TITLE_SUB_GAP = 12
    SUB_ROW_GAP  = 22
    ROW_GAP      = 14
    ROWS_BTN_GAP = 26
    btn_h        = 48
    n_rows       = 3
    rows_h       = n_rows * box_h + (n_rows - 1) * ROW_GAP
    # 在三個能力列下方留 ROW_GAP + box_h 給「可用時間」顯示列
    total_h      = title_h + TITLE_SUB_GAP + sub_h + SUB_ROW_GAP + rows_h + ROW_GAP + box_h + ROWS_BTN_GAP + btn_h
    top_y        = (WIN_H - total_h) // 2
    sub_y        = top_y + title_h + TITLE_SUB_GAP
    row_start_y  = sub_y + sub_h + SUB_ROW_GAP
    row_y        = [row_start_y + i * (box_h + ROW_GAP) for i in range(n_rows)]
    bt_y         = row_y[-1] + box_h + ROW_GAP   # 可用時間顯示列（運氣行正下方）
    ok_y         = bt_y + box_h + ROWS_BTN_GAP

    used = sum(vals)
    rem  = total - used
    _draw_cc_title(surf, "分配能力點", WIN_W // 2, top_y, phase=1.0)
    bonus = total - base
    pts_label = f"{base}(+{bonus})" if bonus > 0 else str(total)
    info_text = f"可用點數：{pts_label}   已用：{used}   剩餘：{rem}   初始金錢 +{rem * 10} 元"
    # 直接渲染文字（粗體，與標籤同色，移除半透明遮罩底板）
    _fy_info = _float_offset(7, 0.00170, 1.0)
    info_s   = fb_lg.render(info_text, True, WHITE)
    surf.blit(info_s, (WIN_W // 2 - info_s.get_width() // 2,
                       sub_y + _fy_info + (sub_h - info_s.get_height()) // 2))

    labels      = ["體力", "智力", "運氣"]
    talent_keys = ["stamina", "intel", "luck"]
    minus_rects = []
    plus_rects  = []

    # ── 水平置中：計算整排（標籤＋[-]＋輸入框＋[+]）的起始 x ──
    GAP_LC   = 16   # 標籤右緣 → [-] 左緣
    GAP_BX   = 10   # [-] 右緣 → 輸入框左緣
    GAP_XP   = 12   # 輸入框右緣 → [+] 左緣
    GAP_PA   = 12   # [+] 右緣 → 加成標注左緣
    label_w  = max(fb_lg.size(l)[0] for l in labels)
    group_w  = label_w + GAP_LC + btn_sz + GAP_BX + box_w + GAP_XP + btn_sz
    row_left = (WIN_W - group_w) // 2
    minus_x  = row_left + label_w + GAP_LC
    input_x  = minus_x + btn_sz + GAP_BX
    plus_x   = input_x + box_w + GAP_XP
    ann_x    = plus_x  + btn_sz + GAP_PA

    # 更新輸入框 Rect 快取（與事件處理對齊）
    _cc_btn_cache["stats_boxes"] = [pygame.Rect(input_x, ry, box_w, box_h) for ry in row_y]

    for i, (label, ry) in enumerate(zip(labels, row_y)):
        # 標籤（右對齊至 [-] 左緣，讓三行整齊）
        lt   = fb_lg.render(label, True, WHITE)
        lt_x = row_left + label_w - lt.get_width()
        surf.blit(lt, (lt_x, ry + (box_h - lt.get_height()) // 2))
        # [-]
        mr    = pygame.Rect(minus_x, ry, btn_sz, btn_sz)
        hover = mr.collidepoint(mpos)
        mr_dr = _premium_btn(surf, mr, BTN_N, hover, radius=10)
        mt    = fb_lg.render("－", True, WHITE)
        surf.blit(mt, (mr_dr.x + (mr_dr.width  - mt.get_width())  // 2,
                       mr_dr.y + (mr_dr.height - mt.get_height()) // 2))
        minus_rects.append(mr)
        # 輸入框（帶焦點高光陰影）
        bdr_col = YELLOW if active == i else CYAN
        ir      = pygame.Rect(input_x, ry, box_w, box_h)
        if active == i:
            _soft_shadow(surf, ir, radius=10, alpha=35, offset=(1, 2), spread=3)
        pygame.draw.rect(surf, MILK, ir, border_radius=10)
        pygame.draw.rect(surf, bdr_col, ir, 2, border_radius=10)
        display = raw[i] if active == i else str(vals[i])
        vt = fm.render(display, True, BLACK)
        surf.blit(vt, (ir.x + (box_w - vt.get_width()) // 2,
                       ir.y + (box_h - vt.get_height()) // 2))
        # [+]
        pr    = pygame.Rect(plus_x, ry, btn_sz, btn_sz)
        hover = pr.collidepoint(mpos)
        pr_dr = _premium_btn(surf, pr, BTN_N, hover, radius=10)
        pt    = fb_lg.render("＋", True, WHITE)
        surf.blit(pt, (pr_dr.x + (pr_dr.width  - pt.get_width())  // 2,
                       pr_dr.y + (pr_dr.height - pt.get_height()) // 2))
        plus_rects.append(pr)
        # 加成標注：（+N）與按鈕等高（btn_sz），綠色
        t_bonus     = (talent   or {}).get(talent_keys[i], 0)
        dl_bonus    = (de_level or {}).get(talent_keys[i], 0)
        total_bonus = t_bonus + dl_bonus
        if total_bonus:
            sign    = "+" if total_bonus > 0 else ""
            ann_txt = f"({sign}{total_bonus})"          # 半形括號
            ann_col = GREEN if total_bonus > 0 else (200, 80, 80)
            ann_s   = fb_lg.render(ann_txt, True, ann_col)   # 粗體，直接渲染
            surf.blit(ann_s, (ann_x,
                              ry + (btn_sz - ann_s.get_height()) // 2))

    # ── 可用時間顯示列（對齊運氣行下方，與能力值同字體格式）────
    bt_talent = (talent   or {}).get("base_time", 0)
    bt_de     = (de_level or {}).get("base_time", 0)
    bt_total  = bt_talent + bt_de
    # 標籤（右對齊至 minus_x，與體力/智力/運氣標籤對齊）
    bt_lt = fb_lg.render("可用時間", True, WHITE)
    surf.blit(bt_lt, (row_left + label_w - bt_lt.get_width(),
                      bt_y + (box_h - bt_lt.get_height()) // 2))
    # 數值「10」：水平置中於輸入框欄（對齊上方三列的數字）
    bt_num = fb_lg.render("10", True, WHITE)
    surf.blit(bt_num, (input_x + (box_w - bt_num.get_width()) // 2,
                       bt_y + (box_h - bt_num.get_height()) // 2))
    # 加成括弧（+N）：從 ann_x 起，對齊上方加成標注欄
    if bt_total:
        sign   = "+" if bt_total > 0 else ""
        bt_ann = f"({sign}{bt_total})"                       # 半形括號
        bt_col = GREEN if bt_total > 0 else (200, 80, 80)
        bt_s   = fb_lg.render(bt_ann, True, bt_col)          # 粗體，直接渲染
        surf.blit(bt_s, (ann_x,
                         bt_y + (box_h - bt_s.get_height()) // 2))

    # 確認
    ok          = pygame.Rect((WIN_W - 160) // 2, ok_y, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = rem >= 0
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fb_lg.render("確認分配", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return minus_rects, plus_rects, ok

def _draw_cc_talent(surf, fm, fs, candidates, sel_idx, mpos):
    """天賦卡片（單選），回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch = 250, 200
    gap          = 24
    label_h      = fm.get_height() + 22   # pad_y=11 × 2
    TITLE_GAP    = 28
    CARD_BTN_GAP = 30
    btn_h        = 48
    total_h      = label_h + TITLE_GAP + ch + CARD_BTN_GAP + btn_h
    top_y        = (WIN_H - total_h) // 2
    sy           = top_y + label_h + TITLE_GAP

    _draw_cc_title(surf, "選擇天賦", WIN_W // 2, top_y, phase=1.5)

    total_w = len(candidates) * cw + (len(candidates) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    for i, t_data in enumerate(candidates):
        selected = (i == sel_idx)
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        # 底色：選中用稍深一階的暖金，未選中用淺暖金（深色文字在兩者上均清晰）
        bg_col   = (200, 155, 75) if selected else (225, 180, 100)
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        # 名稱（深棕，在調淡底色上清晰可讀）
        nt = fb_lg.render(t_data["name"], True, WHITE)
        # ── 垂直 + 水平置中：名稱 + 間距 + 說明行 ────────────────────
        desc_lines = _wrap(t_data["desc"], fs, cw - 20)
        lh      = fs.get_height() + 4
        block_h = fb_lg.get_height() + 12 + len(desc_lines) * lh
        name_y  = dr.y + (dr.height - block_h) // 2
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, name_y))
        desc_y = name_y + fb_lg.get_height() + 12
        for li, dl in enumerate(desc_lines):
            dt = fs.render(dl, True, WHITE)
            surf.blit(dt, (dr.x + (dr.width - dt.get_width()) // 2,
                           desc_y + li * lh))
        card_rects.append((r, i))
    # 確認按鈕
    ok          = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = sel_idx is not None
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return card_rects, ok

def _draw_cc_de_level(surf, fm, fs, levels, sel_idx, mpos):
    """年級卡片（單選），回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    # ── 垂直置中計算 ──────────────────────────────────────────
    cw, ch    = 180, 200
    gap       = 20
    title_h   = fm.get_height() + 22
    TITLE_GAP = 28
    CARD_BTN  = 30
    btn_h     = 48
    total_h   = title_h + TITLE_GAP + ch + CARD_BTN + btn_h
    top_y     = (WIN_H - total_h) // 2
    sy        = top_y + title_h + TITLE_GAP

    _draw_cc_title(surf, "選擇年級", WIN_W // 2, top_y, phase=2.0)

    total_w = len(levels) * cw + (len(levels) - 1) * gap
    sx = (WIN_W - total_w) // 2
    card_rects = []
    buff_labels = [
        ("可用時間加成", "base_time"),
        ("智力",         "intel"),
        ("運氣",         "luck"),
    ]
    for i, lv in enumerate(levels):
        selected = (i == sel_idx)
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected
        # 底色：選中用暖羊皮紙（比米白深一點但仍是淺色），未選中用對話框主體米白
        bg_col   = (238, 210, 170) if selected else (255, 248, 238)
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        # 年級名稱（深棕色文字，在米白或橙棕底上皆清晰可讀）
        nt = fb_lg.render(lv["name"], True, WHITE)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 18))
        # buff 列表
        by = dr.y + 60
        for bl, bk in buff_labels:
            val = lv.get(bk, 0)
            sign = "+" if val >= 0 else ""
            color = GREEN if val > 0 else (GRAY if val == 0 else (200, 80, 80))
            bt = fs.render(f"{bl} {sign}{val}", True, color)
            surf.blit(bt, (dr.x + (dr.width - bt.get_width()) // 2, by))
            by += fs.get_height() + 5
        card_rects.append((r, i))

    ok          = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN, 160, btn_h)
    hover       = ok.collidepoint(mpos)
    can_confirm = sel_idx is not None
    ok_col      = BTN_N if can_confirm else DARK_GRAY
    ok_dr       = _premium_btn(surf, ok, ok_col, hover and can_confirm, radius=14)
    t           = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (ok_dr.x + (ok_dr.width  - t.get_width())  // 2,
                  ok_dr.y + (ok_dr.height - t.get_height()) // 2))
    return card_rects, ok

def _draw_cc_extra_events(surf, fm, fs, mpos):
    """額外事件選擇卡片，回傳 (card_rects, confirm_rect)。"""
    fb_lg = _font_bold_lg[0] or fm
    _draw_cc_bg(surf)
    now = pygame.time.get_ticks()

    cw, ch         = 220, 200
    gap            = 22
    title_h        = fm.get_height() + 22
    TITLE_SUB_GAP  = 12
    sub_h          = fs.get_height() + 12
    SUB_CARD_GAP   = 18
    CARD_BTN_GAP   = 30
    btn_h          = 48
    total_h = title_h + TITLE_SUB_GAP + sub_h + SUB_CARD_GAP + ch + CARD_BTN_GAP + btn_h
    top_y = (WIN_H - total_h) // 2
    sub_y = top_y + title_h + TITLE_SUB_GAP
    sy    = sub_y + sub_h + SUB_CARD_GAP

    _draw_cc_title(surf, "選擇額外事件", WIN_W // 2, top_y, phase=4.0)
    # 直接渲染說明文字（與確認選擇按鈕同色，移除半透明遮罩底板）
    _fy_sub = _float_offset(7, 0.00170, 4.0)
    sub_s   = fs.render("（可複選社團；打工與家教只能擇一；不選可直接確認）", True, WHITE)
    surf.blit(sub_s, (WIN_W // 2 - sub_s.get_width() // 2,
                      sub_y + _fy_sub + (sub_h - sub_s.get_height()) // 2))

    events = _cc_extra_data or []
    intel  = _cc_extra_intel[0]
    total_w = len(events) * cw + (len(events) - 1) * gap
    sx      = (WIN_W - total_w) // 2
    card_rects = []

    for i, ev in enumerate(events):
        ev_id    = ev["id"]
        selected = ev_id in _cc_extra_sel
        disabled = ev.get("intel_req", 0) > intel
        r        = pygame.Rect(sx + i * (cw + gap), sy, cw, ch)
        hover    = r.collidepoint(mpos) and not selected and not disabled
        # 底色：停用深棕、選中暖羊皮紙、未選中用對話框米白
        bg_col   = (50, 35, 20) if disabled else ((238, 210, 170) if selected else (255, 248, 238))
        dr       = _premium_btn(surf, r, bg_col, hover, radius=16)
        if selected:
            pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
        name_col = GRAY if disabled else WHITE  # 深棕文字在淺底上高對比，選中/未選中一致
        nt = fb_lg.render(ev["name"], True, name_col)
        surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, dr.y + 14))
        tc = ev.get("time_cost", 0)
        tc_col = GRAY if disabled else (RED if tc > 0 else GREEN)
        tc_t = fs.render(f"每週時間 -{tc}" if tc > 0 else "不佔時間", True, tc_col)
        surf.blit(tc_t, (dr.x + (dr.width - tc_t.get_width()) // 2, dr.y + 60))
        md = ev.get("money_delta", 0)
        md_col = GRAY if disabled else (GREEN if md > 0 else RED)
        sign = "+" if md >= 0 else ""
        md_t = fs.render(f"每週金錢 {sign}{md}", True, md_col)
        surf.blit(md_t, (dr.x + (dr.width - md_t.get_width()) // 2, dr.y + 90))
        ir = ev.get("intel_req", 0)
        if ir > 0:
            req_col = GRAY if disabled else (GREEN if intel >= ir else RED)
            req_t = fs.render(f"需要智力 ≥ {ir}", True, req_col)
            surf.blit(req_t, (dr.x + (dr.width - req_t.get_width()) // 2, dr.y + 126))
        if not disabled:
            card_rects.append((r, ev_id))

    # ── 互斥警告（右側浮動提示）──────────────────────────────
    warn_elapsed = now - _cc_extra_warn[0]
    if _cc_extra_warn[0] > 0 and warn_elapsed < 2200:
        if warn_elapsed < 280:
            w_alpha = int(255 * warn_elapsed / 280)
        elif warn_elapsed > 1700:
            w_alpha = int(255 * (2200 - warn_elapsed) / 500)
        else:
            w_alpha = 255
        w_alpha = max(0, min(255, w_alpha))
        wt    = fs.render("打工和家教只能二擇一", True, (255, 215, 60))
        ww    = wt.get_width() + 24
        wh    = wt.get_height() + 14
        wx    = WIN_W - ww - 18
        wy    = WIN_H // 2 - wh // 2
        ws    = pygame.Surface((ww, wh), pygame.SRCALPHA)
        pygame.draw.rect(ws, (40, 18, 8, min(220, w_alpha)), (0, 0, ww, wh), border_radius=8)
        pygame.draw.rect(ws, (*[min(255, int(c * w_alpha / 255)) for c in (235, 130, 30)], w_alpha),
                         (0, 0, ww, wh), 2, border_radius=8)
        surf.blit(ws, (wx, wy))
        wt_s = pygame.Surface(wt.get_size(), pygame.SRCALPHA)
        wt_s.blit(wt, (0, 0))
        wt_s.set_alpha(w_alpha)
        surf.blit(wt_s, (wx + 12, wy + 7))

    ok    = pygame.Rect((WIN_W - 160) // 2, sy + ch + CARD_BTN_GAP, 160, btn_h)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fb_lg.render("確認選擇", True, WHITE)
    surf.blit(t, (dr.x + (dr.width - t.get_width()) // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return card_rects, ok

def _draw_cc_summary(surf, fm, fs, mpos, game_mode=False):
    """
    玩家資訊一覽卡片（分區佈局版）。
    game_mode=False: CC 結束確認，回傳 (start_btn_rect, restart_btn_rect)。
    game_mode=True : 遊戲中查閱，回傳 (close_btn_rect, None)。
    """
    fb    = _font_bold[0]    or fs
    fb_lg = _font_bold_lg[0] or fm
    data  = _cc_summary_data[0]

    # ── 背景 ────────────────────────────────────────────────────
    if game_mode:
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surf.blit(ov, (0, 0))
    else:
        _draw_cc_bg(surf)

    # ── 外卡片 ──────────────────────────────────────────────────
    cw = 700; ch = 500
    cx = (WIN_W - cw) // 2; cy = (WIN_H - ch) // 2

    sh = pygame.Surface((cw + 8, ch + 8), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 55), (0, 0, cw + 8, ch + 8), border_radius=20)
    surf.blit(sh, (cx + 4, cy + 4))

    card_s = pygame.Surface((cw, ch), pygame.SRCALPHA)
    pygame.draw.rect(card_s, (255, 245, 228, 248), (0, 0, cw, ch), border_radius=18)
    surf.blit(card_s, (cx, cy))
    pygame.draw.rect(surf, CYAN, pygame.Rect(cx, cy, cw, ch), 2, border_radius=18)

    # ── 標題 ────────────────────────────────────────────────────
    ts = fb_lg.render("玩家資訊一覽", True, TITLE)
    surf.blit(ts, (cx + (cw - ts.get_width()) // 2, cy + 14))
    pygame.draw.line(surf, (210, 185, 155),
                     (cx + 20, cy + 46), (cx + cw - 20, cy + 46), 1)

    # ── 共用 helpers ─────────────────────────────────────────────
    _IC_BG  = (240, 218, 190, 210)
    _IC_BDR = (195, 165, 125)
    _IC_R   = 12
    GAP     = 10

    def _inner_card(rect):
        s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(s, _IC_BG, (0, 0, rect.width, rect.height),
                         border_radius=_IC_R)
        surf.blit(s, rect.topleft)
        pygame.draw.rect(surf, _IC_BDR, rect, 1, border_radius=_IC_R)

    def _small_chip(rect, text, font, bg, fg):
        pygame.draw.rect(surf, bg, rect, border_radius=8)
        t = font.render(text, True, fg)
        surf.blit(t, (rect.x + (rect.width  - t.get_width())  // 2,
                      rect.y + (rect.height - t.get_height()) // 2))

    def _section_card(rect, title, items, row_fn):
        """子卡片：標題列 + 列表（無背景框）。row_fn(item) -> (text, color)"""
        lbl = fb.render(title, True, TITLE)
        surf.blit(lbl, (rect.x + 10, rect.y + 8))
        iy = rect.y + 8 + lbl.get_height() + 5
        if items:
            for item in items:
                text, col = row_fn(item)
                if iy + fs.get_height() > rect.bottom - 6:
                    break
                surf.blit(fs.render(text, True, col), (rect.x + 12, iy))
                iy += fs.get_height() + 3
        else:
            surf.blit(fs.render("（無）", True, GRAY), (rect.x + 12, iy))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 上方區  cy+60 ~ cy+210  (h=150)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    UP_Y = cy + 60;  UP_H = 150
    L_W  = 290

    # ── 左卡（頭像 + 學院 / 年級 + 姓名 chip）────────────────────
    l_rect = pygame.Rect(cx + 20, UP_Y, L_W, UP_H)

    portrait_r = 44
    p_cx = cx + 20 + 16 + portrait_r
    p_cy = UP_Y + 15 + portrait_r

    prefix = _portrait_prefix[0]
    head_s = _portrait_head_load(prefix) if prefix else None
    if head_s is not None:
        d = portrait_r * 2
        surf.blit(pygame.transform.smoothscale(head_s, (d, d)),
                  (p_cx - portrait_r, p_cy - portrait_r))
    else:
        pygame.draw.circle(surf, (200, 90, 90),  (p_cx, p_cy), portrait_r)
        pygame.draw.circle(surf, (230, 140, 110), (p_cx, p_cy), portrait_r, 3)

    tag_x = p_cx + portrait_r + 14
    # 學院（純文字）
    dept_s = fb.render(data.get("department", ""), True, TITLE)
    surf.blit(dept_s, (tag_x, UP_Y + 26))
    # 年級（純文字）
    de_s = fb.render(data.get("de_level", {}).get("name", ""), True, TITLE)
    surf.blit(de_s, (tag_x, UP_Y + 26 + dept_s.get_height() + 12))

    # 姓名（純文字，左下角）
    name_str = data.get("name", "")
    nm_s = fb.render(name_str, True, TITLE)
    surf.blit(nm_s, (cx + 20 + 14, UP_Y + UP_H - nm_s.get_height() - 14))

    # ── 右卡（能力值 2 × 2 chips）────────────────────────────────
    R_X = cx + 20 + L_W + GAP
    R_W = cw - 20 - L_W - GAP - 20        # = 360

    raw_sta = data.get("stamina", 0)
    raw_int = data.get("intel",   0)
    raw_lck = data.get("luck",    0)
    money   = data.get("money",   0)
    ct      = data.get("combined_talent", {})
    dl      = data.get("de_level", {})

    if not game_mode:
        sta_v = raw_sta + ct.get("stamina", 0)
        int_v = raw_int + ct.get("intel",   0) + dl.get("intel", 0)
        lck_v = raw_lck + ct.get("luck",    0) + dl.get("luck",  0)
    else:
        sta_v = raw_sta; int_v = raw_int; lck_v = raw_lck

    # 能力值純文字（兩欄）
    _sv_y1 = UP_Y + 38
    _sv_y2 = _sv_y1 + fb.get_height() + 18
    _sv_c1 = R_X + 20
    _sv_c2 = R_X + R_W // 2 + 10

    for _sx, _sy, _lbl, _val, _vcol in [
        (_sv_c1, _sv_y1, "體力", sta_v, WHITE),
        (_sv_c2, _sv_y1, "智力", int_v, WHITE),
        (_sv_c1, _sv_y2, "運氣", lck_v, WHITE),
        (_sv_c2, _sv_y2, "金錢", money, YELLOW),
    ]:
        _ls = fs.render(f"{_lbl}：", True, GRAY)
        _vs = fb.render(str(_val),  True, _vcol)
        surf.blit(_ls, (_sx, _sy))
        surf.blit(_vs, (_sx + _ls.get_width(), _sy))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 中間區  cy+220 ~ cy+328  (h=108)  天賦 | 負面特質
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    MID_Y  = cy + 220;  MID_H  = 108
    HALF_W = (cw - 20 - 20 - GAP) // 2    # = 325

    slots     = data.get("slot_results", [])
    drawbacks = data.get("drawbacks",    [])

    _indexed_slots = [dict({"_i": i + 1}, **t) for i, t in enumerate(slots)]
    _section_card(
        pygame.Rect(cx + 20, MID_Y, HALF_W, MID_H),
        "天賦", _indexed_slots,
        lambda t: (
            f"槽{t['_i']}：{t.get('name', '')}" +
            (f"：{t.get('desc', '')}" if t.get("desc") else ""),
            GRAY if t.get("name") == "無天賦" else WHITE,
        )
    )
    _section_card(
        pygame.Rect(cx + 20 + HALF_W + GAP, MID_Y, HALF_W, MID_H),
        "負面特質", drawbacks,
        lambda db: (
            db.get("name", "") + ("：" + db.get("desc", "") if db.get("desc") else ""),
            RED,
        )
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 下方區  cy+338 ~ cy+460  (h=122)  額外事件 | 按鈕
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    BOT_Y = cy + 338;  BOT_H = 122

    ev_ids  = data.get("extra_ev_ids",  [])
    ev_map  = {e["id"]: e for e in data.get("extra_ev_data", [])}
    ev_list = []
    for eid in ev_ids:
        ev = ev_map.get(eid)
        if not ev:
            continue
        desc = ev.get("desc", "")
        if not desc:
            tc = ev.get("time_cost",   0)
            md = ev.get("money_delta", 0)
            parts = []
            if tc > 0:  parts.append(f"每週時間 -{tc}")
            if md != 0: parts.append(f"每週金錢 {'+' if md >= 0 else ''}{md}")
            desc = "，".join(parts)
        full_txt = ev["name"] + ("：" + desc if desc else "")
        for line in full_txt.split("\n"):
            ev_list.append({"_txt": line})

    _section_card(
        pygame.Rect(cx + 20, BOT_Y, HALF_W, BOT_H),
        "額外事件", ev_list,
        lambda e: (e["_txt"], WHITE)
    )

    # ── 按鈕 ─────────────────────────────────────────────────────
    BTN_X = cx + 20 + HALF_W + GAP
    BTN_W = HALF_W

    def _summ_btn(rect, label, bg):
        dr = _premium_btn(surf, rect, bg, rect.collidepoint(mpos), radius=12)
        t  = fb_lg.render(label, True, PANEL)
        surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                      dr.y + (dr.height - t.get_height()) // 2))

    if game_mode:
        close_r = pygame.Rect(BTN_X, BOT_Y + (BOT_H - 44) // 2, BTN_W, 44)
        _summ_btn(close_r, "關閉", BTN_N)
        return close_r, None
    else:
        restart_r = pygame.Rect(BTN_X, BOT_Y + 14,          BTN_W, 44)
        start_r   = pygame.Rect(BTN_X, BOT_Y + 14 + 44 + 14, BTN_W, 44)
        _summ_btn(restart_r, "重新創建角色", (115, 75, 40))
        _summ_btn(start_r,   "進入本學期",   BTN_N)
        return start_r, restart_r

def _spawn_confetti():
    """在畫面上方噴射 80 顆彩帶粒子。"""
    for _ in range(80):
        _cc_confetti.append({
            "x":  random.uniform(0, WIN_W),
            "y":  random.uniform(-60, -5),
            "vx": random.uniform(-3.5, 3.5),
            "vy": random.uniform(-9, -3),
            "color": random.choice(_CONFETTI_COLORS),
            "life": random.randint(55, 110),
            "max_life": 110,
            "w": random.randint(6, 13),
            "h": random.randint(4, 8),
        })

def _update_confetti(surf):
    """更新並繪製所有彩帶粒子；自動清除已結束的粒子。"""
    keep = []
    for p in _cc_confetti:
        p["vy"] += 0.35
        p["x"]  += p["vx"]
        p["y"]  += p["vy"]
        p["life"] -= 1
        if p["life"] > 0 and p["y"] < WIN_H + 20:
            alpha = min(255, int(255 * p["life"] / p["max_life"]))
            ps = pygame.Surface((p["w"], p["h"]), pygame.SRCALPHA)
            ps.fill((*p["color"], alpha))
            surf.blit(ps, (int(p["x"]), int(p["y"])))
            keep.append(p)
    _cc_confetti[:] = keep

def _calc_slot_target(i: int) -> int:
    """計算第 i 槽的捲動終點（px），使結果天賦剛好停在卡片垂直中央。
    推導：card_h=230, TILE_H=62
      center_row = (230//2 + 0) // 62 = 1
      => first_tile_idx = (result_idx - 1) % n_pool
      => target = (3*n_pool + first_tile_idx) * TILE_H
    """
    n    = len(_SLOT_SPIN_NAMES)
    res  = _slot_results[i]
    name = res.get("name", "") if res else ""
    ridx = _SLOT_SPIN_NAMES.index(name) if name in _SLOT_SPIN_NAMES else 0
    ftidx = (ridx - 1) % n
    return (3 * n + ftidx) * _SLOT_TILE_H

def _update_slot_state(now):
    """每幀推進拉霸機動畫狀態。"""
    for i in range(3):
        phase = _slot_phase[i]
        if phase == "idle":
            if i > 0 and _slot_phase[i - 1] == "done" \
                    and now - _slot_stop_t[i - 1] >= _SLOT_DELAY_MS:
                _slot_phase[i]   = "spinning"
                _slot_start_t[i] = now
                _slot_target_offsets[i] = _calc_slot_target(i)
        elif phase == "spinning":
            if now - _slot_start_t[i] >= _SLOT_SPIN_MS:
                _slot_phase[i]  = "done"
                _slot_stop_t[i] = now
                result = _slot_results[i]
                if result and result.get("name") != "無天賦":
                    _spawn_confetti()
                    _cc_shake_end[0] = now + 400

def _draw_cc_slot_machine(surf, fm, fs, mpos):
    """拉霸機天賦動畫畫面，回傳「繼續」按鈕 Rect 或 None（尚未完成時）。"""
    fb_lg = _font_bold_lg[0] or fm
    now   = pygame.time.get_ticks()
    _update_slot_state(now)
    _draw_cc_bg(surf)

    # ── 彩帶 ─────────────────────────────────────────────────
    _update_confetti(surf)

    # ── 震動偏移 ──────────────────────────────────────────────
    if now < _cc_shake_end[0]:
        t_rem    = _cc_shake_end[0] - now
        amp      = max(0, int(7 * t_rem / 400))
        shake_dx = random.randint(-amp, amp)
        shake_dy = random.randint(-amp // 2, amp // 2)
    else:
        shake_dx = shake_dy = 0

    # ── 佈局 ──────────────────────────────────────────────────
    cw, ch     = 210, 230
    TILE_H     = _SLOT_TILE_H
    gap        = 22
    title_h    = fm.get_height() + 22
    TITLE_GAP  = 28
    SLOT_BTN   = 32
    btn_h      = 48
    total_h    = title_h + TITLE_GAP + ch + SLOT_BTN + btn_h
    top_y      = (WIN_H - total_h) // 2
    sy         = top_y + title_h + TITLE_GAP
    total_w    = 3 * cw + 2 * gap
    sx         = (WIN_W - total_w) // 2

    _draw_cc_title(surf, "抽取天賦", WIN_W // 2 + shake_dx, top_y + shake_dy, phase=3.0)

    all_done = all(p == "done" for p in _slot_phase)

    for i in range(3):
        r     = pygame.Rect(sx + i * (cw + gap) + shake_dx, sy + shake_dy, cw, ch)
        phase = _slot_phase[i]

        if phase == "idle":
            dr = _premium_btn(surf, r, (255, 245, 225), False, radius=16)
            pygame.draw.rect(surf, (200, 175, 135), dr, 2, border_radius=16)
            q  = fb_lg.render("?", True, TITLE)
            surf.blit(q, (dr.x + (dr.width - q.get_width()) // 2,
                          dr.y + (dr.height - q.get_height()) // 2))

        elif phase == "spinning":
            dr       = _premium_btn(surf, r, (255, 250, 240), False, radius=16)

            elapsed  = now - _slot_start_t[i]
            t_frac   = min(1.0, elapsed / _SLOT_SPIN_MS)
            ease     = 1 - (1 - t_frac) ** 4          # ease-out quart
            offset   = int(_slot_target_offsets[i] * ease)

            n_pool         = len(_SLOT_SPIN_NAMES)
            first_tile_idx = (offset // TILE_H) % n_pool
            pixel_shift    = offset % TILE_H
            center_row     = (dr.height // 2 + pixel_shift) // TILE_H

            surf.set_clip(dr)
            n_draw = dr.height // TILE_H + 2
            for row in range(n_draw):
                ty   = dr.y - pixel_shift + row * TILE_H
                if ty >= dr.bottom:
                    break
                name = _SLOT_SPIN_NAMES[(first_tile_idx + row) % n_pool]
                if row == center_row:
                    hl = pygame.Surface((dr.width - 4, TILE_H), pygame.SRCALPHA)
                    hl.fill((255, 205, 80, 100))
                    surf.blit(hl, (dr.x + 2, ty))
                if row > 0:
                    pygame.draw.line(surf, (210, 185, 145),
                                     (dr.x + 12, ty), (dr.x + dr.width - 12, ty))
                nt = fb_lg.render(name, True, TITLE)
                surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2,
                               ty + (TILE_H - nt.get_height()) // 2))
            surf.set_clip(None)

            # ── 上下漸層遮罩（景深感）─────────────────────────────
            fade_h = 44
            fk = ("slot_fade_top", dr.width, fade_h)
            if fk not in _grads:
                fg = pygame.Surface((dr.width, fade_h), pygame.SRCALPHA)
                for j in range(fade_h):
                    a = int(230 * ((fade_h - j) / fade_h) ** 2)
                    pygame.draw.line(fg, (255, 250, 240, a),
                                     (0, j), (dr.width - 1, j))
                _grads[fk] = fg
            surf.blit(_grads[fk], (dr.x, dr.y))
            fk2 = ("slot_fade_bot", dr.width, fade_h)
            if fk2 not in _grads:
                _grads[fk2] = pygame.transform.flip(_grads[fk], False, True)
            surf.blit(_grads[fk2], (dr.x, dr.y + dr.height - fade_h))

            pygame.draw.rect(surf, (200, 165, 85), dr, 2, border_radius=16)

        elif phase == "done":
            result    = _slot_results[i]
            is_talent = result and result.get("name") != "無天賦"
            # 背景調淡：有天賦用暖金琥珀，無天賦用暖灰棕（皆可讀深色文字）
            bg_col    = (215, 165, 88) if is_talent else (210, 185, 155)
            dr        = _premium_btn(surf, r, bg_col, False, radius=16)
            if is_talent:
                pygame.draw.rect(surf, YELLOW, dr, 2, border_radius=16)
            name     = result.get("name", "無天賦") if result else "無天賦"
            # 深棕文字在淺色底上清晰可讀
            name_col = TITLE if is_talent else WHITE
            nt       = fb_lg.render(name, True, name_col)
            # ── 垂直 + 水平置中 ─────────────────────────────────
            if is_talent:
                desc_lines = _wrap(result.get("desc", ""), fs, cw - 20)
                lh      = fs.get_height() + 4
                block_h = fb_lg.get_height() + 12 + len(desc_lines) * lh
                name_y  = dr.y + (dr.height - block_h) // 2
                surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, name_y))
                desc_y = name_y + fb_lg.get_height() + 12
                for li, dl in enumerate(desc_lines):
                    dt = fs.render(dl, True, WHITE)
                    surf.blit(dt, (dr.x + (dr.width - dt.get_width()) // 2,
                                   desc_y + li * lh))
            else:   # 無天賦 — 只有名稱，垂直置中
                name_y = dr.y + (dr.height - nt.get_height()) // 2
                surf.blit(nt, (dr.x + (dr.width - nt.get_width()) // 2, name_y))

    # ── 繼續按鈕（全部完成後才出現）──────────────────────────────
    ok = pygame.Rect((WIN_W - 160) // 2, sy + ch + SLOT_BTN, 160, btn_h)
    if all_done:
        hover = ok.collidepoint(mpos)
        ok_dr = _premium_btn(surf, ok, BTN_N, hover, radius=14)
        t     = fb_lg.render("繼續", True, WHITE)
        surf.blit(t, (ok_dr.x + (ok_dr.width - t.get_width()) // 2,
                      ok_dr.y + (ok_dr.height - t.get_height()) // 2))
        return ok
    return None


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
