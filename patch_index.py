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
    // 前景重新取得焦點時強制 resume（確保 ScriptProcessorNode 重新同步）
    document.addEventListener('focus', function() {
        var ctx = getAudioCtx();
        if (ctx && ctx.state === 'suspended') ctx.resume();
    });
    window.addEventListener('focus', function() {
        var ctx = getAudioCtx();
        if (ctx && ctx.state === 'suspended') ctx.resume();
    });
})();
</script>
</body>"""

html = html.replace("</body>", AUDIO_FIX_JS, 1)
print("[patch_index] ✓ Page Visibility 音訊修復注入成功")

# ── 修復 pygbag template bug：cdn 結尾 / + 路徑開頭 / = 雙斜線 ──────────
# CDN 上沒有 browserfs，改用 jsdelivr（穩定，不會 404）
import re as _re
html = _re.sub(
    r'https://pygame-web\.github\.io/cdn/[^"\']*//browserfs\.min\.js',
    "https://cdn.jsdelivr.net/npm/browserfs@1.4.3/dist/browserfs.min.js",
    html,
)
html = html.replace(
    "https://pygame-web.github.io/cdn/0.9.3/browserfs.min.js",
    "https://cdn.jsdelivr.net/npm/browserfs@1.4.3/dist/browserfs.min.js",
)
print("[patch_index] ✓ browserfs URL 修復（pygame-web CDN 404 → jsdelivr）")

# ── 注入中文 IME overlay（FS bridge 方案，不用 eval polling）────────────
# Python 呼叫 __cc_show() 一次（await 前），JS 按鈕觸發時直接寫 /tmp/__cc_result.txt
# Python polling 只用 open() 讀檔，完全不在 await 後呼叫任何 JS，避免死鎖
IME_OVERLAY = """
<div id="__cc_ov" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  background:rgba(0,0,0,0.52);z-index:2147483647;align-items:center;justify-content:center;">
  <div style="background:#fff9f0;border-radius:16px;padding:30px 36px;min-width:340px;
    text-align:center;font-family:sans-serif;box-shadow:0 6px 28px rgba(0,0,0,.35);
    border:2px solid #e8c898;">
    <p id="__cc_prm" style="font-size:17px;margin:0 0 8px;color:#4a3020;font-weight:bold;"></p>
    <p style="font-size:12px;margin:0 0 10px;color:#a08060;display:none;"></p>
    <input type="text" id="__cc_inp" lang="zh-TW" autocomplete="off" spellcheck="false"
      style="font-size:18px;width:220px;padding:8px 12px;border:2px solid #d0a870;
      border-radius:8px;background:#fffdf6;color:#3a2010;outline:none;
      font-family:sans-serif;letter-spacing:2px;">
    <div style="margin-top:16px;">
      <button onclick="__cc_submit()" style="padding:8px 30px;font-size:15px;
        background:#FF9460;color:#fff;border:none;border-radius:8px;
        cursor:pointer;font-weight:bold;">確認</button>
    </div>
  </div>
</div>
<script>
// 全螢幕狀態橋接：fullscreenchange → /tmp/__fs_state.txt（Python 每幀讀取）
// 純 JS 方案：user gesture 必須在 JS 事件 handler 內同步呼叫 requestFullscreen，
// 無法透過 Python window.eval() 觸發（已超出 user gesture 時間窗）
(function() {
  var BTN_X = 1234, BTN_Y = 674, BTN_W = 40, BTN_H = 40; // WIN_W=1280, WIN_H=720

  function writeState(s) {
    try { Module.FS.writeFile('/tmp/__fs_state.txt', s); } catch(e) {}
  }

  function fsToggle() {
    var c = document.getElementById('canvas');
    if (!c) return;
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      var req = c.requestFullscreen || c.webkitRequestFullscreen;
      if (req) req.call(c).catch(function(e){ console.warn('[fs] enter failed:', e); });
    } else {
      var ex = document.exitFullscreen || document.webkitExitFullscreen;
      if (ex) ex.call(document);
    }
  }

  function handleCanvasClick(e) {
    if (document.fullscreenElement || document.webkitFullscreenElement) return;
    var c = e.currentTarget;
    var rect = c.getBoundingClientRect();
    var sx = (c.width  || 1280) / (rect.width  || 1);
    var sy = (c.height || 720)  / (rect.height || 1);
    var lx = (e.clientX - rect.left) * sx;
    var ly = (e.clientY - rect.top)  * sy;
    console.log('[fs] click lx=' + Math.round(lx) + ' ly=' + Math.round(ly)
      + ' need x:' + BTN_X + '-' + (BTN_X+BTN_W) + ' y:' + BTN_Y + '-' + (BTN_Y+BTN_H)
      + ' cw=' + c.width + ' cssW=' + Math.round(rect.width));
    if (lx >= BTN_X && lx <= BTN_X + BTN_W && ly >= BTN_Y && ly <= BTN_Y + BTN_H) {
      console.log('[fs] button HIT → toggling fullscreen');
      fsToggle();
    }
  }

  document.addEventListener('fullscreenchange', function() {
    writeState((document.fullscreenElement || document.webkitFullscreenElement) ? '1' : '0');
  });
  document.addEventListener('webkitfullscreenchange', function() {
    writeState((document.fullscreenElement || document.webkitFullscreenElement) ? '1' : '0');
  });

  // canvas 可能在 DOMContentLoaded 後才建立，用 MutationObserver 等待
  function attachClickListener() {
    var c = document.getElementById('canvas');
    if (c) { c.addEventListener('click', handleCanvasClick); return; }
    var obs = new MutationObserver(function() {
      var c2 = document.getElementById('canvas');
      if (c2) { obs.disconnect(); c2.addEventListener('click', handleCanvasClick); }
    });
    obs.observe(document.body || document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachClickListener);
  } else {
    attachClickListener();
  }
})();

function __cc_show(prompt) {
  var ov  = document.getElementById('__cc_ov');
  var inp = document.getElementById('__cc_inp');
  document.getElementById('__cc_prm').textContent = prompt;
  inp.value = '';
  ov.style.display = 'flex';
  ov.style.zIndex   = '2147483647';  // INT_MAX：確保蓋過 canvas
  var cv = document.getElementById('canvas');
  if (cv) {
    cv._oldPe  = cv.style.pointerEvents;
    cv._oldZ   = cv.style.zIndex;
    cv._oldTab = cv.getAttribute('tabindex');
    cv.style.pointerEvents = 'none';
    cv.style.zIndex = '1';        // 強制 canvas 沉底（視覺層）
    cv.setAttribute('tabindex', '-1');  // 移出 tab 焦點鏈（阻止 SDL2 搶鍵盤）
    // 阻截 canvas 的鍵盤事件（IME composition 時 SDL2 不要搶走）
    cv._imeKeyBlock = function(e){ e.stopPropagation(); };
    cv.addEventListener('keydown',  cv._imeKeyBlock, true);
    cv.addEventListener('keypress', cv._imeKeyBlock, true);
    cv.addEventListener('keyup',    cv._imeKeyBlock, true);
    cv.blur();  // 強制 canvas 失焦
  }
  // 延遲 focus：確保 canvas blur 生效後再聚焦 input
  setTimeout(function(){
    inp.focus();
    inp.click();   // 在部分瀏覽器觸發 IME 啟動
    inp.select();
  }, 120);
}
function __cc_submit() {
  var val = (document.getElementById('__cc_inp').value || '').trim();
  var ov  = document.getElementById('__cc_ov');
  ov.style.display = 'none';
  var cv = document.getElementById('canvas');
  if (cv) {
    cv.style.pointerEvents = cv._oldPe || '';
    cv.style.zIndex = cv._oldZ || '';
    // 移除 IME 期間的鍵盤攔截
    if (cv._imeKeyBlock) {
      cv.removeEventListener('keydown',  cv._imeKeyBlock, true);
      cv.removeEventListener('keypress', cv._imeKeyBlock, true);
      cv.removeEventListener('keyup',    cv._imeKeyBlock, true);
      delete cv._imeKeyBlock;
    }
    // 還原 tabindex，讓 SDL2 重新接管鍵盤
    if (cv._oldTab !== null && cv._oldTab !== undefined) {
      cv.setAttribute('tabindex', cv._oldTab);
    } else {
      cv.removeAttribute('tabindex');
    }
    cv.focus();
  }
  try {
    // emscripten FS bridge：直接寫入 WASM 虛擬檔案系統，Python 用 open() 讀取
    Module.FS.writeFile('/tmp/__cc_result.txt', val);
  } catch(e) {
    // fallback：寫到 window property（Python 不需要在 await 後讀，只作備用）
    window.__cc_result_fb = val;
    console.warn('[cc_ime] FS.writeFile failed, using fallback:', e);
  }
}
document.addEventListener('DOMContentLoaded', function(){
  var inp = document.getElementById('__cc_inp');
  if (inp) inp.addEventListener('keydown', function(e){
    if (e.key === 'Enter' && !e.isComposing) __cc_submit();
  });
});
</script>
</body>"""

html = html.replace("</body>", IME_OVERLAY, 1)
print("[patch_index] ✓ 中文 IME overlay 注入成功（FS bridge 方案）")

with open(INDEX_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[patch_index] 完成！已更新 {INDEX_PATH}")
print("[patch_index] 開啟 http://localhost:8000 即可看到新載入畫面。")
