import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import random
import json
import hashlib
import plotly.express as px
import requests  # 🌟 新增：用來發訊息給 Telegram 的套件

st.set_page_config(page_title="VIIYASIY 唯婭心管理系統", page_icon="✨", layout="wide")

# ================= 🌟 Telegram 發報秘書功能 =================
def send_telegram_message(message):
    try:
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        pass # 如果 Telegram 沒設定好或網路斷線，靜默失敗，不要影響正常結帳

# ================= 🌟 狀態初始化與彈出視窗 =================
if "show_success" not in st.session_state:
    st.session_state.show_success = False
if "last_order_id" not in st.session_state:
    st.session_state.last_order_id = ""

@st.dialog("🎉 系統通知")
def order_success_dialog():
    st.success(f"✅ 訂單 **[{st.session_state.last_order_id}]** 已成功送出！")
    st.write("庫存已自動扣除，歷史報表已更新。")
    
    if st.button("關閉視窗", type="primary", use_container_width=True):
        st.session_state.show_success = False
        st.session_state["input_customer"] = ""
        st.session_state["input_channel"] = "IG私訊"
        st.session_state["input_singles"] = []
        st.session_state["input_bundles"] = []
        
        for k in list(st.session_state.keys()):
            if k.startswith("qty_") or k.startswith("bqty_"):
                del st.session_state[k]
        st.rerun()

if st.session_state.show_success:
    order_success_dialog()

# ================= 🔒 系統保全門 =================
def check_password():
    try:
        CORRECT_HASH = st.secrets["APP_PASSWORD_HASH"]
    except Exception:
        CORRECT_HASH = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 VIIYASIY 系統已上鎖")
        st.warning("這是不公開的內部營收管理系統，請輸入專屬密碼解鎖。")
        pwd_input = st.text_input("請輸入管理員密碼", type="password")
        
        if st.button("解鎖登入", type="primary"):
            input_hash = hashlib.sha256(pwd_input.encode()).hexdigest()
            if input_hash == CORRECT_HASH:
                st.session_state["authenticated"] = True
                st.success("解鎖成功！系統載入中...")
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入！")
        st.stop()

check_password()

# ================= 側邊欄：同步按鈕 =================
with st.sidebar:
    st.write("🔧 管理員功能")
    if st.button("🔄 同步最新雲端資料", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ 資料已與 Google 試算表同步！")
        st.rerun()

# ================= 資料庫連線與讀取 =================
@st.cache_resource
def get_gspread():
    try:
        return gspread.service_account(filename=r"C:\Users\Josh\Desktop\z\xx.json")
    except Exception:
        key_dict = json.loads(st.secrets["GCP_KEY"])
        return gspread.service_account_from_dict(key_dict)

try:
    gc = get_gspread()
    sh = gc.open("Stock")
    ws_summary = sh.worksheet("庫存總表")
    ws_log = sh.worksheet("銷售紀錄")
except Exception as e:
    st.error(f"資料庫連線失敗，請檢查金鑰設定：{e}")
    st.stop()

@st.cache_data
def load_all_data():
    df_sum = pd.DataFrame(ws_summary.get_all_records())
    log_records = ws_log.get_all_records()
    if log_records:
        df_l = pd.DataFrame(log_records)
    else:
        df_l = pd.DataFrame(columns=["交易時間", "訂單編號", "產品名稱", "售出數量", "銷售總額", "銷售通路", "客戶", "訂單類型"])
    return df_sum, df_l

df_summary, df_log = load_all_data()

BUNDLE_DEFS = {
    "🌟 明星三件組 ($4,180)": {
        "price": 4180,
        "items": {"PDRN外泌體發光露": 1, "水光肌煥活精華": 1, "修護凝霜": 1}
    },
    "👑 養膚四件組 ($4,580)": {
        "price": 4580,
        "items": {"深層淨卸泡泡慕斯": 1, "PDRN外泌體發光露": 1, "水光肌煥活精華": 1, "修護凝霜": 1}
    }
}

st.title("✨ VIIYASIY 唯婭心 營銷系統")

tab1, tab2, tab3, tab4 = st.tabs(["🛒 快速結帳", "📊 庫存與利潤報表", "🎁 熟客抽獎", "📝 歷史訂單查詢"])

# ----------------- 頁籤 1: 購物車結帳 -----------------
with tab1:
    st.markdown("### 🛍️ VIIYASIY 官方訂購區")
    
    st.markdown("""
    **品牌名稱** ：VIIYASIY 唯婭心  
    **結帳方式** ：信用卡 \ 無卡分期 \ 貨到付款 \ 行動支付 \ 超商付款 \ ATM  
    **配送方式** ：🚚 快速到貨 / 離島配送 / 超商取貨
    """)
    st.divider()
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        customer = st.text_input("客戶名稱 / IG (必填)", placeholder="例如: @amy_123", key="input_customer")
    with col_c2:
        channel = st.selectbox("銷售通路", ["IG私訊", "賣貨便", "蝦皮", "親友/面交"], key="input_channel")
    
    st.divider()
    
    product_list = df_summary['產品名稱'].tolist()
    try:
        selected_singles = st.pills("📦 **選擇單品 (滿3件享95折，可複選)：**", product_list, selection_mode="multi", key="input_singles")
    except AttributeError:
        selected_singles = st.multiselect("📦 **選擇單品 (滿3件享95折，可複選)：**", product_list, key="input_singles")
    
    order_details_singles = []
    total_single_qty = 0
    original_single_total = 0
    
    if selected_singles:
        st.write("👇 請設定數量：")
        for prod in selected_singles:
            unit_price = int(df_summary.loc[df_summary['產品名稱'] == prod, '零售價'].values[0])
            qty = st.number_input(f"{prod} (單價 ${unit_price:,})", min_value=1, value=1, step=1, key=f"qty_{prod}")
            total_single_qty += qty
            original_single_total += unit_price * qty
            order_details_singles.append({"prod": prod, "qty": qty, "price": unit_price})
            
    st.divider()
    
    try:
        selected_bundles = st.pills("🎁 **選擇優惠組合包 (可複選)：**", list(BUNDLE_DEFS.keys()), selection_mode="multi", key="input_bundles")
    except AttributeError:
        selected_bundles = st.multiselect("🎁 **選擇優惠組合包 (可複選)：**", list(BUNDLE_DEFS.keys()), key="input_bundles")
    
    order_details_bundles = []
    total_bundle_price = 0
    if selected_bundles:
        st.write("👇 請設定組合數量：")
        for bundle in selected_bundles:
            b_price = BUNDLE_DEFS[bundle]["price"]
            b_qty = st.number_input(f"{bundle}", min_value=1, value=1, step=1, key=f"bqty_{bundle}")
            total_bundle_price += b_price * b_qty
            order_details_bundles.append({"bundle": bundle, "qty": b_qty, "price": b_price})

    st.divider()
    
    is_discount = False
    final_single_total = 0
    
    if total_single_qty > 0 or total_bundle_price > 0:
        st.subheader("💰 購物車結算")
        if total_single_qty >= 3:
            is_discount = True
            final_single_total = int(round(original_single_total * 0.95))
            st.success(f"✅ 單品共 {total_single_qty} 件，符合【單品 95 折】：**${final_single_total:,}**")
        elif total_single_qty > 0:
            final_single_total = original_single_total
            st.info(f"☑️ 單品共 {total_single_qty} 件 (未達折扣)：**${final_single_total:,}**")
            
        if total_bundle_price > 0:
            st.info(f"☑️ 組合包總額：**${total_bundle_price:,}**")
            
        final_order_total = final_single_total + total_bundle_price
        st.markdown(f"<h2 style='color: #E60044;'>本單應收總額：${final_order_total:,}</h2>", unsafe_allow_html=True)
        
        if st.button("確認送出訂單", type="primary"):
            if not customer:
                st.warning("⚠️ 請記得填寫客戶名稱，否則客人無法累積抽獎資格喔！")
                st.stop()
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order_id = "V-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            rows_to_add = []
            
            # 蒐集購買內容字串給 Telegram
            items_text = []
            
            for item in order_details_singles:
                if is_discount:
                    item_revenue = int(round(item["price"] * item["qty"] * 0.95))
                else:
                    item_revenue = item["price"] * item["qty"]
                rows_to_add.append([now_str, order_id, item["prod"], int(item["qty"]), item_revenue, channel, customer, "單品"])
                items_text.append(f"{item['prod']} x{item['qty']}")
                
            for b_item in order_details_bundles:
                bundle_name = b_item["bundle"]
                b_qty = b_item["qty"]
                b_price_total = b_item["price"] * b_qty
                items = list(BUNDLE_DEFS[bundle_name]["items"].items())
                for idx, (p_name, p_count) in enumerate(items):
                    row_amt = b_price_total if idx == 0 else 0 
                    rows_to_add.append([now_str, order_id, p_name, int(p_count * b_qty), int(row_amt), channel, customer, bundle_name])
                items_text.append(f"📦 {bundle_name} x{b_qty}")
                
            # 寫入資料庫並清除快取
            ws_log.append_rows(rows_to_add)
            st.cache_data.clear()
            
            # ================= 🌟 觸發 Telegram 秘書 =================
            try:
                buy_list_str = " + ".join(items_text)
                tg_msg = f"🎊 **新訂單成立** 🎊\n\n"
                tg_msg += f"👤 客戶：`{customer}`\n"
                tg_msg += f"🛍 內容：{buy_list_str}\n"
                tg_msg += f"💰 總計：**${final_order_total:,}**\n"
                tg_msg += f"🔗 通路：{channel}\n"
                tg_msg += f"🏷 單號：`{order_id}`"
                send_telegram_message(tg_msg)
                
                # 檢查最新庫存 (如果小於等於3件就發送警告)
                df_new_sum, _ = load_all_data()
                low_stock = df_new_sum[df_new_sum['剩餘庫存'] <= 3]
                if not low_stock.empty:
                    alert_msg = "🚨 **低庫存警報** 🚨\n\n"
                    for _, row in low_stock.iterrows():
                        alert_msg += f"⚠️ `{row['產品名稱']}` 僅剩 {row['剩餘庫存']} 件\n"
                    send_telegram_message(alert_msg)
            except Exception:
                pass
            # =========================================================

            st.session_state.last_order_id = order_id
            st.session_state.show_success = True
            st.rerun()
    else:
        st.info("請於上方點擊按鈕選擇要購買的商品。")

# ----------------- 頁籤 2: 庫存與利潤報表 -----------------
with tab2:
    st.subheader("📦 目前庫存狀態")
    display_df = df_summary[['產品名稱', '初始庫存', '累積售出', '剩餘庫存']].copy()
    st.dataframe(display_df, hide_index=True, width="stretch")
    
    st.divider()
    st.subheader("📈 營收與利潤概況")
    if not df_log.empty:
        total_revenue = df_log['銷售總額'].sum()
        df_merged = pd.merge(df_log, df_summary[['產品名稱', '進貨成本']], on='產品名稱', how='left')
        df_merged['單筆成本'] = df_merged['售出數量'] * df_merged['進貨成本']
        total_cost = df_merged['單筆成本'].sum()
        net_profit = total_revenue - total_cost
        
        if '訂單編號' in df_log.columns:
            total_orders = df_log['訂單編號'].nunique()
        else:
            total_orders = df_log['交易時間'].nunique()
            
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("累積總營收", f"${total_revenue:,.0f}")
        col2.metric("已售出總成本", f"${total_cost:,.0f}")
        col3.metric("目前淨利潤", f"${net_profit:,.0f}")
        
        st.write("")
        col4, col5 = st.columns(2)
        col4.metric("總成立訂單數", f"{total_orders} 筆")
        col5.metric("平均客單價", f"${avg_order_value:,.0f}")
        
        st.divider()
        st.subheader("📊 營收數據分析")
        c_chart1, c_chart2 = st.columns(2)
        
        with c_chart1:
            st.markdown("##### 🏆 熱銷商品排行 (數量)")
            df_top_items = df_log.groupby('產品名稱')['售出數量'].sum().reset_index()
            df_top_items = df_top_items.sort_values(by='售出數量', ascending=True)
            fig1 = px.bar(df_top_items, x='售出數量', y='產品名稱', orientation='h', 
                          color='售出數量', color_continuous_scale='Purples')
            fig1.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig1, use_container_width=True)

        with c_chart2:
            st.markdown("##### 💰 各通路營收佔比")
            df_channel = df_log.groupby('銷售通路')['銷售總額'].sum().reset_index()
            fig2 = px.pie(df_channel, names='銷售通路', values='銷售總額', hole=0.4, 
                          color_discrete_sequence=px.colors.sequential.Purples_r)
            fig2.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.write("目前尚無銷售紀錄。")

# ----------------- 頁籤 3: 客戶名單與抽獎 -----------------
with tab3:
    st.subheader("🎉 熟客抽獎系統 (須累積滿 3 筆訂單)")
    if not df_log.empty and '訂單編號' in df_log.columns:
        df_valid = df_log[df_log['客戶名稱/IG'].astype(str).str.strip() != '']
        if not df_valid.empty:
            order_counts = df_valid.groupby('客戶名稱/IG')['訂單編號'].nunique()
            eligible_customers = order_counts[order_counts >= 3].index.tolist()
            
            st.write(f"📊 目前共有 **{len(order_counts)}** 位客戶。")
            st.write(f"🏆 符合抽獎資格： **{len(eligible_customers)}** 位！")
            
            with st.expander("🔍 查看客戶累積訂單數明細"):
                st.dataframe(order_counts.reset_index().rename(columns={"訂單編號": "累積訂單數"}), hide_index=True)
            
            st.divider()
            st.markdown("#### 🎲 幸運大轉盤 (僅限符合資格者)")
            if eligible_customers:
                draw_count = st.number_input("本次要抽出幾位得獎者？", min_value=1, max_value=len(eligible_customers), value=1)
                if st.button("開始隨機抽獎 🎊"):
                    winners = random.sample(eligible_customers, min(draw_count, len(eligible_customers)))
                    st.balloons()
                    st.success(f"🏆 恭喜得獎者： **{', '.join(winners)}** ！！！")
            else:
                st.warning("⚠️ 目前還沒有客戶累積滿 3 筆訂單喔！請多加油宣傳！")
        else:
            st.write("目前尚無有效的客戶紀錄。")
    else:
        st.write("目前尚無銷售紀錄。")

# ----------------- 頁籤 4: 歷史訂單查詢 -----------------
with tab4:
    st.subheader("📝 歷史訂單查詢")
    st.write("💡 系統已自動將資料庫的零碎扣庫紀錄，重組為方便閱讀的完整訂單。")
    
    if not df_log.empty and '訂單編號' in df_log.columns:
        df_valid_orders = df_log[df_log['訂單編號'].astype(str).str.strip() != '']
        if not df_valid_orders.empty:
            orders_display = []
            grouped = df_valid_orders.groupby('訂單編號')
            
            for order_id, group in grouped:
                time_str = group['交易時間'].iloc[0]
                customer_name = group['客戶名稱/IG'].iloc[0]
                channel_name = group['銷售通路'].iloc[0]
                total_order_revenue = group['銷售總額'].sum()
                
                items_str_list = []
                single_items = group[group['訂單類型'] == '單品']
                for _, row in single_items.iterrows():
                    items_str_list.append(f"{row['產品名稱']} x{row['售出數量']}")
                
                bundle_items = group[group['訂單類型'] != '單品']
                if not bundle_items.empty:
                    bundles = bundle_items['訂單類型'].unique()
                    for b_name in bundles:
                        b_rows = bundle_items[bundle_items['訂單類型'] == b_name]
                        b_total = b_rows['銷售總額'].sum()
                        
                        b_price = BUNDLE_DEFS.get(b_name, {}).get('price', 0)
                        if b_price > 0:
                            b_qty = int(b_total / b_price)
                            if b_qty == 0: b_qty = 1
                        else:
                            b_qty = 1
                        items_str_list.append(f"📦 {b_name} x{b_qty}")
                
                orders_display.append({
                    "交易時間": time_str,
                    "客戶": customer_name,
                    "購買內容": " + ".join(items_str_list),
                    "實收總額": f"${total_order_revenue:,}",
                    "通路": channel_name,
                    "訂單編號": order_id
                })
                
            df_display = pd.DataFrame(orders_display)
            df_display = df_display.sort_values(by="交易時間", ascending=False)
            st.dataframe(df_display, hide_index=True, width="stretch")
        else:
            st.info("目前尚無附帶訂單編號的紀錄。")
    else:
        st.info("目前尚無完整銷售紀錄。")
