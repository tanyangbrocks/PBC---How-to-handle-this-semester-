# ============================================================
#  模組：shop.py — 經濟與道具店
# ============================================================
# 這個模組處理遊戲中的交易系統。
# 玩家可以用打工賺來的錢購買道具，來恢復體力或提升能力。
# ============================================================

import random
from ui import display_menu, get_player_choice, notify, open_shop_ui

class Shop:
    """
    道具商店類別。
    這裡存放了商品的清單，並負責處理購買邏輯。
    """
    def __init__(self, player, event_sys=None):
        self.player    = player
        self.event_sys = event_sys   # 用於咖啡的睡過頭風險效果
        self.items = [
            {
                "id": "coffee",
                "name": "咖啡",
                "price": 25,
                "desc": "恢復 10 點體力，但睡過頭觸發機率增加 10%。",
                "stamina_restore": 10,
                "allnighter_risk": 0.10,
            },
            {
                "id": "snack",
                "name": "點心",
                "price": 40,
                "desc": "恢復 5 點體力，自我滿足度 +4（70% 機率）。",
                "stamina_restore": 5,
                "satisfaction_gain": 4,
                "satisfaction_miss_chance": 0.30,
            },
            {
                "id": "energy_drink_monster",
                "name": "猛獸能量",
                "price": 60,
                "desc": "恢復 25 點體力，並獲得「激勵」狀態（2週）。",
                "stamina_restore": 25,
                "status": "激勵",
                "duration": 2
            },
            {
                "id": "energy_drink_bplus",
                "name": "爆力打B+",
                "price": 200,
                "desc": "恢復 30 點體力，並獲得「激勵」狀態（4週）。",
                "stamina_restore": 30,
                "status": "激勵",
                "duration": 4
            },
            {
                "id": "textbook_ref",
                "name": "學霸筆記",
                "price": 300,
                "desc": "智力永久提升 5 點。",
                "intel_gain": 5
            },
            {
                "id": "memory_toast",
                "name": "記憶吐司",
                "price": 500,
                "desc": "智力永久提升 10 點。",
                "intel_gain": 10
            },
            {
                "id": "game_console",
                "name": "新款遊戲機",
                "price": 1000,
                "desc": "自我滿足感大幅提升 30 點。",
                "satisfaction_gain": 30
            },
            {
                "id": "idol_photo",
                "name": "偶像拍立得",
                "price": 1500,
                "desc": "自我滿足感大幅提升 50 點。",
                "satisfaction_gain": 50
            },
            {
                "id": "exam_pencil",
                "name": "考試鉛筆組",
                "price": 80,
                "desc": "獲得「幸運」狀態 1 週。考前衝刺必備！",
                "status": "幸運",
                "duration": 1
            },
            {
                "id": "temple_amulet",
                "name": "廟口平安符",
                "price": 200,
                "desc": "運氣永久提升 3 點。台灣香火保佑！",
                "luck_gain": 3
            },
            {
                "id": "lucky_omamori",
                "name": "幸運御守",
                "price": 350,
                "desc": "運氣永久提升 5 點。日式神社加持！",
                "luck_gain": 5
            }
        ]

    def open_shop(self):
        """
        開啟商店介面（使用 pygame 圖形化 UI）。
        購買邏輯由 ui.py 事件處理器直接套用，此處只負責啟動與結束。
        """
        notify("\n🏪 前往道具店選購！")
        open_shop_ui(self.items, event_sys=self.event_sys)
        notify("👋 謝謝光臨道具店，歡迎下次再來！")

    def _buy_item(self, item):
        """
        私有方法：處理購買道具的細節與效果套用。
        """
        if self.player.money < item["price"]:
            # print(f"❌ 錢不夠喔！你需要 ${item['price']}，但目前只有 ${self.player.money}。")  # 因套用pygame而調整
            notify(f"❌ 錢不夠喔！你需要 ${item['price']}，但目前只有 ${self.player.money}。")
            return
        self.player.money -= item["price"]
        # print(f"💰 購買了【{item['name']}】，剩餘：${self.player.money}")  # 因套用pygame而調整
        notify(f"💰 購買了【{item['name']}】，剩餘：${self.player.money}")
        if "stamina_restore" in item:
            self.player.restore_stamina(item["stamina_restore"])
            # print(f"  ✨ 恢復了 {item['stamina_restore']} 點體力！")  # 因套用pygame而調整
            notify(f"  ✨ 恢復了 {item['stamina_restore']} 點體力！")
        if "intel_gain" in item:
            self.player.intel += item["intel_gain"]
            # print(f"  📖 智力提升了 {item['intel_gain']} 點！")  # 因套用pygame而調整
            notify(f"  📖 智力提升了 {item['intel_gain']} 點！")
        if "satisfaction_gain" in item:
            _miss_chance = item.get("satisfaction_miss_chance", 0.0)
            if _miss_chance > 0 and random.random() < _miss_chance:
                notify("  😐 吃了點心但心情沒什麼起色……（滿足感未提升）")
            else:
                self.player.change_satisfaction(item["satisfaction_gain"])
                notify(f"  🎮 感覺心靈得到了昇華（滿足感提升）！")
        if "luck_gain" in item:
            self.player.luck += item["luck_gain"]
            # print(f"  🍀 運氣提升了 {item['luck_gain']} 點！")  # 因套用pygame而調整
            notify(f"  🍀 運氣提升了 {item['luck_gain']} 點！")
        if "status" in item:
            self.player.add_status(item["status"], item["duration"])
        if "allnighter_risk" in item and self.event_sys is not None:
            self.event_sys.set_allnighter_risk(item["allnighter_risk"])
            notify(f"  ⚠️ 睡過頭觸發機率增加 {int(item['allnighter_risk'] * 100)}%！")
