# ============================================================
#  tests/test_turn_engine_logic.py — TurnEngine 邏輯單元測試
#  （不需要 pygame / UI；已在 conftest.py mock 掉 ui）
# ============================================================
import pytest
import random
from unittest.mock import MagicMock, patch

from character import Character, EXTRA_EVENTS
from turn_engine import TurnEngine, ACTIONS, SPECIAL_ACTIONS


# ──────────────────────────────────────────────────────────────
#  測試輔助
# ──────────────────────────────────────────────────────────────
DE_DEFAULT = {"name": "大一", "base_time": 5, "intel": 0, "luck": 5}

def make_char(stamina=50, intel=50, luck=50, money=300,
              satisfaction=80, talent=None, drawbacks=None):
    p = Character(
        name="TestPlayer",
        department="管理學院",
        stamina=stamina, intel=intel, luck=luck, money=money,
        talent=talent or {}, drawbacks=drawbacks or [],
        de_level=DE_DEFAULT,
    )
    p.satisfaction = satisfaction
    return p

def make_engine(player=None):
    """建立一個 TurnEngine，event_sys / skill_sys / shop 全用 MagicMock。"""
    if player is None:
        player = make_char()
    te = TurnEngine(
        player=player,
        event_sys=MagicMock(),
        skill_sys=MagicMock(),
        shop=MagicMock(),
    )
    return te


# ──────────────────────────────────────────────────────────────
#  1. ACTIONS / SPECIAL_ACTIONS 資料完整性
# ──────────────────────────────────────────────────────────────
class TestActionDataIntegrity:
    REQUIRED_FIELDS = ("id", "name", "stamina_cost", "exp_gain", "satisfaction", "desc")

    def test_actions_required_fields(self):
        for a in ACTIONS:
            for f in self.REQUIRED_FIELDS:
                assert f in a, f"ACTIONS[{a.get('id','?')}] 缺少欄位 {f}"

    def test_special_actions_required_fields(self):
        required = ("id", "name", "stamina_cost")
        for sa in SPECIAL_ACTIONS:
            for f in required:
                assert f in sa, f"SPECIAL_ACTIONS[{sa.get('id','?')}] 缺少欄位 {f}"

    def test_action_ids_unique(self):
        ids = [a["id"] for a in ACTIONS]
        assert len(ids) == len(set(ids)), f"ACTIONS 有重複 id: {ids}"

    def test_special_action_ids_unique(self):
        ids = [sa["id"] for sa in SPECIAL_ACTIONS]
        assert len(ids) == len(set(ids)), f"SPECIAL_ACTIONS 有重複 id: {ids}"

    def test_no_negative_exp_gain(self):
        """一般行動的 exp_gain 不應為負（體力消耗才會負）。"""
        for a in ACTIONS:
            assert a["exp_gain"] >= 0, f"ACTIONS[{a['id']}].exp_gain 為負值 {a['exp_gain']}"


# ──────────────────────────────────────────────────────────────
#  2. _calculate_exam_score — 輸出範圍與公式
# ──────────────────────────────────────────────────────────────
class TestCalculateExamScore:
    def test_output_always_in_range(self):
        """無論輸入，分數應在 [0, 100]。"""
        for stamina in (0, 25, 50, 100):
            for intel in (0, 30, 60, 100):
                for luck in (0, 30, 60, 100):
                    p = make_char(stamina=stamina, intel=intel, luck=luck)
                    # 設定不同熟練度情境
                    for exp in (0, 30, 60, 90):
                        for subj in p.subject_exp:
                            p.subject_exp[subj] = exp
                        te = make_engine(p)
                        score = te._calculate_exam_score("期中")
                        assert 0.0 <= score <= 100.0, (
                            f"期中分數越界 {score} (intel={intel}, luck={luck}, exp={exp})"
                        )
                        score = te._calculate_exam_score("期末")
                        assert 0.0 <= score <= 100.0, (
                            f"期末分數越界 {score}"
                        )

    def test_midterm_uses_exp_times_2_plus_10(self):
        """期中公式：avg_exp = mean(exp*2+10)，期末 = mean(exp)。"""
        # 注意：大一 de_level 讓 luck += 5，故傳入 luck=45 使實際 luck=50，
        # 讓 (luck-50)/500 = 0，便於精確計算。
        p = make_char(intel=50, luck=45)
        for subj in p.subject_exp:
            p.subject_exp[subj] = 20
        te = make_engine(p)

        # 固定 random.uniform 到 0（讓 luck_roll = (50-50)/500 + 0 = 0）
        with patch("turn_engine.random.uniform", return_value=0.0):
            midterm = te._calculate_exam_score("期中")
            final   = te._calculate_exam_score("期末")

        # 期中 avg_exp = 20*2+10 = 50；期末 avg_exp = 20
        # intel_bonus = 1 + min(50/200, 0.5) = 1.25；luck_multiplier = 1.0
        expected_mid   = min(100.0, 50 * 1.25 * 1.0)   # 62.5
        expected_final = min(100.0, 20 * 1.25 * 1.0)   # 25.0
        assert midterm == pytest.approx(expected_mid,   abs=1e-6)
        assert final   == pytest.approx(expected_final, abs=1e-6)

    def test_high_intel_bonus_capped(self):
        """intel_bonus 最高 1.5（intel/200 夾鉗在 0.5）。"""
        # luck=45 → 大一 +5 → 實際 luck=50，消除 luck_roll 的 luck 分量
        p = make_char(intel=200, luck=45)
        for subj in p.subject_exp:
            p.subject_exp[subj] = 30
        te = make_engine(p)
        with patch("turn_engine.random.uniform", return_value=0.0):
            score = te._calculate_exam_score("期末")
        expected = min(100.0, 30 * (1 + 0.5) * 1.0)   # 30 * 1.5 = 45
        assert score == pytest.approx(expected, abs=1e-6)

    def test_zero_exp_gives_low_score(self):
        """熟練度全 0 時，期末分數應極低（接近 0）。"""
        p = make_char(intel=0, luck=50)
        for subj in p.subject_exp:
            p.subject_exp[subj] = 0
        te = make_engine(p)
        with patch("turn_engine.random.uniform", return_value=0.0):
            score = te._calculate_exam_score("期末")
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_midterm_floor_from_plus10(self):
        """期中就算熟練度 0，avg_exp 也有 +10，不會直接從 0 開始。"""
        p = make_char(intel=0, luck=50)
        for subj in p.subject_exp:
            p.subject_exp[subj] = 0
        te = make_engine(p)
        with patch("turn_engine.random.uniform", return_value=0.0):
            score = te._calculate_exam_score("期中")
        # avg_exp = 0*2+10 = 10；intel_bonus = 1.0；luck_roll = 0
        assert score > 0.0


# ──────────────────────────────────────────────────────────────
#  3. _roll_skip_effects — 翹課後果範圍
# ──────────────────────────────────────────────────────────────
class TestRollSkipEffects:
    def test_satisfaction_loss_range(self):
        """自我滿足度扣減值應恆在 8~10 之間（跑 500 次）。"""
        p = make_char(satisfaction=80, luck=50)
        te = make_engine(p)

        losses = []
        for _ in range(500):
            p.satisfaction = 80        # reset
            p.grades["參與度"] = 50.0  # reset
            msgs = te._roll_skip_effects(p)
            # 解析「自我滿足度 -X」訊息
            sat_msg = next(m for m in msgs if "自我滿足度" in m)
            loss = int(sat_msg.split("-")[1])
            losses.append(loss)

        assert min(losses) >= 8,  f"最小扣減 {min(losses)} < 8"
        assert max(losses) <= 10, f"最大扣減 {max(losses)} > 10"
        # 應有多樣性（8、9、10 都出現過）
        assert len(set(losses)) > 1, "500 次中滿足度扣減值從未變動，random 可能失效"

    def test_participation_deduct_is_3_or_5(self):
        """課堂參與度扣減值只能是 3 或 5。"""
        p = make_char(satisfaction=80, luck=50)
        te = make_engine(p)

        deducts = set()
        for _ in range(200):
            p.satisfaction = 80
            p.grades["參與度"] = 50.0
            msgs = te._roll_skip_effects(p)
            part_msg = next(m for m in msgs if "課堂參與度" in m)
            d = int(part_msg.split("-")[1])
            deducts.add(d)

        assert deducts.issubset({3, 5}), f"參與度扣減出現非預期值: {deducts}"

    def test_satisfaction_clamps_at_zero(self):
        """即使原本滿足感 5 被扣 10，也不應低於 0。"""
        p = make_char(satisfaction=5, luck=50)
        te = make_engine(p)
        p.grades["參與度"] = 20.0
        te._roll_skip_effects(p)
        assert p.satisfaction >= 0

    def test_participation_clamps_at_zero(self):
        """課堂參與度不應扣到負數。"""
        p = make_char(satisfaction=80, luck=50)
        te = make_engine(p)
        p.grades["參與度"] = 0.0   # 已是 0，再扣不應變負
        te._roll_skip_effects(p)
        assert p.grades["參與度"] >= 0

    def test_revealed_grades_updated(self):
        """翹課後應把 '參與度' 加入 revealed_grades。"""
        p = make_char(satisfaction=80, luck=50)
        te = make_engine(p)
        p.grades["參與度"] = 30.0
        te._roll_skip_effects(p)
        assert "參與度" in p.revealed_grades

    def test_returns_two_messages(self):
        """應回傳恰好兩條訊息（滿足度 + 參與度）。"""
        p = make_char(satisfaction=80, luck=50)
        te = make_engine(p)
        p.grades["參與度"] = 30.0
        msgs = te._roll_skip_effects(p)
        assert len(msgs) == 2


# ──────────────────────────────────────────────────────────────
#  4. _pre_exam_check — 考前狀態檢測
# ──────────────────────────────────────────────────────────────
class TestPreExamCheck:
    def test_normal_returns_1(self):
        """體力充足、運氣正常 → modifier = 1.0。"""
        p = make_char(stamina=50, luck=60)
        p.stamina = 50   # 高體力
        te = make_engine(p)
        # 確保不觸發任何意外
        with patch("turn_engine.random.random", return_value=0.99):
            mod = te._pre_exam_check()
        assert mod == pytest.approx(1.0)

    def test_oversleep_triggers_when_stamina_low_and_random_hit(self):
        """體力 < 30 且 < stamina_max*0.3 且 random() < 0.4 → modifier = 0.5，滿足感 -15。"""
        p = make_char(stamina=50, luck=60, satisfaction=80)
        p.stamina = 10   # 低體力（< 30 且 < 50*0.3=15）
        te = make_engine(p)
        with patch("turn_engine.random.random", return_value=0.1):   # < 0.4
            mod = te._pre_exam_check()
        assert mod == pytest.approx(0.5)
        assert p.satisfaction == 65   # 80 - 15

    def test_oversleep_not_triggered_when_random_miss(self):
        """體力 < 30 且 < stamina_max*0.3 但 random() >= 0.4 → 繼續判斷運氣（不立即返回 0.5）。"""
        p = make_char(stamina=50, luck=60, satisfaction=80)
        p.stamina = 10   # 低體力（< 30 且 < 50*0.3=15）
        te = make_engine(p)
        with patch("turn_engine.random.random", return_value=0.5):   # >= 0.4
            mod = te._pre_exam_check()
        # 體力 miss 後，luck=65 >= 40，不觸發爆胎
        assert mod == pytest.approx(1.0)

    def test_flat_tire_triggers_when_luck_low(self):
        """運氣 < 40 且 random() < 0.3 → modifier = 0.85，滿足感 -8。"""
        p = make_char(stamina=50, luck=20, satisfaction=80)
        p.stamina = 50   # 體力充足（stamina >= 30），睡過頭分支被短路，不呼叫 random()
        p.luck    = 20   # 但運氣低 → luck < 40，才呼叫 random()
        te = make_engine(p)
        # stamina 分支被短路不呼叫 random()，luck 分支才是第一次呼叫
        with patch("turn_engine.random.random", return_value=0.1):   # < 0.3 → 爆胎
            mod = te._pre_exam_check()
        assert mod == pytest.approx(0.85)
        assert p.satisfaction == 72   # 80 - 8

    def test_modifier_always_in_valid_range(self):
        """任何情況下 modifier 應在 (0, 1]。"""
        p = make_char(stamina=50, luck=50, satisfaction=80)
        te = make_engine(p)
        for _ in range(200):
            p.stamina = random.randint(0, 60)
            p.luck    = random.randint(0, 80)
            p.satisfaction = 80   # reset
            mod = te._pre_exam_check()
            assert 0.0 < mod <= 1.0, f"modifier {mod} 不在 (0, 1]"


# ──────────────────────────────────────────────────────────────
#  5. final_settlement — 最終評語條件
# ──────────────────────────────────────────────────────────────
class TestFinalSettlement:
    """
    評語邏輯：
      final >= 80 且 satisfaction >= 70  → 平衡型
      final >= 60 且 satisfaction >= 60  → 及格快樂
      final >= 60 且 satisfaction <  60  → 成績過但身心崩潰
      else                               → 未及格
    """
    def _run(self, grades: dict, satisfaction: int) -> str:
        """執行結算並回傳 comment 字串（透過攔截 set_settlement_data 呼叫）。"""
        import ui as _ui
        p = make_char(satisfaction=satisfaction)
        for k, v in grades.items():
            p.grades[k] = v
        te = make_engine(p)

        captured = {}
        def mock_set(data):
            captured.update(data)
        _ui.set_settlement_data.side_effect = mock_set

        te.final_settlement()
        return captured.get("comment", "")

    def test_balanced_ending(self):
        grades = {"參與度": 90, "作業": 90, "小考": 90, "期中": 90, "期末": 90}
        comment = self._run(grades, satisfaction=80)
        assert "平衡" in comment

    def test_pass_happy_ending(self):
        grades = {"參與度": 60, "作業": 60, "小考": 60, "期中": 60, "期末": 60}
        comment = self._run(grades, satisfaction=70)
        assert "及格快樂" in comment or "可以放暑假" in comment

    def test_pass_but_burnout(self):
        grades = {"參與度": 60, "作業": 60, "小考": 60, "期中": 80, "期末": 80}
        comment = self._run(grades, satisfaction=50)
        assert "崩潰" in comment or "快沒電" in comment

    def test_fail_ending(self):
        grades = {"參與度": 0, "作業": 0, "小考": 0, "期中": 0, "期末": 0}
        comment = self._run(grades, satisfaction=30)
        assert "遺憾" in comment or "重修" in comment

    def test_satisfaction_boundary_65_70(self):
        """final=85, sat=65 → 平衡條件 sat>=70 不滿足 → 應為及格快樂。"""
        grades = {"參與度": 85, "作業": 85, "小考": 85, "期中": 85, "期末": 85}
        comment = self._run(grades, satisfaction=65)
        # final ≈ 85, sat = 65 < 70 → "及格快樂" 或 "可以放暑假"
        assert "及格" in comment or "快樂" in comment or "放暑假" in comment


# ──────────────────────────────────────────────────────────────
#  6. EXTRA_EVENTS 中家教 intel_req 是否正確
# ──────────────────────────────────────────────────────────────
def test_tutoring_intel_req():
    """家教的智力需求應為 60（已更新）。"""
    tutoring = next(e for e in EXTRA_EVENTS if e["id"] == "tutoring")
    assert tutoring["intel_req"] == 60, (
        f"家教 intel_req = {tutoring['intel_req']}，預期 60"
    )

def test_parttime_intel_req():
    """打工沒有智力需求（intel_req == 0）。"""
    parttime = next(e for e in EXTRA_EVENTS if e["id"] == "part_time")
    assert parttime["intel_req"] == 0
