# ============================================================
#  tests/test_character.py — Character 類別邏輯單元測試
# ============================================================
import pytest

# ── character 依賴 ui（已在 conftest.py 中 mock），可直接 import ──
from character import Character, DRAWBACKS, EXTRA_EVENTS, TALENTS


# ──────────────────────────────────────────────────────────────
#  測試輔助
# ──────────────────────────────────────────────────────────────
DE_DEFAULT = {"name": "大一", "base_time": 5, "intel": 0, "luck": 5}

def make_char(
    stamina=50, intel=50, luck=50, money=300,
    satisfaction=80, talent=None, drawbacks=None, de_level=None,
):
    """建立一個乾淨的測試用 Character（天賦/年級可覆蓋）。"""
    p = Character(
        name="TestPlayer",
        department="管理學院",
        stamina=stamina,
        intel=intel,
        luck=luck,
        money=money,
        talent=talent or {},
        drawbacks=drawbacks or [],
        de_level=de_level or DE_DEFAULT,
    )
    p.satisfaction = satisfaction
    return p


# ──────────────────────────────────────────────────────────────
#  1. change_satisfaction — 邊界夾鉗
# ──────────────────────────────────────────────────────────────
class TestChangeSatisfaction:
    def test_clamp_upper(self):
        """滿足感不應超過 100。"""
        p = make_char(satisfaction=95)
        p.change_satisfaction(20)
        assert p.satisfaction == 100

    def test_clamp_lower(self):
        """滿足感不應低於 0。"""
        p = make_char(satisfaction=5)
        p.change_satisfaction(-20)
        assert p.satisfaction == 0

    def test_exact_boundary(self):
        """恰好到 100 / 0 不應溢出。"""
        p = make_char(satisfaction=50)
        p.change_satisfaction(50)
        assert p.satisfaction == 100
        p.change_satisfaction(-100)
        assert p.satisfaction == 0

    def test_normal_increase(self):
        p = make_char(satisfaction=60)
        p.change_satisfaction(10)
        assert p.satisfaction == 70

    def test_normal_decrease(self):
        p = make_char(satisfaction=60)
        p.change_satisfaction(-15)
        assert p.satisfaction == 45


# ──────────────────────────────────────────────────────────────
#  2. stamina — restore / consume 邊界
# ──────────────────────────────────────────────────────────────
class TestStamina:
    def test_restore_clamp_at_max(self):
        """restore_stamina 不應超過 stamina_max。"""
        p = make_char(stamina=50)
        p.stamina = 40
        p.restore_stamina(30)
        assert p.stamina == p.stamina_max   # 應 == 50（或依 talent 調整的 max）

    def test_restore_normal(self):
        p = make_char(stamina=50)
        p.stamina = 20
        p.restore_stamina(15)
        assert p.stamina == 35

    def test_consume_normal_returns_true(self):
        """體力足夠時，consume_stamina 應回傳 True 且體力正確扣減。"""
        p = make_char(stamina=50)
        p.stamina = 30
        result = p.consume_stamina(10)
        assert result is True
        assert p.stamina == 20

    def test_consume_to_zero_returns_false(self):
        """體力不足時，consume_stamina 回傳 False，體力夾鉗到 0，觸發生病。"""
        p = make_char(stamina=50)
        p.stamina = 5
        result = p.consume_stamina(20)
        assert result is False
        assert p.stamina == 0
        assert "生病" in p.status_effects

    def test_consume_exactly_zero(self):
        """恰好扣至 0 不應報錯，也不觸發生病（沒有「負」體力）。"""
        p = make_char(stamina=50)
        p.stamina = 20
        result = p.consume_stamina(20)
        assert result is True
        assert p.stamina == 0
        assert "生病" not in p.status_effects


# ──────────────────────────────────────────────────────────────
#  3. get_effective_time — 狀態效果乘數
# ──────────────────────────────────────────────────────────────
class TestGetEffectiveTime:
    """base_time = 10 + de_level.base_time(5) = 15（大一無天賦）。"""

    BASE = 15  # 10 + 5（大一）

    def test_no_status_effects(self):
        p = make_char()
        assert p.get_effective_time() == self.BASE

    def test_sick_halves_time(self):
        p = make_char()
        p.status_effects["生病"] = 2
        expected = max(1, int(self.BASE * 0.5))
        assert p.get_effective_time() == expected

    def test_spirit_bonus(self):
        p = make_char()
        p.status_effects["神采奕奕"] = 1
        expected = max(1, int(self.BASE * 1.5))
        assert p.get_effective_time() == expected

    def test_weak_state(self):
        p = make_char()
        p.status_effects["無力狀態"] = 0
        expected = max(1, int(self.BASE * 0.7))
        assert p.get_effective_time() == expected

    def test_motivation_shop_item(self):
        """道具店「激勵」+20%。"""
        p = make_char()
        p.status_effects["激勵"] = 1
        expected = max(1, int(self.BASE * 1.2))
        assert p.get_effective_time() == expected

    def test_sick_and_weak_stack(self):
        """生病 × 無力 應乘算（0.5 × 0.7）。"""
        p = make_char()
        p.status_effects["生病"]   = 2
        p.status_effects["無力狀態"] = 0
        expected = max(1, int(self.BASE * 0.5 * 0.7))
        assert p.get_effective_time() == expected

    def test_minimum_is_1(self):
        """即使所有 debuff 疊加，結果至少為 1。"""
        p = make_char(de_level={"name": "大二", "base_time": 0, "intel": 5, "luck": 10})
        # base_time_bonus = 0 → base_time = 10
        p.status_effects["生病"]     = 2
        p.status_effects["無力狀態"] = 0
        p.base_time_mult = 0.1   # 強制壓低
        assert p.get_effective_time() >= 1

    def test_night_owl_talent_doesnt_affect_base(self):
        """夜貓子天賦只在熬夜行動有效，不影響 get_effective_time。"""
        p = make_char(talent={"night_owl_mult": 1.5})
        assert p.get_effective_time() == self.BASE   # 無特殊狀態


# ──────────────────────────────────────────────────────────────
#  4. apply_weekly_status — 週初狀態賦予
# ──────────────────────────────────────────────────────────────
class TestApplyWeeklyStatus:
    def test_sick_by_low_satisfaction(self):
        """滿足感 < 50（預設閾值）且無「生病」狀態 → 應新增生病。"""
        p = make_char(satisfaction=40)
        p.status_effects.clear()
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "生病" in names
        assert "生病" in p.status_effects

    def test_no_duplicate_sick(self):
        """已有「生病」狀態時，不應重複添加。"""
        p = make_char(satisfaction=30)
        p.status_effects["生病"] = 2
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "生病" not in names

    def test_spirit_when_high_satisfaction(self):
        """滿足感 > 80 且未生病 → 新增「神采奕奕」。"""
        p = make_char(satisfaction=90)
        p.status_effects.clear()
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "神采奕奕" in names

    def test_no_spirit_when_sick(self):
        """生病時不應觸發神采奕奕。"""
        p = make_char(satisfaction=95)
        p.status_effects["生病"] = 1
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "神采奕奕" not in names

    def test_weak_state_when_low_satisfaction(self):
        """滿足感 < 60 → 無力狀態（若未有）。"""
        p = make_char(satisfaction=55)
        p.status_effects.clear()
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "無力狀態" in names

    def test_weak_state_removed_when_recovered(self):
        """滿足感回升至 60 以上 → 應移除無力狀態。"""
        p = make_char(satisfaction=70)
        p.status_effects["無力狀態"] = 0
        p.apply_weekly_status()
        assert "無力狀態" not in p.status_effects

    def test_extra_sick_chance_via_drawback(self):
        """「容易生病」負面特質，機率 1.0 時必定觸發生病（滿足感正常）。"""
        sick_drawback = {"penalty": "sick_chance", "value": 1.0, "id": 2,
                         "name": "容易生病", "desc": "", "bonus_pts": 0}
        p = make_char(satisfaction=80, drawbacks=[sick_drawback])
        p.status_effects.clear()
        new = p.apply_weekly_status()
        names = [s[0] for s in new]
        assert "生病" in names


# ──────────────────────────────────────────────────────────────
#  5. tick_status_effects — 計時型狀態倒數
# ──────────────────────────────────────────────────────────────
class TestTickStatusEffects:
    def test_countdown_decrements(self):
        """duration 2 → 在 tick 後變 1。"""
        p = make_char()
        p.status_effects["生病"] = 2
        p.tick_status_effects()
        assert p.status_effects.get("生病") == 1

    def test_expires_at_one(self):
        """duration 1 → tick 後應從 status_effects 移除。"""
        p = make_char()
        p.status_effects["神采奕奕"] = 1
        p.tick_status_effects()
        assert "神采奕奕" not in p.status_effects

    def test_condition_state_not_decremented(self):
        """v=0（條件型，如無力狀態）不應被 tick 倒數或移除。"""
        p = make_char()
        p.status_effects["無力狀態"] = 0
        p.tick_status_effects()
        assert "無力狀態" in p.status_effects   # 仍在
        assert p.status_effects["無力狀態"] == 0  # 值不變


# ──────────────────────────────────────────────────────────────
#  6. is_game_over / calculate_final_score
# ──────────────────────────────────────────────────────────────
class TestGameOverAndScore:
    def test_game_over_at_zero_satisfaction(self):
        p = make_char(satisfaction=0)
        assert p.is_game_over() is True

    def test_not_game_over_at_one(self):
        p = make_char(satisfaction=1)
        assert p.is_game_over() is False

    def test_final_score_weights_sum_to_one(self):
        """各科目加權總和應為 100（全 100 分時）。"""
        p = make_char()
        for k in p.grades:
            p.grades[k] = 100.0
        assert p.calculate_final_score() == pytest.approx(100.0)

    def test_final_score_zero_grades(self):
        """全 0 分 → 最終成績為 0。"""
        p = make_char()
        for k in p.grades:
            p.grades[k] = 0.0
        assert p.calculate_final_score() == pytest.approx(0.0)

    def test_final_score_partial(self):
        """期中 100、其餘 0 → 應等於期中權重 × 100 = 30.0。"""
        p = make_char()
        for k in p.grades:
            p.grades[k] = 0.0
        p.grades["期中"] = 100.0
        assert p.calculate_final_score() == pytest.approx(30.0)

    def test_final_score_range(self):
        """成績在合理範圍時，最終成績不應超出 [0, 100]。"""
        import random
        p = make_char()
        for _ in range(200):
            for k in p.grades:
                p.grades[k] = random.uniform(0, 100)
            s = p.calculate_final_score()
            assert 0.0 <= s <= 100.0, f"out of range: {s}"


# ──────────────────────────────────────────────────────────────
#  7. 資料庫一致性（DRAWBACKS / EXTRA_EVENTS / TALENTS）
# ──────────────────────────────────────────────────────────────
class TestDataConsistency:
    def test_drawbacks_required_fields(self):
        for d in DRAWBACKS:
            assert "id"        in d, f"{d} missing id"
            assert "name"      in d, f"{d} missing name"
            assert "bonus_pts" in d, f"{d} missing bonus_pts"
            assert "penalty"   in d, f"{d} missing penalty"
            assert "value"     in d, f"{d} missing value"

    def test_extra_events_required_fields(self):
        for e in EXTRA_EVENTS:
            assert "id"         in e, f"{e} missing id"
            assert "name"       in e, f"{e} missing name"
            assert "time_cost"  in e, f"{e} missing time_cost"
            assert "money_delta" in e, f"{e} missing money_delta"
            assert "intel_req"  in e, f"{e} missing intel_req"
            assert "exclusive"  in e, f"{e} missing exclusive"

    def test_extra_events_mutual_exclusion(self):
        """若 A.exclusive 含 B.id，則 B.exclusive 必含 A.id（互斥必須對稱）。"""
        id_to_ev = {e["id"]: e for e in EXTRA_EVENTS}
        for ev in EXTRA_EVENTS:
            for excl_id in ev.get("exclusive", []):
                if excl_id in id_to_ev:
                    assert ev["id"] in id_to_ev[excl_id]["exclusive"], (
                        f"互斥不對稱：{ev['id']} 排除 {excl_id}，但 {excl_id} 未排除 {ev['id']}"
                    )

    def test_talents_prob_sum(self):
        """天賦機率總和應為 100%（prob 欄位為整數百分比）。"""
        total = sum(t["prob"] for t in TALENTS)
        assert total == 100, f"天賦機率總和 {total} ≠ 100"

    def test_talents_required_fields(self):
        for t in TALENTS:
            assert "id"   in t, f"{t} missing id"
            assert "name" in t, f"{t} missing name"
            assert "prob" in t, f"{t} missing prob"
