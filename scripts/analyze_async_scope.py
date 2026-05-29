#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  scripts/analyze_async_scope.py
#
#  分析哪些函式需要改成 async def、哪些呼叫點需要加 await，
#  為 pygbag 重構的 Phase 4 提供精確的工作清單。
#
#  原理：
#    1. 定義「種子」async 函式（ui.py 中現有的阻塞 UI 函式）
#    2. 用 AST 建立呼叫圖（caller → callees）
#    3. 從種子出發做不動點傳播，找出所有需要 async 的函式
#    4. 輸出需要改寫的函式清單 + 需要加 await 的呼叫點清單
#
#  執行：python scripts/analyze_async_scope.py
# ============================================================
import ast
import sys
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 掃描目標 ───────────────────────────────────────────────
GAME_FILES = [
    "ui.py",
    "main.py",
    "turn_engine.py",
    "character.py",
    "event_system.py",
    "skill_system.py",
    "shop_V03.py",
]

# ── 種子：這些函式目前阻塞，Phase 4 會改成 async ───────────
SEED_ASYNC = {
    "ask_yn",
    "ask_choice",
    "ask_ok",
    "ask_text",
    "ask_subject_popup",
    "ask_withdrawal_popup",
    "ask_exam_start",
    "ask_exam_question",
    "run_shape_minigame",
    "tell_story",
    "wait_start",
    "wait_restart",
    "show_extra_event_popup",
    "notify_grade_report",
    "notify_timetable",
    "ask_ok_col",          # 若存在
    "open_shop",           # shop 若有阻塞呼叫
}

# ── ANSI 顏色 ───────────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ============================================================
#  Step 1：解析 AST，建立函式定義 + 呼叫圖
# ============================================================

# func_info[func_name] = {
#     "file":   str,
#     "lineno": int,
#     "calls":  [(callee_name, lineno), ...]
# }
func_info: dict = {}

class _FuncAnalyzer(ast.NodeVisitor):
    """遍歷 AST，收集函式定義及其內部呼叫。"""

    def __init__(self, filename: str):
        self.filename    = filename
        self.func_stack: list[str] = []

    def _enter_func(self, node):
        name = node.name
        # 同名函式只保留第一個（跨檔案的名稱衝突極少）
        if name not in func_info:
            func_info[name] = {
                "file":   self.filename,
                "lineno": node.lineno,
                "calls":  [],
            }
        self.func_stack.append(name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_FunctionDef      = _enter_func
    visit_AsyncFunctionDef = _enter_func

    def visit_Call(self, node):
        if not self.func_stack:
            self.generic_visit(node)
            return
        caller = self.func_stack[-1]
        callee = None
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee:
            func_info[caller]["calls"].append((callee, node.lineno))
        self.generic_visit(node)


for fname in GAME_FILES:
    fpath = PROJECT / fname
    if not fpath.exists():
        continue
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=fname)
        _FuncAnalyzer(fname).visit(tree)
    except SyntaxError as e:
        print(f"{YELLOW}[WARN] {fname} 語法錯誤，跳過：{e}{RESET}")

# ============================================================
#  Step 2：不動點傳播，找出所有需要 async 的函式
# ============================================================

needs_async: set[str] = set(SEED_ASYNC)
changed = True
while changed:
    changed = False
    for fname_key, info in func_info.items():
        if fname_key in needs_async:
            continue
        callees = {c for c, _ in info["calls"]}
        if callees & needs_async:
            needs_async.add(fname_key)
            changed = True

# ============================================================
#  Step 3：找出需要加 await 的呼叫點
# ============================================================

# await_sites: [(file, lineno, caller, callee)]
await_sites: list[tuple] = []
for func_name in needs_async:
    if func_name not in func_info:
        continue
    info = func_info[func_name]
    for callee, lineno in info["calls"]:
        if callee in needs_async:
            await_sites.append((info["file"], lineno, func_name, callee))

await_sites.sort(key=lambda x: (x[0], x[1]))

# ============================================================
#  Step 4：整理輸出
# ============================================================

# 需要改 async def（排除種子本身）
async_funcs = sorted(
    [
        (info["file"], info["lineno"], name)
        for name, info in func_info.items()
        if name in needs_async and name not in SEED_ASYNC
    ],
    key=lambda x: (x[0], x[1]),
)

# 按檔案分組
def _group_by_file(items, file_idx=0):
    d = defaultdict(list)
    for item in items:
        d[item[file_idx]].append(item)
    return d

# ── 印出報告 ─────────────────────────────────────────────────
SEP = "=" * 64

print(f"\n{BOLD}{CYAN}{SEP}{RESET}")
print(f"{BOLD}{CYAN}  async 轉換範圍分析  （pygbag Phase 4 工作清單）{RESET}")
print(f"{BOLD}{CYAN}{SEP}{RESET}")

# ① 種子函式
print(f"\n{BOLD}{CYAN}① 種子 async 函式（ui.py 阻塞呼叫，共 {len(SEED_ASYNC & set(func_info))} 個有解析到）{RESET}")
found_seeds = sorted(SEED_ASYNC & set(func_info))
missing_seeds = sorted(SEED_ASYNC - set(func_info))
for s in found_seeds:
    info = func_info[s]
    print(f"  {GREEN}[OK]{RESET}  {info['file']}:{info['lineno']}  {s}()")
for s in missing_seeds:
    print(f"  {YELLOW}[--]{RESET}  （未解析到）{s}  ← 可能不存在或名稱不同")

# ② 需要改成 async def 的函式
print(f"\n{BOLD}{CYAN}② 需要改成 async def 的函式（共 {len(async_funcs)} 個）{RESET}")
grouped_af = _group_by_file(async_funcs)
for ffile in GAME_FILES:
    items = grouped_af.get(ffile, [])
    if not items:
        continue
    print(f"\n  {BOLD}[{ffile}]{RESET}")
    for _, lineno, fname in items:
        # 說明是哪個 async 函式導致它需要 async
        triggers = sorted({
            callee for callee, _ in func_info[fname]["calls"]
            if callee in needs_async
        })
        trig_str = ", ".join(triggers[:3]) + ("…" if len(triggers) > 3 else "")
        print(f"    L{lineno:<6} {fname}()  ← 呼叫了: {trig_str}")

# ③ 需要加 await 的呼叫點
print(f"\n{BOLD}{CYAN}③ 需要加 await 的呼叫點（共 {len(await_sites)} 個）{RESET}")
grouped_aw = _group_by_file(await_sites)
for ffile in GAME_FILES:
    items = grouped_aw.get(ffile, [])
    if not items:
        continue
    print(f"\n  {BOLD}[{ffile}]{RESET}")
    for _, lineno, caller, callee in items:
        print(f"    L{lineno:<6} {caller}()  →  await {callee}()")

# ④ 統計摘要
print(f"\n{BOLD}{CYAN}{SEP}{RESET}")
print(f"{BOLD}  摘要{RESET}")
print(f"  需要 async def 的函式  : {RED}{len(async_funcs)}{RESET} 個")
print(f"  需要加 await 的呼叫點  : {RED}{len(await_sites)}{RESET} 個")
by_file = defaultdict(int)
for f, _, _, _ in await_sites:
    by_file[f] += 1
for ffile in GAME_FILES:
    n = by_file.get(ffile, 0)
    if n:
        print(f"    {ffile:<30} {n} 個 await")
print(f"{BOLD}{CYAN}{SEP}{RESET}\n")
