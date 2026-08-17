import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import random
import json
import hashlib  # 🌟 新增：Python 內建的加密套件

st.set_page_config(page_title="VIIYASIY 唯婭心管理系統", page_icon="✨", layout="centered")

def check_password():
    # 嘗試從雲端讀取「加密後的密碼」，如果沒設定，就預設使用 "1234" 的加密亂碼
    try:
        CORRECT_HASH = st.secrets["APP_PASSWORD_HASH"]
    except Exception:
        # 這是 "1234" 的 SHA-256 亂碼
        CORRECT_HASH = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 VIIYASIY 系統已上鎖")
        st.warning("這是不公開的內部營收管理系統，請輸入專屬密碼解鎖。")
        pwd_input = st.text_input("請輸入管理員密碼", type="password")
        
        if st.button("解鎖登入", type="primary"):
            # 🌟 核心防護：將使用者輸入的密碼，立刻轉換成加密亂碼，再去比對！
            input_hash = hashlib.sha256(pwd_input.encode()).hexdigest()
            
            if input_hash == CORRECT_HASH:
                st.session_state["authenticated"] = True
                st.success("解鎖成功！系統載入中...")
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入！")
        st.stop()

check_password()

# ================= 以下維持原樣，系統核心不變 =================
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
        df_l = pd.DataFrame(columns=["交易時間", "訂單編號", "產品名稱", "售出數量", "銷售總額", "銷售通路", "客戶名稱/IG", "訂單類型"])
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

tab1, tab2, tab3 = st.tabs(["🛒 購物車結帳", "📊 庫存與利潤報表", "🎁 熟客抽獎 (滿3單)"])

with tab1:
    st.subheader("📝 建立新訂單")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        customer = st.text_input("客戶名稱 / IG (必填)", placeholder="例如: @amy_123")
    with col_c2:
        channel = st.selectbox("銷售通路", ["IG私訊", "賣貨便", "蝦皮", "親友/面交"])
    st.divider()
    
    st.markdown("#### 🛍️ 第一部分：單品自選 (滿3件享95折)")
    product_list = df_summary['產品名稱'].tolist()
    selected_singles = st.multiselect("請選擇單品 (可複選)", product_list)
    
    order_details_singles = []
    total_single_qty = 0
    original_single_total = 0
    
    if selected_singles:
        for prod in selected_singles:
            unit_price = int(df_summary.loc[df_summary['產品名稱'] == prod, '零售價'].values[0])
            qty = st.number_input(f"👉 {prod} (單價 ${unit_price:,})", min_value=1, value=1, step=1, key=f"qty_{prod}")
            total_single_qty += qty
            original_single_total += unit_price * qty
            order_details_singles.append({"prod": prod, "qty": qty, "price": unit_price})
            
    st.divider()
    
    st.markdown("#### 🎁 第二部分：常態優惠組合")
    selected_bundles = st.multiselect("請選擇組合包 (可複選)", list(BUNDLE_DEFS.keys()))
    
    order_details_bundles = []
    total_bundle_price = 0
    if selected_bundles:
        for bundle in selected_bundles:
            b_price = BUNDLE_DEFS[bundle]["price"]
            b_qty = st.number_input(f"👉 {bundle}", min_value=1, value=1, step=1, key=f"bqty_{bundle}")
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
        st.markdown(f"### 🚩 本單應收總額：${final_order_total:,}")
        
        if st.button("確認送出完整訂單", type="primary"):
            if not customer:
                st.warning("⚠️ 請記得填寫客戶名稱，否則客人無法累積抽獎資格喔！")
                st.stop()
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order_id = "V-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            rows_to_add = []
            
            for item in order_details_singles:
                if is_discount:
                    item_revenue = int(round(item["price"] * item["qty"] * 0.95))
                else:
                    item_revenue = item["price"] * item["qty"]
                rows_to_add.append([now_str, order_id, item["prod"], int(item["qty"]), item_revenue, channel, customer, "單品"])
                
            for b_item in order_details_bundles:
                bundle_name = b_item["bundle"]
                b_qty = b_item["qty"]
                b_price_total = b_item["price"] * b_qty
                items = list(BUNDLE_DEFS[bundle_name]["items"].items())
                for idx, (p_name, p_count) in enumerate(items):
                    row_amt = b_price_total if idx == 0 else 0 
                    rows_to_add.append([now_str, order_id, p_name, int(p_count * b_qty), int(row_amt), channel, customer, bundle_name])
                
            ws_log.append_rows(rows_to_add)
            load_all_data.clear()
            st.success(f"✅ 訂單 [{order_id}] 已成功記錄！")
            st.rerun()
    else:
        st.info("請於上方選擇要購買的商品。")

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
    else:
        st.write("目前尚無銷售紀錄。")

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