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
                              "check_pygbag_compat.py")
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
_found = False
for pyf in GAME_PY:
    src = pyf.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        # 找設 tabindex="-1" 且作用在 canvas 的程式碼
        if "tabindex" in line and ("-1" in line):
            if "canvas" in line or "querySelectorAll" in line or "setAttribute" in line:
                _red(f"{pyf.name}:{i}  canvas 被設為 tabindex=-1 → 滑鼠點擊與鍵盤全部失效")
                _found = True

if not _found:
    _ok("無危險的 canvas tabindex=-1 操作")


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

    if "visibilitychange" in _html:
        _ok("Page Visibility 音訊修復已套用")
    else:
        _yellow("index.html 缺少 Page Visibility 音訊修復 → 重跑 patch_index.py")

    if "pbc_bar" in _html:
        _ok("自訂載入畫面已套用")
    else:
        _yellow("index.html 缺少自訂載入畫面 → 重跑 patch_index.py")

    # 檢查 tabindex=-1 是否殘留在已 patch 的 html
    if 'tabindex="-1"' in _html or "tabindex='-1'" in _html:
        _yellow("index.html 內含 tabindex=-1 → 確認是否影響 canvas 事件")
    else:
        _ok("index.html 無危險 tabindex=-1")

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
