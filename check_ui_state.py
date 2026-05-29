#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  check_ui_state.py -- UI static analysis tool
#
#  掃描 ui.py / turn_engine.py / character.py 等，找出：
#  1. MOUSEBUTTONDOWN 早期 continue 封鎖條件
#  2. 各指令 tag 初始化區塊的 state 重置情況
#  3. 封鎖變數 × 模式切換交叉風險
#  4. 事件處理器中設定封鎖變數的位置
#  5. 音效系統審計：play_sfx 呼叫 vs 檔案是否存在
#  6. 指令 tag 覆蓋率：PUT 無 HANDLER / HANDLER 無 PUT
#
#  執行：python check_ui_state.py
# ============================================================

import re
import sys
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).parent
UI_PY   = PROJECT / "ui.py"
SE_DIR  = PROJECT / "asset" / "audio" / "se"

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
#  KNOWN_TAGS：封鎖變數分析中要追蹤的模式切換 tag
#  （非阻塞的 msg/player/set_time 等不需在此列出）
# ─────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────
#  掃描目標：這些 .py 檔案可能含有 play_sfx / _cmd_q.put 呼叫
# ─────────────────────────────────────────────────────────────
SCAN_FILES = [
    PROJECT / "ui.py",
    PROJECT / "turn_engine.py",
    PROJECT / "character.py",
    PROJECT / "ui_draw_base.py",
    PROJECT / "ui_draw_exam.py",
    PROJECT / "ui_draw_fx.py",
    PROJECT / "ui_draw_hud.py",
    PROJECT / "ui_draw_pop.py",
    PROJECT / "ui_draw_ap.py",
    PROJECT / "ui_draw_cc.py",
]


# ═══════════════════════════════════════════════════════════════
#  原有功能（封鎖變數 / tag 重置分析）
# ═══════════════════════════════════════════════════════════════

def load_source() -> list[str]:
    with open(UI_PY, encoding="utf-8") as f:
        return f.readlines()


def find_blocking_conditions(lines: list[str]) -> list[dict]:
    in_handler = False
    results = []
    for i, line in enumerate(lines, start=1):
        if "MOUSEBUTTONDOWN" in line and "ev.type" in line:
            in_handler = True
        if not in_handler:
            continue
        found_vars = [v for v in BLOCKING_VARS if v in line]
        if not found_vars:
            continue
        if not re.search(r"\bif\b|\belif\b", line):
            continue
        lookahead = "".join(lines[i:min(i+8, len(lines))])
        has_continue = bool(re.search(r"\bcontinue\b", lookahead))
        results.append({
            "line_no":              i,
            "line":                 line.rstrip(),
            "vars":                 found_vars,
            "followed_by_continue": has_continue,
        })
    return results


def find_tag_blocks(lines: list[str]) -> dict[str, dict]:
    tag_blocks: dict[str, dict] = {}
    current_tag = None
    block_lines = []
    indent_of_tag = -1

    for i, raw in enumerate(lines, start=1):
        m = re.search(r'elif\s+tag\s*==\s*["\'](\w+)["\']', raw)
        if m:
            if current_tag is not None:
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)
            current_tag   = m.group(1)
            block_lines   = [raw]
            indent_of_tag = len(raw) - len(raw.lstrip())
            continue

        if current_tag is not None:
            stripped = raw.strip()
            if stripped == "" or len(raw) - len(raw.lstrip()) > indent_of_tag:
                block_lines.append(raw)
            elif stripped.startswith("elif tag") or stripped.startswith("else:"):
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)
                current_tag = None
                block_lines = []
            else:
                tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)
                current_tag = None

    if current_tag is not None:
        tag_blocks[current_tag] = _analyze_block(block_lines, current_tag)

    return tag_blocks


def _analyze_block(block_lines: list[str], tag: str) -> dict:
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
    return {"tag": tag, "resets": resets, "sets": sets, "lines": len(block_lines)}


def find_event_handler_sets(lines: list[str]) -> list[dict]:
    results = []
    in_handler = False
    for i, line in enumerate(lines, start=1):
        if "MOUSEBUTTONDOWN" in line and "ev.type" in line:
            in_handler = True
        if not in_handler:
            continue
        for v in BLOCKING_VARS:
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


# ═══════════════════════════════════════════════════════════════
#  新功能 5：音效系統審計
# ═══════════════════════════════════════════════════════════════

def collect_sfx_registrations(lines: list[str]) -> dict[str, str]:
    """
    從 ui.py 的 run_ui() 中收集：
      _sfx["symbolic_key"] = _ld("actual_filename")
    回傳 {symbolic_key: actual_filename}（不含副檔名的 key 映射到含副檔名的檔名）。
    """
    reg = {}
    pat = re.compile(r'_sfx\["([^"]+)"\]\s*=\s*_ld\("([^"]+)"\)')
    for line in lines:
        m = pat.search(line)
        if m:
            reg[m.group(1)] = m.group(2)
    return reg


def collect_play_sfx_calls(scan_files: list[Path]) -> list[dict]:
    """
    掃描指定 .py 檔，收集所有以「字面字串」為參數的 play_sfx / _play_sfx 呼叫。
    動態變數（如 _play_sfx(var)）會被標記為 dynamic=True，不做檔案存在驗證。
    回傳：[{file, line_no, key, dynamic}]
    """
    calls = []
    # 字面字串版
    lit_pat  = re.compile(r'(?:^|\b)(?:_play_sfx|play_sfx)\(\s*["\']([^"\']+)["\']')
    # 動態版（括號內非引號）
    dyn_pat  = re.compile(r'(?:^|\b)(?:_play_sfx|play_sfx)\(\s*(?!["\'])([\w\[\]\.]+)')

    for fp in scan_files:
        if not fp.exists():
            continue
        src = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln, line in enumerate(src, start=1):
            # 跳過定義行本身
            if "def _play_sfx" in line or "def play_sfx" in line:
                continue
            for m in lit_pat.finditer(line):
                calls.append({"file": fp.name, "line_no": ln,
                               "key": m.group(1), "dynamic": False})
            for m in dyn_pat.finditer(line):
                calls.append({"file": fp.name, "line_no": ln,
                               "key": m.group(1), "dynamic": True})
    return calls


def _sfx_file_exists(key: str, sym_map: dict[str, str]) -> tuple[bool, str]:
    """
    判斷音效 key 對應的檔案是否存在。
    回傳 (exists: bool, resolved_filename: str)。
    - symbolic key（在 sym_map 中）→ 直接查 SE_DIR/filename
    - filename-stem key → 嘗試 SE_DIR/{key}.mp3 / .wav
    """
    if key in sym_map:
        fn = sym_map[key]
        return (SE_DIR / fn).exists(), fn
    # 自動載入路徑
    for ext in (".mp3", ".wav"):
        fn = key + ext
        if (SE_DIR / fn).exists():
            return True, fn
    return False, key + ".mp3"   # 最可能的預期路徑


def audit_play_sfx_availability(scan_files: list[Path]) -> None:
    """
    分別追蹤兩個名稱的可用性：
      _play_sfx  → 私有，定義於 ui_draw_base.py
      play_sfx   → 公開包裝，定義於 ui.py
    規則：
      - 自己定義了 def <name>  → OK
      - from <provider> import *   → OK
      - from <provider> import <name>  → OK
      - 其餘 → MISS（NameError at runtime）
    """
    print_section("Sound audit ③: _play_sfx / play_sfx symbol availability per module")

    # 每個可呼叫名稱對應的「提供者模組」
    VARIANTS = {
        "_play_sfx": "ui_draw_base",
        "play_sfx":  "ui",
    }

    wildcard_pat = re.compile(r'from\s+(\w+)\s+import\s+\*')
    miss_count = 0

    for fp in scan_files:
        if not fp.exists():
            continue
        raw_text = fp.read_text(encoding="utf-8", errors="replace")
        lines    = raw_text.splitlines()
        # 把 backslash 繼行合併成單行，方便跨行 import 比對
        merged   = re.sub(r'\\\n\s*', ' ', raw_text)

        # 收集此檔中各名稱的呼叫行（跳過 def 行）
        for fname, provider in VARIANTS.items():
            def_pat      = re.compile(r'def\s+' + re.escape(fname) + r'\s*\(')
            call_pat     = re.compile(r'(?:^|\b)' + re.escape(fname) + r'\s*\(')
            # 也匹配括號式多行 import：from X import (\n  ...\n  play_sfx\n)
            explicit_pat = re.compile(
                r'from\s+\S+\s+import\s+[^;]*\b' + re.escape(fname) + r'\b')

            calls = [ln for ln, line in enumerate(lines, 1)
                     if call_pat.search(line) and not def_pat.search(line)]
            if not calls:
                continue

            has_def     = any(def_pat.search(line) for line in lines)
            wildcard_ok = any(provider == m.group(1)
                              for line in lines
                              for m in wildcard_pat.finditer(line))
            # 在合併後的文字中比對（處理 backslash 繼行 + 括號式多行 import）
            explicit_ok = bool(explicit_pat.search(merged))

            available = has_def or wildcard_ok or explicit_ok

            if available:
                how = ("self-defined" if has_def
                       else f"from {provider} import {'*' if wildcard_ok else fname}")
                print(f"  {GREEN}[OK]  {fp.name:<32}  {fname}  ({how}){RESET}")
            else:
                miss_count += 1
                imports = [line.strip() for line in lines
                           if re.match(r'\s*(import|from)\s', line)]
                print(f"  {RED}[MISS] {fp.name}  ← 呼叫了 {fname} 但未 import！{RESET}")
                print(f"         呼叫位置 (前5): {calls[:5]}")
                print(f"         目前 imports: {imports}")

    if miss_count == 0:
        print(f"  {GREEN}[OK] 所有呼叫 _play_sfx / play_sfx 的模組均已正確 import 對應名稱{RESET}")


def audit_sound_system(lines: list[str]) -> None:
    sym_map  = collect_sfx_registrations(lines)
    all_calls = collect_play_sfx_calls(SCAN_FILES)

    # ── 1. 驗證 _sfx["key"] = _ld("file") 的檔案是否存在 ─────
    print_section("Sound audit ①: _sfx registrations in run_ui()")
    ok_count = 0
    for key, fn in sorted(sym_map.items()):
        exists = (SE_DIR / fn).exists()
        if exists:
            ok_count += 1
        else:
            print(f"  {RED}[MISS] _sfx[\"{key}\"] = _ld(\"{fn}\")  ← 檔案不存在！{RESET}")
    print(f"  {GREEN}[OK] {ok_count}/{len(sym_map)} 個已登記音效的檔案均存在{RESET}"
          if ok_count == len(sym_map) else "")

    # ── 2. 驗證各 play_sfx("key") 呼叫的 key 是否可解析到檔案 ──
    print_section("Sound audit ②: play_sfx / _play_sfx literal-key calls")
    seen_keys: dict[str, bool] = {}   # key → exists
    missing_rows  = []
    dynamic_rows  = []
    ok_call_count = 0

    for c in all_calls:
        if c["dynamic"]:
            dynamic_rows.append(c)
            continue
        key = c["key"]
        if key not in seen_keys:
            exists, _ = _sfx_file_exists(key, sym_map)
            seen_keys[key] = exists
        if not seen_keys[key]:
            missing_rows.append(c)
        else:
            ok_call_count += 1

    if missing_rows:
        for c in missing_rows:
            print(f"  {RED}[MISS] {c['file']}:{c['line_no']}  play_sfx(\"{c['key']}\")  ← 無對應檔案{RESET}")
    else:
        print(f"  {GREEN}[OK] 所有字面字串音效 key 均可解析到 SE 資料夾中的檔案{RESET}")

    if dynamic_rows:
        print(f"\n  {YELLOW}[INFO] 以下 {len(dynamic_rows)} 處為動態參數，無法靜態驗證：{RESET}")
        for c in dynamic_rows:
            print(f"         {c['file']}:{c['line_no']}  play_sfx({c['key']})")

    # ── 3. 驗證每個呼叫模組的 _play_sfx 名稱可取得 ────────────
    audit_play_sfx_availability(SCAN_FILES)


# ═══════════════════════════════════════════════════════════════
#  新功能 6：指令 tag 覆蓋率審計
# ═══════════════════════════════════════════════════════════════

def collect_cmd_put_tags(ui_lines: list[str]) -> dict[str, list[int]]:
    """
    從 ui.py 中收集所有 _cmd_q.put(("tag", ...)) 的 tag 字串。
    回傳 {tag: [line_no, ...]}。
    """
    pat = re.compile(r'_cmd_q\.put\(\(\s*["\'](\w+)["\']')
    tags: dict[str, list[int]] = defaultdict(list)
    for ln, line in enumerate(ui_lines, start=1):
        for m in pat.finditer(line):
            tags[m.group(1)].append(ln)
    return dict(tags)


def collect_tag_handlers(ui_lines: list[str]) -> dict[str, int]:
    """
    從 ui.py 中收集所有 if/elif tag == "X": 的 tag 字串（含鏈首 if）。
    回傳 {tag: line_no}。
    """
    pat = re.compile(r'(?:if|elif)\s+tag\s*==\s*["\'](\w+)["\']')
    handlers: dict[str, int] = {}
    for ln, line in enumerate(ui_lines, start=1):
        m = pat.search(line)
        if m:
            handlers[m.group(1)] = ln
    return handlers


def audit_tag_coverage(ui_lines: list[str]) -> None:
    put_tags     = collect_cmd_put_tags(ui_lines)
    handler_tags = collect_tag_handlers(ui_lines)

    all_tags = sorted(set(put_tags) | set(handler_tags))

    # ── 1. PUT 但無 HANDLER（命令會被靜默丟棄）────────────────
    print_section("Tag coverage ①: PUT without HANDLER (silent drop)")
    orphan_puts = [t for t in sorted(put_tags) if t not in handler_tags]
    if orphan_puts:
        for t in orphan_puts:
            lns = put_tags[t]
            print(f"  {RED}[WARN] tag \"{t}\" put at L{lns} but NO elif handler → 命令被丟棄！{RESET}")
    else:
        print(f"  {GREEN}[OK] 所有 PUT tag 均有對應 handler{RESET}")

    # ── 2. HANDLER 但無 PUT（死碼，永遠不會執行到）─────────────
    print_section("Tag coverage ②: HANDLER without PUT (dead code)")
    dead_handlers = [t for t in sorted(handler_tags) if t not in put_tags]
    if dead_handlers:
        for t in dead_handlers:
            ln = handler_tags[t]
            print(f"  {YELLOW}[INFO] tag \"{t}\" has handler at L{ln} but no _cmd_q.put → 可能是死碼{RESET}")
    else:
        print(f"  {GREEN}[OK] 所有 handler 均有對應 PUT 來源{RESET}")

    # ── 3. KNOWN_TAGS 過時偵測（腳本維護性）────────────────────
    print_section("Tag coverage ③: KNOWN_TAGS staleness check")
    stale = [t for t in KNOWN_TAGS if t not in handler_tags]
    missing_from_known = [t for t in handler_tags
                          if t not in KNOWN_TAGS
                          and t not in {
                              # 非模式切換的輔助 tag，不需納入封鎖分析
                              "msg", "player", "settlement_data", "set_time",
                              "time_overflow_warn", "screen_shake", "bgm_week",
                              "roll_call_set", "roll_call_attended", "roll_call_xed",
                              "roll_call_clear", "special_disabled", "allnighter_count",
                              "portrait_override", "pregame_countdown",
                              "cc_name", "cc_portrait", "cc_dept", "cc_drawbacks",
                              "cc_stats", "cc_extra", "cc_slot", "cc_summary",
                              "cc_de_level", "cc_talent", "cc_de_level",
                              "skip_popup_open",
                          }]
    if stale:
        for t in stale:
            print(f"  {YELLOW}[STALE] KNOWN_TAGS 含有 \"{t}\" 但 ui.py 中已無對應 handler → 可移除{RESET}")
    elif missing_from_known:
        for t in missing_from_known:
            ln = handler_tags.get(t, "?")
            print(f"  {YELLOW}[GAP] tag \"{t}\" (L{ln}) 是模式切換 handler 但不在 KNOWN_TAGS → 封鎖分析會遺漏它{RESET}")
    if not stale and not missing_from_known:
        print(f"  {GREEN}[OK] KNOWN_TAGS 與實際 handler 吻合（模式切換 tag 完整覆蓋）{RESET}")


# ═══════════════════════════════════════════════════════════════
#  輸出輔助
# ═══════════════════════════════════════════════════════════════

def print_section(title: str):
    width = 66
    print(f"\n{BOLD}{CYAN}{'='*width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*width}{RESET}")


# ═══════════════════════════════════════════════════════════════
#  主程式
# ═══════════════════════════════════════════════════════════════

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\n{BOLD}UI Static Analysis  --  {UI_PY.name}{RESET}")

    lines = load_source()

    # ── 1. 封鎖條件 ──────────────────────────────────────────
    print_section("① Early-exit CONTINUE conditions (MOUSEBUTTONDOWN handler)")
    blockers = find_blocking_conditions(lines)
    for b in blockers:
        icon = "[BLOCK]" if b["followed_by_continue"] else "[info ]"
        print(f"  {icon} L{b['line_no']:4d}  {b['vars']}  =>  {b['line'].strip()[:80]}")

    # ── 2. 各 tag 初始化分析 ────────────────────────────────
    print_section("② Per-tag init blocks: which blocking vars are reset?")
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

        missing = [v for v in BLOCKING_VARS
                   if v not in info["resets"] and v not in info["sets"]]
        has_set_issues = any(v in info["sets"] for v in BLOCKING_VARS)
        status = "" if has_set_issues else f"({GREEN}OK{RESET})"
        print(f"\n  tag: {BOLD}{tag}{RESET} {status}")
        if reset_report:
            print(f"       reset/set  : {', '.join(reset_report)}")
        print(f"       not mentioned: {', '.join(missing) or '(none)'}")

    # ── 3. 交叉分析：封鎖條件 × 模式初始化 ───────────────────
    print_section("③ Risk cross-analysis: tags that enter without clearing blocking vars")

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
            print(f"     If [{tag}] entered while any of these are True, clicks may be blocked!")

    if not risk_found:
        print(f"  {GREEN}[OK] No risks found (all blocking vars reset in relevant tag inits){RESET}")

    # ── 4. 事件處理器中設定封鎖變數的位置彙整 ────────────────
    print_section("④ Event handler: lines that SET a blocking var to True/non-empty")
    setters = find_event_handler_sets(lines)
    if setters:
        for s in setters:
            print(f"  L{s['line_no']:4d}  {s['var']}[0] = {s['value'][:50]}")
            print(f"         {s['line'].strip()[:80]}")
    else:
        print(f"  （無）")

    # ── 5. 音效系統審計 ────────────────────────────────────
    audit_sound_system(lines)

    # ── 6. 指令 tag 覆蓋率審計 ─────────────────────────────
    audit_tag_coverage(lines)

    print(f"\n{BOLD}Analysis complete.{RESET}\n")


if __name__ == "__main__":
    main()
