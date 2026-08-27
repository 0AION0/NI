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
    ws_restock = sh.worksheet("進貨紀錄") # 🌟 新增綁定進貨紀錄表
except Exception as e:
    print(f"❌ 資料庫連線失敗：{e}")

# ================= 🔐 2. 門禁安全系統 =================
AUTHORIZED_USERS = set()
ACCESS_PASSWORD = os.environ.get("BOT_PASSWORD") 

def is_authorized(chat_id):
    return chat_id in AUTHORIZED_USERS

def show_main_menu(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🛍️ 開始購物"), KeyboardButton("📥 進貨入庫"))
    markup.add(KeyboardButton("📦 查詢庫存"), KeyboardButton("📈 營收報表"))
    markup.add(KeyboardButton("🔍 查詢訂單"), KeyboardButton("🎉 幸運抽獎"))
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

# ================= 🛒 系統狀態記憶體與快取 =================
user_carts = {}
user_checkout_data = {}
user_shop_step = {} 

user_restocks = {} # 🌟 進貨專用記憶體 (與購物車分開)
user_restock_step = {}

global_catalog = []
last_fetch_time = 0

SHIPPING_PRICES = {
    "ship_38": {"name": "📦 賣貨便運費", "price": 38},
    "ship_60": {"name": "📦 店到店運費", "price": 60},
    "ship_100": {"name": "📦 宅配運費", "price": 100}
}

GIFT_ITEMS = [
    "旅行瓶-沐浴露 60ml",
    "旅行瓶-髮膜 50ml",
    "旅行瓶-髮妝水 30ml",
    "旅行瓶-水光噴霧 30ml"
]

def get_cached_catalog():
    global global_catalog, last_fetch_time
    if not global_catalog or time.time() - last_fetch_time > 60:
        global_catalog = ws_summary.get_all_records()
        last_fetch_time = time.time()
    return global_catalog

# ================= 3. 選單與對話攔截 =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message.chat.id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔐 點擊輸入密碼登入", callback_data="start_login"))
        bot.reply_to(message, "🛑 <b>系統已鎖定！</b>\n您沒有權限操作此系統，請先登入：", reply_markup=markup, parse_mode="HTML")
        return
    show_main_menu(message)

@bot.message_handler(func=lambda message: message.text in ["🛍️ 開始購物", "📥 進貨入庫", "📦 查詢庫存", "📈 營收報表", "🎉 幸運抽獎", "🔍 查詢訂單", "❓ 系統說明"])
def handle_menu_buttons(message):
    if not is_authorized(message.chat.id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔐 點擊輸入密碼登入", callback_data="start_login"))
        bot.reply_to(message, "🛑 <b>操作遭拒絕，系統已鎖定！</b>\n請先進行登入：", reply_markup=markup, parse_mode="HTML")
        return
        
    text = message.text
    if text == "🛍️ 開始購物":
        show_shop(message)
    elif text == "📥 進貨入庫":
        show_restock(message) # 🌟 觸發進貨功能
    elif text == "📦 查詢庫存":
        check_stock(message)
    elif text == "📈 營收報表":
        check_report(message)
    elif text == "🎉 幸運抽獎":
        draw_lottery(message)
    elif text == "🔍 查詢訂單":
        msg = bot.send_message(message.chat.id, "🔍 <b>請直接打字輸入要查詢的「客戶名稱」或「IG 帳號」：</b>\n(支援模糊搜尋，例如輸入 amy 即可找到 @amy_123)", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_search)
    elif text == "❓ 系統說明":
        send_welcome(message)

# ================= 4. 核心功能區 =================
def process_order_search(message):
    chat_id = message.chat.id
    if not is_authorized(chat_id): return
    
    search_name = message.text.strip()
    bot.send_message(chat_id, f"🔄 正在資料庫中搜尋包含「<b>{search_name}</b>」的訂單...", parse_mode="HTML")
    
    try:
        df_log = pd.DataFrame(ws_log.get_all_records())
        if df_log.empty:
            bot.send_message(chat_id, "⚠️ 目前沒有任何銷售紀錄。")
            return
            
        customer_col = '客戶'
        if customer_col not in df_log.columns:
            bot.send_message(chat_id, "⚠️ 試算表中找不到『客戶』欄位。")
            return
            
        matched_df = df_log[df_log[customer_col].astype(str).str.contains(search_name, case=False, na=False)]
        
        if matched_df.empty:
            bot.send_message(chat_id, f"❌ 找不到與「<b>{search_name}</b>」相關的歷史訂單紀錄。", parse_mode="HTML")
            return
            
        matched_df['銷售總額'] = pd.to_numeric(matched_df['銷售總額'], errors='coerce').fillna(0)
        
        reply_text = f"📋 <b>為您找到以下關於「{search_name}」的訂單：</b>\n\n"
        grouped = matched_df.groupby('訂單編號')
        
        for order_id, group in grouped:
            date = group['交易時間'].iloc[0]
            channel = group['銷售通路'].iloc[0]
            actual_customer = group[customer_col].iloc[0]
            order_total = group['銷售總額'].sum()
            
            reply_text += f"📅 <code>{date}</code>\n"
            reply_text += f"🔖 <b>單號：</b><code>{order_id}</code>\n"
            reply_text += f"👤 <b>客戶：</b>{actual_customer} ({channel})\n"
            reply_text += f"🛍️ <b>購買內容：</b>\n"
            
            for _, row in group.iterrows():
                prod = row['產品名稱']
                qty = row['售出數量']
                reply_text += f"   ▪️ {prod} x {qty}\n"
                
            reply_text += f"💰 <b>總金額：${order_total:,.0f}</b>\n"
            reply_text += "➖➖➖➖➖➖➖➖\n"
            
        if len(reply_text) > 4000:
            reply_text = reply_text[:4000] + "...\n(資料過多，僅顯示近期紀錄)"
            
        bot.send_message(chat_id, reply_text, parse_mode="HTML")
        
    except Exception as e:
        bot.send_message(chat_id, f"查詢發生錯誤：{e}")

def check_stock(message):
    try:
        df_sum = pd.DataFrame(ws_summary.get_all_records())
        reply = "📦 <b>【即時庫存狀態】</b>\n\n"
        for _, row in df_sum.iterrows():
            stock_qty = row['剩餘庫存']
            alert = " 🚨(缺貨)" if stock_qty <= 3 else ""
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

        df_log = df_log[~df_log['產品名稱'].astype(str).str.contains('運費', na=False)]
        if '訂單類型' in df_log.columns:
            df_log = df_log[df_log['訂單類型'] != 'TG贈品']

        df_log['銷售總額'] = pd.to_numeric(df_log['銷售總額'], errors='coerce').fillna(0)
        df_log['售出數量'] = pd.to_numeric(df_log['售出數量'], errors='coerce').fillna(0)
        
        total_revenue = df_log['銷售總額'].sum()
        df_merged = pd.merge(df_log, df_sum[['產品名稱', '進貨成本']], on='產品名稱', how='left')
        df_merged['進貨成本'] = pd.to_numeric(df_merged['進貨成本'], errors='coerce').fillna(0)
        total_cost = (df_merged['售出數量'] * df_merged['進貨成本']).sum()
        net_profit = total_revenue - total_cost
        
        reply_text = (f"📈 <b>【純淨商品營收戰情版】</b>\n\n"
                      f"💰 實際商品營收：<code>${total_revenue:,.0f}</code>\n"
                      f"📦 商品出貨成本：<code>${total_cost:,.0f}</code>\n"
                      f"🏆 實際淨利潤：<code>${net_profit:,.0f}</code>\n\n"
                      f"🔥 <b>【熱銷商品排行 (已排除贈品)】</b>\n")

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
        InlineKeyboardButton("🎟️ 狂熱抽獎 (按消費次數)", callback_data="lottery_weighted"),
        InlineKeyboardButton("💰 VIP 抽獎 (消費滿 $1000)", callback_data="lottery_vip")
    )
    bot.reply_to(message, "🎯 <b>請選擇這次的抽獎條件：</b>", reply_markup=markup, parse_mode="HTML")

# 🌟 進貨專用生成器
def get_restock_content(chat_id, step="main"):
    if chat_id not in user_restocks:
        user_restocks[chat_id] = {}
        
    markup = InlineKeyboardMarkup()
    
    if step == "main":
        menu_text = "📥 <b>VIIYASIY 進貨點交單 (1/2)</b>\n\n👇 <b>請輸入廠商送達的常規商品數量：</b>"
        records = get_cached_catalog()[:24] 
        
        for row in records:
            prod_name = row['產品名稱']
            qty = user_restocks[chat_id].get(prod_name, 0)
            
            markup.row(InlineKeyboardButton(f"📦 {prod_name}", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"rsub_{prod_name}"),
                InlineKeyboardButton(f"進貨數量：{qty}", callback_data="ignore"),
                InlineKeyboardButton("➕", callback_data=f"radd_{prod_name}")
            )
            
        markup.row(InlineKeyboardButton("➡️ 下一步 (贈品進貨) ➡️", callback_data="restock_addon"))
        markup.row(InlineKeyboardButton("🗑️ 清空進貨單", callback_data="clear_restock"))

    elif step == "addon":
        menu_text = "📥 <b>VIIYASIY 贈品進貨單 (2/2)</b>\n\n👇 <b>請輸入廠商送達的贈品數量：</b>"
        
        for gift_name in GIFT_ITEMS:
            gift_key = f"gift_{gift_name}"
            qty = user_restocks[chat_id].get(gift_key, 0)
            
            markup.row(InlineKeyboardButton(f"🎁 {gift_name}", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"rsub_{gift_key}"),
                InlineKeyboardButton(f"進貨數量：{qty}", callback_data="ignore"),
                InlineKeyboardButton("➕", callback_data=f"radd_{gift_key}")
            )
            
        markup.row(InlineKeyboardButton("🔙 回上一步 (常規商品)", callback_data="restock_main"))
        markup.row(InlineKeyboardButton("✅ 確認數量無誤，執行進貨", callback_data="confirm_restock"))
        
    return menu_text, markup

def show_restock(message):
    chat_id = message.chat.id
    try:
        user_restock_step[chat_id] = "main"
        menu_text, markup = get_restock_content(chat_id, "main")
        bot.send_message(chat_id, menu_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"載入進貨單失敗：{e}")

# 🌟 購物車生成器
def get_shop_content(chat_id, step="main"):
    if chat_id not in user_carts:
        user_carts[chat_id] = {}
        
    markup = InlineKeyboardMarkup()
    
    if step == "main":
        menu_text = "🛍 <b>VIIYASIY 產品目錄 (1/2)</b>\n\n👇 <b>請選購常規商品：</b>"
        records = get_cached_catalog()[:24] 
        
        for row in records:
            prod_name = row['產品名稱']
            price = row['零售價']
            qty = user_carts[chat_id].get(prod_name, 0)
            
            markup.row(InlineKeyboardButton(f"🔹 {prod_name} (${price:,})", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"sub_{prod_name}"),
                InlineKeyboardButton(f"數量：{qty}", callback_data="ignore"),
                InlineKeyboardButton("➕", callback_data=f"add_{prod_name}")
            )
            
        markup.row(InlineKeyboardButton("➡️ 下一步 (選擇贈品與運費) ➡️", callback_data="shop_addon"))
        markup.row(InlineKeyboardButton("🗑️ 清空購物車", callback_data="clear_cart"))

    elif step == "addon":
        menu_text = "🛍 <b>VIIYASIY 附加項目 (2/2)</b>\n\n👇 <b>請選擇贈品與運費：</b>"
        
        markup.row(InlineKeyboardButton("─── 🎁 贈品選項 (扣庫存/0元) ───", callback_data="ignore"))
        for gift_name in GIFT_ITEMS:
            gift_key = f"gift_{gift_name}"
            qty = user_carts[chat_id].get(gift_key, 0)
            
            markup.row(InlineKeyboardButton(f"🎁 贈品：{gift_name} ($0)", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"sub_{gift_key}"),
                InlineKeyboardButton(f"數量：{qty}", callback_data="ignore"),
                InlineKeyboardButton("➕", callback_data=f"add_{gift_key}")
            )
            
        markup.row(InlineKeyboardButton("─── 🚚 附加運費選項 ───", callback_data="ignore"))
        for ship_key, ship_info in SHIPPING_PRICES.items():
            ship_name = ship_info["name"]
            ship_price = ship_info["price"]
            qty = user_carts[chat_id].get(ship_key, 0)
            
            markup.row(InlineKeyboardButton(f"{ship_name} (${ship_price})", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"sub_{ship_key}"),
                InlineKeyboardButton(f"數量：{qty}", callback_data="ignore"),
                InlineKeyboardButton("➕", callback_data=f"add_{ship_key}")
            )
            
        markup.row(InlineKeyboardButton("🔙 回上一步 (常規商品)", callback_data="shop_main"))
        markup.row(InlineKeyboardButton("🛒 查看購物車並結帳", callback_data="view_cart"))
        
    return menu_text, markup

def show_shop(message):
    chat_id = message.chat.id
    try:
        user_shop_step[chat_id] = "main"
        menu_text, markup = get_shop_content(chat_id, "main")
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
        
    if data == "ignore":
        bot.answer_callback_query(call.id)
        return

    # 🌟 處理進貨單的頁面切換
    if data == "restock_addon":
        user_restock_step[chat_id] = "addon"
        menu_text, markup = get_restock_content(chat_id, "addon")
        bot.edit_message_text(text=menu_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
        
    if data == "restock_main":
        user_restock_step[chat_id] = "main"
        menu_text, markup = get_restock_content(chat_id, "main")
        bot.edit_message_text(text=menu_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return

    # 🌟 處理購物車的頁面切換
    if data == "shop_addon":
        user_shop_step[chat_id] = "addon"
        menu_text, markup = get_shop_content(chat_id, "addon")
        bot.edit_message_text(text=menu_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
        
    if data == "shop_main":
        user_shop_step[chat_id] = "main"
        menu_text, markup = get_shop_content(chat_id, "main")
        bot.edit_message_text(text=menu_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return

    # 🌟 進貨單：加減數量與確認
    if data.startswith("radd_"):
        prod_name = data.replace("radd_", "")
        if chat_id not in user_restocks: user_restocks[chat_id] = {}
        user_restocks[chat_id][prod_name] = user_restocks[chat_id].get(prod_name, 0) + 1
        bot.answer_callback_query(call.id) 
        
        current_step = user_restock_step.get(chat_id, "main")
        _, markup = get_restock_content(chat_id, current_step)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("rsub_"):
        prod_name = data.replace("rsub_", "")
        if chat_id in user_restocks and user_restocks[chat_id].get(prod_name, 0) > 0:
            user_restocks[chat_id][prod_name] -= 1
            if user_restocks[chat_id][prod_name] == 0: del user_restocks[chat_id][prod_name]
            bot.answer_callback_query(call.id)
            
            current_step = user_restock_step.get(chat_id, "main")
            _, markup = get_restock_content(chat_id, current_step)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "⚠️ 進貨數量已經是 0 囉！", show_alert=True)
        return

    if data == "clear_restock":
        user_restocks[chat_id] = {}
        bot.answer_callback_query(call.id, "🗑️ 進貨單已全部清空！", show_alert=True)
        current_step = user_restock_step.get(chat_id, "main")
        _, markup = get_restock_content(chat_id, current_step)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        return

    if data == "confirm_restock":
        cart = user_restocks.get(chat_id, {})
        if not cart:
            bot.answer_callback_query(call.id, "⚠️ 進貨單目前是空的喔！沒有選任何商品。", show_alert=True)
            return
            
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            restock_id = "IN-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            rows_to_append = []
            
            for p_key, qty in cart.items():
                prod_name = p_key.replace("gift_", "") if p_key.startswith("gift_") else p_key
                # 寫入格式：A時間, B單號, C產品名稱, D數量, E成本(空), F備註
                rows_to_append.append([now_str, restock_id, prod_name, qty, "", "TG機器人進貨"])
                
            ws_restock.append_rows(rows_to_append)
            user_restocks[chat_id] = {} # 清空進貨單
            bot.send_message(chat_id, f"✅ <b>進貨登錄成功！</b>\n進貨單號：<code>{restock_id}</code>\n共寫入 {len(rows_to_append)} 筆資料，庫存總表已自動更新！", parse_mode="HTML")
            bot.answer_callback_query(call.id)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ 進貨寫入失敗：{e}")
        return

    # 🛒 購物車：加減數量
    if data.startswith("add_"):
        prod_name = data.replace("add_", "")
        if chat_id not in user_carts: user_carts[chat_id] = {}
        user_carts[chat_id][prod_name] = user_carts[chat_id].get(prod_name, 0) + 1
        bot.answer_callback_query(call.id) 
        
        current_step = user_shop_step.get(chat_id, "main")
        _, markup = get_shop_content(chat_id, current_step)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("sub_"):
        prod_name = data.replace("sub_", "")
        if chat_id in user_carts and user_carts[chat_id].get(prod_name, 0) > 0:
            user_carts[chat_id][prod_name] -= 1
            if user_carts[chat_id][prod_name] == 0: del user_carts[chat_id][prod_name]
            bot.answer_callback_query(call.id)
            
            current_step = user_shop_step.get(chat_id, "main")
            _, markup = get_shop_content(chat_id, current_step)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "⚠️ 數量已經是 0 囉！", show_alert=True)
        return

    if data.startswith("lottery_"):
        bot.answer_callback_query(call.id)
        try:
            df_log = pd.DataFrame(ws_log.get_all_records())
            if df_log.empty:
                bot.send_message(chat_id, "目前還沒有任何銷售紀錄，無法進行抽獎喔！")
                return
                
            customer_column = '客戶'
            if customer_column not in df_log.columns:
                bot.send_message(chat_id, "⚠️ 試算表中找不到『客戶』欄位，請確認銷售紀錄表的標題。")
                return

            df_log = df_log[df_log[customer_column].astype(str).str.strip() != ""]
            customers = []
            mode_name = ""

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

            if data == "lottery_weighted":
                ticket_counts = Counter(customers)
                list_text = "、".join([f"{name}({count}票)" for name, count in ticket_counts.items()])
                participant_info = f"共 {len(ticket_counts)} 人參與，總計 {len(customers)} 張籤"
            else:
                list_text = "、".join(customers)
                participant_info = f"共 {len(customers)} 人參與"

            bot.send_message(chat_id, f"📋 <b>【{mode_name}】符合資格名單：</b>\n({participant_info})\n\n<code>{list_text}</code>", parse_mode="HTML")
            time.sleep(1.5)
            bot.send_message(chat_id, f"🎰 <b>系統正在為您抽出幸運兒...</b>", parse_mode="HTML")
            dice_msg = bot.send_dice(chat_id, emoji='🎰')
            time.sleep(3.5)
            
            winner = random.choice(customers)
            bot.send_message(chat_id, f"🎊 <b>【{mode_name}】結果出爐！</b> 🎊\n\n恭喜幸運得主：\n🏆 <code>{winner}</code>\n\n趕快去私訊領獎吧！", reply_to_message_id=dice_msg.message_id, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"抽獎發生錯誤：{e}")
        return

    if data == "clear_cart":
        user_carts[chat_id] = {}
        bot.answer_callback_query(call.id, "🗑️ 購物車已全部清空！", show_alert=True)
        current_step = user_shop_step.get(chat_id, "main")
        _, markup = get_shop_content(chat_id, current_step)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)

    elif data == "view_cart":
        cart = user_carts.get(chat_id, {})
        if not cart:
            bot.answer_callback_query(call.id, "⚠️ 購物車目前是空的喔！", show_alert=True)
            return
            
        msg = "🛒 <b>您的購物車清單：</b>\n\n"
        total = 0
        df_sum = pd.DataFrame(get_cached_catalog())
        
        for p_key, qty in cart.items():
            if p_key in SHIPPING_PRICES:
                p_name = SHIPPING_PRICES[p_key]["name"]
                unit_price = SHIPPING_PRICES[p_key]["price"]
            elif p_key.startswith("gift_"):
                p_name = "🎁 " + p_key.replace("gift_", "")
                unit_price = 0
            else:
                p_name = p_key
                unit_price = int(df_sum.loc[df_sum['產品名稱'] == p_key, '零售價'].values[0])
                
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
            df_sum = pd.DataFrame(get_cached_catalog())
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order_id = "V-BOT-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            order_total_price = 0
            
            for p_key, qty in cart.items():
                order_type = "TG智慧單品" 
                if p_key in SHIPPING_PRICES:
                    prod_name = SHIPPING_PRICES[p_key]["name"]
                    unit_price = SHIPPING_PRICES[p_key]["price"]
                elif p_key.startswith("gift_"):
                    prod_name = p_key.replace("gift_", "") 
                    unit_price = 0
                    order_type = "TG贈品" 
                else:
                    prod_name = p_key
                    unit_price = int(df_sum.loc[df_sum['產品名稱'] == p_key, '零售價'].values[0])
                    
                total_price = unit_price * qty
                order_total_price += total_price
                ws_log.append_rows([[now_str, order_id, prod_name, qty, total_price, channel, customer, order_type]])
                
            user_carts[chat_id] = {} 
            bot.send_message(chat_id, f"🎉 <b>訂單建立成功！</b>\n單號：<code>{order_id}</code>\n客戶：{customer}\n通路：{channel}\n總計：<b>${order_total_price:,}</b>\n✅ 紀錄與庫存已同步至資料庫！", parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ 結帳發生錯誤：{e}")

def process_customer_name(message):
    chat_id = message.chat.id
    if not is_authorized(chat_id): return
    customer_name = message.text
    user_checkout_data[chat_id] = customer_name 
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📱 IG私訊", callback_data="channel_IG私訊"),
        InlineKeyboardButton("📦 賣貨便", callback_data="channel_賣貨便"),
        InlineKeyboardButton("🦐 蝦皮", callback_data="channel_蝦皮"),
        InlineKeyboardButton("🤝 親友/面交", callback_data="channel_親友/面交")
    )
    bot.send_message(chat_id, f"已記錄客戶：<b>{customer_name}</b>\n\n🚚 <b>結帳第二步：</b>\n請點擊選擇銷售通路：", reply_markup=markup, parse_mode="HTML")

if __name__ == "__main__":
    print("🤖 雲端版機器人 (手機一鍵進貨版) 啟動中...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n機器人已停止運作。")
