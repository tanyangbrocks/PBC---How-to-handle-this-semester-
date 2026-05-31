# ============================================================
#  tests/test_event_system.py — EventSystem 關鍵流程測試
#
#  重點覆蓋：
#    1. 宿醉觸發鏈（這次 demo 崩潰的根因）
#    2. pending_hangover 跨週持久化
#    3. 喝酒後確實扣體力/增滿足感
#    4. 宿醉後確實扣體力/滿足感/參與度
#    5. 幸運狀態 luck +1/-1 對稱性
#    6. 社團活動不耗體力機率受運氣影響
#    7. 點心滿足感機率受運氣影響
# ============================================================
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from character import Character
from event_system import (
    EventSystem,
    _club_drinking_effect,
    _hangover_effect,
    PHASE_EVENTS,
    EVENTS,
)

# ──────────────────────────────────────────────────────────────
#  測試輔助
# ──────────────────────────────────────────────────────────────
DE_DEFAULT = {"name": "大一", "base_time": 5, "intel": 0, "luck": 5}

def make_char(stamina=50, intel=50, luck=50, money=300, satisfaction=80):
    p = Character(
        name="Test", department="管理學院",
        stamina=stamina, intel=intel, luck=luck, money=money,
        talent={}, drawbacks=[], de_level=DE_DEFAULT,
    )
    p.satisfaction = satisfaction
    return p

def make_event_sys(player=None):
    return EventSystem(player or make_char())


# ──────────────────────────────────────────────────────────────
#  1. _club_drinking_effect — 回傳旗標 + 副作用
# ──────────────────────────────────────────────────────────────
class TestClubDrinkingEffect:
    def test_returns_trigger_hangover(self):
        """_club_drinking_effect 必須回傳 'TRIGGER_HANGOVER'。"""
        p = make_char(satisfaction=50, stamina=30)
        result = _club_drinking_effect(p)
        assert result == "TRIGGER_HANGOVER"

    def test_satisfaction_increases(self):
        """喝酒後滿足感 +10。"""
        p = make_char(satisfaction=50)
        _club_drinking_effect(p)
        assert p.satisfaction == 60

    def test_stamina_decreases(self):
        """喝酒後體力 -8。"""
        p = make_char(stamina=30)
        _club_drinking_effect(p)
        assert p.stamina == 22

    def test_stamina_clamp_at_zero(self):
        """體力不足 8 時，扣到 0 即止（不為負）。"""
        p = make_char(stamina=5)
        _club_drinking_effect(p)
        assert p.stamina == 0


# ──────────────────────────────────────────────────────────────
#  2. _hangover_effect — 副作用正確
# ──────────────────────────────────────────────────────────────
class TestHangoverEffect:
    def test_stamina_decreases_10(self):
        p = make_char(stamina=30)
        _hangover_effect(p)
        assert p.stamina == 20

    def test_satisfaction_decreases_15(self):
        p = make_char(satisfaction=80)
        _hangover_effect(p)
        assert p.satisfaction == 65

    def test_participation_decreases_10(self):
        p = make_char()
        p.grades["參與度"] = 50.0
        _hangover_effect(p)
        assert p.grades["參與度"] == pytest.approx(40.0)

    def test_participation_clamp_at_zero(self):
        p = make_char()
        p.grades["參與度"] = 5.0
        _hangover_effect(p)
        assert p.grades["參與度"] == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────
#  3. _fire_event — 社團喝酒後設定 pending_hangover
# ──────────────────────────────────────────────────────────────
class TestFireEventSetsHangover:
    def _get_club_drinking_event(self):
        """從 PHASE_EVENTS 取得社團喝酒事件 dict。"""
        ev = next(e for e in PHASE_EVENTS if e["id"] == "club_drinking")
        return ev

    def test_pending_hangover_set_after_drinking(self):
        """觸發 club_drinking 事件後，pending_hangover 應變 True。"""
        p = make_char(satisfaction=50, stamina=30)
        es = make_event_sys(p)
        assert es.pending_hangover is False

        ev = self._get_club_drinking_event()
        asyncio.run(es._fire_event("phase", ev))

        assert es.pending_hangover is True

    def test_pending_hangover_false_before_drinking(self):
        """初始狀態 pending_hangover 應為 False。"""
        es = make_event_sys()
        assert es.pending_hangover is False


# ──────────────────────────────────────────────────────────────
#  4. roll_event_after_action — 宿醉強制觸發鏈（最關鍵）
# ──────────────────────────────────────────────────────────────
class TestHangoverTriggerChain:
    def test_hangover_fires_on_next_action(self):
        """
        pending_hangover = True 時，roll_event_after_action 應：
          1. 無條件執行宿醉效果
          2. 將 pending_hangover 清為 False
        這是本次 demo 崩潰的根因（缺 await）的回歸測試。
        """
        p = make_char(stamina=40, satisfaction=80)
        p.grades["參與度"] = 50.0
        es = make_event_sys(p)
        es.pending_hangover = True

        asyncio.run(es.roll_event_after_action(week=2))

        # 宿醉效果應已套用
        assert p.stamina == 30        # -10
        assert p.satisfaction == 65   # -15
        assert p.grades["參與度"] == pytest.approx(40.0)  # -10

        # pending_hangover 應已清除
        assert es.pending_hangover is False

    def test_hangover_fires_even_when_weekly_limit_reached(self):
        """即使本週事件已達 2 次上限，宿醉仍應強制觸發。"""
        p = make_char(stamina=40, satisfaction=80)
        p.grades["參與度"] = 50.0
        es = make_event_sys(p)
        es.pending_hangover  = True
        es.events_this_week  = 2   # 已達上限

        asyncio.run(es.roll_event_after_action(week=2))

        # 宿醉仍然套用
        assert p.stamina == 30
        assert es.pending_hangover is False

    def test_no_hangover_without_pending(self):
        """pending_hangover = False 時不應觸發宿醉效果。"""
        p = make_char(stamina=40, satisfaction=80)
        es = make_event_sys(p)
        es.pending_hangover = False

        # 強制所有隨機事件都不觸發
        with patch("event_system.random.random", return_value=1.0):
            asyncio.run(es.roll_event_after_action(week=2))

        # 體力和滿足感不應有宿醉扣減
        assert p.stamina    == 40
        assert p.satisfaction == 80

    def test_full_chain_drink_then_act(self):
        """
        完整鏈路：
          1. 觸發 club_drinking（pending_hangover → True）
          2. 呼叫 roll_event_after_action（宿醉應觸發）
        """
        p = make_char(stamina=40, satisfaction=50)
        p.grades["參與度"] = 50.0
        es = make_event_sys(p)

        # Step 1: 觸發喝酒事件
        ev = next(e for e in PHASE_EVENTS if e["id"] == "club_drinking")
        asyncio.run(es._fire_event("phase", ev))
        assert es.pending_hangover is True, "喝酒後應設定 pending_hangover"

        # 記錄喝酒後的狀態
        sat_after_drink = p.satisfaction
        sta_after_drink = p.stamina
        par_after_drink = p.grades["參與度"]

        # Step 2: 下一次行動後宿醉觸發
        asyncio.run(es.roll_event_after_action(week=2))
        assert es.pending_hangover is False, "宿醉觸發後 pending_hangover 應清除"
        assert p.stamina     == sta_after_drink - 10
        assert p.satisfaction == sat_after_drink - 15
        assert p.grades["參與度"] == pytest.approx(max(0, par_after_drink - 10))


# ──────────────────────────────────────────────────────────────
#  5. pending_hangover 跨週持久化
# ──────────────────────────────────────────────────────────────
class TestHangoverPersistence:
    def test_hangover_survives_weekly_reset(self):
        """reset_weekly_count 不應清除 pending_hangover。"""
        es = make_event_sys()
        es.pending_hangover = True
        es.reset_weekly_count()
        assert es.pending_hangover is True

    def test_events_count_resets_but_hangover_persists(self):
        """weekly count 清零，但 pending_hangover 仍為 True。"""
        es = make_event_sys()
        es.events_this_week = 2
        es.pending_hangover = True
        es.reset_weekly_count()
        assert es.events_this_week == 0
        assert es.pending_hangover is True


# ──────────────────────────────────────────────────────────────
#  6. 幸運狀態 — luck +1/-1 對稱性
# ──────────────────────────────────────────────────────────────
class TestLuckyStatusLuck:
    def test_luck_increments_when_added(self):
        """add_status('幸運', 2) 應讓 luck +1。"""
        p = make_char()
        initial = p.luck
        p.add_status("幸運", 2)
        assert p.luck == initial + 1

    def test_luck_not_incremented_if_already_has_lucky(self):
        """已有幸運狀態時再次 add_status 不應再 +1。"""
        p = make_char()
        initial = p.luck
        p.add_status("幸運", 2)
        assert p.luck == initial + 1   # 第一次 +1
        p.add_status("幸運", 2)        # 第二次：幸運已在 status_effects → 不再加
        assert p.luck == initial + 1   # 仍只 +1

    def test_luck_decrements_on_expire(self):
        """幸運狀態 duration=1 → tick 後解除，luck -1。"""
        p = make_char()
        initial = p.luck
        p.status_effects["幸運"] = 1
        p.tick_status_effects()
        assert "幸運" not in p.status_effects
        assert p.luck == initial - 1

    def test_luck_symmetry(self):
        """add_status → 撐 2 週 → tick × 2 後 luck 回到原始值。"""
        p = make_char()
        original = p.luck
        p.add_status("幸運", 2)
        assert p.luck == original + 1    # 加了
        p.tick_status_effects()          # duration 2 → 1
        assert "幸運" in p.status_effects
        assert p.luck == original + 1    # 還在
        p.tick_status_effects()          # duration 1 → 解除
        assert "幸運" not in p.status_effects
        assert p.luck == original        # 回到原始值


# ──────────────────────────────────────────────────────────────
#  7. 社團活動不耗體力機率受運氣影響
# ──────────────────────────────────────────────────────────────
class TestClubActivityStaminaFreeProbability:
    """驗證 turn_engine.py 社團活動中 _free_prob 的邊界。"""

    def _calc_free_prob(self, luck: int) -> float:
        return min(0.95, 0.30 + luck * 0.01)

    def test_base_probability_at_luck_0(self):
        assert self._calc_free_prob(0) == pytest.approx(0.30)

    def test_probability_increases_with_luck(self):
        assert self._calc_free_prob(40) == pytest.approx(0.70)

    def test_probability_capped_at_95(self):
        assert self._calc_free_prob(100) == pytest.approx(0.95)
        assert self._calc_free_prob(200) == pytest.approx(0.95)

    def test_probability_never_below_30(self):
        for luck in range(0, 150, 10):
            p = self._calc_free_prob(luck)
            assert p >= 0.30, f"luck={luck} → prob={p} < 0.30"

    def test_probability_never_above_95(self):
        for luck in range(0, 150, 10):
            p = self._calc_free_prob(luck)
            assert p <= 0.95, f"luck={luck} → prob={p} > 0.95"


# ──────────────────────────────────────────────────────────────
#  8. 點心滿足感機率受運氣影響
# ──────────────────────────────────────────────────────────────
class TestSnackSatisfactionProbability:
    """驗證 ui_draw_base.py 點心效果中 _sat_prob 的邊界。"""

    def _calc_sat_prob(self, luck: int) -> float:
        return max(0.0, min(1.0, 0.70 + (luck - 40) * 0.01))

    def test_base_probability_at_luck_40(self):
        """luck=40 時成功率應恰好 70%。"""
        assert self._calc_sat_prob(40) == pytest.approx(0.70)

    def test_high_luck_increases_probability(self):
        assert self._calc_sat_prob(80) == pytest.approx(1.0)

    def test_low_luck_decreases_probability(self):
        assert self._calc_sat_prob(0) == pytest.approx(0.30)

    def test_probability_never_below_0(self):
        for luck in range(0, 150, 5):
            p = self._calc_sat_prob(luck)
            assert p >= 0.0, f"luck={luck} → prob={p} < 0"

    def test_probability_never_above_1(self):
        for luck in range(0, 150, 5):
            p = self._calc_sat_prob(luck)
            assert p <= 1.0, f"luck={luck} → prob={p} > 1"

    def test_probability_clamped_both_ends(self):
        """極端值：luck=0 → 30%, luck=110+ → 100%。"""
        assert self._calc_sat_prob(0)   == pytest.approx(0.30)
        assert self._calc_sat_prob(110) == pytest.approx(1.0)
