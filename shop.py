# ============================================================
#  模組：shop.py — 經濟與道具店
# ============================================================
# 這個模組處理遊戲中的交易系統。
# 玩家可以用打工賺來的錢購買道具，來恢復體力或提升能力。
# ============================================================

from ui import display_menu, get_player_choice

class Shop:
    """
    道具商店類別。
    這裡存放了商品的清單，並負責處理購買邏輯。
    """

    def __init__(self, player):
        self.player = player
        # 商品清單：定義每個道具的名稱、價格、描述與效果
        self.items = [
            {
                "id": "coffee",
                "name": "超商咖啡",
                "price": 50,
                "desc": "恢復 15 點體力，學生熬夜良伴。",
                "stamina_restore": 15
            },
            {
                "id": "energy_drink",
                "name": "提神飲料",
                "price": 120,
                "desc": "恢復 25 點體力，並獲得「激勵」狀態（2週）。",
                "stamina_restore": 25,
                "status": "激勵",
                "duration": 2
            },
            {
                "id": "textbook_ref",
                "name": "學霸筆記",
                "price": 300,
                "desc": "智力永久提升 5 點。",
                "intel_gain": 5
            },
            {
                "id": "game_console",
                "name": "新款遊戲機",
                "price": 500,
                "desc": "自我滿足感大幅提升 30 點。",
                "satisfaction_gain": 30
            }
        ]

    def open_shop(self):
        """
        開啟商店介面，讓玩家可以反覆購買直到選擇離開。
        """
        print("\n🏪 【校園道具店】")
        print(f"  目前餘額：${self.player.money}")
        
        while True:
            # 顯示商品選單
            display_menu(self.items, title="商品列表")
            choice = get_player_choice(self.items)

            if choice == 0:
                print("👋 謝謝光臨，歡迎下次再來！")
                break
            
            # 取得玩家選擇的道具
            item = self.items[choice - 1]
            self._buy_item(item)

    def _buy_item(self, item):
        """
        私有方法：處理購買道具的細節與效果套用。
        """
        # 1. 檢查餘額
        if self.player.money < item["price"]:
            print(f"❌ 錢不夠喔！你需要 ${item['price']}，但目前只有 ${self.player.money}。")
            return

        # 2. 扣款
        self.player.money -= item["price"]
        print(f"💰 購買了【{item['name']}】，剩餘：${self.player.money}")

        # 3. 執行效果
        # 恢復體力
        if "stamina_restore" in item:
            self.player.restore_stamina(item["stamina_restore"])
            print(f"  ✨ 恢復了 {item['stamina_restore']} 點體力！")

        # 增加智力
        if "intel_gain" in item:
            self.player.intel += item["intel_gain"]
            print(f"  📖 智力提升了 {item['intel_gain']} 點！")

        # 增加滿足感
        if "satisfaction_gain" in item:
            self.player.change_satisfaction(item["satisfaction_gain"])
            print(f"  🎮 感覺心靈得到了昇華（滿足感提升）！")

        # 賦予狀態效果
        if "status" in item:
            self.player.add_status(item["status"], item["duration"])
