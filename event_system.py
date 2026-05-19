# ============================================================
#  模組：event_system.py — 突發事件系統
# ============================================================
# 負責「扶老奶奶」、「腳踏車報銷」、「睡過頭」等隨機事件。
# 每週結束後擲一次骰，依照運氣值決定觸發機率與好壞事件比例。
# ============================================================

import random
from character import Character

# ── 事件資料庫 ────────────────────────────────────────────
# 每個事件是一個字典，包含：
#   trigger_condition：觸發條件（函式，傳入 player 回傳 bool）
#   weight：基礎觸發權重（越高越容易抽到）
#   is_positive：True=好事，False=壞事（運氣值會調整比例）
#   effect：實際效果函式（傳入 player，直接修改其數值）
#   desc：事件描述文字

EVENTS = [
    {
        "id":       "grandma",
        "name":     "扶老奶奶過馬路",
        "weight":   10,
        "is_positive": True,
        "trigger_condition": lambda p: True,  # 任何情況都可能觸發
        "desc":     (
            "你在路上扶了一位老奶奶過馬路。\n"
            "老奶奶有 50% 的機率是學校董事會成員…"
        ),
        "effect":   lambda p: _grandma_effect(p),
    },
    {
        "id":       "flat_tire",
        "name":     "腳踏車報銷",
        "weight":   8,
        "is_positive": False,
        "trigger_condition": lambda p: True,
        "desc":     "你的腳踏車在半路爆胎，今天遲到了！",
        "effect":   lambda p: _flat_tire_effect(p),
    },
    {
        "id":       "oversleep",
        "name":     "睡過頭",
        "weight":   12,
        "is_positive": False,
        # 觸發條件：疲勞高（體力 < 30）才有機率觸發
        "trigger_condition": lambda p: p.stamina < 30,
        "desc":     "鬧鐘沒響？你睡過頭，錯過了今天的課！",
        "effect":   lambda p: _oversleep_effect(p),
    },
    {
        "id":       "scholarship",
        "name":     "意外獎學金",
        "weight":   5,
        "is_positive": True,
        "trigger_condition": lambda p: True,
        "desc":     "系辦通知你獲得了一筆小額獎學金！",
        "effect":   lambda p: setattr(p, "money", p.money + 300) or print("  💰 獲得 300 元獎學金！"),
    },
    {
        "id":       "group_project",
        "name":     "組員跑路",
        "weight":   9,
        "is_positive": False,
        "trigger_condition": lambda p: True,
        "desc":     "小組報告的組員突然消失，你得一個人扛完所有工作……",
        "effect":   lambda p: _group_project_effect(p),
    },
    {
        "id":       "free_meal",
        "name":     "學長姐請吃飯",
        "weight":   7,
        "is_positive": True,
        "trigger_condition": lambda p: True,
        "desc":     "學長姐心情好，請你去吃大餐！滿足感大增。",
        "effect":   lambda p: p.change_satisfaction(15) or p.restore_stamina(3),
    },
]


# ── 事件效果函式（獨立在類別外，保持程式碼整潔）──────────
def _grandma_effect(player: Character):
    """扶老奶奶：50% 機率是董事會成員。"""
    if random.random() < 0.5:
        print("  ✨ 老奶奶竟然是董事會成員！平時成績 +5！")
        player.grades["參與度"] = min(100, player.grades["參與度"] + 5)
    else:
        print("  😊 老奶奶感謝你，你心情愉快。滿足感 +5。")
        player.change_satisfaction(5)

def _flat_tire_effect(player: Character):
    """腳踏車報銷：遲到 → 參與度 -5，需花錢修車。"""
    repair_cost = random.randint(100, 300)
    player.money = max(0, player.money - repair_cost)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 5)
    player.change_satisfaction(-8)
    print(f"  🔧 修車花費 {repair_cost} 元，參與度下降。")

def _oversleep_effect(player: Character):
    """睡過頭：根據當週是否考試決定嚴重程度。"""
    player.grades["參與度"] = max(0, player.grades["參與度"] - 8)
    player.change_satisfaction(-10)
    print("  😴 你睡到中午才起床，缺席了早上的課。參與度大跌！")

def _group_project_effect(player: Character):
    """組員跑路：體力大耗，但作業分數有機會拿高分。"""
    player.consume_stamina(5)
    player.change_satisfaction(-12)
    # 雖然很慘，但一個人做有機率加分（教授憐憫）
    if random.random() < 0.3:
        player.grades["作業"] = min(100, player.grades["作業"] + 10)
        print("  📝 你獨立完成了報告，教授給了額外加分！")
    else:
        print("  😩 你獨力完成，但精疲力竭，體力與滿足感大跌。")


class EventSystem:
    """突發事件管理器：每週呼叫 roll_event() 來隨機觸發事件。"""

    def __init__(self, player: Character):
        self.player = player

    def roll_event(self, week: int):
        """
        擲骰決定本週是否觸發突發事件。
        運氣值高的角色較容易遇到好事件、較少遇到壞事件。
        """
        player = self.player

        # 先篩出「符合觸發條件」的事件
        # （list comprehension：把 EVENTS 裡符合條件的撈出來）
        eligible = [
            e for e in EVENTS
            if e["trigger_condition"](player)
        ]

        if not eligible:
            return  # 沒有可觸發事件，直接略過

        # 30% 機率觸發事件（避免每週都爆）
        if random.random() > 0.30:
            return

        # 根據運氣決定好事件 / 壞事件的比例
        # luck 50 時各半；luck 100 時好事件機率翻倍
        luck_bonus = (player.luck - 50) / 100  # -0.5 ~ +0.5

        # 計算每個事件的實際權重
        weighted_events = []
        for e in eligible:
            w = e["weight"]
            if e["is_positive"]:
                w *= (1 + luck_bonus)   # 好事：運氣越高，機率越大
            else:
                w *= (1 - luck_bonus)   # 壞事：運氣越高，機率越小
            w = max(1, w)               # 至少為 1，避免權重為 0
            weighted_events.append((e, w))

        # random.choices 支援加權隨機抽取
        events, weights = zip(*weighted_events)  # 把列表拆成兩個 tuple
        chosen = random.choices(events, weights=weights, k=1)[0]

        # 觸發事件！
        print(f"\n⚡ 突發事件：【{chosen['name']}】")
        print(f"  {chosen['desc']}")
        chosen["effect"](player)
