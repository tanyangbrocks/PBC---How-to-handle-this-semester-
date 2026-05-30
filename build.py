#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — pygbag build + 自動套用 patch_index
使用方式：python build.py

流程：
  1. 啟動 pygbag dev server（python -X utf8 -m pygbag main.py）
  2. 偵測到 build 完成訊號後，自動執行 patch_index.py
  3. server 繼續運行，開啟 http://localhost:8000 測試
  4. Ctrl+C 停止
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

_patched = False
_patch_lock = threading.Lock()

def _run_patch():
    global _patched
    with _patch_lock:
        if _patched:
            return
        _patched = True
    time.sleep(1)   # 讓 server 完全就緒
    print("\n[build] 偵測到 build 完成，套用 patch_index.py...")
    result = subprocess.run(
        [sys.executable, "patch_index.py"],
        cwd=ROOT,
    )
    if result.returncode == 0:
        print("[build] patch 完成！開啟 http://localhost:8000 測試，Ctrl+C 停止。\n")
    else:
        print(f"[build] patch_index 失敗（exit {result.returncode}）。\n")

def _monitor(proc):
    """監控 pygbag stdout，偵測到 build 完成訊號就執行 patch。"""
    for raw in proc.stdout:
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            line = str(raw)
        sys.stdout.write(line)
        sys.stdout.flush()
        if not _patched and any(sig in line for sig in _BUILD_DONE_SIGNALS):
            threading.Thread(target=_run_patch, daemon=True).start()

print("[build] 啟動 pygbag...")
proc = subprocess.Popen(
    [sys.executable, "-X", "utf8", "-m", "pygbag", "main.py"],
    cwd=ROOT,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

monitor_thread = threading.Thread(target=_monitor, args=(proc,), daemon=True)
monitor_thread.start()

try:
    proc.wait()
except KeyboardInterrupt:
    print("\n[build] 停止。")
    proc.terminate()
