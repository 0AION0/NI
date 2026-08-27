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

# ================= 0. 保持雲端喚醒 =================
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
    else:
        gc = gspread.service_account(filename=r"C:\Users\Josh\Desktop\z\xx.json")
        
    sh = gc.open("Stock")
    ws_summary = sh.worksheet("庫存總表")
    ws_log = sh.worksheet("銷售紀錄")
    ws_restock = sh.worksheet("進貨紀錄")
    print("✅ 資料庫連線成功！")
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
    bot.send_message(message.chat.id, "🤖 <b>VIIYASIY 系統小秘書已解鎖！</b> 👇", reply_markup=markup, parse_mode="HTML")

def process_password(message):
    chat_id = message.chat.id
    if ACCESS_PASSWORD and message.text.strip() == ACCESS_PASSWORD:
        AUTHORIZED_USERS.add(chat_id)
        bot.reply_to(message, "✅ <b>登入成功！</b>", parse_mode="HTML")
        show_main_menu(message) 
    else:
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 重新嘗試", callback_data="start_login"))
        bot.reply_to(message, "❌ <b>密碼錯誤！</b>", reply_markup=markup, parse_mode="HTML")

# ================= 🛒 系統狀態與智能快取引擎 =================
user_carts = {}
user_checkout_data = {}
user_shop_step = {} 
user_restocks = {}
user_restock_step = {}

global_catalog = []
last_fetch_time = 0

SHIPPING_PRICES = {
    "ship_38": {"name": "📦 賣貨便運費", "price": 38},
    "ship_60": {"name": "📦 店到店運費", "price": 60},
    "ship_100": {"name": "📦 宅配運費", "price": 100}
}
GIFT_ITEMS = ["旅行瓶-沐浴露 60ml", "旅行瓶-髮膜 50ml", "旅行瓶-髮妝水 30ml", "旅行瓶-水光噴霧 30ml"]

def get_cached_catalog():
    global global_catalog, last_fetch_time
    if not global_catalog or time.time() - last_fetch_time > 300:
        global_catalog = ws_summary.get_all_records()
        last_fetch_time = time.time()
    return global_catalog

def force_refresh_cache():
    global last_fetch_time
    last_fetch_time = 0

# ================= 3. 選單與對話攔截 =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message.chat.id):
        bot.reply_to(message, "🛑 <b>系統已鎖定！</b>\n請點擊下方按鈕登入：", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔐 點擊登入", callback_data="start_login")), parse_mode="HTML")
        return
    show_main_menu(message)

@bot.message_handler(func=lambda message: message.text in ["🛍️ 開始購物", "📥 進貨入庫", "📦 查詢庫存", "📈 營收報表", "🎉 幸運抽獎", "🔍 查詢訂單", "❓ 系統說明"])
def handle_menu_buttons(message):
    # 🌟 修復裝死 Bug：如果沒登入，會跳出警告要求登入，而不是已讀不回！
    if not is_authorized(message.chat.id): 
        bot.reply_to(message, "🛑 <b>系統已重新啟動或鎖定！</b>\n請重新進行登入：", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔐 點擊登入", callback_data="start_login")), parse_mode="HTML")
        return
        
    text = message.text
    if text == "🛍️ 開始購物": show_shop(message)
    elif text == "📥 進貨入庫": show_restock(message)
    elif text == "📦 查詢庫存": check_stock(message)
    elif text == "📈 營收報表":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📅 本日", callback_data="report_today"), InlineKeyboardButton("🗓️ 本月", callback_data="report_month"), InlineKeyboardButton("📊 歷史總和", callback_data="report_all"))
        bot.send_message(message.chat.id, "📈 <b>選擇報表期間：</b>", reply_markup=markup, parse_mode="HTML")
    elif text == "🎉 幸運抽獎":
        draw_lottery(message)
    elif text == "🔍 查詢訂單":
        msg = bot.send_message(message.chat.id, "🔍 <b>直接打字輸入「客戶名稱」或「IG 帳號」：</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_search)
    elif text == "❓ 系統說明":
        send_welcome(message)

# ================= 4. 核心功能區 (極速化) =================
def process_order_search(message):
    chat_id = message.chat.id
    if not is_authorized(chat_id): return
    search_name = message.text.strip()
    
    try:
        df_log = pd.DataFrame(ws_log.get_all_records())
        if df_log.empty or '客戶' not in df_log.columns:
            bot.send_message(chat_id, "⚠️ 目前無紀錄。")
            return
            
        matched_df = df_log[df_log['客戶'].astype(str).str.contains(search_name, case=False, na=False)]
        if matched_df.empty:
            bot.send_message(chat_id, f"❌ 找不到與「<b>{search_name}</b>」相關的紀錄。", parse_mode="HTML")
            return
            
        matched_df['銷售總額'] = pd.to_numeric(matched_df['銷售總額'], errors='coerce').fillna(0)
        recent_orders = list(matched_df.groupby('訂單編號'))[-5:] 
        
        bot.send_message(chat_id, f"📋 <b>為您找到「{search_name}」的近期訂單：</b>", parse_mode="HTML")
        for order_id, group in recent_orders:
            reply_text = f"📅 <code>{group['交易時間'].iloc[0]}</code>\n🔖 <b>單號：</b><code>{order_id}</code>\n👤 <b>客戶：</b>{group['客戶'].iloc[0]} ({group['銷售通路'].iloc[0]})\n🛍️ <b>內容：</b>\n"
            for _, row in group.iterrows(): reply_text += f"   ▪️ {row['產品名稱']} x {row['售出數量']}\n"
            reply_text += f"💰 <b>總金額：${group['銷售總額'].sum():,.0f}</b>"
            
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🗑️ 撤銷訂單", callback_data=f"cancel_{order_id}"))
            bot.send_message(chat_id, reply_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(chat_id, f"查詢錯誤：{e}")

def check_stock(message):
    try:
        force_refresh_cache() 
        df_sum = pd.DataFrame(get_cached_catalog())
        reply = "📦 <b>【即時庫存狀態】</b>\n\n"
        for _, row in df_sum.iterrows():
            qty = row.get('剩餘庫存', 0)
            alert = " 🚨(缺貨)" if str(qty).isdigit() and int(qty) <= 3 else ""
            reply += f"▪️ {row.get('產品名稱', '未知')}: <code>{qty}</code> 件{alert}\n"
        bot.reply_to(message, reply, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"查詢失敗：{e}")

def generate_report(chat_id, period, message_id):
    try:
        df_log = pd.DataFrame(ws_log.get_all_records())
        df_sum = pd.DataFrame(get_cached_catalog())
        
        if df_log.empty:
            bot.edit_message_text("⚠️ 無銷售紀錄。", chat_id=chat_id, message_id=message_id)
            return

        if period == "today":
            df_log = df_log[df_log['交易時間'].astype(str).str.startswith(datetime.now().strftime("%Y-%m-%d"))]
            title = "本日"
        elif period == "month":
            df_log = df_log[df_log['交易時間'].astype(str).str.startswith(datetime.now().strftime("%Y-%m"))]
            title = "本月"
        else: title = "歷史總"
            
        if df_log.empty:
            bot.edit_message_text(f"⚠️ <b>{title}</b> 無銷售紀錄。", chat_id=chat_id, message_id=message_id, parse_mode="HTML")
            return

        df_ship = df_log[df_log['產品名稱'].astype(str).str.contains('運費', na=False)]
        total_shipping = pd.to_numeric(df_ship['銷售總額'], errors='coerce').fillna(0).sum()

        df_log = df_log[~df_log['產品名稱'].astype(str).str.contains('運費', na=False)]
        if '訂單類型' in df_log.columns: df_log = df_log[df_log['訂單類型'] != 'TG贈品']

        df_log['銷售總額'] = pd.to_numeric(df_log['銷售總額'], errors='coerce').fillna(0)
        df_log['售出數量'] = pd.to_numeric(df_log['售出數量'], errors='coerce').fillna(0)
        
        total_revenue = df_log['銷售總額'].sum()
        df_merged = pd.merge(df_log, df_sum[['產品名稱', '進貨成本']], on='產品名稱', how='left')
        total_cost = (df_merged['售出數量'] * pd.to_numeric(df_merged['進貨成本'], errors='coerce').fillna(0)).sum()
        
        reply_text = (f"📈 <b>【{title}營收戰情版】</b>\n\n💰 實際商品營收：<code>${total_revenue:,.0f}</code>\n📦 商品出貨成本：<code>${total_cost:,.0f}</code>\n🏆 實際淨利潤：<code>${total_revenue - total_cost:,.0f}</code>\n\n🚚 代收運費：<code>${total_shipping:,.0f}</code>\n\n🔥 <b>【熱銷排行】</b>\n")
        sales_ranking = df_log.groupby('產品名稱')['售出數量'].sum().reset_index().sort_values(by='售出數量', ascending=False)
        medals = ["🥇", "🥈", "🥉"]
        has_sales = False
        
        for i, row in enumerate(sales_ranking[sales_ranking['售出數量'] > 0].itertuples()):
            icon = medals[i] if i < 3 else "▪️"
            reply_text += f"{icon} {row.產品名稱}：<code>{int(row.售出數量)}</code> 件\n"
            has_sales = True
                
        if not has_sales: reply_text += "無紀錄。"
        bot.edit_message_text(reply_text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
    except Exception as e:
        bot.edit_message_text(f"報表失敗：{e}", chat_id=chat_id, message_id=message_id)

def draw_lottery(message):
    markup = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("👤 公平抽獎", callback_data="lottery_fair"),
        InlineKeyboardButton("🎟️ 狂熱抽獎", callback_data="lottery_weighted"),
        InlineKeyboardButton("💰 VIP 滿額", callback_data="lottery_vip")
    )
    bot.reply_to(message, "🎯 <b>請選擇抽獎條件：</b>", reply_markup=markup, parse_mode="HTML")

# ================= 生成器重構 =================
def get_action_content(chat_id, step, action_type):
    mem_dict = user_carts if action_type == 'shop' else user_restocks
    if chat_id not in mem_dict: mem_dict[chat_id] = {}
    markup = InlineKeyboardMarkup()
    
    cb_prefix = "c" if action_type == 'shop' else "r"
    add_prefix = "add_" if action_type == 'shop' else "radd_"
    sub_prefix = "sub_" if action_type == 'shop' else "rsub_"
    
    if step == "main":
        title = "🛍 <b>產品目錄 (1/2)</b>" if action_type == 'shop' else "📥 <b>進貨點交單 (1/2)</b>"
        for row in get_cached_catalog()[:24]:
            p_name = row['產品名稱']
            qty = mem_dict[chat_id].get(p_name, 0)
            markup.row(InlineKeyboardButton(f"🔹 {p_name} (${row['零售價']:,})" if action_type == 'shop' else f"📦 {p_name}", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"{sub_prefix}{p_name}"),
                InlineKeyboardButton(f"✏️ 數量：{qty}", callback_data=f"{cb_prefix}set_{p_name}"),
                InlineKeyboardButton("➕", callback_data=f"{add_prefix}{p_name}")
            )
        markup.row(InlineKeyboardButton("➡️ 下一步 (附加項目)", callback_data=f"{action_type}_addon"))
        markup.row(InlineKeyboardButton("🗑️ 清空清單", callback_data=f"clear_{action_type}"))

    elif step == "addon":
        title = "🛍 <b>附加項目 (2/2)</b>" if action_type == 'shop' else "📥 <b>贈品進貨單 (2/2)</b>"
        for gift in GIFT_ITEMS:
            qty = mem_dict[chat_id].get(f"gift_{gift}", 0)
            markup.row(InlineKeyboardButton(f"🎁 {gift} ($0)", callback_data="ignore"))
            markup.row(
                InlineKeyboardButton("➖", callback_data=f"{sub_prefix}gift_{gift}"),
                InlineKeyboardButton(f"✏️ 數量：{qty}", callback_data=f"{cb_prefix}set_gift_{gift}"),
                InlineKeyboardButton("➕", callback_data=f"{add_prefix}gift_{gift}")
            )
        if action_type == 'shop':
            for s_key, s_info in SHIPPING_PRICES.items():
                qty = mem_dict[chat_id].get(s_key, 0)
                markup.row(InlineKeyboardButton(f"{s_info['name']} (${s_info['price']})", callback_data="ignore"))
                markup.row(
                    InlineKeyboardButton("➖", callback_data=f"{sub_prefix}{s_key}"),
                    InlineKeyboardButton(f"✏️ 數量：{qty}", callback_data=f"{cb_prefix}set_{s_key}"),
                    InlineKeyboardButton("➕", callback_data=f"{add_prefix}{s_key}")
                )
        markup.row(InlineKeyboardButton("🔙 回上一步", callback_data=f"{action_type}_main"))
        markup.row(InlineKeyboardButton("🛒 結帳" if action_type == 'shop' else "✅ 執行進貨", callback_data="view_cart" if action_type == 'shop' else "confirm_restock"))
        
    return f"{title}\n\n👇 <b>請選購/輸入數量 (點 ✏️ 可打字)：</b>", markup

def show_shop(message):
    user_shop_step[message.chat.id] = "main"
    text, markup = get_action_content(message.chat.id, "main", "shop")
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

def show_restock(message):
    user_restock_step[message.chat.id] = "main"
    text, markup = get_action_content(message.chat.id, "main", "restock")
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

# ================= 處理打字輸入 =================
def process_input(message, item_key, menu_msg_id, prompt_msg_id, action_type):
    chat_id = message.chat.id
    if not is_authorized(chat_id): return
    try:
        qty = max(0, int(message.text.strip()))
        mem_dict = user_carts if action_type == 'shop' else user_restocks
        if chat_id not in mem_dict: mem_dict[chat_id] = {}
        
        if qty == 0 and item_key in mem_dict[chat_id]: del mem_dict[chat_id][item_key]
        elif qty > 0: mem_dict[chat_id][item_key] = qty
            
        step = user_shop_step.get(chat_id, "main") if action_type == 'shop' else user_restock_step.get(chat_id, "main")
        _, markup = get_action_content(chat_id, step, action_type)
        
        try: bot.delete_message(chat_id, message.message_id); bot.delete_message(chat_id, prompt_msg_id)
        except: pass
        bot.edit_message_reply_markup(chat_id, menu_msg_id, reply_markup=markup)
    except ValueError:
        bot.send_message(chat_id, "⚠️ 請輸入純數字。")

# ================= 5. 按鈕互動處理區 =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    data = call.data
    if not is_authorized(chat_id) and data != "start_login": return

    if data == "ignore":
        bot.answer_callback_query(call.id)
        return
        
    if data == "start_login":
        msg = bot.send_message(chat_id, "✍️ <b>輸入密碼：</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_password)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("report_"):
        generate_report(chat_id, data.replace("report_", ""), call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cancel_"):
        order_id = data.replace("cancel_", "")
        try:
            bot.answer_callback_query(call.id, "執行撤銷中...") 
            col_b = ws_log.col_values(2) 
            for r in reversed([i+1 for i, val in enumerate(col_b) if val == order_id]):
                ws_log.delete_rows(r)
            force_refresh_cache() 
            bot.edit_message_text(f"✅ <b>單號 {order_id} 已撤銷，庫存已退回！</b>", chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception as e:
            bot.edit_message_text(f"⚠️ 撤銷失敗：{e}", chat_id=chat_id, message_id=call.message.message_id)
        return

    for act in ['shop', 'restock']:
        if data in [f"{act}_main", f"{act}_addon"]:
            if act == 'shop': user_shop_step[chat_id] = data.split("_")[1]
            else: user_restock_step[chat_id] = data.split("_")[1]
            text, markup = get_action_content(chat_id, data.split("_")[1], act)
            bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

    if data.startswith(("add_", "sub_", "radd_", "rsub_")):
        act = 'restock' if data.startswith("r") else 'shop'
        is_add = "add" in data
        p_name = data.split("_", 1)[1]
        
        mem = user_restocks if act == 'restock' else user_carts
        if chat_id not in mem: mem[chat_id] = {}
        
        if is_add: mem[chat_id][p_name] = mem[chat_id].get(p_name, 0) + 1
        else:
            if mem[chat_id].get(p_name, 0) > 0:
                mem[chat_id][p_name] -= 1
                if mem[chat_id][p_name] == 0: del mem[chat_id][p_name]
            else: bot.answer_callback_query(call.id, "已經是 0 囉！", show_alert=True); return
            
        step = user_restock_step.get(chat_id, "main") if act == 'restock' else user_shop_step.get(chat_id, "main")
        _, markup = get_action_content(chat_id, step, act)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    if data.startswith(("cset_", "rset_")):
        act = 'restock' if data.startswith("r") else 'shop'
        item_key = data.split("_", 1)[1]
        disp = SHIPPING_PRICES.get(item_key, {}).get("name", item_key.replace("gift_", ""))
        prompt = bot.send_message(chat_id, f"⌨️ <b>輸入【{disp}】的數量：</b>", parse_mode="HTML")
        bot.register_next_step_handler(prompt, process_input, item_key, call.message.message_id, prompt.message_id, act)
        bot.answer_callback_query(call.id)
        return

    if data in ["clear_cart", "clear_restock"]:
        act = 'shop' if data == "clear_cart" else 'restock'
        if act == 'shop': user_carts[chat_id] = {}
        else: user_restocks[chat_id] = {}
        step = user_shop_step.get(chat_id, "main") if act == 'shop' else user_restock_step.get(chat_id, "main")
        _, markup = get_action_content(chat_id, step, act)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, "🗑️ 清單已清空", show_alert=True)
        return

    if data == "confirm_restock":
        cart = user_restocks.get(chat_id, {})
        if not cart:
            bot.answer_callback_query(call.id, "⚠️ 進貨單是空的喔！", show_alert=True); return
        
        bot.answer_callback_query(call.id, "執行寫入中...") 
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rid = "IN-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            rows = [[now_str, rid, k.replace("gift_", ""), v, "", "TG機器人進貨"] for k, v in cart.items()]
            ws_restock.append_rows(rows, value_input_option="USER_ENTERED")
            user_restocks[chat_id] = {} 
            force_refresh_cache() 
            bot.edit_message_text(f"✅ <b>進貨成功！單號：<code>{rid}</code></b>", chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ 進貨失敗：{e}")
        return

    if data == "view_cart":
        cart = user_carts.get(chat_id, {})
        if not cart:
            bot.answer_callback_query(call.id, "⚠️ 購物車是空的喔！", show_alert=True); return
            
        total = 0
        df_sum = pd.DataFrame(get_cached_catalog())
        msg = "🛒 <b>購物車清單：</b>\n\n"
        for p, qty in cart.items():
            if p in SHIPPING_PRICES: price = SHIPPING_PRICES[p]["price"]; name = SHIPPING_PRICES[p]["name"]
            elif p.startswith("gift_"): price = 0; name = "🎁 " + p.replace("gift_", "")
            else: price = int(df_sum.loc[df_sum['產品名稱'] == p, '零售價'].values[0]); name = p
            total += price * qty
            msg += f"▪️ {name} x {qty}\n"
            
        msg += f"\n💰 <b>總計：${total:,}</b>"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("💳 結帳", callback_data="start_checkout"), InlineKeyboardButton("🗑️ 清空", callback_data="clear_cart"))
        bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return

    if data == "start_checkout":
        msg = bot.send_message(chat_id, "✍️ <b>輸入客戶名稱/IG：</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_customer_name)
        bot.answer_callback_query(call.id)
        return
        
    if data.startswith("channel_"):
        channel = data.replace("channel_", "")
        customer = user_checkout_data.get(chat_id, "未知")
        cart = user_carts.get(chat_id, {})
        if not cart: return
            
        bot.answer_callback_query(call.id, "扣除庫存中...") 
        try:
            df_sum = pd.DataFrame(get_cached_catalog())
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            oid = "V-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            rows, total = [], 0
            
            for p, qty in cart.items():
                if p in SHIPPING_PRICES:
                    price = SHIPPING_PRICES[p]["price"]; name = SHIPPING_PRICES[p]["name"]; o_type = "TG智慧單品"
                elif p.startswith("gift_"):
                    price = 0; name = p.replace("gift_", ""); o_type = "TG贈品"
                else:
                    price = int(df_sum.loc[df_sum['產品名稱'] == p, '零售價'].values[0]); name = p; o_type = "TG智慧單品"
                
                rows.append([now_str, oid, name, qty, price * qty, channel, customer, o_type])
                total += price * qty
                
            ws_log.append_rows(rows, value_input_option="USER_ENTERED")
            user_carts[chat_id] = {} 
            force_refresh_cache() 
            
            df_sum_updated = pd.DataFrame(get_cached_catalog())
            alerts = [f"▪️ 【{r}】剩 {row['剩餘庫存'].values[0]} 件" for r in [k.replace("gift_", "") for k in cart.keys() if k not in SHIPPING_PRICES] if not (row:=df_sum_updated[df_sum_updated['產品名稱']==r]).empty and str(row['剩餘庫存'].values[0]).isdigit() and int(row['剩餘庫存'].values[0]) <= 3]
            alert_text = f"\n\n⚠️ <b>低庫存警報：</b>\n" + "\n".join(alerts) if alerts else ""
            
            bot.edit_message_text(f"🎉 <b>訂單建立成功！</b>\n單號：<code>{oid}</code>\n通路：{channel}\n總計：<b>${total:,}</b>{alert_text}", chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ 錯誤：{e}")

    if data.startswith("lottery_"):
        bot.answer_callback_query(call.id, "抽獎中...")
        try:
            df_log = pd.DataFrame(ws_log.get_all_records())
            if df_log.empty or '客戶' not in df_log.columns: bot.send_message(chat_id, "⚠️ 無效紀錄。"); return
            df_log = df_log[df_log['客戶'].astype(str).str.strip() != ""]
            
            if data == "lottery_fair": cust = df_log['客戶'].unique().tolist()
            elif data == "lottery_weighted": cust = df_log['客戶'].tolist()
            elif data == "lottery_vip":
                df_log['銷售總額'] = pd.to_numeric(df_log['銷售總額'], errors='coerce').fillna(0)
                cust = df_log.groupby('客戶')['銷售總額'].sum().reset_index().query('銷售總額 >= 1000')['客戶'].tolist()

            if not cust: bot.send_message(chat_id, "⚠️ 沒人符合資格！"); return
            bot.send_message(chat_id, f"🎰 <b>抽出幸運兒：</b>\n🏆 <code>{random.choice(cust)}</code>", parse_mode="HTML")
        except Exception as e: bot.send_message(chat_id, f"錯誤：{e}")

def process_customer_name(message):
    chat_id = message.chat.id
    if not is_authorized(chat_id): return
    user_checkout_data[chat_id] = message.text
    markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("📱 IG私訊", callback_data="channel_IG私訊"), InlineKeyboardButton("📦 賣貨便", callback_data="channel_賣貨便"), InlineKeyboardButton("🦐 蝦皮", callback_data="channel_蝦皮"), InlineKeyboardButton("🤝 親友面交", callback_data="channel_親友面交"))
    
    try: bot.delete_message(chat_id, message.message_id); bot.delete_message(chat_id, message.message_id - 1)
    except: pass
    
    bot.send_message(chat_id, f"客戶：<b>{message.text}</b>\n🚚 <b>選擇通路結帳：</b>", reply_markup=markup, parse_mode="HTML")

if __name__ == "__main__":
    print("🤖 雲端版機器人 (修復未登入裝死版) 啟動中...")
    bot.infinity_polling()
