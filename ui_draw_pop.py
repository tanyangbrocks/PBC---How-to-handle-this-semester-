# ============================================================
#  ui_draw_pop.py -- Popups, modals, shop
#  by refactor_ui.py
# ============================================================
import pygame
import math
import random
import os

from ui_const import *
from ui_state  import *
from ui_draw_base import *
from ui_draw_hud import _draw_icon_coin

def _draw_choice_popup(surf, fm, fs, mode, choices, log, prompt_text,
                       yn_labels, mpos):
    """
    畫面中央通用選項彈出視窗。
      mode == "choices"（非標準）→ 顯示題目（log 末尾）+ 選項按鈕（縱排）
      mode == "yn"               → 顯示 prompt + 是/否按鈕（橫排）
    回傳 [(rect, val), ...] 可點擊按鈕清單。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17（題目 / 按鈕文字）
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22（yn 按鈕）
    # ── 全螢幕遮罩 ────────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 155))
    surf.blit(ov, (0, 0))

    PAD_X   = 32   # 視窗左右內距
    PAD_TOP = 22
    PAD_BOT = 24
    BTN_PX  = 16   # 按鈕水平內距
    BTN_PY  = 10   # 按鈕垂直內距
    BTN_GAP = 8    # 按鈕間距
    SEP_H   = 14   # 題目與按鈕之間間距

    popup_w    = min(WIN_W - 40, 900)
    text_w     = popup_w - PAD_X * 2
    btn_text_w = text_w - BTN_PX * 2

    # ── 題目文字準備 ─────────────────────────────────────────
    _yn_ctx_count = 0   # yn 模式：紀錄「文案背景行數」，用於分色渲染
    if mode == "yn":
        raw = prompt_text or ""
        if _yn_show_ctx[0]:
            # 取最近幾條 log 純字串作為文案背景（最多 3 條）
            ctx_entries = [l for l in log if isinstance(l, str)][-3:]
            ctx_lines   = []
            for entry in ctx_entries:
                ctx_lines.extend(_wrap(entry, fb, text_w))
            _yn_ctx_count = len(ctx_lines)
            q_lines = ctx_lines + (_wrap(raw, fb, text_w) if raw else [])
        else:
            # 不附帶 log 背景，只顯示 prompt 本身
            q_lines = _wrap(raw, fb, text_w) if raw else []
    else:
        q_lines = list(log[-6:]) if log else []

    q_lh = fb.get_height() + 4
    q_h  = len(q_lines) * q_lh

    # ── 按鈕佈局計算 ─────────────────────────────────────────
    btn_layout = []   # [(wrapped_lines, btn_h, val), ...]
    if mode == "yn":
        yn_half_w = (text_w - BTN_GAP) // 2 - BTN_PX * 2
        for label, val in [(yn_labels[0], True), (yn_labels[1], False)]:
            lines = _wrap(label, fb_lg, yn_half_w)
            bh    = max(46, len(lines) * (fb_lg.get_height() + 3) + BTN_PY * 2)
            btn_layout.append((lines, bh, val))
        btns_h = max(bh for _, bh, _ in btn_layout)
    else:
        for i, label in enumerate(choices):
            lines = _wrap(_clean(label), fb, btn_text_w)
            bh    = max(46, len(lines) * (fb.get_height() + 3) + BTN_PY * 2)
            btn_layout.append((lines, bh, i + 1))
        btns_h = (sum(bh + BTN_GAP for _, bh, _ in btn_layout) - BTN_GAP
                  if btn_layout else 0)

    sep_actual = SEP_H if q_lines else 0
    total_h    = min(PAD_TOP + q_h + sep_actual + btns_h + PAD_BOT,
                     WIN_H - 60)
    px = (WIN_W - popup_w) // 2
    py = max(30, (WIN_H - total_h) // 2)

    # ── 投影 + 卡片 ──────────────────────────────────────────
    sh = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 55),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(sh, (px + 4, py + 4))
    card = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 248, 238, 248),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(card, (px, py))
    pygame.draw.rect(surf, CYAN,
                     pygame.Rect(px, py, popup_w, total_h), 2, border_radius=18)

    # ── 設定 clip 防溢出 ──────────────────────────────────────
    old_clip = surf.get_clip()
    inner    = pygame.Rect(px + 2, py + 2, popup_w - 4, total_h - 4)
    surf.set_clip(inner)

    # ── 題目文字 ─────────────────────────────────────────────
    # yn 模式：文案背景行（前 _yn_ctx_count 行）用暖棕灰色，
    # 問題本身（後段）用正常深棕色，形成視覺層次。
    cur_y = py + PAD_TOP
    for i, line in enumerate(q_lines):
        line_col = GRAY if (mode == "yn" and i < _yn_ctx_count) else WHITE
        lt = fb.render(line, True, line_col)
        surf.blit(lt, (px + PAD_X, cur_y))
        cur_y += q_lh

    if q_lines and sep_actual:
        mid_sep = cur_y + sep_actual // 2
        pygame.draw.line(surf, (210, 190, 165),
                         (px + PAD_X, mid_sep), (px + popup_w - PAD_X, mid_sep), 1)
        cur_y += sep_actual

    # ── 按鈕 ─────────────────────────────────────────────────
    btn_rects = []
    bx = px + PAD_X
    bw = text_w

    if mode == "yn":
        yw    = (bw - BTN_GAP) // 2
        yn_bh = max(bh for _, bh, _ in btn_layout)
        for j, (lines, _, val) in enumerate(btn_layout):
            br    = pygame.Rect(bx + j * (yw + BTN_GAP), cur_y, yw, yn_bh)
            col_b = BTN_N if val else DARK_GRAY
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, col_b, hover, radius=12)
            th    = len(lines) * (fb_lg.get_height() + 3)
            ty    = dr.y + (dr.height - th) // 2
            for line in lines:
                lt = fb_lg.render(line, True, PANEL)
                surf.blit(lt, (dr.x + (dr.width - lt.get_width()) // 2, ty))
                ty += fb_lg.get_height() + 3
            btn_rects.append((br, val))
    else:
        for lines, bh, val in btn_layout:
            br    = pygame.Rect(bx, cur_y, bw, bh)
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
            th    = len(lines) * (fb.get_height() + 3)
            ty    = dr.y + (dr.height - th) // 2
            for line in lines:
                lt = fb.render(line, True, PANEL)
                surf.blit(lt, (dr.x + (dr.width - lt.get_width()) // 2, ty))
                ty += fb.get_height() + 3
            btn_rects.append((br, val))
            cur_y += bh + BTN_GAP

    surf.set_clip(old_clip)
    return btn_rects

def _draw_event_ok_popup(surf: pygame.Surface, fm, fs, mpos) -> list:
    """
    突發事件通知彈窗（單一「確認」按鈕）。
    _event_ok_text[0] 格式：「前綴：【事件名】\\n描述文字」
    回傳 [(rect, True)] 確認按鈕 rect 清單。
    """
    fb    = _font_bold[0]    or fs
    fb_lg = _font_bold_lg[0] or fm

    # ── 解析文字 ─────────────────────────────────────────────
    raw   = _event_ok_text[0] or ""
    parts = raw.split("\n", 1)
    title = parts[0]
    body  = parts[1].strip() if len(parts) > 1 else ""

    # ── 版面常數 ─────────────────────────────────────────────
    popup_w = min(WIN_W - 80, 760)
    PAD_X   = 28
    PAD_TOP = 18
    PAD_BOT = 24
    HDR_H   = fb_lg.get_height() + 22
    SEP_H   = 14
    BTN_H   = 48
    BTN_W   = 180
    text_w  = popup_w - PAD_X * 2

    # ── 包裹文字 ─────────────────────────────────────────────
    title_lines = _wrap(title, fb_lg, text_w)
    body_lines  = _wrap(body, fb, text_w) if body else []
    q_lh_lg = fb_lg.get_height() + 4
    q_lh    = fb.get_height()    + 4
    body_h  = len(body_lines) * q_lh

    total_h = min(HDR_H + PAD_TOP + body_h + SEP_H + BTN_H + PAD_BOT,
                  WIN_H - 60)
    px = (WIN_W - popup_w) // 2
    py = max(30, (WIN_H - total_h) // 2)

    # ── 全螢幕遮罩 ────────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 165))
    surf.blit(ov, (0, 0))

    # ── 投影 ──────────────────────────────────────────────────
    sh = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 60),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(sh, (px + 4, py + 4))

    # ── 主體（米白）──────────────────────────────────────────
    card = pygame.Surface((popup_w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 248, 238, 252),
                     pygame.Rect(0, 0, popup_w, total_h), border_radius=18)
    surf.blit(card, (px, py))

    # ── 標題列（深橙棕，僅上方圓角）─────────────────────────
    _HDR_COL = (165, 88, 32)
    hdr = pygame.Surface((popup_w, HDR_H), pygame.SRCALPHA)
    pygame.draw.rect(hdr, (*_HDR_COL, 255),
                     pygame.Rect(0, 0, popup_w, HDR_H), border_radius=18)
    pygame.draw.rect(hdr, (*_HDR_COL, 255),
                     pygame.Rect(0, 14, popup_w, HDR_H - 14))
    surf.blit(hdr, (px, py))

    # 標題文字（居中，亮米色）
    hdr_ty = py + (HDR_H - len(title_lines) * q_lh_lg) // 2
    for line in title_lines:
        ts = fb_lg.render(line, True, (255, 232, 190))
        surf.blit(ts, (px + (popup_w - ts.get_width()) // 2, hdr_ty))
        hdr_ty += q_lh_lg

    # ── 邊框（可自定義顏色，用於額外事件彈窗）────────────────────
    _bdr = _event_ok_border_color[0] or (155, 100, 50)
    pygame.draw.rect(surf, _bdr,
                     pygame.Rect(px, py, popup_w, total_h), 3, border_radius=18)

    # ── clip ─────────────────────────────────────────────────
    old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(px + 2, py + 2, popup_w - 4, total_h - 4))

    # ── 描述文字 ──────────────────────────────────────────────
    cur_y = py + HDR_H + PAD_TOP
    for line in body_lines:
        ls = fb.render(line, True, WHITE)
        surf.blit(ls, (px + PAD_X, cur_y))
        cur_y += q_lh

    # ── 分隔線 ────────────────────────────────────────────────
    sep_y = py + total_h - PAD_BOT - BTN_H - SEP_H // 2
    pygame.draw.line(surf, (210, 190, 165),
                     (px + PAD_X, sep_y), (px + popup_w - PAD_X, sep_y), 1)

    # ── 確認按鈕（置中）──────────────────────────────────────
    btn_x = px + (popup_w - BTN_W) // 2
    btn_y = py + total_h - PAD_BOT - BTN_H
    br    = pygame.Rect(btn_x, btn_y, BTN_W, BTN_H)
    hover = br.collidepoint(mpos)
    dr    = _premium_btn(surf, br, BTN_N, hover, radius=12)
    ct    = fb_lg.render(_event_ok_btn_label[0], True, PANEL)
    surf.blit(ct, (dr.x + (dr.width  - ct.get_width())  // 2,
                   dr.y + (dr.height - ct.get_height()) // 2))

    surf.set_clip(old_clip)
    return [(br, True)]

def _draw_subj_popup(surf, fm, fs, mpos):
    """
    在畫面中央繪製「選擇科目」彈出視窗，並回傳按鈕清單 [(rect, idx), ...]。
    idx 為 1-based；玩家點擊後由事件迴圈負責解除 popup 並回傳結果。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17（按鈕文字）
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22（標題）
    # ── 半透明暗色遮罩 ────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 160))
    surf.blit(ov, (0, 0))

    n       = len(_subj_popup_opts)
    bw      = 460          # 按鈕寬度
    bh      = 46           # 按鈕高度
    gap     = 10           # 按鈕間距
    pad_x   = 40           # 左右內距
    pad_top = 20           # 頂部內距（標題上方）
    pad_mid = 14           # 標題與按鈕之間
    pad_bot = 24           # 最後按鈕到底部
    sep_h   = 1            # 標題下方分隔線高度

    total_w = bw + pad_x * 2
    title_h = fm.get_height()
    total_h = (pad_top + title_h + 6 + sep_h + pad_mid
               + n * bh + max(n - 1, 0) * gap
               + pad_bot)

    px = (WIN_W - total_w) // 2
    py = (WIN_H - total_h) // 2

    # ── 視窗背景 ──────────────────────────────────────────────
    box = pygame.Rect(px, py, total_w, total_h)
    pygame.draw.rect(surf, (255, 244, 228), box, border_radius=18)
    pygame.draw.rect(surf, CYAN,            box, 2, border_radius=18)

    # ── 標題 ──────────────────────────────────────────────────
    ttx = fb_lg.render(_subj_popup_title[0], True, WHITE)
    surf.blit(ttx, (px + (total_w - ttx.get_width()) // 2, py + pad_top))

    # 標題下分隔線
    line_y = py + pad_top + title_h + 6
    pygame.draw.line(surf, (CYAN[0], CYAN[1], CYAN[2]),
                     (px + 18, line_y), (px + total_w - 18, line_y), 1)

    # ── 選項按鈕 ──────────────────────────────────────────────
    bx  = px + pad_x
    by0 = line_y + sep_h + pad_mid
    btn_list = []
    for i, label in enumerate(_subj_popup_opts):
        br    = pygame.Rect(bx, by0 + i * (bh + gap), bw, bh)
        hover = br.collidepoint(mpos)
        dr    = _premium_btn(surf, br, (255, 248, 238), hover, radius=12)
        lt    = fb.render(label, True, WHITE)
        surf.blit(lt, (dr.x + (dr.width  - lt.get_width())  // 2,
                       dr.y + (dr.height - lt.get_height()) // 2))
        btn_list.append((br, i + 1))

    return btn_list

def _draw_withdrawal_popup(surf, fm, fs, mpos):
    """
    停修選課彈窗：每個選項顯示課程名稱（粗體）+ 說明文字（小字，第二行）。
    回傳 [(rect, 課名字串), ...]。
    """
    fb    = _font_bold[0]    or fs    # 粗體 size-17（課名）
    fb_lg = _font_bold_lg[0] or fm    # 粗體 size-22（標題）

    # ── 半透明暗色遮罩 ────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 160))
    surf.blit(ov, (0, 0))

    n       = len(_withdrawal_popup_opts)
    bw      = 640          # 按鈕寬度（比科目彈窗寬，容納說明文字）
    bh      = 72           # 按鈕高度（含兩行文字）
    gap     = 10
    pad_x   = 40
    pad_top = 20
    pad_mid = 14
    pad_bot = 24
    sep_h   = 1

    total_w = bw + pad_x * 2
    title_h = fb_lg.get_height()
    total_h = (pad_top + title_h + 6 + sep_h + pad_mid
               + n * bh + max(n - 1, 0) * gap
               + pad_bot)

    px = (WIN_W - total_w) // 2
    py = (WIN_H - total_h) // 2

    # ── 視窗背景 ──────────────────────────────────────────────
    box = pygame.Rect(px, py, total_w, total_h)
    pygame.draw.rect(surf, (255, 244, 228), box, border_radius=18)
    pygame.draw.rect(surf, CYAN,            box, 2, border_radius=18)

    # ── 標題 ──────────────────────────────────────────────────
    POPUP_TITLE = "好課值得一修再修，請選擇你的停修科目"
    ttx = fb_lg.render(POPUP_TITLE, True, WHITE)
    surf.blit(ttx, (px + (total_w - ttx.get_width()) // 2, py + pad_top))

    # 標題下分隔線
    line_y = py + pad_top + title_h + 6
    pygame.draw.line(surf, (CYAN[0], CYAN[1], CYAN[2]),
                     (px + 18, line_y), (px + total_w - 18, line_y), 1)

    # ── 選項按鈕 ──────────────────────────────────────────────
    bx  = px + pad_x
    by0 = line_y + sep_h + pad_mid
    btn_list = []
    for i, (course, desc) in enumerate(_withdrawal_popup_opts):
        br    = pygame.Rect(bx, by0 + i * (bh + gap), bw, bh)
        hover = br.collidepoint(mpos)
        dr    = _premium_btn(surf, br, (255, 248, 238), hover, radius=12)
        # 課程名稱（粗體，上行）
        nt     = fb.render(course, True, WHITE)
        name_y = dr.y + (bh - fb.get_height() - fs.get_height() - 4) // 2
        surf.blit(nt, (dr.x + 16, name_y))
        # 說明文字（小字，下行）
        dt = fs.render(desc, True, GRAY)
        surf.blit(dt, (dr.x + 16, name_y + fb.get_height() + 4))
        btn_list.append((br, course))

    return btn_list


def _draw_skip_class_popup(surf, fm, fs, mpos):
    """
    在畫面中央繪製「翹課選課」彈出視窗。
    已翹 / 已上的課顯示斜蓋印章且不可點擊。
    回傳 [(rect, value), ...] 其中 value = 課名字串 或 None（取消）。
    """
    fb    = _font_bold[0]    or fs
    fb_lg = _font_bold_lg[0] or fm

    # ── 半透明暗色遮罩 ──────────────────────────────────────────
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 160))
    surf.blit(ov, (0, 0))

    n    = len(_skip_popup_courses)
    COLS = 2
    CW   = 200   # 卡片寬
    CH   = 52    # 卡片高
    HGAP = 14    # 水平間距
    VGAP = 10    # 垂直間距
    rows = max(1, (n + COLS - 1) // COLS)

    pad_x    = 36
    pad_top  = 22
    pad_mid  = 14
    pad_bot  = 20
    cancel_h = 40
    title_h  = fm.get_height()

    grid_w  = COLS * CW + (COLS - 1) * HGAP
    total_w = grid_w + pad_x * 2
    grid_h  = rows * CH + max(rows - 1, 0) * VGAP
    total_h = (pad_top + title_h + 6 + 1 + pad_mid
               + grid_h + pad_mid + cancel_h + pad_bot)

    px = (WIN_W - total_w) // 2
    py = (WIN_H - total_h) // 2

    # ── 視窗背景 ──────────────────────────────────────────────
    box = pygame.Rect(px, py, total_w, total_h)
    pygame.draw.rect(surf, (255, 244, 228), box, border_radius=18)
    pygame.draw.rect(surf, CYAN,            box, 2, border_radius=18)

    # ── 標題 ──────────────────────────────────────────────────
    ttx = fb_lg.render("選擇要翹的課", True, WHITE)
    surf.blit(ttx, (px + (total_w - ttx.get_width()) // 2, py + pad_top))

    line_y = py + pad_top + title_h + 6
    pygame.draw.line(surf, CYAN, (px + 18, line_y), (px + total_w - 18, line_y), 1)

    # ── 卡片網格 ──────────────────────────────────────────────
    gx0 = px + pad_x
    gy0 = line_y + 1 + pad_mid

    btn_list = []
    for i, course in enumerate(_skip_popup_courses):
        col = i % COLS
        row = i // COLS
        cx  = gx0 + col * (CW + HGAP)
        cy  = gy0 + row * (CH + VGAP)
        cr  = pygame.Rect(cx, cy, CW, CH)

        is_skipped  = course in _skip_popup_skipped
        is_attended = course in _skip_popup_attended
        is_disabled = is_skipped or is_attended

        if is_disabled:
            # ── 灰色底 ────────────────────────────────────────
            pygame.draw.rect(surf, (72, 58, 48), cr, border_radius=10)
            pygame.draw.rect(surf, (100, 82, 65), cr, 1, border_radius=10)
            # 課名（灰暗色）
            ct = fb.render(course, True, (105, 88, 72))
            surf.blit(ct, (cr.x + (cr.width  - ct.get_width())  // 2,
                           cr.y + (cr.height - ct.get_height()) // 2))
            # ── 斜蓋印章 ──────────────────────────────────────
            if is_skipped:
                stamp_col  = (220,  40,  40)
                stamp_text = "已翹課"
            else:
                stamp_col  = ( 40, 185,  75)
                stamp_text = "已上課"
            stamp_surf = pygame.Surface((CW, CH), pygame.SRCALPHA)
            # 半透明底色渲染在 SRCALPHA 面
            tint = pygame.Surface((CW, CH), pygame.SRCALPHA)
            pygame.draw.rect(tint, (*stamp_col, 30),
                             pygame.Rect(0, 0, CW, CH), border_radius=10)
            stamp_surf.blit(tint, (0, 0))
            # 旋轉文字（set_alpha 模擬半透明）
            stx     = fb_lg.render(stamp_text, True, stamp_col)
            stx.set_alpha(220)
            str_rot = pygame.transform.rotate(stx, 18)
            stamp_surf.blit(str_rot,
                            ((CW - str_rot.get_width())  // 2,
                             (CH - str_rot.get_height()) // 2))
            surf.blit(stamp_surf, cr.topleft)
            # 彩色邊框
            pygame.draw.rect(surf, stamp_col, cr, 2, border_radius=10)
        else:
            # ── 正常可點擊卡片 ────────────────────────────────
            hover = cr.collidepoint(mpos)
            _premium_btn(surf, cr, (255, 248, 238), hover, radius=10)
            ct = fb.render(course, True, WHITE)
            surf.blit(ct, (cr.x + (cr.width  - ct.get_width())  // 2,
                           cr.y + (cr.height - ct.get_height()) // 2))
            btn_list.append((cr, course))

    # ── 取消按鈕 ──────────────────────────────────────────────
    cancel_r = pygame.Rect(gx0, gy0 + grid_h + pad_mid, grid_w, cancel_h)
    hover_c  = cancel_r.collidepoint(mpos)
    _premium_btn(surf, cancel_r, (80, 65, 55), hover_c, radius=10)
    ct2 = fb.render("取消", True, PANEL)
    surf.blit(ct2, (cancel_r.x + (cancel_r.width  - ct2.get_width())  // 2,
                    cancel_r.y + (cancel_r.height - ct2.get_height()) // 2))
    btn_list.append((cancel_r, None))

    return btn_list

def _draw_action_popup(surf, fs):
    """
    在遊戲畫面右側繪製由右而左滑入的行動結果視窗。
    特殊前綴：
      "! " → 警示行（紅色，加上小分隔線）
      "---" → 分隔線
    使用 _popup_t0[0] 與 _popup_lines 驅動動畫，由 run_ui 每幀呼叫。

    注意：繪製前設定 clip 至遊戲邊界 (WIN_W, WIN_H)，防止全螢幕模式下
    Surface 尺寸大於邏輯解析度時，動畫滑出位置超過右邊界並殘留上幀像素。
    """
    if _popup_t0[0] == 0 or not _popup_lines:
        return

    elapsed = pygame.time.get_ticks() - _popup_t0[0]
    if elapsed >= POPUP_DURATION:
        _popup_t0[0] = 0
        return

    # ── 限制繪製區域於遊戲邊界內（全螢幕 bug 防護）──────────
    _old_clip = surf.get_clip()
    surf.set_clip(pygame.Rect(0, 0, WIN_W, WIN_H))

    POPUP_W = 250
    lh      = fs.get_height() + 5
    SEP_H   = 10   # 分隔線高度（含上下空隙）

    # ── 預先展開所有行（支援自動換行）以計算總高度 ──────────
    title_h = fs.get_height() + 10
    rows    = []   # list of ("text", color) | ("sep",) | ("warn_sep",)
    for raw in _popup_lines:
        if isinstance(raw, tuple) and raw[0] == "multi":
            # ("multi", [(text, col), ...])：多色區段，單行渲染
            rows.append(("multi", raw[1]))
        elif isinstance(raw, tuple):
            # 舊式 2-tuple (text, color_rgb)：直接以指定顏色渲染
            _annot_text, _annot_col = raw
            rows.append((_annot_text, _annot_col))
        elif raw == "---":
            rows.append(("sep",))
        elif raw.startswith("! "):
            display = raw[2:]
            rows.append(("warn_sep",))
            for wl in _wrap(display, fs, POPUP_W - 28):
                rows.append((wl, RED))
        else:
            if "+" in raw:
                col = GREEN
            elif "-" in raw:
                col = RED
            else:
                col = WHITE
            for wl in _wrap(raw, fs, POPUP_W - 28):
                rows.append((wl, col))

    ph = (title_h + 4
          + sum(SEP_H if r[0] in ("sep", "warn_sep") else lh for r in rows)
          + 14)
    # "multi" 行的 r[0] == "multi"，不在 sep/warn_sep 中，正確算 lh ✓

    # ── x 位置動畫 ─────────────────────────────────────────
    target_x = WIN_W - POPUP_W - 16
    if elapsed < POPUP_IN_MS:
        t  = elapsed / POPUP_IN_MS
        t2 = 1 - (1 - t) ** 3
        x  = WIN_W - int(t2 * (POPUP_W + 16))
    elif elapsed > POPUP_DURATION - POPUP_OUT_MS:
        t  = (elapsed - (POPUP_DURATION - POPUP_OUT_MS)) / POPUP_OUT_MS
        t2 = t * t
        x  = target_x + int(t2 * (POPUP_W + 32))
    else:
        x  = target_x

    y     = STATUS_H + (CHAR_H - ph) // 2
    pop_r = pygame.Rect(x, y, POPUP_W, ph)

    # ── 繪製面板 ───────────────────────────────────────────
    _soft_shadow(surf, pop_r, radius=12, alpha=60, offset=(4, 6), spread=5)
    pygame.draw.rect(surf, PANEL, pop_r, border_radius=12)
    pygame.draw.rect(surf, CYAN,  pop_r, 2, border_radius=12)
    _gloss_rect(surf, pop_r)

    # 標題列
    ty = pop_r.y + 8
    title_t = fs.render(_popup_title[0], True, TITLE)
    surf.blit(title_t, (pop_r.x + (POPUP_W - title_t.get_width()) // 2, ty))
    ty += title_t.get_height() + 4
    pygame.draw.line(surf, DARK_GRAY,
                     (pop_r.x + 12, ty), (pop_r.right - 12, ty), 1)
    ty += 6

    # 結果行
    for row in rows:
        if row[0] in ("sep", "warn_sep"):
            ty += SEP_H // 2
            pygame.draw.line(surf, DARK_GRAY,
                             (pop_r.x + 12, ty), (pop_r.right - 12, ty), 1)
            ty += SEP_H // 2
        elif row[0] == "multi":
            # 多色區段：逐段橫向排列在同一行
            xoff = pop_r.x + 14
            for seg_text, seg_col in row[1]:
                seg_s = fs.render(seg_text, True, seg_col)
                surf.blit(seg_s, (xoff, ty))
                xoff += seg_s.get_width()
            ty += lh
        else:
            text, col = row
            lt = fs.render(text, True, col)
            surf.blit(lt, (pop_r.x + 14, ty))
            ty += lh

    # ── 恢復原始 clip（避免影響後續繪製）────────────────────
    surf.set_clip(_old_clip)

def _draw_modal_overlay(surf):
    """在畫面上覆蓋一層半透明暗幕，突顯 modal。"""
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill((80, 50, 20, 110))   # 暖棕半透明遮罩（比純黑更有溫度）
    surf.blit(overlay, (0, 0))

def _tt_parse_time(t_str: str):
    """
    解析 'HH:MM–HH:MM' 格式（支援 en-dash / em-dash / 連字號）。
    回傳 (start_minutes, end_minutes)；失敗回傳 (None, None)。
    """
    for sep in ('–', '—', '-'):
        if sep in t_str:
            parts = t_str.split(sep, 1)
            def _m(s):
                s = s.strip()
                if ':' in s:
                    h, m = s.split(':', 1)
                    return int(h) * 60 + int(m)
                return int(s) * 60
            try:
                return _m(parts[0]), _m(parts[1])
            except (ValueError, IndexError):
                pass
    return None, None


# 課程固定色對照（暖色系，配合遊戲棕橘主調）
_TT_COURSE_COLORS = {
    "個體經濟學下": (210, 155,  58),
    "統計學":       (108, 162,  86),
    "商管程式設計": (190, 103,  76),
    "社會學甲下":   ( 92, 136, 180),
    "會計學（二）": (176, 106, 126),
    "哲學概論":     (148, 118, 182),
    "全球品牌管理": (168, 140,  75),
    "政治學二":     (155, 105,  80),
    "看電影學愛情": (185, 125, 155),
}
_TT_DEFAULT_COLOR = (198, 136, 76)


def _draw_modal_timetable(surf, fm, fs, courses, mpos):
    """
    格狀週課表 modal（仿 sheet.webp 佈局，遊戲暖色調）。
    courses: [{"name":str, "day":str, "time":str, "credits":int}, ...]
    回傳「確認」按鈕 Rect。
    """
    _draw_modal_overlay(surf)

    # ── 卡片尺寸與位置 ───────────────────────────────────────────
    cw, ch = 760, 620
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=18, alpha=80, offset=(4, 8), spread=8)
    pygame.draw.rect(surf, PANEL, card, border_radius=18)
    pygame.draw.rect(surf, CYAN,  card, 2,  border_radius=18)

    # ── 標題 ────────────────────────────────────────────────────
    fb = _font_bold[0] or fm
    title_s = fb.render("本週課表", True, TITLE)
    surf.blit(title_s, (cx + (cw - title_s.get_width()) // 2, cy + 12))
    pygame.draw.line(surf, (195, 163, 123),
                     (cx + 16, cy + 44), (cx + cw - 16, cy + 44), 1)

    # ── 格狀區域參數 ─────────────────────────────────────────────
    TIME_COL_W = 46          # 左側時間標籤欄寬
    PAD_L      = 14          # 卡片內左 padding
    PAD_R      = 14          # 卡片內右 padding
    HEADER_H   = 26          # 星期標頭列高
    BTN_H_RSV  = 54          # 底部按鈕預留高度

    DAYS     = ["週一", "週二", "週三", "週四", "週五"]
    N_DAYS   = len(DAYS)
    START_H  = 8             # 08:00 起
    END_H    = 23            # 23:00 止
    N_HOURS  = END_H - START_H  # 15 小時

    # 格子區左邊界 X / 上邊界 Y
    GRID_X0 = cx + PAD_L + TIME_COL_W + 3
    GRID_Y0 = cy + 50 + HEADER_H
    GRID_W  = cw - PAD_L - TIME_COL_W - 3 - PAD_R
    GRID_H  = ch - 50 - HEADER_H - BTN_H_RSV - 4

    COL_W   = GRID_W // N_DAYS
    ROW_H   = GRID_H / N_HOURS          # float，精確定位用

    # ── 格子區背景（羊皮紙色）───────────────────────────────────
    bg_s = pygame.Surface((TIME_COL_W + 3 + GRID_W, HEADER_H + GRID_H),
                           pygame.SRCALPHA)
    pygame.draw.rect(bg_s, (250, 241, 224, 255),
                     (0, 0, TIME_COL_W + 3 + GRID_W, HEADER_H + GRID_H),
                     border_radius=8)
    surf.blit(bg_s, (cx + PAD_L, cy + 50))

    # ── 星期標頭 ────────────────────────────────────────────────
    for di, day in enumerate(DAYS):
        col_cx = GRID_X0 + di * COL_W + COL_W // 2
        dt = fs.render(day, True, YELLOW)
        surf.blit(dt, (col_cx - dt.get_width() // 2,
                       cy + 50 + (HEADER_H - dt.get_height()) // 2))

    # 標頭底部分隔線
    pygame.draw.line(surf, (195, 163, 123),
                     (cx + PAD_L, GRID_Y0),
                     (GRID_X0 + GRID_W, GRID_Y0), 1)

    # ── 水平格線 + 時間標籤 ──────────────────────────────────────
    for hi in range(N_HOURS + 1):
        gy   = GRID_Y0 + int(hi * ROW_H)
        hour = START_H + hi
        lc   = (195, 163, 123) if hi == 0 or hi == N_HOURS else (215, 190, 158)
        pygame.draw.line(surf, lc,
                         (cx + PAD_L, gy), (GRID_X0 + GRID_W, gy), 1)
        if hi < N_HOURS:
            tl = fs.render(f"{hour:02d}:00", True, GRAY)
            surf.blit(tl, (cx + PAD_L + (TIME_COL_W - tl.get_width()) // 2,
                           gy + 3))

    # ── 垂直格線（各 day 欄之間）────────────────────────────────
    for di in range(N_DAYS + 1):
        lx = GRID_X0 + di * COL_W
        lc = (195, 163, 123) if di == 0 or di == N_DAYS else (215, 190, 158)
        pygame.draw.line(surf, lc,
                         (lx, GRID_Y0), (lx, GRID_Y0 + GRID_H), 1)

    # ── 課程色塊 ─────────────────────────────────────────────────
    day_map   = {d: i for i, d in enumerate(DAYS)}
    total_min = N_HOURS * 60

    for course in courses:
        di = day_map.get(course.get("day", ""))
        if di is None:
            continue

        s_min, e_min = _tt_parse_time(course.get("time", ""))
        if s_min is None:
            continue

        # 裁剪至顯示範圍
        s_min = max(s_min, START_H * 60)
        e_min = min(e_min, END_H   * 60)
        if e_min <= s_min:
            continue

        off_s = s_min - START_H * 60
        off_e = e_min - START_H * 60

        bx = GRID_X0 + di * COL_W + 2
        by = GRID_Y0 + int(off_s / total_min * GRID_H)
        bw = COL_W - 4
        bh = max(14, int((off_e - off_s) / total_min * GRID_H) - 1)

        col3 = _TT_COURSE_COLORS.get(course.get("name", ""), _TT_DEFAULT_COLOR)

        # 圓角色塊（半透明）
        blk = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(blk, (*col3, 195), (0, 0, bw, bh), border_radius=5)
        light = tuple(min(255, c + 55) for c in col3)
        pygame.draw.rect(blk, (*light, 215), (0, 0, bw, bh), 1, border_radius=5)
        surf.blit(blk, (bx, by))

        # 課名（置中，空間不足時略過）
        name = course.get("name", "")
        nt   = fs.render(name, True, (255, 255, 255))
        if nt.get_width() <= bw - 4 and bh >= nt.get_height() + 2:
            surf.blit(nt, (bx + (bw - nt.get_width())  // 2,
                           by + (bh - nt.get_height()) // 2))

    # ── 確認按鈕 ────────────────────────────────────────────────
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + ch - 50, 140, 44)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok

def _draw_modal_grade(surf, fm, fl, fs, items, mpos):
    """
    成績公告彈出 modal。
    items: [{"name":str, "score": int|float}, ...]
    回傳「確認」按鈕 Rect。
    """
    _draw_modal_overlay(surf)
    cw, ch = 420, 100 + len(items) * 80 + 80
    cx = (WIN_W - cw) // 2
    cy = (WIN_H - ch) // 2
    card = pygame.Rect(cx, cy, cw, ch)
    _soft_shadow(surf, card, radius=20, alpha=80, offset=(4, 8), spread=8)
    pygame.draw.rect(surf, PANEL, card, border_radius=20)
    pygame.draw.rect(surf, YELLOW, card, 2, border_radius=20)

    # 標題
    title = fm.render("成績公告", True, YELLOW)
    surf.blit(title, (cx + (cw - title.get_width()) // 2, cy + 18))
    pygame.draw.line(surf, GRAY,
                     (cx + 20, cy + 52), (cx + cw - 20, cy + 52), 1)

    row_y = cy + 66
    for item in items:
        score = item["score"]
        score_str = f"{score:.0f} 分" if isinstance(score, float) else f"{score} 分"
        # 分數顏色
        if isinstance(score, (int, float)) and score >= 80:
            sc = GREEN
        elif isinstance(score, (int, float)) and score >= 60:
            sc = YELLOW
        else:
            sc = RED
        name_t  = fm.render(item["name"], True, WHITE)
        score_t = fl.render(score_str, True, sc)
        surf.blit(name_t,  (cx + 30, row_y))
        surf.blit(score_t, (cx + cw - score_t.get_width() - 30, row_y - 6))
        pygame.draw.line(surf, DARK_GRAY,
                         (cx + 20, row_y + 60), (cx + cw - 20, row_y + 60), 1)
        row_y += 80

    # 確認按鈕
    ok    = pygame.Rect(cx + (cw - 140) // 2, cy + ch - 56, 140, 44)
    hover = ok.collidepoint(mpos)
    dr    = _premium_btn(surf, ok, BTN_N, hover, radius=14)
    t     = fm.render("確認", True, WHITE)
    surf.blit(t, (dr.x + (dr.width  - t.get_width())  // 2,
                  dr.y + (dr.height - t.get_height()) // 2))
    return ok

def _draw_shop(surf: pygame.Surface,
               fm, fs, fl,
               items:  list,
               player,
               mpos:   tuple):
    """
    道具店全螢幕介面。
    左側：2欄×5列商品卡（圖示 + 名稱 + 簡述 + 購買按鈕）
    右側：效果說明面板 + 剩餘金錢 + 離開按鈕
    回傳 (buy_rects[(Rect, idx)...], exit_btn_rect)
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22
    # 背景
    surf.blit(_grads.get("bg", pygame.Surface((WIN_W, WIN_H))), (0, 0))
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((255, 238, 200, 55))
    surf.blit(ov, (0, 0))

    # ── 版面常數 ───────────────────────────────────────────────
    COLS   = 2
    ITEM_W = 305
    ITEM_H = 118
    GAP_X  = 10
    GAP_Y  = 8
    GX     = 15
    GY     = 15
    RP_X   = GX + COLS * (ITEM_W + GAP_X)   # 645
    RP_W   = WIN_W - RP_X - 15              # 300

    # ── 捲動計算 ──────────────────────────────────────────────
    GRID_H    = WIN_H - GY * 2              # 690px 可見高度
    rows_all  = max(1, math.ceil(len(items) / COLS))
    total_h   = rows_all * ITEM_H + (rows_all - 1) * GAP_Y
    max_scroll = max(0, total_h - GRID_H)
    scroll_y  = max(0, min(_shop_scroll_y[0], max_scroll))
    _shop_scroll_y[0] = scroll_y   # 箝制回 state

    # 商品格的裁切矩形（防止卡片畫到右側面板 / 上下邊界外）
    GRID_CLIP = pygame.Rect(GX - 4, GY, RP_X - GX, GRID_H)

    buy_rects  = []
    hover_this = -1

    # ── 預先判斷 hover（加入捲動偏移 + 限制在 grid 範圍內）──────
    for i in range(len(items)):
        col = i % COLS
        row = i // COLS
        bx  = GX + col * (ITEM_W + GAP_X)
        by  = GY + row * (ITEM_H + GAP_Y) - scroll_y
        if (pygame.Rect(bx, by, ITEM_W, ITEM_H).collidepoint(mpos)
                and GRID_CLIP.collidepoint(mpos)):
            hover_this = i
            break

    # ── 繪製商品卡（先畫非 hover，再畫 hover 確保在最上層）──────
    draw_order = [i for i in range(len(items)) if i != hover_this]
    if hover_this >= 0:
        draw_order.append(hover_this)

    old_clip = surf.get_clip()
    surf.set_clip(GRID_CLIP)          # 開始裁切

    for i in draw_order:
        item = items[i]
        col  = i % COLS
        row  = i // COLS
        bx   = GX + col * (ITEM_W + GAP_X)
        by   = GY + row * (ITEM_H + GAP_Y) - scroll_y
        # 完全在可見範圍外則跳過
        if by + ITEM_H < GY or by > GY + GRID_H:
            continue
        base = pygame.Rect(bx, by, ITEM_W, ITEM_H)
        is_hov = (i == hover_this)

        # 卡片 hover 動畫（獨立 key，不與按鈕動畫混用）
        ckey = ("sc", i)
        t    = _anim_hover.get(ckey, 0.0)
        t    = min(1.0, t + 0.12) if is_hov else max(0.0, t - 0.12)
        _anim_hover[ckey] = t
        scale = 1.0 + _ease_out_back(t) * 0.042 if t > 0 else 1.0

        dr = _scaled_rect(base, scale)

        # 卡片背景
        _soft_shadow(surf, dr, radius=14,
                     alpha=60 if is_hov else 38,
                     offset=(3, 5) if is_hov else (2, 3),
                     spread=6 if is_hov else 3)
        pygame.draw.rect(surf, PANEL, dr, border_radius=14)
        # 頂部光澤條
        _gloss_rect(surf, dr)
        # 邊框
        pygame.draw.rect(surf, CYAN if is_hov else DARK_GRAY, dr, 2,
                         border_radius=14)

        # ── 道具圖示圓形 ─────────────────────────────────────────
        icon_r  = int(30 * scale)
        icon_cx = dr.x + int(50 * scale)
        icon_cy = dr.centery
        ic_col  = _item_icon_color(item)

        _soft_shadow_circle(surf, icon_cx, icon_cy, icon_r, alpha=38)
        dark_ic = tuple(max(0, int(c * 0.70)) for c in ic_col)
        pygame.draw.circle(surf, dark_ic, (icon_cx, icon_cy + int(3 * scale)), icon_r)
        pygame.draw.circle(surf, ic_col,  (icon_cx, icon_cy), icon_r)
        _gloss_circle(surf, icon_cx, icon_cy, icon_r)
        bdr_ic = tuple(min(255, int(c * 1.20 + 28)) for c in ic_col)
        pygame.draw.circle(surf, bdr_ic, (icon_cx, icon_cy), icon_r, 2)
        # 圖示：優先使用小圖（圓形裁切），無對應圖則退回首字
        _icon_d  = max(4, int(icon_r * 2 - 4))   # 直徑略小於圓，留 2px 邊距
        _icon_sf = _get_shop_icon(item.get("id", ""), _icon_d)
        if _icon_sf is not None:
            surf.blit(_icon_sf, (icon_cx - _icon_d // 2,
                                 icon_cy - _icon_d // 2))
        else:
            il = fs.render(item["name"][0], True, PANEL)
            surf.blit(il, (icon_cx - il.get_width()  // 2,
                           icon_cy - il.get_height() // 2))

        # ── 文字區 ───────────────────────────────────────────────
        info_x = dr.x + int(90 * scale)
        info_w = dr.right - info_x - int(8 * scale)

        # 道具名稱
        nt = fb_lg.render(item["name"], True, WHITE)
        surf.blit(nt, (info_x, dr.y + int(10 * scale)))

        # 效果簡述（1 行截斷）
        desc_s = item.get("desc", "")
        while desc_s and fs.size(desc_s + "…")[0] > info_w:
            desc_s = desc_s[:-1]
        if desc_s != item.get("desc", ""):
            desc_s += "…"
        dt = fs.render(desc_s, True, GRAY)
        surf.blit(dt, (info_x, dr.y + int(38 * scale)))

        # ── 購買按鈕 ─────────────────────────────────────────────
        buy_h  = int(32 * scale)
        buy_y  = dr.bottom - buy_h - int(9 * scale)
        buy_r  = pygame.Rect(info_x, buy_y, info_w, buy_h)
        bhov   = buy_r.collidepoint(mpos)
        afford = (player is not None and player.money >= item["price"])
        b_col  = BTN_N if afford else DARK_GRAY
        bdr_r  = _premium_btn(surf, buy_r, b_col,
                               bhov and afford, radius=int(9 * scale))
        # 購買按鈕：「購買 」+ 金幣圖示 + 「{price}」，整體置中
        _bc_r   = max(5, int(fb.get_height() * 0.38))   # 金幣半徑隨字型縮放
        _bc_col = PANEL if afford else GRAY
        pt_t    = fb.render(f"購買  ", True, _bc_col)
        pc_t    = fb.render(f" {item['price']}", True, _bc_col)
        _brow_w = pt_t.get_width() + _bc_r * 2 + pc_t.get_width()
        _brow_x = bdr_r.x + (bdr_r.width - _brow_w) // 2
        _brow_y = bdr_r.y + (bdr_r.height - pt_t.get_height()) // 2
        surf.blit(pt_t, (_brow_x, _brow_y))
        _draw_icon_coin(surf,
                        _brow_x + pt_t.get_width() + _bc_r,
                        bdr_r.centery, _bc_r)
        surf.blit(pc_t, (_brow_x + pt_t.get_width() + _bc_r * 2, _brow_y))

        buy_rects.append((buy_r, i))

    surf.set_clip(old_clip)           # 結束裁切

    # ── 垂直捲軸（有超出內容時才繪製）──────────────────────────
    if max_scroll > 0:
        SB_X  = RP_X - 9
        SB_W  = 5
        SB_Y  = GY
        SB_H  = GRID_H
        # 軌道
        pygame.draw.rect(surf, (200, 185, 165),
                         (SB_X, SB_Y, SB_W, SB_H), border_radius=3)
        # 滑塊
        thumb_h = max(22, int(SB_H * GRID_H / total_h))
        thumb_y = SB_Y + int((SB_H - thumb_h) * scroll_y / max_scroll)
        pygame.draw.rect(surf, (150, 120, 88),
                         (SB_X, thumb_y, SB_W, thumb_h), border_radius=3)

    _shop_hover_idx[0] = hover_this

    # ── 右側說明面板 ─────────────────────────────────────────────
    rp = pygame.Rect(RP_X, 15, RP_W, WIN_H - 80)
    _soft_shadow(surf, rp, radius=16, alpha=55, offset=(3, 5), spread=6)
    pygame.draw.rect(surf, PANEL, rp, border_radius=16)
    _gloss_rect(surf, rp)
    pygame.draw.rect(surf, CYAN, rp, 2, border_radius=16)

    # 標題
    tt = fb_lg.render("效果說明", True, TITLE)
    surf.blit(tt, (rp.x + (rp.width - tt.get_width()) // 2, rp.y + 16))
    pygame.draw.line(surf, GRAY,
                     (rp.x + 14, rp.y + 50), (rp.right - 14, rp.y + 50), 1)

    # 說明內容
    desc_y    = rp.y + 62
    msg_valid = (_shop_msg[0] and
                 pygame.time.get_ticks() - _shop_msg_time[0] < 2500)

    if msg_valid:
        mc = GREEN if _shop_msg[0].startswith("✅") else RED
        for j, ln in enumerate(_wrap(_shop_msg[0], fs, rp.width - 28)):
            mt = fs.render(_clean(ln), True, mc)
            surf.blit(mt, (rp.x + 14, desc_y + j * (fs.get_height() + 4)))
    elif hover_this >= 0 and hover_this < len(items):
        hi = items[hover_this]
        hn = fb_lg.render(hi["name"], True, WHITE)
        surf.blit(hn, (rp.x + 14, desc_y))
        # 售價：「售價：」+ 金幣 + 「{price} 元」
        _hr    = 9
        _hl_t  = fb.render("售價：", True, YELLOW)
        _hn2_t = fb.render(f" {hi['price']} 元", True, YELLOW)
        _hy    = desc_y + fm.get_height() + 6
        _hcy   = _hy + _hl_t.get_height() // 2
        surf.blit(_hl_t, (rp.x + 14, _hy))
        _draw_icon_coin(surf, rp.x + 14 + _hl_t.get_width() + _hr, _hcy, _hr)
        surf.blit(_hn2_t, (rp.x + 14 + _hl_t.get_width() + _hr * 2, _hy))
        dy2 = desc_y + fm.get_height() + fs.get_height() + 18
        for j, ln in enumerate(_wrap(hi.get("desc", ""), fs, rp.width - 28)):
            surf.blit(fs.render(ln, True, GRAY),
                      (rp.x + 14, dy2 + j * (fs.get_height() + 5)))
    else:
        for j, hint in enumerate(["將游標移至道具", "查看效果說明"]):
            ht = fs.render(hint, True, GRAY)
            surf.blit(ht, (rp.x + (rp.width - ht.get_width()) // 2,
                           desc_y + 24 + j * (fs.get_height() + 6)))

    # 分隔線 + 金錢
    pygame.draw.line(surf, GRAY,
                     (rp.x + 14, rp.bottom - 108),
                     (rp.right - 14, rp.bottom - 108), 1)
    # 剩餘金錢：「剩餘金錢：」+ 金幣圖示 + 數字，水平置中
    mval   = player.money if player else 0
    _mr    = 11                                         # 金幣圖示半徑
    _ml_t  = fb_lg.render("剩餘金錢：", True, YELLOW)
    _mn_t  = fb_lg.render(f"{mval}", True, YELLOW)
    _mrow_w = _ml_t.get_width() + _mr * 2 + 4 + _mn_t.get_width()
    _mrow_x = rp.x + (rp.width - _mrow_w) // 2
    _mrow_y = rp.bottom - 94
    _mcy    = _mrow_y + _ml_t.get_height() // 2
    surf.blit(_ml_t, (_mrow_x, _mrow_y))
    _draw_icon_coin(surf, _mrow_x + _ml_t.get_width() + _mr, _mcy, _mr)
    surf.blit(_mn_t, (_mrow_x + _ml_t.get_width() + _mr * 2 + 4, _mrow_y))

    # 離開道具店按鈕
    eb   = pygame.Rect(rp.x + 14, WIN_H - 60, rp.width - 28, 44)
    ehov = eb.collidepoint(mpos)
    edr  = _premium_btn(surf, eb, (200, 78, 58), ehov, radius=14)
    et   = fb_lg.render("離開道具店", True, PANEL)
    surf.blit(et, (edr.x + (edr.width  - et.get_width())  // 2,
                   edr.y + (edr.height - et.get_height()) // 2))

    return buy_rects, eb


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
