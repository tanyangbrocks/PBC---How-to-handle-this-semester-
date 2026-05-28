#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  check_ui_state.py -- UI event handler static analysis tool
#
#  掃描 ui.py 中的 MOUSEBUTTONDOWN 事件處理器，找出：
#  1. 所有「早期 continue」攔截條件（哪些 state 變數會封鎖點擊）
#  2. 所有指令 tag 的初始化區塊（切換遊戲模式時重置了哪些 state）
#  3. 交叉比對：哪些 state 在進入某個 mode 時「未被重置」
#     → 這就是可能造成「點擊無反應」的潛在 bug 路徑
#
#  執行：python check_ui_state.py
# ============================================================

import re
import sys
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).parent
UI_PY   = PROJECT / "ui.py"

# ── ANSI 顏色（終端機）──────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ─────────────────────────────────────────────────────────────
#  我們追蹤的「封鎖型」狀態變數（出現在 continue 前的 if 條件裡）
# ─────────────────────────────────────────────────────────────
BLOCKING_VARS = [
    "_modal",
    "_info_modal_active",
    "_skip_popup_active",
    "_withdrawal_popup_active",
    "_guide_active",
    "_smg_active",
    "_smg_final_score_t0",
    "_smg_q_active",
    "_smg_q_answered",
]

# ─────────────────────────────────────────────────────────────
#  所有指令 tag（elif tag == "..."）
# ─────────────────────────────────────────────────────────────
# 這些 tag 代表從 game logic thread 進入的新模式
KNOWN_TAGS = [
    "shape_minigame",
    "exam_ready",
    "exam_q",
    "timetable",
    "grade_report",
    "story",
    "event_ok",
    "event_ok_col",
    "yn",
    "choices",
    "text",
    "ripple",
    "reset",
    "phase",
    "subj_popup",
    "withdrawal_popup_open",
    "allnighter_count",
]


def load_source() -> list[str]:
    with open(UI_PY, encoding="utf-8") as f:
        return f.readlines()


def find_blocking_conditions(lines: list[str]) -> list[dict]:
    """
    找出 MOUSEBUTTONDOWN 事件處理器中，出現「封鎖型」狀態變數的 if/elif 條件行。
    回傳格式：[{line_no, line, vars_found, followed_by_continue}]
    """
    # 只分析事件處理器範圍（粗估：找到 MOUSEBUTTONDOWN 後的程式碼）
    in_handler = False
    results = []

    for i, line in enumerate(lines, start=1):
        if "MOUSEBUTTONDOWN" in line and "ev.type" in line:
            in_handler = True

        if not in_handler:
            continue

        # 找包含封鎖變數的 if/elif 行
        found_vars = [v for v in BLOCKING_VARS if v in line]
        if not found_vars:
            continue
        if not re.search(r"\bif\b|\belif\b", line):
            continue

        # 往後幾行找 continue
        lookahead = "".join(lines[i:min(i+8, len(lines))])
        has_continue = bool(re.search(r"\bcontinue\b", lookahead))

        results.append({
            "line_no":             i,
            "line":                line.rstrip(),
            "vars":                found_vars,
            "followed_by_continue": has_continue,
        })

    return results


def find_tag_blocks(lines: list[str]) -> dict[str, dict]:
    """
    找到每個 `elif tag == "X":` 區塊，並記錄區塊內被「重置」的封鎖型狀態變數。
    重置定義：出現 `_var[0] = False/None/0` 或 `_var[0]  = False/None/0`。
    """
    tag_blocks: dict[str, dict] = {}

    current_tag = None
    block_lines = []
    indent_of_tag = -1

    for i, raw in enumerate(lines, start=1):
        # 嘗試偵測 elif tag == "XXX":
        m = re.search(r'elif\s+tag\s*==\s*["\'](\w+)["\']', raw)
        if m:
            # 儲存上一個 tag 的資料
            if current_tag is not None:
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)

            current_tag  = m.group(1)
            block_lines  = [raw]
            indent_of_tag = len(raw) - len(raw.lstrip())
            continue

        if current_tag is not None:
            # 同層或更深縮排 → 屬於本 block
            stripped = raw.strip()
            if stripped == "" or len(raw) - len(raw.lstrip()) > indent_of_tag:
                block_lines.append(raw)
            elif stripped.startswith("elif tag") or stripped.startswith("else:"):
                # 下一個 tag block 開始前先儲存
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)
                current_tag = None
                block_lines = []
            else:
                # 縮排回退，結束本 block
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)
                current_tag = None

    if current_tag is not None:
        tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)

    return tag_blocks


def _analyze_block(block_lines: list[str], tag: str) -> dict:
    """分析 block 內容：哪些封鎖變數被重置，哪些被 SET（可能引入問題）。"""
    text = "".join(block_lines)

    reset_pattern = re.compile(
        r"(" + "|".join(re.escape(v) for v in BLOCKING_VARS) + r")"
        r"\[0\]\s*=\s*(False|None|0)"
    )
    set_pattern = re.compile(
        r"(" + "|".join(re.escape(v) for v in BLOCKING_VARS) + r")"
        r"\[0\]\s*=\s*(?!False|None|0)\S"
    )

    resets = set(m.group(1) for m in reset_pattern.finditer(text))
    sets   = set(m.group(1) for m in set_pattern.finditer(text))

    return {
        "tag":    tag,
        "resets": resets,
        "sets":   sets,
        "lines":  len(block_lines),
    }


def find_event_handler_sets(lines: list[str]) -> list[dict]:
    """
    在事件處理器（非 tag block）中，找出設定封鎖變數為 True/非 None 的地方。
    這些是「可能讓狀態卡住」的位置。
    """
    results = []
    in_handler = False

    for i, line in enumerate(lines, start=1):
        if "MOUSEBUTTONDOWN" in line and "ev.type" in line:
            in_handler = True
        if not in_handler:
            continue

        for v in BLOCKING_VARS:
            # 搜尋 _var[0] = True / = "something" (非 False/None/0)
            m = re.search(
                re.escape(v) + r"\[0\]\s*=\s*(?!False|None\b|0\b)(.*)",
                line,
            )
            if m:
                results.append({
                    "line_no": i,
                    "line":    line.rstrip(),
                    "var":     v,
                    "value":   m.group(1).strip(),
                })
    return results


def print_section(title: str):
    width = 62
    print(f"\n{BOLD}{CYAN}{'='*width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*width}{RESET}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\n{BOLD}UI Event Handler Static Analysis  --  {UI_PY.name}{RESET}")

    lines = load_source()

    # ── 1. 封鎖條件 ──────────────────────────────────────────
    print_section("Early-exit CONTINUE conditions (MOUSEBUTTONDOWN handler)")
    blockers = find_blocking_conditions(lines)
    for b in blockers:
        icon = "[BLOCK]" if b["followed_by_continue"] else "[info ]"
        print(f"  {icon} L{b['line_no']:4d}  {b['vars']}  =>  {b['line'].strip()[:80]}")

    # ── 2. 各 tag 初始化分析 ────────────────────────────────
    print_section("Per-tag init blocks: which blocking vars are reset?")
    tag_blocks = find_tag_blocks(lines)

    for tag in KNOWN_TAGS:
        info = tag_blocks.get(tag)
        if info is None:
            print(f"  [WARN] tag [{tag}] not found in ui.py elif block")
            continue

        reset_report = []
        for v in BLOCKING_VARS:
            if v in info["resets"]:
                reset_report.append(f"{GREEN}RESET {v}{RESET}")
            elif v in info["sets"]:
                reset_report.append(f"{YELLOW}SET   {v}{RESET}")
            # else: 未提及，不報告（只報告有問題的）

        missing = [v for v in BLOCKING_VARS
                   if v not in info["resets"] and v not in info["sets"]]

        has_set_issues = any(v in info["sets"] for v in BLOCKING_VARS)
        status = "" if has_set_issues else f"({GREEN}OK{RESET})"
        print(f"\n  tag: {BOLD}{tag}{RESET} {status}")
        if reset_report:
            print(f"       reset/set  : {', '.join(reset_report)}")
        print(f"       not mentioned: {', '.join(missing) or '(none)'}")

    # ── 3. 交叉分析：封鎖條件 × 模式初始化 ───────────────────
    print_section("Risk cross-analysis: tags that enter without clearing blocking vars")

    # 找出真正「有 continue」的封鎖變數集合
    blocking_vars_active = set()
    for b in blockers:
        if b["followed_by_continue"]:
            blocking_vars_active.update(b["vars"])

    risk_found = False
    for tag in KNOWN_TAGS:
        info = tag_blocks.get(tag)
        if info is None:
            continue

        not_reset = [v for v in blocking_vars_active if v not in info["resets"]]
        if not_reset:
            risk_found = True
            print(f"\n  {RED}[RISK] tag [{tag}]: following blocking vars NOT reset on entry:{RESET}")
            setters = find_event_handler_sets(lines)
            for v in not_reset:
                setter_lines = [s["line_no"] for s in setters if s["var"] == v]
                if setter_lines:
                    print(f"     {YELLOW}* {v}  <- can be set True at L{setter_lines}{RESET}")
                else:
                    print(f"     {YELLOW}* {v}{RESET}")
            print(f"     If [{tag}] is entered while any of these are True, all clicks may be blocked!")

    if not risk_found:
        print(f"  {GREEN}[OK] No risks found (all blocking vars reset in relevant tag inits){RESET}")

    # ── 4. 事件處理器中設定封鎖變數的位置彙整 ────────────────
    print_section("Event handler: lines that SET a blocking var to True/non-empty")
    setters = find_event_handler_sets(lines)
    if setters:
        for s in setters:
            print(f"  L{s['line_no']:4d}  {s['var']}[0] = {s['value'][:50]}")
            print(f"         {s['line'].strip()[:80]}")
    else:
        print(f"  （無）")

    print(f"\n{BOLD}Analysis complete.{RESET}\n")


if __name__ == "__main__":
    main()
