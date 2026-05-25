# ============================================================
#  模組：skill_system.py — 養成與熟練度系統
# ============================================================
# 負責「時間投入 → 熟練度 → 效益提升」的公式運算。
# 熟練度分為 4 個等級，等級越高，每次行動獲得的效益越好。
# ============================================================

from character import Character
from ui import notify

# 熟練度等級門檻（累積 exp 達到多少進入該等級）
LEVEL_THRESHOLDS = [0, 30, 60, 90]     # 等級 0、1、2、3
LEVEL_NAMES      = ["新手", "普通", "熟練", "精通"]

# 各等級的效益乘數（精通時每單位時間效益是新手的 2 倍）
LEVEL_MULTIPLIERS = [1.0, 1.3, 1.6, 2.0]

# 智力加成門檻
INTEL_THRESHOLDS = [0, 20, 40, 60, 80]
INTEL_NAMES = ["障礙", "困擾", "平均", "優秀", "聰明"]

# 各程度的效益乘數
INTEL_MULTIPLIERS = [0.6, 0.8, 1.0, 1.3, 1.6]

# ── popup 標注顏色（同一五色階）────────────────────────────────
# 智力五級
INTEL_ANNOT_COLORS = [
    (160,  40,  40),   # 障礙 — 暗紅
    ( 72,  38,  18),   # 困擾 — 深棕黑
    ( 60, 120, 200),   # 平均 — 藍色
    ( 60, 160,  75),   # 優秀 — 綠色
    (190, 140,   0),   # 聰明 — 金色
]
# 熟練度四級（對應五色階中間四格，新手略帶棕色、精通金色）
LEVEL_ANNOT_COLORS = [
    ( 72,  38,  18),   # 新手 — 深棕黑（困擾色）
    ( 60, 120, 200),   # 普通 — 藍色（平均色）
    ( 60, 160,  75),   # 熟練 — 綠色（優秀色）
    (190, 140,   0),   # 精通 — 金色（聰明色）
]
# 標注括弧與分隔符號的顏色
_ANNOT_PUNC = (105, 72, 45)


class SkillSystem:
    """
    養成系統：管理每個科目或技能的熟練度等級與成長。
    """

    def __init__(self, player: Character):
        self.player = player
        # 用字典記錄每個科目的累積 exp（會跟 player.subject_exp 同步）
        # 這裡直接引用同一個字典物件（改這裡等於改 player 裡的）
        self.exp_pool = player.subject_exp

    def gain_exp(self, subject: str, base_amount: int) -> tuple:
        """
        增加某科目的熟練度經驗值。
        實際獲得的量 = base_amount × 當前等級乘數 × 智力乘數。
        回傳 (actual_gain, annot_str, annot_color)：
          actual_gain  — 實際入帳整數
          annot_str    — 標注文字，例如「（障礙，×0.6）」
          annot_color  — 對應 RGB tuple
        """
        player = self.player

        # 如果科目不在池中，初始化為 0
        if subject not in self.exp_pool:
            self.exp_pool[subject] = 0

        level = self._get_level(subject)
        skill_multiplier = LEVEL_MULTIPLIERS[level]

        # 取得智力加成乘數
        intel_level = self._get_intel_level()
        intel_multiplier = INTEL_MULTIPLIERS[intel_level]

        # 計算實際增加量
        actual_gain = int(base_amount * skill_multiplier * intel_multiplier)

        self.exp_pool[subject] = min(100, self.exp_pool[subject] + actual_gain)
        
        # print(f"📚 [{subject}] 熟練度 +{actual_gain} "  # 因套用pygame而調整
        #     f"(熟練度等級：{LEVEL_NAMES[level]}，"
        #     f"智力程度：{INTEL_NAMES[intel_level]}，"
        #     f"目前：{self.exp_pool[subject]})")
        notify(f"📚 [{subject}] 熟練度 +{actual_gain} (熟練度等級：{LEVEL_NAMES[level]}，智力程度：{INTEL_NAMES[intel_level]}，目前：{self.exp_pool[subject]})")

        # 順便同步到 player.subject_exp（其實同一個字典，多此一舉但幫助理解）
        player.subject_exp[subject] = self.exp_pool[subject]

        # 組合多色標注區段（供 popup "multi" 行使用）
        sk_mult_str = f"×{LEVEL_MULTIPLIERS[level]:g}"
        it_mult_str = f"×{INTEL_MULTIPLIERS[intel_level]:g}"
        segments = [
            ("  （",                           _ANNOT_PUNC),
            (f"{LEVEL_NAMES[level]}{sk_mult_str}",   LEVEL_ANNOT_COLORS[level]),
            ("，",                             _ANNOT_PUNC),
            (f"{INTEL_NAMES[intel_level]}{it_mult_str}）", INTEL_ANNOT_COLORS[intel_level]),
        ]
        return actual_gain, segments

    def _get_level(self, subject: str) -> int:
        """
        根據累積 exp 回傳等級（0~3）。
        倒序遍歷門檻，找到第一個「exp >= 門檻」的就是當前等級。
        """
        exp = self.exp_pool.get(subject, 0)
        for lvl in range(len(LEVEL_THRESHOLDS) - 1, -1, -1):  # 從 3 數到 0
            if exp >= LEVEL_THRESHOLDS[lvl]:
                return lvl
        return 0

    def get_level_name(self, subject: str) -> str:
        """回傳科目的等級名稱（方便 UI 顯示）。"""
        return LEVEL_NAMES[self._get_level(subject)]

    def _get_intel_level(self) -> int:
        """
        根據玩家智力回傳智力等級索引。
        0: 障礙, 1: 困擾, 2: 平均, 3: 優秀, 4: 聰明
        """
        intel = self.player.intel

        for lvl in range(len(INTEL_THRESHOLDS) - 1, -1, -1):
            if intel >= INTEL_THRESHOLDS[lvl]:
                return lvl

        return 0

    def get_intel_level_name(self) -> str:
        """
        回傳玩家智力程度名稱，方便 UI 顯示。
        """
        return INTEL_NAMES[self._get_intel_level()]