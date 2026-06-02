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

# ── 4. 注入 AudioWorklet proxy（大緩衝版）+ Page Visibility ──────────
# 問題根源：
#   ScriptProcessorNode bufSz=512 = 11.6ms；遊戲 rAF 幀時間常達 20-40ms。
#   主執行緒忙時 onaudioprocess 被延遲，直接輸出就失真（buffer underrun）。
#
# 修法（改良版 AudioWorklet proxy）：
#   1. ScriptProcessorNode 照常接收 SDL2 音訊（每次 512 samples / 11.6ms）
#   2. 每個 packet 傳給 AudioWorklet（獨立執行緒，不受主執行緒影響）
#   3. Worklet 預緩衝 MIN_PKTS=8 個 packet（= 8×512 samples = 93ms）再開始播放
#      → 即使主執行緒 block 了 80ms，Worklet 的緩衝也夠用
#   4. Underrun 時輸出靜音（而非失真），Worklet 不重置 ready 狀態
#      → 可能出現 1-2 個靜音 quantum（2.9ms）但無持續失真
AUDIO_FIX_JS = """
<script>
// ── AudioWorklet proxy（穩定版）+ Page Visibility ─────────────────────
// 架構說明：
//   ScriptProcessorNode 必須「留在」音訊圖中（連接 destination），
//   onaudioprocess 才會持續觸發（Web Audio spec 規定）。
//   因此我們不 disconnect，改為在 onaudioprocess 中把 outputBuffer 填 0，
//   讓 ScriptProcessorNode 輸出靜音；Worklet（獨立執行緒）輸出真實音訊。
//   兩者在 destination 混合 = 靜音 + 音訊 = 正常播放。
//
// pre-buffer：1 packet（11.6ms @44100Hz）
//   - 最小可用緩衝，降低 SFX 延遲感（人耳感知閾值 ~20ms）
//   - underrun 時輸出靜音 quantum（2.9ms），不重置 ready，等新 packet 自動恢復
//   - 若未來出現明顯破音，可提高回 2（23ms）
(function(){
'use strict';

var WORKLET_SRC = [
  'class SDL2Proxy extends AudioWorkletProcessor {',
  '  constructor(){',
  '    super();',
  '    this._q=[];',
  '    this._pos=0;',
  '    this._ready=false;',
  '    this._MIN=1;', // pre-buffer: 1×512=512 samples = 11.6ms @44100Hz
  '    this.port.onmessage=function(e){this._q.push(e.data);}.bind(this);',
  '  }',
  '  process(inp,out){',
  '    var ch=out[0]; if(!ch||!ch[0]) return true;',
  '    if(!this._ready){',
  '      if(this._q.length>=this._MIN) this._ready=true;',
  '      else{ for(var c=0;c<ch.length;c++) ch[c].fill(0); return true; }',
  '    }',
  '    var n=ch[0].length; var done=0;',
  '    while(done<n){',
  '      if(!this._q.length){',
  '        for(var c=0;c<ch.length;c++) ch[c].fill(0,done);',
  '        break;',
  '      }',
  '      var pkt=this._q[0];',
  '      var avail=pkt[0].length-this._pos;',
  '      var take=Math.min(avail,n-done);',
  '      for(var c=0;c<ch.length&&c<pkt.length;c++){',
  '        ch[c].set(pkt[c].subarray(this._pos,this._pos+take),done);',
  '      }',
  '      done+=take; this._pos+=take;',
  '      if(this._pos>=pkt[0].length){ this._q.shift(); this._pos=0; }',
  '    }',
  '    return true;',
  '  }',
  '}',
  'registerProcessor("sdl2-proxy",SDL2Proxy);'
].join('\\n');

var _wNode=null, _wReady=false;

var _origCSP = AudioContext.prototype.createScriptProcessor;
AudioContext.prototype.createScriptProcessor = function(bufSz, inCh, outCh) {
  var real = _origCSP.call(this, bufSz, inCh, outCh);
  var ctx  = this;
  window.__sdl2AudioCtx = ctx;
  outCh = outCh || 2;

  // 非同步建立 AudioWorklet
  var blob = new Blob([WORKLET_SRC], {type:'application/javascript'});
  var url  = URL.createObjectURL(blob);
  ctx.audioWorklet.addModule(url).then(function(){
    URL.revokeObjectURL(url);
    _wNode = new AudioWorkletNode(ctx, 'sdl2-proxy', {
      numberOfInputs:0, numberOfOutputs:1,
      outputChannelCount:[outCh]
    });
    _wNode.connect(ctx.destination);
    _wReady = true;
    console.log('[audio-proxy] AudioWorklet ready (1-pkt pre-buffer, copy mode)');
  }).catch(function(e){
    console.warn('[audio-proxy] AudioWorklet failed, using ScriptProcessorNode fallback:', e.message);
    URL.revokeObjectURL(url);
  });

  var _sdl2fn = null;

  return new Proxy(real, {
    set: function(t, p, v) {
      if (p === 'onaudioprocess') {
        _sdl2fn = v;
        t.onaudioprocess = function(evt) {
          if (_sdl2fn) _sdl2fn.call(t, evt);
          if (_wReady && _wNode) {
            var ob  = evt.outputBuffer;
            var nCh = ob.numberOfChannels;
            // Copy（不 transfer）：確保 Worklet 端收到完整資料
            // ScriptProcessorNode 不 disconnect，留在音訊圖中讓 onaudioprocess 持續觸發
            var pkt = [];
            for (var c = 0; c < nCh; c++) {
              pkt.push(ob.getChannelData(c).slice(0));
            }
            _wNode.port.postMessage(pkt);
            // outputBuffer 填 0：ScriptProcessorNode 輸出靜音，避免直通雙重出聲
            for (var c2 = 0; c2 < nCh; c2++) {
              ob.getChannelData(c2).fill(0);
            }
          }
        };
        return true;
      }
      return Reflect.set(t, p, v);
    },
    get: function(t, p) {
      var val = Reflect.get(t, p);
      return typeof val === 'function' ? val.bind(t) : val;
    }
  });
};

// Page Visibility + 首次互動：resume AudioContext
// 瀏覽器 autoplay 政策：AudioContext 在使用者互動前維持 suspended 狀態，
// 必須在 click/pointerdown 時明確呼叫 resume()，否則整場無音樂。
function getAudioCtx() {
  // 優先使用攔截 createScriptProcessor 時存下的參照（最可靠）
  if (window.__sdl2AudioCtx) return window.__sdl2AudioCtx;
  // 備援：其他框架的慣用路徑
  try { if (window.MM && window.MM.audioContext) return window.MM.audioContext; } catch(e){}
  try { if (typeof Module !== 'undefined' && Module.SDL2 && Module.SDL2.audioContext) return Module.SDL2.audioContext; } catch(e){}
  return null;
}
function _tryResumeAudio() {
  var ctx = getAudioCtx();
  if (ctx && ctx.state === 'suspended') {
    ctx.resume().catch(function(e) {
      console.warn('[audio] ctx.resume() failed:', e);
    });
  }
}
// 首次點擊 / 觸控 → resume（解決開場無音樂問題）
// 重要：用 capture:true — SDL2/Emscripten 在 canvas 上呼叫 stopPropagation()，
// bubble phase 的 document 層監聽器收不到事件；
// capture phase 在 SDL2 的 handler 之前觸發，不受 stopPropagation 影響。
// document capture 已能捕捉所有元素（含 canvas）的事件，不需再對 canvas 單獨掛載。
document.addEventListener('click',       _tryResumeAudio, {capture: true, passive: true});
document.addEventListener('pointerdown', _tryResumeAudio, {capture: true, passive: true});
document.addEventListener('keydown',     _tryResumeAudio, {capture: true, passive: true});
// 切回分頁 / 重新取得焦點 → resume（解決切換分頁後音樂消失問題）
document.addEventListener('visibilitychange', function() {
  if (document.visibilityState === 'visible') _tryResumeAudio();
});
document.addEventListener('focus', _tryResumeAudio);
window.addEventListener('focus',   _tryResumeAudio);

})();
</script>
</body>"""

# 防重複注入：若已含 sdl2-proxy 識別碼，代表本次 patch 已套用過，跳過
if 'sdl2-proxy' in html:
    print("[patch_index] ⚠️  音訊修復已存在於 index.html，跳過注入（需先 build.py 取得乾淨版本）")
else:
    html = html.replace("</body>", AUDIO_FIX_JS, 1)
    print("[patch_index] ✓ AudioWorklet proxy + Page Visibility 音訊修復注入成功")

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
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      // 以 document.documentElement（html 根元素）為全螢幕目標。
      // 原因：以 <canvas> 為目標時，canvas 不渲染 HTML 子元素，
      // 導致 IME overlay div 移入 canvas 後仍不可見（canvas spec 規定）。
      // 以 documentElement 為目標時，body 內所有元素（含 overlay）自動可見，
      // 無需移動 DOM；視覺效果與 canvas 全螢幕相同（canvas 已 100vw/100vh）。
      var root = document.documentElement;
      var req  = root.requestFullscreen || root.webkitRequestFullscreen;
      if (req) req.call(root).catch(function(e){ console.warn('[fs] enter failed:', e); });
    } else {
      var ex = document.exitFullscreen || document.webkitExitFullscreen;
      if (ex) ex.call(document);
    }
  }

  function handleCanvasClick(e) {
    if (document.fullscreenElement || document.webkitFullscreenElement) return;
    var c = e.currentTarget;
    var rect = c.getBoundingClientRect();
    // canvas.width 可能因 pygbag 縮放而不等於遊戲解析度（例如 960 而非 1280）
    // BTN_X/BTN_Y 是遊戲邏輯座標（1280×720），必須用固定遊戲解析度換算
    var sx = 1280 / (rect.width  || 1);
    var sy = 720  / (rect.height || 1);
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

  function _syncOvForFs() {
    // fsToggle() 改為以 document.documentElement 為全螢幕目標。
    // documentElement 包含 body 包含 overlay，overlay 永遠在全螢幕元素內，
    // 無需移動 DOM。此函式保留（供 fullscreenchange 事件使用）但已無實際操作。
  }

  document.addEventListener('fullscreenchange', function() {
    writeState((document.fullscreenElement || document.webkitFullscreenElement) ? '1' : '0');
    _syncOvForFs();
  });
  document.addEventListener('webkitfullscreenchange', function() {
    writeState((document.fullscreenElement || document.webkitFullscreenElement) ? '1' : '0');
    _syncOvForFs();
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
    // 注意：不呼叫 cv.blur()。
    // cv.blur() 會讓 pygbag 偵測到 canvas 失去焦點並暫停渲染主迴圈，
    // 導致遊戲凍結。改由 inp.focus() 自然搶走焦點，避免此問題。
  }
  // 延遲 focus：讓 canvas 先完成當前幀再移交焦點，避免搶佔時序問題
  setTimeout(function(){
    inp.focus();
    inp.click();   // 在部分瀏覽器觸發 IME 啟動
    inp.select();
  }, 50);
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
    // 確保 /tmp/ 目錄存在（部分 BrowserFS 設定下不會自動建立）
    try { Module.FS.mkdir('/tmp'); } catch(e2) { /* 已存在時忽略 */ }
    Module.FS.writeFile('/tmp/__cc_result.txt', val);
    // 同時寫到 JS global，讓 Python fallback 路徑也能取得結果
    window.__cc_result_fb = val;
    console.log('[cc_ime] FS.writeFile OK, val=' + JSON.stringify(val));
  } catch(e) {
    // fallback：僅寫到 window property（Python fallback 路徑讀取）
    window.__cc_result_fb = val;
    console.warn('[cc_ime] FS.writeFile failed, fallback set. val='
                 + JSON.stringify(val) + ' err=' + e);
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

# ── 5. 注入 JS 全域崩潰攔截（WASM heap 耗盡 / RuntimeError）────────────
# Python try/except 在 WASM/heap 崩潰時根本無法執行。
# 在 JS 層用 window.onerror + unhandledrejection 攔截，
# 顯示可操作的重整畫面，避免玩家面對空白黑屏不知所措。
CRASH_HANDLER_JS = """
<script>
(function(){
  var _crashed = false;

  function _showCrash(reason) {
    if (_crashed) return;
    _crashed = true;
    console.error('[PBC crash]', reason);
    // 嘗試暫停音訊
    try {
      var ctx = (window.MM && window.MM.audioContext) ||
                (typeof Module !== 'undefined' && Module.SDL2 && Module.SDL2.audioContext);
      if (ctx) ctx.suspend();
    } catch(e) {}
    // 建立全螢幕錯誤覆蓋層
    var ov = document.createElement('div');
    ov.style.cssText =
      'position:fixed;top:0;left:0;width:100%;height:100%;z-index:2147483647;' +
      'background:rgba(20,10,5,0.93);display:flex;flex-direction:column;' +
      'align-items:center;justify-content:center;font-family:sans-serif;';
    var title = document.createElement('div');
    title.textContent = '遊戲發生錯誤';
    title.style.cssText = 'font-size:26px;font-weight:bold;color:#ffcc88;margin-bottom:12px;';
    var sub = document.createElement('div');
    sub.textContent = '請重新整理頁面繼續遊玩';
    sub.style.cssText = 'font-size:14px;color:#aa9070;margin-bottom:8px;';
    var detail = document.createElement('div');
    detail.textContent = String(reason).substring(0, 120);
    detail.style.cssText = 'font-size:11px;color:#666;margin-bottom:28px;max-width:480px;text-align:center;';
    var btn = document.createElement('button');
    btn.textContent = '重新整理';
    btn.style.cssText =
      'padding:12px 40px;font-size:16px;font-weight:bold;' +
      'background:#FF9460;color:#fff;border:none;border-radius:10px;cursor:pointer;';
    btn.onclick = function(){ location.reload(); };
    ov.appendChild(title);
    ov.appendChild(sub);
    ov.appendChild(detail);
    ov.appendChild(btn);
    document.body.appendChild(ov);
  }

  // JS 全域例外（含 WASM RuntimeError / abort / OOM）
  window.addEventListener('error', function(e) {
    var msg = (e.error && e.error.message) || e.message || 'Unknown error';
    // 過濾無害的資源載入錯誤（img/script 404 等）
    if (e.filename || e.lineno) {
      _showCrash(msg);
    }
  });

  // 未處理的 Promise rejection（emscripten abort() 有時走這條路）
  window.addEventListener('unhandledrejection', function(e) {
    var reason = (e.reason && e.reason.message) || String(e.reason) || 'Unhandled rejection';
    if (reason.indexOf('abort') !== -1 ||
        reason.indexOf('OOM')   !== -1 ||
        reason.indexOf('memory') !== -1 ||
        reason.indexOf('RuntimeError') !== -1) {
      _showCrash(reason);
    }
  });
})();
</script>
</body>"""

html = html.replace("</body>", CRASH_HANDLER_JS, 1)
print("[patch_index] ✓ JS 全域崩潰攔截注入成功（window.onerror + unhandledrejection）")

with open(INDEX_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[patch_index] 完成！已更新 {INDEX_PATH}")
print("[patch_index] 開啟 http://localhost:8000 即可看到新載入畫面。")
