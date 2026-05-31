# ============================================================
#  ui_new.py -- Public API + run_ui main loop
#  by refactor_ui.py  --  rename to ui.py when verified
# ============================================================
from __future__ import annotations
import pygame
import asyncio
import sys
import os
import math
import random

from ui_const import *
from ui_state  import *
from ui_draw_base import *
from ui_video import SpritePlayer
from ui_draw_fx   import *
from ui_draw_hud  import *
from ui_draw_cc   import *
from ui_draw_pop  import *
from ui_draw_ap   import *
from ui_draw_exam import *

def notify(msg: str):
    """取代 print()：把訊息推入 UI 訊息區。"""
    _cmd_q.append(("msg", str(msg)))
    if _notify_capturing[0]:
        _notify_capture_buf.append(str(msg))

def start_notify_capture() -> None:
    """開始捕捉後續 notify 訊息（同時仍會推入 log）。遊戲執行緒專用。"""
    _notify_capture_buf.clear()
    _notify_capturing[0] = True

def stop_notify_capture() -> list:
    """停止捕捉，回傳已捕捉的訊息列表（去除前後空白與空行）。"""
    _notify_capturing[0] = False
    result = [m.strip() for m in _notify_capture_buf if m.strip()]
    _notify_capture_buf.clear()
    return result

def set_player(player):
    """把角色物件傳給 UI，讓狀態欄即時更新。"""
    _cmd_q.append(("player", player))

async def ask_choice(options, disabled: set = None) -> int:
    """
    取代 get_player_choice()。
    options:  字串列表 或 帶 'name' key 的字典列表。
    disabled: 停用選項的 1-based 索引集合（None = 全部可選）；
              停用的選項會以灰色顯示且不可點擊。
    回傳：0 = 返回/結束，1..n = 玩家選擇的編號（1-based）。
    """
    labels = [opt["name"] if isinstance(opt, dict) else str(opt) for opt in options]
    _cmd_q.append(("choices", labels, disabled or set()))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

async def ask_subject_popup(title: str, options: list) -> int:
    """
    在畫面中央顯示科目選擇彈出視窗。
    options: 字串列表（或帶 'name' key 的 dict 列表）。
    回傳：1-based 選擇索引（不提供「返回」選項，玩家必須選一科）。
    """
    labels = [opt["name"] if isinstance(opt, dict) else str(opt) for opt in options]
    _cmd_q.append(("subj_popup", title, labels))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

async def ask_withdrawal_popup(options: list) -> str:
    """
    顯示停修選課彈出視窗。阻塞直到玩家選取一科。
    options: [(課程名稱, 說明文字), ...] 清單。
    回傳選定的課程名稱字串。
    """
    _withdrawal_popup_opts.clear()
    _withdrawal_popup_opts.extend(options)
    _withdrawal_popup_rects.clear()
    _cmd_q.append(("withdrawal_popup_open",))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

def _wasm_input_setup(prompt: str, default: str = "") -> None:
    """WASM 專用：建立支援中文 IME 的 HTML 輸入框，同時安全地讓它取得鍵盤焦點。
    採用 tabindex 屬性切換（不觸發 blur/focus 事件），避免 SDL2 崩潰。
    不呼叫 pygame.key.stop_text_input()：HTML input focus 後瀏覽器自動攔截鍵盤，
    無需停用 SDL2 text input；停用反而可能破壞 emscripten 事件迴圈。
    """
    import platform as _plt
    import json as _json
    _plt.window.eval(f"window._ask_text_prompt={_json.dumps(prompt)};")
    _plt.window.eval(f"window._ask_text_default={_json.dumps(default)};")
    _plt.window.eval(f"window._ask_text_hint={_json.dumps('（支援繁體中文輸入法）')};")
    _plt.window.eval(f"window._ask_text_btn={_json.dumps('確認')};")
    _plt.window.eval("""
(function(){
  var d=document.createElement('div');
  d.id='__py_input_ov';
  d.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;'
    +'background:rgba(0,0,0,0.52);z-index:2147483647;'
    +'display:flex;align-items:center;justify-content:center;';
  var box=document.createElement('div');
  box.style.cssText='background:#fff9f0;border-radius:16px;padding:30px 36px;'
    +'min-width:340px;text-align:center;font-family:sans-serif;'
    +'box-shadow:0 6px 28px rgba(0,0,0,0.35);'
    +'border:2px solid #e8c898;';
  var p=document.createElement('p');
  p.textContent=window._ask_text_prompt;
  p.style.cssText='font-size:17px;margin:0 0 16px;color:#4a3020;font-weight:bold;';
  var hint=document.createElement('p');
  hint.textContent=window._ask_text_hint||'';
  hint.style.cssText='font-size:12px;margin:0 0 10px;color:#a08060;';
  var inp=document.createElement('input');
  inp.type='text'; inp.id='__py_inp';
  inp.setAttribute('lang','zh-TW');
  inp.setAttribute('inputmode','text');
  inp.setAttribute('autocomplete','off');
  inp.setAttribute('spellcheck','false');
  inp.value=window._ask_text_default||'';
  inp.style.cssText='font-size:18px;width:220px;padding:8px 12px;'
    +'border:2px solid #d0a870;border-radius:8px;'
    +'background:#fffdf6;color:#3a2010;outline:none;'
    +'font-family:sans-serif;letter-spacing:2px;';
  var row=document.createElement('div');
  row.style.cssText='display:flex;gap:10px;justify-content:center;margin-top:16px;';
  var btn=document.createElement('button');
  btn.textContent=window._ask_text_btn||'';
  btn.style.cssText='padding:8px 30px;font-size:15px;'
    +'background:#FF9460;color:#fff;border:none;border-radius:8px;'
    +'cursor:pointer;font-weight:bold;';
  function ok(){
    var v=document.getElementById('__py_inp');
    if(!v) return;
    var val=v.value||'';
    try{ Module.FS.writeFile('/tmp/__ask_text_result.txt', val); }
    catch(e){ window.__ask_text_fb=val; console.warn('[ask_text] FS.writeFile failed:',e); }
  }
  btn.onclick=ok;
  inp.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.isComposing)ok();
  });
  // 組字事件（IME 輸入法使用中）→ 即時更新組字狀態供 Python 讀取
  window._cc_composing_wasm='';
  inp.addEventListener('compositionstart',function(e){
    window._cc_composing_wasm=e.data||'';
  });
  inp.addEventListener('compositionupdate',function(e){
    window._cc_composing_wasm=e.data||'';
  });
  inp.addEventListener('compositionend',function(e){
    window._cc_composing_wasm='';
  });
  row.appendChild(btn);
  box.appendChild(p); box.appendChild(hint);
  box.appendChild(inp); box.appendChild(row);
  d.appendChild(box); document.body.appendChild(d);
  // 停用 canvas 的 pointer-events，避免 canvas 事件攔截 overlay 的滑鼠點擊
  var cv=document.getElementById('canvas');
  if(cv){cv.dataset.oldPe=cv.style.pointerEvents||'';cv.style.pointerEvents='none';}
  // 延遲 focus 確保 DOM 已渲染
  setTimeout(function(){inp.focus();inp.select();},80);
})();
""")

def _wasm_input_teardown() -> None:
    """WASM 專用：移除輸入框 overlay，恢復 canvas 鍵盤焦點。"""
    import platform as _plt
    _plt.window.eval(
        "var e=document.getElementById('__py_input_ov');if(e)e.remove();"
        "delete window.__ask_text_fb;"
    )
    try:
        import os as _os_atd
        _os_atd.remove("/tmp/__ask_text_result.txt")
    except (FileNotFoundError, OSError):
        pass
    # 恢復 canvas pointer-events 與焦點
    _plt.window.eval(
        "var c=document.getElementById('canvas');"
        "if(c){c.style.pointerEvents=c.dataset.oldPe||'';delete c.dataset.oldPe;c.focus();}"
    )
    # 不呼叫 pygame.key.start_text_input()：交由 run_ui 在 cc_name 指令中管理

async def ask_text(prompt: str, default: str = "") -> str:
    """取代自由文字輸入的 input()：顯示輸入框，確認後回傳字串。
    WASM 環境：HTML overlay（支援中文 IME，不阻塞事件迴圈）。
    桌面環境：pygame 自訂輸入框（SDL2 IME，含組字預覽）。
    """
    import sys
    if sys.platform == "emscripten":
        import os as _os_at
        _ATFILE = "/tmp/__ask_text_result.txt"
        try: _os_at.remove(_ATFILE)
        except (FileNotFoundError, OSError): pass
        try:
            _wasm_input_setup(prompt, default)
            # FS bridge polling：純 open()，零 WASM→JS eval 呼叫，不影響主執行緒
            while True:
                try:
                    with open(_ATFILE, "r", encoding="utf-8") as _f:
                        result = _f.read()
                    _wasm_input_teardown()
                    return result
                except (FileNotFoundError, OSError):
                    pass
                await asyncio.sleep(0)
        except Exception as _e:
            try: _wasm_input_teardown()
            except Exception: pass
            print(f"[ask_text WASM] 失敗：{_e}")
            return default
    # 桌面環境
    _cmd_q.append(("text", prompt, default))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

async def ask_yn(prompt: str,
           yes_label:  str = "是",
           no_label:   str = "否",
           show_ctx:   bool = True,
           yes_color=None,
           no_color=None) -> bool:
    """取代 y/N 型的 input()：顯示自定義標籤按鈕，回傳 True / False。
    show_ctx=False 時不附帶 log 背景，只顯示 prompt 本身。"""
    _cmd_q.append(("yn", prompt, yes_label, no_label, show_ctx, yes_color, no_color))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

async def ask_ok(text: str, btn_label: str = "確認") -> None:
    """顯示突發事件通知彈窗（單一按鈕），block 直到玩家確認。
    text 格式：「前綴：【事件名】\\n描述文字」"""
    _cmd_q.append(("event_ok", text, btn_label))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)

async def ask_exam_start(exam_name: str) -> None:
    """在底部行動面板顯示單一「準備期中考」/「準備期末考」大按鈕，
    阻塞直到玩家點擊後才繼續（進入考試流程）。"""
    _reply_ready[0] = False
    _cmd_q.append(("exam_ready", exam_name))
    while not _reply_ready[0]: await asyncio.sleep(0)

async def ask_exam_question(prompt: str, options: list) -> int:
    """考試題目選擇彈窗：只顯示題幹與選項，不附帶任何 log 背景。
    回傳 1-based 選擇編號。"""
    labels = [opt["name"] if isinstance(opt, dict) else str(opt) for opt in options]
    _exam_q_prompt[0] = prompt
    _cmd_q.append(("exam_q", labels))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)
    return _reply_val[0]

def play_exam_sfx(correct: bool) -> None:
    """播放考試答題音效（答對/答錯）。可從遊戲執行緒直接呼叫。"""
    _play_sfx("exam_correct" if correct else "event_bad")

async def run_shape_minigame(exam_type: str = "期中") -> float:
    """執行形狀小遊戲，阻塞直到兩回合結束，回傳 0.0–1.0。"""
    _reply_ready[0] = False
    _cmd_q.append(("shape_minigame", exam_type))
    while not _reply_ready[0]: await asyncio.sleep(0)
    return float(_reply_val[0])

async def tell_story(lines: list) -> None:
    """顯示劇情對話框，每次點擊推進一行，全部結束後解除阻塞。
    lines: list of str 或 {"speaker": str, "text": str}。
    傳入 str 時自動偵測說話者：「開頭→我；X：開頭→X；其他→旁白。"""
    def _normalize(entry):
        if isinstance(entry, dict):
            return entry
        t = str(entry)
        if t.startswith("「") or t.startswith('"'):
            return {"speaker": "我", "text": t}
        colon_pos = t.find("：")
        if 0 < colon_pos <= 5:
            return {"speaker": t[:colon_pos], "text": t}
        return {"speaker": "旁白", "text": t}
    _cmd_q.append(("story", [_normalize(e) for e in lines]))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)

async def wait_start():
    """遊戲執行緒呼叫：阻塞直到玩家點擊「開始遊戲」。"""
    _start_ready[0] = False
    while not _start_ready[0]: await asyncio.sleep(0)

def notify_end():
    """遊戲結束後呼叫：切換到結束畫面。"""
    _cmd_q.append(("phase", "end"))

def notify_gameover():
    """提前 Game Over 時呼叫：切換到 Game Over 畫面（黑幕 → 背景圖 + 剪影）。"""
    _cmd_q.append(("phase", "gameover"))

def set_settlement_data(data: dict) -> None:
    """傳入期末結算資料（grades / final_score / comment）供成績單畫面使用。"""
    _cmd_q.append(("settlement_data", data))

async def wait_restart():
    """阻塞直到玩家點擊「再來一次」。"""
    _restart_ready[0] = False
    while not _restart_ready[0]: await asyncio.sleep(0)

def reset_ui():
    """清除上一局的 log 與狀態，供下一局使用。"""
    _cmd_q.append(("reset", None))

def set_time(n: int):
    """更新底部標籤列的剩餘時間點數字。"""
    _cmd_q.append(("set_time", n))

def trigger_time_overflow_warning():
    """
    觸發「時間不足」警告特效：
    剩餘時間點文字紅色閃動 + 左右震動，同時播放 damage6 音效。
    由 turn_engine 在玩家即將將時間扣成負數時呼叫。
    """
    _cmd_q.append(("time_overflow_warn", None))

def trigger_screen_shake() -> None:
    """觸發全螢幕短暫劇烈晃動效果（突發事件出現時）。非阻塞。"""
    _cmd_q.append(("screen_shake",))

def play_sfx(name: str) -> None:
    """從遊戲執行緒播放指定音效（非阻塞）。"""
    _play_sfx(name)

def play_event_sfx(is_positive: bool) -> None:
    """突發事件觸發時播放對應音效（可從遊戲執行緒直接呼叫）。"""
    if is_positive:
        snd = _sfx.get("event_good")
        ch  = _event_ch[0]
        if snd and ch:
            try:
                ch.play(snd)   # 專用保留頻道，不會被其他音效搶占
            except Exception:
                pass
        else:
            _play_sfx("event_good")
    else:
        _play_sfx("event_bad")

def was_debug_skip() -> bool:
    """若本次開始是透過 DEV 跳關按鈕觸發，回傳 True 並清除旗標。"""
    if _debug_skip_ready[0]:
        _debug_skip_ready[0] = False
        return True
    return False

def set_roll_call(course: str) -> None:
    """設定本週點名科目，在成績面板左側顯示警示便利貼。非阻塞。"""
    _cmd_q.append(("roll_call_set", course))

def clear_roll_call() -> None:
    """清除點名警示便利貼（週末結算後呼叫）。非阻塞。"""
    _cmd_q.append(("roll_call_clear",))

def set_roll_call_attended(attended: bool) -> None:
    """設定本週點名週次是否已執行「正常上課」（動態更新綠勾顯示）。非阻塞。"""
    _cmd_q.append(("roll_call_attended", attended))

def set_roll_call_xed(xed: bool) -> None:
    """設定點名課是否被翹掉（動態更新紅叉顯示）。非阻塞。"""
    _cmd_q.append(("roll_call_xed", xed))

async def ask_skip_class_popup(courses: list, skipped: set, attended: set) -> "str | None":
    """
    顯示翹課選課彈出視窗。阻塞直到玩家選取課名或取消。
    courses: 所有課名清單
    skipped: 本週已翹的課（顯示紅色印章）
    attended: 本週已上的課（顯示綠色印章）
    回傳選定的課名字串，或 None（取消）。
    """
    _skip_popup_courses.clear()
    _skip_popup_courses.extend(courses)
    _skip_popup_skipped.clear()
    _skip_popup_skipped.update(skipped)
    _skip_popup_attended.clear()
    _skip_popup_attended.update(attended)
    _skip_popup_result[0] = None
    _skip_popup_ready[0] = False
    _cmd_q.append(("skip_popup_open",))
    while not _skip_popup_ready[0]: await asyncio.sleep(0)
    return _skip_popup_result[0]

def set_special_disabled(names: dict) -> None:
    """更新特殊行動的停用狀態。names = {行動名: 倒數格數}（空 dict 表示清除全部）。"""
    _cmd_q.append(("special_disabled", dict(names)))

def set_allnighter_count(n: int) -> None:
    """更新本週已熬夜次數（0-5），驅動按鈕右下角計數器。"""
    _cmd_q.append(("allnighter_count", n))

def set_week(w: int):
    """由遊戲執行緒呼叫，更新週次輪盤顯示並觸發對應 BGM。"""
    _week[0] = w
    _cmd_q.append(("bgm_week", w))

def begin_char_create():
    """切換到角色創建畫面（隱藏一般遊戲 UI）。"""
    _cmd_q.append(("phase", "char_create"))

def end_char_create():
    """角色創建完成，切回遊戲畫面。"""
    _cmd_q.append(("phase", "game"))

async def ask_cc_name(prompt: str) -> str:
    """顯示姓名輸入 modal，回傳玩家輸入的字串。
    WASM：FS bridge 方案——JS 寫 /tmp/__cc_result.txt，Python 用 open() 讀（無 eval polling 死鎖）。
    桌面：pygame cc_name 輸入框（SDL2 IME）。
    """
    import sys as _sys_ccn
    if _sys_ccn.platform == "emscripten":
        import os
        _RESULT_FILE = "/tmp/__cc_result.txt"
        # 清除上次殘留結果
        try: os.remove(_RESULT_FILE)
        except FileNotFoundError: pass

        # ① 呼叫 JS 顯示 overlay — 唯一一次 eval()，在任何 await 之前執行
        _shown = False
        try:
            import platform as _plt
            import json as _jj
            # 清除上次可能殘留的 JS global fallback（必須在任何 await 之前執行）
            try: _plt.window.eval("window.__cc_result_fb = null;")
            except Exception: pass
            _plt.window.eval(f"__cc_show({_jj.dumps(prompt)})")
            _shown = True
        except Exception as _e:
            print(f"[ask_cc_name] __cc_show 失敗：{_e}，回退 cc_name 模式")

        if _shown:
            # polling：以下順序：
            #   ① 讀 /tmp/__cc_result.txt（FS bridge 主路徑）
            #   ② 讀 window.__cc_result_fb（JS global fallback；FS.writeFile 失敗時用）
            # 不在 await 後呼叫 eval()，僅做 property 讀取（同步、無死鎖風險）
            _poll_count = 0
            while True:
                # ─── ① FS bridge ────────────────────────────────
                try:
                    with open(_RESULT_FILE, "r", encoding="utf-8") as _f:
                        _raw = _f.read()
                    final = _raw.strip() or "無名氏"
                    _cc_reply_val[0]  = final
                    _cc_reply_ready[0] = True
                    return final
                except (FileNotFoundError, OSError):
                    pass
                # ─── ② JS global fallback ────────────────────────
                try:
                    import platform as _plt2
                    _fb = _plt2.window.__cc_result_fb
                    # _fb 為 null/undefined/空 時跳過
                    if _fb is not None and str(_fb) not in ("", "null", "undefined", "None"):
                        final = str(_fb).strip() or "無名氏"
                        _cc_reply_val[0]  = final
                        _cc_reply_ready[0] = True
                        return final
                except Exception:
                    pass
                _poll_count += 1
                if _poll_count % 120 == 60:   # 每隔約 1 秒印一次
                    print("[ask_cc_name] polling 等待玩家輸入名字...")
                await asyncio.sleep(0)

    # 桌面（及 WASM overlay 顯示失敗時的 fallback）
    _cmd_q.append(("cc_name", prompt))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]:
        await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_portrait() -> str:
    """讓玩家選擇人物外觀（b1 / g1），回傳前綴字串。"""
    _cc_reply_ready[0] = False
    _cmd_q.append(("cc_portrait",))
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_dept(options: list) -> int:
    """顯示系級橫向卡片，回傳 1-based 選擇編號。"""
    _cmd_q.append(("cc_dept", options))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_drawbacks(drawbacks: list, max_sel: int = 2) -> list:
    """顯示負面特質切換卡片（最多 max_sel 個），回傳已選字典列表。"""
    _cmd_q.append(("cc_drawbacks", drawbacks, max_sel))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_stats(total_pts: int, base_pts: int = 0, talent: dict = None, de_level: dict = None) -> tuple:
    """顯示能力點分配畫面，回傳 (stamina, intel, luck)。"""
    _cmd_q.append(("cc_stats", total_pts, base_pts, talent or {}, de_level or {}))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_de_level(levels: list) -> dict:
    """顯示年級卡片（單選），回傳選中的年級字典。"""
    _cmd_q.append(("cc_de_level", levels))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_talent(slot_results: list) -> None:
    """觸發拉霸機天賦動畫，3 個結果由呼叫方預先決定。阻塞直到玩家點繼續。"""
    _cmd_q.append(("cc_slot", list(slot_results)))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)

async def ask_cc_extra_events(events_data: list, intel: int) -> list:
    """顯示額外事件選擇畫面，回傳選中的事件 ID 列表。"""
    _cmd_q.append(("cc_extra", list(events_data), intel))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def ask_cc_summary(data: dict) -> str:
    """顯示玩家資訊一覽卡片，回傳 'start' 或 'restart'。"""
    _cmd_q.append(("cc_summary", dict(data)))
    _cc_reply_ready[0] = False
    while not _cc_reply_ready[0]: await asyncio.sleep(0)
    return _cc_reply_val[0]

async def show_guide_modal() -> None:
    """顯示「遊戲說明」modal（任何 phase 均可），阻塞直到玩家關閉。
    用於遊戲開始時的新手教學，替代三個 show_extra_event_popup 純文字彈窗。
    """
    _guide_page[0] = 0
    _guide_active[0] = True
    while _guide_active[0]:
        await asyncio.sleep(0)

async def show_extra_event_popup(lines: list, title: str, border_color: tuple) -> None:
    """顯示帶彩色邊框的事件通知彈窗，阻塞直到玩家點確認。"""
    body = "\n".join(str(l) for l in lines if l)
    text = f"{title}\n{body}" if body else title
    _cmd_q.append(("event_ok_col", text, border_color))
    _reply_ready[0] = False
    while not _reply_ready[0]: await asyncio.sleep(0)

async def notify_timetable(courses: list):
    """
    顯示課表彈出畫面，阻塞直到玩家點確認。
    courses: [{"name": "統計學", "day": "週一", "time": "08:10", "credits": 3}, ...]
    """
    _cmd_q.append(("timetable", courses))
    _modal_ready[0] = False
    while not _modal_ready[0]:
        await asyncio.sleep(0)

async def notify_grade_report(items: list, sfx: str = None):
    """
    顯示成績公告彈出畫面，阻塞直到玩家點確認。
    items: [{"name": "小考一", "score": 75}, ...]
    sfx:   彈窗出現時立即播放的音效 key（選填）
    """
    _cmd_q.append(("grade_report", items, sfx))
    _modal_ready[0] = False
    while not _modal_ready[0]: await asyncio.sleep(0)

async def open_shop_ui(items: list, event_sys=None) -> None:
    """
    開啟道具店圖形化介面，阻塞遊戲執行緒直到玩家離開商店。
    購買邏輯由 pygame 主執行緒的事件處理器直接套用（遊戲執行緒此時已暫停）。
    """
    _shop_items.clear()
    _shop_items.extend(items)
    _shop_event_sys[0]  = event_sys
    _shop_hover_idx[0]  = -1
    _shop_msg[0]        = ""
    _shop_msg_time[0]   = 0
    _shop_scroll_y[0]   = 0   # 每次開店重置捲動位置
    _shop_exit_ready[0] = False
    _cmd_q.append(("phase", "shop"))
    while not _shop_exit_ready[0]: await asyncio.sleep(0)
    _cmd_q.append(("phase", "game"))

def trigger_ripple() -> None:
    """觸發漣漪轉場效果；由遊戲執行緒在週次切換時呼叫。"""
    _cmd_q.append(("ripple",))

def set_portrait_override(key: "str | None") -> None:
    """
    強制立繪顯示指定 key（e.g. 'b1_9'）。
    key=None 時解除強制，恢復 _get_portrait_key() 的自動選擇邏輯。非阻塞。
    """
    _cmd_q.append(("portrait_override", key))

def get_portrait_prefix() -> str:
    """回傳當前角色立繪前綴（'b1' 或 'g1'）。可從遊戲執行緒直接讀取（無鎖）。"""
    return _portrait_prefix[0]

async def run_pregame_countdown() -> None:
    """
    在形狀小遊戲之前播放倒數動畫（準備提示 → 3 → 2 → 1 → 開始！）。
    阻塞直到「開始！」完全淡出後才繼續。
    """
    _reply_ready[0] = False
    _cmd_q.append(("pregame_countdown",))
    while not _reply_ready[0]: await asyncio.sleep(0)

def show_action_result(lines: list, title: str = "行動結果",
                       direction: str = "right") -> None:
    """
    由遊戲執行緒呼叫，觸發行動結果視窗。
    direction="right" → 由右而左滑入（一般行動 / 特殊行動）
    direction="top"   → 由上而下滑入（考試答對 / 答錯）
    lines: 要顯示的結果文字列表（如「體力 -4」、「金錢 +150」）。
    title: 彈出視窗的標題，通常傳入行動名稱（如「認真讀書」）。
    """
    _popup_lines.clear()
    _popup_lines.extend(lines)   # 保留 tuple 型別（"multi" 多色行、(text,col) 標注行）
    _popup_title[0]     = title
    _popup_direction[0] = direction
    _now = pygame.time.get_ticks()
    _popup_t0[0]        = _now
    _action_flash_t0[0] = _now   # 觸發全螢幕白光閃爍

def show_action_blocked(lines: list, title: str = "",
                        sfx: str = "damage6",
                        direction: str = "right") -> None:
    """
    由遊戲執行緒呼叫：顯示行動阻斷提示視窗（不觸發白光閃爍），並播放音效。
    適用於進食金錢不足等無法執行行動的情況。
    """
    _popup_lines.clear()
    _popup_lines.extend(lines)
    _popup_title[0]     = title
    _popup_direction[0] = direction
    _popup_t0[0]        = pygame.time.get_ticks()
    # 不設定 _action_flash_t0（不觸發白光閃爍）
    _play_sfx(sfx)

def display_status(player):
    set_player(player)

def display_menu(options, title="請選擇行動"):
    notify(f"--- {title} ---")
    for i, opt in enumerate(options, start=1):
        name = opt["name"] if isinstance(opt, dict) else opt
        desc = f" - {opt['desc']}" if isinstance(opt, dict) and "desc" in opt else ""
        notify(f"  {i}. {name}{desc}")
    notify("  0. 返回 / 結束")

def get_player_choice(options) -> int:
    return ask_choice(options)

def _handle_cc_action(ev_pos):
    """
    處理 char_create 階段的滑鼠點擊事件。
    修改全域 _cc_* 狀態；若步驟完成則呼叫 _cc_reply_ready[0] = True。
    """
    mode = _cc_mode[0]
    data = _cc_data[0]

    if mode == "name":
        # 依賴 _cc_btn_cache 中暫存的按鈕 Rect（由繪製函式寫入）
        ok = _cc_btn_cache.get("name_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = _cc_tvalue[0] + _cc_composing[0]   # 包含組字中的文字
            _cc_composing[0] = ""
            _cc_mode[0] = ""
            pygame.key.stop_text_input()
            _cc_reply_ready[0] = True

    elif mode == "portrait":
        for (r, prefix) in (_cc_btn_cache.get("portrait_cards") or []):
            if r.collidepoint(ev_pos):
                _portrait_prefix[0] = prefix
                _cc_reply_val[0]    = prefix
                _cc_mode[0]         = ""
                _cc_reply_ready[0] = True
                return

    elif mode == "dept":
        for (r, idx) in (_cc_btn_cache.get("dept_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_reply_val[0] = idx
                _cc_mode[0] = ""
                _cc_reply_ready[0] = True
                return

    elif mode == "drawbacks":
        max_sel = _cc_btn_cache.get("drawbacks_max", 2)
        for (r, idx) in (_cc_btn_cache.get("drawback_cards") or []):
            if r.collidepoint(ev_pos):
                if idx in _cc_sel:
                    _cc_sel.remove(idx)
                elif len(_cc_sel) < max_sel:
                    _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("drawbacks_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = [data[i] for i in _cc_sel]
            _cc_mode[0] = ""
            _cc_reply_ready[0] = True

    elif mode == "stats":
        total = _cc_stat_total[0]
        # [-] 按鈕
        for i, r in enumerate(_cc_btn_cache.get("stats_minus") or []):
            if r.collidepoint(ev_pos):
                if _cc_stat_vals[i] > 0:
                    _cc_stat_vals[i] -= 1
                    _cc_stat_raw[i] = str(_cc_stat_vals[i])
                _cc_active_stat[0] = None
                return
        # [+] 按鈕
        for i, r in enumerate(_cc_btn_cache.get("stats_plus") or []):
            if r.collidepoint(ev_pos):
                if sum(_cc_stat_vals) < total:
                    _cc_stat_vals[i] += 1
                    _cc_stat_raw[i] = str(_cc_stat_vals[i])
                _cc_active_stat[0] = None
                return
        # 輸入框焦點（依位置判斷）
        for i, r in enumerate(_cc_btn_cache.get("stats_boxes") or []):
            if r.collidepoint(ev_pos):
                _cc_active_stat[0] = i
                _cc_stat_raw[i] = ""
                return
        # 確認按鈕
        ok = _cc_btn_cache.get("stats_ok")
        if ok and ok.collidepoint(ev_pos):
            if sum(_cc_stat_vals) <= total:
                _cc_reply_val[0] = tuple(_cc_stat_vals)
                _cc_mode[0] = ""
                _cc_active_stat[0] = None
                _cc_reply_ready[0] = True

    elif mode == "extra":
        for (r, ev_id) in (_cc_btn_cache.get("extra_cards") or []):
            if r.collidepoint(ev_pos):
                ev_map = {e["id"]: e for e in _cc_extra_data}
                ev     = ev_map.get(ev_id)
                if not ev:
                    return
                if ev_id in _cc_extra_sel:
                    _cc_extra_sel.remove(ev_id)
                else:
                    excl = ev.get("exclusive", [])
                    if any(x in _cc_extra_sel for x in excl):
                        _cc_extra_warn[0] = pygame.time.get_ticks()
                        return
                    _cc_extra_sel.append(ev_id)
                return
        ok = _cc_btn_cache.get("extra_ok")
        if ok and ok.collidepoint(ev_pos):
            _cc_reply_val[0] = list(_cc_extra_sel)
            _cc_mode[0]      = ""
            _cc_extra_sel.clear()
            _cc_reply_ready[0] = True

    elif mode == "slot":
        ok = _cc_btn_cache.get("slot_ok")
        if ok and ok.collidepoint(ev_pos) and all(p == "done" for p in _slot_phase):
            _cc_mode[0] = ""
            _cc_confetti.clear()
            _cc_reply_ready[0] = True

    elif mode == "summary":
        start_r   = _cc_btn_cache.get("summary_start")
        restart_r = _cc_btn_cache.get("summary_restart")
        if start_r and start_r.collidepoint(ev_pos):
            _play_sfx("start_click")   # soundreality-interface-6-204504.ogg
            _cc_reply_val[0] = "start"
            _cc_mode[0] = ""
            _cc_reply_ready[0] = True
        elif restart_r and restart_r.collidepoint(ev_pos):
            _play_sfx("ui_click")
            _cc_reply_val[0] = "restart"
            _cc_mode[0] = ""
            _cc_reply_ready[0] = True

    elif mode == "de_level":
        for (r, idx) in (_cc_btn_cache.get("de_level_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_sel.clear()
                _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("de_level_ok")
        if ok and ok.collidepoint(ev_pos):
            if _cc_sel:
                _cc_reply_val[0] = data[_cc_sel[0]]
                _cc_mode[0] = ""
                _cc_reply_ready[0] = True

    elif mode == "talent":
        for (r, idx) in (_cc_btn_cache.get("talent_cards") or []):
            if r.collidepoint(ev_pos):
                _cc_sel.clear()
                _cc_sel.append(idx)
                return
        ok = _cc_btn_cache.get("talent_ok")
        if ok and ok.collidepoint(ev_pos):
            if _cc_sel:
                _cc_reply_val[0] = data[_cc_sel[0]]
                _cc_mode[0] = ""
                _cc_reply_ready[0] = True

async def run_ui():
    """啟動 pygame 視窗並進入主迴圈，直到視窗關閉。"""
    import os
    os.environ["SDL_IME_SHOW_UI"] = "1"   # 啟用原生 IME 候選字清單與組字底線（須在 init 前設定）
    pygame.init()
    pygame.key.set_repeat(400, 50)  # 長按重複：400ms 後開始，每 50ms 一次（backspace 連刪）

    # ── 初始化音效 ────────────────────────────────────────────
    try:
        import sys as _sys_m
        # 所有 OGG 原始編碼為 44100Hz（已驗證，dropping.ogg 為 48000Hz）。
        # WASM 和桌面都用 44100Hz：pygame 無需 resample，SDL2 → Web Audio API 直送。
        # （之前誤設 22050Hz，導致 pygame 把 44100→22050 降頻 → 失真）
        # tab 切換造成的 AudioContext suspend/resume 由 patch_index.py 的 Page Visibility fix 處理
        _freq = 44100
        # WASM: ScriptProcessorNode 在主執行緒處理音效。
        # 前景時主執行緒忙於渲染，buffer 填不及 → 失真。
        # 增大 buffer 到 8192 給更多餘裕（~186ms latency，BGM 可接受）。
        # 8192 延遲太明顯（~186ms）；退回 4096（~93ms），latency 可接受。
        # 若仍有失真考慮降低渲染負載（已修 SRCALPHA heap）而非再加大 buffer。
        _buf  = 4096  if _sys_m.platform == "emscripten" else 512
        pygame.mixer.init(frequency=_freq, size=-16, channels=2, buffer=_buf)
        # WASM：減少 channel 數量降低音訊處理負載
        if _sys_m.platform == "emscripten":
            pygame.mixer.set_num_channels(6)   # 桌面預設 8，WASM 降為 6（含 BGM ch）
        pygame.mixer.set_reserved(2)          # channel 0: 突發事件正面音效
                                              # channel 1: BGM 專用（Sound 取代 music）
        _event_ch[0]  = pygame.mixer.Channel(0)
        _bgm_ch_obj[0] = pygame.mixer.Channel(1)   # BGM 專用 channel（WASM 相容）
        _se_dir = resource_path("asset", "audio", "se")
        def _ld(fn):
            try:
                return pygame.mixer.Sound(os.path.join(_se_dir, fn))
            except Exception:
                return None
        _sfx["start_click"] = _ld("soundreality-interface-6-204504.ogg")
        _sfx["cc_click"]    = _ld("dropping.ogg")
        _sfx["action"]      = _ld("attack1.ogg")
        _sfx["ui_click"]    = _ld("poka.ogg")
        _sfx["back"]        = _ld("universfield-interface-03-277552.ogg")
        _sfx["damage6"]     = _ld("damage6.ogg")
        _sfx["cash"]        = _ld("cash.ogg")
        _sfx["hover"]       = _ld("liecio-menu-buttom-190020.ogg")
        _sfx["event_good"]   = _ld("freesound_community-good-6081.ogg")
        _sfx["event_bad"]    = _ld("u_3bsnvt0dsu-spin-fail-295088.ogg")
        _sfx["midterm_pass"] = _ld("freesound_community-piglevelwin2mp3-14800.ogg")
        _sfx["midterm_fail"] = _ld("shidenbeatsmusic-no-luck-too-bad-disappointing-sound-effect-112943.ogg")
        _sfx["grade_reveal"] = _ld("freesound_community-level-win-6416.ogg")
        _sfx["stamp_hit"]    = _ld("lordsonny-cinematic-hit-159487.ogg")
        _sfx["game_over"]    = _ld("blendertimer-happy-outro-8110.ogg")
        _sfx["shop_open"]    = _ld("mubeenstudio-money-counting-machine-sfx-406495.ogg")
        _sfx["talent_draw"]  = _ld("u_u4pf5h7zip-prop_show-345987.ogg")
        _sfx["talent_none"]  = _ld("nikin-pop-up-something-160353.ogg")
        _sfx["exam_correct"] = _ld("updatepelgo-success-221935.ogg")
        _sfx["pcd_3"]  = _ld("universfield-soft-notice-146623.ogg")
        _sfx["pcd_go"] = _ld("notification_message-notification-alert-9-331720.ogg")
    except Exception:
        pass

    # ── WASM BGM 快取：預載最常用的兩個 BGM，避免遊戲中 OGG decode 造成卡頓 ──
    # 只在 WASM 上需要（桌面用 music 串流，不需要預先 decode）。
    # Morning_Rain：標題畫面立刻就播；Aether：進入角色創建時立刻要用。
    if sys.platform == "emscripten":
        try:
            _bgm_pre_dir = resource_path("asset", "audio", "bgm")
            for _bgm_pre_fn in ("Music-Morning_Rain.ogg", "Music-Aether.ogg"):
                _bgm_pre_path = os.path.join(_bgm_pre_dir, _bgm_pre_fn)
                if os.path.isfile(_bgm_pre_path) and _bgm_pre_fn not in _bgm_cache:
                    try:
                        _bgm_cache[_bgm_pre_fn] = pygame.mixer.Sound(_bgm_pre_path)
                    except Exception:
                        pass
        except Exception:
            pass

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("如何渡過這學期？")
    clock  = pygame.time.Clock()

    # ── 自訂游標（pen_mouse.png）────────────────────────────────
    # 注意：mouse.set_visible(False) 移至圖片載入成功後才呼叫
    # 若圖片載入失敗（如 WASM 環境），系統游標維持可見
    _cursor_normal   = None
    _cursor_pressed  = None
    _cursor_glow_pad = 0
    _cursor_gball    = None   # 筆尖奶茶色光球 Surface
    _cursor_gball_r  = 0      # 光球在 Surface 中的中心偏移量

    def _build_cursor_with_glow(src):
        """回傳 (composite_surf, pad)。
        composite 中心即原圖，四周有白色柔光暈；pad 為光暈擴張 px 數。"""
        pad  = 8
        w, h = src.get_size()
        comp = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        # 白色版：保留原始 alpha，RGB 全設為白
        white = src.copy()
        white.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
        # 三層光暈（由外而內：漸放大 + 降低 alpha）
        for expand, glow_a in [(6, 18), (4, 40), (2, 65)]:
            gw, gh = w + expand * 2, h + expand * 2
            glow_layer = pygame.transform.smoothscale(white, (gw, gh))
            # 將 glow_layer 的 alpha 壓縮為 glow_a / 255
            a_mask = pygame.Surface((gw, gh), pygame.SRCALPHA)
            a_mask.fill((255, 255, 255, glow_a))
            glow_layer.blit(a_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            comp.blit(glow_layer, (pad - expand, pad - expand))
        # 原圖疊在最上層
        comp.blit(src, (pad, pad))
        return comp, pad

    try:
        _cur_raw = pygame.image.load(
            resource_path("asset", "picture", "small_object", "pen_mouse.png")
        ).convert_alpha()
        _cur_h   = min(_cur_raw.get_height(), 40)
        _cur_w   = int(_cur_raw.get_width() * _cur_h / _cur_raw.get_height())
        _cur_base = pygame.transform.smoothscale(_cur_raw, (_cur_w, _cur_h))
        _cursor_normal,  _cursor_glow_pad = _build_cursor_with_glow(_cur_base)
        # 按下版：先染奶茶色，再包光暈
        _cur_press = _cur_base.copy()
        _cur_press.fill((200, 155, 110), special_flags=pygame.BLEND_RGB_MULT)
        _cursor_pressed, _ = _build_cursor_with_glow(_cur_press)
        pygame.mouse.set_visible(False)   # 圖片載入成功才隱藏系統游標
        # ── 筆尖奶茶色光球（預建，永久顯示於筆尖） ──────────────
        _gb_r  = 20                       # 光球半徑（px）
        _gb_d  = _gb_r * 2 + 2
        _cursor_gball   = pygame.Surface((_gb_d, _gb_d), pygame.SRCALPHA)
        _cursor_gball_r = _gb_r + 1       # Surface 內的中心座標
        _mt = (215, 170, 118)             # 奶茶色
        for _gr, _ga in [(_gb_r,       12),
                         (int(_gb_r * 0.72), 30),
                         (int(_gb_r * 0.48), 58),
                         (int(_gb_r * 0.28), 95)]:
            pygame.draw.circle(_cursor_gball, (*_mt, _ga),
                               (_cursor_gball_r, _cursor_gball_r), _gr)
    except Exception:
        pass

    fl = _get_font(40)   # 開始 / 結束畫面標題大字
    fm = _get_font(22)
    fs = _get_font(17)
    _font_micro[0]   = _get_font(11)        # 週次輪盤小字
    _font_bold[0]    = _get_font_bold(17)   # 粗體 size-17（按鈕 / 小文字）
    _font_bold_lg[0] = _get_font_bold(22)   # 粗體 size-22（標題 / 上方視窗）
    _font_bold_xl[0] = _get_font_bold(26)   # 粗體 size-26（日曆週次大字）

    # 版面 Rect
    sr = pygame.Rect(0, 0,           WIN_W, STATUS_H)   # 狀態欄
    cr = pygame.Rect(0, STATUS_H,    WIN_W, CHAR_H)      # 人物立繪區
    ar = pygame.Rect(0, STATUS_H + CHAR_H, WIN_W, ACTION_H)  # 底部行動面板
    # 結束畫面的 log 用人物區的 Rect
    lr = cr

    # ── 預先計算漸層 Surface ──────────────────────────────────
    _grads["bg"]     = _gradient_surf(WIN_W, WIN_H,    (255, 245, 222), (252, 232, 200))
    _grads["status"] = _gradient_surf(WIN_W, STATUS_H, (255, 226, 190), (255, 242, 214))
    _grads["input"]  = _gradient_surf(WIN_W, ACTION_H, (255, 242, 214), (255, 226, 190))
    _grads["start"]  = _gradient_surf(WIN_W, WIN_H,    (255, 248, 226), (255, 228, 192))

    # ── 匯入背景圖片（cover 縮放，失敗時保留漸層）───────────
    _bg_dir = resource_path("asset", "picture", "background")
    _title_img = _load_cover(
        os.path.join(_bg_dir, "title_background.jpg"), WIN_W, WIN_H)
    if _title_img is not None:
        _grads["start"] = _title_img

    # ── 批次載入所有週次背景圖 ────────────────────────────────
    _unique_bg_files = sorted(set(v for v in _WEEK_BG.values() if v is not None))
    for _fn in _unique_bg_files:
        _img = _load_cover(os.path.join(_bg_dir, _fn), WIN_W, WIN_H)
        if _img is not None:
            _bg_surfs[_fn] = _img
    # 用第 1-2 週背景作初始底圖（無圖則保持漸層）
    _init_bg = _bg_surfs.get("1234_background.jpg")
    if _init_bg is not None:
        _bg_current[0] = _init_bg
        _grads["bg"]   = _init_bg   # 保持 fallback 相容
        # 圖片背景時，狀態欄與行動面板改為半透明疊層，讓建築圖透出
        _st_ov = pygame.Surface((WIN_W, STATUS_H), pygame.SRCALPHA)
        _st_ov.fill((255, 238, 212, 215))
        _grads["status"] = _st_ov
        _in_ov = pygame.Surface((WIN_W, ACTION_H), pygame.SRCALPHA)
        _in_ov.fill((255, 238, 212, 215))
        _grads["input"] = _in_ov

    # ── Game Over 背景圖 ───────────────────────────────────────────
    try:
        _go_img = _load_cover(
            os.path.join(_bg_dir, "the_end_background.jpg"), WIN_W, WIN_H)
        if _go_img is not None:
            _grads["gameover"] = _go_img
    except Exception:
        pass

    # ── 全螢幕黑邊背景圖（原始尺寸，進入全螢幕時再縮放至螢幕大小）──
    _outside_bg_raw = None
    try:
        _outside_bg_raw = pygame.image.load(
            os.path.join(_bg_dir, "outside_background.jpg")).convert()
    except Exception as _e:
        _p = os.path.join(_bg_dir, "outside_background.jpg")
        print(f"[圖片診斷] outside_bg 失敗: {_p}  存在:{os.path.exists(_p)}  錯誤:{_e}")

    # ── BGM 初始化（設定資料夾，播放標題音樂）──────────────────
    _bgm_dir[0] = resource_path("asset", "audio", "bgm")
    _request_bgm("Music-Morning_Rain.ogg")

    # ── 角色創建背景影片（SpritePlayer，循環）──────────────────
    _cc_player[0] = SpritePlayer(
        resource_path("asset", "video_frames", "skill_bg"), loop=True)

    # ── 結算過場影片（SpritePlayer，單次播放）───────────────────
    _end_player[0] = SpritePlayer(
        resource_path("asset", "video_frames", "end_cutscene"), loop=False)

    # ── 結局背景影片（SpritePlayer，循環）──────────────────────
    for _ebkey, _ebslug in [
        ("best",  "best_bg"),
        ("next",  "next_bg"),
        ("break", "break_bg"),
        ("lose",  "lose_bg"),
    ]:
        _end_bg_players[_ebkey] = SpritePlayer(
            resource_path("asset", "video_frames", _ebslug), loop=True)

    # ── 預初始化 CC overlay surface（避免首幀 720×draw.line 卡死主執行緒）──
    # _draw_cc_bg 在 char_create 首幀會建立 1280×720 SRCALPHA surface
    # 並執行 720 次 pygame.draw.line（約 1–5 秒），無 yield → Chrome 判定頁面無回應。
    # 在載入畫面期間（進度條）預先呼叫一次，把代價移到玩家等待的時間點。
    try:
        _pre_surf = pygame.Surface((WIN_W, WIN_H))
        _draw_cc_bg(_pre_surf)
        del _pre_surf
    except Exception as _pre_e:
        print(f"[run_ui] CC overlay 預初始化失敗（不影響遊戲）：{_pre_e}")

    # 全螢幕切換按鈕固定 Rect（右下角，各畫面常駐）
    fs_btn = pygame.Rect(WIN_W - 46, WIN_H - 46, 40, 40)

    # ── 全螢幕支援：真實 Surface、偏移量、縮放背景 ──────────────
    real_screen  = screen   # 指向實際 display surface
    fs_bg_scaled = None     # 縮放後的全螢幕黑邊背景（進入全螢幕時產生）
    _fs_off = [0, 0]        # [off_x, off_y]：遊戲畫布在螢幕上的偏移

    def _tpos(pos):
        """將原生螢幕座標轉換為遊戲畫布座標（全螢幕有偏移時使用）。"""
        return (pos[0] - _fs_off[0], pos[1] - _fs_off[1])

    running = True
    _prev_hov_btns: set = set()   # 上一幀 hover 中的按鈕 key 集合（用於首次進入偵測）
    _prev_tick = pygame.time.get_ticks()
    _ime_arrow_prev    = {"left": False, "right": False}  # 上一幀 ←/→ 按壓狀態（邊緣偵測用）
    _ime_cancel_frames = [0]   # 強制取消 IME 後，忽略殘留 TEXTEDITING 的幀數倒數
    while running:
        _now_tick = pygame.time.get_ticks()
        _dt_ms    = max(1, _now_tick - _prev_tick)
        _prev_tick = _now_tick
        mpos = _tpos(pygame.mouse.get_pos())

        # ── WASM：每幀同步全螢幕狀態（JS fullscreenchange 寫 /tmp/__fs_state.txt）
        # '1' = 全螢幕中，'0' = 已退出。不刪檔，JS 每次事件都會覆寫。
        import sys as _sys_fschk
        if _sys_fschk.platform == "emscripten":
            try:
                import os as _os_fschk
                if _os_fschk.path.exists("/tmp/__fs_state.txt"):
                    with open("/tmp/__fs_state.txt", "r") as _fsf:
                        _is_fullscreen[0] = (_fsf.read().strip() == "1")
            except (FileNotFoundError, OSError):
                pass

        # 道具店按鈕是否可點擊：只有在行動選單中且選項包含道具店時才亮起
        shop_active = (_mode[0] == "choices" and "🏪 前往道具店" in _choices)

        # ── BGM 非阻塞切換 tick ───────────────────────────────
        # 平台差異：
        #   桌面：pygame.mixer.music（串流，即時 load，有 fade 效果）
        #   WASM：Sound + Channel（music 無聲音輸出；Sound 用快取避免 decode stutter）
        if (_bgm_pending[0] is not None
                and pygame.time.get_ticks() >= _bgm_switch_at[0]):
            _next_bgm      = _bgm_pending[0]
            _bgm_pending[0] = None
            _bgm_current[0] = _next_bgm
            if _next_bgm is not None:
                _bpath = os.path.join(_bgm_dir[0], _next_bgm)
                if os.path.isfile(_bpath):
                    try:
                        if sys.platform == "emscripten":
                            # ── WASM：Sound + Channel ──────────────────
                            _ch = _bgm_ch_obj[0]
                            # 優先從快取取得（避免重複 OGG decode stutter）
                            if _next_bgm in _bgm_cache:
                                _new_snd = _bgm_cache[_next_bgm]
                            else:
                                _new_snd = pygame.mixer.Sound(_bpath)
                                _bgm_cache[_next_bgm] = _new_snd
                            _bgm_snd_obj[0] = _new_snd
                            if _ch is not None:
                                _ch.play(_new_snd, loops=-1)
                            else:
                                _new_snd.play(-1)
                        else:
                            # ── 桌面：music（串流，即時切換）─────────
                            pygame.mixer.music.load(_bpath)
                            pygame.mixer.music.play(-1, fade_ms=BGM_FADE_MS)
                    except Exception as _bgm_e:
                        print(f"[BGM] load/play 失敗：{_bgm_e}")
            else:
                # 切換到靜音
                try:
                    if sys.platform == "emscripten":
                        _ch = _bgm_ch_obj[0]
                        if _ch is not None:
                            _ch.stop()
                        elif _bgm_snd_obj[0] is not None:
                            _bgm_snd_obj[0].stop()
                    else:
                        pygame.mixer.music.stop()
                except Exception:
                    pass

        # ── 消化遊戲執行緒的命令 ─────────────────────────────
        # try/except 保護：任何 tag handler 例外不會 crash 整個 run_ui asyncio task
        while _cmd_q:
          try:
            cmd = _cmd_q.popleft()
            tag = cmd[0]
            if tag == "msg":
                _log.extend(_wrap(cmd[1], fs, WIN_W - 28))
                _scroll[0] = 0
            elif tag == "player":
                _player[0] = cmd[1]
            elif tag == "choices":
                _choices.clear()
                _choices.extend(cmd[1])
                _choices_disabled.clear()
                if len(cmd) > 2:
                    _choices_disabled.update(cmd[2])
                _mode[0] = "choices"
            elif tag == "yn":
                _prompt[0]       = cmd[1]
                _yn_labels[0]    = cmd[2] if len(cmd) > 2 else "是"
                _yn_labels[1]    = cmd[3] if len(cmd) > 3 else "否"
                _yn_show_ctx[0]  = cmd[4] if len(cmd) > 4 else True
                _yn_yes_color[0] = cmd[5] if len(cmd) > 5 else None
                _yn_no_color[0]  = cmd[6] if len(cmd) > 6 else None
                _mode[0] = "yn"
            elif tag == "event_ok":
                _event_ok_text[0]         = cmd[1]
                _event_ok_btn_label[0]    = cmd[2] if len(cmd) > 2 else "確認"
                _event_ok_border_color[0] = None
                _mode[0]                  = "event_ok"
            elif tag == "event_ok_col":
                _event_ok_text[0]         = cmd[1]
                _event_ok_btn_label[0]    = "確認"
                _event_ok_border_color[0] = cmd[2]
                _mode[0]                  = "event_ok"
            elif tag == "text":
                _prompt[0] = cmd[1]
                _tvalue[0] = cmd[2] if len(cmd) > 2 else ""
                _mode[0] = "text"
                pygame.key.start_text_input()  # Windows IME 必須主動開啟
            elif tag == "settlement_data":
                _settlement_data[0] = cmd[1]
            elif tag == "phase":
                _phase[0] = cmd[1]
                if cmd[1] == "shop":          # 道具店：觸發由上而下滑入
                    _shop_slide_dir[0] = "in"
                    _shop_slide_t0[0]  = pygame.time.get_ticks()
                    _play_sfx("shop_open")
                elif cmd[1] == "char_create":
                    _request_bgm("Music-Aether.ogg")
                elif cmd[1] == "end":
                    # BGM 在此繼續播放，等到成績單畫面才淡出
                    _end_sub[0]              = "fade_out_1"
                    _end_t0[0]               = pygame.time.get_ticks()
                    _end_stamps_shown[0]     = 0
                    _stamp_shake_t0[0]       = 0
                    _ending_bgm_triggered[0] = False
                    _end_video_done[0]       = False
                    _end_video_surf[0]       = None
                    _end_bg_surf[0]          = None
                    _end_bg_fade_t0[0]       = 0
                    _end_bg_key[0]           = None
                    # 結局背景影片倒帶，以供下一局重新播放
                    for _rplayer in _end_bg_players.values():
                        if _rplayer is not None:
                            _rplayer.reset()
                elif cmd[1] == "gameover":
                    _request_bgm(None)
                    _play_sfx("game_over")
                    _go_sub[0]        = "fade_out"
                    _go_t0[0]         = pygame.time.get_ticks()
                    _go_silhouette[0] = None   # 重置剪影快取
                elif cmd[1] == "game" and _weather_type[0] is None:
                    _weather_reset()   # 首次進入遊戲階段時確保天氣已初始化
            elif tag == "ripple":
                _ripple_t0[0] = pygame.time.get_ticks()
                _play_sfx("cc_click")
            elif tag == "bgm_week":
                _request_bgm(_WEEK_BGM.get(cmd[1]))
                _request_week_bg(_WEEK_BG.get(cmd[1]))
                _weather_reset()   # 每週隨機切換天氣
            elif tag == "reset":
                _log.clear()
                _player[0] = None
                _mode[0] = None
                _choices.clear()
                _prompt[0] = ""
                _tvalue[0] = ""
                _scroll[0] = 0
                _composing[0] = ""
                _settlement_data[0] = None
                _request_bgm("Music-Morning_Rain.ogg")
            elif tag == "cc_name":
                _cc_mode[0]      = "name"
                _cc_data[0]      = tag
                _cc_tvalue[0]    = ""
                _cc_composing[0] = ""
                _cc_caret_pos[0] = 0
                pygame.key.start_text_input()
                # 告知 IME 輸入框位置，讓候選字清單出現在正確位置
                pygame.key.set_text_input_rect(pygame.Rect(
                    (WIN_W - 520) // 2 + 30 + _fs_off[0],
                    (WIN_H - 250) // 2 + 80 + _fs_off[1],
                    460, 42))
            elif tag == "cc_portrait":
                _cc_mode[0] = "portrait"
            elif tag == "cc_dept":
                _cc_mode[0] = "dept"
                _cc_data[0] = cmd[1]   # options list
            elif tag == "cc_drawbacks":
                _cc_mode[0] = "drawbacks"
                _cc_data[0] = cmd[1]   # drawbacks list
                _cc_sel.clear()
                _cc_btn_cache["drawbacks_max"] = cmd[2]
            elif tag == "cc_stats":
                _cc_mode[0]          = "stats"
                _cc_stat_total[0]    = cmd[1]
                _cc_stat_base[0]     = cmd[2] if len(cmd) > 2 else cmd[1]
                _cc_stat_talent[0]   = cmd[3] if len(cmd) > 3 else {}
                _cc_stat_de_level[0] = cmd[4] if len(cmd) > 4 else {}
                _cc_stat_vals[:]     = [10, 10, 10]
                _cc_stat_raw[:]      = ["10", "10", "10"]
                _cc_active_stat[0]   = None
            elif tag == "cc_extra":
                _cc_extra_data[:]  = cmd[1]
                _cc_extra_intel[0] = cmd[2]
                _cc_extra_sel.clear()
                _cc_extra_warn[0]  = 0
                _cc_mode[0]        = "extra"
            elif tag == "cc_slot":
                results = cmd[1]
                _slot_results[:] = results
                _slot_phase[:]   = ["idle", "idle", "idle"]
                _slot_stop_t[:]  = [0, 0, 0]
                _slot_start_t[:] = [0, 0, 0]
                _cc_confetti.clear()
                _cc_shake_end[0] = 0
                _cc_mode[0]      = "slot"
                # 第一槽立刻開始旋轉，並預算目標 offset
                _n_sp = len(_SLOT_SPIN_NAMES)
                _r0   = results[0]
                _nm0  = _r0.get("name", "") if _r0 else ""
                _ri0  = _SLOT_SPIN_NAMES.index(_nm0) if _nm0 in _SLOT_SPIN_NAMES else 0
                _slot_target_offsets[0] = (3 * _n_sp + (_ri0 - 1) % _n_sp) * 62
                _slot_phase[0]    = "spinning"
                _slot_start_t[0]  = pygame.time.get_ticks()
            elif tag == "cc_summary":
                _cc_summary_data[0] = cmd[1]
                _cc_mode[0]         = "summary"
            elif tag == "cc_de_level":
                _cc_mode[0] = "de_level"
                _cc_data[0] = cmd[1]   # levels list
                _cc_sel.clear()
            elif tag == "cc_talent":
                _cc_mode[0] = "talent"
                _cc_data[0] = cmd[1]   # candidates list
                _cc_sel.clear()
            elif tag == "set_time":
                new_time = cmd[1]
                # 時間有減少 → 觸發震動特效（每次扣時都閃）
                if new_time < _time_units[0]:
                    _time_shake_t0[0] = pygame.time.get_ticks()
                _time_units[0] = new_time
            elif tag == "time_overflow_warn":
                # 時間即將變負 → 震動 + damage6 音效
                _time_shake_t0[0] = pygame.time.get_ticks()
                _play_sfx("damage6")
            elif tag == "screen_shake":
                _evt_shake_t0[0] = pygame.time.get_ticks()
                _play_sfx("damage6")
            elif tag == "portrait_override":
                _portrait_override_key[0] = cmd[1]
            elif tag == "pregame_countdown":
                _info_modal_active[0] = False   # 確保資訊一覽不干擾
                _panel_slide_val[0]   = 1.0     # 立即完全收起面板（無動畫）
                _panel_slide_dir[0]   = "none"
                _pcd_active[0]        = True
                _pcd_phase[0]         = "msg"
                _pcd_t0[0]            = pygame.time.get_ticks()
            elif tag == "roll_call_set":
                _roll_call_course[0]   = cmd[1]
                _roll_call_attended[0] = False   # 新的點名週次，重置出席狀態
                _roll_call_xed[0]      = False
            elif tag == "roll_call_attended":
                _roll_call_attended[0] = cmd[1]
            elif tag == "roll_call_xed":
                _roll_call_xed[0] = cmd[1]
            elif tag == "roll_call_clear":
                _roll_call_course[0]   = ""
                _roll_call_attended[0] = False
                _roll_call_xed[0]      = False
            elif tag == "skip_popup_open":
                _skip_popup_active[0] = True
            elif tag == "special_disabled":
                _special_disabled.clear()
                _special_disabled.update(cmd[1])
            elif tag == "allnighter_count":
                _allnighter_count[0] = cmd[1]
            elif tag == "subj_popup":
                _subj_popup_title[0] = cmd[1]
                _subj_popup_opts.clear()
                _subj_popup_opts.extend(cmd[2])
                _subj_popup_rects.clear()
                _subj_popup_active[0] = True
            elif tag == "withdrawal_popup_open":
                _withdrawal_popup_active[0] = True
            elif tag == "timetable":
                _modal[0]      = "timetable"
                _modal_data[0] = cmd[1]   # courses list
            elif tag == "grade_report":
                _modal[0]      = "grade_report"
                _modal_data[0] = cmd[1]   # items list
                if len(cmd) > 2 and cmd[2]:
                    _play_sfx(cmd[2])
            elif tag == "story":
                _story_lines.clear()
                _story_lines.extend(cmd[1])
                _story_index[0] = 0
                _mode[0] = "story"
                # ── 觸發三側面板收起動畫 ─────────────────────────────
                _panel_slide_dir[0] = "out"
                _panel_slide_t0[0]  = pygame.time.get_ticks()
            elif tag == "exam_ready":
                _exam_ready_label[0] = cmd[1]
                _mode[0] = "exam_ready"
            elif tag == "exam_q":
                _choices.clear()
                _choices.extend(cmd[1])
                _mode[0] = "exam_q"
            elif tag == "shape_minigame":
                _smg_exam_type[0]      = cmd[1] if len(cmd) > 1 else "期中"
                _smg_active[0]         = True
                _smg_round[0]          = 1
                _smg_direction[0]      = -1
                _smg_t0[0]             = pygame.time.get_ticks()
                _smg_phase[0]          = random.choice(["circle", "cross"])
                _smg_phase_end_t[0]    = _smg_t0[0] + random.randint(8000, 12000)
                _smg_phase_flash_t[0]  = 0
                _smg_shapes.clear()
                _smg_tri_count[0]      = 0
                _smg_dia_count[0]      = 0
                _smg_correct_clicks[0] = 0
                _smg_wrong_clicks[0]   = 0
                _smg_spawn_budget[0]   = 20
                _smg_tri_budget[0]     = random.randint(7, 12)
                _smg_dia_budget[0]     = random.randint(7, 12)
                _smg_last_spawn_t[0]   = _smg_t0[0]
                _smg_next_spawn_dt[0]  = random.randint(700, 1100)
                _smg_round_scores[:]   = [0, 0]
                _smg_q_active[0]       = False
                _smg_q_answered[0]     = False
                _smg_r1_score_t0[0]    = 0
                _smg_final_score_t0[0] = 0
                _smg_phase_clearing[0] = False   # 確保 phase 清場旗標歸零
                _info_modal_active[0]  = False   # 確保資訊 modal 不會鎖住點擊
                _modal[0]              = None    # 確保課表/成績 modal 不會鎖住點擊
          except Exception as _cmd_e:
            import traceback as _tb
            print(f"[run_ui] cmd handler 例外（tag={cmd[0] if cmd else '?'}）: {_cmd_e}")
            _tb.print_exc()

        # ── 繪製（依畫面階段切換內容）────────────────────────
        # 全螢幕：先把黑邊區域鋪上背景圖（screen 是 real_screen 的子 Surface，
        # 遊戲內容隨後會正確疊在中央遊戲區域上）。
        if _is_fullscreen[0] and fs_bg_scaled is not None:
            real_screen.blit(fs_bg_scaled, (0, 0))

        btn_rects      = []
        start_btn      = None
        _debug_btn     = None
        _guide_btn     = None
        _guide_close_r = None
        _guide_prev_r  = None
        _guide_next_r  = None
        end_btn        = None
        go_btn         = None
        end_week_btn   = None
        shop_btn_rect  = None
        info_btn_rect  = None
        shop_buy_rects = []
        shop_exit_btn  = None

        if _phase[0] == "start":
            start_btn, _debug_btn, _guide_btn = _draw_start(screen, fm, fl, mpos)
            if _guide_active[0]:
                _guide_close_r, _guide_prev_r, _guide_next_r = \
                    _draw_guide_modal(screen, fm, fl, mpos)
        elif _phase[0] == "shop":
            # ── 計算道具店滑動偏移 ──────────────────────────────
            _sdir = _shop_slide_dir[0]
            _sel  = max(pygame.time.get_ticks() - _shop_slide_t0[0], 0)
            if _sdir == "in":
                _rt  = min(_sel / SHOP_SLIDE_MS, 1.0)
                _yoff = int(-WIN_H * (1.0 - _ease_out_quart(_rt)))
                if _rt >= 1.0:
                    _shop_slide_dir[0] = "none"
                    _yoff = 0
            elif _sdir == "out":
                _rt  = min(_sel / SHOP_SLIDE_MS, 1.0)
                _yoff = int(-WIN_H * _ease_in_cubic(_rt))
                if _rt >= 1.0:
                    _shop_slide_dir[0] = "out_done"
                    _shop_exit_ready[0] = True
            elif _sdir == "out_done":
                _yoff = -WIN_H   # 完全滑走，等待 phase 切換
            else:
                _yoff = 0

            if _sdir == "out_done":
                # 顯示遊戲底圖，等待相位切換為 "game"
                _draw_game_bg(screen)
                shop_buy_rects, shop_exit_btn = [], None
            elif _yoff != 0:
                # 動畫中：先畫遊戲底圖，再把道具店 Surface 蓋上並偏移
                _draw_game_bg(screen)
                _shop_tmp = pygame.Surface((WIN_W, WIN_H))
                shop_buy_rects, shop_exit_btn = _draw_shop(
                    _shop_tmp, fm, fs, fl, _shop_items, _player[0], (-1, -1))
                screen.blit(_shop_tmp, (0, _yoff))
            else:
                shop_buy_rects, shop_exit_btn = _draw_shop(
                    screen, fm, fs, fl, _shop_items, _player[0], mpos)
        elif _phase[0] == "end":
            end_btn = _draw_end(screen, fm, fs, mpos)
        elif _phase[0] == "gameover":
            go_btn = _draw_gameover(screen, fm, fs, mpos)
        elif _phase[0] == "char_create":
            cm = _cc_mode[0]
            if cm == "name":
                ok = _draw_cc_name(screen, fm, fs, mpos)
                _cc_btn_cache["name_ok"] = ok
            elif cm == "portrait":
                pcards = _draw_cc_portrait(screen, fm, fs, mpos)
                _cc_btn_cache["portrait_cards"] = pcards
            elif cm == "dept":
                drects = _draw_cc_dept(screen, fm, fs, _cc_data[0] or [], mpos)
                _cc_btn_cache["dept_cards"] = drects
            elif cm == "drawbacks":
                crects, ok = _draw_cc_drawbacks(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel,
                    _cc_btn_cache.get("drawbacks_max", 2), mpos)
                _cc_btn_cache["drawback_cards"] = crects
                _cc_btn_cache["drawbacks_ok"]   = ok
            elif cm == "stats":
                mr, pr, ok = _draw_cc_stats(
                    screen, fm, fs,
                    _cc_stat_total[0], _cc_stat_base[0], _cc_stat_talent[0],
                    _cc_stat_vals, _cc_stat_raw,
                    _cc_active_stat[0], mpos, _cc_stat_de_level[0])
                _cc_btn_cache["stats_minus"] = mr
                _cc_btn_cache["stats_plus"]  = pr
                _cc_btn_cache["stats_ok"]    = ok
            elif cm == "extra":
                crects, ok = _draw_cc_extra_events(screen, fm, fs, mpos)
                _cc_btn_cache["extra_cards"] = crects
                _cc_btn_cache["extra_ok"]    = ok
            elif cm == "slot":
                ok = _draw_cc_slot_machine(screen, fm, fs, mpos)
                _cc_btn_cache["slot_ok"] = ok
                # 天賦音效（由 _update_slot_state 設旗標，此處播放後清除）
                if _slot_sfx_pending[0]:
                    _play_sfx(_slot_sfx_pending[0])
                    _slot_sfx_pending[0] = ""
            elif cm == "summary":
                s_r, r_r = _draw_cc_summary(screen, fm, fs, mpos, game_mode=False)
                _cc_btn_cache["summary_start"]   = s_r
                _cc_btn_cache["summary_restart"] = r_r
            elif cm == "de_level":
                drects, ok = _draw_cc_de_level(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel[0] if _cc_sel else None, mpos)
                _cc_btn_cache["de_level_cards"] = drects
                _cc_btn_cache["de_level_ok"]    = ok
            elif cm == "talent":
                trects, ok = _draw_cc_talent(
                    screen, fm, fs,
                    _cc_data[0] or [], _cc_sel[0] if _cc_sel else None, mpos)
                _cc_btn_cache["talent_cards"] = trects
                _cc_btn_cache["talent_ok"]    = ok
            else:
                # 切換中的空白幀
                _draw_cc_bg(screen)
        else:   # "game"
            _draw_game_bg(screen)
            # ── 動態天氣特效（背景圖與 UI 之間）────────────────────
            _draw_weather(screen, pygame.time.get_ticks())

            # ── 面板滑動動畫計算（story 模式收起 / 解除後展開）──────
            _pdir = _panel_slide_dir[0]
            if _pdir != "none":
                _pel = max(pygame.time.get_ticks() - _panel_slide_t0[0], 0)
                _pt  = min(_pel / PANEL_SLIDE_MS, 1.0)
                if _pdir == "out":
                    _panel_slide_val[0] = _ease_in_cubic(_pt)
                    if _pt >= 1.0:
                        _panel_slide_dir[0] = "none"
                        _panel_slide_val[0] = 1.0
                elif _pdir == "in":
                    _panel_slide_val[0] = 1.0 - _ease_out_quart(_pt)
                    if _pt >= 1.0:
                        _panel_slide_dir[0] = "none"
                        _panel_slide_val[0] = 0.0
            # max：story 模式收折 vs. 玩家手動收折，取較大者驅動上/左/右面板
            pst = max(_panel_slide_val[0], _ap_collapse_val[0])

            # ── 底部行動面板折疊動畫 ──────────────────────────────────────
            _acdir = _ap_collapse_dir[0]
            if _acdir != "none":
                _acel = max(pygame.time.get_ticks() - _ap_collapse_t0[0], 0)
                _act  = min(_acel / AP_COLLAPSE_MS, 1.0)
                if _acdir == "out":
                    _ap_collapse_val[0] = _ease_in_cubic(_act)
                    if _act >= 1.0:
                        _ap_collapse_dir[0] = "none"
                        _ap_collapse_val[0] = 1.0
                elif _acdir == "in":
                    _ap_collapse_val[0] = 1.0 - _ease_out_quart(_act)
                    if _act >= 1.0:
                        _ap_collapse_dir[0] = "none"
                        _ap_collapse_val[0] = 0.0

            # 依 pst 計算各面板偏移量
            _SL_M    = _SIDE_PANEL_W + 20          # 足以完全移出畫面的距離
            _st_yoff = int(-STATUS_H * pst)        # 狀態欄：向上移出
            _ep_xoff = int(-_SL_M * pst)           # 左側面板：向左移出
            _gp_xoff = int( _SL_M * pst)           # 右側面板：向右移出

            # 狀態欄（依 y 偏移繪製）
            sr_shifted = pygame.Rect(0, _st_yoff, WIN_W, STATUS_H)
            shop_btn_rect, info_btn_rect = _draw_status_v2(
                screen, fm, fs, _player[0], sr_shifted, mpos)
            # 面板收起中禁止互動
            if pst > 0.0:
                shop_btn_rect = None
                info_btn_rect = None

            # 人物立繪區
            _draw_character_art(screen, cr)
            # 左側熟練度面板 / 右側成績記錄面板（依 x 偏移繪製）
            _draw_exp_panel(screen, fm, _font_micro[0], _player[0], x_offset=_ep_xoff)
            _draw_grade_panel(screen, fm, _font_micro[0], _player[0], x_offset=_gp_xoff)
            # 點名警示便利貼（隨成績面板同步右移）
            _draw_roll_call_note(screen, _font_micro[0], x_offset=_gp_xoff)
            # 非標準選項 / yn / event_ok → 需先計算，讓底部面板知道要不要留白
            _cp_active = (
                (_mode[0] == "choices" and bool(_choices)
                 and not all(c in _STANDARD_ACTIONS for c in _choices))
                or _mode[0] in ("yn", "event_ok", "exam_q")
            )
            # 底部行動面板：中央彈窗已啟用時改用空白選項，避免重複顯示
            _panel_mode    = "choices" if _cp_active else _mode[0]
            _panel_choices = []        if _cp_active else _choices
            # 全螢幕科目／翹課／停修彈窗，以及課表/成績公告 modal 開啟時，
            # 隱藏底部 log 避免透出雜訊（考試答題文案等不應出現在背景）
            _popup_hides_log = (
                _subj_popup_active[0]
                or _skip_popup_active[0]
                or _withdrawal_popup_active[0]
                or _modal[0] is not None   # 課表 / 成績公告 modal 背景靜音
            )
            _ap_yoff  = int(_ap_collapse_val[0] * ACTION_H)
            ar_drawn  = pygame.Rect(ar.x, ar.y + _ap_yoff, ar.width, ar.height)
            btn_rects, end_week_btn = _draw_action_panel(
                screen, fm, fs, _panel_mode, _panel_choices,
                [] if _popup_hides_log else _log,
                _prompt, _tvalue, ar_drawn, _time_units[0], mpos)
            # 考前壓力特效（邊框顫抖 + 底色微微泛紅）：疊在所有面板之上、彈窗之下
            _draw_exam_stress_fx(screen)
            # 低滿意度黑色暈圈遮罩（中央亮、外圍暗 + 雜訊）
            _draw_low_sat_vignette(screen, _player[0])
            # 生病狀態邊緣光暈（紅→藍→綠循環脈動，疊在黑色遮罩之上）
            _draw_sick_vignette(screen, _player[0])
            # 中央彈出視窗（yn / 非標準選項 / 考試題目）
            _draw_cp = (
                (_mode[0] == "choices" and bool(_choices)
                 and not all(c in _STANDARD_ACTIONS for c in _choices))
                or _mode[0] in ("yn", "exam_q")
            )
            if _draw_cp:
                _choice_popup_rects.clear()
                try:
                    _choice_popup_rects.extend(
                        _draw_choice_popup(screen, fm, fs, _mode[0], _choices,
                                           _log, _prompt[0], _yn_labels, mpos))
                except Exception as _e:
                    print(f"[DBG] _draw_choice_popup ERROR: {type(_e).__name__}: {_e}")
                    import traceback; traceback.print_exc()
            else:
                _choice_popup_rects.clear()
            # 行動結果彈出視窗（上方由上而下滑入，畫在考試遮罩之上）
            _draw_action_popup(screen, fs)
            # 突發事件通知彈窗（單按鈕，最上層）
            if _mode[0] == "event_ok":
                _event_ok_popup_rects.clear()
                try:
                    _event_ok_popup_rects.extend(
                        _draw_event_ok_popup(screen, fm, fs, mpos))
                except Exception as _e:
                    print(f"[DBG] _draw_event_ok_popup ERROR: {type(_e).__name__}: {_e}")
                    import traceback; traceback.print_exc()
            else:
                _event_ok_popup_rects.clear()
            # 翹課選課彈出視窗（蓋在所有遊戲 UI 之上）
            if _skip_popup_active[0]:
                _skip_popup_rects.clear()
                _skip_popup_rects.extend(
                    _draw_skip_class_popup(screen, fm, fs, mpos))
            # 科目選擇彈出視窗（中央 modal，蓋在所有遊戲 UI 之上）
            if _subj_popup_active[0]:
                _subj_popup_rects.clear()
                _subj_popup_rects.extend(
                    _draw_subj_popup(screen, fm, fs, mpos))
            # 停修選課彈出視窗（蓋在所有遊戲 UI 之上）
            if _withdrawal_popup_active[0]:
                _withdrawal_popup_rects.clear()
                _withdrawal_popup_rects.extend(
                    _draw_withdrawal_popup(screen, fm, fs, mpos))

        # ── 玩家資訊一覽 modal（遊戲中查閱，浮在所有畫面之上）─────
        if _phase[0] == "game" and _info_modal_active[0]:
            _close_r, _ = _draw_cc_summary(screen, fm, fs, mpos, game_mode=True)
            _info_modal_close[0] = _close_r

        # ── 遊戲說明 modal（start phase 以外時在此渲染，浮在最上層）─
        # start phase 時已在 _draw_start 塊中渲染，此處處理其他 phase
        if _guide_active[0] and _phase[0] != "start":
            _guide_close_r, _guide_prev_r, _guide_next_r = \
                _draw_guide_modal(screen, fm, fl, mpos)

        # ── Modal 疊加（課表 / 成績公告，浮在所有畫面之上）────────
        _modal_ok_btn = None
        if _modal[0] == "timetable":
            try:
                _modal_ok_btn = _draw_modal_timetable(
                    screen, fm, fs, _modal_data[0] or [], mpos)
            except Exception as _e:
                print(f"[DBG] _draw_modal_timetable ERROR: {type(_e).__name__}: {_e}")
                import traceback; traceback.print_exc()
        elif _modal[0] == "grade_report":
            try:
                _modal_ok_btn = _draw_modal_grade(
                    screen, fm, fl, fs, _modal_data[0] or [], mpos)
            except Exception as _e:
                print(f"[DBG] _draw_modal_grade ERROR: {type(_e).__name__}: {_e}")

        # ── 全螢幕切換按鈕（全螢幕模式下隱藏；非全螢幕時右下角常駐）──
        if not _is_fullscreen[0]:
            _fs_hover = fs_btn.collidepoint(mpos)
            _fs_bg    = (110, 80, 50) if _fs_hover else (70, 50, 32)
            pygame.draw.rect(screen, _fs_bg, fs_btn, border_radius=8)
            pygame.draw.rect(screen, CYAN, fs_btn, 1, border_radius=8)
        # 繪製展開圖示（非全螢幕才顯示）
        if not _is_fullscreen[0]:
            _ix = fs_btn.x + 7
            _iy = fs_btn.y + 7
            _iw = fs_btn.width  - 14
            _ih = fs_btn.height - 14
            _a  = 7
            _ic = PANEL
            # 展開圖示：L 形箭頭指向四角外側
            pygame.draw.line(screen, _ic, (_ix,         _iy),        (_ix+_a,      _iy),            2)
            pygame.draw.line(screen, _ic, (_ix,         _iy),        (_ix,         _iy+_a),         2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy),        (_ix+_iw-_a,  _iy),            2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy),        (_ix+_iw,     _iy+_a),         2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_ih),    (_ix+_a,      _iy+_ih),        2)
            pygame.draw.line(screen, _ic, (_ix,         _iy+_ih),    (_ix,         _iy+_ih-_a),     2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_ih),    (_ix+_iw-_a,  _iy+_ih),       2)
            pygame.draw.line(screen, _ic, (_ix+_iw,     _iy+_ih),    (_ix+_iw,     _iy+_ih-_a),    2)

        # ── 考場倒數動畫覆蓋層（形狀小遊戲前，蓋在所有遊戲 UI 之上）──
        if _pcd_active[0]:
            _pcd_done = _draw_pregame_countdown(screen, fm, pygame.time.get_ticks())
            if _pcd_done:
                _pcd_active[0]  = False
                _reply_val[0]   = True
                _reply_ready[0] = True

        # ── 形狀小遊戲覆蓋層（優先蓋過所有遊戲 UI）────────────
        if _smg_active[0]:
            _draw_shape_minigame(screen, fm, fs, fm, mpos, _dt_ms)

        # ── 漣漪轉場覆蓋層（最頂層，疊在所有內容之上）──────────
        _draw_ripple_overlay(screen)

        # ── 行動成功白光閃爍（漣漪之上，點擊波紋之下）──────────
        _draw_action_flash(screen, pygame.time.get_ticks())

        # ── 點擊波紋特效（最最頂層，覆蓋一切 UI）──────────────
        _draw_click_effects(screen, pygame.time.get_ticks())

        # ── 突發事件全螢幕震動（最後一步，copy+blit 整張畫面偏移）──
        _sdx, _sdy = _get_evt_shake_offset()
        if _sdx != 0 or _sdy != 0:
            _shk_copy = screen.copy()
            screen.fill((0, 0, 0))
            screen.blit(_shk_copy, (_sdx, _sdy))

        # ── 印章晃動（成績單專用，幅度較輕）────────────────────
        _ssx, _ssy = _get_stamp_shake_offset()
        if _ssx != 0 or _ssy != 0:
            _shk_copy2 = screen.copy()
            screen.fill((248, 238, 220))
            screen.blit(_shk_copy2, (_ssx, _ssy))

        # ── 按鈕 hover 音效（首次進入時播放一次）────────────────
        _curr_hov_btns = {k for k, v in _anim_hover.items() if v > 0}
        if _curr_hov_btns - _prev_hov_btns:
            _play_sfx("hover")
        _prev_hov_btns = _curr_hov_btns

        # ── 自訂游標（所有層最頂端，不受震動偏移影響）──────────
        if _cursor_normal is not None:
            _cur_img = _cursor_pressed if pygame.mouse.get_pressed()[0] else _cursor_normal
            # 筆尖奶茶色光球（畫在游標之下，中心對齊筆尖）
            if _cursor_gball is not None:
                screen.blit(_cursor_gball,
                            (mpos[0] - _cursor_gball_r,
                             mpos[1] - _cursor_gball_r))
            screen.blit(_cur_img, (mpos[0] - _cursor_glow_pad,
                                   mpos[1] - _cur_img.get_height() + _cursor_glow_pad))

        pygame.display.flip()

        # ── IME 組字中方向鍵偵測（Windows 限定：GetAsyncKeyState 輪詢）────────
        if (_phase[0] == "char_create" and _cc_mode[0] == "name"
                and _cc_composing[0] and sys.platform == "win32"):
            try:
                import ctypes
                _left_now  = bool(ctypes.windll.user32.GetAsyncKeyState(0x25) & 0x8000)
                _right_now = bool(ctypes.windll.user32.GetAsyncKeyState(0x27) & 0x8000)
                _triggered = None
                if _left_now and not _ime_arrow_prev["left"]:
                    _triggered = "left"
                elif _right_now and not _ime_arrow_prev["right"]:
                    _triggered = "right"
                _ime_arrow_prev["left"]  = _left_now
                _ime_arrow_prev["right"] = _right_now
                if _triggered:
                    # 移動游標（在已確認文字範圍內）
                    # 到達邊界時不 commit 組字，只壓制 TEXTEDITING 讓虛線保持可見
                    if _triggered == "left":
                        _cc_caret_pos[0] = max(0, _cc_caret_pos[0] - 1)
                    else:
                        _cc_caret_pos[0] = min(len(_cc_tvalue[0]), _cc_caret_pos[0] + 1)
                    # 壓制 IME 回傳的 TEXTEDITING，避免它把 _cc_composing 清空
                    _ime_cancel_frames[0] = 3
            except Exception:
                pass
        else:
            _ime_arrow_prev["left"]  = False
            _ime_arrow_prev["right"] = False
        if _ime_cancel_frames[0] > 0:
            _ime_cancel_frames[0] -= 1

        # ── pygame 事件 ───────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # 點擊波紋特效（任何畫面均觸發，無條件生成）
                _click_spawn(_tpos(ev.pos)[0], _tpos(ev.pos)[1], pygame.time.get_ticks())

                # 全螢幕切換按鈕
                import sys as _sys_fs
                if fs_btn.collidepoint(_tpos(ev.pos)):
                    if _sys_fs.platform == "emscripten":
                        # WASM：全螢幕由 JS canvas click listener 處理（user gesture 要求）
                        # requestFullscreen() 必須在 JS event handler 內同步呼叫，
                        # Python window.eval() 呼叫時已超出 user gesture 時間窗 → 無效。
                        # 狀態由 fullscreenchange → /tmp/__fs_state.txt → Python 每幀讀取同步。
                        pass  # JS 已處理，Python 只需 continue
                    else:
                        # 桌面：用 pygame display mode
                        if _is_fullscreen[0]:
                            screen = pygame.display.set_mode((WIN_W, WIN_H))
                            real_screen  = screen
                            fs_bg_scaled = None
                            _fs_off[0] = _fs_off[1] = 0
                            _is_fullscreen[0] = False
                        else:
                            real_screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                            _rw, _rh = real_screen.get_size()
                            _gx = max(0, (_rw - WIN_W) // 2)
                            _gy = max(0, (_rh - WIN_H) // 2)
                            _fs_off[0], _fs_off[1] = _gx, _gy
                            screen = real_screen.subsurface(
                                pygame.Rect(_gx, _gy, WIN_W, WIN_H))
                            if _outside_bg_raw is not None:
                                fs_bg_scaled = pygame.transform.scale(
                                    _outside_bg_raw, (_rw, _rh))
                            else:
                                fs_bg_scaled = None
                            _is_fullscreen[0] = True
                    continue

                # ── Modal 優先攔截（課表 / 成績公告）────────────
                if _modal[0] is not None:
                    if _modal_ok_btn and _modal_ok_btn.collidepoint(_tpos(ev.pos)):
                        _modal[0]      = None
                        _modal_data[0] = None
                        _modal_ready[0] = True
                    continue   # modal 開著時不處理底層按鈕

                # ── 遊戲中資訊一覽 modal 攔截 ────────────────────
                if _phase[0] == "game" and _info_modal_active[0]:
                    close_r = _info_modal_close[0]
                    if close_r and close_r.collidepoint(_tpos(ev.pos)):
                        _play_sfx("back")
                        _info_modal_active[0] = False
                    continue   # modal 開著時攔截所有點擊

                # ── 遊戲中「資訊一覽」按鈕開啟 modal ────────────
                # 小遊戲進行中禁止開啟（形狀可能覆蓋按鈕，誤觸會鎖住所有點擊）
                if _phase[0] == "game" and not _smg_active[0] \
                        and info_btn_rect is not None \
                        and info_btn_rect.collidepoint(_tpos(ev.pos)):
                    _play_sfx("ui_click")
                    player = _player[0]
                    if player is not None:
                        from character import EXTRA_EVENTS as _EXTRA_EVTS
                        _cc_summary_data[0] = {
                            "name":            player.name,
                            "department":      player.department,
                            "de_level":        player.de_level,
                            "stamina":         player.stamina_max,
                            "intel":           player.intel,
                            "luck":            player.luck,
                            "money":           player.money,
                            "combined_talent": player.talent,
                            "slot_results":    getattr(player, "slot_results", []),
                            "drawbacks":       player.drawbacks,
                            "extra_ev_ids":    player.extra_events,
                            "extra_ev_data":   list(_EXTRA_EVTS),
                        }
                        _info_modal_active[0] = True
                    continue

                # ── 遊戲說明 modal 通用點擊（start 以外的 phase）────────
                # start phase 的 guide 點擊在下方的 start 區塊處理
                if _guide_active[0] and _phase[0] != "start":
                    if _guide_close_r and _guide_close_r.collidepoint(_tpos(ev.pos)):
                        _play_sfx("back")
                        _guide_active[0] = False
                    elif _guide_prev_r and _guide_prev_r.collidepoint(_tpos(ev.pos)):
                        _play_sfx("ui_click")
                        _guide_page[0] = max(0, _guide_page[0] - 1)
                    elif _guide_next_r and _guide_next_r.collidepoint(_tpos(ev.pos)):
                        _play_sfx("ui_click")
                        _guide_page[0] = min(_GUIDE_N - 1, _guide_page[0] + 1)
                    continue   # 點擊不穿透到底層 UI

                if _phase[0] == "start":
                    if _guide_active[0]:
                        if _guide_close_r and _guide_close_r.collidepoint(_tpos(ev.pos)):
                            _play_sfx("back")
                            _guide_active[0] = False
                        elif _guide_prev_r and _guide_prev_r.collidepoint(_tpos(ev.pos)):
                            _play_sfx("ui_click")
                            _guide_page[0] = max(0, _guide_page[0] - 1)
                        elif _guide_next_r and _guide_next_r.collidepoint(_tpos(ev.pos)):
                            _play_sfx("ui_click")
                            _guide_page[0] = min(_GUIDE_N - 1, _guide_page[0] + 1)
                    elif start_btn and start_btn.collidepoint(_tpos(ev.pos)):
                        _play_sfx("start_click")
                        _click_reg[(start_btn.centerx, start_btn.centery)] = pygame.time.get_ticks()
                        _phase[0] = "game"
                        _start_ready[0] = True
                    elif _debug_btn and _debug_btn.collidepoint(_tpos(ev.pos)):
                        _play_sfx("ui_click")
                        _phase[0] = "game"
                        _debug_skip_ready[0] = True
                        _start_ready[0] = True
                    elif _guide_btn and _guide_btn.collidepoint(_tpos(ev.pos)):
                        _play_sfx("ui_click")
                        _guide_active[0] = True
                        _guide_page[0]   = 0
                elif _phase[0] == "shop":
                    # 離開按鈕：僅在靜止狀態（非動畫中）才響應
                    if (shop_exit_btn and shop_exit_btn.collidepoint(_tpos(ev.pos))
                            and _shop_slide_dir[0] == "none"):
                        _play_sfx("back")
                        _click_reg[(shop_exit_btn.centerx, shop_exit_btn.centery)] = pygame.time.get_ticks()
                        # 觸發由下而上滑出動畫，動畫結束後才設定 exit event
                        _shop_slide_dir[0] = "out"
                        _shop_slide_t0[0]  = pygame.time.get_ticks()
                    else:
                        # 購買按鈕
                        for (br, idx) in shop_buy_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _apply_shop_purchase(idx)
                                break
                elif _phase[0] == "char_create":
                    # 能力點 +/- 按鈕使用 poka 音效；其他創角操作使用 cc_click
                    if _cc_mode[0] == "stats":
                        _is_stat_btn = False
                        for _sr in (_cc_btn_cache.get("stats_minus") or []):
                            if _sr.collidepoint(_tpos(ev.pos)):
                                _is_stat_btn = True; break
                        if not _is_stat_btn:
                            for _sr in (_cc_btn_cache.get("stats_plus") or []):
                                if _sr.collidepoint(_tpos(ev.pos)):
                                    _is_stat_btn = True; break
                        _play_sfx("ui_click" if _is_stat_btn else "cc_click")
                    else:
                        _play_sfx("cc_click")
                    _handle_cc_action(_tpos(ev.pos))
                elif _phase[0] == "end":
                    if end_btn and end_btn.collidepoint(_tpos(ev.pos)):
                        _play_sfx("start_click")
                        _click_reg[(end_btn.centerx, end_btn.centery)] = pygame.time.get_ticks()
                        _phase[0] = "start"
                        _request_bgm("Music-Morning_Rain.ogg")
                        _restart_ready[0] = True
                elif _phase[0] == "gameover":
                    if go_btn and go_btn.collidepoint(_tpos(ev.pos)):
                        _play_sfx("start_click")
                        _click_reg[(go_btn.centerx, go_btn.centery)] = pygame.time.get_ticks()
                        _phase[0] = "start"
                        _request_bgm("Music-Morning_Rain.ogg")
                        _restart_ready[0] = True
                else:
                    # ── 遊戲中 ────────────────────────────────

                    # 形狀小遊戲優先攔截（蓋過所有遊戲 UI）
                    if _smg_active[0]:
                        # ── 最終分數畫面：只響應「確認」按鈕 ─────────
                        if _smg_final_score_t0[0] > 0:
                            ok_rect = _smg_final_ok_rect[0]
                            if ok_rect and ok_rect.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click")
                                total = _smg_round_scores[0] + _smg_round_scores[1]
                                _smg_active[0]         = False
                                _smg_final_score_t0[0] = 0
                                _smg_final_ok_rect[0]  = None
                                _reply_val[0]          = total / 200.0
                                _reply_ready[0] = True
                            continue   # 最終分數畫面攔截所有點擊
                        if _smg_q_active[0]:
                            if not _smg_q_answered[0]:   # 防止重複點擊
                                for br, val in _smg_q_rects:
                                    if br.collidepoint(_tpos(ev.pos)):
                                        _play_sfx("ui_click")
                                        mem_score = 20 if val == _smg_q_correct[0] else 0
                                        pv = 80 / 20
                                        click_score = max(
                                            0.0,
                                            _smg_correct_clicks[0] * pv
                                            - _smg_wrong_clicks[0] * pv,
                                        )
                                        _smg_round_scores[_smg_round[0] - 1] = min(100, int(click_score + mem_score))
                                        _smg_q_ans_correct[0] = (val == _smg_q_correct[0])
                                        _smg_q_ans_t0[0]      = pygame.time.get_ticks()
                                        _smg_q_answered[0]    = True
                                        # 回合轉換由 _draw_shape_minigame 計時 1.5s 後處理
                                        break
                        else:
                            for s in _smg_shapes:
                                if not s["alive"]:
                                    continue
                                if shape_rect(s).collidepoint(_tpos(ev.pos)):
                                    s["alive"] = False
                                    is_target = (
                                        (s["type"] == "circle" and _smg_phase[0] == "circle")
                                        or (s["type"] == "cross" and _smg_phase[0] == "cross")
                                    )
                                    if is_target:
                                        _smg_correct_clicks[0] += 1
                                        _play_sfx("talent_none")
                                    else:
                                        _smg_wrong_clicks[0] += 1
                                        _play_sfx("damage6")
                                    break
                        continue   # 小遊戲中攔截所有底層點擊

                    # 劇情對話框：任意點擊推進（優先級次於突發事件彈窗）
                    if _mode[0] == "story":
                        _play_sfx("ui_click")
                        _story_index[0] += 1
                        if _story_index[0] >= len(_story_lines):
                            _mode[0] = None
                            _reply_ready[0] = True
                            # ── 觸發三側面板展開動畫 ────────────────────────
                            _panel_slide_dir[0] = "in"
                            _panel_slide_t0[0]  = pygame.time.get_ticks()
                        continue

                    # 突發事件彈窗優先攔截（最高優先）
                    if _mode[0] == "event_ok":
                        for (br, _) in _event_ok_popup_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _reply_val[0] = True
                                _mode[0] = None
                                _event_ok_popup_rects.clear()
                                _event_ok_border_color[0] = None
                                _event_ok_btn_label[0]    = "確認"
                                _reply_ready[0] = True
                                break
                        continue   # 彈窗開啟時阻擋所有點擊

                    # 非標準選項 / yn / 考試題目 中央彈窗優先攔截（最高優先）
                    _cp_now = (
                        (_mode[0] == "choices" and bool(_choices)
                         and not all(c in _STANDARD_ACTIONS for c in _choices))
                        or _mode[0] in ("yn", "exam_q")
                    )
                    if _cp_now:
                        for (br, val) in _choice_popup_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                if _mode[0] == "choices":
                                    _play_sfx("ui_click")
                                    _reply_val[0] = val
                                    _mode[0] = None
                                    _choices.clear()
                                    _reply_ready[0] = True
                                elif _mode[0] == "exam_q":
                                    _play_sfx("ui_click")
                                    _reply_val[0] = val
                                    _mode[0] = None
                                    _choices.clear()
                                    _exam_q_prompt[0] = ""
                                    _reply_ready[0] = True
                                else:  # yn
                                    _play_sfx("ui_click" if val else "back")
                                    _reply_val[0] = val
                                    _mode[0] = None
                                    _reply_ready[0] = True
                                break
                        continue   # 彈窗開啟時所有點擊都不透傳

                    # 翹課選課 popup 優先攔截所有點擊
                    if _skip_popup_active[0]:
                        for (br, val) in _skip_popup_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click" if val is not None else "back")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _skip_popup_result[0] = val
                                _skip_popup_active[0] = False
                                _skip_popup_rects.clear()
                                _skip_popup_ready[0] = True
                                break
                        continue   # 無論有沒有點中按鈕，都不透傳到下方邏輯

                    # 科目選擇 popup 優先攔截所有點擊
                    if _subj_popup_active[0]:
                        for (br, val) in _subj_popup_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _reply_val[0] = val
                                _subj_popup_active[0] = False
                                _subj_popup_opts.clear()
                                _subj_popup_rects.clear()
                                _reply_ready[0] = True
                                break
                        continue   # 無論有沒有點中按鈕，都不透傳到下方邏輯

                    # 停修選課 popup 優先攔截所有點擊
                    if _withdrawal_popup_active[0]:
                        for (br, val) in _withdrawal_popup_rects:
                            if br.collidepoint(_tpos(ev.pos)):
                                _play_sfx("ui_click")
                                _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                                _reply_val[0] = val
                                _withdrawal_popup_active[0] = False
                                _withdrawal_popup_opts.clear()
                                _withdrawal_popup_rects.clear()
                                _reply_ready[0] = True
                                break
                        continue   # 無論有沒有點中按鈕，都不透傳到下方邏輯

                    # ── 底部行動面板折疊/展開 toggle ─────────────────────
                    if (_ap_toggle_rect[0] is not None
                            and _ap_toggle_rect[0].collidepoint(_tpos(ev.pos))):
                        _play_sfx("ui_click")
                        if _ap_collapse_val[0] < 0.5:
                            _ap_collapse_dir[0] = "out"
                        else:
                            _ap_collapse_dir[0] = "in"
                        _ap_collapse_t0[0] = pygame.time.get_ticks()
                        continue

                    # 狀態欄道具店按鈕（僅在行動選單時有效）
                    if (shop_active
                            and shop_btn_rect is not None
                            and shop_btn_rect.collidepoint(_tpos(ev.pos))):
                        _play_sfx("ui_click")
                        _click_reg[(shop_btn_rect.centerx, shop_btn_rect.centery)] = pygame.time.get_ticks()
                        shop_idx = next(
                            (i + 1 for i, c in enumerate(_choices)
                             if c == "🏪 前往道具店"), None)
                        if shop_idx is not None:
                            _reply_val[0] = shop_idx
                            _mode[0] = None
                            _choices.clear()
                            _reply_ready[0] = True
                        continue

                    # 結束本週按鈕（回傳 0）
                    if (_mode[0] == "choices"
                            and end_week_btn is not None
                            and end_week_btn.collidepoint(_tpos(ev.pos))):
                        _play_sfx("back")
                        _click_reg[(end_week_btn.centerx, end_week_btn.centery)] = pygame.time.get_ticks()
                        _reply_val[0] = 0
                        _mode[0] = None
                        _choices.clear()
                        _time_units[0] = 0
                        _reply_ready[0] = True
                        continue

                    # 行動按鈕 / yn / text 確認
                    for (br, val) in btn_rects:
                        if br.collidepoint(_tpos(ev.pos)):
                            _click_reg[(br.centerx, br.centery)] = pygame.time.get_ticks()
                            if _mode[0] == "text" and val == "__ok__":
                                _play_sfx("ui_click")
                                _reply_val[0] = _tvalue[0]
                                _mode[0] = None
                                _composing[0] = ""
                                pygame.key.stop_text_input()
                                _reply_ready[0] = True
                            elif _mode[0] in ("choices", "yn"):
                                # 決定音效
                                if _mode[0] == "choices":
                                    if isinstance(val, int) and val < 0:
                                        # 進食（val == -3）且金錢不足 → 不播 action 音效
                                        # （由 show_action_blocked 負責播放 damage6）
                                        _sa_name = (
                                            _SPECIAL_ACTION_NAMES[(-val) - 1]
                                            if 1 <= (-val) <= len(_SPECIAL_ACTION_NAMES)
                                            else ""
                                        )
                                        _eat_money_blocked = (
                                            _sa_name == "進食"
                                            and _player[0] is not None
                                            and _player[0].money < 50
                                        )
                                        if not _eat_money_blocked:
                                            _play_sfx("action")
                                    else:
                                        _cname = (_choices[val - 1]
                                                  if isinstance(val, int) and 1 <= val <= len(_choices)
                                                  else "")
                                        _play_sfx("action" if _cname in _STANDARD_ACTIONS
                                                              and _cname != "🏪 前往道具店"
                                                  else "ui_click")
                                else:  # yn
                                    _play_sfx("ui_click" if val else "back")
                                _reply_val[0] = val
                                _mode[0] = None
                                _choices.clear()
                                _reply_ready[0] = True
                            elif _mode[0] == "exam_ready":
                                _play_sfx("ui_click")
                                _reply_val[0] = val
                                _mode[0] = None
                                _exam_ready_label[0] = ""
                                _reply_ready[0] = True

                    # 若點到停用中的特殊行動按鈕（cooldown 中），播放 damage6
                    for _dsr in (_cc_btn_cache.get("sp_disabled_rects") or []):
                        if _dsr.collidepoint(_tpos(ev.pos)):
                            _play_sfx("damage6")
                            break

            elif ev.type == pygame.MOUSEWHEEL:
                # 道具店商品格捲動（向上滾 = 往下看更多商品）
                if _phase[0] == "shop":
                    _shop_scroll_y[0] = max(0, _shop_scroll_y[0] - ev.y * 38)

            elif ev.type == pygame.TEXTEDITING:
                # 輸入法組字中（例如注音還沒按確認）：只更新預覽，不寫入正文
                if _phase[0] == "char_create" and _cc_mode[0] == "name":
                    if _ime_cancel_frames[0] > 0:
                        pass   # 忽略強制取消 IME 後的殘留 TEXTEDITING 事件
                    else:
                        _cc_composing[0] = ev.text
                elif _mode[0] == "text":
                    _composing[0] = ev.text

            elif ev.type == pygame.TEXTINPUT:
                # 輸入法確認（或直接打英數）：寫入正文，清除組字預覽
                if _phase[0] == "char_create" and _cc_mode[0] == "name":
                    _p = _cc_caret_pos[0]
                    _cc_tvalue[0]    = _cc_tvalue[0][:_p] + ev.text + _cc_tvalue[0][_p:]
                    _cc_caret_pos[0] = _p + len(ev.text)
                    _cc_composing[0] = ""
                elif _mode[0] == "text":
                    _tvalue[0] += ev.text
                    _composing[0] = ""

            elif ev.type == pygame.KEYDOWN:
                # ESC：全螢幕模式下退出全螢幕
                if ev.key == pygame.K_ESCAPE and _is_fullscreen[0]:
                    import sys as _sys_esc
                    if _sys_esc.platform != "emscripten":
                        # 桌面：pygame 直接管理全螢幕模式
                        screen = pygame.display.set_mode((WIN_W, WIN_H))
                        real_screen  = screen
                        fs_bg_scaled = None
                        _fs_off[0] = _fs_off[1] = 0
                        _is_fullscreen[0] = False
                    # WASM：瀏覽器 ESC → fullscreenchange 事件 → 寫 /tmp/__fs_exit.txt
                    # 狀態更新由上方 FS exit 偵測區處理，此處不呼叫 pygame.display.set_mode
                elif _phase[0] == "char_create":
                    if _cc_mode[0] == "name":
                        _ime_rect = pygame.Rect(
                            (WIN_W - 520) // 2 + 30 + _fs_off[0],
                            (WIN_H - 250) // 2 + 80 + _fs_off[1],
                            460, 42)
                        if ev.key == pygame.K_RETURN:
                            _cc_reply_val[0] = _cc_tvalue[0] + _cc_composing[0]
                            _cc_composing[0] = ""
                            _cc_mode[0] = ""
                            pygame.key.stop_text_input()
                            _cc_reply_ready[0] = True
                        elif ev.key == pygame.K_BACKSPACE:
                            if _cc_composing[0]:
                                _cc_composing[0] = ""
                            elif _cc_caret_pos[0] > 0:
                                _p = _cc_caret_pos[0]
                                _cc_tvalue[0]    = _cc_tvalue[0][:_p - 1] + _cc_tvalue[0][_p:]
                                _cc_caret_pos[0] = _p - 1
                        elif ev.key == pygame.K_DELETE:
                            if not _cc_composing[0]:
                                _p = _cc_caret_pos[0]
                                if _p < len(_cc_tvalue[0]):
                                    _cc_tvalue[0] = _cc_tvalue[0][:_p] + _cc_tvalue[0][_p + 1:]
                        elif ev.key == pygame.K_LEFT:
                            if _cc_composing[0]:   # 組字中：先取消組字再移動
                                _cc_composing[0] = ""
                                pygame.key.stop_text_input()
                                pygame.key.start_text_input()
                                pygame.key.set_text_input_rect(_ime_rect)
                            _cc_caret_pos[0] = max(0, _cc_caret_pos[0] - 1)
                        elif ev.key == pygame.K_RIGHT:
                            if _cc_composing[0]:   # 組字中：先取消組字再移動
                                _cc_composing[0] = ""
                                pygame.key.stop_text_input()
                                pygame.key.start_text_input()
                                pygame.key.set_text_input_rect(_ime_rect)
                            _cc_caret_pos[0] = min(len(_cc_tvalue[0]), _cc_caret_pos[0] + 1)
                        elif ev.key == pygame.K_HOME:
                            if not _cc_composing[0]:
                                _cc_caret_pos[0] = 0
                        elif ev.key == pygame.K_END:
                            if not _cc_composing[0]:
                                _cc_caret_pos[0] = len(_cc_tvalue[0])
                        elif ev.key == pygame.K_ESCAPE:
                            # ESC：強制重置輸入法，從候選字卡住狀態脫困
                            _cc_composing[0] = ""
                            pygame.key.stop_text_input()
                            pygame.key.start_text_input()
                            pygame.key.set_text_input_rect(_ime_rect)
                        elif ev.key in (pygame.K_DOWN, pygame.K_UP):
                            if _cc_composing[0]:
                                # ↓↑ 在組字中會觸發候選字模式，卡住後續按鍵
                                _cc_composing[0] = ""
                                pygame.key.stop_text_input()
                                pygame.key.start_text_input()
                                pygame.key.set_text_input_rect(_ime_rect)
                    elif _cc_mode[0] == "stats":
                        ai = _cc_active_stat[0]
                        if ai is not None:
                            digit = None
                            if pygame.K_0 <= ev.key <= pygame.K_9:
                                digit = ev.key - pygame.K_0
                            elif pygame.K_KP0 <= ev.key <= pygame.K_KP9:
                                digit = ev.key - pygame.K_KP0
                            if digit is not None:
                                new_raw = _cc_stat_raw[ai] + str(digit)
                                try:
                                    v = int(new_raw)
                                    other = sum(_cc_stat_vals) - _cc_stat_vals[ai]
                                    if 0 <= v <= _cc_stat_total[0] - other:
                                        _cc_stat_vals[ai] = v
                                        _cc_stat_raw[ai]  = new_raw
                                except ValueError:
                                    pass
                            elif ev.key == pygame.K_BACKSPACE:
                                new_raw = _cc_stat_raw[ai][:-1]
                                _cc_stat_raw[ai] = new_raw
                                try:
                                    _cc_stat_vals[ai] = int(new_raw) if new_raw else 0
                                except ValueError:
                                    _cc_stat_vals[ai] = 0
                elif _mode[0] == "text":
                    if ev.key == pygame.K_RETURN:
                        _reply_val[0] = _tvalue[0]
                        _mode[0] = None
                        _composing[0] = ""
                        pygame.key.stop_text_input()
                        _reply_ready[0] = True
                    elif ev.key == pygame.K_BACKSPACE:
                        if _composing[0]:
                            _composing[0] = ""  # 先清組字預覽
                        else:
                            _tvalue[0] = _tvalue[0][:-1]

        await asyncio.sleep(0)   # yield #1：讓瀏覽器跑 onaudioprocess / 其他 task
        clock.tick(30)
        # yield #2（WASM only）：clock.tick 結束後再讓一次，確保 ScriptProcessorNode
        # 在下一幀渲染開始前還有機會填滿 audio buffer，減少 underrun 失真。
        if sys.platform == "emscripten":
            await asyncio.sleep(0)

    pygame.quit()
    if sys.platform != "emscripten":
        sys.exit()

