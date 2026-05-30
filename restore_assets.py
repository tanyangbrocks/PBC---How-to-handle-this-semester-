"""
restore_assets.py
=================
將 convert_assets.py 轉換前備份的原始檔案完整還原。

使用方式：
    python restore_assets.py

還原內容：
  - 原始 MP3 音檔（從 _asset_backup/ 複製回來）
  - 原始 WebP 圖檔（從 _asset_backup/ 複製回來）
  - 原始 Python 程式碼（從 _asset_backup/_py_snapshot/ 複製回來）
  - 自動刪除轉換後產生的 OGG / PNG / JPEG 檔
"""

import os
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# 備份在專案目錄外
BACKUP_DIR   = os.path.join(os.path.dirname(PROJECT_ROOT), "_pbc_asset_backup")
PY_SNAP_DIR  = os.path.join(BACKUP_DIR, "_py_snapshot")

if not os.path.isdir(BACKUP_DIR):
    print("❌ 找不到備份資料夾 _asset_backup/")
    print("   請先執行 convert_assets.py（它會在轉換前自動備份）。")
    raise SystemExit(1)

# ── 1. 還原原始音訊 / 圖片檔案 ──────────────────────────────────
print("── 還原原始資產檔案 ─────────────────────────────────────")
restored = 0
for dirpath, _, filenames in os.walk(BACKUP_DIR):
    # 跳過 Python 快照資料夾
    if PY_SNAP_DIR in dirpath:
        continue
    for fn in filenames:
        src = os.path.join(dirpath, fn)
        # 計算對應的專案路徑（去掉 _asset_backup/ 前綴）
        rel = os.path.relpath(src, BACKUP_DIR)
        dst = os.path.join(PROJECT_ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  還原：{rel}")
        restored += 1

print(f"\n共還原 {restored} 個原始檔案。")

# ── 2. 刪除轉換後產生的 OGG / PNG / JPEG（僅刪除有對應原始檔的） ──
print("\n── 刪除轉換後的新格式檔案 ──────────────────────────────")
deleted = 0
CONVERTED_EXTS = {".ogg", ".png", ".jpg"}
ORIGINAL_EXTS  = {".ogg", ".png"}

# 列出所有已還原的原始檔名（無副檔名）
original_stems = set()
for dirpath, _, filenames in os.walk(BACKUP_DIR):
    if PY_SNAP_DIR in dirpath:
        continue
    for fn in filenames:
        stem = os.path.splitext(fn)[0]
        rel_dir = os.path.relpath(dirpath, BACKUP_DIR)
        original_stems.add(os.path.join(rel_dir, stem))

# 掃描專案，刪除對應的轉換檔
asset_dir = os.path.join(PROJECT_ROOT, "asset")
for dirpath, _, filenames in os.walk(asset_dir):
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in CONVERTED_EXTS:
            continue
        stem = os.path.splitext(fn)[0]
        rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)
        key = os.path.join(rel_dir, stem)
        if key in original_stems:
            full = os.path.join(dirpath, fn)
            os.remove(full)
            print(f"  刪除：{os.path.relpath(full, PROJECT_ROOT)}")
            deleted += 1

print(f"\n共刪除 {deleted} 個轉換後檔案。")

# ── 3. 還原 Python 程式碼 ────────────────────────────────────────
print("\n── 還原 Python 程式碼 ──────────────────────────────────")
if os.path.isdir(PY_SNAP_DIR):
    py_restored = 0
    for fn in os.listdir(PY_SNAP_DIR):
        if not fn.endswith(".py"):
            continue
        src = os.path.join(PY_SNAP_DIR, fn)
        dst = os.path.join(PROJECT_ROOT, fn)
        shutil.copy2(src, dst)
        print(f"  還原：{fn}")
        py_restored += 1
    print(f"\n共還原 {py_restored} 個 Python 檔。")
else:
    print("  （無 Python 快照，跳過）")

# ── 4. 結果摘要 ──────────────────────────────────────────────────
print("\n" + "="*50)
print("✅  還原完成！專案已回到轉換前的狀態。")
print("="*50)
print("\n若要重新轉換：")
print("  python convert_assets.py")
