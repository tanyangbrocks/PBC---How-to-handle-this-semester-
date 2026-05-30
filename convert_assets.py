"""
convert_assets.py
=================
批次轉換：
  - MP3  → OGG（音訊，pygbag WASM 不支援 MP3）
  - WebP → PNG（有透明度的圖：立繪、icon、游標等）
  - WebP → JPEG（無透明度的背景圖，檔案較小）

自動更新所有 .py 程式碼裡的副檔名參照。

使用方式：
    python convert_assets.py

需求：系統已安裝 ffmpeg。
"""

import os
import shutil
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR    = os.path.join(PROJECT_ROOT, "asset")
# 備份放在專案目錄外，避免 pygbag 掃描時把原始 MP3/WAV 也打包進去
BACKUP_DIR   = os.path.join(os.path.dirname(PROJECT_ROOT), "_pbc_asset_backup")
PY_SNAP_DIR  = os.path.join(BACKUP_DIR, "_py_snapshot")

# 背景圖資料夾 → 轉 JPEG（不需要透明度，檔案較小）
# 其他圖 → 轉 PNG（保留透明度）
JPEG_DIRS = {os.path.join(ASSET_DIR, "picture", "background")}

# ── 0. 備份原始檔案（轉換前保留副本，供 restore_assets.py 還原）────
print("── 備份原始檔案至 _asset_backup/ ──────────────────────")
os.makedirs(PY_SNAP_DIR, exist_ok=True)

backup_count = 0
for dirpath, _, filenames in os.walk(ASSET_DIR):
    for fn in filenames:
        if fn.lower().endswith((".mp3", ".wav", ".webp")):
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, PROJECT_ROOT)
            dst = os.path.join(BACKUP_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            backup_count += 1

# 備份所有 .py 程式碼（供還原時恢復副檔名參照）
for fn in os.listdir(PROJECT_ROOT):
    if fn.endswith(".py"):
        shutil.copy2(os.path.join(PROJECT_ROOT, fn),
                     os.path.join(PY_SNAP_DIR, fn))

print(f"  已備份 {backup_count} 個資產檔案 + Python 程式碼 → _asset_backup/")
print(f"  （還原方法：執行 python restore_assets.py）\n")

# ── 1. 收集需要轉換的檔案 ────────────────────────────────────────
audio_files = []   # MP3 + WAV → OGG
webp_files  = []   # WebP → PNG / JPEG

for dirpath, _, filenames in os.walk(ASSET_DIR):
    for fn in filenames:
        full = os.path.join(dirpath, fn)
        if fn.lower().endswith((".mp3", ".wav")):
            audio_files.append(full)
        elif fn.lower().endswith(".webp"):
            webp_files.append(full)

print(f"找到 {len(audio_files)} 個音訊（MP3/WAV）、{len(webp_files)} 個 WebP，開始轉換…\n")

# ── 2. 轉換函式 ──────────────────────────────────────────────────
def run_ffmpeg(args: list) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error"] + args,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [錯誤] {result.stderr.strip()}")
        return False
    return True

errors = []

# ── MP3 → OGG ──────────────────────────────────────────────────
print("── MP3 / WAV → OGG ─────────────────────────────────────")
for src in audio_files:
    dst = src[: src.lower().rfind(".")] + ".ogg"
    rel = os.path.relpath(src, PROJECT_ROOT)
    print(f"  {rel}")
    if run_ffmpeg(["-i", src, "-c:a", "libvorbis", "-q:a", "5", dst]):
        os.remove(src)
        print(f"    OK")
    else:
        errors.append(rel)

# ── WebP → PNG / JPEG ──────────────────────────────────────────
print("\n── WebP → PNG / JPEG ───────────────────────────────────")
for src in webp_files:
    rel = os.path.relpath(src, PROJECT_ROOT)
    dirpath = os.path.dirname(src)

    if dirpath in JPEG_DIRS:
        # 背景圖 → JPEG
        dst = src[:-5] + ".jpg"
        fmt_label = "JPEG"
        extra_args = ["-q:v", "90"]
    else:
        # 立繪、icon 等 → PNG（保留透明度）
        dst = src[:-5] + ".png"
        fmt_label = "PNG"
        extra_args = []

    print(f"  {rel}  →  {fmt_label}")
    if run_ffmpeg(["-i", src] + extra_args + [dst]):
        os.remove(src)
        print(f"    OK")
    else:
        errors.append(rel)

# ── 3. 更新 .py 程式碼裡的副檔名參照 ────────────────────────────
print("\n── 更新 Python 程式碼參照 ──────────────────────────────")

# 背景圖 .png → .jpg，其他 .png → .png
# 策略：先找出各背景檔名，再做精確替換
bg_dir = os.path.join(ASSET_DIR, "picture", "background")
bg_filenames = set()
for fn in os.listdir(bg_dir) if os.path.isdir(bg_dir) else []:
    if fn.lower().endswith(".jpg"):
        bg_filenames.add(fn[:-4])  # 去掉 .jpg，存檔名本體

py_files = []
for dirpath, _, filenames in os.walk(PROJECT_ROOT):
    parts = dirpath.split(os.sep)
    # 跳過 build/ 和 _asset_backup/（備份資料夾不修改）
    if "build" in parts or "_asset_backup" in parts:
        continue
    for fn in filenames:
        if fn.endswith(".py"):
            py_files.append(os.path.join(dirpath, fn))

total_changes = 0
for pyf in py_files:
    with open(pyf, "r", encoding="utf-8") as f:
        content = f.read()

    updated = content

    # MP3 → OGG
    updated = updated.replace(".ogg", ".ogg")

    # WebP → PNG 或 JPEG（逐個背景檔名精確替換）
    for basename in bg_filenames:
        updated = updated.replace(f"{basename}.png", f"{basename}.jpg")

    # 剩餘 .png 全部 → .png（立繪、icon 等）
    updated = updated.replace(".png", ".png")

    if updated != content:
        with open(pyf, "w", encoding="utf-8") as f:
            f.write(updated)
        n = (content.count(".ogg") + content.count(".png"))
        total_changes += n
        print(f"  {os.path.relpath(pyf, PROJECT_ROOT)}（{n} 處）")

print(f"\n共替換 {total_changes} 處參照。")

# ── 4. 結果摘要 ──────────────────────────────────────────────────
print("\n" + "="*55)
if errors:
    print(f"[WARNING] 以下 {len(errors)} 個檔案轉換失敗：")
    for e in errors:
        print(f"   - {e}")
else:
    print("[OK] 全部轉換完成，無錯誤！")
print("="*55)
print("\n完成後重新 build：")
print("  python -X utf8 -m pygbag main.py")
print("（可以移除 --disable-sound-format-error 了）")
