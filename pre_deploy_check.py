#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre_deploy_check.py — 部署前 WASM bug 預警腳本
================================================
與 check_ui_state.py（tag/event 靜態分析）互補，
專門針對「部署到網路後才會炸」的問題類別。

執行：python pre_deploy_check.py

檢查項目：
  🔴 A. eval() 內含中文字串       → WASM encoding bug，亂碼
  🔴 B. canvas tabindex=-1        → pygame 滑鼠/鍵盤事件全部失效
  🔴 C. platform.window.屬性=中文 → encoding bug，應改用 json.dumps
  🔴 D. 靜態資源不存在            → WASM 載入失敗，遊戲卡死
  🔴 E. play_sfx key 找不到對應   → 音效靜音或 KeyError
  🟡 F. while 等待迴圈無 yield    → 主迴圈凍結
  🟡 G. build 產出完整性          → patch 未套用或包未建立
  🟡 H. _WEEK_BGM / BG 資源缺漏   → 週次切換時黑畫面或靜音
  ℹ️  I. 遊戲邏輯裡的裸 print()   → WASM pyconsole 隱藏，debug 訊息消失
  🔴 S. index.html 本地資源引用   → favicon / .apk / browserfs 等缺失
  🟡 T. SharedArrayBuffer / COOP  → http.server 缺標頭，多執行緒靜默失效
  🔴 U. 動態連線探測              → server 運行時 wheel/包 404 = 灰屏根因
  🔴 V. 資源引用大小寫不一致      → Windows 可用→WASM VFS 找不到
  🟡 W. Build 過期偵測            → .py 比 index.html 新，需重新 build
  🔴 X. WASM 禁用模組 import      → subprocess/multiprocessing/ctypes 等
  🔴 Y. threading 殘留            → asyncio 重構後應完全移除
  🟡 Z. 遊戲邏輯阻塞 I/O & 寫入  → WASM VFS 唯讀，網路呼叫靜默失效
  🔴 AA. 資源檔名非 ASCII/空格    → WASM VFS Emscripten 不支援 Unicode
  🟡 BB. index.html HTTP 外部源   → HTTPS 部署時混合內容被瀏覽器封鎖
  🟡 CC. 大型音訊檔案             → 影響 WASM 初次載入時間與記憶體
  🔴 DD. asyncio.run() 入口驗證   → pygbag 必要條件，包在 __main__ 會失效
  🔴 EE. SysFont 無 TTF 備援      → WASM 找不到系統字型，文字全部消失
  🟡 FF. 遊戲包 / 資源總大小      → 過大導致瀏覽器載入失敗或逾時
"""

import ast
import io
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Windows cp950 終端機無法顯示中文輸出，強制換 utf-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT      = Path(__file__).parent
ASSET_DIR = ROOT / "asset"
BUILD_WEB = ROOT / "build" / "web"
SE_DIR    = ASSET_DIR / "audio" / "se"
BGM_DIR   = ASSET_DIR / "audio" / "bgm"
PIC_DIR   = ASSET_DIR / "picture"

# ── 顏色 ──────────────────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_counts = {"red": 0, "yellow": 0, "info": 0}

def _red(msg):    _counts["red"]    += 1; print(f"  {RED}[ERR] {msg}{RESET}")
def _yellow(msg): _counts["yellow"] += 1; print(f"  {YELLOW}[WRN] {msg}{RESET}")
def _info(msg):   _counts["info"]   += 1; print(f"  [INF] {msg}")
def _ok(msg):     print(f"  {GREEN}[OK ] {msg}{RESET}")
def _section(t):
    print(f"\n{BOLD}{CYAN}{'='*62}{RESET}")
    print(f"{BOLD}{CYAN}  {t}{RESET}")
    print(f"{BOLD}{CYAN}{'='*62}{RESET}")

# ── 讀取所有遊戲 .py ──────────────────────────────────────────
GAME_PY = [p for p in ROOT.glob("*.py")
           if p.name not in ("pre_deploy_check.py",
                              "patch_index.py",
                              "refactor_ui.py",
                              "restore_assets.py",
                              "convert_assets.py",
                              "check_ui_state.py",
                              "check_pygbag_compat.py",
                              "build.py",      # build 工具，在開發機執行，不進 WASM
                              "ui_draw.py")    # 重構前舊版整合檔，已不再被 import
           and "_origin" not in p.stem]   # 排除 *_origin.py 備份檔

def _has_cjk(s: str) -> bool:
    return any('　' <= c <= '鿿' or '＀' <= c <= '￯' for c in s)


# ════════════════════════════════════════════════════════════════
# A. eval() 內含中文字串
# ════════════════════════════════════════════════════════════════
_section("A. eval() 內含中文字串（WASM encoding bug）")
_found = False
_EVAL_RE = re.compile(r'(platform\.window|_plt\.window)\.eval\s*\(')

for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "eval"):
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        # 只看純字串常數（不是 f-string / 變數）
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            # 跳過純 JS 注釋行（// ...）裡的中文，不會造成 encoding 問題
            non_comment = "\n".join(
                l for l in arg0.value.splitlines()
                if not l.strip().startswith("//")
            )
            if _has_cjk(non_comment):
                _red(f"{pyf.name}:{node.lineno}  eval() 直接含中文 → 改用 json.dumps 傳入 JS 變數")
                _found = True

if not _found:
    _ok("eval() 內無直接中文字串")


# ════════════════════════════════════════════════════════════════
# B. canvas tabindex=-1（會讓 pygame 事件全部失效）
# ════════════════════════════════════════════════════════════════
_section("B. canvas tabindex=-1（pygame 事件失效）")
# IME overlay（__cc_show）在 patch_index.py 裡會暫時設 tabindex=-1，
# 但 __cc_submit 會還原，屬於受控操作。
# 此處只抓「沒有配對 restore 的裸操作」，即 Python 端的 _wasm_input_setup 型錯誤。
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        if "tabindex" not in line or "-1" not in line:
            continue
        if not ("canvas" in line or "querySelectorAll" in line or "setAttribute" in line):
            continue
        # 若同函式 ±20 行內有 restore（tabindex 還原 / oldTab / pointerEvents 還原）就跳過
        ctx = "\n".join(lines[max(0,i-20):min(len(lines),i+20)])
        if any(kw in ctx for kw in ("_oldTab", "oldPe", "setAttribute('tabindex','1')",
                                     'setAttribute("tabindex","1")', "removeAttribute('tabindex')",
                                     'removeAttribute("tabindex")', "__cc_submit", "_imeKeyBlock")):
            continue
        _red(f"{pyf.name}:{i}  canvas 設 tabindex=-1 且無 restore → 滑鼠/鍵盤事件永久失效")
        _found = True

if not _found:
    _ok("canvas tabindex=-1 操作均有對應 restore（或不存在）")


# ════════════════════════════════════════════════════════════════
# C. platform.window.屬性 = 中文（應改用 json.dumps）
# ════════════════════════════════════════════════════════════════
_section("C. platform.window.屬性 直接賦值中文（encoding bug）")
_found = False
_WIN_ASSIGN = re.compile(r'(platform|_plt)\.window\.\w+\s*=(?!=)')
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        if _WIN_ASSIGN.search(line) and _has_cjk(line):
            _red(f"{pyf.name}:{i}  platform.window 屬性直接賦中文值 → 改用 _plt.window.eval + json.dumps")
            _found = True

if not _found:
    _ok("platform.window 賦值無中文直接賦值")


# ════════════════════════════════════════════════════════════════
# D. 靜態資源存在性（圖片 / 字型）
# ════════════════════════════════════════════════════════════════
_section("D. 靜態資源存在性（圖片 / 字型）")

# 建立 asset 目錄所有檔案索引
_asset_index: dict[str, Path] = {}
for p in ASSET_DIR.rglob("*"):
    if p.is_file():
        _asset_index[p.name] = p

# 從 ui_const.py 手動收集已知資源引用
_ui_const = ROOT / "ui_const.py"
_refs: list[tuple[str, str, int]] = []   # (filename, source_file, lineno)

if _ui_const.exists():
    src = _ui_const.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        for m in re.finditer(r'''["']([^"'\{\}]+\.(png|jpg|jpeg|ttf|otf|webp))["']''',
                             line, re.IGNORECASE):
            raw = m.group(1)
            if '{' in raw or '}' in raw:
                continue
            fname = Path(raw).name
            _refs.append((fname, "ui_const.py", i))

# 掃描其他 py 檔的圖片/字型引用
for pyf in GAME_PY:
    if pyf.name == "ui_const.py":
        continue
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        for m in re.finditer(r'''["']([^"'\{\}]+\.(png|jpg|jpeg|ttf|otf|webp))["']''',
                             line, re.IGNORECASE):
            raw = m.group(1)
            if '{' in raw or '}' in raw:
                continue
            fname = Path(raw).name
            if "/" not in raw and "\\" not in raw:
                _refs.append((fname, pyf.name, i))

_found = False
_seen: set[str] = set()
for fname, src_file, lineno in _refs:
    if fname in _seen:
        continue
    _seen.add(fname)
    if fname not in _asset_index:
        _red(f"找不到資源：{fname}  （引用於 {src_file}:{lineno}）")
        _found = True

if not _found:
    _ok(f"所有圖片 / 字型資源均存在（{len(_seen)} 個參照）")


# ════════════════════════════════════════════════════════════════
# E. play_sfx key 找不到對應檔案
#    （check_ui_state.py 已做 key→file 驗證；此處補做「直接檔名呼叫」）
# ════════════════════════════════════════════════════════════════
_section("E. play_sfx() 直接傳檔名 key 存在性")

# 從 ui.py 取出 _sfx 字典：key -> filename
_sfx_map: dict[str, str] = {}
_ui_src = (ROOT / "ui.py").read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r'_sfx\["([^"]+)"\]\s*=\s*_ld\("([^"]+)"\)', _ui_src):
    _sfx_map[m.group(1)] = m.group(2)

# 把直接傳檔名（含 .ogg）的 play_sfx 呼叫也抓進來
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        for m in re.finditer(r'play_sfx\(\s*["\']([^"\']+)["\']', line):
            key = m.group(1)
            if key not in _sfx_map:
                # 可能直接傳 filename（turn_engine 的 benkirb-... 等）
                fname = key if key.endswith(".ogg") else key + ".ogg"
                if not (SE_DIR / fname).exists() and not (BGM_DIR / fname).exists():
                    _red(f"{pyf.name}:{i}  play_sfx(\"{key}\") → 在 _sfx 字典和音效目錄都找不到")
                    _found = True
                else:
                    _info(f"{pyf.name}:{i}  play_sfx(\"{key}\") 直接傳檔名（非 _sfx key），可正常播放")

if not _found:
    _ok("play_sfx() 的 key 全部可解析")


# ════════════════════════════════════════════════════════════════
# F. while 等待迴圈無 yield（潛在主迴圈凍結）
# ════════════════════════════════════════════════════════════════
_section("F. while 等待迴圈無 await asyncio.sleep（主迴圈凍結風險）")
_found = False

def _has_sleep_yield(while_node) -> bool:
    """任何 await 呼叫都算 yield（包含 await ask_*、await asyncio.sleep 等）。"""
    for child in ast.walk(while_node):
        if isinstance(child, ast.Await):
            return True
    return False

for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    # 只看 async 函式內的 while
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.While):
                continue
            # 只關心明顯的「等待旗標」迴圈
            is_flag_loop = (
                isinstance(node.test, ast.Constant) and node.test.value is True
            ) or isinstance(node.test, ast.UnaryOp)
            if is_flag_loop and not _has_sleep_yield(node):
                _yellow(f"{pyf.name}:{node.lineno}  async 函式 {fn.name}() 的 while 迴圈無 await sleep → 可能凍結")
                _found = True

if not _found:
    _ok("所有 async 等待迴圈均有 await asyncio.sleep")


# ════════════════════════════════════════════════════════════════
# G. build 產出完整性
# ════════════════════════════════════════════════════════════════
_section("G. build 產出完整性")

_index = BUILD_WEB / "index.html"
if not _index.exists():
    _red(f"找不到 {_index.relative_to(ROOT)} → 尚未執行 pygbag build")
else:
    _html = _index.read_text(encoding="utf-8", errors="replace")

    # 以 patch_index.py 實際注入的關鍵字串驗證每個 patch 是否已套用
    _patches = [
        ("pbc_bar",              "自訂載入畫面"),
        ("AudioWorklet",         "AudioWorklet proxy（音訊主執行緒隔離）"),
        ("visibilitychange",     "Page Visibility AudioContext resume"),
        ("sdl2-proxy",           "AudioWorklet Worklet processor"),
        ("browserfs.min.js",     "browserfs URL 修復"),
        ("cdn.jsdelivr.net",     "browserfs 改用 jsdelivr CDN"),
        ("__cc_show",            "中文 IME overlay（FS bridge）"),
        ("__cc_submit",          "IME overlay 提交函式"),
        ("documentElement",      "全螢幕使用 documentElement（IME 可見）"),
        ("handleCanvasClick",    "全螢幕按鈕座標換算"),
        ("1280 / (rect.width",   "全螢幕座標修正（canvas.width ≠ 遊戲寬）"),
        ("__fs_state.txt",       "全螢幕狀態 FS bridge"),
    ]
    for keyword, label in _patches:
        if keyword in _html:
            _ok(f"patch 已套用：{label}")
        else:
            _red(f"patch 缺失：{label} → 重跑 patch_index.py")

    # 遊戲包
    _pkg_name = "pbc---how-to-handle-this-semester-"
    _apk = BUILD_WEB / f"{_pkg_name}.apk"
    _tgz = BUILD_WEB / f"{_pkg_name}.tar.gz"
    if _apk.exists():
        _ok(f"遊戲包存在：{_apk.name}  ({_apk.stat().st_size // 1024} KB)")
    elif _tgz.exists():
        _ok(f"遊戲包存在：{_tgz.name}  ({_tgz.stat().st_size // 1024} KB)")
    else:
        _red("找不到 .apk 或 .tar.gz → 需要重新 pygbag build")


# ════════════════════════════════════════════════════════════════
# H. _WEEK_BGM 和 _WEEK_BG 背景/音樂資源缺漏
# ════════════════════════════════════════════════════════════════
_section("H. 週次 BGM / 背景圖資源缺漏")

_ui_const_src = _ui_const.read_text(encoding="utf-8", errors="replace") if _ui_const.exists() else ""

# 抓 _WEEK_BGM
_WEEK_BGM_RE = re.compile(r'\d+\s*:\s*"([^"]+\.ogg)"')
_bgm_files = _WEEK_BGM_RE.findall(_ui_const_src)
_bgm_found = False
for fname in _bgm_files:
    if not (BGM_DIR / fname).exists():
        _red(f"_WEEK_BGM 找不到 BGM 檔：{fname}  （週次音樂缺失）")
        _bgm_found = True
if not _bgm_found and _bgm_files:
    _ok(f"_WEEK_BGM 所有 BGM 均存在（{len(_bgm_files)} 首）")

# 抓 _WEEK_BG（背景圖）
_BG_RE = re.compile(r'\d+\s*:\s*"([^"]+\.(jpg|jpeg|png))"')
_bg_files = _BG_RE.findall(_ui_const_src)
_BG_DIR = PIC_DIR / "background"
_bg_found = False
for fname, _ in _bg_files:
    if not (_BG_DIR / fname).exists() and not (PIC_DIR / fname).exists():
        _yellow(f"_WEEK_BG 找不到背景圖：{fname}")
        _bg_found = True
if not _bg_found and _bg_files:
    _ok(f"_WEEK_BG 所有背景圖均存在（{len(_bg_files)} 張）")


# ════════════════════════════════════════════════════════════════
# I. 遊戲邏輯裡的裸 print()
# ════════════════════════════════════════════════════════════════
_section("I. 遊戲邏輯裡的裸 print()（WASM 下 pyconsole 隱藏）")
_LOGIC_FILES = {"main.py", "character.py", "turn_engine.py",
                "event_system.py", "skill_system.py", "shop_V03.py"}
_found = False
for pyf in GAME_PY:
    if pyf.name not in _LOGIC_FILES:
        continue
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        s = line.strip()
        if s.startswith("print(") and "# ok" not in s and "# debug-ok" not in s:
            _info(f"{pyf.name}:{i}  print() → 玩家看不到，考慮改 ui.notify()")
            _found = True
if not _found:
    _ok("遊戲邏輯無裸 print()（或已標記 # ok）")


# ════════════════════════════════════════════════════════════════
# J. sys.exit() 在遊戲邏輯裡（WASM 直接崩潰）
# ════════════════════════════════════════════════════════════════
_section("J. sys.exit() / raise SystemExit（WASM 崩潰）")
_CRASH_RE = re.compile(r'\bsys\.exit\s*\(|raise\s+SystemExit')
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _CRASH_RE.search(line):
            # 若上一行有 if ... != "emscripten" 或 if ... == "desktop" 就跳過
            prev = src.splitlines()[i - 2].strip() if i >= 2 else ""
            if "emscripten" in prev or "platform" in prev:
                continue
            _red(f"{pyf.name}:{i}  sys.exit() / SystemExit → WASM 直接崩潰，改用旗標或讓 run_ui 自然結束")
            _found = True
if not _found:
    _ok("無 sys.exit() / SystemExit 在遊戲程式碼中")


# ════════════════════════════════════════════════════════════════
# K. time.sleep() 在遊戲邏輯裡（阻塞 asyncio 主迴圈）
# ════════════════════════════════════════════════════════════════
_section("K. time.sleep() 在遊戲邏輯裡（阻塞主迴圈）")
_SLEEP_RE = re.compile(r'\btime\.sleep\s*\(')
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        if _SLEEP_RE.search(line):
            _red(f"{pyf.name}:{i}  time.sleep() → 阻塞 asyncio，改用 await asyncio.sleep()")
            _found = True
if not _found:
    _ok("無 time.sleep() 在遊戲邏輯中")


# ════════════════════════════════════════════════════════════════
# L. pygame.FULLSCREEN 相容性（WASM 全螢幕需要特殊處理）
# ════════════════════════════════════════════════════════════════
_section("L. pygame.FULLSCREEN 相容性（WASM 全螢幕）")
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        if "pygame.FULLSCREEN" in line and "set_mode" in line:
            # 檢查是否有 platform / emscripten 的保護
            context_start = max(0, i - 5)
            context = "\n".join(src.splitlines()[context_start:i])
            if "emscripten" not in context and "platform" not in context:
                _yellow(f"{pyf.name}:{i}  pygame.FULLSCREEN 無 WASM 平台判斷 → 可能在瀏覽器黑屏")
                _found = True
if not _found:
    _ok("pygame.FULLSCREEN 有平台保護或未使用")


# ════════════════════════════════════════════════════════════════
# M. 音訊格式（MP3/WAV 在 WASM 瀏覽器可能無法播放）
# ════════════════════════════════════════════════════════════════
_section("M. 音訊格式（MP3/WAV → 瀏覽器兼容性問題）")
_found = False
# 掃描 asset/audio 目錄實際存在的非 OGG 音訊
for afile in (SE_DIR.glob("*") if SE_DIR.exists() else []):
    if afile.suffix.lower() in (".mp3", ".wav"):
        _red(f"音效目錄含 {afile.suffix} 檔：{afile.name} → pygbag WASM 不支援 MP3/WAV，需轉 OGG")
        _found = True
for afile in (BGM_DIR.glob("*") if BGM_DIR.exists() else []):
    if afile.suffix.lower() in (".mp3", ".wav"):
        _red(f"BGM 目錄含 {afile.suffix} 檔：{afile.name} → pygbag WASM 不支援 MP3/WAV，需轉 OGG")
        _found = True
# 掃描程式碼裡直接引用非 OGG 格式
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        for m in re.finditer(r'''["']([^"']+\.(mp3|wav))["']''', line, re.IGNORECASE):
            _yellow(f"{pyf.name}:{i}  引用 {m.group(2).upper()} 格式：{m.group(1)} → 改用 OGG")
            _found = True
if not _found:
    _ok("所有音訊格式均為 OGG")


# ════════════════════════════════════════════════════════════════
# N. smoothscale 在每幀繪製函式裡且無快取（卡頓風險）
# ════════════════════════════════════════════════════════════════
_section("N. smoothscale 在繪製函式無快取（WASM 卡頓）")
_DRAW_FUNCS = re.compile(r'^def _draw_\w+\(')
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines()
    in_draw_fn = False
    fn_name = ""
    fn_start = 0
    for i, line in enumerate(lines, 1):
        if _DRAW_FUNCS.match(line.strip()):
            in_draw_fn = True
            fn_name = line.strip().split("(")[0].replace("def ", "")
            fn_start = i
        elif re.match(r'^def \w+|^class \w+', line) and not line.startswith(" "):
            in_draw_fn = False
        if in_draw_fn and "smoothscale" in line:
            # 若同函式近 5 行內有 cache/快取/dict 就跳過
            ctx = "\n".join(lines[max(0, i-6):i+2])
            if not any(kw in ctx for kw in ("cache", "_cache", "_scl", "_orig", "if key", "if (key")):
                _yellow(f"{pyf.name}:{i}  {fn_name}() 含 smoothscale 且無明顯快取 → 每幀重縮可能卡頓")
                _found = True
if not _found:
    _ok("smoothscale 呼叫均有快取保護")


# ════════════════════════════════════════════════════════════════
# O. 非 Python 程式碼檔案（本專案嚴禁）
# ════════════════════════════════════════════════════════════════
_section("O. 非 Python 程式碼檔案（嚴禁）")
_CODE_EXTS  = {".js", ".ts", ".jsx", ".tsx", ".lua", ".cpp", ".c",
               ".h", ".java", ".rb", ".go", ".rs", ".cs", ".php",
               ".sh", ".bat", ".ps1", ".css", ".html"}
_ASSET_EXTS = {".ogg", ".mp3", ".wav", ".png", ".jpg", ".jpeg",
               ".ttf", ".otf", ".ttc", ".webp", ".gif", ".ico",
               ".webm", ".mp4", ".apk", ".gz", ".json",
               ".txt", ".md", ".toml", ".cfg", ".ini",
               ".spec", ".gitignore", ".log", ".LICENSE", ""}
_SKIP_DIRS  = {"build", "dist", "__pycache__", ".git", ".idea",
               ".pytest_cache", "node_modules", "_asset_backup"}
_found = False
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if any(part in _SKIP_DIRS for part in p.parts):
        continue
    ext = p.suffix.lower()
    if ext in _CODE_EXTS:
        _red(f"發現非 Python 程式碼檔：{p.relative_to(ROOT)}  → 本專案嚴禁")
        _found = True
if not _found:
    _ok("專案內無非 Python 程式碼檔案")


# ════════════════════════════════════════════════════════════════
# P. open() 使用非 resource_path 的硬編碼路徑（WASM 找不到）
# ════════════════════════════════════════════════════════════════
_section("P. 遊戲邏輯 open() 未用 resource_path（WASM 路徑錯誤）")
_OPEN_RE = re.compile(r'\bopen\s*\(')
# 排除只用相對短字串的（如 open("r") 類似錯誤偵測）
_found = False
for pyf in GAME_PY:
    if pyf.name in ("ui_const.py",):
        continue
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _OPEN_RE.search(line) and "resource_path" not in line:
            # 進一步過濾：只有含路徑字串的才警告
            if re.search(r'''open\s*\(\s*["'][^"']{5,}["']''', line):
                _yellow(f"{pyf.name}:{i}  open() 使用硬編碼路徑 → WASM 可能找不到，改用 resource_path()")
                _found = True
if not _found:
    _ok("遊戲邏輯 open() 均透過 resource_path 或動態路徑")


# ════════════════════════════════════════════════════════════════
# Q. mixer 參數審計（音質 / 卡頓 / 延遲根因）
# ════════════════════════════════════════════════════════════════
_section("Q. pygame.mixer.init() 參數審計（音質與延遲）")
_MIX_RE = re.compile(r'pygame\.mixer\.init\s*\(([^)]+)\)')
_found_any = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        m = _MIX_RE.search(line)
        if not m:
            continue
        args = m.group(1)
        _found_any = True
        freq  = re.search(r'frequency\s*=\s*(\d+)', args)
        buf   = re.search(r'buffer\s*=\s*(\d+)', args)
        freq_v = int(freq.group(1)) if freq else None
        buf_v  = int(buf.group(1)) if buf else None
        print(f"  [INF] {pyf.name}:{i}  mixer.init({args.strip()})")
        if freq_v and freq_v < 44100:
            _info(f"  → frequency={freq_v}Hz（低於 44100）：音質下降，但減輕 WASM 主線程負擔")
        if buf_v:
            if buf_v > 2048:
                _yellow(f"  → buffer={buf_v}：buffer 過大，音效延遲明顯（建議 WASM ≤ 2048）")
            elif buf_v < 512:
                _yellow(f"  → buffer={buf_v}：buffer 過小，WASM 下易爆音（建議 WASM ≥ 1024）")
            else:
                _info(f"  → buffer={buf_v}（合理範圍）")

if not _found_any:
    _yellow("找不到 pygame.mixer.init() 呼叫 → 使用預設參數，WASM 下可能音質差")


# ════════════════════════════════════════════════════════════════
# R. pygame_ce wheel 存在性（本機 http.server 測試時灰屏根因）
# ════════════════════════════════════════════════════════════════
_section("R. pygame_ce wheel（本機 http.server 灰屏風險）")
_cdn_dir = BUILD_WEB / "cdn" / "cp312"
_wheels  = list(_cdn_dir.glob("pygame_ce*.whl")) if _cdn_dir.exists() else []
if _wheels:
    _ok(f"pygame_ce wheel 已存在於 build/web/cdn/cp312/：{_wheels[0].name}")
else:
    _yellow(
        "build/web/cdn/cp312/ 無 pygame_ce wheel → "
        "用 http.server 本機測試時會 404 灰屏。\n"
        "  解法：用 python build.py（pygbag dev server 自動提供 wheel），\n"
        "  或部署到有 HTTPS 的伺服器（會從 CDN 下載）。"
    )


# ════════════════════════════════════════════════════════════════
# S. index.html 本地資源引用完整性
# ════════════════════════════════════════════════════════════════
_section("S. index.html 本地資源引用完整性")

_index_s = BUILD_WEB / "index.html"
if not _index_s.exists():
    _yellow("index.html 不存在，略過 S 檢查（需先執行 pygbag build）")
else:
    _html_s = _index_s.read_text(encoding="utf-8", errors="replace")

    _local_refs: list[str] = []

    # 可識別為本地資源的副檔名集合
    _RESOURCE_EXTS = {
        ".js", ".css", ".html", ".htm", ".whl", ".apk", ".gz",
        ".json", ".wasm", ".png", ".ico", ".jpg", ".jpeg", ".svg",
        ".ttf", ".otf", ".webp", ".ogg", ".mp3", ".wav", ".txt",
    }

    # src=、href=、data-*= 屬性（含單引號與雙引號形式）
    for _m in re.finditer(
            r'''(?:src|href|data-[\w-]+)\s*=\s*["']([^"']+)["']''',
            _html_s, re.IGNORECASE):
        _val = _m.group(1).split("?")[0].split("#")[0].strip()
        if not _val:
            continue
        if _val.startswith(("http://", "https://", "//",
                             "data:", "javascript:", "#", "about:")):
            continue
        # 必須含 / 路徑分隔符，或結尾是已知資源副檔名
        _ext = Path(_val.split("/")[-1]).suffix.lower()
        if "/" in _val or _ext in _RESOURCE_EXTS:
            _local_refs.append(_val)

    # fetch( 字串
    for _m in re.finditer(r'''fetch\s*\(\s*["']([^"']+)["']''', _html_s):
        _val = _m.group(1).split("?")[0].split("#")[0].strip()
        if _val and not _val.startswith(("http://", "https://", "//")):
            _local_refs.append(_val)

    _s_found  = False
    _seen_refs: set[str] = set()
    for _ref in _local_refs:
        if _ref in _seen_refs:
            continue
        _seen_refs.add(_ref)
        # 正規化：去掉開頭的 / 或 ./
        _clean = _ref.lstrip("/")
        if _clean.startswith("./"):
            _clean = _clean[2:]
        if not (BUILD_WEB / _clean).exists():
            _red(f"index.html 引用本地資源不存在：{_ref}")
            _s_found = True

    if not _s_found:
        _ok(f"index.html 所有本地資源均存在（{len(_seen_refs)} 個引用檢查通過）")


# ════════════════════════════════════════════════════════════════
# T. SharedArrayBuffer / COOP 標頭警告
# ════════════════════════════════════════════════════════════════
_section("T. SharedArrayBuffer / COOP 標頭需求檢測")

_index_t = BUILD_WEB / "index.html"
if not _index_t.exists():
    _yellow("index.html 不存在，略過 T 檢查")
else:
    _html_t = _index_t.read_text(encoding="utf-8", errors="replace")
    _ISOLATION_KEYWORDS = (
        "crossOriginIsolated",
        "SharedArrayBuffer",
        "Atomics.wait",
        "Atomics.waitAsync",
        "require-corp",
        "same-origin",
    )
    _matched_kw = [kw for kw in _ISOLATION_KEYWORDS if kw in _html_t]
    if _matched_kw:
        _yellow(
            "index.html 含跨來源隔離相關關鍵字：" + "、".join(_matched_kw) + "\n"
            "  http.server 不會設定以下 HTTP 標頭，WASM 多執行緒功能將靜默失效：\n"
            "    Cross-Origin-Opener-Policy: same-origin\n"
            "    Cross-Origin-Embedder-Policy: require-corp\n"
            "  建議改用 pygbag 內建 dev server，或部署到有正確回應標頭的 HTTPS 伺服器。"
        )
    else:
        _ok("index.html 無 SharedArrayBuffer / crossOriginIsolated 相關需求，http.server 足夠")


# ════════════════════════════════════════════════════════════════
# U. 動態連線探測（server 跑起來時才執行）
# ════════════════════════════════════════════════════════════════
_section("U. 動態連線探測（localhost:8000）")

_SERVER    = "http://localhost:8000"
_PKG_NAME  = "pbc---how-to-handle-this-semester-"
_server_up = False

try:
    _ping = urllib.request.urlopen(f"{_SERVER}/", timeout=2)
    _server_up = True
    _ping.close()
except Exception:
    pass

if not _server_up:
    _ok("localhost:8000 無回應，略過動態連線探測"
        "（需先 cd build/web && python -m http.server 8000）")
else:
    # ── U-1  GET / → 200 + text/html ────────────────────────
    try:
        _r = urllib.request.urlopen(f"{_SERVER}/", timeout=3)
        _ct = _r.headers.get("Content-Type", "")
        _r.close()
        if _r.status == 200 and "html" in _ct:
            _ok(f"GET /  → {_r.status} OK, Content-Type: {_ct.split(';')[0].strip()}")
        else:
            _yellow(f"GET /  → {_r.status}, Content-Type: {_ct}（預期 200 text/html）")
    except Exception as _e:
        _yellow(f"GET / 連線異常：{_e}")

    # ── U-2  GET 遊戲包（.apk 優先，.tar.gz 備用）───────────
    _pkg_ok = False
    for _ext in (".apk", ".tar.gz"):
        try:
            _r = urllib.request.urlopen(f"{_SERVER}/{_PKG_NAME}{_ext}", timeout=8)
            _cl = _r.headers.get("Content-Length")
            _r.close()
            if _r.status == 200:
                if _cl is not None and int(_cl) == 0:
                    _yellow(f"GET /{_PKG_NAME}{_ext} → 200 但 Content-Length=0（包可能空白）")
                else:
                    _size = f" ({int(_cl) // 1024} KB)" if _cl else ""
                    _ok(f"GET /{_PKG_NAME}{_ext} → 200 OK{_size}")
                _pkg_ok = True
                break
        except urllib.error.HTTPError as _e:
            if _e.code == 404:
                continue   # 試下一個副檔名
            _yellow(f"GET /{_PKG_NAME}{_ext} → HTTP {_e.code}")
            _pkg_ok = True   # 非 404 錯誤，不必再試
            break
        except Exception as _e:
            _yellow(f"GET /{_PKG_NAME}{_ext} 連線異常：{_e}")
            _pkg_ok = True
            break
    if not _pkg_ok:
        _red(f"GET /{_PKG_NAME}.apk / .tar.gz → 404 — 遊戲包不可訪問，玩家無法載入遊戲")

    # ── U-3  GET pygame_ce wheel → 404 = 灰屏根因 ───────────
    _cdn_local = BUILD_WEB / "cdn" / "cp312"
    _whl_list  = list(_cdn_local.glob("pygame_ce*.whl")) if _cdn_local.exists() else []
    if _whl_list:
        _whl_name = _whl_list[0].name
        try:
            _r = urllib.request.urlopen(
                f"{_SERVER}/cdn/cp312/{_whl_name}", timeout=8)
            _r.close()
            if _r.status == 200:
                _ok(f"GET /cdn/cp312/{_whl_name} → 200 OK（wheel 可訪問）")
            else:
                _red(f"GET /cdn/cp312/{_whl_name} → {_r.status} — 灰屏根因！")
        except urllib.error.HTTPError as _e:
            _red(f"GET /cdn/cp312/{_whl_name} → HTTP {_e.code} — 灰屏根因！")
        except Exception as _e:
            _yellow(f"GET /cdn/cp312/{_whl_name} 連線異常：{_e}")
    else:
        _red("build/web/cdn/cp312/ 無 pygame_ce wheel，http.server 必然 404 灰屏")

    # ── U-4  回應標頭：Cross-Origin-Opener-Policy ─────────────
    try:
        _r = urllib.request.urlopen(f"{_SERVER}/", timeout=3)
        _coop = _r.headers.get("Cross-Origin-Opener-Policy")
        _r.close()
        if _coop:
            _ok(f"回應含 Cross-Origin-Opener-Policy: {_coop}")
        else:
            _yellow(
                "回應無 Cross-Origin-Opener-Policy 標頭（http.server 預設行為）\n"
                "  若遊戲依賴 SharedArrayBuffer / WASM 多執行緒，功能將靜默失效"
            )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# V. 資源引用大小寫一致性（Windows→WASM VFS 大小寫敏感陷阱）
# ════════════════════════════════════════════════════════════════
_section("V. 資源引用大小寫一致性（Windows→WASM VFS 陷阱）")

# 建立不分大小寫的全資源映射（含音訊）
_asset_lower: dict[str, Path] = {k.lower(): v for k, v in _asset_index.items()}
_audio_lower: dict[str, Path] = {}
for _adir in (SE_DIR, BGM_DIR):
    if _adir.exists():
        for _ap in _adir.iterdir():
            if _ap.is_file():
                _audio_lower[_ap.name.lower()] = _ap

_v_found  = False
_seen_v: set[str] = set()

# 圖片 / 字型（重用 D 節的 _refs）
for _fname_v, _src_v, _ln_v in _refs:
    if _fname_v in _seen_v:
        continue
    _seen_v.add(_fname_v)
    if _fname_v in _asset_index:
        continue           # 完全一致
    _actual_v = _asset_lower.get(_fname_v.lower())
    if _actual_v is not None:
        _red(f"{_src_v}:{_ln_v}  大小寫不符（Windows 可用→WASM 失效）：\n"
             f"    引用「{_fname_v}」  磁碟實際「{_actual_v.name}」")
        _v_found = True
    # 真正不存在的情況 D 節已報告，此處不重複

# 音效 sfx map（重用 E 節的 _sfx_map）
for _sfx_k, _sfx_fn in _sfx_map.items():
    _act_a = _audio_lower.get(_sfx_fn.lower())
    if _act_a is not None and _act_a.name != _sfx_fn:
        _red(f"ui.py  _sfx[\"{_sfx_k}\"]  音效大小寫不符："
             f"引用「{_sfx_fn}」  磁碟「{_act_a.name}」")
        _v_found = True

# _WEEK_BGM（重用 H 節的 _bgm_files）
for _bgm_fn in _bgm_files:
    _act_b = _audio_lower.get(_bgm_fn.lower())
    if _act_b is not None and _act_b.name != _bgm_fn:
        _red(f"ui_const.py  _WEEK_BGM 大小寫不符："
             f"引用「{_bgm_fn}」  磁碟「{_act_b.name}」")
        _v_found = True

if not _v_found:
    _ok("所有資源引用大小寫與磁碟完全一致（WASM VFS 安全）")


# ════════════════════════════════════════════════════════════════
# W. Build 過期偵測（遊戲 .py 比 index.html 新 → 需重新 build）
# ════════════════════════════════════════════════════════════════
_section("W. Build 過期偵測（.py 修改時間 vs index.html）")

_index_w = BUILD_WEB / "index.html"
if not _index_w.exists():
    _yellow("index.html 不存在，略過 W 檢查")
else:
    _build_mtime = _index_w.stat().st_mtime
    # 只比對遊戲邏輯 .py（排除工具腳本與備份）
    _SKIP_W = {"pre_deploy_check.py", "check_ui_state.py", "patch_index.py",
               "refactor_ui.py", "restore_assets.py", "convert_assets.py",
               "build.py", "check_pygbag_compat.py"}
    _newer_py = sorted(
        (p for p in ROOT.glob("*.py")
         if p.name not in _SKIP_W
         and "_origin" not in p.stem
         and p.stat().st_mtime > _build_mtime),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if _newer_py:
        _preview = "\n".join(
            f"    {p.name}  (+{int(p.stat().st_mtime - _build_mtime)}s)"
            for p in _newer_py[:6]
        ) + ("\n    ..." if len(_newer_py) > 6 else "")
        _yellow(
            f"{len(_newer_py)} 個遊戲 .py 比 build/web/index.html 新，"
            "build 可能過期：\n" + _preview
        )
    else:
        _ok("build/web/index.html 與所有遊戲 .py 同步（無過期風險）")


# ════════════════════════════════════════════════════════════════
# X. WASM 禁用模組 import（subprocess / multiprocessing / ctypes 等）
# ════════════════════════════════════════════════════════════════
_section("X. WASM 禁用模組 import 偵測")

_WASM_BANNED: dict[str, str] = {
    "subprocess":      "WASM 無法啟動子行程",
    "multiprocessing": "WASM 無多行程支援",
    "ctypes":          "WASM 無 C 動態連結庫呼叫",
    "socket":          "WASM 不支援原始 socket（需用 fetch/WebSocket）",
    "ssl":             "WASM 無 ssl 模組（由瀏覽器原生 TLS 處理）",
    "select":          "WASM 不支援 select/poll",
    "mmap":            "WASM 無 mmap",
    "signal":          "WASM 僅支援極少數 signal",
    "fcntl":           "Unix 限定，WASM 不存在",
    "termios":         "Unix 限定，WASM 不存在",
    "winreg":          "Windows 限定，WASM 不存在",
    "cv2":             "OpenCV 未包含於 pygbag WASM 環境",
}

# Windows/Mac 平台限定模組：若包在 sys.platform 判斷內則降為警告
_PLATFORM_GUARDED = {"ctypes", "winreg", "winsound", "fcntl", "termios"}

def _is_platform_guarded(src: str, lineno: int) -> bool:
    """檢查 lineno 前 15 行內是否有 sys.platform / platform.system 判斷。"""
    lines = src.splitlines()
    window = lines[max(0, lineno - 15): lineno]
    return any("sys.platform" in l or "platform.system" in l for l in window)

_x_found = False
for _pyf in GAME_PY:
    _src = _pyf.read_text(encoding="utf-8", errors="replace")
    try:
        _tree = ast.parse(_src)
    except SyntaxError:
        continue
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.Import):
            for _alias in _node.names:
                _mod_root = _alias.name.split(".")[0]
                if _mod_root not in _WASM_BANNED:
                    continue
                if _mod_root in _PLATFORM_GUARDED and \
                        _is_platform_guarded(_src, _node.lineno):
                    _info(f"{_pyf.name}:{_node.lineno}  import {_alias.name}"
                          " 在 sys.platform 保護內（WASM 不執行此分支）")
                else:
                    _red(f"{_pyf.name}:{_node.lineno}  import {_alias.name}"
                         f" → {_WASM_BANNED[_mod_root]}")
                    _x_found = True
        elif isinstance(_node, ast.ImportFrom):
            if not _node.module:
                continue
            _mod_root = _node.module.split(".")[0]
            if _mod_root not in _WASM_BANNED:
                continue
            _names = ", ".join(a.name for a in _node.names)
            if _mod_root in _PLATFORM_GUARDED and \
                    _is_platform_guarded(_src, _node.lineno):
                _info(f"{_pyf.name}:{_node.lineno}  from {_node.module}"
                      f" import {_names} 在 sys.platform 保護內（WASM 安全）")
            else:
                _red(f"{_pyf.name}:{_node.lineno}  from {_node.module}"
                     f" import {_names} → {_WASM_BANNED[_mod_root]}")
                _x_found = True

if not _x_found:
    _ok("無 WASM 禁用模組 import（build 工具除外）")


# ════════════════════════════════════════════════════════════════
# Y. threading 殘留偵測（asyncio 重構後應完全移除）
# ════════════════════════════════════════════════════════════════
_section("Y. threading 殘留偵測（asyncio 重構後）")

# 實際執行緒物件建立（WASM 下執行緒無法運作）
_THREAD_CALL_RE = re.compile(
    r'\bthreading\.'
    r'(Thread|Lock|RLock|Event|Condition|Semaphore|BoundedSemaphore|Timer|Barrier)'
    r'\s*\('
)
# 阻塞式佇列（asyncio 環境應改用 asyncio.Queue）
_BLOCKING_QUEUE_RE = re.compile(r'\bqueue\.(Queue|SimpleQueue|LifoQueue|PriorityQueue)\s*\(')

_y_found = False
for _pyf in GAME_PY:
    _src = _pyf.read_text(encoding="utf-8", errors="replace")
    # import threading 是否仍存在
    for _m in re.finditer(r'^(?:import threading|from threading import)', _src, re.MULTILINE):
        _ln = _src[:_m.start()].count("\n") + 1
        _yellow(f"{_pyf.name}:{_ln}  仍有 threading import，asyncio 重構後應可移除")
        _y_found = True
    # threading 物件建立
    for _i, _line in enumerate(_src.splitlines(), 1):
        if _line.strip().startswith("#"):
            continue
        if _THREAD_CALL_RE.search(_line):
            _red(f"{_pyf.name}:{_i}  threading 物件建立 → WASM 執行緒無法運作")
            _y_found = True
        if _BLOCKING_QUEUE_RE.search(_line):
            _red(f"{_pyf.name}:{_i}  queue.Queue() 阻塞佇列 → 改用 asyncio.Queue()")
            _y_found = True

if not _y_found:
    _ok("遊戲邏輯無 threading 殘留")


# ════════════════════════════════════════════════════════════════
# Z. 遊戲邏輯內阻塞 I/O & 檔案寫入（WASM 限制）
# ════════════════════════════════════════════════════════════════
_section("Z. 遊戲邏輯內阻塞 I/O & 檔案寫入（WASM 限制）")

# 寫入/追加模式的 open()；排除 open("r"...) 純讀取
_WRITE_OPEN_RE  = re.compile(
    r'''\bopen\s*\([^,)]+,\s*["'](?:w|a|x|r\+)[bt+]*["']'''
)
# 外部網路呼叫（WASM 需透過 fetch/WebSocket JS 互操作）
_NET_CALL_RE = re.compile(
    r'\b(requests\.(get|post|put|delete|patch|head|request|Session)'
    r'|urllib\.request\.urlopen'
    r'|http\.client\.(HTTPConnection|HTTPSConnection)'
    r'|ftplib\.FTP|smtplib\.SMTP)\s*\('
)
# pickle / shelve 持久化（WASM VFS 寫入失效）
_PICKLE_RE = re.compile(r'\b(pickle\.(dump|dumps)|shelve\.open)\s*\(')

_Z_LOGIC = {"main.py", "character.py", "turn_engine.py",
            "event_system.py", "skill_system.py", "shop_V03.py"}

_z_found = False
for _pyf in GAME_PY:
    if _pyf.name not in _Z_LOGIC:
        continue
    _src = _pyf.read_text(encoding="utf-8", errors="replace")
    for _i, _line in enumerate(_src.splitlines(), 1):
        _s = _line.strip()
        if _s.startswith("#"):
            continue
        if _WRITE_OPEN_RE.search(_line):
            _yellow(f"{_pyf.name}:{_i}  open() 寫入模式 → WASM VFS 通常唯讀，寫入靜默失敗")
            _z_found = True
        if _NET_CALL_RE.search(_line):
            _red(f"{_pyf.name}:{_i}  阻塞式網路呼叫 → WASM 不支援，需改用 fetch() JS 互操作")
            _z_found = True
        if _PICKLE_RE.search(_line):
            _yellow(f"{_pyf.name}:{_i}  pickle/shelve 寫入 → WASM VFS 無法持久化，資料每次重置")
            _z_found = True

if not _z_found:
    _ok("遊戲邏輯無阻塞式網路呼叫或危險檔案寫入")


# ════════════════════════════════════════════════════════════════
# AA. 資源檔名含非 ASCII 或危險字元（WASM VFS Emscripten 不支援）
# ════════════════════════════════════════════════════════════════
_section("AA. 資源檔名含非 ASCII 或危險字元（WASM VFS 相容性）")

# POSIX / URL 安全字元：字母、數字、- _ . 以外均視為危險
_SAFE_FNAME_RE = re.compile(r'^[\w.\-]+$', re.ASCII)

_aa_found = False
for _ap in ASSET_DIR.rglob("*"):
    if not _ap.is_file():
        continue
    _n = _ap.name
    if not _n.isascii():
        _red(f"非 ASCII 檔名：{_ap.relative_to(ROOT)}\n"
             f"    Emscripten VFS 不支援 Unicode 路徑，WASM 必然找不到此檔")
        _aa_found = True
    elif not _SAFE_FNAME_RE.match(_n):
        _bad_chars = sorted({c for c in _n if not re.match(r'[\w.\-]', c, re.ASCII)})
        _yellow(f"含危險字元 {_bad_chars}：{_ap.relative_to(ROOT)}\n"
                f"    空格或特殊符號可能導致 WASM VFS 路徑解析失敗")
        _aa_found = True

if not _aa_found:
    _ok("所有資源檔名均為 ASCII 安全字元（WASM VFS 相容）")


# ════════════════════════════════════════════════════════════════
# BB. index.html HTTP 外部資源（HTTPS 部署時混合內容被封鎖）
# ════════════════════════════════════════════════════════════════
_section("BB. index.html HTTP 外部資源（HTTPS 混合內容風險）")

_index_bb = BUILD_WEB / "index.html"
if not _index_bb.exists():
    _yellow("index.html 不存在，略過 BB 檢查")
else:
    _html_bb = _index_bb.read_text(encoding="utf-8", errors="replace")
    _bb_found = False

    # HTML 屬性中的 http:// 外部資源
    for _m in re.finditer(
            r'''(?:src|href|action|data|content)\s*=\s*["'](http://[^"']+)["']''',
            _html_bb, re.IGNORECASE):
        _yellow(f"index.html 含 http:// 外部資源（部署 HTTPS 時瀏覽器封鎖）：\n"
                f"    {_m.group(1)[:120]}")
        _bb_found = True

    # JS 程式碼中的 fetch("http://...")
    for _m in re.finditer(r'''fetch\s*\(\s*["'](http://[^"']+)["']''', _html_bb):
        _yellow(f"index.html JS fetch(http://...) → HTTPS 部署時混合內容封鎖：\n"
                f"    {_m.group(1)[:120]}")
        _bb_found = True

    # script src 中的非 HTTPS CDN
    for _m in re.finditer(r'''<script[^>]+src=["'](http://[^"']+)["']''',
                           _html_bb, re.IGNORECASE):
        _red(f"index.html <script src> 含 http:// CDN → 非 HTTPS，現代瀏覽器拒絕執行：\n"
             f"    {_m.group(1)[:120]}")
        _bb_found = True

    if not _bb_found:
        _ok("index.html 無 http:// 外部資源（混合內容安全）")


# ════════════════════════════════════════════════════════════════
# CC. 大型音訊檔案警告（影響 WASM 初次載入時間與記憶體）
# ════════════════════════════════════════════════════════════════
_section("CC. 大型音訊檔案警告（WASM 載入效能）")

_CC_SE_WARN_KB    = 500      # 單一音效  > 500 KB
_CC_BGM_WARN_KB   = 5 * 1024 # 單一 BGM  > 5 MB
_CC_TOTAL_WARN_MB = 50        # 音訊總計  > 50 MB

_cc_found        = False
_cc_total_bytes  = 0

for _af in (list(SE_DIR.iterdir()) if SE_DIR.exists() else []):
    if not _af.is_file():
        continue
    _sz = _af.stat().st_size
    _cc_total_bytes += _sz
    if _sz > _CC_SE_WARN_KB * 1024:
        _yellow(f"音效過大：{_af.name}  ({_sz // 1024} KB > {_CC_SE_WARN_KB} KB)"
                " → 增加 WASM 初載記憶體")
        _cc_found = True

for _af in (list(BGM_DIR.iterdir()) if BGM_DIR.exists() else []):
    if not _af.is_file():
        continue
    _sz = _af.stat().st_size
    _cc_total_bytes += _sz
    if _sz > _CC_BGM_WARN_KB * 1024:
        _yellow(f"BGM 過大：{_af.name}  ({_sz // 1024} KB > {_CC_BGM_WARN_KB} KB)"
                " → 增加 WASM 初載時間")
        _cc_found = True

_cc_total_mb = _cc_total_bytes / (1024 * 1024)
if _cc_total_mb > _CC_TOTAL_WARN_MB:
    _yellow(f"音訊資源總計 {_cc_total_mb:.1f} MB（> {_CC_TOTAL_WARN_MB} MB）"
            "，建議壓縮或按需載入")
    _cc_found = True
else:
    _info(f"音訊資源總計 {_cc_total_mb:.1f} MB")

if not _cc_found:
    _ok(f"所有音訊大小正常（總計 {_cc_total_mb:.1f} MB）")


# ════════════════════════════════════════════════════════════════
# DD. asyncio.run() 入口模式驗證（pygbag 必要條件）
# ════════════════════════════════════════════════════════════════
_section("DD. asyncio.run() 入口模式驗證（pygbag 必要條件）")

_main_py = ROOT / "main.py"
if not _main_py.exists():
    _red("找不到 main.py → 無法驗證 asyncio 入口")
else:
    _main_src = _main_py.read_text(encoding="utf-8", errors="replace")
    _dd_found = False

    # 必要：asyncio.run() 必須在模組層級（非縮排的頂層）
    if not re.search(r'^asyncio\.run\s*\(', _main_src, re.MULTILINE):
        _red("main.py 無模組層級 asyncio.run() → pygbag 無法排程協程，遊戲不會啟動")
        _dd_found = True
    else:
        _ok("main.py 含模組層級 asyncio.run()（pygbag 入口正確）")

    # 危險：asyncio.run() 藏在 if __name__ == '__main__' 裡
    _nm_block = re.search(r'^if\s+__name__\s*==\s*["\']__main__["\']\s*:',
                           _main_src, re.MULTILINE)
    if _nm_block:
        _block_src = _main_src[_nm_block.start():]
        if re.search(r'asyncio\.run\s*\(', _block_src):
            _red("asyncio.run() 包在 if __name__ == '__main__' 內 → "
                 "pygbag 直接 import main.py，__main__ 區塊不執行，遊戲協程永遠不啟動")
            _dd_found = True

    # 舊式事件迴圈 API
    if re.search(r'get_event_loop\s*\(\s*\)\.run_until_complete', _main_src):
        _red("main.py 含 get_event_loop().run_until_complete() → 改用 asyncio.run()")
        _dd_found = True

    # async def main() 存在性
    if not re.search(r'^async\s+def\s+main\s*\(\s*\)', _main_src, re.MULTILINE):
        _yellow("main.py 缺少 async def main()，確認頂層協程名稱與 asyncio.run() 一致")
        _dd_found = True

    if not _dd_found:
        _ok("main.py asyncio 入口模式完整正確")


# ════════════════════════════════════════════════════════════════
# EE. pygame.font.SysFont() 無 TTF 備援（WASM 無系統字型）
# ════════════════════════════════════════════════════════════════
_section("EE. pygame.font.SysFont() 無 TTF 備援（WASM 字型缺失）")

_SYSFONT_RE = re.compile(r'\bpygame\.font\.SysFont\s*\(')
_TTF_FALLBACK_KW = (".ttf", ".otf", ".ttc", "resource_path", "pygame.font.Font(")
_ee_found = False

for _pyf in GAME_PY:
    _src = _pyf.read_text(encoding="utf-8", errors="replace")
    _lines = _src.splitlines()
    for _i, _line in enumerate(_lines, 1):
        if _line.strip().startswith("#"):
            continue
        if not _SYSFONT_RE.search(_line):
            continue
        # 查看上下各 15 行內是否有 TTF 備援
        _ctx = "\n".join(_lines[max(0, _i - 15): _i + 15])
        if any(kw in _ctx for kw in _TTF_FALLBACK_KW):
            _info(f"{_pyf.name}:{_i}  SysFont() 附近有 TTF 備援，請確認回退邏輯正確")
        else:
            _red(f"{_pyf.name}:{_i}  SysFont() 無 TTF 備援 → "
                 "WASM 找不到任何系統字型，所有文字將消失")
            _ee_found = True

if not _ee_found:
    _ok("無裸 SysFont() 呼叫（或均已附 TTF 備援）")


# ════════════════════════════════════════════════════════════════
# FF. 遊戲包與資源總大小估算（過大導致瀏覽器載入失敗）
# ════════════════════════════════════════════════════════════════
_section("FF. 遊戲包 / 資源總大小估算（瀏覽器載入閾值）")

# 實際 build 包大小
_ff_pkg_bytes = 0
_ff_pkg_name  = ""
for _ext in (".apk", ".tar.gz"):
    _fp = BUILD_WEB / f"pbc---how-to-handle-this-semester-{_ext}"
    if _fp.exists():
        _ff_pkg_bytes = _fp.stat().st_size
        _ff_pkg_name  = _fp.name
        break

# asset/ 目錄總計
_ff_asset_bytes = sum(
    p.stat().st_size for p in ASSET_DIR.rglob("*") if p.is_file()
)

# 分項大小（圖片 / 音訊 / 字型）
_ff_img_bytes   = sum(p.stat().st_size for p in ASSET_DIR.rglob("*")
                      if p.is_file() and p.suffix.lower()
                      in {".png", ".jpg", ".jpeg", ".webp", ".gif"})
_ff_audio_bytes = sum(p.stat().st_size for p in ASSET_DIR.rglob("*")
                      if p.is_file() and p.suffix.lower()
                      in {".ogg", ".mp3", ".wav"})
_ff_font_bytes  = sum(p.stat().st_size for p in ASSET_DIR.rglob("*")
                      if p.is_file() and p.suffix.lower()
                      in {".ttf", ".otf", ".ttc"})

def _mb(b: int) -> str:
    return f"{b / 1048576:.1f} MB"

_info(f"asset/ 總計 {_mb(_ff_asset_bytes)}"
      f"（圖片 {_mb(_ff_img_bytes)} ｜音訊 {_mb(_ff_audio_bytes)}"
      f" ｜字型 {_mb(_ff_font_bytes)}）")

if _ff_pkg_bytes:
    _info(f"遊戲包 {_ff_pkg_name}：{_mb(_ff_pkg_bytes)}")
    if _ff_pkg_bytes > 200 * 1048576:
        _yellow(f"遊戲包 > 200 MB（{_mb(_ff_pkg_bytes)}）→ 行動瀏覽器可能拒絕載入，考慮分割資源")
    elif _ff_pkg_bytes > 100 * 1048576:
        _yellow(f"遊戲包 > 100 MB（{_mb(_ff_pkg_bytes)}）→ 初次載入在慢速網路需 30s+，建議 loading 提示")
    else:
        _ok(f"遊戲包 {_mb(_ff_pkg_bytes)}（在合理範圍）")
else:
    _yellow("找不到遊戲包，略過大小檢查")

# 單張圖片過大檢查（>3 MB 的單一圖片可能在低記憶體裝置 OOM）
_FF_IMG_WARN_MB = 3
for _ip in ASSET_DIR.rglob("*"):
    if _ip.is_file() and _ip.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        _isz = _ip.stat().st_size
        if _isz > _FF_IMG_WARN_MB * 1048576:
            _yellow(f"單張圖片過大：{_ip.relative_to(ROOT)}  ({_mb(_isz)})"
                    " → 低記憶體裝置載入可能 OOM")


# ════════════════════════════════════════════════════════════════
# 摘要
# ════════════════════════════════════════════════════════════════
print(f"\n{BOLD}{'='*62}{RESET}")
print(f"{BOLD}  部署前檢查摘要{RESET}")
print(f"{BOLD}{'='*62}{RESET}")
print(f"  {RED}[ERR] 高優先問題  : {_counts['red']} 處{RESET}")
print(f"  {YELLOW}[WRN] 中優先問題  : {_counts['yellow']} 處{RESET}")
print(f"  [INF] 提示事項    : {_counts['info']} 處")

if _counts["red"]:
    print(f"\n  {RED}{BOLD}[STOP] 有高優先問題，請修復後再部署！{RESET}")
elif _counts["yellow"]:
    print(f"\n  {YELLOW}部署前請確認中優先問題是否影響玩家體驗。{RESET}")
else:
    print(f"\n  {GREEN}{BOLD}[PASS] 無重大問題，可以部署！{RESET}")
