# ============================================================
#  模組：event_system.py — 突發事件系統
# ============================================================
# 負責「扶老奶奶」、「腳踏車報銷」、「睡過頭」等隨機事件。
# 每週結束後擲一次骰，依照運氣值決定觸發機率與好壞事件比例。
#
# 事件分為四種類型：
#   EVENTS        — 全學期加權隨機池（原有邏輯）
#   PHASE_EVENTS  — 階段限定事件（固定機率，依週次篩選）
#   WEEKLY_EVENTS — 每週獨立觸發事件（不進加權池）
#   SPECIAL_EVENTS— 特殊突發事件（固定機率，有額外觸發條件）
# ============================================================

import random
from character import Character


# ── 主事件資料庫（全學期，加權隨機）─────────────────────────────
EVENTS = [
    {
        "id":       "grandma",
        "name":     "扶老奶奶過馬路",
        "weight":   10,
        "is_positive": True,
        "trigger_condition": lambda p: True,
        "desc":     (
            "路上遇到一個老奶奶要過馬路，你就順手扶了一下。\n"
            "結果她掏出名片——有 50% 機率是董事會的人……"
        ),
        "effect":   lambda p: _grandma_effect(p),
    },
    {
        "id":       "flat_tire",
        "name":     "腳踏車報銷",
        "weight":   8,
        "is_positive": False,
        "trigger_condition": lambda p: True,
        "desc":     "騎到一半胎爆了。就這樣。今天遲到，沒什麼好說的。",
        "effect":   lambda p: _flat_tire_effect(p),
    },
    {
        "id":       "oversleep",
        "name":     "睡過頭",
        "weight":   12,
        "is_positive": False,
        "trigger_condition": lambda p: p.stamina < 30,
        "desc":     "鬧鐘響了，但你沒有。睜眼一看——十一點半。今天上午的課掰掰。",
        "effect":   lambda p: _oversleep_effect(p),
    },
    {
        "id":       "scholarship",
        "name":     "意外獎學金",
        "weight":   5,
        "is_positive": True,
        "trigger_condition": lambda p: True,
        "desc":     "系辦寄信來說你有一筆獎學金可以領。你愣了三秒才確認不是詐騙。",
        "effect":   lambda p: setattr(p, "money", p.money + 300) or print("  💰 入帳 300 元，今晚可以吃好一點了。"),
    },
    {
        "id":       "group_project",
        "name":     "組員跑路",
        "weight":   9,
        "is_positive": False,
        "trigger_condition": lambda p: True,
        "desc":     "group chat 已讀不回，PPT 一頁都沒動。好，我知道了，我來就好。",
        "effect":   lambda p: _group_project_effect(p),
    },
]


# ── 階段限定事件（固定機率，依 week_range 篩選）─────────────────
# prob：該事件本身的觸發機率（獨立於主事件池的 30% 骰子）
# week_range：(開始週, 結束週)，兩端包含

PHASE_EVENTS = [
    {
        "id":       "add_drop_fail",
        "name":     "加簽失敗",
        "prob":     0.20,           # 最高 20%
        "week_range": (1, 3),
        "is_positive": False,
        "desc":     "等了整整兩週，教授直接把加簽單退回來了。課表就這樣，認了。",
        "effect":   lambda p: _add_drop_fail_effect(p),
    },
    {
        "id":       "club_drinking",
        "name":     "社團迎新被拱喝酒",
        "prob":     0.20,           # 最高 20%
        "week_range": (1, 3),
        "is_positive": False,       # 當下開心，但隔天宿醉是真的慘
        "desc":     (
            "本來說好喝果汁，學長姐一人塞你一杯說「乾！」\n"
            "你也不好意思拒絕……喝得很開心，但明天應該會死。"
        ),
        "effect":   lambda p: _club_drinking_effect(p),
        # 回傳 "TRIGGER_HANGOVER" 旗標，由 EventSystem 在下週強制觸發宿醉
    },
    {
        "id":       "library_full",
        "name":     "圖書館搶不到位子",
        "prob":     0.50,           # 最高 50%，最低不為 0%（固定 50% 滿足兩條件）
        "week_range": (4, 8),
        "is_positive": False,
        "desc":     "早上九點到圖書館，一樓滿、二樓滿、三樓也滿。最後坐在走廊地板K書。",
        "effect":   lambda p: _library_full_effect(p),
    },
    {
        "id":       "drop_crisis",
        "name":     "退選危機",
        "prob":     0.10,           # 最高 10%
        "week_range": (9, 16),
        "is_positive": False,
        "desc":     "想退那堂爛課，結果查了一下——退選截止日上週就過了。幹。",
        "effect":   lambda p: _drop_crisis_effect(p),
    },
]


# ── 每週獨立觸發事件（不進加權池，單獨擲骰）────────────────────
WEEKLY_EVENTS = [
    {
        "id":       "cafeteria_price",
        "name":     "小福便當漲價",
        "prob":     0.10,           # 每週 10% 機率觸發，但全學期只發生一次（once 旗標控制）
        "week_range": (1, 16),
        "is_positive": False,
        "once":     True,           # True = 觸發後不再重複
        "desc":     "小福便當又漲了。這學期就這一次，但每次看到新價格還是很想罵人。",
        "effect":   lambda p: _cafeteria_price_effect(p),
    },
]


# ── 特殊突發事件（固定 5%，有額外觸發條件）──────────────────────
# trigger_condition：傳入 (player, week)，需同時滿足才有機率觸發

SPECIAL_EVENTS = [
    {
        "id":       "green_hat",
        "name":     "被戴綠帽了",
        "prob":     0.05,           # 固定 5%
        # 期中考（第 8 週）結束後才可能發生
        "trigger_condition": lambda p, week: week > 8,
        "is_positive": False,
        "desc":     (
            "對象最近怪怪的，你就隨手翻了一下手機。\n"
            "然後你就不想翻了。"
        ),
        "effect":   lambda p: _green_hat_effect(p),
    },
]


# ── 事件效果函式 ──────────────────────────────────────────────────

def _grandma_effect(player: Character):
    """扶老奶奶：50% 機率是董事會成員。"""
    if random.random() < 0.5:
        print("  ✨ 那個老奶奶竟然是董事會的！參與度 +5，賺到了。")
        player.grades["參與度"] = min(100, player.grades["參與度"] + 5)
    else:
        print("  😊 老奶奶一直跟你道謝，心情莫名好了起來。滿足感 +5。")
        player.change_satisfaction(5)

def _flat_tire_effect(player: Character):
    """腳踏車報銷：遲到 → 參與度 -5，需花錢修車。"""
    repair_cost = random.randint(100, 300)
    player.money = max(0, player.money - repair_cost)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 5)
    player.change_satisfaction(-8)
    print(f"  🔧 修車費 {repair_cost} 元，還被教授點名。這天不用過了。")

def _oversleep_effect(player: Character):
    """睡過頭：缺席早上的課，參與度與滿足感下跌。"""
    player.grades["參與度"] = max(0, player.grades["參與度"] - 8)
    player.change_satisfaction(-10)
    print("  😴 睜眼十一點半，傳了一則「老師我今天身體不舒服」然後繼續躺著。")

def _group_project_effect(player: Character):
    """組員跑路：體力大耗，但有 30% 機率教授憐憫加分。"""
    player.consume_stamina(5)
    player.change_satisfaction(-12)
    if random.random() < 0.3:
        player.grades["作業"] = min(100, player.grades["作業"] + 10)
        print("  📝 一個人做完了，教授還特別誇你。可喜可賀，但你累到說不出話。")
    else:
        print("  😩 做完了。沒什麼好說的，就是累。")

def _add_drop_fail_effect(player: Character):
    """加簽失敗：課表一團亂，參與度與滿足感下跌。"""
    player.change_satisfaction(-10)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 5)
    print("  📋 加簽單被退回來了。課表就這樣，能怎樣，修就修吧。")

def _club_drinking_effect(player: Character):
    """
    社團迎新被拱喝酒：當下滿足感上升，但體力大耗。
    回傳 'TRIGGER_HANGOVER'，由 EventSystem 在下週強制觸發宿醉。
    """
    player.change_satisfaction(10)    # 當下很爽
    player.consume_stamina(8)
    print("  🍺 喝得很盡興，當下覺得一切都值得。")
    print("  ⚠️  但現在是凌晨兩點，明天你會後悔的。")
    return "TRIGGER_HANGOVER"

def _hangover_effect(player: Character):
    """宿醉：由 pending_hangover 旗標在下週強制觸發。"""
    player.consume_stamina(10)
    player.change_satisfaction(-15)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 10)
    print("  🤢 頭痛、想吐、光線太刺眼。今天的課？不存在的。")

def _library_full_effect(player: Character):
    """圖書館搶不到位子：在走廊讀書，效率下滑。"""
    player.consume_stamina(3)
    player.grades["作業"] = max(0, player.grades["作業"] - 5)
    player.change_satisfaction(-6)
    print("  📚 走廊地板坐了一整天，屁股麻、書沒讀多少，作業品質直接打折。")

def _drop_crisis_effect(player: Character):
    """退選危機：被迫繼續修不想修的課，滿足感暴跌並額外花錢補救。"""
    player.change_satisfaction(-12)
    player.money = max(0, player.money - 100)    # 買參考書等補救措施
    print("  😰 截止日過了。那堂課退不掉了，只能硬撐到期末。")

def _cafeteria_price_effect(player: Character):
    """小福便當漲價：金錢小失血，滿足感微降。"""
    extra_cost = random.randint(10, 30)
    player.money = max(0, player.money - extra_cost)
    player.change_satisfaction(-2)
    print(f"  🍱 又漲了 {extra_cost} 元。默默付錢，默默難過。")

def _green_hat_effect(player: Character):
    """
    被戴綠帽了：
      - 滿足感強制 -25，扣到 0 為止（交由 change_satisfaction 夾值）
      - 接下來 4 週每週再扣 25 滿足感（由 EventSystem debuff 系統追蹤）
    回傳 "TRIGGER_GREEN_HAT_DEBUFF" 旗標，讓 EventSystem 註冊 debuff。
    """
    player.change_satisfaction(-25)
    print("  💔 你盯著手機螢幕看了很久，然後把它蓋起來。什麼都不想說。")
    print("  📉 接下來幾週大概也讀不進去什麼了。")
    return "TRIGGER_GREEN_HAT_DEBUFF"


# ── EventSystem ───────────────────────────────────────────────────

class EventSystem:
    """
    突發事件管理器：每週呼叫 roll_event(week) 來隨機觸發事件。

    觸發順序（每週依序執行）：
      1. 強制待觸發事件（宿醉）— 若有旗標，直接觸發並結束本週
      2. 每週固定獨立事件  （小福便當漲價）— 獨立 10% 擲骰，全學期至多一次
      3. 特殊突發事件      （被戴綠帽了）  — 固定 5%，條件限制
      4. 階段限定事件      （加簽失敗等）  — 固定機率，週次篩選
      5. 主事件池          （原有加權邏輯）— 30% 基礎機率，運氣加權
    """

    def __init__(self, player: Character):
        self.player = player
        self.pending_hangover = False   # 宿醉旗標：下週強制觸發
        self.triggered_once = set()     # 記錄已觸發過的 once=True 事件 id
        self.active_debuffs = []        # 進行中的 debuff 列表

    def roll_event(self, week: int):
        """
        每週事件流程：
          0. Debuff 計時（永遠執行，不佔事件槽）
          1. 蒐集所有「擲骰通過」的候選事件
          2. 裁決本週觸發數量（上限 2，第 2 個機率極低）
          3. 逐一執行選中的事件
        """
        player = self.player

        # ── 0. Debuff 計時器（永遠執行，不佔事件槽）─────────────
        self._tick_debuffs()

        # ── 1. 蒐集候選事件 ──────────────────────────────────────
        # 每個候選為 (type_str, event_dict | None)
        candidates = []

        # 強制事件（宿醉）：不需擲骰，直接入列
        if self.pending_hangover:
            candidates.append(("hangover", None))

        # 每週獨立事件（小福便當漲價）
        for we in WEEKLY_EVENTS:
            start, end = we["week_range"]
            if start <= week <= end:
                if we.get("once") and we["id"] in self.triggered_once:
                    continue
                if random.random() < we["prob"]:
                    candidates.append(("weekly", we))

        # 特殊突發事件（被戴綠帽）
        for se in SPECIAL_EVENTS:
            if se["trigger_condition"](player, week):
                if random.random() < se["prob"]:
                    candidates.append(("special", se))

        # 階段限定事件
        for pe in PHASE_EVENTS:
            start, end = pe["week_range"]
            if start <= week <= end:
                if random.random() < pe["prob"]:
                    candidates.append(("phase", pe))

        # 主事件池（加權隨機）
        eligible = [e for e in EVENTS if e["trigger_condition"](player)]
        if eligible and random.random() < 0.30:
            luck_bonus = (player.luck - 50) / 100
            weighted = []
            for e in eligible:
                w = e["weight"]
                w *= (1 + luck_bonus) if e["is_positive"] else (1 - luck_bonus)
                weighted.append((e, max(1, w)))
            evts, wts = zip(*weighted)
            candidates.append(("main", random.choices(evts, weights=wts, k=1)[0]))

        if not candidates:
            return

        # ── 2. 裁決觸發數量（上限 2，第 2 個機率極低）──────────
        # 宿醉為強制事件，優先保留，其餘隨機抽取
        forced   = [c for c in candidates if c[0] == "hangover"]
        optional = [c for c in candidates if c[0] != "hangover"]

        if forced:
            # 有宿醉：宿醉必觸發，10% 機率再附帶一個可選事件
            to_trigger = [forced[0]]
            if optional and random.random() < 0.10:
                to_trigger.append(random.choice(optional))
        else:
            # 無宿醉：從候選中隨機挑 1 個，10% 機率再挑第 2 個
            first = random.choice(candidates)
            to_trigger = [first]
            rest = [c for c in candidates if c is not first]
            if rest and random.random() < 0.10:
                to_trigger.append(random.choice(rest))

        # ── 3. 執行選中的事件 ────────────────────────────────────
        for event_type, event in to_trigger:
            self._fire_event(event_type, event)

    def _fire_event(self, event_type: str, event):
        """單一事件的執行邏輯，處理印出、效果呼叫與旗標回傳。"""
        player = self.player

        # 宿醉（強制）
        if event_type == "hangover":
            self.pending_hangover = False
            print("\n⚡ 強制事件：【宿醉發作】")
            print("  🤢 昨晚喝太多，今天整個人不對勁。")
            _hangover_effect(player)
            return

        # 其他事件：印出標題與描述
        prefix = "💥 特殊事件" if event_type == "special" else "⚡ 突發事件"
        print(f"\n{prefix}：【{event['name']}】")
        print(f"  {event['desc']}")

        # 執行效果並處理旗標
        result = event["effect"](player)
        if result == "TRIGGER_HANGOVER":
            self.pending_hangover = True
        elif result == "TRIGGER_GREEN_HAT_DEBUFF":
            self._register_green_hat_debuff()

        # once 事件觸發後記錄，避免重複
        if event_type == "weekly" and event.get("once"):
            self.triggered_once.add(event["id"])

    # ── Debuff 工具方法 ───────────────────────────────────────────

    def _register_green_hat_debuff(self):
        """
        註冊「被戴綠帽」debuff：每週固定扣 25 滿足感，不足額直接歸 0，持續 4 週。
        """
        self.active_debuffs.append({
            "id":              "green_hat_debuff",
            "name":            "心碎狀態",
            "weeks_remaining": 4,
            "weekly_effect":   lambda p: p.change_satisfaction(-25),
        })
        print("  🔻 心碎狀態啟動：接下來 4 週每週滿足感 -25，振作不起來。")

    def _tick_debuffs(self):
        """
        每週開始時呼叫，將所有進行中的 debuff 倒數一週並執行週效果。
        週數歸零時解除效果並從列表移除。
        """
        still_active = []
        for debuff in self.active_debuffs:
            # 先執行本週效果
            if "weekly_effect" in debuff:
                debuff["weekly_effect"](self.player)
            debuff["weeks_remaining"] -= 1
            if debuff["weeks_remaining"] > 0:
                still_active.append(debuff)
                print(
                    f"  ⏳ 【{debuff['name']}】還沒好，"
                    f"剩 {debuff['weeks_remaining']} 週。"
                )
            else:
                print(f"  ✅ 【{debuff['name']}】總算過去了，狀態恢復正常。")
        self.active_debuffs = still_active
