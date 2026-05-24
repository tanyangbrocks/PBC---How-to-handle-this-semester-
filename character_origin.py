# ============================================================
#  模組：character.py — 角色狀態管理器
# ============================================================
# 這個模組負責「儲存」與「計算」所有跟角色有關的數值。
# 把角色資料集中在同一個地方，可以避免數值散落在各個檔案，
# 方便除錯與維護。
# ============================================================

import random

# ── 天賦資料庫（字典的串列）──────────────────────────────
# 每一個天賦是一個「字典」(dict)，key 是欄位名，value 是內容。
TALENTS = [
    {"id": 1, "name": "天選之人",   "desc": "運氣 +20",          "luck": 20,  "stamina": 0,  "intel": 0},
    {"id": 2, "name": "勤奮學霸",   "desc": "智力 +15",          "luck": 0,   "stamina": 0,  "intel": 15},
    {"id": 3, "name": "精力充沛",   "desc": "體力上限 +20",      "luck": 0,   "stamina": 20, "intel": 0},
    {"id": 4, "name": "富二代",     "desc": "初始金錢 +500",     "luck": 5,   "stamina": 0,  "intel": 0,  "money": 500},
    {"id": 5, "name": "社交達人",   "desc": "突發事件獎勵 +10%", "luck": 0,   "stamina": 5,  "intel": 0,  "social_bonus": 0.1},
    {"id": 6, "name": "夜貓子",     "desc": "熬夜副作用減半",   "luck": 0,   "stamina": 0,  "intel": 5,  "night_owl": True},
]

# ── 負面特質資料庫 ─────────────────────────────────────────
# 玩家選擇負面特質，換取更多能力點數
DRAWBACKS = [
    {"id": 1, "name": "路痴",       "desc": "遲到機率 +20%，換取 10 點",  "penalty": "late_chance",   "value": 0.2,  "bonus_pts": 10},
    {"id": 2, "name": "容易生病",   "desc": "生病機率 +15%，換取 15 點",  "penalty": "sick_chance",   "value": 0.15, "bonus_pts": 15},
    {"id": 3, "name": "購物狂",     "desc": "每週自動花費 50 元，換取 10 點", "penalty": "weekly_cost", "value": 50,  "bonus_pts": 10},
]


class Character:
    """
    「類別」(Class) 是 Python 的物件導向寫法。
    可以想成：Character 是一張「角色卡模板」，
    每次 Character(...) 就印出一張填好數值的卡。
    """

    def __init__(self, name: str, department: str,
                 stamina: int, intel: int, luck: int, money: int,
                 talent: dict, drawbacks: list):
        """
        __init__ 是「建構子」，當你寫 Character(...) 時會自動執行，
        負責把傳入的參數存到 self（自己這張角色卡）上。
        """
        self.name       = name          # 角色名字
        self.department = department    # 系級

        # ── 基礎能力值 ──────────────────────────────────
        self.stamina_max = stamina      # 體力上限（最大值）
        self.stamina     = stamina      # 當前體力
        self.intel       = intel        # 智力
        self.luck        = luck         # 運氣（影響機率）
        self.money       = money        # 金錢

        # ── 特殊設定 ─────────────────────────────────────
        self.talent   = talent          # 天賦（字典）
        self.drawbacks = drawbacks      # 負面特質列表

        # ── 隱藏數值：自我滿足感 ─────────────────────────
        # 初始值 80，低於 60 就進入無力狀態
        self.satisfaction = 80

        # ── 狀態效果 (Buff / Debuff) ─────────────────────
        # 用一個「字典」記錄所有暫時效果，例如 {"感冒": 2} 代表感冒還剩 2 週
        self.status_effects: dict[str, int] = {}

        # ── 成績相關 ─────────────────────────────────────
        # 用字典存各科的學習熟練度（0~100）
        self.subject_exp: dict[str, int] = {
            "商管程式設計": 0,
            "統計學":       0,
            "經濟學":       0,
            "管理學":       0,
            "會計學":       0,
        }

        # 各科作業、小考等分數（最終計算用）
        self.grades: dict[str, float] = {
            "參與度": 0.0,
            "作業":   0.0,
            "小考":   0.0,
            "期中":   0.0,
            "期末":   0.0,
        }

        # 套用天賦加成
        self._apply_talent()

    # ────────────────────────────────────────────────────────
    #  工廠方法：引導玩家一步步建立角色
    # ────────────────────────────────────────────────────────
    @classmethod
    def create_new(cls) -> "Character":
        """
        @classmethod 代表這個方法屬於「類別本身」而非某個實例。
        可以想成這是一個「角色創建嚮導」，走完之後回傳一個建好的 Character。
        """
        print("\n【角色創建】")
        name = input("請輸入角色名字：").strip() or "無名大學生"

        # 選擇系級
        departments = ["資管系", "企管系", "財金系", "會計系"]
        print("\n請選擇系級：")
        for i, d in enumerate(departments, start=1):  # enumerate 同時給編號與內容
            print(f"  {i}. {d}")
        dept_idx = cls._safe_int_input("輸入編號：", 1, len(departments)) - 1
        department = departments[dept_idx]

        # 能力點分配（初始 50 點，可用負面特質換更多）
        base_pts = 50
        chosen_drawbacks = cls._pick_drawbacks(base_pts)
        total_pts = base_pts + sum(d["bonus_pts"] for d in chosen_drawbacks)

        print(f"\n你共有 {total_pts} 點可分配（體力 / 智力 / 運氣）")
        stamina, intel, luck, remaining = cls._distribute_points(total_pts)

        # 剩餘點數轉換為初始金錢
        money = 300 + remaining * 10

        # 抽取天賦（隨機抽 3 張，選 1 張）
        talent = cls._pick_talent()

        # 套用天賦金錢加成
        money += talent.get("money", 0)

        return cls(name, department, stamina, intel, luck, money, talent, chosen_drawbacks)
    


    # ────────────────────────────────────────────────────────
    #  角色行為方法
    # ────────────────────────────────────────────────────────
    def consume_stamina(self, amount: int) -> bool:
        """
        消耗體力。
        回傳 True 表示成功，False 表示體力不足（角色生病）。
        """
        self.stamina -= amount
        if self.stamina < 0:
            self.stamina = 0
            self.add_status("生病", duration=2)  # 體力歸零 → 生病 2 週
            print("⚠ 你累壞了，生病了！本週與下週行動效率大幅下降。")
            return False
        return True

    def restore_stamina(self, amount: int):
        """恢復體力，但不能超過上限。"""
        self.stamina = min(self.stamina + amount, self.stamina_max)

    def change_satisfaction(self, delta: int):
        """
        改變自我滿足感，並夾在 0~100 之間。
        delta > 0 是增加，delta < 0 是減少。
        """
        self.satisfaction = max(0, min(100, self.satisfaction + delta))
        if self.satisfaction < 60:
            print("😞 自我滿足感過低，你陷入無力狀態……本週可支配時間大幅下降。")

    def add_status(self, name: str, duration: int):
        """新增狀態效果，duration 是持續週數。"""
        self.status_effects[name] = duration
        print(f"  ➕ 獲得狀態：【{name}】（持續 {duration} 週）")

    def tick_status_effects(self):
        """
        每週結束時呼叫，把所有狀態效果的剩餘週數 -1，
        並移除已過期的效果。
        """
        # 先找出要移除的（不能在迭代中直接刪，所以先收集）
        expired = [name for name, weeks in self.status_effects.items() if weeks <= 1]
        for name in expired:
            del self.status_effects[name]
            print(f"  ➖ 狀態解除：【{name}】")
        # 其餘 -1
        for name in self.status_effects:
            self.status_effects[name] -= 1

    def get_effective_time(self) -> int:
        """
        計算本週「有效可支配時間單位」。
        基礎為 10，自我滿足感 < 60 時縮減為 5，
        各種狀態也會影響。
        """
        base_time = 10
        if self.satisfaction < 60:
            base_time = 5        # 失落狀態
        if "生病" in self.status_effects:
            base_time -= 3       # 生病扣時間
        if "疲勞" in self.status_effects:
            base_time -= 2      # 疲勞扣時間
        if "激勵" in self.status_effects:
            base_time += 2       # 激勵加時間
        return max(1, base_time) # 至少 1，避免除以零的問題

    def is_game_over(self) -> bool:
        """判斷是否觸發 Game Over 條件。"""
        if self.stamina <= 0 and "生病" in self.status_effects:
            return False         # 生病可以撐過，不直接 Game Over
        if self.satisfaction <= 0:
            return True          # 滿足感歸零 → 心理崩潰
        return False

    def calculate_final_score(self) -> float:
        """
        計算最終加權成績：
          參與度 10% + 作業 20% + 小考 10% + 期中 30% + 期末 30%
        """
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
    #  私有輔助方法（名稱前加底線代表「內部使用」）
    # ────────────────────────────────────────────────────────
    def _apply_talent(self):
        """把天賦的數值加成套用到角色身上。"""
        t = self.talent
        self.luck        += t.get("luck",    0)  # .get() 找不到 key 時回傳預設值 0
        self.stamina_max += t.get("stamina", 0)
        self.stamina      = self.stamina_max
        self.intel       += t.get("intel",   0)

    @staticmethod
    def _pick_talent() -> dict:
        """隨機抽 3 張天賦，讓玩家選一張。@staticmethod 不需要 self，單純是工具函式。"""
        candidates = random.sample(TALENTS, k=3)  # 不重複地抽 3 張
        print("\n【天賦選擇】抽到以下三張，請選一張：")
        for i, t in enumerate(candidates, start=1):
            print(f"  {i}. {t['name']}：{t['desc']}")
        idx = Character._safe_int_input("選擇：", 1, 3) - 1
        return candidates[idx]

    @staticmethod
    def _pick_drawbacks(base_pts: int) -> list:
        """讓玩家自由選擇 0~2 個負面特質，換取額外能力點。"""
        chosen = []
        print("\n【負面特質】選擇負面特質可換取額外點數（最多 2 個，直接按 Enter 跳過）：")
        for d in DRAWBACKS:
            print(f"  {d['id']}. {d['name']}：{d['desc']}")
            ans = input("要選嗎？(y/N)：").strip().lower()
            if ans == "y":
                chosen.append(d)
            if len(chosen) >= 2:
                break
        return chosen

    @staticmethod
    def _distribute_points(total: int) -> tuple[int, int, int, int]:
        """
        讓玩家把點數分配到體力、智力、運氣。
        回傳 (stamina, intel, luck, remaining)。
        """
        print(f"\n【能力點分配】共 {total} 點，分配到體力 / 智力 / 運氣")
        while True:
            stamina = Character._safe_int_input("體力（建議 10~40）：", 0, total)
            intel   = Character._safe_int_input("智力（建議 10~40）：", 0, total - stamina)
            luck    = Character._safe_int_input("運氣（建議 10~40）：", 0, total - stamina - intel)
            remaining = total - stamina - intel - luck
            print(f"  ➜ 剩餘 {remaining} 點將轉換為初始金錢（+{remaining * 10} 元）")
            confirm = input("確認？(Y/n)：").strip().lower()
            if confirm != "n":
                return stamina, intel, luck, remaining

    @staticmethod
    def _safe_int_input(prompt: str, lo: int, hi: int) -> int:
        """安全地讀取整數輸入，避免玩家亂輸入導致程式崩潰。"""
        while True:
            try:
                val = int(input(prompt))
                if lo <= val <= hi:
                    return val
                print(f"  請輸入 {lo} ~ {hi} 之間的整數。")
            except ValueError:
                print("  請輸入數字！")

    def __repr__(self) -> str:
        """
        __repr__ 讓 print(player) 時顯示有意義的資訊，
        而不是一串記憶體位址。方便除錯。
        """
        return (f"<Character {self.name} | "
                f"體力:{self.stamina}/{self.stamina_max} "
                f"智力:{self.intel} 運氣:{self.luck} "
                f"金錢:{self.money} 滿足感:{self.satisfaction}>")
