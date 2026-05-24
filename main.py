# ============================================================
#  主程式：如何渡過這學期？（pygame 版）
# ============================================================
# 與 main_origin.py 的差異：
#   - 遊戲邏輯包進 game_main()，跑在背景執行緒
#   - 主執行緒交給 ui.run_ui() 跑 pygame 事件迴圈
#   - print() 改為 ui.notify()；display_status 改為 ui.set_player()
# ============================================================

import threading

import ui
from character import Character
from turn_engine import TurnEngine
from event_system import EventSystem
from skill_system import SkillSystem
from shop_V03 import Shop


def game_main():
    """
    遊戲邏輯主函式，在背景執行緒中執行。
    所有 ui.notify() / ui.ask_*() 呼叫都是執行緒安全的阻塞呼叫，
    邏輯順序與原版完全相同。
    外層 while 迴圈支援「再來一次」重玩。
    """
    while True:
        # ── 等待玩家點擊「開始遊戲」────────────────────────
        ui.wait_start()

        # print("=" * 50)  # 因套用pygame而調整
        ui.notify("=" * 50)
        # print("  歡迎來到《如何渡過這學期？》")  # 因套用pygame而調整
        ui.notify("  歡迎來到《如何渡過這學期？》")
        # print("=" * 50)  # 因套用pygame而調整
        ui.notify("=" * 50)

        # ── 步驟 1：建立角色 ──────────────────────────────────
        player = Character.create_new()
        ui.set_player(player)

        # ── 步驟 2：建立各大子系統 ───────────────────────────
        event_sys = EventSystem(player)
        skill_sys = SkillSystem(player)
        shop      = Shop(player)
        engine    = TurnEngine(
            player    = player,
            event_sys = event_sys,
            skill_sys = skill_sys,
            shop      = shop,
        )

        # ── 步驟 3：主遊戲循環（共 16 回合 = 16 週）──────────
        for week in range(1, 17):
            # print(f"\n{'─'*50}")  # 因套用pygame而調整
            ui.notify(f"\n{'─'*50}")
            # print(f"  第 {week} 週")  # 因套用pygame而調整
            ui.notify(f"  第 {week} 週")
            # print(f"{'─'*50}")  # 因套用pygame而調整
            ui.notify(f"{'─'*50}")

            # display_status(player)  # 因套用pygame而調整（狀態欄由 pygame 持續顯示）
            ui.set_player(player)

            game_over = engine.run_week(week)

            if game_over:
                # print("\n💀 遊戲結束：你沒能撐過這學期……")  # 因套用pygame而調整
                ui.notify("\n💀 遊戲結束：你沒能撐過這學期……")
                break   # 跳出 for，不執行 else（即不呼叫 final_settlement）

        else:
            # ── 步驟 4：期末結算（16 週正常完成）────────────
            engine.final_settlement()

        # ── 步驟 5：切換結束畫面，等待玩家決定────────────
        ui.notify_end()
        ui.wait_restart()
        ui.reset_ui()   # 清除 log 與狀態，準備下一局


if __name__ == "__main__":
    # 遊戲邏輯跑在 daemon 執行緒：視窗關閉時自動結束
    t = threading.Thread(target=game_main, daemon=True)
    t.start()

    # 主執行緒交給 pygame（必須在主執行緒，pygame 的限制）
    ui.run_ui()
