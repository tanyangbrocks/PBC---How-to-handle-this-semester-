#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_win.py — Windows 安裝檔自動打包
使用方式：python build_win.py

流程：
  1. 執行 pyinstaller main.spec（產生 dist/main/）
  2. 將 dist/main/ 壓縮為 dist/【Windows】How to handle this semester.zip
"""
import subprocess
import sys
import os
import zipfile

ROOT     = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist", "main")
ZIP_NAME = "【Windows】How to handle this semester.zip"
ZIP_PATH = os.path.join(ROOT, "dist", ZIP_NAME)


def run_pyinstaller():
    print("[build_win] 執行 PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "main.spec"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(f"[build_win] ❌  PyInstaller 失敗（exit {result.returncode}），中止。")
        sys.exit(1)
    print("[build_win] ✅  PyInstaller 完成")


def pack_zip():
    if not os.path.isdir(DIST_DIR):
        print(f"[build_win] ❌  找不到 {DIST_DIR}，請確認 PyInstaller 已正確執行。")
        sys.exit(1)

    print(f"[build_win] 打包 {ZIP_NAME}...")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, files in os.walk(DIST_DIR):
            for fname in files:
                abs_path = os.path.join(dirpath, fname)
                # 保留 main/ 前綴（玩家解壓後看到 main 資料夾）
                arc_name = os.path.relpath(abs_path, os.path.join(ROOT, "dist"))
                zf.write(abs_path, arc_name)

    size_mb = os.path.getsize(ZIP_PATH) / 1024 / 1024
    print(f"[build_win] ✅  {ZIP_NAME}（{size_mb:.1f} MB）→ dist/")


if __name__ == "__main__":
    run_pyinstaller()
    pack_zip()
