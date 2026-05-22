# ============================================================
#  主程式：如何渡過這學期？
#  Semester Survival Game — 入口點
# ============================================================
# 這裡是整個遊戲的「大門」，負責把所有模組串在一起、
# 依序執行遊戲的主循環。
# ============================================================

from character import Character          # 角色狀態管理器
from turn_engine import TurnEngine       # 回合與時間引擎
from event_system import EventSystem     # 突發事件系統
from skill_system import SkillSystem     # 養成與熟練度系統
from shop_V03 import Shop                    # 經濟與道具店
from ui import display_status, display_menu, get_player_choice  # 簡單 UI 工具


def main():
    """
    遊戲主函式：從角色創建到最終結算，全程在這裡串接。
    Python 慣例：把「程式的起點」包成一個叫 main() 的函式，
    方便日後測試與擴充。
    """

    print("=" * 50)
    print("  歡迎來到《如何渡過這學期？》")
    print("=" * 50)

    # ── 步驟 1：建立角色 ──────────────────────────────────
    # 讓玩家輸入名字並抽取天賦，Character 會幫我們管好所有數值。
    player = Character.create_new()

    # ── 步驟 2：建立各大子系統 ───────────────────────────
    event_sys  = EventSystem(player)    # 突發事件引擎
    skill_sys  = SkillSystem(player)    # 熟練度 / 養成引擎
    shop       = Shop(player)           # 道具商店
    engine     = TurnEngine(           # 回合引擎（把其他系統都傳進去）
        player     = player,
        event_sys  = event_sys,
        skill_sys  = skill_sys,
        shop       = shop,
    )

    # ── 步驟 3：主遊戲循環（共 16 回合 = 16 週）──────────
    # range(1, 17) 會產生 1, 2, 3, … 16
    for week in range(1, 17):
        print(f"\n{'─'*50}")
        print(f"  第 {week} 週")
        print(f"{'─'*50}")

        # 顯示角色當前狀態
        display_status(player)

        # 交給回合引擎處理這一週的所有邏輯
        game_over = engine.run_week(week)

        # 如果角色死亡、掛科或自我滿足感歸零，就提前結束
        if game_over:
            print("\n💀 遊戲結束：你沒能撐過這學期……")
            return

    # ── 步驟 4：期末結算 ──────────────────────────────────
    engine.final_settlement()


# ── Python 標準寫法：只有「直接執行這個檔案」時才跑 main() ──
# 如果別的檔案 import main.py，就不會自動執行，避免混亂。
if __name__ == "__main__":
    main()
