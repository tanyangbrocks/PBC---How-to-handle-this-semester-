# ============================================================
# 模組：turn_engine.py — 回合與時間引擎（升級版）
# ============================================================
# 控制 16 週的時間流轉：
#   開始週 → 判定本週特殊劇情 → 選擇行動 → 計算消耗收益
#          → 觸發突發事件 → 週結算 → 下一週
#
# 第 8 週：期中考週
# 第 16 週：期末考週
# ============================================================

import random
import time

from character import Character
from event_system import EventSystem
from skill_system import SkillSystem
from shop_V03 import Shop
from ui import get_player_choice, display_status


# ── 每週可選擇的行動清單 ──────────────────────────────────
ACTIONS = [
    {
        "id": "study_hard",
        "name": "認真讀書",
        "stamina_cost": 4,
        "exp_gain": 8,
        "satisfaction": -5,
        "desc": "花大量時間在課業上，學習效率高但很耗體力。",
    },
    {
        "id": "attend_class",
        "name": "正常上課",
        "stamina_cost": 2,
        "exp_gain": 4,
        "satisfaction": 0,
        "participation": 5,
        "desc": "按時上課，維持基本學習進度。",
    },
    {
        "id": "club_activity",
        "name": "社團活動",
        "stamina_cost": 3,
        "exp_gain": 0,
        "satisfaction": 10,
        "desc": "參加社團，放鬆心情，但會犧牲讀書時間。",
    },
    {
        "id": "part_time_job",
        "name": "打工賺錢",
        "stamina_cost": 4,
        "exp_gain": 0,
        "satisfaction": 3,
        "money_gain": 150,
        "desc": "去打工貼補生活費，但很耗體力。",
    },
    {
        "id": "rest",
        "name": "好好休息",
        "stamina_cost": -6,
        "exp_gain": 0,
        "satisfaction": 8,
        "desc": "什麼都不做，充電休息。",
    },
    {
        "id": "help_friend",
        "name": "幫助朋友",
        "stamina_cost": 2,
        "exp_gain": 0,
        "satisfaction": 12,
        "desc": "花時間陪伴身邊的人，自我滿足感大增。",
    },
]


class TurnEngine:
    def __init__(
        self,
        player: Character,
        event_sys: EventSystem,
        skill_sys: SkillSystem,
        shop: Shop,
    ):
        self.player = player
        self.event_sys = event_sys
        self.skill_sys = skill_sys
        self.shop = shop

    def run_week(self, week: int) -> bool:
        """
        執行一週的完整流程。
        回傳 True 代表 Game Over。
        """
        player = self.player

        if week == 8:
            self._midterm_week()
        elif week == 16:
            self._final_week()
        else:
            self._normal_week(week)

            # 普通週才觸發一般突發事件。
            # 期中、期末已經有專屬考前事件，避免事件太亂。
            self.event_sys.roll_event(week)

        self._end_of_week_reflection(week)
        player.tick_status_effects()

        return player.is_game_over()

    # ============================================================
    # 普通週與行事曆劇情
    # ============================================================
    def _normal_week(self, week: int):
        player = self.player

        print(f"\n📅 【第 {week} 週 行事曆提示】")

        if week in (4, 12):
            print("  ⚠️ 助教提醒：本週有隨堂小考！大家準備好了嗎？")
            player.consume_stamina(2)

            total_exp = sum(player.subject_exp.values())

            if total_exp > 50:
                print("  ✅ 熟練度足夠，小考輕鬆過關！")
                player.grades["小考"] = max(player.grades["小考"], 80)
                player.change_satisfaction(5)
            else:
                print("  ❌ 準備不足，小考慘遭滑鐵盧……")
                player.grades["小考"] = max(player.grades["小考"], 50)
                player.change_satisfaction(-8)

        elif week == 9:
            print("  🎉 系學會會長在群組裡公告招工事宜。")
            choice = input("  要答應幫忙辦活動嗎？(y/N)：").strip().lower()

            if choice == "y":
                print("  ✨ 答應成為工人！運氣 +10，但體力 -8。")
                player.luck += 10
                player.consume_stamina(8)
                player.change_satisfaction(5)
            else:
                print("  🛏️ 決定把時間留給自己，好好休息。")
                player.change_satisfaction(3)

        elif week == 13:
            print("  ⚠️ 停修期限截止在即！看著成績，你陷入猶豫……")
            choice = input("  要壯士斷腕選擇停修某一科嗎？(y/N)：").strip().lower()

            if choice == "y":
                print("  💥 停修成功！體力 +10，但運氣 -10。")
                player.restore_stamina(10)
                player.luck = max(0, player.luck - 10)
                player.change_satisfaction(5)
            else:
                print("  💪 決定硬著頭皮撐下去！滿足感 +5。")
                player.change_satisfaction(5)

        elif week == 14:
            print("  🔥 簡報、報告、期末作業突然一起出現，deadline 大爆炸！")
            print("  你必須選擇優先完成哪一項：")
            print("  1. 製作小組簡報：作業成績 70，體力 -10")
            print("  2. 撰寫五千字報告：作業成績 85，體力 -20")

            ans = input("  請做出抉擇 (1/2)：").strip()

            if ans == "2":
                player.grades["作業"] = max(player.grades["作業"], 85)
                player.consume_stamina(20)
                player.change_satisfaction(-8)
                print("  📝 瘋狂趕工完成五千字報告！作業成績提升。")
            else:
                player.grades["作業"] = max(player.grades["作業"], 70)
                player.consume_stamina(10)
                player.change_satisfaction(-3)
                print("  🤝 順利完成小組簡報，至少不會被組員罵。")

        else:
            print("  🍃 本週校園風平浪靜，照著自己的步調前進吧。")

        # ── 常規行動迴圈 ───────────────────────────────
        time_units = player.get_effective_time()
        print(f"\n本週可支配時間：{time_units} 單位")

        if input("\n要去道具店嗎？(y/N)：").strip().lower() == "y":
            self.shop.open_shop()

        remaining_time = time_units

        while remaining_time > 0:
            display_status(player)

            print(f"\n⏱ 本週剩餘時間：{remaining_time} 單位")
            print("選擇本週行動：")

            for i, action in enumerate(ACTIONS, start=1):
                cost = action["stamina_cost"]
                cost_str = f"體力 {'恢復' if cost < 0 else '消耗'} {abs(cost)}"
                print(f"  {i}. {action['name']} ({cost_str}) — {action['desc']}")

            print("  0. 結束本週行動")

            choice = get_player_choice(ACTIONS)

            if choice == 0:
                break

            action = ACTIONS[choice - 1]

            if action["stamina_cost"] > player.stamina:
                print(f"⚠️ 提醒：你的體力剩餘 {player.stamina}，執行此行動可能會導致生病！")
                confirm = input("確定要執行嗎？(y/N)：").strip().lower()

                if confirm != "y":
                    continue

            self._execute_action(action)
            remaining_time -= 1

    def _execute_action(self, action: dict):
        player = self.player
        cost = action["stamina_cost"]

        if cost > 0:
            player.consume_stamina(cost)
        else:
            player.restore_stamina(abs(cost))

        if action.get("exp_gain", 0) > 0:
            self.skill_sys.gain_exp("綜合", action["exp_gain"])

        player.change_satisfaction(action.get("satisfaction", 0))

        if "participation" in action:
            player.grades["參與度"] = min(
                100,
                player.grades["參與度"] + action["participation"],
            )

        if "money_gain" in action:
            player.money += action["money_gain"]
            print(f"  💰 賺到 {action['money_gain']} 元（現有：{player.money} 元）")

        print(f"  ✔ 執行【{action['name']}】完成。")

    # ============================================================
    # 期中 / 期末考
    # ============================================================
    def _pre_exam_check(self) -> float:
        """
        考前危機判定。
        回傳分數修正係數，正常為 1.0。
        """
        player = self.player
        modifier = 1.0

        print("\n  🔍 考前狀態檢測中……")
        time.sleep(0.5)

        if player.stamina < 30 and random.random() < 0.4:
            print("  💀 悲劇！因為考前熬夜體力不支，你居然睡過頭了！")
            print("  ⚠️ 趕到考場時時間只剩一半，本次考試總分打 5 折。")
            player.change_satisfaction(-15)
            modifier *= 0.5
            return modifier

        if player.luck < 40 and random.random() < 0.3:
            print("  🔧 倒楣！騎腳踏車去考場的路上居然爆胎！")
            print("  ⚠️ 滿頭大汗跑進考場，思緒混亂，考試總分打 85 折。")
            player.change_satisfaction(-8)
            modifier *= 0.85
            return modifier

        print("  🍀 一切順利，你安全且準時地坐在考場座位上。")
        return modifier

    def _run_exam_mini_game(self, exam_type: str) -> float:
        """
        考試問答小遊戲。
        回傳答題得分率，範圍 0.0 ~ 1.0。
        """
        print(f"\n✍ ═══ {exam_type}考：知識問答挑戰 ═══")
        print("請根據題目輸入正確的數字編號。")

        questions = [
            {
                "q": "台大三大夜沒有哪個之夜?？\n  (1) 會計之夜  (2) 電機之夜  (3) 南友之夜 (4) 國企之夜 ",
                "a": 1,
            },
            {
                "q": "下列何者不屬於三校聯盟？\n  (1) NTUST  (2) NTNU  (3) NTUE ",
                "a": 3,
            },
            {
                "q": "行政大樓前的傅鐘每次只敲幾下？\n  (1) 20 (2) 21  (3) 22",
                "a": 2,
            },
            {
                 "q": "台大附近的餐廳何者不位於118?？\n  (1) 三米三  (2) 笑嘻嘻  (3) IMPASTA (4) 李記水餃 ",
                 "a": 1,
            },
            {
                 "q": "台大附近的餐廳何者不位於水源商圈？\n  (1) 塊雞師食物所  (2) 大埔鐵板燒  (3) 小高拉麵 (4) 瑪莉珍披薩 ",
                 "a": 4,
            },
            {
                 "q": "商管程式設計這門課是由哪個系的教授開設的？\n  (1) 資工系  (2) 資管系  (3) 統計系",
                 "a": 1,
            },

       ]

        selected_qs = random.sample(questions, 4)
        correct_count = 0

        for i, q in enumerate(selected_qs, start=1):
            print(f"\n📌 題目 {i}: {q['q']}")

            try:
                ans = int(input("  👉 你的答案是："))
                if ans == q["a"]:
                    print("  ✨ 答對了！")
                    correct_count += 1
                else:
                    print("  ❌ 選錯了……")
            except ValueError:
                print("  ❌ 輸入錯誤，這題不計分。")

        return correct_count / len(selected_qs)

    def _midterm_week(self):
        player = self.player

        print("\n📋 ═══ 期中考週！═══")

        exam_modifier = self._pre_exam_check()

        base_stats_score = self._calculate_exam_score("期中") * 0.5
        mini_game_rate = self._run_exam_mini_game("期中")
        mini_game_score = mini_game_rate * 100 * 0.5

        total_score = (base_stats_score + mini_game_score) * exam_modifier
        player.grades["期中"] = max(0.0, min(100.0, total_score))

        print(f"\n📊 期中考最終成績：{player.grades['期中']:.1f} 分")
        print(f"  實力底分：{base_stats_score:.1f}")
        print(f"  考場發揮：{mini_game_score:.1f}")

        if player.grades["期中"] >= 60:
            print("  ✅ 順利飛過及格線！")
            player.change_satisfaction(10)
        else:
            print("  ❌ 望著滿江紅的考卷，你覺得這學期前途堪憂……")
            player.change_satisfaction(-15)

    def _final_week(self):
        player = self.player

        print("\n🎯 ═══ 期末考週！（最終關卡）═══")

        exam_modifier = self._pre_exam_check()

        base_stats_score = self._calculate_exam_score("期末") * 0.5
        mini_game_rate = self._run_exam_mini_game("期末")
        mini_game_score = mini_game_rate * 100 * 0.5

        total_score = (base_stats_score + mini_game_score) * exam_modifier
        player.grades["期末"] = max(0.0, min(100.0, total_score))

        print(f"\n📊 期末考最終成績：{player.grades['期末']:.1f} 分")
        print(f"  實力底分：{base_stats_score:.1f}")
        print(f"  考場發揮：{mini_game_score:.1f}")

        if player.grades["期末"] >= 60:
            print("  ✅ 成功撐過期末大魔王！")
            player.change_satisfaction(15)
        else:
            print("  ❌ 考卷上的分數宣判了你的死刑……")
            player.change_satisfaction(-20)

    def _calculate_exam_score(self, exam_type: str) -> float:
        """
        考試基礎分數公式。
        主要依據：
        - 熟練度平均
        - 智力加成
        - 運氣修正
        """
        player = self.player

        if not player.subject_exp:
            avg_exp = 0
        else:
            avg_exp = sum(player.subject_exp.values()) / len(player.subject_exp)

        intel_bonus = 1.0 + min(player.intel / 200, 0.5)
        luck_roll = random.uniform(-0.1, 0.1) + (player.luck - 50) / 500
        luck_multiplier = 1.0 + luck_roll

        raw_score = avg_exp * intel_bonus * luck_multiplier

        return max(0.0, min(100.0, raw_score))

    # ============================================================
    # 結算邏輯
    # ============================================================
    def _end_of_week_reflection(self, week: int):
        print("\n💭 【週末內心總結】")

        player = self.player
        stamina_ratio = player.stamina / player.stamina_max

        if stamina_ratio > 0.7:
            outcome_text = "狀態極佳，感覺下週能做更多事！"
            satisfaction_change = 5
        elif stamina_ratio > 0.3:
            outcome_text = "平穩度過，大學生活就是這樣吧。"
            satisfaction_change = 2
        else:
            outcome_text = "筋疲力竭，只想躺在床上當植物人……"
            satisfaction_change = -8

        print(f"  本週狀態：{outcome_text}")
        player.change_satisfaction(satisfaction_change)

    def final_settlement(self):
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
        print("  ─────────────────")
        print(f"  加權總分：{final_score:.1f} 分")
        print()

        if final_score >= 80 and player.satisfaction >= 70:
            print("  🌟 平衡型結局：成績漂亮，身心狀態也維持得很好。")
        elif final_score >= 60 and player.satisfaction >= 60:
            print("  🎉 及格快樂結局：你成功渡過了這學期，可以放暑假了！")
        elif final_score >= 60 and player.satisfaction < 60:
            print("  🫠 成績過了但身心崩潰：你及格了，但也快沒電了。")
        else:
            print("  💸 很遺憾……成績未達及格，明年準備重修吧。")

        print(f"\n  最終自我滿足感：{player.satisfaction}")
        print(f"  剩餘金錢：{player.money} 元")
        print("=" * 50)