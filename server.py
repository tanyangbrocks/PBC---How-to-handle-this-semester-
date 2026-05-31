#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — 乾淨靜態伺服器，取代 pygbag dev server
設定正確 COOP/COEP header，不含 dev server 額外開銷

使用方式：
  python server.py          # 預設 port 8000
  python server.py 8080     # 自訂 port

前置條件：
  先執行 python build.py（產生 build/web/ 並套用 patch）
"""
import sys
import os
import http.server
import socketserver

ROOT      = os.path.dirname(os.path.abspath(__file__))
SERVE_DIR = os.path.join(ROOT, "build", "web")
DEFAULT_PORT = 8000

# 需要明確指定的 MIME type（瀏覽器對 wasm/whl 要求嚴格）
_MIME = {
    ".wasm"  : "application/wasm",
    ".js"    : "application/javascript",
    ".mjs"   : "application/javascript",
    ".whl"   : "application/zip",
    ".zip"   : "application/zip",
    ".data"  : "application/octet-stream",
    ".ogg"   : "audio/ogg",
    ".mp3"   : "audio/mpeg",
    ".webm"  : "video/webm",
    ".mp4"   : "video/mp4",
    ".ttf"   : "font/ttf",
    ".ttc"   : "font/ttc",
    ".png"   : "image/png",
    ".jpg"   : "image/jpeg",
    ".webp"  : "image/webp",
}


class WASMHandler(http.server.SimpleHTTPRequestHandler):
    """
    靜態檔案處理器：
    - 每個回應加上 COOP / COEP header（WASM SharedArrayBuffer 必要條件）
    - 正確的 MIME type（避免瀏覽器拒絕載入 .wasm / .whl）
    - 只印出非 200/304 的 log，減少雜訊
    """

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy",   "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def guess_type(self, path):
        _, ext = os.path.splitext(str(path))
        return _MIME.get(ext.lower(), super().guess_type(path))

    def log_message(self, fmt, *args):
        # 過濾 200/304，只顯示錯誤（4xx/5xx）
        if args and len(args) >= 2 and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)


def _check_build():
    """確認 build/web/ 完整且已套用 patch，否則提示並退出。"""
    ok = True

    if not os.path.isdir(SERVE_DIR):
        print("[server] ❌  build/web/ 不存在，請先執行：python build.py")
        ok = False

    index = os.path.join(SERVE_DIR, "index.html")
    if ok and not os.path.isfile(index):
        print("[server] ❌  build/web/index.html 不存在，請先執行：python build.py")
        ok = False

    if ok:
        wheel_dir = os.path.join(SERVE_DIR, "cdn", "cp312")
        wheels = (
            [f for f in os.listdir(wheel_dir) if f.endswith(".whl")]
            if os.path.isdir(wheel_dir) else []
        )
        if not wheels:
            print(f"[server] ❌  pygame_ce wheel 不存在（{wheel_dir}），請先執行：python build.py")
            ok = False
        else:
            print(f"[server] ✅  wheel  : {wheels[0]}")

    if ok:
        with open(index, "r", encoding="utf-8", errors="replace") as _f:
            _html = _f.read()
        if "AudioWorkletProcessor" not in _html:
            print("[server] ❌  index.html 尚未套用 patch，請執行：python patch_index.py")
            ok = False
        else:
            print("[server] ✅  patch   : AudioWorklet 已注入")

    if not ok:
        sys.exit(1)

    print(f"[server] ✅  serve   : {SERVE_DIR}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    _check_build()

    os.chdir(SERVE_DIR)

    # allow_reuse_address 避免 "Address already in use" 重啟問題
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), WASMHandler) as httpd:
        print(f"[server] 🚀  http://localhost:{port}")
        print("[server]     Ctrl+C 停止\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[server] 停止。")


if __name__ == "__main__":
    main()
