# ============================================================
# 模組：turn_engine.py — 回合與時間引擎（pygame 版）
# ============================================================
# 與 turn_engine_origin.py 的差異：
#   - 所有 print() 改為 notify()
#   - 所有 input() 改為 ask_yn() / ask_choice() / ask_text()
#   - 移除 time.sleep()（pygame 不需要假暫停）
#   - 不需要狀態機：執行緒模型下 ask_* 本身就是阻塞等待，
#     線性流程完全保留
# ============================================================

import random

from character import Character
from event_system import EventSystem
from skill_system import SkillSystem
from shop_V03 import Shop
from ui import notify, ask_yn, ask_choice, ask_text, set_player, \
               notify_timetable, notify_grade_report, set_time, show_action_result, \
               ask_subject_popup, trigger_time_overflow_warning, tell_story, \
               show_extra_event_popup, ask_exam_start, set_roll_call, clear_roll_call, \
               set_special_disabled


# ── 點名事件觸發週次 ─────────────────────────────────────────────
ROLL_CALL_WEEKS = {2, 5, 7, 10, 12, 15}


# ── 每週可選擇的行動清單 ──────────────────────────────────
ACTIONS = [
    {
        "id": "study_hard",
        "name": "認真讀書",
        "stamina_cost": 4,
        "exp_gain": 8,
        "satisfaction": -5,
        "desc": "花大量時間在課業上，學習效率高但很耗體力。",
    },
    {
        "id": "attend_class",
        "name": "正常上課",
        "stamina_cost": 2,
        "exp_gain": 4,
        "satisfaction": 0,
        "participation": 5,
        "desc": "按時上課，維持基本學習進度。",
    },
    {
        "id": "club_activity",
        "name": "社團活動",
        "stamina_cost": 3,
        "exp_gain": 0,
        "satisfaction": 10,
        "desc": "參加社團，放鬆心情，但會犧牲讀書時間。",
    },
    {
        "id": "part_time_job",
        "name": "打工賺錢",
        "stamina_cost": 4,
        "exp_gain": 0,
        "satisfaction": 3,
        "money_gain": 150,
        "desc": "去打工貼補生活費，但很耗體力。",
    },
    {
        "id": "rest",
        "name": "好好休息",
        "stamina_cost": -6,
        "exp_gain": 0,
        "satisfaction": 8,
        "desc": "什麼都不做，充電休息。",
    },
    {
        "id": "help_friend",
        "name": "幫助朋友",
        "stamina_cost": 2,
        "exp_gain": 0,
        "satisfaction": 12,
        "desc": "花時間陪伴身邊的人，自我滿足感大增。",
    },
    {
        "id": "shop",
        "name": "🏪 前往道具店",
        "stamina_cost": 0,
        "exp_gain": 0,
        "satisfaction": 0,
        "desc": "前往校園道具店購買道具（不消耗時間單位）。",
    },
]

# ── 特殊行動（不消耗時間單位，不觸發突發事件）────────────────
SPECIAL_ACTIONS = [
    {
        "id": "pull_allnighter",
        "name": "熬夜",
        "stamina_cost": 10,       # 消耗體力
        "time_gain": 2,           # 增加可用時間格
        "satisfaction": -5,
        "allnighter_risk": True,  # 睡過頭機率 +10%
        "desc": "犧牲體力換取額外行動時間，但睡過頭機率上升。",
    },
    {
        "id": "skip_class",
        "name": "翹課",
        "stamina_cost": -10,      # 恢復體力（負值代表回復）
        "time_gain": 1,
        "satisfaction": 0,
        "quiz_miss_chance": True, # 可能錯過小考 / 點名
        "desc": "翹課補眠，不消耗時間，但可能錯過小考或點名。",
    },
    {
        "id": "eat",
        "name": "進食",
        "stamina_cost": -10,      # 恢復體力
        "money_cost": 50,
        "satisfaction": 0,
        "time_gain": 0,
        "gives_full_status": True,
        "desc": "花 50 元吃飯恢復體力，飽腹後無法再進食（持續 3 時間格）。",
    },
]


class TurnEngine:
    def __init__(
        self,
        player: Character,
        event_sys: EventSystem,
        skill_sys: SkillSystem,
        shop: Shop,
    ):
        self.player    = player
        self.event_sys = event_sys
        self.skill_sys = skill_sys
        self.shop      = shop

        # ── 跨週追蹤資料 ──────────────────────────────────────
        self._quiz1_score  = 0     # 第四週計算，第五週展示
        self._quiz2_score  = 0     # 第十二週計算，第十四週展示
        self._week2_course = None  # {"name":str, "credits":int}
        self._week9_job    = ""    # 美宣 / 公關 / 現場工人

    def run_week(self, week: int) -> bool:
        player = self.player

        self.event_sys.reset_weekly_count()   # 每週開始重置突發事件計數

        if week == 8:
            self._midterm_week()
        elif week == 16:
            self._final_week()
        else:
            self._normal_week(week)
            self.event_sys.roll_green_hat(week)   # 被戴綠帽：週末獨立觸發

        self.event_sys.tick_debuffs()             # 週末 debuff 計時（所有週）
        self._end_of_week_reflection(week)
        player.tick_status_effects()

        return player.is_game_over()

    # ============================================================
    # 普通週
    # ============================================================
    def _apply_extra_events(self) -> int:
        """週開始時觸發所有額外事件；回傳本週額外時間消耗總量。"""
        from character import EXTRA_EVENTS
        player  = self.player
        ev_map  = {e["id"]: e for e in EXTRA_EVENTS}
        total_t = 0
        for ev_id in getattr(player, "extra_events", []):
            ev = ev_map.get(ev_id)
            if not ev:
                continue
            tc  = ev.get("time_cost", 0)
            md  = ev.get("money_delta", 0)
            sat = ev.get("satisfaction_delta", 0)
            total_t      += tc
            player.money += md
            if sat != 0:
                player.change_satisfaction(sat)
            lines = []
            if tc > 0:
                lines.append(f"時間 -{tc}")
            if md != 0:
                lines.append(f"金錢 {'+' if md >= 0 else ''}{md}")
            if sat != 0:
                lines.append(f"自我滿足度 {'+' if sat > 0 else ''}{sat}")
            show_extra_event_popup(lines or ["（本週生效）"], ev["name"],
                                   ev.get("popup_color", (155, 100, 50)))
        return total_t

    def _normal_week(self, week: int):
        player = self.player

        # 每週開始體力回滿
        player.stamina = player.stamina_max

        notify(f"\n📅 【第 {week} 週 行事曆提示】")

        # ── 週前劇情（台詞、選擇、事件）──────────────────────
        self._pre_action_narrative(week)

        # ── 額外事件（第 2 週起）──────────────────────────
        extra_cost = 0
        if week > 1:
            extra_cost = self._apply_extra_events()

        # ── 點名事件（特定週次：額外事件後、滿意度判定前）────
        roll_call_course = None
        if week in ROLL_CALL_WEEKS:
            _subjects = [k for k in player.subject_exp.keys() if k != "綜合"]
            if _subjects:
                roll_call_course = random.choice(_subjects)
                set_roll_call(roll_call_course)
                notify(f"📋 點名通知：【{roll_call_course}】本週教授將進行點名！")

        # ── 自我滿意度狀態判定（所有週初事件結束後、行動開始前）──
        for name, msg, color in player.apply_weekly_status():
            show_extra_event_popup([msg], f"【{name}】", color)

        # ── 計算本週可支配時間（狀態乘數已套用）──────────────
        time_units = max(1, player.get_effective_time() - extra_cost)
        notify(f"\n本週可支配時間：{time_units} 單位")

        # ── 行動選擇迴圈 ──────────────────────────────────
        remaining_time = time_units
        attended_class = False     # 本週是否有執行「正常上課」（點名結算用）
        full_timer = 0             # 飽腹倒數格數（>0 表示飽腹中）
        set_time(remaining_time)   # 初始化底部標籤列

        while remaining_time >= 0:
            set_player(player)     # 刷新狀態欄
            set_time(remaining_time)

            # choice = get_player_choice(ACTIONS)  # 因套用pygame而調整
            choice = ask_choice(ACTIONS)

            if choice == 0:
                break

            # ── 特殊行動（負值 index）─────────────────────────
            if choice < 0:
                sa = SPECIAL_ACTIONS[(-choice) - 1]

                # 進食：飽腹中不可用 / 錢不夠不可用
                if sa["id"] == "eat":
                    if full_timer > 0:
                        notify(f"😶 你還不餓，飽腹狀態剩 {full_timer} 個時間格後解除。")
                        continue
                    if player.money < sa.get("money_cost", 0):
                        notify(f"💸 錢不夠！【{sa['name']}】需要 ${sa['money_cost']}，"
                               f"目前只有 ${player.money}。")
                        continue

                self._execute_special_action(sa, roll_call_course)
                remaining_time += sa.get("time_gain", 0)
                set_time(remaining_time)

                if sa.get("gives_full_status"):
                    full_timer = 3
                    set_special_disabled({"進食": 3})
                # 特殊行動不觸發突發事件，直接繼續
                continue

            action = ACTIONS[choice - 1]

            # 道具店：不消耗時間單位，直接開店再回到行動選單
            if action["id"] == "shop":
                self.shop.open_shop()
                continue

            # 時間即將耗盡（本行動會使時間變成負數）→ 警告確認
            if remaining_time - 1 < 0:
                trigger_time_overflow_warning()   # 震動 + damage6
                confirm = ask_yn(
                    "本週時間已耗盡",
                    yes_label="強行繼續",
                    no_label="結束本週",
                    show_ctx=False,
                )
                if not confirm:
                    break
                # 玩家確認強行繼續：執行動作後立刻結束本週（時間不顯示負數）
                if action["stamina_cost"] > player.stamina:
                    confirm2 = ask_yn(
                        f"體力剩餘 {player.stamina} 點，執行此行動可能會導致生病！",
                        yes_label="仍要執行",
                        no_label="還是算了",
                        show_ctx=False,
                    )
                    if not confirm2:
                        continue
                self._execute_action(action)
                if action["id"] == "attend_class":
                    attended_class = True
                self.event_sys.roll_event_after_action(week)   # 行動後突發事件
                # 普通行動消耗一格時間 → 飽腹倒數
                if full_timer > 0:
                    full_timer -= 1
                    if full_timer == 0:
                        set_special_disabled({})
                    else:
                        set_special_disabled({"進食": full_timer})
                break

            if action["stamina_cost"] > player.stamina:
                confirm = ask_yn(
                    f"體力剩餘 {player.stamina} 點，執行此行動可能會導致生病！",
                    yes_label="仍要執行",
                    no_label="還是算了",
                    show_ctx=False,
                )
                if not confirm:
                    continue

            self._execute_action(action)
            if action["id"] == "attend_class":
                attended_class = True
            self.event_sys.roll_event_after_action(week)   # 行動後突發事件
            remaining_time -= 1
            set_time(remaining_time)

            # 普通行動消耗一格時間 → 飽腹倒數
            if full_timer > 0:
                full_timer -= 1
                if full_timer == 0:
                    set_special_disabled({})
                else:
                    set_special_disabled({"進食": full_timer})

        # 週結束時清除飽腹停用狀態
        if full_timer > 0:
            set_special_disabled({})

        # ── 點名結算（週末，所有行動結束後）────────────────────
        if roll_call_course is not None:
            if not attended_class:
                player.grades["參與度"] = max(0, player.grades["參與度"] - 10)
                notify(f"⚠️  【{roll_call_course}】點名缺席！課堂參與度 -10。")
            else:
                notify(f"✅ 本週有上課，【{roll_call_course}】點名順利通過。")
            clear_roll_call()

    # ============================================================
    # 週前劇情（行動選單出現之前）
    # ============================================================

    # 固定課表資料（第一週展示）
    _WEEK1_TIMETABLE = [
        {"day": "週一", "name": "統計學",       "time": "08:10–09:00", "credits": 3},
        {"day": "週一", "name": "管理學",       "time": "10:20–12:10", "credits": 3},
        {"day": "週二", "name": "商管程式設計", "time": "13:20–16:20", "credits": 3},
        {"day": "週三", "name": "統計學",       "time": "08:10–09:00", "credits": 0},
        {"day": "週三", "name": "會計學",       "time": "10:20–12:10", "credits": 3},
        {"day": "週四", "name": "經濟學",       "time": "09:10–12:10", "credits": 4},
        {"day": "週五", "name": "管理學",       "time": "13:20–15:10", "credits": 0},
    ]

    # 第二週加簽課程選項
    _WEEK2_COURSES = [
        {"name": "普通心理學",   "credits": 3},
        {"name": "商管程式設計", "credits": 3},
        {"name": "總經原",       "credits": 4},
        {"name": "普通化學丙",   "credits": 3},
    ]

    def _calc_quiz_score(self, base=40, rand_range=(-5, 5)) -> int:
        """依體力比例 + 運氣 + 熟練度計算小考分數（0–100）。"""
        p = self.player
        stamina_ratio = p.stamina / max(p.stamina_max, 1)
        score = (base
                 + min(30, int(stamina_ratio * 30))
                 + min(20, p.luck // 5)
                 + min(10, sum(p.subject_exp.values()) // 10)
                 + random.randint(*rand_range))
        return max(0, min(100, score))

    def _pre_action_narrative(self, week: int):
        """每週行動選單出現前的劇情、台詞與互動選擇。"""
        player = self.player

        if week == 1:
            tell_story(["新的一學期又開始了，帶著暑假的好心情來上課。"])
            notify_timetable(self._WEEK1_TIMETABLE)
            tell_story([
                "「吼呦，雖然大部分的課是我自己選的，不過這學期的課表看起來也太無聊了吧！」",
                "上課時太無聊，眼睛快要闔起來了，下課時要不要去商店裡繞一繞？",
            ])
            if ask_yn("要前往道具店嗎？"):
                self.shop.open_shop()
            tell_story(["「天啊這禮拜忘記去加簽了，只能下禮拜再去了TT」"])

        elif week == 2:
            tell_story([
                "因為上週忘記去加簽，加簽大地開始！",
                "「太晚才想到了，目前還能加簽的課還有這些，要去簽什麼課啊？」",
            ])
            labels = [f"{c['name']}（{c['credits']} 學分）" for c in self._WEEK2_COURSES]
            choice = ask_choice(labels)
            if choice > 0:
                course = self._WEEK2_COURSES[choice - 1]
                self._week2_course = course
                # 將加簽科目納入熟練度系統（若尚未存在則以 0 初始化）
                if course["name"] not in player.subject_exp:
                    player.subject_exp[course["name"]] = 0
                tell_story([f"努力跑了好多課程，最後加簽成功科目有：{course['name']}。"])
                if course["name"] == "商管程式設計":
                    self.skill_sys.gain_exp("綜合", 5)
            else:
                self._week2_course = {"name": "（無）", "credits": 0}
                tell_story(["猶豫了一下，最後還是沒有加任何課。"])

        elif week == 3:
            tell_story([
                "開始進入學期節奏。",
                "「課表看起來還可以，但每天還是莫名很累。」",
                "「有人已經默默開始翹課了。」",
            ])

        elif week == 4:
            tell_story([
                "⚠️ 小考來臨(1)！",
                "「原本想說作業應該不難，結果一打開發現要求比想像中還多。」",
                "「都忘記這份作業居然要交三千字讀書心得，我完了。」",
                "「等一下，居然還有兩個小考嗎！根本讀不完啊！」",
                "「這幾天都要熬夜了，要先去商店看一下有什麼道具可以用嗎？」",
            ])
            if ask_yn("要前往道具店嗎？"):
                self.shop.open_shop()
            # 計算並儲存小考一分數
            self._quiz1_score = self._calc_quiz_score(base=40, rand_range=(-5, 5))
            player.grades["小考"] = max(player.grades["小考"], float(self._quiz1_score))
            if self._quiz1_score >= 80:
                player.change_satisfaction(5)
            else:
                player.change_satisfaction(-8)
            tell_story(["助教：『小考成績約兩週後公布，請大家到時候留意 NTU COOL 的通知。』"])

        elif week == 5:
            tell_story([
                "⚡ 緊急狀況：作業和小考成績公布(1)！",
                "「行事曆上的待辦事項開始變多，每次都覺得有東西快到期了。」",
                "「原本以為還很閒，結果發現突然多了好多事情。欸？等等。」",
            ])
            player.grades["作業"] = max(player.grades["作業"], 90.0)
            notify_grade_report([
                {"name": "小考一", "score": self._quiz1_score},
                {"name": "作業一", "score": 90},
            ])
            player.revealed_grades.update(["作業", "小考"])

        elif week == 6:
            tell_story([
                "系上聚餐。",
                "「朋友突然拉你去參加系上聚餐，原本只想待一下，結果不知不覺玩到很晚。」",
            ])
            player.change_satisfaction(10)
            player.consume_stamina(5)

        elif week == 7:
            tell_story([
                "期中前夕，備考中。",
                "「明明早八遲到了二十分鐘，但我居然是第五個到教室的。」",
                "「來上課的人真的少了好多，而且圖書館變得好難找位置。」",
            ])

        elif week == 9:
            tell_story([
                "🎉 系學會會長在群組裡公告招工事宜。",
                "「好朋友問你想不想一起當工人。」",
            ])
            if ask_yn("要答應幫忙辦活動嗎？"):
                player.luck += 10
                player.consume_stamina(8)
                job_choice = ask_choice(["美宣：畫超級漂亮的圖",
                                         "公關：寫文案、和廠商對接",
                                         "現場工人：搬東西、場佈、場復"])
                if job_choice == 1:
                    self._week9_job = "美宣"
                    player.change_satisfaction(10)
                    tell_story(["✨ 答應成為工人！運氣 +10，體力 -8。",
                                 "「你運用了你的美術天分，大家都說你畫的圖很棒！滿足感 +10。」"])
                elif job_choice == 2:
                    self._week9_job = "公關"
                    player.luck += 5
                    player.change_satisfaction(8)
                    tell_story(["✨ 答應成為工人！運氣 +10，體力 -8。",
                                 "「你動用了你的社交技能，和廠商對接超順利！運氣 +5，滿足感 +8。」"])
                else:
                    self._week9_job = "現場工人"
                    player.consume_stamina(5)
                    player.change_satisfaction(5)
                    tell_story(["✨ 答應成為工人！運氣 +10，體力 -8。",
                                 "「你負責搬東西、場佈、場復，累翻了但活動很成功！體力 -5，滿足感 +5。」"])
            else:
                tell_story(["🛏️ 決定把時間留給自己，好好休息。"])
                player.change_satisfaction(3)

        elif week == 10:
            tell_story([
                "學期已經過了一半，大家開始討論暑假的規劃。",
                "「朋友已經開始在討論暑假實習、雙主修和交換學生了。」",
                "同學：「你有想好暑假要幹嘛了嗎？」",
                "「呃...還沒。」",
            ])

        elif week == 11:
            tell_story([
                "分組報告地獄開始。",
                "「組員想要約時間討論，但大家的空堂完全對不上。」",
                "「有人完全消失，在群組裡潛水，也有人凌晨兩點還在改簡報。」",
            ])

        elif week == 12:
            tell_story([
                "⚠️ 小考來臨(2)！",
                "「最近常常一邊吃飯一邊看 NTU COOL，深怕又漏掉什麼公告。」",
                "「睡眠時間太混亂了，有時甚至不知道今天星期幾。」",
                "「不過還好我已經讀完這週小考了，耶。」",
            ])
            # 計算並儲存小考二分數
            self._quiz2_score = self._calc_quiz_score(base=35, rand_range=(-10, 10))
            player.grades["小考"] = max(player.grades["小考"], float(self._quiz2_score))
            if self._quiz2_score >= 80:
                player.change_satisfaction(5)
            else:
                player.change_satisfaction(-8)
            tell_story([
                "「考完小考後，大家開始討論題目。」",
                "「欸？我剛才有寫到這題嗎？」",
            ])

        elif week == 13:
            tell_story([
                "⚠️ 停修期限截止在即！",
                "「天啊我的成績看起來超不妙，還是在停修截止前，趕快停修呢？」",
            ])
            if ask_yn("要壯士斷腕選擇停修某一科嗎？"):
                course_choice = ask_choice([
                    "日文：好不容易加簽到的課，但作業太重、期末還要交報告",
                    "統計學：系訂必修，作業不太會寫，不知道能不能撐到期末",
                ])
                player.restore_stamina(10)
                player.luck = max(0, player.luck - 10)
                if course_choice == 1:
                    player.change_satisfaction(-5)
                    tell_story(["💥 停修【日文】成功！體力 +10，但運氣 -10，滿足感 -5。"])
                else:
                    player.subject_exp["統計學"] = max(0, player.subject_exp.get("統計學", 0) - 8)
                    tell_story(["💥 停修【統計學】成功！體力 +10，但運氣 -10，熟練度 -8。"])
            else:
                player.change_satisfaction(5)
                tell_story(["💪 決定硬著頭皮撐下去！滿足感 +5。"])
            tell_story(["「無論是否停休，每堂課教授都在提醒：『距離期末只剩幾週了，大家要開始讀書囉！』」"])

        elif week == 14:
            tell_story([
                "🔥 期末報告和作業爆炸！",
                "「簡報、報告、期末作業突然一起出現，行事曆被排得密密麻麻。」",
                "「到底要先處理什麼東西啊！」",
            ])
            ans = ask_choice([
                "製作小組簡報：從零開始排版，完成後作業 70 分，體力 -10",
                "撰寫個人五千字書面報告：最困難的部分還等著你，完成後作業 85 分，體力 -20",
                "撰寫個人三千字觀影心得：要先重看一遍電影才能寫，完成後作業 65 分，體力 -5",
            ])
            if ans == 1:
                player.grades["作業"] = max(player.grades["作業"], 70.0)
                player.consume_stamina(10)
                player.change_satisfaction(-3)
                tell_story(["🤝 順利完成小組簡報，至少不會被組員罵。"])
            elif ans == 2:
                player.grades["作業"] = max(player.grades["作業"], 85.0)
                player.consume_stamina(20)
                player.change_satisfaction(-8)
                tell_story(["📝 瘋狂趕工完成五千字報告！作業成績提升。"])
            else:
                player.grades["作業"] = max(player.grades["作業"], 65.0)
                player.consume_stamina(5)
                player.change_satisfaction(-2)
                tell_story(["🎬 重看了一遍電影，心得總算寫完了。"])
            tell_story(["「唉，小考成績出來了，該來的還是來了。」"])
            notify_grade_report([{"name": "小考二", "score": self._quiz2_score}])
            player.revealed_grades.add("小考")

        elif week == 15:
            tell_story([
                "最後衝刺！",
                "「總圖、社科圖都沒位子，到處都有人在趕報告，去系館看看好了。」",
                "「系館半夜依然燈火通明，平常大家此起彼落的聊天聲，都變成了敲擊鍵盤的聲音。」",
                "「大家見面的第一句話從『要一起吃飯嗎』變成『你做完了嗎』。」",
            ])

        else:
            # 其餘週（無特定劇情）
            tell_story(["🍃 本週校園風平浪靜，照著自己的步調前進吧。"])

    def _execute_action(self, action: dict):
        player  = self.player
        cost    = action["stamina_cost"]
        results = []   # 供彈出視窗顯示的結果列表

        # ── 體力 ──────────────────────────────────────────────
        if cost > 0:
            player.consume_stamina(cost)
            results.append(f"體力 -{cost}")
        else:
            player.restore_stamina(abs(cost))
            results.append(f"體力 +{abs(cost)}")

        # ── 課業熟練度 ────────────────────────────────────────
        exp = action.get("exp_gain", 0)
        if exp > 0:
            # 讓玩家選擇本次要加強哪一科
            _subj_opts = [s for s in player.subject_exp.keys() if s != "綜合"]
            if _subj_opts:
                _idx = ask_subject_popup("這次要集中精力在哪一科？", _subj_opts)
                # _idx == 0 表示異常情況，預設第一科
                _chosen = _subj_opts[(_idx - 1) if _idx > 0 else 0]
            else:
                _chosen = "綜合"
            _actual, _segs = self.skill_sys.gain_exp(_chosen, exp)
            results.append(f"【{_chosen}】熟練度 +{_actual}")
            results.append(("multi", _segs))   # 多色標注行

        # ── 自我滿足度 ────────────────────────────────────────
        sat = action.get("satisfaction", 0)
        player.change_satisfaction(sat)
        if sat != 0:
            sign = "+" if sat > 0 else ""
            results.append(f"自我滿足度 {sign}{sat}")
        # 若自我滿足度過低，附加警示行到彈出視窗
        if player.satisfaction < 60:
            results.append("---")
            results.append("! 自我滿足度過低，本週可支配時間大幅下降")

        # ── 課堂參與度 ────────────────────────────────────────
        if "participation" in action:
            gain = action["participation"]
            player.grades["參與度"] = min(100, player.grades["參與度"] + gain)
            player.revealed_grades.add("參與度")
            results.append(f"課堂參與度 +{gain}")

        # ── 金錢 ──────────────────────────────────────────────
        if "money_gain" in action:
            player.money += action["money_gain"]
            results.append(f"金錢 +{action['money_gain']} 元")
            notify(f"  賺到 {action['money_gain']} 元（現有：{player.money} 元）")

        notify(f"  ✔ 執行【{action['name']}】完成。")

        # ── 觸發彈出結果視窗 ──────────────────────────────────
        show_action_result(results, title=action["name"])

    def _execute_special_action(self, sa: dict, roll_call_course) -> None:
        """執行特殊行動（熬夜 / 翹課 / 進食）。不消耗時間單位，不觸發突發事件。"""
        player  = self.player
        results = []

        # ── 體力 ──────────────────────────────────────────────
        stamina_cost = sa.get("stamina_cost", 0)
        if stamina_cost > 0:
            player.consume_stamina(stamina_cost)
            results.append(f"體力 -{stamina_cost}")
        elif stamina_cost < 0:
            player.restore_stamina(-stamina_cost)
            results.append(f"體力 +{-stamina_cost}")

        # ── 金錢 ──────────────────────────────────────────────
        money_cost = sa.get("money_cost", 0)
        if money_cost > 0:
            player.money -= money_cost
            results.append(f"金錢 -{money_cost}")

        # ── 自我滿足度 ────────────────────────────────────────
        sat = sa.get("satisfaction", 0)
        if sat != 0:
            player.change_satisfaction(sat)
            sign = "+" if sat > 0 else ""
            results.append(f"自我滿足度 {sign}{sat}")

        # ── 時間加成 ──────────────────────────────────────────
        if sa.get("time_gain", 0) > 0:
            results.append(f"時間 +{sa['time_gain']}")

        # ── 熬夜副作用 ────────────────────────────────────────
        if sa.get("allnighter_risk"):
            self.event_sys.set_allnighter_risk(0.10)
            results.append("睡過頭機率 ↑10%")

        # ── 翹課風險 ──────────────────────────────────────────
        if sa.get("quiz_miss_chance"):
            self._roll_skip_effects(player, roll_call_course)

        # ── 飽腹狀態 ──────────────────────────────────────────
        if sa.get("gives_full_status"):
            results.append("獲得「飽腹」狀態（3 個時間格後解除）")

        notify(f"  ✔ 執行【{sa['name']}】完成。")
        show_action_result(results, title=sa["name"])

    def _roll_skip_effects(self, player, roll_call_course) -> None:
        """翹課的隨機後果：可能錯過小考 / 點名。"""
        skip_prob = max(0.0, (100 - player.luck)) / 100
        if random.random() < skip_prob:
            player.grades["參與度"] = max(0, player.grades["參與度"] - 3)
            player.change_satisfaction(-5)
            notify("  📕 翹課結果：錯過了一次小考考核！參與度 -3，滿足感 -5。")
        if roll_call_course and random.random() < skip_prob:
            player.grades["參與度"] = max(0, player.grades["參與度"] - 2)
            notify(f"  📋 翹課時剛好是【{roll_call_course}】的點名日！參與度 -2。")

    # ============================================================
    # 期中 / 期末考
    # ============================================================
    def _pre_exam_check(self) -> float:
        player   = self.player
        modifier = 1.0

        # print("\n  🔍 考前狀態檢測中……")  # 因套用pygame而調整
        notify("\n  🔍 考前狀態檢測中……")
        # time.sleep(0.5)  # 因套用pygame而調整（pygame 不需要假暫停）

        if player.stamina < 30 and random.random() < 0.4:
            # print("  💀 悲劇！因為考前熬夜體力不支，你居然睡過頭了！")  # 因套用pygame而調整
            notify("  💀 悲劇！因為考前熬夜體力不支，你居然睡過頭了！")
            # print("  ⚠️ 趕到考場時時間只剩一半，本次考試總分打 5 折。")  # 因套用pygame而調整
            notify("  ⚠️ 趕到考場時時間只剩一半，本次考試總分打 5 折。")
            player.change_satisfaction(-15)
            modifier *= 0.5
            return modifier

        if player.luck < 40 and random.random() < 0.3:
            # print("  🔧 倒楣！騎腳踏車去考場的路上居然爆胎！")  # 因套用pygame而調整
            notify("  🔧 倒楣！騎腳踏車去考場的路上居然爆胎！")
            # print("  ⚠️ 滿頭大汗跑進考場，思緒混亂，考試總分打 85 折。")  # 因套用pygame而調整
            notify("  ⚠️ 滿頭大汗跑進考場，思緒混亂，考試總分打 85 折。")
            player.change_satisfaction(-8)
            modifier *= 0.85
            return modifier

        # print("  🍀 一切順利，你安全且準時地坐在考場座位上。")  # 因套用pygame而調整
        notify("  🍀 一切順利，你安全且準時地坐在考場座位上。")
        return modifier

    def _run_exam_mini_game(self, exam_type: str) -> float:
        notify(f"\n{exam_type}考：知識問答挑戰開始！")

        questions = [
            {
                "q": "台大三大夜沒有哪個之夜？",
                "options": ["會計之夜", "電機之夜", "南友之夜", "國企之夜"],
                "a": 1,
            },
            {
                "q": "下列何者不屬於三校聯盟？",
                "options": ["NTUST", "NTNU", "NTUE"],
                "a": 3,
            },
            {
                "q": "行政大樓前的傅鐘每次只敲幾下？",
                "options": ["20 下", "21 下", "22 下"],
                "a": 2,
            },
            {
                "q": "台大附近的餐廳何者不位於 118？",
                "options": ["三米三", "笑嘻嘻", "IMPASTA", "李記水餃"],
                "a": 1,
            },
            {
                "q": "台大附近的餐廳何者不位於水源商圈？",
                "options": ["塊雞師食物所", "大埔鐵板燒", "小高拉麵", "瑪莉珍披薩"],
                "a": 4,
            },
            {
                "q": "商管程式設計這門課是由哪個系的教授開設的？",
                "options": ["資工系", "資管系", "統計系"],
                "a": 1,
            },
        ]

        selected_qs   = random.sample(questions, 4)
        correct_count = 0

        for i, q in enumerate(selected_qs, start=1):
            notify(f"題目 {i}：{q['q']}")
            ans = ask_choice(q["options"])
            if ans == q["a"]:
                notify("  答對了！")
                correct_count += 1
            else:
                notify("  選錯了……")

        return correct_count / len(selected_qs)

    def _midterm_week(self):
        player = self.player

        notify("\n📋 ═══ 期中考週！═══")
        notify("「每天都有人在便利商店熬夜念書，校園裡瀰漫著咖啡味。」")
        notify("「考完一科後發現下一科根本還沒讀完。」")

        ask_exam_start("準備期中考")

        exam_modifier    = self._pre_exam_check()
        base_stats_score = self._calculate_exam_score("期中") * 0.5
        mini_game_rate   = self._run_exam_mini_game("期中")
        mini_game_score  = mini_game_rate * 100 * 0.5

        total_score = (base_stats_score + mini_game_score) * exam_modifier
        player.grades["期中"] = max(0.0, min(100.0, total_score))
        player.revealed_grades.add("期中")

        # print(f"\n📊 期中考最終成績：{player.grades['期中']:.1f} 分")  # 因套用pygame而調整
        notify(f"\n📊 期中考最終成績：{player.grades['期中']:.1f} 分")
        # print(f"  實力底分：{base_stats_score:.1f}")  # 因套用pygame而調整
        notify(f"  實力底分：{base_stats_score:.1f}")
        # print(f"  考場發揮：{mini_game_score:.1f}")  # 因套用pygame而調整
        notify(f"  考場發揮：{mini_game_score:.1f}")

        if player.grades["期中"] >= 60:
            # print("  ✅ 順利飛過及格線！")  # 因套用pygame而調整
            notify("  ✅ 順利飛過及格線！")
            player.change_satisfaction(10)
        else:
            # print("  ❌ 望著滿江紅的考卷，你覺得這學期前途堪憂……")  # 因套用pygame而調整
            notify("  ❌ 望著滿江紅的考卷，你覺得這學期前途堪憂……")
            player.change_satisfaction(-15)

    def _final_week(self):
        player = self.player

        # print("\n🎯 ═══ 期末考週！（最終關卡）═══")  # 因套用pygame而調整
        notify("\n🎯 ═══ 期末考週！（最終關卡）═══")

        ask_exam_start("準備期末考")

        exam_modifier    = self._pre_exam_check()
        base_stats_score = self._calculate_exam_score("期末") * 0.5
        mini_game_rate   = self._run_exam_mini_game("期末")
        mini_game_score  = mini_game_rate * 100 * 0.5

        total_score = (base_stats_score + mini_game_score) * exam_modifier
        player.grades["期末"] = max(0.0, min(100.0, total_score))
        player.revealed_grades.add("期末")

        # print(f"\n📊 期末考最終成績：{player.grades['期末']:.1f} 分")  # 因套用pygame而調整
        notify(f"\n📊 期末考最終成績：{player.grades['期末']:.1f} 分")
        # print(f"  實力底分：{base_stats_score:.1f}")  # 因套用pygame而調整
        notify(f"  實力底分：{base_stats_score:.1f}")
        # print(f"  考場發揮：{mini_game_score:.1f}")  # 因套用pygame而調整
        notify(f"  考場發揮：{mini_game_score:.1f}")

        if player.grades["期末"] >= 60:
            # print("  ✅ 成功撐過期末大魔王！")  # 因套用pygame而調整
            notify("  ✅ 成功撐過期末大魔王！")
            player.change_satisfaction(15)
        else:
            # print("  ❌ 考卷上的分數宣判了你的死刑……")  # 因套用pygame而調整
            notify("  ❌ 考卷上的分數宣判了你的死刑……")
            player.change_satisfaction(-20)

        notify("「考完最後一科的瞬間，突然有種不真實感。」")
        notify("「校園裡安靜了很多，路上可以見到許多拖著行李箱，準備回家的人。」")

    def _calculate_exam_score(self, exam_type: str) -> float:
        player = self.player

        # 只計算五個正式科目（排除 "綜合" 等歷史殘留 key）
        _valid = {k: v for k, v in player.subject_exp.items() if k != "綜合"}
        if not _valid:
            avg_exp = 0
        else:
            avg_exp = sum(_valid.values()) / len(_valid)

        intel_bonus      = 1.0 + min(player.intel / 200, 0.5)
        luck_roll        = random.uniform(-0.1, 0.1) + (player.luck - 50) / 500
        luck_multiplier  = 1.0 + luck_roll
        raw_score        = avg_exp * intel_bonus * luck_multiplier

        return max(0.0, min(100.0, raw_score))

    # ============================================================
    # 週末與最終結算
    # ============================================================
    # 每週心情結語（第二週動態填入學分，其餘為固定字串）
    _WEEKLY_QUOTES = {
        1:  "下禮拜要開始加簽地獄了...",
        3:  "開學的新鮮感好像慢慢消失了。",
        4:  "還好最後有讀完，不管小考考得怎樣，我下週開始一定要改掉拖延的習慣。",
        5:  "不是說兩週後公布嗎？我還沒準備好面對分數欸！",
        6:  "參加活動還不錯，但這週待辦事項沒有做完TT。",
        7:  "大家怎麼突然都開始讀書了？",
        8:  "終於考完了…吧？",
        9:  "原來系上要辦活動，之前怎麼沒聽說？",
        10: "...蛤？為什麼只有我還在想明天晚餐要吃什麼。",
        11: "比起報告本身，分組好像才是最大的挑戰，雷組員真的可以下去了╰(‵□′)╯",
        12: "？？？？？完了。",
        13: "我不聽我不聽，拜託不要再提醒我期末了啦。",
        14: "哪有人在停修截止後才公布小考分數的！",
        15: "撐過這週就快解脫了…",
        16: "這學期終於結束了，好感動。",
    }

    def _end_of_week_reflection(self, week: int):
        notify("\n💭 【週末內心總結】")
        player = self.player

        # ── 週別專屬心情結語 ───────────────────────────────────
        if week == 2:
            course_name = self._week2_course["name"] if self._week2_course else "（無）"
            credits     = self._week2_course["credits"] if self._week2_course else 0
            quote = f"多了 {credits} 學分（{course_name}），真是太好了TT。"
        else:
            quote = self._WEEKLY_QUOTES.get(week, "")

        if quote:
            notify(f"  💭 {quote}")

        # ── 體力狀態通用結語 ───────────────────────────────────
        stamina_ratio = player.stamina / max(player.stamina_max, 1)
        if stamina_ratio > 0.7:
            outcome_text        = "狀態極佳，感覺下週能做更多事！"
            satisfaction_change = 5
        elif stamina_ratio > 0.3:
            outcome_text        = "平穩度過，大學生活就是這樣吧。"
            satisfaction_change = 2
        else:
            outcome_text        = "筋疲力竭，只想躺在床上當植物人……"
            satisfaction_change = -8

        notify(f"  本週狀態：{outcome_text}")
        player.change_satisfaction(satisfaction_change)

    def final_settlement(self):
        player      = self.player
        final_score = player.calculate_final_score()

        # print("\n" + "=" * 50)  # 因套用pygame而調整
        notify("\n" + "=" * 50)
        # print("  🎓 學期結束！最終成績結算")  # 因套用pygame而調整
        notify("  🎓 學期結束！最終成績結算")
        # print("=" * 50)  # 因套用pygame而調整
        notify("=" * 50)
        # print(f"  參與度 (10%)：{player.grades['參與度']:.1f}")  # 因套用pygame而調整
        notify(f"  參與度 (10%)：{player.grades['參與度']:.1f}")
        # print(f"  作業   (20%)：{player.grades['作業']:.1f}")  # 因套用pygame而調整
        notify(f"  作業   (20%)：{player.grades['作業']:.1f}")
        # print(f"  小考   (10%)：{player.grades['小考']:.1f}")  # 因套用pygame而調整
        notify(f"  小考   (10%)：{player.grades['小考']:.1f}")
        # print(f"  期中   (30%)：{player.grades['期中']:.1f}")  # 因套用pygame而調整
        notify(f"  期中   (30%)：{player.grades['期中']:.1f}")
        # print(f"  期末   (30%)：{player.grades['期末']:.1f}")  # 因套用pygame而調整
        notify(f"  期末   (30%)：{player.grades['期末']:.1f}")
        # print("  ─────────────────")  # 因套用pygame而調整
        notify("  ─────────────────")
        # print(f"  加權總分：{final_score:.1f} 分")  # 因套用pygame而調整
        notify(f"  加權總分：{final_score:.1f} 分")
        notify("")

        if final_score >= 80 and player.satisfaction >= 70:
            # print("  🌟 平衡型結局：成績漂亮，身心狀態也維持得很好。")  # 因套用pygame而調整
            notify("  🌟 平衡型結局：成績漂亮，身心狀態也維持得很好。")
        elif final_score >= 60 and player.satisfaction >= 60:
            # print("  🎉 及格快樂結局：你成功渡過了這學期，可以放暑假了！")  # 因套用pygame而調整
            notify("  🎉 及格快樂結局：你成功渡過了這學期，可以放暑假了！")
        elif final_score >= 60 and player.satisfaction < 60:
            # print("  🫠 成績過了但身心崩潰：你及格了，但也快沒電了。")  # 因套用pygame而調整
            notify("  🫠 成績過了但身心崩潰：你及格了，但也快沒電了。")
        else:
            # print("  💸 很遺憾……成績未達及格，明年準備重修吧。")  # 因套用pygame而調整
            notify("  💸 很遺憾……成績未達及格，明年準備重修吧。")

        # print(f"\n  最終自我滿足度：{player.satisfaction}")  # 因套用pygame而調整
        notify(f"\n  最終自我滿足度：{player.satisfaction}")
        # print(f"  剩餘金錢：{player.money} 元")  # 因套用pygame而調整
        notify(f"  剩餘金錢：{player.money} 元")
        # print("=" * 50)  # 因套用pygame而調整
        notify("=" * 50)
