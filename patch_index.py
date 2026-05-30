"""
patch_index.py
==============
在 pygbag build 完成後執行，替換 build/web/index.html 的載入畫面。
把原本的灰底 + 一般進度條，改成符合遊戲暖色主題的精美載入畫面。

使用方式（每次 build 後執行）：
    python patch_index.py
"""

import os
import re

INDEX_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "build", "web", "index.html"
)

if not os.path.exists(INDEX_PATH):
    print(f"[patch_index] 找不到 {INDEX_PATH}，請先執行 pygbag build。")
    raise SystemExit(1)

with open(INDEX_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ── 1. 替換背景色（powderblue → 遊戲暖色）────────────────────────
html = html.replace(
    "background-color:powderblue;",
    "background:linear-gradient(160deg,#fff5e0 0%,#ffe4c0 60%,#ffd4a8 100%);"
)

# ── 2. 替換整個 transfer div（含進度條）─────────────────────────
OLD_TRANSFER = re.compile(
    r'<div id="transfer"[^>]*>.*?</div>\s*</div>',
    re.DOTALL
)

NEW_TRANSFER = """<div id="transfer" align="center" style="
    position:fixed;top:0;left:0;width:100%;height:100%;
    z-index:9998;">
  <!-- 內層 wrapper 負責排版（transfer 本身不設 display，讓 hidden 屬性能正常隱藏） -->
  <div style="width:100%;height:100%;
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:linear-gradient(160deg,#fff5e0 0%,#ffe4c0 60%,#ffd4a8 100%);
    font-family:sans-serif;">
  <!-- 遊戲標題 -->
  <div style="font-size:32px;font-weight:bold;color:#5d4037;
              margin-bottom:8px;letter-spacing:4px;
              text-shadow:2px 2px 4px rgba(0,0,0,0.15);">
    如何渡過這學期？
  </div>
  <div style="font-size:13px;color:#a08060;margin-bottom:32px;letter-spacing:2px;">
    How to Survive This Semester
  </div>
  <!-- 進度條外框 -->
  <div style="width:320px;height:16px;
              background:#f0dcc0;border-radius:8px;
              box-shadow:inset 0 2px 4px rgba(0,0,0,0.12);
              overflow:hidden;">
    <div id="pbc_bar" style="height:100%;width:0%;
         background:linear-gradient(90deg,#ff9460,#ffc080);
         border-radius:8px;
         transition:width 0.4s ease;"></div>
  </div>
  <!-- 進度數字 -->
  <div id="pbc_pct" style="font-size:13px;color:#a08060;
                            margin-top:10px;">0%</div>
  <!-- 狀態訊息（pygbag infobox 的替代位置） -->
  <div id="status" style="font-size:12px;color:#c09070;
                            margin-top:6px;">正在載入中...</div>
  <progress id="progress" value="0" max="100"
            style="display:none;"></progress>
  </div><!-- end inner wrapper -->
</div><!-- end #transfer -->

<script>
// 監聽隱藏 progress 元素的 value 變化，同步到自訂進度條
(function(){
  var bar  = document.getElementById('pbc_bar');
  var pct  = document.getElementById('pbc_pct');
  var prog = document.getElementById('progress');
  if(!prog||!bar) return;
  var obs = new MutationObserver(function(){
    var v = parseInt(prog.value)||0;
    var m = parseInt(prog.max)||100;
    var p = m>0 ? Math.round(v/m*100) : 0;
    bar.style.width = p+'%';
    pct.textContent = p+'%';
  });
  obs.observe(prog, {attributes:true, attributeFilter:['value']});
})();
</script>"""

if OLD_TRANSFER.search(html):
    html = OLD_TRANSFER.sub(NEW_TRANSFER, html, count=1)
    print("[patch_index] ✓ transfer div 替換成功")
else:
    print("[patch_index] 警告：找不到 transfer div，可能 pygbag 版本有變動")

# ── 3. 替換 infobox 樣式（綠底藍字 → 遊戲風格）────────────────────
html = html.replace(
    """    #infobox {
            position: fixed; /* center relative to viewport */
            background: green;
            color: blue;
            font-weight: bold;
            padding: 12px 24px;
 /*           display: none; */
            z-index: 999999;
        }""",
    """    #infobox {
            position: fixed;
            background: rgba(255,244,224,0.95);
            color: #5d4037;
            font-weight: bold;
            font-size: 13px;
            padding: 10px 20px;
            border-radius: 8px;
            border: 1px solid #e0c090;
            box-shadow: 0 2px 12px rgba(0,0,0,0.15);
            z-index: 999999;
        }"""
)
print("[patch_index] ✓ infobox 樣式替換成功")

# ── 4. 注入 Page Visibility API 音訊修復 ─────────────────────────
# 根本原因：切 tab 時瀏覽器節流主線程，ScriptProcessorNode 的 buffer 積壓；
# 切回來時一次爆發 → 爆音。解法：隱藏時 suspend AudioContext，顯示時 resume。
AUDIO_FIX_JS = """
<script>
// Page Visibility API — 防止 tab 切換時 ScriptProcessorNode buffer 積壓爆音
(function(){
    function getAudioCtx() {
        try { if (window.MM && window.MM.audioContext) return window.MM.audioContext; } catch(e){}
        try { if (typeof Module !== 'undefined' && Module.SDL2 && Module.SDL2.audioContext) return Module.SDL2.audioContext; } catch(e){}
        return null;
    }
    document.addEventListener('visibilitychange', function() {
        var ctx = getAudioCtx();
        if (!ctx) return;
        if (document.visibilityState === 'hidden') {
            ctx.suspend();
        } else {
            ctx.resume();
        }
    });
})();
</script>
</body>"""

html = html.replace("</body>", AUDIO_FIX_JS, 1)
print("[patch_index] ✓ Page Visibility 音訊修復注入成功")

with open(INDEX_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[patch_index] 完成！已更新 {INDEX_PATH}")
print("[patch_index] 開啟 http://localhost:8000 即可看到新載入畫面。")
