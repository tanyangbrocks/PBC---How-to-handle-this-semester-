#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  scripts/extract_video_frames.py
#
#  使用 cv2 將影片解包成 WEBP 影格資料夾。
#  執行一次即可，之後 cv2 相依即可移除。
#
#  執行：python scripts/extract_video_frames.py
# ============================================================
import cv2
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT  = Path(__file__).parent.parent
OUT_ROOT = PROJECT / "asset" / "video_frames"

# ── 影片清單 ─────────────────────────────────────────────────
VIDEOS = [
    {
        "src":         "asset/picture/background/skill_background.webm",
        "slug":        "skill_bg",
        "extract_fps": 15,   # 擷取幀率（降半以節省空間）
        "quality":     80,   # WEBP 品質（0-100）
        "max_frames":  0,    # 0 = 全部
    },
    {
        "src":         "asset/picture/background/best_ending_background.webm",
        "slug":        "best_bg",
        "extract_fps": 15,
        "quality":     80,
        "max_frames":  0,
    },
    {
        "src":         "asset/picture/background/next_ending_background.webm",
        "slug":        "next_bg",
        "extract_fps": 15,
        "quality":     80,
        "max_frames":  0,
    },
    {
        "src":         "asset/picture/background/break_background.webm",
        "slug":        "break_bg",
        "extract_fps": 15,
        "quality":     80,
        "max_frames":  0,
    },
    {
        "src":         "asset/picture/background/lose_background.webm",
        "slug":        "lose_bg",
        "extract_fps": 15,
        "quality":     80,
        "max_frames":  0,
    },
    {
        "src":         "asset/video/15673cd6-bc6e-432b-bf3f-de47ecfe4918_0.mp4",
        "slug":        "end_cutscene",
        "extract_fps": 24,   # 結算過場保留較高幀率
        "quality":     85,
        "max_frames":  0,
    },
]

# ── ANSI 顏色 ─────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
SEP    = "=" * 60

# ── 主迴圈 ───────────────────────────────────────────────────
OUT_ROOT.mkdir(parents=True, exist_ok=True)
total_size = 0

print(f"\n{BOLD}{SEP}{RESET}")
print(f"{BOLD}  影片影格擷取  →  asset/video_frames/{RESET}")
print(f"{BOLD}{SEP}{RESET}\n")

for vid in VIDEOS:
    src_path = PROJECT / vid["src"]
    out_dir  = OUT_ROOT / vid["slug"]

    if not src_path.exists():
        print(f"{YELLOW}[SKIP]{RESET}  {vid['src']}  （檔案不存在，略過）")
        continue

    out_dir.mkdir(parents=True, exist_ok=True)

    cap      = cv2.VideoCapture(str(src_path))
    src_fps  = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target   = vid["extract_fps"]
    step     = max(1, round(src_fps / target))
    quality  = vid["quality"]
    max_fr   = vid["max_frames"]
    actual_fps = src_fps / step

    print(f"{BOLD}[{vid['slug']}]{RESET}  {src_path.name}")
    print(f"  原始 FPS={src_fps:.1f}  總幀數={total_fc}"
          f"  step={step}  → 擷取 FPS≈{actual_fps:.1f}")

    frame_count = 0
    read_count  = 0
    dir_size    = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if read_count % step == 0:
            out_path = out_dir / f"{frame_count:05d}.webp"
            ok = cv2.imwrite(str(out_path), frame,
                             [cv2.IMWRITE_WEBP_QUALITY, quality])
            if ok:
                sz = out_path.stat().st_size
                dir_size += sz
                frame_count += 1
            if max_fr and frame_count >= max_fr:
                break
        read_count += 1

    cap.release()

    # ── 寫入 meta.json ───────────────────────────────────────
    meta = {"fps": round(actual_fps, 3), "frame_count": frame_count}
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    total_size += dir_size
    mb = dir_size / 1024 / 1024
    print(f"  {GREEN}完成{RESET}  {frame_count} 幀  {mb:.1f} MB  → {out_dir.relative_to(PROJECT)}\n")

print(f"{BOLD}{SEP}{RESET}")
print(f"{BOLD}全部完成。  總大小 {total_size/1024/1024:.1f} MB{RESET}")
print("提示：若不再需要 cv2，可執行  pip uninstall opencv-python")
print(f"{BOLD}{SEP}{RESET}\n")
