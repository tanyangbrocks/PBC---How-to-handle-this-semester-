# ============================================================
#  模組：event_system.py — 突發事件系統
# ============================================================
# 每次行動後擲骰（機率為原本的一半），依週次範圍篩選事件。
#
# 觸發規則（每次行動後）：
#   1. 宿醉（強制）         — 有旗標時必觸發，不受週次限制
#   2. 有週次範圍的事件     — phase / weekly，週次符合時擲骰（機率減半）
#   3. 全學期事件           — 主事件池，15% 擲骰（原 30% / 2）
#   ▸ 2 > 3 優先級，同級隨機選一，一次行動只觸發一個
#   ▸ 一週累計至多 2 次突發事件（宿醉不計入上限）
#
# 「被戴綠帽」：週末獨立觸發（5%，週次 > 8），不受上述規則影響。
# ============================================================

import random
from character import Character
from ui import notify, ask_ok, trigger_screen_shake, play_event_sfx, start_notify_capture, stop_notify_capture


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
            "結果她掏出名片——"
        ),
        "btn_label": "然後呢？",
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
        "effect":   lambda p: _scholarship_effect(p),
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
PHASE_EVENTS = [
    {
        "id":       "add_drop_fail",
        "name":     "加簽失敗",
        "prob":     0.20,   # 原機率；roll_event_after_action 內自動減半
        "week_range": (1, 3),
        "is_positive": False,
        "desc":     "等了整整兩週，教授直接把加簽單退回來了。課表就這樣，認了。",
        "effect":   lambda p: _add_drop_fail_effect(p),
    },
    {
        "id":       "club_drinking",
        "name":     "社團迎新被拱喝酒",
        "prob":     0.20,
        "week_range": (1, 3),
        "is_positive": False,
        "desc":     (
            "本來說好喝果汁，學長姐一人塞你一杯說「乾！」\n"
            "你也不好意思拒絕……喝得很開心，但明天應該會死。"
        ),
        "effect":   lambda p: _club_drinking_effect(p),
    },
    {
        "id":       "library_full",
        "name":     "圖書館搶不到位子",
        "prob":     0.50,
        "week_range": (4, 8),
        "is_positive": False,
        "desc":     "早上九點到圖書館，一樓滿、二樓滿、三樓也滿。最後坐在走廊地板K書。",
        "effect":   lambda p: _library_full_effect(p),
    },
    {
        "id":       "drop_crisis",
        "name":     "退選危機",
        "prob":     0.10,
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
        "prob":     0.10,
        "week_range": (1, 16),
        "is_positive": False,
        "once":     True,
        "desc":     "小福便當又漲了。這學期就這一次，但每次看到新價格還是很想罵人。",
        "effect":   lambda p: _cafeteria_price_effect(p),
    },
]


# ── 特殊突發事件（「被戴綠帽」：週末獨立，固定 5%）──────────────
SPECIAL_EVENTS = [
    {
        "id":       "green_hat",
        "name":     "被戴綠帽了",
        "prob":     0.05,
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
    if random.random() < 0.5:
        player.money += 200
        notify("✨ 老奶奶竟是董事會的人！金錢 +200")
    else:
        player.change_satisfaction(5)
        notify("😊 老奶奶一直道謝，心情好起來。自我滿足感 +5")

def _flat_tire_effect(player: Character):
    repair_cost = random.randint(100, 300)
    player.money = max(0, player.money - repair_cost)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 5)
    player.change_satisfaction(-8)
    notify(f"  🔧 修車費 {repair_cost} 元，還被教授點名。這天不用過了。")

def _oversleep_effect(player: Character):
    player.grades["參與度"] = max(0, player.grades["參與度"] - 8)
    player.change_satisfaction(-10)
    notify("  😴 睜眼十一點半，傳了一則「老師我今天身體不舒服」然後繼續躺著。")

def _scholarship_effect(player: Character):
    player.money += 300
    notify("  💰 入帳 300 元，今晚可以吃好一點了。")

def _group_project_effect(player: Character):
    player.consume_stamina(5)
    player.change_satisfaction(-12)
    if random.random() < 0.3:
        player.grades["作業"] = min(100, player.grades["作業"] + 10)
        notify("  📝 一個人做完了，教授還特別誇你。可喜可賀，但你累到說不出話。")
    else:
        notify("  😩 做完了。沒什麼好說的，就是累。")

def _add_drop_fail_effect(player: Character):
    player.change_satisfaction(-10)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 5)
    notify("  📋 加簽單被退回來了。課表就這樣，能怎樣，修就修吧。")

def _club_drinking_effect(player: Character):
    player.change_satisfaction(10)
    player.consume_stamina(8)
    notify("  🍺 喝得很盡興，當下覺得一切都值得。")
    notify("  ⚠️  但現在是凌晨兩點，明天你會後悔的。")
    return "TRIGGER_HANGOVER"

def _hangover_effect(player: Character):
    player.consume_stamina(10)
    player.change_satisfaction(-15)
    player.grades["參與度"] = max(0, player.grades["參與度"] - 10)
    notify("  🤢 頭痛、想吐、光線太刺眼。今天的課？不存在的。")

def _library_full_effect(player: Character):
    player.consume_stamina(3)
    player.grades["作業"] = max(0, player.grades["作業"] - 5)
    player.change_satisfaction(-6)
    notify("  📚 走廊地板坐了一整天，屁股麻、書沒讀多少，作業品質直接打折。")

def _drop_crisis_effect(player: Character):
    player.change_satisfaction(-12)
    player.money = max(0, player.money - 100)
    notify("  😰 截止日過了。那堂課退不掉了，只能硬撐到期末。")

def _cafeteria_price_effect(player: Character):
    extra_cost = random.randint(10, 30)
    player.money = max(0, player.money - extra_cost)
    player.change_satisfaction(-2)
    notify(f"  🍱 又漲了 {extra_cost} 元。默默付錢，默默難過。")

def _green_hat_effect(player: Character):
    player.change_satisfaction(-25)
    notify("  💔 你盯著手機螢幕看了很久，然後把它蓋起來。什麼都不想說。")
    notify("  📉 接下來幾週大概也讀不進去什麼了。")
    return "TRIGGER_GREEN_HAT_DEBUFF"


# ── EventSystem ───────────────────────────────────────────────────

class EventSystem:
    """
    突發事件管理器。

    per-action 觸發（roll_event_after_action）：
      除「被戴綠帽」外的所有事件，每次行動後各自擲骰（機率減半），
      至多一次行動觸發一個事件，且一週累計不超過 2 次。

    週末獨立觸發（roll_green_hat）：
      「被戴綠帽」固定 5%（週次 > 8），不受 per-action 計數影響。

    週末 debuff 計時（tick_debuffs）：
      每週末呼叫一次，處理持續 debuff 的週效果與倒計時。
    """

    def __init__(self, player: Character):
        self.player              = player
        self.pending_hangover    = False
        self.triggered_once      = set()
        self.active_debuffs      = []
        self.events_this_week    = 0    # 本週已觸發突發事件次數（最多 2）
        self.triggered_this_week = set()  # 本週已觸發的事件 ID（防重複）
        self.allnighter_risk     = 0.0  # 熬夜後額外睡過頭機率（累加）

    # ── 公開 API ──────────────────────────────────────────────────

    def reset_weekly_count(self):
        """每週開始時呼叫，重置本週事件計數器與已觸發集合。"""
        self.events_this_week    = 0
        self.triggered_this_week = set()

    def set_allnighter_risk(self, chance: float = 0.10) -> None:
        """熬夜後增加睡過頭額外觸發機率（可累加，最高 100%）。"""
        self.allnighter_risk = min(1.0, self.allnighter_risk + chance)

    def roll_event_after_action(self, week: int) -> bool:
        """
        每次行動結束後呼叫。
        觸發規則：
          - 宿醉（pending_hangover）：強制觸發，不受次數限制
          - 熬夜睡過頭（allnighter_risk > 0）：獨立擲骰
          - 一般事件：每週至多 2 次
          - 有週次範圍的事件 > 全學期事件（同優先級隨機選一）
        回傳 True 若有事件觸發。
        """
        player = self.player

        # 強制宿醉（不受次數上限約束，但計入計數）
        if self.pending_hangover:
            self._fire_event("hangover", None)
            self.events_this_week += 1
            return True

        # 熬夜額外睡過頭風險
        if self.allnighter_risk > 0.0:
            if random.random() < self.allnighter_risk:
                popup_text = "💤 熬夜代價：【睡過頭】\n昨晚熬夜太晚，今天完全爬不起來！"
                notify(popup_text)
                trigger_screen_shake()
                play_event_sfx(False)
                ask_ok(popup_text)
                start_notify_capture()
                _oversleep_effect(player)
                captured = stop_notify_capture()
                if captured:
                    ask_ok("📋 效果：【睡過頭】\n" + "\n".join(captured))
                self.events_this_week += 1
            self.allnighter_risk = 0.0

        # 已達本週上限
        if self.events_this_week >= 2:
            return False

        # ── 有週次範圍的候選事件（機率減半）─────────────────
        priority_candidates = []

        for pe in PHASE_EVENTS:
            s, e = pe["week_range"]
            if pe["id"] in self.triggered_this_week:
                continue
            if s <= week <= e and random.random() < pe["prob"] / 2:
                priority_candidates.append(("phase", pe))

        for we in WEEKLY_EVENTS:
            s, e = we["week_range"]
            if we["id"] in self.triggered_this_week:
                continue
            if s <= week <= e:
                if we.get("once") and we["id"] in self.triggered_once:
                    continue
                if random.random() < we["prob"] / 2:
                    priority_candidates.append(("weekly", we))

        # ── 全學期主事件候選（原 30% → 15%）─────────────────
        main_candidate = None
        eligible = [ev for ev in EVENTS
                    if ev["trigger_condition"](player)
                    and ev["id"] not in self.triggered_this_week]
        if eligible and random.random() < 0.15:
            luck_bonus = (player.luck - 50) / 100
            weighted = []
            for ev in eligible:
                w = ev["weight"]
                w *= (1 + luck_bonus) if ev["is_positive"] else (1 - luck_bonus * 0.5)
                weighted.append((ev, max(1.0, w)))
            evts, wts = zip(*weighted)
            main_candidate = ("main", random.choices(evts, weights=wts, k=1)[0])

        # ── 選取（有週次範圍 > 全學期；同級隨機一個）────────
        if priority_candidates:
            event_type, event = random.choice(priority_candidates)
        elif main_candidate:
            event_type, event = main_candidate
        else:
            return False

        self._fire_event(event_type, event)
        self.events_this_week += 1
        return True

    def roll_green_hat(self, week: int) -> None:
        """
        週末呼叫：「被戴綠帽」固定 5% 機率（週次 > 8）。
        不受 events_this_week 計數影響。
        """
        for se in SPECIAL_EVENTS:
            if (se["id"] == "green_hat"
                    and se["trigger_condition"](self.player, week)
                    and random.random() < se["prob"]):
                self._fire_event("special", se)
                break

    def tick_debuffs(self) -> None:
        """
        週末呼叫：推進所有進行中的 debuff 倒計時並執行週效果。
        """
        self._tick_debuffs()

    # ── 內部方法 ──────────────────────────────────────────────────

    def _fire_event(self, event_type: str, event):
        """執行單一事件：彈窗通知 → 效果 → 旗標處理。"""
        player = self.player

        if event_type == "hangover":
            self.pending_hangover = False
            popup_text = "⚡ 強制事件：【宿醉發作】\n昨晚喝太多，今天整個人不對勁。"
            notify(popup_text)
            trigger_screen_shake()
            play_event_sfx(False)
            ask_ok(popup_text)
            start_notify_capture()
            _hangover_effect(player)
            captured = stop_notify_capture()
            if captured:
                ask_ok("📋 效果：【宿醉發作】\n" + "\n".join(captured))
            return

        prefix = "💥 特殊事件" if event_type == "special" else "⚡ 突發事件"
        popup_text = f"{prefix}：【{event['name']}】\n{event['desc']}"
        notify(f"\n{prefix}：【{event['name']}】")
        notify(f"  {event['desc']}")
        trigger_screen_shake()
        play_event_sfx(event.get("is_positive", False))
        ask_ok(popup_text, event.get("btn_label", "確認"))

        start_notify_capture()
        result = event["effect"](player)
        captured = stop_notify_capture()
        if captured:
            ask_ok(f"📋 效果：【{event['name']}】\n" + "\n".join(captured))

        if result == "TRIGGER_HANGOVER":
            self.pending_hangover = True
        elif result == "TRIGGER_GREEN_HAT_DEBUFF":
            self._register_green_hat_debuff()

        self.triggered_this_week.add(event["id"])
        if event_type == "weekly" and event.get("once"):
            self.triggered_once.add(event["id"])

    def _register_green_hat_debuff(self):
        self.active_debuffs.append({
            "id":              "green_hat_debuff",
            "name":            "心碎狀態",
            "weeks_remaining": 4,
            "weekly_effect":   lambda p: p.change_satisfaction(-25),
        })
        notify("  🔻 心碎狀態啟動：接下來 4 週每週滿足感 -25，振作不起來。")

    def _tick_debuffs(self):
        still_active = []
        for debuff in self.active_debuffs:
            if "weekly_effect" in debuff:
                debuff["weekly_effect"](self.player)
            debuff["weeks_remaining"] -= 1
            if debuff["weeks_remaining"] > 0:
                still_active.append(debuff)
                notify(f"  ⏳ 【{debuff['name']}】還沒好，剩 {debuff['weeks_remaining']} 週。")
            else:
                notify(f"  ✅ 【{debuff['name']}】總算過去了，狀態恢復正常。")
        self.active_debuffs = still_active
