# ============================================================
#  ui_draw_hud.py -- Status bar, icons, log area, week calendar
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

# ── 狀態效果 Emoji 對應表 ─────────────────────────────────────
_STATUS_EMOJI = {
    "生病":    "🤒",
    "無力狀態": "😔",
    "神采奕奕": "✨",
    "激勵":    "💪",
    "幸運":    "🍀",
}
# 各狀態 emoji 的自訂渲染顏色（近似原色，彌補單色字型的限制）
_STATUS_EMOJI_COLOR = {
    "🤒": (130, 210, 235),   # 淡青藍 — 病懨懨
    "😔": (160, 148, 132),   # 暖灰   — 無力
    "✨": (255, 215,  60),   # 金黃   — 神采奕奕
    "💪": (255, 130,  50),   # 橘     — 激勵
    "🍀": ( 70, 200,  90),   # 嫩綠   — 幸運
}
# 正面/負面顏色區分
_STATUS_POS = {"神采奕奕", "激勵", "幸運"}   # GREEN；其餘 RED
_FW_DIGITS  = "０１２３４５６７８９"

def _fw_num(v: int) -> str:
    """整數轉全形數字；v == 0（條件型狀態）→ '∞'"""
    return "∞" if v == 0 else "".join(_FW_DIGITS[int(d)] for d in str(v))

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

    _dn = player.de_level.get("name", "") if hasattr(player, "de_level") else ""
    surf.blit(fm.render(f"【{player.name}】 {player.department}{' ' + _dn if _dn else ''}", True, TITLE), (x, y))
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
    sc = YELLOW
    pygame.draw.rect(surf, DARK_GRAY, (x, y, bw, bh))
    pygame.draw.rect(surf, sc, (x, y, int(bw * sr), bh))
    surf.blit(fs.render(f"自我滿足度 {player.satisfaction}%", True, WHITE),
              (x + bw + 8, y))
    y += bh + gap

    if player.status_effects:
        ex = x
        em_f = _get_emoji_font(fs.get_height() + 2)
        for sname, sv in player.status_effects.items():
            em_ch  = _STATUS_EMOJI.get(sname, "❓")
            num_ch = _fw_num(sv)
            col    = GREEN if sname in _STATUS_POS else RED
            em_col = _STATUS_EMOJI_COLOR.get(em_ch, WHITE)
            em_s   = em_f.render(em_ch, True, em_col) if em_f else None
            num_s  = fs.render(num_ch, True, col)
            if em_s:
                surf.blit(em_s,  (ex, y + (num_s.get_height() - em_s.get_height()) // 2))
                ex += em_s.get_width() + 1
            surf.blit(num_s, (ex, y))
            ex += num_s.get_width() + 8

def _draw_icon_cart(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """購物車小圖示（純 pygame.draw，不使用外部資源）。"""
    # r 為半高基準；整體大小約 r*2.2 × r*1.8
    body_w = max(6, int(r * 1.8))
    body_h = max(4, int(r * 1.1))
    bx     = cx - body_w // 2
    by     = cy - body_h // 2 + max(1, r // 5)   # 略下移讓圖示視覺居中

    # 車身（圓角矩形）
    pygame.draw.rect(surf, (93, 64, 55), pygame.Rect(bx, by, body_w, body_h), border_radius=2)
    pygame.draw.rect(surf, (140, 100, 65), pygame.Rect(bx, by, body_w, body_h), 1, border_radius=2)

    # 車架柄（左斜線 → 上延伸）
    handle_rx = bx - max(2, r // 3)
    handle_ty = by - max(3, int(r * 0.8))
    pygame.draw.line(surf, (93, 64, 55), (bx, by), (handle_rx, handle_ty), max(1, r // 5))

    # 車輪（兩個小圓）
    whl_r = max(2, r // 3)
    whl_y = by + body_h + whl_r
    pygame.draw.circle(surf, (93, 64, 55),  (bx + body_w // 4,         whl_y), whl_r)
    pygame.draw.circle(surf, (93, 64, 55),  (bx + body_w * 3 // 4,     whl_y), whl_r)
    pygame.draw.circle(surf, (200, 170, 130),(bx + body_w // 4,         whl_y), max(1, whl_r - 1))
    pygame.draw.circle(surf, (200, 170, 130),(bx + body_w * 3 // 4,     whl_y), max(1, whl_r - 1))

def _draw_week_calendar(surf: pygame.Surface,
                        fm, cx: int, cy: int, week: int) -> None:
    """
    日曆式週次顯示器：以翻頁日曆造型大字呈現當前週次。
    頂部深紅標題列 + 裝訂環 + 主體白底大字。
    """
    fb_xl = _font_bold_xl[0] or fm
    fmic  = _font_micro[0]

    CAL_W  = 108   # 日曆卡片寬度
    CAL_H  = 112   # 日曆卡片高度
    HDR_H  = 28    # 頂部紅色標題列高度
    RADIUS = 8
    RING_R = 5     # 裝訂環半徑

    sx = cx - CAL_W // 2
    sy = cy - CAL_H // 2
    outer = pygame.Rect(sx, sy, CAL_W, CAL_H)

    cal = pygame.Surface((CAL_W, CAL_H), pygame.SRCALPHA)

    # ── 主體（米白）────────────────────────────────────────────
    pygame.draw.rect(cal, (255, 249, 237, 255),
                     pygame.Rect(0, 0, CAL_W, CAL_H), border_radius=RADIUS)

    # ── 頂部標題列（深紅，僅上方圓角）─────────────────────────
    pygame.draw.rect(cal, (188, 50, 40, 255),
                     pygame.Rect(0, 0, CAL_W, HDR_H), border_radius=RADIUS)
    # 蓋掉標題列下方多餘的圓角（讓下邊緣平整）
    pygame.draw.rect(cal, (188, 50, 40, 255),
                     pygame.Rect(0, RADIUS, CAL_W, HDR_H - RADIUS))

    # 標題文字「本週」
    if fmic is not None:
        hdr_t = fmic.render("本  週", True, (255, 215, 195))
        cal.blit(hdr_t, ((CAL_W - hdr_t.get_width()) // 2,
                         (HDR_H - hdr_t.get_height()) // 2))

    # ── 裝訂環（位於頂邊，橫跨標題列上緣）─────────────────────
    for ring_cx in [CAL_W // 3, CAL_W * 2 // 3]:
        ring_cy = RING_R + 1
        # 環柱（深棕色小矩形）
        pygame.draw.rect(cal, (70, 46, 25),
                         pygame.Rect(ring_cx - 3, 0, 6, ring_cy + RING_R))
        # 外環
        pygame.draw.circle(cal, (110, 78, 44), (ring_cx, ring_cy), RING_R)
        # 孔洞
        pygame.draw.circle(cal, (35, 20, 10), (ring_cx, ring_cy), max(2, RING_R - 2))

    # ── 週次大字（置中於主體區域）──────────────────────────────
    body_y = HDR_H
    body_h = CAL_H - HDR_H
    week_t = fb_xl.render(f"第{week}週", True, (72, 38, 18))
    # 若文字超寬則改用 fb_lg
    if week_t.get_width() > CAL_W - 8:
        _fb_lg = _font_bold_lg[0] or fm
        week_t = _fb_lg.render(f"第{week}週", True, (72, 38, 18))
    cal.blit(week_t, ((CAL_W - week_t.get_width()) // 2,
                      body_y + (body_h - week_t.get_height()) // 2 - 2))

    # ── 底部細線裝飾（模擬日曆頁格線）─────────────────────────
    deco_y = CAL_H - 9
    pygame.draw.line(cal, (210, 195, 175),
                     (12, deco_y), (CAL_W - 12, deco_y))

    # ── 卡片邊框 ────────────────────────────────────────────────
    pygame.draw.rect(cal, (148, 108, 70, 255),
                     pygame.Rect(0, 0, CAL_W, CAL_H), 1, border_radius=RADIUS)

    # ── 投影 + 貼圖 ─────────────────────────────────────────────
    _soft_shadow(surf, outer, radius=RADIUS, alpha=52, offset=(0, 5))
    surf.blit(cal, (sx, sy))

def _get_intel_level_ui(intel: int) -> int:
    """根據智力數值回傳等階索引（0–4），供狀態欄顯示用。"""
    for lvl in range(len(_INTEL_THRESHOLDS_UI) - 1, -1, -1):
        if intel >= _INTEL_THRESHOLDS_UI[lvl]:
            return lvl
    return 0

def _draw_icon_coin(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """金幣圖示：立體金圓＋高光。r 為外圓半徑。"""
    # 陰影（右下偏移 1px）
    pygame.draw.circle(surf, (140, 100, 10), (cx + 1, cy + 1), r)
    # 主體（深金）
    pygame.draw.circle(surf, (210, 158, 24), (cx, cy), r)
    # 亮面（較淺金，去掉外緣 2px）
    if r > 3:
        pygame.draw.circle(surf, (248, 210, 60), (cx, cy), r - 2)
    # 高光點（左上）
    if r >= 6:
        pygame.draw.circle(surf, (255, 245, 160),
                           (cx - max(1, r // 3), cy - max(1, r // 3)),
                           max(1, r // 4))
    # 邊框（深金色）
    pygame.draw.circle(surf, (160, 115, 15), (cx, cy), r, 1)
    # 內環裝飾線
    if r >= 5:
        pygame.draw.circle(surf, (185, 140, 22), (cx, cy), max(1, r - 3), 1)

def _draw_icon_clock(surf: pygame.Surface, cx: int, cy: int, r: int,
                     col: tuple = (93, 64, 55)) -> None:
    """時鐘圖示：錶盤＋時針＋分針。col 控制邊框與指針顏色（支援動畫色）。"""
    face = (255, 250, 236)
    # 錶盤
    pygame.draw.circle(surf, face, (cx, cy), r)
    pygame.draw.circle(surf, col,  (cx, cy), r, 1)
    # 時針（短，指向 10 點方向）
    ha  = math.radians(-60)   # 10 點 = -60° from 12
    hx  = cx + int(math.sin(ha) * r * 0.50)
    hy  = cy - int(math.cos(ha) * r * 0.50)
    pygame.draw.line(surf, col, (cx, cy), (hx, hy), max(1, r // 5))
    # 分針（長，指向 12 點方向）
    mx2 = cx
    my2 = cy - int(r * 0.78)
    pygame.draw.line(surf, col, (cx, cy), (mx2, my2), max(1, r // 6))
    # 中心點
    pygame.draw.circle(surf, col, (cx, cy), max(1, r // 5))

def _draw_icon_brain(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """大腦圖示：兩半球 + 中央縱溝 + 腦回折痕弧線 + 高光。"""
    pink  = (232, 148, 148)   # 腦組織粉紅
    dark  = (175,  78,  78)   # 深玫瑰（輪廓 / 折痕）
    light = (252, 208, 208)   # 高光粉

    _pad = 2
    sz   = (r + _pad) * 2
    bs   = pygame.Surface((sz, sz), pygame.SRCALPHA)
    bx = by = sz // 2

    hl  = max(3, int(r * 0.60))            # 半球半徑
    sep = max(1, int(r * 0.26))            # 半球圓心離中軸距離
    hcy = by - max(1, int(r * 0.12))       # 半球圓心略偏上
    lhx = bx - sep                         # 左半球圓心 x
    rhx = bx + sep                         # 右半球圓心 x

    # ── 填充：左右半球 + 底部連接（小腦區）──────────────────
    pygame.draw.circle(bs, pink, (lhx, hcy), hl)
    pygame.draw.circle(bs, pink, (rhx, hcy), hl)
    bot_rect = pygame.Rect(bx - int(r * 0.55), by - int(r * 0.05),
                           int(r * 1.1), int(r * 0.75))
    pygame.draw.ellipse(bs, pink, bot_rect)

    # ── 輪廓 ─────────────────────────────────────────────────
    pygame.draw.circle(bs, dark, (lhx, hcy), hl, 1)
    pygame.draw.circle(bs, dark, (rhx, hcy), hl, 1)
    pygame.draw.ellipse(bs, dark, bot_rect, 1)

    # ── 中央縱溝 ─────────────────────────────────────────────
    pygame.draw.line(bs, dark,
                     (bx, hcy - hl + max(1, int(r * 0.15))),
                     (bx, by  + int(r * 0.55)), 1)

    # ── 腦回折痕（向下開口弧線＝溝回）──────────────────────
    fw = max(4, int(r * 0.55))
    fh = max(3, int(r * 0.38))
    fy = hcy - int(r * 0.05)
    pygame.draw.arc(bs, dark,
                    pygame.Rect(lhx - fw // 2, fy, fw, fh),
                    math.pi, math.tau, 1)   # 左半球折痕
    pygame.draw.arc(bs, dark,
                    pygame.Rect(rhx - fw // 2, fy, fw, fh),
                    math.pi, math.tau, 1)   # 右半球折痕

    # ── 高光 ─────────────────────────────────────────────────
    if r >= 6:
        pygame.draw.circle(bs, light,
                           (lhx - max(1, int(r * 0.18)),
                            hcy - max(1, int(r * 0.22))),
                           max(1, int(r * 0.18)))

    surf.blit(bs, (cx - bx, cy - by))

def _draw_icon_clover(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """四葉幸運草圖示。r 為整體半徑。"""
    leaf_r  = max(2, int(r * 0.48))
    offset  = max(2, int(r * 0.44))
    green   = (68, 178, 82)
    dark_g  = (38, 125, 52)
    shadow  = (30, 100, 42)
    # 四葉（上下左右），先畫陰影再畫本色
    for dx, dy in [(0, -offset), (0, offset), (-offset, 0), (offset, 0)]:
        pygame.draw.circle(surf, shadow, (cx + dx + 1, cy + dy + 1), leaf_r)
        pygame.draw.circle(surf, green,  (cx + dx,     cy + dy),     leaf_r)
    # 葉脈（細線，各葉從中心往葉頂）
    for dx, dy in [(0, -offset), (0, offset), (-offset, 0), (offset, 0)]:
        pygame.draw.line(surf, dark_g, (cx, cy),
                         (cx + dx, cy + dy), 1)
    # 莖（往下延伸）
    pygame.draw.line(surf, dark_g, (cx, cy + leaf_r),
                     (cx, cy + r + 3), max(1, r // 5))
    # 中心蓋住葉脈交叉點
    pygame.draw.circle(surf, dark_g, (cx, cy), max(1, leaf_r // 2))

def _draw_icon_info(surf: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """ℹ 圓形資訊圖示：白藍底圓 + 深藍 i 字形（點 + 豎）。r = 外圓半徑。"""
    FILL   = (240, 248, 255)   # 偏白藍底圓
    INK    = (40,   80, 140)   # 深藍 i 字
    BORDER = (160, 200, 235)   # 淡藍描邊
    # 底圓
    pygame.draw.circle(surf, FILL,   (cx, cy), r)
    pygame.draw.circle(surf, BORDER, (cx, cy), r, 1)
    # i 的點（上方）
    dot_r = max(1, r // 4)
    pygame.draw.circle(surf, INK, (cx, cy - r // 3), dot_r)
    # i 的豎（下方中段）
    bar_h = max(2, r // 2 + 1)
    bar_w = max(1, r // 3)
    pygame.draw.rect(surf, INK,
                     pygame.Rect(cx - bar_w // 2, cy - r // 8, bar_w, bar_h))

def _draw_status_v2(surf, fm, fs, player, rect, mpos):
    """
    新版狀態欄（浮動卡片）：
      左側：圓形頭像 → 名字/系級/體力條/滿足感條 → 智力/運氣小標籤
      右側：道具店按鈕 + 金錢（靠右對齊道具店右緣）
    回傳道具店按鈕 Rect。
    """
    fb    = _font_bold[0]    or fs   # 粗體 size-17
    fb_lg = _font_bold_lg[0] or fm  # 粗體 size-22

    M  = 8
    pr = pygame.Rect(rect.x + M, rect.y + M,
                     rect.width - M * 2, rect.height - M * 2)

    # ── 投影 ──────────────────────────────────────────────────
    sh = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 52),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(sh, (pr.x + 4, pr.y + 4))

    # ── 卡片底色 ──────────────────────────────────────────────
    card = pygame.Surface((pr.width, pr.height), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 244, 228, 238),
                     pygame.Rect(0, 0, pr.width, pr.height), border_radius=14)
    surf.blit(card, pr.topleft)
    pygame.draw.rect(surf, CYAN, pr, 2, border_radius=14)

    if player is None:
        t = fm.render("等待角色資料…", True, GRAY)
        surf.blit(t, (pr.x + 20, pr.y + pr.height // 2 - t.get_height() // 2))
        shop_r = pygame.Rect(pr.right - 122, pr.y + (pr.height - 40) // 2, 118, 40)
        pygame.draw.rect(surf, DARK_GRAY, shop_r, border_radius=14)
        return shop_r, None

    # ── 圓形頭像（立繪 _head，若無則顯示姓名首字）─────────────
    av_cx = pr.x + 52
    av_cy = pr.y + 58
    av_r  = 42
    _head = _portrait_head_load(_portrait_prefix[0]) if _portrait_prefix[0] else None
    if _head:
        surf.blit(_head, (av_cx - av_r, av_cy - av_r))
    else:
        pygame.draw.circle(surf, PANEL, (av_cx, av_cy), av_r)
        init_ch = player.name[0] if player.name else "？"
        init_t  = fb_lg.render(init_ch, True, TITLE)
        surf.blit(init_t, (av_cx - init_t.get_width() // 2,
                           av_cy - init_t.get_height() // 2))
    pygame.draw.circle(surf, CYAN, (av_cx, av_cy), av_r, 3)

    # ── 名字 + 系級（純文字）────────────────────────────────
    info_x = pr.x + 106
    info_y = pr.y + 14
    _de_name  = player.de_level.get("name", "") if hasattr(player, "de_level") else ""
    _base_str = f"{player.name}  {player.department}{' ' + _de_name if _de_name else ''}"
    name_t = fb_lg.render(_base_str, True, WHITE)
    surf.blit(name_t, (info_x, info_y))

    # ── 狀態效果 emoji chip（接在名字右側）──────────────────
    _hovered_status[0] = None          # 每幀重置
    if player.status_effects:
        CHIP_H   = name_t.get_height()  # chip 高度與名字行等高
        EM_SZ_N  = 20                   # 正常 emoji 大小
        EM_SZ_H  = 28                   # hover emoji 大小

        em_fn = _get_emoji_font(EM_SZ_N)
        em_fh = _get_emoji_font(EM_SZ_H)

        cx = info_x + name_t.get_width() + 10  # chip 起始 x

        for sname, sv in player.status_effects.items():
            em_ch  = _STATUS_EMOJI.get(sname, "❓")
            num_ch = _fw_num(sv)
            col_n  = GREEN if sname in _STATUS_POS else RED

            # ── 正常尺寸量測 ──────────────────────────────
            em_sn   = em_fn.render(em_ch, True, WHITE) if em_fn else None
            num_sn  = fb_lg.render(num_ch, True, col_n)
            em_wn   = em_sn.get_width() if em_sn else 0
            cw_n    = em_wn + 2 + num_sn.get_width()

            # ── hover 偵測 ────────────────────────────────
            hit = pygame.Rect(cx - 2, info_y, cw_n + 8, CHIP_H)
            is_hov = hit.collidepoint(mpos)

            if is_hov:
                # 寫入提示文字（text, is_positive）
                _hovered_status[0] = (
                    f"{sname} {sv}週" if sv > 0 else sname,
                    sname in _STATUS_POS,
                )

                # hover 尺寸
                em_sh   = em_fh.render(em_ch, True, WHITE) if em_fh else em_sn
                num_sh  = fb_lg.render(num_ch, True, (255, 220, 80))
                em_wh   = em_sh.get_width() if em_sh else 0
                cw_h    = em_wh + 2 + num_sh.get_width()
                th      = max(
                    em_sh.get_height() if em_sh else 0,
                    num_sh.get_height()
                )

                # 把 emoji + 數字畫進 temp SRCALPHA Surface
                temp = pygame.Surface((cw_h, th), pygame.SRCALPHA)
                if em_sh:
                    temp.blit(em_sh,  (0,          (th - em_sh.get_height())  // 2))
                temp.blit(num_sh, (em_wh + 2,  (th - num_sh.get_height()) // 2))

                # smoothscale 放大至 1.3×
                nw = max(1, int(cw_h * 1.3))
                nh = max(1, int(th   * 1.3))
                scaled = pygame.transform.smoothscale(temp, (nw, nh))

                # 發光背景（SRCALPHA 圓角矩形）
                gw, gh = nw + 12, nh + 8
                glow = pygame.Surface((gw, gh), pygame.SRCALPHA)
                pygame.draw.rect(glow, (255, 220, 80, 60),
                                 pygame.Rect(0, 0, gw, gh), border_radius=9)
                surf.blit(glow,   (cx - 6,  info_y + (CHIP_H - gh) // 2))
                surf.blit(scaled, (cx,       info_y + (CHIP_H - nh) // 2))

                cx += nw + 10

            else:
                # 正常繪製
                dy_em  = info_y + (CHIP_H - (em_sn.get_height()  if em_sn  else 0)) // 2
                dy_num = info_y + (CHIP_H - num_sn.get_height()) // 2
                if em_sn:
                    surf.blit(em_sn,  (cx,           dy_em))
                surf.blit(num_sn, (cx + em_wn + 2, dy_num))
                cx += cw_n + 8

    # 名字下細線
    line_y = info_y + name_t.get_height() + 2
    pygame.draw.line(surf, (210, 190, 165),
                     (info_x, line_y), (info_x + name_t.get_width(), line_y), 1)

    # ── 體力條 / 滿足感條 ────────────────────────────────────
    # 標籤在左側，數值置中顯示於條內；兩列標籤對齊同一 x
    bar_h  = 22                          # 加粗（原 14）
    bar_w  = 280                         # 略縮，讓左側標籤有空間
    bar_gap = 8                          # 標籤與條之間的間距

    # 預算標籤寬度（取最寬者做對齊基準）
    _lbl_stam = fb.render("體力", True, WHITE)
    _lbl_sat  = fb.render("自我滿足度", True, WHITE)
    lbl_col_w = max(_lbl_stam.get_width(), _lbl_sat.get_width())
    bar_x     = info_x + lbl_col_w + bar_gap   # 兩條共同左起點

    bar_y  = line_y + 7
    ratio  = player.stamina / max(player.stamina_max, 1)

    # 標籤（右對齊於標籤欄）
    surf.blit(_lbl_stam,
              (info_x + lbl_col_w - _lbl_stam.get_width(),
               bar_y + (bar_h - _lbl_stam.get_height()) // 2))
    # 進度條底 + 填充 + 邊框
    pygame.draw.rect(surf, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h), border_radius=9)
    _fill_w = max(0, int(bar_w * ratio))
    if _fill_w > 0:
        pygame.draw.rect(surf, GREEN, (bar_x, bar_y, _fill_w, bar_h), border_radius=9)
    pygame.draw.rect(surf, GRAY, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=9)
    # 數值置中於整條
    _sv = fb.render(f"{player.stamina}/{player.stamina_max}", True, PANEL)
    surf.blit(_sv, (bar_x + (bar_w - _sv.get_width()) // 2,
                    bar_y + (bar_h - _sv.get_height()) // 2))

    sat_y  = bar_y + bar_h + 7
    sr_val = player.satisfaction / 100
    sat_c  = YELLOW

    # 滿足感條
    surf.blit(_lbl_sat,
              (info_x + lbl_col_w - _lbl_sat.get_width(),
               sat_y + (bar_h - _lbl_sat.get_height()) // 2))
    pygame.draw.rect(surf, DARK_GRAY, (bar_x, sat_y, bar_w, bar_h), border_radius=9)
    _fill_sw = max(0, int(bar_w * sr_val))
    if _fill_sw > 0:
        pygame.draw.rect(surf, sat_c, (bar_x, sat_y, _fill_sw, bar_h), border_radius=9)
    pygame.draw.rect(surf, GRAY, (bar_x, sat_y, bar_w, bar_h), 1, border_radius=9)
    _satv = fb.render(f"{player.satisfaction}%", True, PANEL)
    surf.blit(_satv, (bar_x + (bar_w - _satv.get_width()) // 2,
                      sat_y + (bar_h - _satv.get_height()) // 2))
    sat_t = _lbl_sat   # 供下方 sat_right 計算使用（取標籤寬度作基準）

    # ── 智力 / 運氣 小標籤 + 資訊一覽按鈕（頭像正下方）─────
    chip_y = pr.bottom - 42

    # 「自我滿足度」標籤左緣 = 「自」字 x 位置（供腦圖示對齊）
    _sat_label_left = info_x + lbl_col_w - _lbl_sat.get_width()

    # 「資訊一覽」按鈕：寬度由「腦圖示對齊『自』字」反推，顏色與道具店一致
    # intel_chip_x = info_btn_r.right + 8，腦圖示左緣 = intel_chip_x + 9
    # 故 info_btn_w = _sat_label_left - 9（腦圖示左緣） - 8（間距） - (pr.x+6)（按鈕左）
    _ib_t      = fb.render("資訊一覽", True, PANEL)
    info_btn_w = max(_sat_label_left - 9 - 8 - (pr.x + 6), 60)
    info_btn_r = pygame.Rect(pr.x + 6, chip_y, info_btn_w, 32)
    _ib_hover  = info_btn_r.collidepoint(mpos)
    dr_info    = _premium_btn(surf, info_btn_r, BTN_N, _ib_hover, radius=12)
    surf.blit(_ib_t, (dr_info.x + (dr_info.width  - _ib_t.get_width())  // 2,
                      dr_info.y + (dr_info.height - _ib_t.get_height()) // 2))

    # 智力 chip（緊接按鈕右側；腦圖示左緣因此對齊「自我滿足度」的「自」）
    intel_lvl  = _get_intel_level_ui(player.intel)
    lvl_name   = _INTEL_NAMES_UI[intel_lvl]
    lvl_col    = _INTEL_ANNOT_COLS_UI[intel_lvl]
    base_s     = fb.render(f"智力: {player.intel}", True, WHITE)
    lvl_s      = fb.render(f"（{lvl_name}）", True, lvl_col)
    _CR = 8
    _ISPACE = _CR * 2 + 5
    intel_chip_w = _ISPACE + base_s.get_width() + lvl_s.get_width() + 18
    intel_chip_x = info_btn_r.right + 8
    intel_chip_r = pygame.Rect(intel_chip_x, chip_y, intel_chip_w, 30)
    _draw_icon_brain(surf,
                     intel_chip_r.x + 9 + _CR,
                     intel_chip_r.centery, _CR)
    bx = intel_chip_r.x + 9 + _ISPACE
    by = intel_chip_r.y + (intel_chip_r.height - base_s.get_height()) // 2
    surf.blit(base_s, (bx, by))
    surf.blit(lvl_s,  (bx + base_s.get_width(), by))

    # 運氣（緊接在智力右側，間距 8px）
    luck_chip_x = intel_chip_r.right + 8
    lt = fb.render(f"運氣: {player.luck}", True, WHITE)
    luck_chip_w = _ISPACE + lt.get_width() + 18
    luck_chip_r = pygame.Rect(luck_chip_x, chip_y, luck_chip_w, 30)
    _draw_icon_clover(surf,
                      luck_chip_r.x + 9 + _CR,
                      luck_chip_r.centery, _CR)
    lbx = luck_chip_r.x + 9 + _ISPACE
    lby = luck_chip_r.y + (luck_chip_r.height - lt.get_height()) // 2
    surf.blit(lt, (lbx, lby))

    # ── 道具店按鈕（先計算，供金錢靠右對齊使用）─────────────
    shop_r = pygame.Rect(pr.right - 150, pr.y + (pr.height - 40) // 2, 118, 40)
    hover  = shop_r.collidepoint(mpos)
    dr     = _premium_btn(surf, shop_r, BTN_N, hover, radius=14)
    st     = fb_lg.render("道具店", True, PANEL)
    _CART_R  = 7                                          # 購物車圖示半高
    _CART_SP = 6                                          # 圖示與文字間距
    _total_w = _CART_R * 2 + _CART_SP + st.get_width()   # 圖示 + 間距 + 文字
    _btn_cx  = dr.x + dr.width  // 2
    _btn_cy  = dr.y + dr.height // 2
    _cart_cx = _btn_cx - _total_w // 2 + _CART_R
    _text_x  = _btn_cx - _total_w // 2 + _CART_R * 2 + _CART_SP
    _draw_icon_cart(surf, _cart_cx, _btn_cy, _CART_R)
    surf.blit(st, (_text_x, _btn_cy - st.get_height() // 2))

    # ── 金錢（金幣圖示 + 數字，靠右對齊道具店按鈕右邊緣）────
    _COIN_R   = 11                          # 金幣圖示半徑
    money_t   = fb_lg.render(f"{player.money}", True, YELLOW)
    _mtotal_w = _COIN_R * 2 + 5 + money_t.get_width()
    _mx0      = shop_r.right - _mtotal_w   # 整組左起點
    _mcy      = pr.y + 14 + money_t.get_height() // 2
    _draw_icon_coin(surf, _mx0 + _COIN_R, _mcy, _COIN_R)
    surf.blit(money_t, (_mx0 + _COIN_R * 2 + 5, pr.y + 14))

    # 提前計算（供日曆等距置中使用）
    sat_right  = bar_x + bar_w + 12   # 進度條右緣 + 間距
    money_left = shop_r.x - 12        # 道具店左緣 - 間距
    _cdwn_rx   = money_left           # fallback：無倒數提示時以此為右界

    # ── 考試倒數提示（道具店按鈕正下方，靠右對齊）──────────────
    _w = _week[0]
    if fb and _w > 0:
        if _w < 8:
            _cdwn_txt      = f"距離期中考還有 {8 - _w} 週"
            _cdwn_base_col = WHITE
            _cdwn_bg       = (80, 40, 10, 140)
        elif _w == 8:
            _cdwn_txt      = "期中考週！"
            _cdwn_base_col = RED
            _cdwn_bg       = (160, 30, 20, 170)
        elif _w < 16:
            _cdwn_txt      = f"距離期末考還有 {16 - _w} 週"
            _cdwn_base_col = WHITE
            _cdwn_bg       = (80, 40, 10, 140)
        else:
            _cdwn_txt      = "期末考週！"
            _cdwn_base_col = RED
            _cdwn_bg       = (160, 30, 20, 170)
        # 第 7、15 週：每秒 4 次閃爍
        if _w in (7, 15):
            _cdwn_col = RED if (pygame.time.get_ticks() % 250) < 125 else WHITE
        else:
            _cdwn_col = _cdwn_base_col
        _cdwn_s  = fb.render(_cdwn_txt, True, _cdwn_col)
        _cdwn_px, _cdwn_py = 12, 5
        _cdwn_w  = _cdwn_s.get_width()  + _cdwn_px * 2
        _cdwn_h  = _cdwn_s.get_height() + _cdwn_py * 2
        _cdwn_rx = shop_r.right - _cdwn_w
        _cdwn_ry = shop_r.bottom + 16
        _cdwn_pill = pygame.Surface((_cdwn_w, _cdwn_h), pygame.SRCALPHA)
        pygame.draw.rect(_cdwn_pill, _cdwn_bg,
                         pygame.Rect(0, 0, _cdwn_w, _cdwn_h), border_radius=10)
        surf.blit(_cdwn_pill, (_cdwn_rx, _cdwn_ry))
        surf.blit(_cdwn_s,    (_cdwn_rx + _cdwn_px, _cdwn_ry + _cdwn_py))

    # ── 週次日曆（等距置中：進度條右緣 ↔ 倒數提示左緣）──────────────
    CAL_W     = 108
    ticker_cx = (sat_right + _cdwn_rx) // 2
    ticker_cy = pr.y + pr.height // 2
    if _cdwn_rx - sat_right >= CAL_W + 8:
        _draw_week_calendar(surf, fm, ticker_cx, ticker_cy, _week[0])

    return shop_r, info_btn_r

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
        _render_mixed(surf, fs, line, color,
                      rect.x + 6, rect.y + i * lh + 4)
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

def _draw_panel(surf, rect, border=CYAN):
    """畫一個帶漸層+圓角框的面板。"""
    if "start" in _grads:
        surf.blit(_grads["start"], (0, 0))
    else:
        surf.fill(BG)
    pygame.draw.rect(surf, PANEL, rect, border_radius=18)
    pygame.draw.rect(surf, border, rect, 2, border_radius=18)


# 明確宣告所有名稱可被 import * 匯出（含 _ 前綴）
__all__ = [_n for _n in vars() if not _n.startswith('__')]
