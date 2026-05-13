# ============================================================
#  模組：ui.py — 介面與顯示工具
# ============================================================
# 這個模組負責所有「與玩家互動」的視覺呈現。
# 把 print 和 input 邏輯集中在這裡，可以讓其他系統（如戰鬥、商店）
# 的程式碼保持乾淨，只專注於邏輯運算。
# ============================================================

def display_status(player):
    """
    在螢幕上印出目前角色的所有數值狀態。
    使用了格式化字串 (f-string) 來對齊文字，讓介面看起來更整齊。
    """
    print(f"\n{'#'*50}")
    print(f"  角色：{player.name} ({player.department})")
    print(f"  體力：{player.stamina} / {player.stamina_max}")
    print(f"  智力：{player.intel}  |  運氣：{player.luck}  |  金錢：${player.money}")
    print(f"  滿足感：{player.satisfaction}%")
    
    # 顯示目前擁有的狀態效果
    if player.status_effects:
        effects = ", ".join([f"{k}({v}週)" for k, v in player.status_effects.items()])
        print(f"  當前狀態：[{effects}]")
    else:
        print(f"  當前狀態：[正常]")
    print(f"{'#'*50}")


def display_menu(options, title="請選擇行動"):
    """
    印出一個選單供玩家選擇。
    options: 一個清單，每個元素可以是字串，或是一個帶有 'name' 的字典。
    """
    print(f"\n--- {title} ---")
    for i, opt in enumerate(options, start=1):
        # 判斷是單純的字串還是字典格式
        name = opt["name"] if isinstance(opt, dict) else opt
        desc = f" - {opt['desc']}" if isinstance(opt, dict) and "desc" in opt else ""
        print(f"  {i}. {name}{desc}")
    print("  0. 返回 / 結束")


def get_player_choice(options):
    """
    讀取玩家的輸入，並確保輸入在正確的編號範圍內。
    """
    while True:
        try:
            choice = int(input("\n請輸入編號："))
            if 0 <= choice <= len(options):
                return choice
            else:
                print(f"❌ 請輸入 0 到 {len(options)} 之間的數字。")
        except ValueError:
            print("❌ 輸入錯誤！請輸入數字編號。")
