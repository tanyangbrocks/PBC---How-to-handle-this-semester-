# ============================================================
#  模組：turn_engine.py — 回合與時間引擎
# ============================================================
# 控制 16 週的時間流轉：
#   開始週 → 選擇行動 → 計算消耗收益 → 觸發突發事件
#              → 週結算（內心總結）→ 下一週
# 第 8 週（期中）與第 16 週（期末）切換為特殊邏輯。
# ============================================================

import random
from character import Character
from event_system import EventSystem
from skill_system import SkillSystem
from shop import Shop
from ui import display_menu, get_player_choice, display_status

# ── 每週可選擇的行動清單 ──────────────────────────────────
# 每個行動是一個字典，存放名稱、體力消耗、各項收益等。
ACTIONS = [
    {
        "id":          "study_hard",
        "name":        "認真讀書",
        "stamina_cost": 4,       # 消耗體力
        "exp_gain":    8,        # 增加學習熟練度
        "satisfaction": -5,      # 減少滿足感（太無聊了）
        "desc":        "花大量時間在課業上，學習效率高但很耗體力。",
    },
    {
        "id":          "attend_class",
        "name":        "正常上課",
        "stamina_cost": 2,
        "exp_gain":    4,
        "satisfaction": 0,
        "participation": 5,      # 增加參與度分數
        "desc":        "按時上課，維持基本學習進度。",
    },
    {
        "id":          "club_activity",
        "name":        "社團活動",
        "stamina_cost": 3,
        "exp_gain":    0,
        "satisfaction": 10,      # 大幅增加滿足感
        "desc":        "參加社團，放鬆心情，但會犧牲讀書時間。",
    },
    {
        "id":          "part_time_job",
        "name":        "打工賺錢",
        "stamina_cost": 4,
        "exp_gain":    0,
        "satisfaction": 3,
        "money_gain":  150,      # 賺到金錢
        "desc":        "去打工貼補生活費，但很耗體力。",
    },
    {
        "id":          "rest",
        "name":        "好好休息",
        "stamina_cost": -6,      # 負數代表「恢復體力」
        "exp_gain":    0,
        "satisfaction": 8,
        "desc":        "什麼都不做，充電休息。",
    },
    {
        "id":          "help_friend",
        "name":        "幫助朋友",
        "stamina_cost": 2,
        "exp_gain":    0,
        "satisfaction": 12,
        "desc":        "花時間陪伴身邊的人，自我滿足感大增。",
    },
]


class TurnEngine:
    """
    回合引擎：負責每一週的流程控制。
    把 player、event_sys、skill_sys、shop 都存起來，
    方便在各個步驟之間互相呼叫。
    """

    def __init__(self, player: Character, event_sys: EventSystem,
                 skill_sys: SkillSystem, shop: Shop):
        self.player    = player
        self.event_sys = event_sys
        self.skill_sys = skill_sys
        self.shop      = shop

    def run_week(self, week: int) -> bool:
        """
        執行一週的完整流程。
        回傳 True 代表 Game Over，False 代表繼續遊戲。
        week：目前是第幾週（1~16）。
        """
        player = self.player

        # 判斷這週是否為期中 / 期末特殊回合
        if week == 8:
            self._midterm_week()
        elif week == 16:
            self._final_week()
        else:
            if week == 9:
                player.status_effects["疲勞"] = 1
                print("第 9 週：期中考後太累了，進入【疲勞】狀態，本週有效時間 -2。")
            
            self._normal_week(week)

        # 突發事件（每週都可能觸發）
        self.event_sys.roll_event(week)

        # 週結算：內心總結
        self._end_of_week_reflection(week)

        # 衰減狀態效果
        player.tick_status_effects()

        # 判斷是否 Game Over
        return player.is_game_over()

    # ────────────────────────────────────────────────────────
    #  普通回合
    # ────────────────────────────────────────────────────────
    def _normal_week(self, week: int):
        """普通週：讓玩家分配時間、使用道具。"""
        player = self.player
        time_units = player.get_effective_time()  # 本週可用時間
        print(f"\n本週可支配時間：{time_units} 單位")

        # 先讓玩家逛一次道具店
        if input("\n要去道具店嗎？(y/N)：").strip().lower() == "y":
            self.shop.open_shop()

        # 讓玩家選擇行動，直到時間用完
        remaining_time = time_units
        while remaining_time > 0:
            # 讓玩家在選擇前能看到目前的體力與狀態（初學者較易理解數值變化）
            display_status(player)
            
            print(f"\n⏱ 本週剩餘時間：{remaining_time} 單位")
            print("選擇本週行動：")
            for i, action in enumerate(ACTIONS, start=1):
                cost = action["stamina_cost"]
                cost_str = f"體力 {'恢復' if cost < 0 else '消耗'} {abs(cost)}"
                print(f"  {i}. {action['name']} ({cost_str}) — {action['desc']}")
            print("  0. 結束本週行動")

            # 修正 get_player_choice 的呼叫方式，只傳入清單（配合 ui.py 的定義）
            choice = get_player_choice(ACTIONS)
            
            # 如果選擇 0 則結束本週行動
            if choice == 0:
                break

            action = ACTIONS[choice - 1]
            
            # 執行前檢查體力（使用簡單的 if 判斷，對初學者很友善）
            if action["stamina_cost"] > player.stamina:
                print(f"⚠️  提醒：你的體力剩餘 {player.stamina}，執行此行動會導致生病！")
                if input("確定要執行嗎？(y/N)：").strip().lower() != 'y':
                    continue

            self._execute_action(action)
            remaining_time -= 1  # 每次行動消耗 1 單位時間

    def _execute_action(self, action: dict):
        """
        執行一個行動：套用體力消耗、熟練度成長、滿足感變化等。
        """
        player = self.player
        cost = action["stamina_cost"]

        # 體力消耗（cost < 0 表示恢復）
        if cost > 0:
            player.consume_stamina(cost)
        else:
            player.restore_stamina(abs(cost))

        # 學習熟練度成長（交給 skill_sys 計算，有等級加乘）
        if action.get("exp_gain", 0) > 0:
            self.skill_sys.gain_exp("綜合", action["exp_gain"])

        # 滿足感變化
        player.change_satisfaction(action.get("satisfaction", 0))

        # 參與度
        if "participation" in action:
            player.grades["參與度"] = min(100, player.grades["參與度"] + action["participation"])

        # 金錢收益
        if "money_gain" in action:
            player.money += action["money_gain"]
            print(f"  💰 賺到 {action['money_gain']} 元（現有：{player.money} 元）")

        print(f"  ✔ 執行【{action['name']}】完成。")

    # ────────────────────────────────────────────────────────
    #  期中回合（第 8 週）
    # ────────────────────────────────────────────────────────
    def _midterm_week(self):
        """
        期中考週：根據玩家的智力、熟練度、運氣來決定分數，
        並且有一定機率觸發「考試小遊戲」（預留擴充用）。
        """
        player = self.player
        print("\n📋 ═══ 期中考週！═══")
        print("這週你需要面對期中考的挑戰……")

        # 計算期中分數
        # 基礎分 = 熟練度平均 * 智力加成 * 運氣修正
        base_score = self._calculate_exam_score(exam_type="期中")
        player.grades["期中"] = base_score

        print(f"\n  📊 期中考成績：{base_score:.1f} 分")
        if base_score >= 60:
            print("  ✅ 恭喜過關！繼續加油！")
            player.change_satisfaction(10)
        else:
            print("  ❌ 未達及格標準，期末要更努力了……")
            player.change_satisfaction(-15)

    # ────────────────────────────────────────────────────────
    #  期末回合（第 16 週）
    # ────────────────────────────────────────────────────────
    def _final_week(self):
        """期末考週：邏輯同期中，但這是最後一關。"""
        player = self.player
        print("\n🎯 ═══ 期末考週！（最終關卡）═══")

        base_score = self._calculate_exam_score(exam_type="期末")
        player.grades["期末"] = base_score

        print(f"\n  📊 期末考成績：{base_score:.1f} 分")
        if base_score >= 60:
            print("  ✅ 你通過了期末考！")
            player.change_satisfaction(15)
        else:
            print("  ❌ 期末考不及格，前途堪憂……")
            player.change_satisfaction(-20)

    def _calculate_exam_score(self, exam_type: str) -> float:
        """
        考試分數公式：
          基礎 = 熟練度平均（0~100）
          智力加成 = intel / 100（最多翻倍）
          運氣修正 = random ±10%（模擬考場發揮）
        """
        player = self.player

        # 取所有科目熟練度的平均值
        avg_exp = sum(player.subject_exp.values()) / len(player.subject_exp)

        # 智力加成（intel 越高，乘數越大，上限 1.5 倍）
        intel_bonus = 1.0 + min(player.intel / 200, 0.5)

        # 運氣修正（lucky roll，-10% ~ +10%）
        luck_roll = random.uniform(-0.1, 0.1) + (player.luck - 50) / 500
        luck_multiplier = 1.0 + luck_roll

        raw_score = avg_exp * intel_bonus * luck_multiplier

        # 夾在 0~100
        return max(0.0, min(100.0, raw_score))

    # ────────────────────────────────────────────────────────
    #  週結算：內心總結
    # ────────────────────────────────────────────────────────
    def _end_of_week_reflection(self, week: int):
        """
        每週結束時，根據本週的整體表現給予一次總結收益。
        玩家可以獲得一個正向或負向的隨機事件結果。
        """
        print("\n💭 【週末內心總結】")

        # 簡單依照體力剩餘比例給予滿足感微調
        player = self.player
        stamina_ratio = player.stamina / player.stamina_max

        if stamina_ratio > 0.7:
            outcome = ("活力充沛", 5)       # (說明文字, 滿足感變化)
        elif stamina_ratio > 0.3:
            outcome = ("平穩度過", 2)
        else:
            outcome = ("筋疲力竭", -8)

        print(f"  本週狀態：{outcome[0]}")
        player.change_satisfaction(outcome[1])

    # ────────────────────────────────────────────────────────
    #  最終結算（16 週後呼叫）
    # ────────────────────────────────────────────────────────
    def final_settlement(self):
        """計算並顯示最終成績，判斷是否通關。"""
        player = self.player
        final_score = player.calculate_final_score()

        print("\n" + "=" * 50)
        print("  🎓 學期結束！最終成績結算")
        print("=" * 50)
        print(f"  參與度 (10%)：{player.grades['參與度']:.1f}")
        print(f"  作業   (20%)：{player.grades['作業']:.1f}")
        print(f"  小考   (10%)：{player.grades['小考']:.1f}")
        print(f"  期中   (30%)：{player.grades['期中']:.1f}")
        print(f"  期末   (30%)：{player.grades['期末']:.1f}")
        print(f"  ─────────────────")
        print(f"  加權總分：{final_score:.1f} 分")
        print()

        if final_score >= 60:
            print("  🎉 恭喜！你成功渡過了這學期！")
        else:
            print("  💸 很遺憾……成績未達及格，你需要重修了。")

        print(f"\n  最終自我滿足感：{player.satisfaction}")
        print(f"  剩餘金錢：{player.money} 元")
        print("=" * 50)
