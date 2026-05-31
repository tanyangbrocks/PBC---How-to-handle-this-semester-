# WASM 部署除錯記錄
## 遊戲：如何渡過這學期？ | pygbag 0.9.3 | 2025–2026

---

## 一、環境與架構說明

| 項目 | 值 |
|------|---|
| 打包工具 | pygbag 0.9.3 |
| Python | CPython 3.12 (WASM) |
| 遊戲解析度 | 1280 × 720 |
| canvas 實際寬度 | 960 px（DPR = 1.5，pygbag 自動縮放） |
| 音訊後端 | SDL2 → `ScriptProcessorNode`（主執行緒） |
| 文字輸入 | pygbag IME overlay (`__cc_ov` div) |

**WASM 執行模型**：Python/WASM 與 JavaScript 同跑在主執行緒。`asyncio.sleep(0)` 是唯一讓出主執行緒的方式（yield to browser event loop）。

---

## 二、已修復問題清單

### 2-1 道具店購買後遊戲凍結
- **根因**：`_cmd_q` 是 `collections.deque`，沒有 `.put()` 方法。`_apply_shop_purchase` 誤用 `_cmd_q.put(...)` → `AttributeError` → `run_ui` asyncio task crash → 遊戲凍結（Python 仍在跑，可見 `DISCARD: blur` log）
- **現象**：點購買後遊戲停止渲染，但 console 繼續有 focus/blur 事件
- **修法**：`_cmd_q.put(...)` → `_cmd_q.append(...)`（`ui_draw_base.py`）

### 2-2 全螢幕按鈕 X 座標計算錯誤
- **根因**：`handleCanvasClick` 用 `canvas.width / rect.width` 換算比例。DPR=1.5 時 `canvas.width = 960`，而遊戲邏輯座標是 1280。比例錯誤導致點擊位置偏移。
- **修法**：改為固定遊戲解析度換算：`sx = 1280 / rect.width`（`patch_index.py`）

### 2-3 切分頁後音訊靜音
- **根因**：錯誤地在 `visibilitychange:hidden` 時呼叫 `ctx.suspend()`，導致背景音消失
- **修法**：移除 `ctx.suspend()`，只在 visible 時 `ctx.resume()`（`patch_index.py`）

### 2-4 全螢幕時 IME overlay 消失
- **根因**：`__cc_ov` div 在 `<body>` 中。進入全螢幕後，瀏覽器只顯示 fullscreen element 及其子元素，`<body>` 中其他元素全隱藏
- **嘗試過的錯誤方向**：把 overlay 移入 `<canvas>`（fullscreen element）→ 仍然不可見。原因：HTML spec 規定 `<canvas>` 不渲染 HTML 子元素（子元素只是不支援 canvas 的瀏覽器用的 fallback content）
- **最終正確修法**：`fsToggle()` 改為對 `document.documentElement`（html 根元素）呼叫 `requestFullscreen()`。`documentElement` 包含整個 `<body>`，所有元素（含 overlay）自動在全螢幕範圍內，無需移動任何 DOM（`patch_index.py`）

### 2-5 WASM heap 耗盡（全面性 SRCALPHA 問題）
- **根因**：每幀建立大型 SRCALPHA Surface，Python GC 追不上 → heap 溢位 → 凍結
- **最嚴重的來源**（每幀分配量）：

| 位置 | 大小 | 頻率 |
|------|------|------|
| `SpritePlayer.get_surface()` 每幀 `transform.scale` | 3.68 MB | CC 背景影片每幀 |
| `_draw_action_panel` sh + card | 1.17 MB | 遊戲階段每幀 |
| `_side_panel_bg` sh + bg × 2 面板 | 1.46 MB | 遊戲階段每幀 |
| `_draw_cc_summary` sh + card_s | 2.84 MB | CC 總覽每幀 |
| `_draw_end` / `_draw_gameover` 過場 ov | 2.76 MB | 結局/GameOver 過場每幀 |
| `_draw_cc_title` comp 表面 | ~48 KB | CC 各步驟每幀 |
| `_draw_roll_call_note` 建立+旋轉 | ~30 KB | 遊戲每幀（有點名時）|
| hover glow / disabled dim 各按鈕 | 小 | 每幀（各 hover 狀態）|

- **修法模式**：
  1. `_get_sfx_surf(name)` — WIN_W×WIN_H SRCALPHA，首次建立、後續 fill 清空重用
  2. `_blit_ov(surf, r, g, b, a)` — 固定 alpha 全螢幕遮罩，按 (r,g,b,a) 快取
  3. `_get_popup_sh(w, h, alpha)` — 圓角陰影，按 (w,h,alpha) 快取
  4. `_ap_surf_cache` — `ui_draw_ap.py` 專用快取，按 key 儲存面板陰影/卡片
  5. `_get_fade_surf(r,g,b)` — 過場 fade，只快取填色，每幀 `set_alpha` 後重用
  6. `_cc_title_cache[(text, active_idx)]` — CC 標題按狀態快取
  7. `SpritePlayer` LRU-1 scaled cache — 相同幀 idx + 尺寸時直接回傳，不重建

### 2-6 音訊失真（前景 ScriptProcessorNode underrun）
- **根因**：SDL2 的 `ScriptProcessorNode.onaudioprocess` 跑在主執行緒。主執行緒忙於 WASM 渲染 + GC → callback 來不及填滿 buffer → underrun = 失真。
- **確認依據**：「遊戲凍結後音效反而正常了」→ 凍結時主執行緒空閒 → audio callback 正常填入
- **官方狀態**（參見[附錄 A](#附錄-a外部資料來源)）：pygbag issue #19 為已知問題；FAQ 建議改用外部 JS sound manager 或等待 SDL2 換成 OpenAL
- **修法（分層）**：
  1. **根本修**：AudioWorklet proxy（`patch_index.py`）——monkey-patch `AudioContext.createScriptProcessor`，用 Proxy 攔截 SDL2 的音訊節點，把資料 `postMessage` 給 AudioWorkletNode（獨立執行緒），主執行緒不再決定音訊輸出時機
  2. **輔助修**：移除所有 `[DBG] print()` 語句——每次 `print()` 都跨越 WASM→JS boundary，直接增加主執行緒負擔（pygbag FAQ 明確記載）
  3. **輔助修**：主迴圈 double yield（`asyncio.sleep(0)` × 2）——給瀏覽器更多機會執行任務
  4. **基礎修**：大量 SRCALPHA 快取——降低 GC 頻率，縮短每幀時間

### 2-6a AudioWorklet proxy 實作踩坑
- **AudioWorklet 送接 packet 大小不匹配**（第一版 bug）：  
  `ScriptProcessorNode` 每次 `onaudioprocess` 送出 4096 sample 的 packet；  
  `AudioWorkletProcessor.process()` 每次只有 128 個 sample 的 buffer。  
  初版直接 `ch[c].set(pkt[c])`，只複製前 128/4096 = **3.1%**，其餘 96.9% 丟棄 → 音樂「消失」。  
  **正確做法**：Worklet 內維護 `this._pos` cursor，跨多次 `process()` 呼叫連續消化完整 packet。

### 2-7 run_ui asyncio task 被例外 crash 後無法恢復
- **根因**：`while _cmd_q:` 中的 tag handler 若拋出例外，整個 `run_ui` coroutine 終止 → 遊戲永久凍結
- **修法**：用 `try/except Exception` 包住整個 cmd handler block，例外時 `print + traceback` 後繼續下一個 cmd

---

## 三、JS 注入架構（patch_index.py）

`patch_index.py` 在 `python build.py` 完成後對 `build/web/index.html` 注入以下 JavaScript：

| 功能 | 機制 |
|------|------|
| 全螢幕按鈕座標換算 | `canvas.click` listener，用固定遊戲解析度 1280×720 換算 |
| 全螢幕狀態橋接 | `fullscreenchange` → 寫 `/tmp/__fs_state.txt` → Python 每幀讀取 |
| 全螢幕目標 | `document.documentElement.requestFullscreen()`，使 body 內所有元素可見 |
| 中文 IME overlay | `__cc_show(prompt)`、`__cc_submit()` → FS bridge → `/tmp/__cc_result.txt` |
| AudioWorklet proxy | monkey-patch `createScriptProcessor`，把音訊路由到獨立 Worklet 執行緒 |
| Page Visibility resume | `visibilitychange` 時 `ctx.resume()`，防止 AudioContext 停留在 suspended 狀態 |
| 進度條美化 | 替換 `#transfer` div，暖色主題載入畫面 |
| browserfs URL 修正 | pygame-web CDN 404 → 改用 jsdelivr |

---

## 四、重要技術限制

### 4-1 全螢幕 requestFullscreen() 限制
- 瀏覽器要求 `requestFullscreen()` 必須在 **user gesture event handler** 內同步呼叫
- Python `window.eval()` 已超出時間窗 → 無效
- 解法：在 JS canvas `click` listener 內偵測點擊位置，Python 只需 `pass + continue`

### 4-2 canvas.width ≠ 遊戲解析度
- `canvas.width = 960`（DPR = 1.5 時）但遊戲邏輯是 1280
- JS 座標換算必須用 `1280 / rect.width`（CSS 像素），而非 `canvas.width / rect.width`

### 4-3 ScriptProcessorNode 已棄用
- 瀏覽器已顯示 deprecation warning
- pygbag 0.9.3 的 SDL2 仍使用 ScriptProcessorNode
- AudioWorklet proxy 是目前在不修改 pygbag 底層的情況下最有效的解法

### 4-4 WASM print() 效能
- 每次 `print()` 在 WASM 中需跨 WASM→JS boundary 呼叫 `console.log`
- 代價：1–5ms / 次，polling loop 中呼叫 = 持續消耗主執行緒
- 規則：WASM 中只保留錯誤 print，移除所有 debug print

### 4-5 asyncio.sleep(0) 語意
- Python WASM 中 `asyncio.sleep(0)` = `emscripten_yield` = 把控制交回 JS event loop
- 每幀末尾必須呼叫，否則 Python 會佔用主執行緒直到完成整個遊戲主迴圈
- 過多的 yield 不會造成效能問題，但每次 yield 的回復時間取決於 JS task queue 長度

---

## 五、每次部署流程

```bash
# 1. 打包
python build.py

# 2. 注入 JS 修復
python -X utf8 patch_index.py

# 3. 測試（必須用無痕視窗清除 IndexedDB 快取）
# 開 http://localhost:8000
```

**注意**：每次 build 後都必須重新跑 `patch_index.py`，否則 JS 修復不會生效。

---

## 六、Git commit 歷史（本輪修復）

| commit | 說明 |
|--------|------|
| `9aeef73` | 增大 WASM audio buffer 4096 修 ScriptProcessorNode 競爭失真 |
| `d886c80` | 全螢幕按鈕 X 座標修正（canvas.width ≠ 遊戲寬） |
| `af4bcc4` | 消除 per-frame SRCALPHA 分配 + 修 audio suspend |
| `5d31911` | 消除 WIN_W×WIN_H per-frame SRCALPHA（天氣/FX/popup 等）|
| `11b028c` | 道具店 crash（deque.put）+ 全螢幕 IME + audio buffer |
| `a19315d` | 全面 WASM heap 修復（SpritePlayer/AP panel/CC summary 等）+ _syncOvForFs 條件修正 |
| `74ec40b` | Double yield + cmd handler guard + fade surf cache + cc_title cache |
| `ab420cb` | **AudioWorklet proxy + 移除 debug print**（音訊根本修） |
| `b7e7489` | **Worklet cursor bug 修（音樂消失）+ fullscreen 改用 documentElement** |

---

## 七、已知剩餘問題

| 問題 | 狀態 | 說明 |
|------|------|------|
| 音訊失真 | ✅ 已修（AudioWorklet proxy + cursor fix） | Worklet 就緒前（~200ms）有短暫直通；Worklet 就緒後完全離開主執行緒 |
| 全螢幕 IME overlay | ✅ 已修（documentElement fullscreen） | 改用 html 根元素為全螢幕目標，overlay 自動可見 |
| CC 粒子 wisp 每幀小 Surface | ⚠️ 待優化 | ~30 個小 SRCALPHA/frame，影響較小但未快取 |
| `_render_mixed` 每幀建立 Surface | ⚠️ 待優化 | 拉霸機可見時，每個 tile 都建立小 Surface |
| `ui_draw.py`（死碼） | ℹ️ 無影響 | 原始未拆分的 4628 行巨型檔案，未被 `ui.py` import，不影響遊戲 |

---

## 附錄 A：外部資料來源

### pygbag issue #19 — "sound may have problems"
**連結**：https://github.com/pygame-web/pygbag/issues/19

**官方說明摘要**：
- 狀態：已知問題，尚未在 pygbag 層面根本修復
- 症狀：各瀏覽器均有不同程度的嘶嘶聲 / 失真，Brave / Edge 尤其明顯
- 官方根因：「SDL2 is hard realtime, so sometimes the game asks too much from average devices and is a bit late on frame. Because of this, sound effects are distorted.」（SDL2 是硬即時，裝置太忙時掉幀導致音效失真）
- 官方建議：
  1. 升級到 pygbag 0.1.5 以上（已解決部分問題）
  2. 用外部 JavaScript sound manager 取代 SDL2 音效
  3. 長期方向：「Possible other solution: replace sdl2_audio by openal, PR welcomed」
- 本專案的進展：我們透過 AudioWorklet proxy（見 2-6）在不修改 pygbag 底層的情況下從根本解決了主執行緒競爭問題

### pygbag code FAQ — "Pygbag code FAQ/Samples"
**連結**：https://pygame-web.github.io/wiki/pygbag-code/

**與音訊相關的官方注意事項**：
- **`print()` 效能警告**（官方明確記載）：「remove all debug `print()` statements from your code, as console output significantly reduces browser performance」——每個 `print()` 在 WASM 中都要跨越 WASM→JS boundary。本專案已全面移除所有 polling loop 中的 debug print。
- **音訊格式建議**：所有音訊檔案使用 **OGG 格式**，目標 16-bit、24 kHz、Mono。（本專案使用 44100 Hz stereo OGG，已驗證無降頻失真問題）
- **音訊初始化**：不建議主動 `ctx.suspend()`，瀏覽器本身會在頁面不可見時節流，主動 suspend 反而導致背景音消失（本專案 2-3 已修）
