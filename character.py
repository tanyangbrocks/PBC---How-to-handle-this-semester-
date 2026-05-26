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
                ask_cc_name, ask_cc_dept,
                ask_cc_drawbacks, ask_cc_stats, ask_cc_talent)

# ── 天賦資料庫 ────────────────────────────────────────────────
TALENTS = [
    {"id": 1, "name": "天選之人",   "desc": "運氣 +20",          "luck": 20,  "stamina": 0,  "intel": 0},
    {"id": 2, "name": "勤奮學霸",   "desc": "智力 +15",          "luck": 0,   "stamina": 0,  "intel": 15},
    {"id": 3, "name": "精力充沛",   "desc": "體力上限 +20",      "luck": 0,   "stamina": 20, "intel": 0},
    {"id": 4, "name": "富二代",     "desc": "初始金錢 +500",     "luck": 5,   "stamina": 0,  "intel": 0,  "money": 500},
    {"id": 5, "name": "社交達人",   "desc": "突發事件獎勵 +10%", "luck": 0,   "stamina": 5,  "intel": 0,  "social_bonus": 0.1},
    {"id": 6, "name": "夜貓子",     "desc": "熬夜副作用減半",   "luck": 0,   "stamina": 0,  "intel": 5,  "night_owl": True},
]

# ── 負面特質資料庫 ────────────────────────────────────────────
DRAWBACKS = [
    {"id": 1, "name": "路痴",       "desc": "遲到機率 +20%，換取 10 點",      "penalty": "late_chance",   "value": 0.2,  "bonus_pts": 10},
    {"id": 2, "name": "容易生病",   "desc": "生病機率 +15%，換取 15 點",      "penalty": "sick_chance",   "value": 0.15, "bonus_pts": 15},
    {"id": 3, "name": "購物狂",     "desc": "每週自動花費 50 元，換取 10 點", "penalty": "weekly_cost",   "value": 50,   "bonus_pts": 10},
]


class Character:

    def __init__(self, name: str, department: str,
                 stamina: int, intel: int, luck: int, money: int,
                 talent: dict, drawbacks: list):
        self.name       = name
        self.department = department
        self.stamina_max = stamina
        self.stamina     = stamina
        self.intel       = intel
        self.luck        = luck
        self.money       = money
        self.talent      = talent
        self.drawbacks   = drawbacks
        self.satisfaction = 80
        self.status_effects: dict[str, int] = {}
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

    # ────────────────────────────────────────────────────────
    #  工廠方法：角色創建精靈
    # ────────────────────────────────────────────────────────
    @classmethod
    def create_new(cls) -> "Character":
        # ── 切換到角色創建專屬畫面 ──────────────────────────────
        begin_char_create()

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

        # 3. 選擇負面特質（最多 2 個）
        base_pts         = random.randint(30, 70)
        chosen_drawbacks = ask_cc_drawbacks(DRAWBACKS, 2)
        bonus_pts        = sum(d["bonus_pts"] for d in chosen_drawbacks)
        total_pts        = base_pts + bonus_pts

        # 4. 選擇天賦（從 TALENTS 隨機抽 3 張）
        candidates = random.sample(TALENTS, k=3)
        talent = ask_cc_talent(candidates)

        # 5. 分配能力點（天賦加成顯示在面板上）
        stamina, intel, luck = ask_cc_stats(total_pts, base_pts, talent)
        remaining = total_pts - stamina - intel - luck
        money = 300 + remaining * 10 + talent.get("money", 0)

        # ── 切回一般遊戲畫面 ─────────────────────────────────────
        end_char_create()

        notify(f"\n角色創建完成！{name}（{department}）準備迎接這學期的挑戰。")
        return cls(name, department, stamina, intel, luck, money, talent, chosen_drawbacks)

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
        expired = [name for name, weeks in self.status_effects.items() if weeks <= 1]
        for name in expired:
            del self.status_effects[name]
            # print(f"  ➖ 狀態解除：【{name}】")  # 因套用pygame而調整
            notify(f"  ➖ 狀態解除：【{name}】")
        for name in self.status_effects:
            self.status_effects[name] -= 1

    def get_effective_time(self) -> int:
        base_time = 10
        if self.satisfaction < 60:
            base_time = 5
        if "生病" in self.status_effects:
            base_time -= 3
        if "疲勞" in self.status_effects:
            base_time -= 2
        if "激勵" in self.status_effects:
            base_time += 2
        return max(1, base_time)

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
        self.luck        += t.get("luck",    0)
        self.stamina_max += t.get("stamina", 0)
        self.stamina      = self.stamina_max
        self.intel       += t.get("intel",   0)

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
