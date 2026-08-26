import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import gspread
import pandas as pd
from datetime import datetime
import os
import json
import random
import time
from collections import Counter
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

# ================= 0. 保持雲端喚醒 (Render & UptimeRobot 專用) =================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

Thread(target=run_dummy_server, daemon=True).start()

# ================= 1. 系統設定 =================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(TOKEN)

try:
    gcp_env = os.environ.get("GCP_KEY_JSON")
    if gcp_env:
        gcp_dict = json.loads(gcp_env)
        gc = gspread.service_account_from_dict(gcp_dict)
        print("✅ 成功使用雲端金鑰連線！")
    else:
        gc = gspread.service_account(filename=r"C:\Users\Josh\Desktop\z\xx.json")
        print("✅ 成功使用本機金鑰連線！")
        
    sh = gc.open("Stock")
    ws_summary = sh.worksheet("庫存總表")
    ws_log = sh.worksheet("銷售紀錄")
except Exception as e:
    print(f"❌ 資料庫連線失敗：{e}")

# ================= 🔐 2. 門禁安全系統 =================
AUTHORIZED_USERS = set()
ACCESS_PASSWORD = os.environ.get("BOT_PASSWORD") 

def is_authorized(chat_id):
    return chat_id in AUTHORIZED_USERS

def show_main_menu(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🛍️ 開始購物"), KeyboardButton("📦 查詢庫存"))
    markup.add(KeyboardButton("📈 營收報表"), KeyboardButton("🎉 幸運抽獎"))
    markup.add(KeyboardButton("❓ 系統說明"))
    bot.send_message(message.chat.id, "🤖 <b>VIIYASIY 系統小秘書已解鎖！</b>\n請直接點擊下方按鈕開始操作 👇", reply_markup=markup, parse_mode="HTML")

def process_password(message):
    chat_id = message.chat.id
    entered_password = message.text.strip()
    
    if ACCESS_PASSWORD and entered_password == ACCESS_PASSWORD:
        AUTHORIZED_USERS.add(chat_id)
        bot.reply_to(message, "✅ <b>登入成功！身分已確認。</b>", parse_mode="HTML")
        show_main_menu(message) 
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 重新嘗試登入", callback_data="start_login"))
        bot.reply_to(message, "❌ <b>密碼錯誤或系統未設定密碼！</b>\n請確認後再試一次。", reply_markup=markup, parse_mode="HTML")

# ================= 🛒 系統狀態記憶體 =================
user_carts = {}
user_checkout_data = {}

# ================= 3. 選單與對話攔截 =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message.chat.id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔐 點擊輸入密碼登入", callback_data="start_login"))
        bot.reply_to(message, "🛑 <b>系統已鎖定！</b>\n您沒有權限操作此系統，請先登入：", reply_markup=markup, parse_mode="HTML")
        return
    show_main_menu(message)

@bot.message_handler(func=lambda message: message.text in ["🛍️ 開始購物", "📦 查詢庫存", "📈 營收報表", "🎉 幸運抽獎", "❓ 系統說明"])
def handle_menu_buttons(message):
    if not is_authorized(message.chat.id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔐 點擊輸入密碼登入", callback_data="start_login"))
        bot.reply_to(message, "🛑 <b>操作遭拒絕，系統已鎖定！</b>\n請先進行登入：", reply_markup=markup, parse_mode="HTML")
        return
        
    text = message.text
    if text == "🛍️ 開始購物":
        show_shop(message)
    elif text == "📦 查詢庫存":
        check_stock(message)
    elif text == "📈 營收報表":
        check_report(message)
    elif text == "🎉 幸運抽獎":
        draw_lottery(message)
    elif text == "❓ 系統說明":
        send_welcome(message)

# ================= 4. 核心功能區 =================
def check_stock(message):
    try:
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        reply = "📦 <b>【即時庫存狀態】</b>\n\n"
        for _, row in df_sum.iterrows():
            stock_qty = row['剩餘庫存']
            alert = " 🚨(即將缺貨)" if stock_qty <= 3 else ""
            reply += f"▪️ {row['產品名稱']}: <code>{stock_qty}</code> 件{alert}\n"
        bot.reply_to(message, reply, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"查詢失敗：{e}")

def check_report(message):
    try:
        df_log = pd.DataFrame(ws_log.get_all_records())
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        if df_log.empty:
            bot.reply_to(message, "目前還沒有任何銷售紀錄喔！")
            return

        df_log['銷售總額'] = pd.to_numeric(df_log['銷售總額'], errors='coerce').fillna(0)
        df_log['售出數量'] = pd.to_numeric(df_log['售出數量'], errors='coerce').fillna(0)
        
        total_revenue = df_log['銷售總額'].sum()
        df_merged = pd.merge(df_log, df_sum[['產品名稱', '進貨成本']], on='產品名稱', how='left')
        df_merged['進貨成本'] = pd.to_numeric(df_merged['進貨成本'], errors='coerce').fillna(0)
        total_cost = (df_merged['售出數量'] * df_merged['進貨成本']).sum()
        net_profit = total_revenue - total_cost
        
        reply_text = (f"📈 <b>【營收利潤戰情版】</b>\n\n"
                      f"💰 累積總營收：<code>${total_revenue:,.0f}</code>\n"
                      f"📦 總出貨成本：<code>${total_cost:,.0f}</code>\n"
                      f"🏆 目前淨利潤：<code>${net_profit:,.0f}</code>\n\n"
                      f"🔥 <b>【熱銷商品排行 (數量)】</b>\n")

        sales_ranking = df_log.groupby('產品名稱')['售出數量'].sum().reset_index()
        sales_ranking = sales_ranking.sort_values(by='售出數量', ascending=False)

        medals = ["🥇", "🥈", "🥉"]
        rank_idx = 0
        for _, row in sales_ranking.iterrows():
            prod_name = row['產品名稱']
            qty = int(row['售出數量'])
            if qty > 0: 
                icon = medals[rank_idx] if rank_idx < 3 else "▪️"
                reply_text += f"{icon} {prod_name}：<code>{qty}</code> 件\n"
                rank_idx += 1

        bot.reply_to(message, reply_text, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"查詢報表失敗：{e}")

def draw_lottery(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("👤 公平抽獎 (每人一票)", callback_data="lottery_fair"),
        InlineKeyboardButton("🎟️ 狂熱抽獎 (按消費次數提升機率)", callback_data="lottery_weighted"),
        InlineKeyboardButton("💰 VIP 抽獎 (總消費滿 $1000)", callback_data="lottery_vip")
    )
    bot.reply_to(message, "🎯 <b>請選擇這次的抽獎條件：</b>", reply_markup=markup, parse_mode="HTML")

def show_shop(message):
    chat_id = message.chat.id
    if chat_id not in user_carts:
        user_carts[chat_id] = {} 
        
    try:
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        markup = InlineKeyboardMarkup()
        
        # 準備文字菜單
        menu_text = "🛍 <b>VIIYASIY 產品目錄</b>\n\n"
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for idx, row in df_sum.iterrows():
            prod_name = row['產品名稱']
            price = row['零售價']
            
            # 給每個商品一個專屬代號
            icon = emojis[idx] if idx < len(emojis) else f"({idx+1})"
            
            # 把商品名稱和價格印在「對話文字」裡
            menu_text += f"{icon} {prod_name} <code>(${price:,})</code>\n"
            
            # 下方的按鈕只顯示簡短的「加號/減號 + 代號」
            markup.row(
                InlineKeyboardButton(f"➕ 新增 {icon}", callback_data=f"add_{prod_name}"),
                InlineKeyboardButton(f"➖ 減少 {icon}", callback_data=f"sub_{prod_name}")
            )
            
        menu_text += "\n👇 <b>請點擊下方對應的代號按鈕來增減商品：</b>"
            
        markup.row(InlineKeyboardButton("🛒 查看購物車並結帳", callback_data="view_cart"))
        markup.row(InlineKeyboardButton("🗑️ 清空購物車", callback_data="clear_cart"))
        
        bot.send_message(chat_id, menu_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"載入目錄失敗：{e}")

# ================= 5. 按鈕互動處理區 =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if not is_authorized(chat_id) and data != "start_login":
        bot.answer_callback_query(call.id, "🛑 系統已鎖定！請先完成登入程序。", show_alert=True)
        return

    if data == "start_login":
        msg = bot.send_message(chat_id, "✍️ <b>請直接打字輸入您的登入密碼：</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_password)
        bot.answer_callback_query(call.id)
        return

    # 🌟 處理抽獎規則的核心邏輯
    if data.startswith("lottery_"):
        bot.answer_callback_query(call.id)
        try:
            df_log = pd.DataFrame(ws_log.get_all_records())
            if df_log.empty:
                bot.send_message(chat_id, "目前還沒有任何銷售紀錄，無法進行抽獎喔！")
                return
                
            customer_column = '客戶' # 💡 若你的試算表標題不是客戶，請改這裡
            if customer_column not in df_log.columns:
                bot.send_message(chat_id, "⚠️ 試算表中找不到『客戶』欄位，請確認銷售紀錄表的標題。")
                return

            # 過濾掉空白名稱
            df_log = df_log[df_log[customer_column].astype(str).str.strip() != ""]
            
            customers = []
            mode_name = ""

            # 根據按鈕選擇不同的運算規則
            if data == "lottery_fair":
                mode_name = "👤 公平抽獎"
                customers = df_log[customer_column].unique().tolist()
            elif data == "lottery_weighted":
                mode_name = "🎟️ 狂熱抽獎"
                customers = df_log[customer_column].tolist()
            elif data == "lottery_vip":
                mode_name = "💰 VIP 滿額抽獎"
                df_log['銷售總額'] = pd.to_numeric(df_log['銷售總額'], errors='coerce').fillna(0)
                vip_df = df_log.groupby(customer_column)['銷售總額'].sum().reset_index()
                customers = vip_df[vip_df['銷售總額'] >= 1000][customer_column].tolist()

            if not customers:
                bot.send_message(chat_id, f"⚠️ 在【{mode_name}】規則下，沒有找到符合資格的客戶！")
                return

            # 列出參賽名單
            if data == "lottery_weighted":
                ticket_counts = Counter(customers)
                list_text = "、".join([f"{name}({count}票)" for name, count in ticket_counts.items()])
                participant_info = f"共 {len(ticket_counts)} 人參與，總計 {len(customers)} 張籤"
            else:
                list_text = "、".join(customers)
                participant_info = f"共 {len(customers)} 人參與"

            bot.send_message(
                chat_id, 
                f"📋 <b>【{mode_name}】符合資格名單：</b>\n"
                f"({participant_info})\n\n"
                f"<code>{list_text}</code>", 
                parse_mode="HTML"
            )

            time.sleep(1.5)
            bot.send_message(chat_id, f"🎰 <b>系統正在為您抽出幸運兒...</b>", parse_mode="HTML")
            dice_msg = bot.send_dice(chat_id, emoji='🎰')
            time.sleep(3.5)
            
            winner = random.choice(customers)
            
            bot.send_message(
                chat_id, 
                f"🎊 <b>【{mode_name}】結果出爐！</b> 🎊\n\n"
                f"恭喜本次的幸運得主是：\n"
                f"🏆 <code>{winner}</code>\n\n"
                f"趕快去私訊他領獎吧！", 
                reply_to_message_id=dice_msg.message_id,
                parse_mode="HTML"
            )
        except Exception as e:
            bot.send_message(chat_id, f"抽獎發生錯誤：{e}")
        return

    # 🛒 購物車邏輯
    if chat_id not in user_carts:
        user_carts[chat_id] = {}

    if data.startswith("add_"):
        prod_name = data.replace("add_", "")
        user_carts[chat_id][prod_name] = user_carts[chat_id].get(prod_name, 0) + 1
        bot.answer_callback_query(call.id, f"✅ 已加入 1 件【{prod_name}】")

    elif data.startswith("sub_"):
        prod_name = data.replace("sub_", "")
        if user_carts[chat_id].get(prod_name, 0) > 0:
            user_carts[chat_id][prod_name] -= 1
            if user_carts[chat_id][prod_name] == 0:
                del user_carts[chat_id][prod_name]
            bot.answer_callback_query(call.id, f"➖ 已拿出一件【{prod_name}】")
        else:
            bot.answer_callback_query(call.id, f"⚠️ 購物車裡已經沒有【{prod_name}】囉！", show_alert=True)

    elif data == "clear_cart":
        user_carts[chat_id] = {}
        bot.answer_callback_query(call.id, "🗑️ 購物車已全部清空！", show_alert=True)
        bot.send_message(chat_id, "🗑️ 您的購物車已清空，可點選下方選單重新開始。")

    elif data == "view_cart":
        cart = user_carts[chat_id]
        if not cart:
            bot.answer_callback_query(call.id, "⚠️ 購物車目前是空的喔！", show_alert=True)
            return
            
        msg = "🛒 <b>您的購物車清單：</b>\n\n"
        total = 0
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        for p_name, qty in cart.items():
            unit_price = int(df_sum.loc[df_sum['產品名稱'] == p_name, '零售價'].values[0])
            total += unit_price * qty
            msg += f"▪️ {p_name} x {qty}\n"
            
        msg += f"\n💰 <b>應收總計：${total:,}</b>"
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("💳 確認無誤，開始結帳", callback_data="start_checkout"),
            InlineKeyboardButton("🗑️ 放棄結帳並清空", callback_data="clear_cart")
        )
        bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif data == "start_checkout":
        msg = bot.send_message(chat_id, "✍️ <b>結帳第一步：</b>\n請直接打字輸入客人的「名稱或 IG 帳號」(例如：@amy_123)：", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_customer_name)
        bot.answer_callback_query(call.id)
        
    elif data.startswith("channel_"):
        channel = data.replace("channel_", "")
        customer = user_checkout_data.get(chat_id, "未知客戶")
        cart = user_carts.get(chat_id, {})
        if not cart:
            bot.send_message(chat_id, "⚠️ 購物車已失效，請重新下單。")
            return
        try:
            df_sum = pd.DataFrame(ws_summary.get_all_records())
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order_id = "V-BOT-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            order_total_price = 0
            for prod_name, qty in cart.items():
                unit_price = int(df_sum.loc[df_sum['產品名稱'] == prod_name, '零售價'].values[0])
                total_price = unit_price * qty
                order_total_price += total_price
                ws_log.append_rows([[now_str, order_id, prod_name, qty, total_price, channel, customer, "TG智慧單品"]])
                
            user_carts[chat_id] = {} 
            bot.send_message(chat_id, f"🎉 <b>訂單建立成功！</b>\n單號：<code>{order_id}</code>\n客戶：{customer}\n通路：{channel}\n總計：<b>${order_total_price:,}</b>\n✅ 庫存已即時扣除！", parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ 結帳發生錯誤：{e}")

def process_customer_name(message):
    chat_id = message.chat.id
    if not is_authorized(chat_id):
        return
        
    customer_name = message.text
    user_checkout_data[chat_id] = customer_name 
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📱 IG私訊", callback_data="channel_IG私訊"),
        InlineKeyboardButton("📦 賣貨便", callback_data="channel_賣貨便")
    )
    markup.add(
        InlineKeyboardButton("🦐 蝦皮", callback_data="channel_蝦皮"),
        InlineKeyboardButton("🤝 親友/面交", callback_data="channel_親友/面交")
    )
    bot.send_message(chat_id, f"已記錄客戶：<b>{customer_name}</b>\n\n🚚 <b>結帳第二步：</b>\n請點擊選擇銷售通路：", reply_markup=markup, parse_mode="HTML")

# ================= 6. 啟動機器人 =================
if __name__ == "__main__":
    print("🤖 雲端版機器人 (終極代號菜單版) 啟動中...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n機器人已停止運作。")
