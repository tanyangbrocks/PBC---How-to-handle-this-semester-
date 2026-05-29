#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  scripts/check_pygbag_compat.py
#
#  掃描專案，輸出 pygbag 相容性報告。
#  在每個 Phase 完成後重跑，確認問題逐步清零。
#
#  檢查項目：
#    🔴 threading 使用點      → Phase 4 處理
#    🔴 SysFont 呼叫點        → Phase 2 處理
#    🔴 cv2 / OpenCV 使用點   → Phase 3 處理
#    🔴 阻塞式 .wait() 呼叫   → Phase 4 處理
#    🟡 硬編碼資源路徑         → Phase 1 處理
#    🟡 queue.Queue 使用       → Phase 4 處理
#
#  執行：python scripts/check_pygbag_compat.py
# ============================================================
import re
import sys
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).parent.parent

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCAN_FILES = [
    "main.py",
    "ui.py",
    "ui_state.py",
    "ui_const.py",
    "ui_draw_base.py",
    "ui_draw_fx.py",
    "ui_draw_cc.py",
    "ui_draw_pop.py",
    "ui_draw_hud.py",
    "ui_draw_ap.py",
    "ui_draw_exam.py",
    "ui_draw_base.py",
    "turn_engine.py",
    "character.py",
    "event_system.py",
    "skill_system.py",
    "shop_V03.py",
]

# ── ANSI 顏色 ───────────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

SEP  = "=" * 64
SEP2 = "-" * 64

# ── 檢查規則 ────────────────────────────────────────────────
CHECKS = [
    {
        "id":       "threading",
        "severity": "🔴",
        "label":    "threading 使用點",
        "phase":    "Phase 4",
        "pattern":  re.compile(
            r"import\s+threading"
            r"|threading\.(Thread|Event|Lock|RLock|Semaphore|Condition|Barrier|Timer)"
            r"|from\s+threading\s+import"
        ),
    },
    {
        "id":       "sysfont",
        "severity": "🔴",
        "label":    "SysFont 呼叫（系統字型，網頁版不存在）",
        "phase":    "Phase 2",
        "pattern":  re.compile(r"pygame\.font\.SysFont"),
    },
    {
        "id":       "cv2",
        "severity": "🔴",
        "label":    "cv2 / OpenCV 使用點（WebAssembly 不支援）",
        "phase":    "Phase 3",
        "pattern":  re.compile(r"import\s+cv2|cv2\.|from\s+cv2"),
    },
    {
        "id":       "blocking_wait",
        "severity": "🔴",
        "label":    "阻塞式 .wait() 呼叫",
        "phase":    "Phase 4",
        "pattern":  re.compile(
            r"_reply_event\.wait\(\)"
            r"|_start_event\.wait\(\)"
            r"|_restart_event\.wait\(\)"
            r"|\.wait\(\s*\)"       # 任何 threading.Event.wait()
        ),
    },
    {
        "id":       "queue",
        "severity": "🟡",
        "label":    "queue.Queue 使用（需改為 asyncio.Queue）",
        "phase":    "Phase 4",
        "pattern":  re.compile(r"import\s+queue|queue\.Queue|Queue\(\)"),
    },
    {
        "id":       "hardpath",
        "severity": "🟡",
        "label":    "硬編碼資源路徑（需改為 resource_path()）",
        "phase":    "Phase 1",
        "pattern":  re.compile(
            r'os\.path\.(dirname|abspath)\s*\(\s*__file__\s*\)'
            r'|os\.path\.dirname\s*\(\s*__file__\s*\)'
        ),
    },
    {
        "id":       "video_files",
        "severity": "🔴",
        "label":    "影片檔案引用（.webm / .mp4）",
        "phase":    "Phase 3",
        "pattern":  re.compile(r'["\'].*\.(webm|mp4)["\']'),
    },
]

# ── 掃描 ────────────────────────────────────────────────────
results = {c["id"]: [] for c in CHECKS}

seen_files = set()
for fname in SCAN_FILES:
    if fname in seen_files:
        continue
    seen_files.add(fname)
    fpath = PROJECT / fname
    if not fpath.exists():
        continue
    lines = fpath.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for check in CHECKS:
            if check["pattern"].search(line):
                results[check["id"]].append((fname, lineno, line.rstrip()))

# ── 印出報告 ─────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}{SEP}{RESET}")
print(f"{BOLD}{CYAN}  pygbag 相容性檢查報告{RESET}")
print(f"{BOLD}{CYAN}{SEP}{RESET}")

total_issues = 0
for check in CHECKS:
    hits = results[check["id"]]
    total_issues += len(hits)
    sev  = check["severity"]
    lbl  = check["label"]
    phase = check["phase"]
    count = len(hits)

    if count == 0:
        print(f"\n  {GREEN}✅  {lbl}  → 無問題{RESET}")
        continue

    print(f"\n  {sev}  {BOLD}{lbl}{RESET}  （{count} 處，{phase} 處理）")
    for fname, lineno, code in hits[:20]:   # 最多顯示 20 行
        print(f"    {fname}:{lineno:<5}  {code[:80]}")
    if count > 20:
        print(f"    ... 還有 {count - 20} 處")

# ── 摘要 ────────────────────────────────────────────────────
print(f"\n{BOLD}{CYAN}{SEP}{RESET}")
print(f"{BOLD}  相容性摘要{RESET}")
red_count    = sum(len(results[c["id"]]) for c in CHECKS if c["severity"] == "🔴")
yellow_count = sum(len(results[c["id"]]) for c in CHECKS if c["severity"] == "🟡")
print(f"  🔴 高優先問題  : {RED}{red_count}{RESET} 處")
print(f"  🟡 中優先問題  : {YELLOW}{yellow_count}{RESET} 處")
if total_issues == 0:
    print(f"  {GREEN}{BOLD}全部通過！可以用 pygbag 打包。{RESET}")
else:
    print(f"  總計尚待解決  : {total_issues} 處")
print(f"{BOLD}{CYAN}{SEP}{RESET}\n")
