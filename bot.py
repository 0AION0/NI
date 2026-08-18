import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import gspread
import pandas as pd
from datetime import datetime
import os
import json
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

# ================= 0. 保持雲端喚醒 (Render 專用防斷線機制) =================
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

# 在背景啟動一個虛擬網頁伺服器，讓 Render 覺得我們活著
Thread(target=run_dummy_server, daemon=True).start()

# ================= 1. 系統設定 (支援雲端與本機) =================
# 優先從雲端讀取 Token，如果沒有才用預設的
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(TOKEN)

try:
    # 優先從雲端環境變數讀取 Google 金鑰
    gcp_env = os.environ.get("GCP_KEY_JSON")
    if gcp_env:
        gcp_dict = json.loads(gcp_env)
        gc = gspread.service_account_from_dict(gcp_dict)
        print("✅ 成功使用雲端金鑰連線！")
    else:
        # 如果雲端沒有，就找本機的 xx.json
        gc = gspread.service_account(filename=r"C:\Users\Josh\Desktop\z\xx.json")
        print("✅ 成功使用本機金鑰連線！")
        
    sh = gc.open("Stock")
    ws_summary = sh.worksheet("庫存總表")
    ws_log = sh.worksheet("銷售紀錄")
except Exception as e:
    print(f"❌ 資料庫連線失敗：{e}")

# ================= 🛒 系統狀態記憶體 =================
user_carts = {}
user_checkout_data = {}

# ================= 2. 底部主選單 =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🛍️ 開始購物"), KeyboardButton("📦 查詢庫存"))
    markup.add(KeyboardButton("📈 營收報表"), KeyboardButton("❓ 系統說明"))
    bot.reply_to(message, "🤖 <b>VIIYASIY 系統小秘書已上線！</b>\n請直接點擊下方按鈕開始操作 👇", reply_markup=markup, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text in ["🛍️ 開始購物", "📦 查詢庫存", "📈 營收報表", "❓ 系統說明"])
def handle_menu_buttons(message):
    text = message.text
    if text == "🛍️ 開始購物":
        show_shop(message)
    elif text == "📦 查詢庫存":
        check_stock(message)
    elif text == "📈 營收報表":
        check_report(message)
    elif text == "❓ 系統說明":
        send_welcome(message)

# ================= 3. 核心功能區 =================
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
        total_revenue = df_log['銷售總額'].sum()
        df_merged = pd.merge(df_log, df_sum[['產品名稱', '進貨成本']], on='產品名稱', how='left')
        total_cost = (df_merged['售出數量'] * df_merged['進貨成本']).sum()
        net_profit = total_revenue - total_cost
        
        reply = (f"📈 <b>【營收利潤戰情版】</b>\n\n💰 累積總營收：<code>${total_revenue:,}</code>\n"
                 f"📦 總出貨成本：<code>${total_cost:,}</code>\n🏆 目前淨利潤：<code>${net_profit:,}</code>")
        bot.reply_to(message, reply, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"查詢報表失敗：{e}")

def show_shop(message):
    chat_id = message.chat.id
    if chat_id not in user_carts:
        user_carts[chat_id] = {} 
        
    try:
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        markup = InlineKeyboardMarkup()
        for _, row in df_sum.iterrows():
            prod_name = row['產品名稱']
            price = row['零售價']
            markup.row(
                InlineKeyboardButton(f"➕ 加入 {prod_name} (${price:,})", callback_data=f"add_{prod_name}"),
                InlineKeyboardButton("➖", callback_data=f"sub_{prod_name}")
            )
        markup.row(InlineKeyboardButton("🛒 查看購物車並結帳", callback_data="view_cart"))
        markup.row(InlineKeyboardButton("🗑️ 清空購物車", callback_data="clear_cart"))
        bot.send_message(chat_id, "🛍 <b>VIIYASIY 產品目錄</b>\n請點擊按鈕增減商品：", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, "載入目錄失敗。")

# ================= 4. 按鈕互動處理區 =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    data = call.data
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

# ================= 5. 啟動機器人 =================
if __name__ == "__main__":
    print("🤖 雲端版機器人啟動中...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n機器人已停止運作。")
