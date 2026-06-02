#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — pygbag build + patch + 乾淨伺服器
使用方式：python build.py

流程：
  1. 啟動 pygbag dev server（python -X utf8 -m pygbag main.py）
     ↳ 產生 build/web/（含 pygame_ce wheel）
  2. 偵測到 build 完成訊號後，自動執行 patch_index.py
  3. 終止 pygbag dev server
  4. 啟動 server.py（乾淨靜態伺服器，正確 COOP/COEP header）
  5. Ctrl+C 停止
"""
import subprocess
import sys
import os
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# pygbag 輸出中出現這些關鍵字代表 build 完成、server 已啟動
_BUILD_DONE_SIGNALS = [
    "serving at",
    "Serving at",
    "127.0.0.1",
    "localhost:8000",
    "http://localhost",
]

_patched   = False
_patch_lock = threading.Lock()


def _run_patch_and_switch(pygbag_proc):
    """Build 完成後：patch index.html → 終止 pygbag → 啟動 server.py。"""
    global _patched
    with _patch_lock:
        if _patched:
            return
        _patched = True

    time.sleep(1)   # 讓 pygbag server 完全就緒、檔案全部寫入

    # ── 步驟 2：patch index.html ──────────────────────────────────
    print("\n[build] 套用 patch_index.py...")
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "patch_index.py"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(f"[build] ❌  patch_index 失敗（exit {result.returncode}），中止。")
        pygbag_proc.terminate()
        return

    print("[build] ✅  patch 完成")

    # ── 步驟 2.5：打包 itch.io 上傳用 zip ────────────────────────
    import zipfile
    web_dir  = os.path.join(ROOT, "build", "web")
    zip_path = os.path.join(ROOT, "build", "pbc_web.zip")
    print("[build] 打包 itch.io 用 zip...")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, files in os.walk(web_dir):
                for fname in files:
                    abs_path = os.path.join(dirpath, fname)
                    arc_name = os.path.relpath(abs_path, web_dir)
                    zf.write(abs_path, arc_name)
        size_mb = os.path.getsize(zip_path) / 1024 / 1024
        print(f"[build] ✅  pbc_web.zip（{size_mb:.1f} MB）→ build/pbc_web.zip")
    except Exception as _ze:
        print(f"[build] ⚠  打包失敗（不影響後續）：{_ze}")

    # ── 步驟 3：終止 pygbag dev server ───────────────────────────
    print("[build] 終止 pygbag dev server...")
    pygbag_proc.terminate()
    try:
        pygbag_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pygbag_proc.kill()

    time.sleep(0.5)

    # ── 步驟 4：啟動乾淨的 server.py ─────────────────────────────
    print("[build] 啟動 server.py（乾淨靜態伺服器）...\n")
    server_proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "server.py"],
        cwd=ROOT,
    )
    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\n[build] 停止 server.py。")
        server_proc.terminate()


def _monitor(proc):
    """監控 pygbag stdout，偵測到 build 完成訊號就執行 patch + 切換伺服器。"""
    for raw in proc.stdout:
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            line = str(raw)
        sys.stdout.write(line)
        sys.stdout.flush()
        if not _patched and any(sig in line for sig in _BUILD_DONE_SIGNALS):
            threading.Thread(
                target=_run_patch_and_switch,
                args=(proc,),
                daemon=True,
            ).start()


def _file_watcher(pygbag_proc):
    """
    備援觸發器：監看 build/web/index.html 是否出現／更新。
    Windows 上 pygbag 常在 WASM mimetype 警告後卡住、不再輸出任何訊號，
    導致 _monitor 永遠無法觸發 patch。
    此執行緒改由檔案系統確認 build 完成，與 _monitor 競速，先到先觸發（有鎖防重複）。
    """
    target = os.path.join(ROOT, "build", "web", "index.html")
    existed     = os.path.isfile(target)
    init_mtime  = os.path.getmtime(target) if existed else 0

    POLL  = 5    # 每 5 秒輪詢一次
    LIMIT = 120  # 最多等 600 秒（10 分鐘）

    print("[build] 備援監看 build/web/index.html（每 5 秒檢查）...")
    for i in range(LIMIT):
        time.sleep(POLL)
        if _patched:          # stdout 那側已觸發，退出
            return
        if os.path.isfile(target):
            mtime = os.path.getmtime(target)
            if mtime > init_mtime + 1:   # 檔案有更新，判定 build 完成
                elapsed = (i + 1) * POLL
                print(f"\n[build] 備援觸發：index.html 已更新（等待 {elapsed}s）")
                _run_patch_and_switch(pygbag_proc)
                return

    if not _patched:
        print("[build] ⚠  等待 10 分鐘仍未偵測到 build 完成，請確認 pygbag 是否正常運行。")


print("[build] 啟動 pygbag（產生 build/web/）...")
pygbag_proc = subprocess.Popen(
    [sys.executable, "-X", "utf8", "-m", "pygbag", "main.py"],
    cwd=ROOT,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

monitor_thread = threading.Thread(target=_monitor, args=(pygbag_proc,), daemon=True)
watcher_thread = threading.Thread(target=_file_watcher, args=(pygbag_proc,), daemon=True)
monitor_thread.start()
watcher_thread.start()

try:
    pygbag_proc.wait()
except KeyboardInterrupt:
    print("\n[build] 停止 pygbag。")
    pygbag_proc.terminate()

# pygbag 結束後，monitor thread 可能還在跑 server.py，等它
monitor_thread.join(timeout=2)
