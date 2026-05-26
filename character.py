# ============================================================
#  模組：character.py — 角色狀態管理器（pygame 版）
# ============================================================
# 與 character_origin.py 的差異：
#   - 所有 print() 改為 notify()
#   - 所有 input() 改為 ask_text() / ask_choice() / ask_yn()
#   - create_new() 的線性精靈流程保持不變，
#     每個 ask_* 呼叫都是阻塞的（遊戲執行緒等待 pygame 事件），
#     所以邏輯順序無需改動。
# ============================================================

import random
from ui import (notify, ask_text, ask_choice, ask_yn,
                begin_char_create, end_char_create,
                ask_cc_name, ask_cc_dept, ask_cc_de_level,
                ask_cc_drawbacks, ask_cc_stats, ask_cc_talent,
                ask_cc_extra_events, ask_cc_summary)

# ── 年級資料庫 ────────────────────────────────────────────────
DE_LEVELS = [
    {"name": "大一", "base_time": 5,  "intel": 0,  "luck": 5},
    {"name": "大二", "base_time": 0,  "intel": 5,  "luck": 10},
    {"name": "大三", "base_time": 5,  "intel": 10, "luck": 5},
    {"name": "大四", "base_time": 10, "intel": 5,  "luck": 5},
]

# ── 天賦資料庫 ────────────────────────────────────────────────
TALENTS = [
    {"id": 1, "name": "天選之人",   "prob": 1,  "desc": "智力+10，運氣+10",             "intel": 10, "luck": 10},
    {"id": 2, "name": "勤奮學霸",   "prob": 5,  "desc": "時間+1，智力+10",              "base_time": 1,  "intel": 10},
    {"id": 3, "name": "勤奮學渣",   "prob": 5,  "desc": "運氣+5，可用時間×0.9",         "luck": 5,   "base_time_mult": 0.9},
    {"id": 4, "name": "富二代",     "prob": 5,  "desc": "初始金錢+500",                  "money": 500},
    {"id": 5, "name": "社交達人",   "prob": 5,  "desc": "可用時間+4",                    "base_time": 4},
    {"id": 6, "name": "夜貓子",     "prob": 5,  "desc": "熬夜行動時間×1.5",             "night_owl_mult": 1.5},
    {"id": 7, "name": "路痴",       "prob": 5,  "desc": "時間-1，能力點+5",              "base_time": -1, "base_pts_bonus": 5},
    {"id": 8, "name": "抵抗力低下", "prob": 5,  "desc": "滿足感<70時易生病，能力點+15", "sick_threshold": 70, "base_pts_bonus": 15},
    {"id": 0, "name": "無天賦",     "prob": 64, "desc": ""},
]

# ── 負面特質資料庫 ────────────────────────────────────────────
EXTRA_EVENTS = [
    {
        "id":          "part_time",
        "name":        "打工",
        "time_cost":   3,
        "money_delta": 500,
        "intel_req":   0,
        "exclusive":   ["tutoring"],
        "popup_color": (235, 130, 30),
    },
    {
        "id":          "tutoring",
        "name":        "家教",
        "time_cost":   2,
        "money_delta": 350,
        "intel_req":   75,
        "exclusive":   ["part_time"],
        "popup_color": (200, 50, 50),
    },
    {
        "id":          "club",
        "name":        "參加社團",
        "time_cost":   0,
        "money_delta": -260,
        "intel_req":   0,
        "exclusive":   [],
        "popup_color": (110, 50, 185),
    },
]

DRAWBACKS = [
    {"id": 1, "name": "路痴",       "desc": "遲到機率 +20%，換取 10 點",      "penalty": "late_chance",   "value": 0.2,  "bonus_pts": 10},
    {"id": 2, "name": "容易生病",   "desc": "生病機率 +15%，換取 15 點",      "penalty": "sick_chance",   "value": 0.15, "bonus_pts": 15},
    {"id": 3, "name": "購物狂",     "desc": "每週自動花費 50 元，換取 10 點", "penalty": "weekly_cost",   "value": 50,   "bonus_pts": 10},
]


class Character:

    def __init__(self, name: str, department: str,
                 stamina: int, intel: int, luck: int, money: int,
                 talent: dict, drawbacks: list, de_level: dict = None,
                 extra_events: list = None, slot_results: list = None):
        self.name       = name
        self.department = department
        self.stamina_max = stamina
        self.stamina     = stamina
        self.intel       = intel
        self.luck        = luck
        self.money       = money
        self.talent      = talent
        self.drawbacks   = drawbacks
        self.extra_events = list(extra_events or [])
        self.slot_results = list(slot_results or [])
        self.de_level    = de_level or {"name": "大一", "base_time": 5, "intel": 0, "luck": 5}
        self.base_time_bonus = self.de_level.get("base_time", 0)
        self.base_time_mult  = 1.0
        self.night_owl_mult  = 1.0
        self.sick_threshold  = 0
        self.satisfaction = 80
        self.status_effects: dict[str, int] = {}
        self.revealed_grades: set = set()   # 已公布、可在面板顯示的成績 key
        self.subject_exp: dict[str, int] = {
            "商管程式設計": 0,
            "統計學":       0,
            "經濟學":       0,
            "管理學":       0,
            "會計學":       0,
        }
        self.grades: dict[str, float] = {
            "參與度": 0.0,
            "作業":   0.0,
            "小考":   0.0,
            "期中":   0.0,
            "期末":   0.0,
        }
        self._apply_talent()
        self._apply_de_level()

    # ────────────────────────────────────────────────────────
    #  工廠方法：角色創建精靈
    # ────────────────────────────────────────────────────────
    @classmethod
    def create_new(cls) -> "Character":
        # ── 切換到角色創建專屬畫面 ──────────────────────────────
        begin_char_create()

        while True:
            # 1. 輸入名字
            name = ask_cc_name("請輸入角色名字").strip() or "無名大學生"

            # 2. 選擇系級
            departments = [
                "文學院", "理學院", "社會科學院", "醫學院",
                "工學院", "生物資源暨農學院", "管理學院", "公共衛生學院",
                "電機資訊學院", "法律學院", "生命科學院",
            ]
            dept_idx    = ask_cc_dept(departments) - 1
            department  = departments[dept_idx]

            # 2.5. 選擇年級
            de_level = ask_cc_de_level(DE_LEVELS)

            # 3. 選擇負面特質（最多 2 個）
            base_pts         = random.randint(30, 70)
            chosen_drawbacks = ask_cc_drawbacks(DRAWBACKS, 2)
            bonus_pts        = sum(d["bonus_pts"] for d in chosen_drawbacks)
            total_pts        = base_pts + bonus_pts

            # 4. 拉霸機抽天賦（3 槽，玩家觀看動畫）
            slot_results    = cls._draw_slots()
            ask_cc_talent(slot_results)                           # 觸發動畫，不需回傳值
            combined_talent = cls._combine_talents(slot_results)
            talent_base_pts = sum(t.get("base_pts_bonus", 0)
                                  for t in slot_results if t["name"] != "無天賦")
            total_pts += talent_base_pts

            # 5. 分配能力點（天賦 + 年級加成顯示在面板上）
            stamina, intel, luck = ask_cc_stats(total_pts, base_pts, combined_talent, de_level)
            remaining = total_pts - stamina - intel - luck
            money = 300 + remaining * 10 + combined_talent.get("money", 0)

            # 6. 選擇額外事件（依最終智力判斷可選項目）
            final_intel = (intel
                           + combined_talent.get("intel", 0)
                           + de_level.get("intel", 0))
            extra_evs = ask_cc_extra_events(EXTRA_EVENTS, final_intel)

            # 7. 玩家資訊一覽（確認或重新創建）
            summary = {
                "name":            name,
                "department":      department,
                "de_level":        de_level,
                "base_pts":        base_pts,
                "total_pts":       total_pts,
                "stamina":         stamina,
                "intel":           intel,
                "luck":            luck,
                "money":           money,
                "combined_talent": combined_talent,
                "slot_results":    slot_results,
                "drawbacks":       chosen_drawbacks,
                "extra_ev_ids":    extra_evs,
                "extra_ev_data":   EXTRA_EVENTS,
            }
            result = ask_cc_summary(summary)
            if result == "start":
                break
            # result == "restart"：清除資料，重新從姓名輸入

        # ── 切回一般遊戲畫面 ─────────────────────────────────────
        end_char_create()

        notify(f"\n角色創建完成！{name}（{department} {de_level['name']}）準備迎接這學期的挑戰。")
        return cls(name, department, stamina, intel, luck, money, combined_talent,
                   chosen_drawbacks, de_level, extra_evs, slot_results)

    # ────────────────────────────────────────────────────────
    #  角色行為方法
    # ────────────────────────────────────────────────────────
    def consume_stamina(self, amount: int) -> bool:
        self.stamina -= amount
        if self.stamina < 0:
            self.stamina = 0
            self.add_status("生病", duration=2)
            # print("⚠ 你累壞了，生病了！本週與下週行動效率大幅下降。")  # 因套用pygame而調整
            notify("⚠ 你累壞了，生病了！本週與下週行動效率大幅下降。")
            return False
        return True

    def restore_stamina(self, amount: int):
        self.stamina = min(self.stamina + amount, self.stamina_max)

    def change_satisfaction(self, delta: int):
        self.satisfaction = max(0, min(100, self.satisfaction + delta))
        if self.satisfaction < 60:
            # print("😞 自我滿足感過低，你陷入無力狀態……本週可支配時間大幅下降。")  # 因套用pygame而調整
            notify("😞 自我滿足感過低，你陷入無力狀態……本週可支配時間大幅下降。")

    def add_status(self, name: str, duration: int):
        self.status_effects[name] = duration
        # print(f"  ➕ 獲得狀態：【{name}】（持續 {duration} 週）")  # 因套用pygame而調整
        notify(f"  ➕ 獲得狀態：【{name}】（持續 {duration} 週）")

    def tick_status_effects(self):
        if self.sick_threshold > 0 and self.satisfaction < self.sick_threshold \
                and "生病" not in self.status_effects:
            self.add_status("生病", duration=1)
        expired = [name for name, weeks in self.status_effects.items() if weeks <= 1]
        for name in expired:
            del self.status_effects[name]
            # print(f"  ➖ 狀態解除：【{name}】")  # 因套用pygame而調整
            notify(f"  ➖ 狀態解除：【{name}】")
        for name in self.status_effects:
            self.status_effects[name] -= 1

    def get_effective_time(self) -> int:
        base_time = 10 + self.base_time_bonus
        if self.satisfaction < 60:
            base_time = 5 + self.base_time_bonus
        if "生病" in self.status_effects:
            base_time -= 3
        if "疲勞" in self.status_effects:
            base_time -= 2
        if "激勵" in self.status_effects:
            base_time += 2
        return max(1, int(base_time * self.base_time_mult))

    def is_game_over(self) -> bool:
        if self.stamina <= 0 and "生病" in self.status_effects:
            return False
        if self.satisfaction <= 0:
            return True
        return False

    def calculate_final_score(self) -> float:
        weights = {
            "參與度": 0.10,
            "作業":   0.20,
            "小考":   0.10,
            "期中":   0.30,
            "期末":   0.30,
        }
        score = sum(self.grades[item] * w for item, w in weights.items())
        return round(score, 2)

    # ────────────────────────────────────────────────────────
    #  私有輔助方法
    # ────────────────────────────────────────────────────────
    def _apply_talent(self):
        t = self.talent
        self.luck            += t.get("luck",           0)
        self.stamina_max     += t.get("stamina",        0)
        self.stamina          = self.stamina_max
        self.intel           += t.get("intel",          0)
        self.base_time_bonus += t.get("base_time",      0)
        self.base_time_mult   = t.get("base_time_mult", 1.0)
        self.night_owl_mult   = t.get("night_owl_mult", 1.0)
        self.sick_threshold   = t.get("sick_threshold", 0)

    def _apply_de_level(self):
        d = self.de_level
        self.intel += d.get("intel", 0)
        self.luck  += d.get("luck",  0)

    @classmethod
    def _draw_slots(cls) -> list:
        """拉霸機抽 3 槽；若前兩槽均為無天賦，第三槽保底抽到天賦。"""
        pool        = TALENTS
        weights     = [t["prob"] for t in pool]
        non_null    = [t for t in pool if t["name"] != "無天賦"]
        nn_weights  = [t["prob"] for t in non_null]
        results = []
        for i in range(3):
            if i == 2 and all(r["name"] == "無天賦" for r in results):
                drawn = random.choices(non_null, weights=nn_weights, k=1)[0]
            else:
                drawn = random.choices(pool, weights=weights, k=1)[0]
            results.append(drawn)
        return results

    @staticmethod
    def _combine_talents(drawn: list) -> dict:
        """合併所有非無天賦天賦的數值（加法；乘數型 key 用乘法；門檻取最大值）。"""
        combined = {}
        _ADDITIVE = ("luck", "intel", "stamina", "base_time", "money")
        for t in drawn:
            if t["name"] == "無天賦":
                continue
            for k, v in t.items():
                if k in ("id", "name", "prob", "desc", "base_pts_bonus"):
                    continue
                if k in ("base_time_mult", "night_owl_mult"):
                    combined[k] = combined.get(k, 1.0) * v
                elif k == "sick_threshold":
                    combined[k] = max(combined.get(k, 0), v)
                elif k in _ADDITIVE:
                    combined[k] = combined.get(k, 0) + v
                else:
                    combined[k] = v
        return combined

    @staticmethod
    def _pick_talent() -> dict:
        candidates = random.sample(TALENTS, k=3)
        # print("\n【天賦選擇】抽到以下三張，請選一張：")  # 因套用pygame而調整
        notify("\n【天賦選擇】抽到以下三張，請選一張：")
        # for i, t in enumerate(candidates, start=1):  # 因套用pygame而調整
        #     print(f"  {i}. {t['name']}：{t['desc']}")
        # idx = Character._safe_int_input("選擇：", 1, 3) - 1  # 因套用pygame而調整
        for t in candidates:
            notify(f"  • {t['name']}：{t['desc']}")
        while True:
            choice = ask_choice([f"{t['name']}：{t['desc']}" for t in candidates])
            if choice > 0:
                return candidates[choice - 1]
            notify("  請選擇一個天賦！")

    @staticmethod
    def _pick_drawbacks(base_pts: int) -> list:
        chosen = []
        # print("\n【負面特質】選擇負面特質可換取額外點數（最多 2 個，直接按 Enter 跳過）：")  # 因套用pygame而調整
        notify("\n【負面特質】選擇負面特質可換取額外點數（最多 2 個）：")
        for d in DRAWBACKS:
            if len(chosen) >= 2:
                break
            # print(f"  {d['id']}. {d['name']}：{d['desc']}")  # 因套用pygame而調整
            notify(f"  {d['id']}. {d['name']}：{d['desc']}")
            # ans = input("要選嗎？(y/N)：").strip().lower()  # 因套用pygame而調整
            ans = ask_yn(f"要選擇「{d['name']}」嗎？")
            if ans:
                chosen.append(d)
                notify(f"  ✔ 選擇了【{d['name']}】，可獲得 {d['bonus_pts']} 點。")
        return chosen

    @staticmethod
    def _distribute_points(total: int) -> tuple:
        # print(f"\n【能力點分配】共 {total} 點，分配到體力 / 智力 / 運氣")  # 因套用pygame而調整
        notify(f"\n【能力點分配】共 {total} 點，分配到體力 / 智力 / 運氣")
        while True:
            # stamina = Character._safe_int_input("體力（建議 10~40）：", 0, total)  # 因套用pygame而調整
            stamina = Character._safe_int_input(f"體力（建議 10~40）", 0, total)
            # intel   = Character._safe_int_input("智力（建議 10~40）：", 0, total - stamina)  # 因套用pygame而調整
            intel   = Character._safe_int_input(f"智力（建議 10~40）", 0, total - stamina)
            # luck    = Character._safe_int_input("運氣（建議 10~40）：", 0, total - stamina - intel)  # 因套用pygame而調整
            luck    = Character._safe_int_input(f"運氣（建議 10~40）", 0, total - stamina - intel)
            remaining = total - stamina - intel - luck
            # print(f"  ➜ 剩餘 {remaining} 點將轉換為初始金錢（+{remaining * 10} 元）")  # 因套用pygame而調整
            notify(f"  ➜ 剩餘 {remaining} 點將轉換為初始金錢（+{remaining * 10} 元）")
            # confirm = input("確認？(Y/n)：").strip().lower()  # 因套用pygame而調整
            confirm = ask_yn("確認這樣分配嗎？")
            if confirm:
                return stamina, intel, luck, remaining
            notify("  重新分配點數。")

    @staticmethod
    def _safe_int_input(prompt: str, lo: int, hi: int) -> int:
        # 若範圍只有一個值，直接回傳，不需要詢問
        if lo == hi:
            notify(f"  {prompt}：{lo}（自動填入）")
            return lo
        while True:
            # try:  # 因套用pygame而調整
            #     val = int(input(prompt))
            #     if lo <= val <= hi:
            #         return val
            #     print(f"  請輸入 {lo} ~ {hi} 之間的整數。")
            # except ValueError:
            #     print("  請輸入數字！")
            raw = ask_text(f"{prompt}（請輸入 {lo}~{hi} 的整數）")
            try:
                val = int(raw)
                if lo <= val <= hi:
                    return val
                notify(f"  請輸入 {lo} ~ {hi} 之間的整數。")
            except ValueError:
                notify("  請輸入數字！")

    def __repr__(self) -> str:
        return (f"<Character {self.name} | "
                f"體力:{self.stamina}/{self.stamina_max} "
                f"智力:{self.intel} 運氣:{self.luck} "
                f"金錢:{self.money} 滿足感:{self.satisfaction}>")
