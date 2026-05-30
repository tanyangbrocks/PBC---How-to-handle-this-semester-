# ============================================================
#  主程式：如何渡過這學期？（pygame 版）
# ============================================================
# 與 main_origin.py 的差異：
#   - 遊戲邏輯包進 game_main()，跑在背景執行緒
#   - 主執行緒交給 ui.run_ui() 跑 pygame 事件迴圈
#   - print() 改為 ui.notify()；display_status 改為 ui.set_player()
# ============================================================

import asyncio
import random
import pygame   # 必須在 main.py 直接 import，讓 pygbag 偵測到需要預載 pygame WebAssembly
# numpy 在 pygbag 的 emscripten 環境不相容（僅支援 Pyodide wheel），已移除
# 漣漪特效在 WASM 使用純 pygame 的 rings 退回版

import ui
from ui import notify_gameover
from character import Character, TALENTS, DRAWBACKS, DE_LEVELS
from turn_engine import TurnEngine
from event_system import EventSystem
from skill_system import SkillSystem
from shop_V03 import Shop

# ── DEV 模式開關 ────────────────────────────────────────────────
# 目前已關閉。還原方法：
#   1. 將下方 DEBUG 改回 True
#   2. 在 ui_draw_fx.py 找 "[DEV_BTN DISABLED]" 區塊，取消繪製程式碼的註解，
#      並將同函式的 return 裡 None 改回 dev_r
DEBUG = False


async def game_main():
    """
    遊戲邏輯主協程，與 run_ui() 協程並行運行。
    所有 ui.ask_*() 呼叫都是 async 函式，透過 await 讓出控制權給 UI 迴圈。
    外層 while 迴圈支援「再來一次」重玩。
    """
    while True:
        # ── 等待玩家點擊「開始遊戲」────────────────────────
        await ui.wait_start()

        # print("=" * 50)  # 因套用pygame而調整
        ui.notify("=" * 50)
        # print("  歡迎來到《如何渡過這學期？》")  # 因套用pygame而調整
        ui.notify("  歡迎來到《如何渡過這學期？》")
        # print("=" * 50)  # 因套用pygame而調整
        ui.notify("=" * 50)

        # ── DEV 跳關：全隨機角色直接跳至最終結算 ────────────────
        if DEBUG and ui.was_debug_skip():
            _de  = random.choice(DE_LEVELS)
            _tal = random.choice(TALENTS)
            _dbs = random.sample(DRAWBACKS, random.randint(0, len(DRAWBACKS)))
            player = Character(
                name             = "DEV",
                department       = random.choice(["管理學院", "文學院", "理學院", "工學院"]),
                stamina          = random.randint(10, 80),
                intel            = random.randint(10, 80),
                luck             = random.randint(10, 80),
                money            = random.randint(0, 800),
                talent           = _tal,
                drawbacks        = _dbs,
                de_level         = _de,
                portrait_prefix  = random.choice(["b1", "g1"]),
                slot_results     = [_tal, random.choice(TALENTS), random.choice(TALENTS)],
            )
            for _k in player.grades:
                player.grades[_k] = random.uniform(20, 100)
            player.satisfaction = random.randint(30, 100)
            ui.set_player(player)
            event_sys = EventSystem(player)
            skill_sys = SkillSystem(player)
            shop      = Shop(player, event_sys=event_sys)
            engine    = TurnEngine(player=player, event_sys=event_sys,
                                   skill_sys=skill_sys, shop=shop)
            ui.notify(f"\n{'─'*50}")
            ui.notify("  第 16 週")
            ui.notify(f"{'─'*50}")
            ui.set_player(player)
            ui.set_week(16)
            ui.trigger_ripple()
            game_over = engine.run_week(16)
            if not game_over:
                engine.final_settlement()
            ui.notify_end()
            await ui.wait_restart()
            ui.reset_ui()
            continue

        # ── 步驟 1：建立角色 ──────────────────────────────────
        player = await Character.create_new()
        ui.set_player(player)

        # ── 步驟 2：建立各大子系統 ───────────────────────────
        event_sys = EventSystem(player)
        skill_sys = SkillSystem(player)
        shop      = Shop(player, event_sys=event_sys)
        engine    = TurnEngine(
            player    = player,
            event_sys = event_sys,
            skill_sys = skill_sys,
            shop      = shop,
        )

        # ── 步驟 2.5：詢問是否跳過新手教學 ──────────────────
        skip_tutorial = await ui.ask_yn(
            "要跳過新手教學嗎？",
            yes_label="直接開始",
            no_label="觀看教學",
            show_ctx=False,
        )
        engine.show_tutorial = not skip_tutorial

        # ── 步驟 3：主遊戲循環（共 16 回合 = 16 週）──────────
        premature_gameover = False
        for week in range(1, 17):
            # print(f"\n{'─'*50}")  # 因套用pygame而調整
            ui.notify(f"\n{'─'*50}")
            # print(f"  第 {week} 週")  # 因套用pygame而調整
            ui.notify(f"  第 {week} 週")
            # print(f"{'─'*50}")  # 因套用pygame而調整
            ui.notify(f"{'─'*50}")

            # display_status(player)  # 因套用pygame而調整（狀態欄由 pygame 持續顯示）
            ui.set_player(player)

            ui.set_week(week)
            if week > 1:
                ui.trigger_ripple()   # 週次切換漣漪轉場
            game_over = await engine.run_week(week)

            if game_over:
                # print("\n💀 遊戲結束：你沒能撐過這學期……")  # 因套用pygame而調整
                ui.notify("\n💀 遊戲結束：你沒能撐過這學期……")
                premature_gameover = True
                break   # 跳出 for，不執行 else（即不呼叫 final_settlement）

        else:
            # ── 步驟 4：期末結算（16 週正常完成）────────────
            await engine.final_settlement()

        # ── 步驟 5：切換結束畫面，等待玩家決定────────────
        if premature_gameover:
            ui.notify_gameover()   # Game Over 畫面（黑幕 → 背景圖 + 剪影）
        else:
            ui.notify_end()        # 正常結算畫面
        await ui.wait_restart()
        ui.reset_ui()   # 清除 log 與狀態，準備下一局


async def main():
    """頂層協程：同時啟動遊戲邏輯與 UI 迴圈。"""
    asyncio.ensure_future(game_main())   # 遊戲邏輯協程進入排程
    await ui.run_ui()                    # UI 主迴圈（每幀 await asyncio.sleep(0)）

asyncio.run(main())
