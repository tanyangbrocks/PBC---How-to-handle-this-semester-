# ============================================================
#  ui_draw_ap.py -- Action panel, grade/exp panels  [most edited]
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
from ui_draw_hud  import *

def _draw_action_icon(surf: pygame.Surface, cx: int, cy: int, ar: int, label: str) -> None:
    """在圓形按鈕表面貼上滿版 icon（圓形裁切）。"""
    if label not in _ACTION_ICON_FILES:
        return
    # 懶載入原始圖（每個 label 只 load 一次）
    if label not in _action_icon_srcs:
        _icon_dir = resource_path("asset", "picture", "icon")
        path = os.path.join(_icon_dir, _ACTION_ICON_FILES[label])
        try:
            _action_icon_srcs[label] = pygame.image.load(path).convert_alpha()
        except Exception:
            _action_icon_srcs[label] = None
    src = _action_icon_srcs.get(label)
    if src is None:
        return
    d = ar * 2
    scaled = pygame.transform.smoothscale(src, (d, d))
    # 圓形遮罩：圓外 alpha→0
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.circle(mask, (255, 255, 255, 255), (ar, ar), ar)
    scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(scaled, (cx - ar, cy - ar))

def _draw_bump_bg(surf: pygame.Surface, pr: pygame.Rect) -> None:
    """
    在行動面板（pr）頂邊繪製向上凸起的特殊行動承載區。
    凸起底部延伸至 pr.y + 14，使面板卡片（同奶霜色）自然覆蓋接縫。
    """
    cx     = pr.x + pr.width // 2
    bx     = cx - _BUMP_W // 2
    top_y  = pr.y - _BUMP_H
    full_h = _BUMP_H + 14                    # 凸起 + 與面板的重疊部份

    # 陰影
    sh_sf = pygame.Surface((_BUMP_W + 8, full_h + 6), pygame.SRCALPHA)
    pygame.draw.rect(sh_sf, (0, 0, 0, 42),
                     pygame.Rect(0, 0, _BUMP_W + 8, full_h + 6), border_radius=14)
    surf.blit(sh_sf, (bx - 2, top_y + 5))

    # 凸起本體（奶霜底色 + 深棕邊框）
    pygame.draw.rect(surf, (255, 244, 228),
                     pygame.Rect(bx, top_y, _BUMP_W, full_h), border_radius=14)
    pygame.draw.rect(surf, CYAN,
                     pygame.Rect(bx, top_y, _BUMP_W, full_h), 2, border_radius=14)

def _draw_ap_toggle_btn(surf: pygame.Surface, ar: pygame.Rect, mpos: tuple) -> None:
    """在底部行動面板頂部中央繪製折疊/展開手柄，並更新 _ap_toggle_rect。"""
    tw, th = _AP_TOGGLE_W, _AP_TOGGLE_H
    tx = ar.centerx - tw // 2
    ty = ar.y - th
    trect = pygame.Rect(tx, ty, tw, th)
    _ap_toggle_rect[0] = trect

    collapsed = _ap_collapse_val[0] > 0.5
    hover = trect.collidepoint(mpos)

    # 膠囊背景
    bg_alpha = 225 if hover else 190
    bg = pygame.Surface((tw, th), pygame.SRCALPHA)
    pygame.draw.rect(bg, (255, 244, 228, bg_alpha), (0, 0, tw, th), border_radius=th // 2)
    surf.blit(bg, trect.topleft)

    # 邊框
    bdr_col = CYAN if hover else (175, 145, 105)
    pygame.draw.rect(surf, bdr_col, trect, 1, border_radius=th // 2)

    # 中央握把線（兩條短橫線）
    grip_col = (85, 65, 45) if not hover else (45, 35, 20)
    cx, cy = trect.centerx, trect.centery
    for dy in (-2, 2):
        pygame.draw.line(surf, grip_col, (cx - 10, cy + dy), (cx + 10, cy + dy), 1)

    # 兩側小三角（▲ 展開 / ▼ 收起）
    aw, ah = 7, 4
    for sx in (cx - 20, cx + 20):
        if collapsed:   # ▲ 提示可展開
            pts = [(sx - aw//2, cy + ah//2), (sx, cy - ah//2), (sx + aw//2, cy + ah//2)]
        else:           # ▼ 提示可收起
            pts = [(sx - aw//2, cy - ah//2), (sx, cy + ah//2), (sx + aw//2, cy - ah//2)]
        pygame.draw.polygon(surf, grip_col, pts)


def _draw_action_panel(surf, fm, fs, mode, choices, log, prompt, tvalue, rect, time_left, mpos):
    """
    新版底部面板（浮動卡片）。
    rect: 整個底部區域（含 TAB_H 標籤列）
    回傳 (content_rects, end_week_btn)
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22
    M  = 8
    pr = pygame.Rect(rect.x + M, rect.y + M,
                     rect.width - M * 2, rect.height - M * 2)

    # ── 判斷是否為標準行動模式（需在投影前確定，以便決定是否畫凸起）──
    is_std_action = (mode == "choices" and
                     all(c in _STANDARD_ACTIONS for c in choices))

    # ── tab 幾何（絕對座標，僅標準行動模式使用）────────────────
    if is_std_action:
        _brx     = WIN_W - _SIDE_PANEL_W - 16
        _blx     = _brx - _BUMP_W
        _btop    = pr.y  - _BUMP_H
        _bump_cx = (_blx + _brx) // 2
        _bump_cy = (_btop + pr.y) // 2

        # tab 投影（頂部圓角）
        _TR = 12
        _tsh = pygame.Surface((_BUMP_W + 6, _BUMP_H + 6), pygame.SRCALPHA)
        pygame.draw.rect(_tsh, (0, 0, 0, 40),
                         pygame.Rect(0, 0, _BUMP_W, _BUMP_H),
                         border_top_left_radius=_TR,
                         border_top_right_radius=_TR)
        surf.blit(_tsh, (_blx + 4, _btop + 4))

    # ── 主面板投影 ──────────────────────────────────────────────
    sh = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 52),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(sh, (pr.x + 4, pr.y + 4))

    # ── 主面板卡片底色 ──────────────────────────────────────────
    card = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 244, 228, 238),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(card, pr.topleft)
    if not is_std_action:
        pygame.draw.rect(surf, CYAN, pr, 2, border_radius=14)

    # ── tab 填色 + 合體外框（主面板圓角 + tab 直角，邊線無斷裂）──
    if is_std_action:
        _PF = (255, 244, 228)
        # tab 填色（同奶霜底色，頂部圓角）
        _TR = 12
        pygame.draw.rect(surf, _PF,
                         pygame.Rect(_blx, _btop, _BUMP_W, _BUMP_H + 2),
                         border_top_left_radius=_TR,
                         border_top_right_radius=_TR)

        # 合體外框：依序畫完整輪廓（面板四個圓角 + tab 三條直角邊）
        R = 14
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(pr.x, pr.y, R * 2, R * 2),
                        math.pi / 2, math.pi, 2)                              # 左上圓角
        pygame.draw.line(surf, CYAN, (pr.x + R, pr.y), (_blx, pr.y), 2)      # 頂邊左段
        pygame.draw.line(surf, CYAN, (_blx, pr.y), (_blx, _btop + _TR), 2)    # tab 左邊
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(_blx, _btop, _TR * 2, _TR * 2),
                        math.pi / 2, math.pi, 2)                              # tab 左上圓角
        pygame.draw.line(surf, CYAN,
                         (_blx + _TR, _btop), (_brx - _TR, _btop), 2)        # tab 頂邊
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(_brx - _TR * 2, _btop, _TR * 2, _TR * 2),
                        0, math.pi / 2, 2)                                    # tab 右上圓角
        pygame.draw.line(surf, CYAN, (_brx, _btop + _TR), (_brx, pr.y), 2)   # tab 右邊
        pygame.draw.line(surf, CYAN, (_brx, pr.y), (pr.right - R, pr.y), 2)  # 頂邊右段
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(pr.right - R * 2, pr.y, R * 2, R * 2),
                        0, math.pi / 2, 2)                                    # 右上圓角
        pygame.draw.line(surf, CYAN,
                         (pr.right, pr.y + R), (pr.right, pr.bottom - R), 2) # 右邊
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(pr.right - R * 2, pr.bottom - R * 2, R * 2, R * 2),
                        3 * math.pi / 2, 2 * math.pi, 2)                     # 右下圓角
        pygame.draw.line(surf, CYAN,
                         (pr.right - R, pr.bottom), (pr.x + R, pr.bottom), 2)# 底邊
        pygame.draw.arc(surf, CYAN,
                        pygame.Rect(pr.x, pr.bottom - R * 2, R * 2, R * 2),
                        math.pi, 3 * math.pi / 2, 2)                         # 左下圓角
        pygame.draw.line(surf, CYAN,
                         (pr.x, pr.bottom - R), (pr.x, pr.y + R), 2)         # 左邊

    # ── 標籤列 ───────────────────────────────────────────────
    tab_rect    = pygame.Rect(pr.x, pr.y, pr.width, TAB_H)
    content_top = pr.y + TAB_H

    # ── 預先計算 hover 狀態（供標籤列 tooltip 使用）─────────
    hovered_action = None
    if is_std_action:
        action_choices_pre = [c for c in choices if c != "🏪 前往道具店"]
        n_pre       = len(action_choices_pre)
        r_pre       = 36
        main_aw_pre = pr.width                            # 主按鈕使用全寬
        sp_pre      = min(140, (main_aw_pre - 40) // max(n_pre, 1))
        sx_pre      = pr.x + (main_aw_pre - n_pre * sp_pre) // 2 + sp_pre // 2
        cy_pre      = content_top + r_pre + ((pr.height - TAB_H - r_pre * 2 - fs.get_height() - 8) // 2)
        for i, lbl in enumerate(action_choices_pre):
            cx_i = sx_pre + i * sp_pre
            if pygame.Rect(cx_i - r_pre - 8, cy_pre - r_pre - 8,
                           (r_pre + 8) * 2, (r_pre + 8) * 2).collidepoint(mpos):
                hovered_action = lbl
                break
        # ── 特殊按鈕 hover 偵測（主按鈕沒中才繼續）──────────────
        if hovered_action is None:
            _brx_pre    = WIN_W - _SIDE_PANEL_W - 16
            _blx_pre    = _brx_pre - _BUMP_W
            _bump_cy_pre = pr.y - _BUMP_H // 2           # 凸起垂直中心
            _sp_cx0_pre = (_blx_pre + _brx_pre) // 2     # 凸起水平中心（翹課）
            for _si_p, _sn_p in enumerate(_SPECIAL_ACTION_NAMES):
                _sp_cx_p = _sp_cx0_pre + (_si_p - 1) * _BUMP_SP
                if (_sn_p not in _special_disabled and
                        pygame.Rect(_sp_cx_p - _BUMP_R - 8, _bump_cy_pre - _BUMP_R - 8,
                                    (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2).collidepoint(mpos)):
                    hovered_action = _sn_p
                    break

    # 左側：剩餘時間點（含震動 / 紅色閃動特效）
    _now_ms      = pygame.time.get_ticks()
    _shake_elapsed = _now_ms - _time_shake_t0[0] if _time_shake_t0[0] > 0 else _TIME_SHAKE_MS
    if _time_shake_t0[0] > 0 and _shake_elapsed < _TIME_SHAKE_MS:
        _t     = _shake_elapsed / _TIME_SHAKE_MS          # 0→1
        _decay = (1.0 - _t) ** 1.5
        _offset_x = int(math.sin(_t * math.pi * 5) * 10 * _decay)
        _mix   = _decay                                   # 1→0，紅色→正常色
        _time_col = (
            int(RED[0] * _mix + WHITE[0] * (1.0 - _mix)),
            int(RED[1] * _mix + WHITE[1] * (1.0 - _mix)),
            int(RED[2] * _mix + WHITE[2] * (1.0 - _mix)),
        )
    else:
        _offset_x = 0
        _time_col = WHITE
        if _time_shake_t0[0] > 0 and _shake_elapsed >= _TIME_SHAKE_MS:
            _time_shake_t0[0] = 0   # 動畫結束後重置
    # 時鐘圖示 + 時間文字（整組跟著震動偏移）
    _CLK_R   = 9                          # 時鐘圖示半徑
    _clk_x0  = tab_rect.x + 14 + _offset_x   # 整組左起點
    _clk_cy  = tab_rect.y + TAB_H // 2       # 垂直中心
    _draw_icon_clock(surf,
                     _clk_x0 + _CLK_R,        # 圖示圓心 x
                     _clk_cy, _CLK_R,
                     col=_time_col)            # 指針顏色跟著閃動色
    time_txt = fb.render(f"剩餘時間點：{time_left}", True, _time_col)
    surf.blit(time_txt, (_clk_x0 + _CLK_R * 2 + 5,
                         tab_rect.y + (TAB_H - time_txt.get_height()) // 2))

    # 中間：狀態效果 hover 提示（優先）/ 行動 hover 提示
    _tip_x0 = _clk_x0 + _CLK_R * 2 + 5 + time_txt.get_width() + 24
    _tip_y  = tab_rect.y + (TAB_H - fb.get_height()) // 2

    if _hovered_status[0]:
        # 狀態效果 hover：顯示 "生病 1週" 等說明文字
        _st_text, _st_pos = _hovered_status[0]
        _st_col = (30, 120, 50) if _st_pos else (160, 50, 30)   # 正面→深綠；負面→深紅棕
        st_t = fb.render(_st_text, True, _st_col)
        surf.blit(st_t, (_tip_x0, _tip_y))
    elif hovered_action and hovered_action in _ACTION_INFO:
        cost_str, eff_str = _ACTION_INFO[hovered_action]
        # 社團活動：動態計算不耗體力機率 + 判斷是否有社團加成
        if hovered_action == "社團活動":
            _ap = _player[0]
            if _ap is not None:
                _lk = _ap.luck
                if _lk <= 20:
                    _lb = 0.0
                elif _lk <= 40:
                    _lb = (_lk - 20) * 0.01
                else:
                    _lb = 0.20 + (_lk - 40) * 0.005
                _free_pct = int(min(0.80, 0.30 + _lb) * 100)
                cost_str  = f"體力-3，{_free_pct}%免"
                _has_club = "club" in _ap.extra_events
                if _has_club:
                    eff_str = "滿足度+15 未知好處"
        is_restore = cost_str.startswith("恢復")
        cost_col   = GREEN if is_restore else RED
        cost_t = fb.render(cost_str, True, cost_col)
        surf.blit(cost_t, (_tip_x0, _tip_y))
        sep_x  = _tip_x0 + cost_t.get_width() + 10
        sep_t  = fs.render("|", True, GRAY)
        surf.blit(sep_t, (sep_x, _tip_y))
        eff_t  = fb.render(eff_str, True, YELLOW)
        surf.blit(eff_t, (sep_x + sep_t.get_width() + 10, _tip_y))

    # 右側：結束本週按鈕（考試週隱藏）
    if mode != "exam_ready":
        ew_btn   = pygame.Rect(pr.right - 110, tab_rect.y + 4, 100, TAB_H - 8)
        ew_hover = ew_btn.collidepoint(mpos)
        ew_dr    = _premium_btn(surf, ew_btn, (200, 78, 58), ew_hover, radius=10)
        ew_t     = fb.render("結束本週", True, PANEL)
        surf.blit(ew_t, (ew_dr.x + (ew_dr.width  - ew_t.get_width())  // 2,
                         ew_dr.y + (ew_dr.height - ew_t.get_height()) // 2))
    else:
        ew_btn = None

    content_rect = pygame.Rect(pr.x, content_top, pr.width, pr.height - TAB_H)
    content_rects = []
    _cc_btn_cache["sp_disabled_rects"] = []   # 每幀重置（供點擊無效按鈕播音效偵測）

    # ── 內容區：依模式切換 ────────────────────────────────────

    if mode == "choices" and is_std_action:
        # ── 圓形行動按鈕（左側區域；右側保留給特殊行動）─────────
        action_choices = [c for c in choices if c != "🏪 前往道具店"]
        n        = len(action_choices)
        r        = 36
        main_aw  = pr.width                 # 主按鈕使用全寬
        spacing  = min(140, (main_aw - 40) // max(n, 1))
        total_w  = n * spacing
        sx       = pr.x + (main_aw - total_w) // 2 + spacing // 2
        # 垂直：圓心上移，留空間給下方標籤
        fb      = _font_bold[0] or fs      # 粗體字型（行動標籤）
        lh      = fb.get_height()
        cy_btn  = content_top + r + ((content_rect.height - r * 2 - lh - 8) // 2)

        ms_now  = pygame.time.get_ticks()

        for i, label in enumerate(action_choices):
            cx_btn   = sx + i * spacing
            orig_idx = choices.index(label) + 1
            hover    = pygame.Rect(cx_btn - r - 8, cy_btn - r - 8,
                                   (r + 8) * 2, (r + 8) * 2).collidepoint(mpos)

            # ── 按鈕脈動：hover 時暫停，離開後自動與所有按鈕同步 ────
            # 因為全部按鈕都以 ms_now % cycle 計算，游標移開時自動銜接。
            _PULSE_CYCLE = 1000
            _PULSE_SPAN  = 500
            _t_p         = ms_now % _PULSE_CYCLE
            if hover:
                r_draw = r              # hover → 暫停脈動，固定自然大小
            elif _t_p < _PULSE_SPAN:
                _pulse_phase = (_t_p / _PULSE_SPAN) * math.tau
                r_draw = r + int(math.sin(_pulse_phase) * 3.0)
            else:
                r_draw = r              # 靜止段

            ar    = _premium_circle(surf, cx_btn, cy_btn, r_draw,
                                    BTN_N, hover, key=(cx_btn, cy_btn))
            _draw_action_icon(surf, cx_btn, cy_btn, ar, label)
            # icon 蓋住 _premium_circle 的邊框，補畫一圈
            _bdr = tuple(min(255, int(c * 1.20 + 30)) for c in BTN_N)
            pygame.draw.circle(surf, _bdr, (cx_btn, cy_btn), ar, 2)
            brect = pygame.Rect(cx_btn - r - 8, cy_btn - r - 8,
                                (r + 8) * 2, (r + 8) * 2)   # 點擊判定用原始 r

            # ── Hover 光暈：SRCALPHA 同心圓環，畫在按鈕邊框外側 ─────
            if hover:
                _glow_sz = (ar + 28) * 2
                _glow_sf = pygame.Surface((_glow_sz, _glow_sz), pygame.SRCALPHA)
                _gc      = _glow_sz // 2
                for _gr, _ga in [(ar + 24, 28), (ar + 16, 50), (ar + 8, 72)]:
                    pygame.draw.circle(_glow_sf, (160, 210, 255, _ga),
                                       (_gc, _gc), _gr, 4)
                surf.blit(_glow_sf, (cx_btn - _gc, cy_btn - _gc))

            # ── 波浪標籤：每 2 秒 1 次，hover 時靜止 ────────────────
            # 每 2000ms 週期：前 1000ms 播波浪（同速），後 1000ms 靜止；
            # 以 Hann 包絡 sin(π·t) 讓振幅平滑淡入淡出，避免首尾跳變。
            clean_label  = label.replace("🏪 ", "")
            _WAVE_CYCLE  = 2000
            _WAVE_SPAN   = 1000
            _t_w         = ms_now % _WAVE_CYCLE
            wave_amp     = 3.5    # 峰值振幅（像素）
            wave_step    = 0.9    # 相鄰字元相位差（弧度）

            ch_surfs  = [fb.render(ch, True, WHITE) for ch in clean_label]
            txt_total = sum(s.get_width() for s in ch_surfs)
            x_cur     = cx_btn - txt_total // 2
            label_y   = cy_btn + r + 16

            if hover:
                # hover → 標籤靜止，不做波浪
                for ch_s in ch_surfs:
                    surf.blit(ch_s, (x_cur, label_y))
                    x_cur += ch_s.get_width()
            elif _t_w < _WAVE_SPAN:
                _t_norm    = _t_w / _WAVE_SPAN          # 0.0 → 1.0
                _wave_base = _t_norm * math.tau          # 與原 1Hz 相同速度
                _env       = math.sin(_t_norm * math.pi) # Hann 包絡，首尾振幅→0
                for j, ch_s in enumerate(ch_surfs):
                    y_off = int(wave_amp * _env * math.sin(_wave_base - j * wave_step))
                    surf.blit(ch_s, (x_cur, label_y + y_off))
                    x_cur += ch_s.get_width()
            else:
                for ch_s in ch_surfs:                   # 靜止，全部 y_off=0
                    surf.blit(ch_s, (x_cur, label_y))
                    x_cur += ch_s.get_width()

            content_rects.append((brect, orig_idx))

        # ── 特殊行動按鈕（凸起區，已在面板繪製時計算幾何）──────────
        _sp_cy  = _bump_cy                        # 凸起垂直中心
        _sp_cx0 = _bump_cx                        # 凸起水平中心（翹課居中）
        for _si, _sn in enumerate(_SPECIAL_ACTION_NAMES):
            _sp_cx    = _sp_cx0 + (_si - 1) * _BUMP_SP
            _disabled = _sn in _special_disabled
            _sp_hover = (not _disabled and
                         pygame.Rect(_sp_cx - _BUMP_R - 8, _sp_cy - _BUMP_R - 8,
                                     (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2).collidepoint(mpos))

            # 脈動（停用 / hover 時固定）
            _SP_PULSE_CYCLE = 1000
            _SP_PULSE_SPAN  = 500
            _sp_tp = ms_now % _SP_PULSE_CYCLE
            if _disabled or _sp_hover:
                _sp_r_draw = _BUMP_R
            elif _sp_tp < _SP_PULSE_SPAN:
                _sp_pulse_phase = (_sp_tp / _SP_PULSE_SPAN) * math.tau
                _sp_r_draw = _BUMP_R + int(math.sin(_sp_pulse_phase) * 3.0)
            else:
                _sp_r_draw = _BUMP_R

            # 按鈕本體顏色（停用時灰色）
            _sp_col = (105, 105, 115) if _disabled else BTN_N
            _sp_ar  = _premium_circle(surf, _sp_cx, _sp_cy, _sp_r_draw,
                                      _sp_col, _sp_hover and not _disabled,
                                      key=(_sp_cx, _sp_cy + 9000))  # 避免 key 衝突

            # 圖示（webp icon，圓形裁切）
            _draw_action_icon(surf, _sp_cx, _sp_cy, _sp_ar, _sn)
            # icon 蓋住 _premium_circle 的邊框，補畫一圈
            _sp_bdr = (105, 105, 115) if _disabled else tuple(min(255, int(c * 1.20 + 30)) for c in BTN_N)
            pygame.draw.circle(surf, _sp_bdr, (_sp_cx, _sp_cy), _sp_ar, 2)
            # 停用時疊半透明灰膜使 icon 變暗
            if _disabled:
                _dim = pygame.Surface((_sp_ar * 2, _sp_ar * 2), pygame.SRCALPHA)
                pygame.draw.circle(_dim, (130, 130, 140, 140), (_sp_ar, _sp_ar), _sp_ar)
                surf.blit(_dim, (_sp_cx - _sp_ar, _sp_cy - _sp_ar))

            # hover 光暈
            if _sp_hover:
                _glow_sz = (_sp_ar + 28) * 2
                _glow_sf = pygame.Surface((_glow_sz, _glow_sz), pygame.SRCALPHA)
                _gc2     = _glow_sz // 2
                for _gr2, _ga2 in [(_sp_ar + 24, 28), (_sp_ar + 16, 50), (_sp_ar + 8, 72)]:
                    pygame.draw.circle(_glow_sf, (160, 210, 255, _ga2),
                                       (_gc2, _gc2), _gr2, 4)
                surf.blit(_glow_sf, (_sp_cx - _gc2, _sp_cy - _gc2))

            # 停用倒數數字 overlay
            if _disabled:
                _cd_val  = _special_disabled[_sn]
                _cd_str  = str(_cd_val)
                _cd_s    = fb.render(_cd_str, True, (220, 100, 60))
                surf.blit(_cd_s, (_sp_cx + _sp_ar // 2 - _cd_s.get_width() // 2,
                                  _sp_cy + _sp_ar // 2 - _cd_s.get_height() // 2))
            # 熬夜次數計數器（右下角常駐）
            elif _sn == "熬夜" and _allnighter_count[0] > 0:
                _cnt_str = f"{_allnighter_count[0]}/5"
                _cnt_col = (230, 80, 50) if _allnighter_count[0] >= 4 else (220, 160, 60)
                _cnt_s   = fb.render(_cnt_str, True, _cnt_col)
                _cnt_bx  = _sp_cx + _sp_ar // 2 - _cnt_s.get_width() // 2
                _cnt_by  = _sp_cy + _sp_ar // 2 - _cnt_s.get_height() // 2
                # 小黑底板增加可讀性
                _cnt_bg  = pygame.Surface((_cnt_s.get_width() + 4, _cnt_s.get_height() + 2),
                                          pygame.SRCALPHA)
                _cnt_bg.fill((0, 0, 0, 160))
                surf.blit(_cnt_bg, (_cnt_bx - 2, _cnt_by - 1))
                surf.blit(_cnt_s,  (_cnt_bx, _cnt_by))

            # 波浪標籤（與主按鈕相同邏輯）
            _sp_clean   = _sn
            _SP_WAVE_CYCLE = 2000
            _SP_WAVE_SPAN  = 1000
            _sp_tw     = ms_now % _SP_WAVE_CYCLE
            _sp_wave_amp  = 3.5
            _sp_wave_step = 0.9
            _sp_ch_surfs  = [fb.render(ch, True, WHITE if not _disabled else (140, 140, 150))
                             for ch in _sp_clean]
            _sp_txt_total = sum(s.get_width() for s in _sp_ch_surfs)
            _sp_x_cur     = _sp_cx - _sp_txt_total // 2
            _sp_label_y   = _sp_cy + _BUMP_R + 12

            if _sp_hover:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()
            elif _disabled:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()
            elif _sp_tw < _SP_WAVE_SPAN:
                _sp_t_norm    = _sp_tw / _SP_WAVE_SPAN
                _sp_wave_base = _sp_t_norm * math.tau
                _sp_env       = math.sin(_sp_t_norm * math.pi)
                for j2, _ch_s in enumerate(_sp_ch_surfs):
                    _y_off2 = int(_sp_wave_amp * _sp_env * math.sin(_sp_wave_base - j2 * _sp_wave_step))
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y + _y_off2))
                    _sp_x_cur += _ch_s.get_width()
            else:
                for _ch_s in _sp_ch_surfs:
                    surf.blit(_ch_s, (_sp_x_cur, _sp_label_y))
                    _sp_x_cur += _ch_s.get_width()

            # 點擊判定（停用時不加入 content_rects，但保留 rect 供無效點擊音效偵測）
            _sp_brect = pygame.Rect(_sp_cx - _BUMP_R - 8, _sp_cy - _BUMP_R - 8,
                                    (_BUMP_R + 8) * 2, (_BUMP_R + 8) * 2)
            if not _disabled:
                content_rects.append((_sp_brect, -(_si + 1)))
            else:
                _cc_btn_cache["sp_disabled_rects"].append(_sp_brect)

    elif mode == "choices" and not is_std_action:
        # ── 非標準選項：上方顯示最新 log（題目文字），下方按鈕作答 ──
        LOG_LINES = 3
        lh_log    = fs.get_height() + 4
        log_h     = LOG_LINES * lh_log + 6
        log_area  = pygame.Rect(content_rect.x, content_rect.y,
                                content_rect.width, log_h)
        _draw_panel_log(surf, fs, log, log_area, lines=LOG_LINES)

        # 按鈕區從 log 下方開始
        bw   = (pr.width - 36) // 2 - 6
        bh   = 40
        px   = pr.x + 12
        py   = content_top + log_h + 6
        for i, label in enumerate(choices):
            col = i % 2
            row = i // 2
            br    = pygame.Rect(px + col * (bw + 12), py + row * (bh + 8), bw, bh)
            hover = br.collidepoint(mpos)
            dr    = _premium_btn(surf, br, (238, 210, 170), hover, radius=12)
            lw = _measure_mixed(fb, label)
            _render_mixed(surf, fb, label, WHITE,
                          dr.x + (dr.width  - lw) // 2,
                          dr.y + (dr.height - fb.get_height()) // 2)
            content_rects.append((br, i + 1))

    elif mode == "yn":
        # ── prompt 提示 + 是 / 否 按鈕 + 最新 log ────────────
        BTN_H2, BTN_W2, BTN_SP = 44, 128, 14
        btn_y   = content_top + content_rect.height - BTN_H2 - 8
        prompt_y = btn_y - fs.get_height() - 8
        _draw_panel_log(surf, fs, log, content_rect, lines=2)
        # prompt 文字（紅色，顯示於按鈕正上方）
        if prompt[0]:
            for j, pln in enumerate(_wrap(prompt[0], fs, content_rect.width - 28)):
                _render_mixed(surf, fs, pln, RED, pr.x + 14,
                              prompt_y - (len(_wrap(prompt[0], fs, content_rect.width - 28)) - 1 - j)
                              * (fs.get_height() + 3))
        for i, (label, val) in enumerate([(_yn_labels[1], False), (_yn_labels[0], True)]):
            br    = pygame.Rect(pr.x + 14 + i * (BTN_W2 + BTN_SP), btn_y, BTN_W2, BTN_H2)
            hover = br.collidepoint(mpos)
            if val:
                col_b = _yn_yes_color[0] if _yn_yes_color[0] is not None else BTN_N
            else:
                col_b = _yn_no_color[0]  if _yn_no_color[0]  is not None else DARK_GRAY
            dr    = _premium_btn(surf, br, col_b, hover, radius=12)
            lw = _measure_mixed(fb_lg, label)
            _render_mixed(surf, fb_lg, label, PANEL,
                          dr.x + (dr.width  - lw) // 2,
                          dr.y + (dr.height - fb_lg.get_height()) // 2)
            content_rects.append((br, val))

    elif mode == "text":
        # ── 文字輸入框 ────────────────────────────────────────
        _draw_panel_log(surf, fs, log, content_rect, lines=2)
        surf.blit(fs.render(prompt[0], True, GRAY),
                  (pr.x + 14, content_top + content_rect.height - 88))
        ir2 = pygame.Rect(pr.x + 14, content_top + content_rect.height - 64, pr.width - 140, 36)
        pygame.draw.rect(surf, MILK, ir2, border_radius=10)
        t_done = fm.render(tvalue[0], True, BLACK)
        t_comp = fm.render(_composing[0], True, (150, 90, 180)) if _composing[0] else None
        t_cur  = fm.render("|", True, BLACK)
        xo = ir2.x + 8
        surf.blit(t_done, (xo, ir2.y + 5)); xo += t_done.get_width()
        if t_comp:
            surf.blit(t_comp, (xo, ir2.y + 5)); xo += t_comp.get_width()
        surf.blit(t_cur, (xo, ir2.y + 5))
        ok    = pygame.Rect(pr.right - 118, ir2.y, 104, 36)
        ok_dr = _premium_btn(surf, ok, BTN_N, ok.collidepoint(mpos), radius=12)
        ot    = fb_lg.render("確認", True, PANEL)
        surf.blit(ot, (ok_dr.x + (ok_dr.width  - ot.get_width())  // 2,
                       ok_dr.y + (ok_dr.height - ot.get_height()) // 2))
        content_rects.append((ok, "__ok__"))

    elif mode == "story":
        # ── 劇情對話框（VN 風格）────────────────────────────
        idx = _story_index[0]
        if 0 <= idx < len(_story_lines):
            entry   = _story_lines[idx]
            speaker = entry.get("speaker", "")
            text    = entry.get("text", "")
        else:
            speaker = ""
            text    = ""

        PAD      = 16
        text_top = content_rect.y + PAD

        # 說話者名稱框（左上角）
        if speaker:
            spk_w    = _measure_mixed(fb_lg, speaker) + 20
            spk_h    = fb_lg.get_height() + 6
            spk_rect = pygame.Rect(content_rect.x + PAD,
                                   content_rect.y + 6, spk_w, spk_h)
            pygame.draw.rect(surf, BTN_N, spk_rect, border_radius=6)
            pygame.draw.rect(surf, CYAN,  spk_rect, 1, border_radius=6)
            _render_mixed(surf, fb_lg, speaker, PANEL,
                          spk_rect.x + 10,
                          spk_rect.y + (spk_h - fb_lg.get_height()) // 2)
            text_top = spk_rect.bottom + 8

        # 劇情文字（自動換行）
        wrapped = _wrap(text, fm, content_rect.width - PAD * 2)
        for ln in wrapped:
            _render_mixed(surf, fm, ln, WHITE,
                          content_rect.x + PAD, text_top)
            text_top += fm.get_height() + 4

        # ▼ 點擊繼續（右下角，0.5 Hz 閃爍）
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            arr = fs.render("▼ 點擊繼續", True, BTN_N)
            surf.blit(arr, (content_rect.right - arr.get_width() - PAD,
                            content_rect.bottom - arr.get_height() - 6))

    elif mode == "exam_ready":
        # ── 考試開始按鈕（單一大按鈕，居中）────────────────────
        ex_label = _exam_ready_label[0]
        bw_ex    = min(320, content_rect.width - 48)
        bh_ex    = 56
        bx_ex    = content_rect.x + (content_rect.width - bw_ex) // 2
        by_ex    = content_rect.y + (content_rect.height - bh_ex) // 2
        br_ex    = pygame.Rect(bx_ex, by_ex, bw_ex, bh_ex)
        ex_hover = br_ex.collidepoint(mpos)
        _premium_btn(surf, br_ex, (180, 80, 30), ex_hover, radius=14)
        lt_ex = fb_lg.render(ex_label, True, PANEL)
        surf.blit(lt_ex, (br_ex.x + (br_ex.width  - lt_ex.get_width())  // 2,
                          br_ex.y + (br_ex.height - lt_ex.get_height()) // 2))
        content_rects.append((br_ex, 1))

    else:
        # ── 敘述模式（mode == None）：顯示最新 log ────────────
        _draw_panel_log(surf, fs, log, content_rect, lines=6)

    # ── 折疊/展開手柄（始終顯示於面板頂部中央）────────────────
    _draw_ap_toggle_btn(surf, rect, mpos)

    return content_rects, ew_btn

def _draw_panel_log(surf, fs, log, rect, lines=5):
    """在 rect 內顯示 log 最後 N 行（敘述模式輔助函式）。"""
    lh   = fs.get_height() + 4
    show = log[-(lines):]
    for i, line in enumerate(show):
        if line.startswith(("⚡", "💥", "📅", "📋", "🎓", "✍")):
            col = YELLOW
        elif line.startswith(("❌", "💀", "😞", "⚠", "💔", "📉")):
            col = RED
        elif line.startswith(("✅", "🌟", "🎉", "✨", "💰", "📚")):
            col = GREEN
        else:
            col = WHITE
        _render_mixed(surf, fs, line, col,
                      rect.x + 14, rect.y + 8 + i * lh)

def _draw_exam_stress_fx(surf: pygame.Surface) -> None:
    """
    考前壓力視覺特效：
      距期中（第 8 週）或期末（第 16 週）剩 ≤ 2 週時
        → 各面板邊框套用紅色顫抖鬼影效果。
      距考試剩 1 週時
        → 額外在全畫面疊加微量紅色底色。
    """
    week = _week[0]
    if week <= 0:
        return

    # 計算距最近考試的週數
    dist_mid = 8  - week if week < 8  else 999
    dist_fin = 16 - week if week < 16 else 999
    dist     = min(dist_mid, dist_fin)

    if dist > 2 or dist <= 0:
        return

    # ── 各面板邊框 Rect（與 _draw_status_v2 / _side_panel_bg 對齊）──
    M  = 8
    PW = _SIDE_PANEL_W
    panels = [
        (pygame.Rect(M,             M,               WIN_W - M*2,  STATUS_H - M*2), 14),
        (pygame.Rect(M,             STATUS_H + M,    PW,           CHAR_H - M*2),   13),
        (pygame.Rect(WIN_W - M - PW, STATUS_H + M,  PW,           CHAR_H - M*2),   13),
        (pygame.Rect(M,             STATUS_H + CHAR_H + M, WIN_W - M*2, ACTION_H - M*2), 14),
    ]

    # 單張合併疊加 Surface → 只 blit 一次（重用，不重建）
    overlay = _get_sfx_surf("ap_exam_overlay")

    # dist == 1：全畫面底色微微泛紅
    if dist == 1:
        overlay.fill((200, 30, 20, 22))   # alpha ≈ 8.6%，極淡紅暈

    # 邊框顫抖：用時間種子亂數產生偏移，每 80 ms 換一次 → 顫抖感
    now = pygame.time.get_ticks()
    rng = random.Random(now // 80)
    amp = 3 if dist == 1 else 2           # 越近考試抖得越厲害
    red = (215, 68, 62)                   # 草莓紅（= RED 常數）

    for rect, brad in panels:
        for layer_i in range(3):
            alpha = 70 - layer_i * 20     # 70 → 50 → 30
            dx    = rng.randint(-amp, amp)
            dy    = rng.randint(-amp, amp)
            pygame.draw.rect(
                overlay,
                (*red, alpha),
                pygame.Rect(rect.x + dx, rect.y + dy, rect.width, rect.height),
                2, border_radius=brad,
            )

    surf.blit(overlay, (0, 0))

def _side_panel_bg(surf: pygame.Surface, x: int, y: int, w: int, h: int) -> None:
    """繪製白色筆記本卡片底色（陰影 + 奶白底 + 暖棕邊框）。"""
    # 投影
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 48), pygame.Rect(0, 0, w, h), border_radius=13)
    surf.blit(sh, (x + 3, y + 4))
    # 卡片底色
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (251, 248, 243, 242), pygame.Rect(0, 0, w, h), border_radius=13)
    surf.blit(bg, (x, y))
    # 邊框
    pygame.draw.rect(surf, (185, 163, 138), pygame.Rect(x, y, w, h), 1, border_radius=13)

def _draw_exp_panel(surf: pygame.Surface, fm, fmic, player, x_offset: int = 0) -> None:
    """左側：各科課業熟練度面板（動態，含加簽科目）。"""
    if player is None:
        return
    fb    = _font_bold[0]    or fmic   # size-17 bold（科目名 / 徽章）
    fb_lg = _font_bold_lg[0] or fm    # size-22 bold（標題）
    PW  = _SIDE_PANEL_W
    PAD = 9
    sx, sy = 8 + x_offset, STATUS_H + 8
    sh  = CHAR_H - 16

    _side_panel_bg(surf, sx, sy, PW, sh)

    # 標題
    title = fb_lg.render("課業熟練度", True, YELLOW)
    surf.blit(title, (sx + (PW - title.get_width()) // 2, sy + 7))
    div_y = sy + 7 + title.get_height() + 5
    pygame.draw.line(surf, (205, 188, 168),
                     (sx + PAD, div_y), (sx + PW - PAD, div_y))

    # 動態科目列表（排除輔助鍵 "綜合"）
    subjects = [(k, v) for k, v in player.subject_exp.items() if k != "綜合"]
    n     = max(len(subjects), 1)
    content_h = sy + sh - 6 - (div_y + 8)
    row_h = content_h // n
    bar_h = max(8, min(13, row_h - fb.get_height() - 5))
    bar_w = PW - PAD * 2
    row_y = div_y + 8

    for full, exp in subjects:
        short = _SUBJ_SHORT_NAMES.get(full, full[:3])
        # 計算等級
        lvl = 0
        for i, thr in enumerate(_EXP_LVL_THR):
            if exp >= thr:
                lvl = i
        col      = _EXP_LVL_COLORS[lvl]
        lvl_name = _EXP_LVL_NAMES[lvl]

        # 科目短名（左）+ 等級徽章（右）
        lbl   = fb.render(short, True, WHITE)
        badge = fmic.render(lvl_name, True, col)
        surf.blit(lbl,   (sx + PAD, row_y))
        surf.blit(badge, (sx + PW - PAD - badge.get_width(),
                          row_y + (fb.get_height() - badge.get_height()) // 2))

        # 進度條
        by = row_y + fb.get_height() + 2
        pygame.draw.rect(surf, (215, 204, 192),
                         pygame.Rect(sx + PAD, by, bar_w, bar_h), border_radius=4)
        fw = int(bar_w * exp / 100)
        if fw > 0:
            pygame.draw.rect(surf, col,
                             pygame.Rect(sx + PAD, by, fw, bar_h), border_radius=4)

        # exp 數字（置中於條內）
        val_lbl = fmic.render(f"{exp}/100", True, PANEL)
        surf.blit(val_lbl, (sx + PAD + (bar_w - val_lbl.get_width()) // 2,
                            by + (bar_h - val_lbl.get_height()) // 2))

        row_y += row_h

def _draw_grade_panel(surf: pygame.Surface, fm, fmic, player, x_offset: int = 0) -> None:
    """右側：已發生成績記錄面板（未公布項目顯示 ──）。"""
    if player is None:
        return
    fb_lg = _font_bold_lg[0] or fm   # 粗體 size-22（標題 / 科目名 / 分數）
    PW  = _SIDE_PANEL_W
    PAD = 9
    sx  = WIN_W - 8 - PW + x_offset
    sy  = STATUS_H + 8
    sh  = CHAR_H - 16

    _side_panel_bg(surf, sx, sy, PW, sh)

    # 標題
    title = fb_lg.render("成績記錄", True, YELLOW)
    surf.blit(title, (sx + (PW - title.get_width()) // 2, sy + 7))
    div_y = sy + 7 + title.get_height() + 5
    pygame.draw.line(surf, (205, 188, 168),
                     (sx + PAD, div_y), (sx + PW - PAD, div_y))

    # 參與度始終顯示（實時更新）；其餘欄位須公布後且有分數才顯示
    _revealed = getattr(player, "revealed_grades", set())
    active_rows = [(label, key, weight)
                   for label, key, weight in _GRADE_ROWS
                   if key == "參與度"
                   or (key in _revealed and player.grades.get(key, 0.0) > 0.0)]

    if not active_rows:
        hint = fmic.render("尚無成績記錄", True, GRAY)
        surf.blit(hint, (sx + (PW - hint.get_width()) // 2, div_y + 14))
        return

    content_h = sy + sh - 6 - (div_y + 8)
    row_h     = content_h // len(active_rows)
    row_y     = div_y + 8

    fb = _font_bold[0] or fm   # size-17（佔比標籤，比 fmic 更易閱讀）

    for label, key, weight in active_rows:
        val = player.grades.get(key, 0.0)

        # 第一行：科目名（左）+ 分數（右），同行排列
        lbl_s   = fb_lg.render(label, True, WHITE)
        col     = GREEN if val >= 80 else (YELLOW if val >= 60 else RED)
        score_s = fb_lg.render(f"{val:.1f}", True, col)
        surf.blit(lbl_s,   (sx + PAD, row_y))
        surf.blit(score_s, (sx + PW - PAD - score_s.get_width(), row_y))

        # 第二行：佔比（size-17，適當放大、偏左縮排）
        wt_s = fb.render(weight, True, (160, 110, 65))
        surf.blit(wt_s, (sx + PAD + 2, row_y + fb_lg.get_height() + 2))

        row_y += row_h

def _draw_roll_call_note(surf: pygame.Surface, fmic, x_offset: int = 0) -> None:
    """
    在成績記錄面板左側繪製點名警示便利貼。
    _roll_call_course[0] 為空字串時不顯示。
    x_offset：水平位移（供面板收起動畫使用）。
    """
    course = _roll_call_course[0]
    if not course:
        return

    fb = _font_bold[0] or fmic

    # ── 便利貼 Surface（100×68 px）────────────────────────────
    NW, NH = 100, 68
    note = pygame.Surface((NW, NH), pygame.SRCALPHA)

    # 主底色（亮黃便利貼）
    pygame.draw.rect(note, (255, 228, 52, 242),
                     pygame.Rect(0, 0, NW, NH), border_radius=4)

    # 折角（右下角）
    pygame.draw.polygon(note, (196, 162, 18, 230),
                        [(NW - 14, NH), (NW, NH - 14), (NW, NH)])
    pygame.draw.line(note, (155, 128, 8, 190),
                     (NW - 14, NH - 1), (NW, NH - 14), 1)

    # 頂部警示色帶（深橘紅）
    pygame.draw.rect(note, (210, 52, 42, 225),
                     pygame.Rect(0, 0, NW, 15), border_radius=4)

    # 色帶文字
    tape_s = fmic.render("點 名 通 知", True, (255, 240, 230))
    note.blit(tape_s, ((NW - tape_s.get_width()) // 2,
                        (15 - tape_s.get_height()) // 2))

    # 課程短名（粗體，置中）
    short = _SUBJ_SHORT_NAMES.get(course, course[:4])
    sub_s = fb.render(short, True, (80, 42, 10))
    note.blit(sub_s, ((NW - sub_s.get_width()) // 2, 20))

    if _roll_call_xed[0]:
        # ── 點名課已被翹掉：紅色大叉 ─────────────────────────────
        tint = pygame.Surface((NW, NH - 15), pygame.SRCALPHA)
        pygame.draw.rect(tint, (220, 40, 40, 55),
                         pygame.Rect(0, 0, NW, NH - 15), border_radius=4)
        note.blit(tint, (0, 15))
        xc = (185, 32, 32)
        pygame.draw.line(note, xc, (18, 28), (82, 64), 6)   # 左上→右下
        pygame.draw.line(note, xc, (82, 28), (18, 64), 6)   # 右上→左下
        # 抗鋸齒端點補圓
        for pt in [(18, 28), (82, 64), (82, 28), (18, 64)]:
            pygame.draw.circle(note, xc, pt, 3)
    elif _roll_call_attended[0]:
        # ── 已出席：綠色大勾 ─────────────────────────────────────
        tint = pygame.Surface((NW, NH - 15), pygame.SRCALPHA)
        pygame.draw.rect(tint, (60, 200, 90, 48),
                         pygame.Rect(0, 0, NW, NH - 15), border_radius=4)
        note.blit(tint, (0, 15))
        chk = (30, 185, 65)
        pygame.draw.line(note, chk, (22, 52), (36, 62), 5)
        pygame.draw.line(note, chk, (36, 62), (78, 28), 5)
        pygame.draw.circle(note, chk, (36, 62), 3)
    else:
        # 提示小字（兩行）
        r1 = fmic.render("本週將點名", True, (120, 68, 18))
        r2 = fmic.render("記得出席！", True, (160, 78, 18))
        note.blit(r1, ((NW - r1.get_width()) // 2, 44))
        note.blit(r2, ((NW - r2.get_width()) // 2, 56))

    # ── 旋轉 -8°（便利貼略歪，增加手感）─────────────────────
    rotated = pygame.transform.rotate(note, -8)
    rw, rh  = rotated.get_size()

    # ── 定位：成績面板左邊緣偏左 24 px 為便利貼中心 ──────────
    PW = _SIDE_PANEL_W
    cx = WIN_W - 8 - PW - 24 + x_offset   # 隨成績面板同步平移
    cy = STATUS_H + 8 + 130               # 175 + 8 + 130 = 313

    # 陰影（偏移 +5, +6 的半透明矩形）
    shad_sf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    pygame.draw.rect(shad_sf, (0, 0, 0, 55),
                     pygame.Rect(0, 0, rw, rh), border_radius=6)
    surf.blit(shad_sf, (cx - rw // 2 + 5, cy - rh // 2 + 6))

    # 便利貼本體
    surf.blit(rotated, (cx - rw // 2, cy - rh // 2))


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
