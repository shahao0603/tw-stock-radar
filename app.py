import streamlit as st
import pandas as pd
import numpy as np
import requests
import datetime
import io
import os
import time

st.set_page_config(page_title="台股策略選股雷達 - 旗艦版", layout="wide")

st.title("🎯 台股自訂策略選股雷達 (旗艦多策略版)")
st.caption("涵蓋三大核心技術面、投信籌碼面、共振指標與波段出場避險訊號 ｜ 全樣本滾動回測 ｜ 產業族群分類")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)

# ----------------- 官方產業代碼對照表 -----------------
TWSE_INDUSTRY_CODES = {
    "01": "水泥工業", "1": "水泥工業", "02": "食品工業", "2": "食品工業",
    "03": "塑膠工業", "3": "塑膠工業", "04": "紡織纖維", "4": "紡織纖維",
    "05": "電機機械", "5": "電機機械", "06": "電器電纜", "6": "電器電纜",
    "07": "化學生技醫療", "7": "化學生技醫療", "08": "玻璃陶瓷", "8": "玻璃陶瓷",
    "09": "造紙工業", "9": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業",
    "12": "汽車工業", "13": "電子工業", "14": "建材營造業", "15": "航運業",
    "16": "觀光餐旅業", "17": "金融保險業", "18": "貿易百貨業", "19": "綜合",
    "20": "其他業", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
    "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
    "32": "綠能環保業", "33": "數位雲端業", "34": "運動休閒業", "35": "居家生活業"
}

PREFIX_FALLBACK = {
    "11": "水泥工業", "12": "食品工業", "13": "塑膠工業", "14": "紡織纖維",
    "15": "電機機械", "16": "電器電纜", "17": "化學工業", "18": "玻璃陶瓷",
    "19": "造紙工業", "20": "鋼鐵工業", "21": "橡膠工業", "22": "汽車工業",
    "23": "半導體業", "24": "半導體業", "25": "建材營造業", "26": "航運業",
    "27": "觀光餐旅業", "28": "金融保險業", "29": "貿易百貨業", "30": "電腦及週邊設備業",
    "31": "電子零組件業", "32": "資訊服務業", "33": "電子零組件業", "34": "光電業",
    "35": "光電業", "36": "電子零組件業", "41": "生技醫療業", "47": "化學工業",
    "49": "通信網路業", "52": "半導體業", "53": "電子通路業", "54": "通信網路業",
    "55": "建材營造業", "61": "電子零組件業", "62": "電子零組件業", "64": "半導體業",
    "65": "生技醫療業", "66": "綠能環保業", "67": "生技醫療業", "68": "綠能環保業",
    "80": "半導體業", "81": "半導體業", "82": "數位雲端業", "83": "綠能環保業",
    "84": "運動休閒業", "89": "其他電子業", "99": "其他業"
}

@st.cache_data(ttl=86400 * 30)
def get_industry_mapping():
    cache_path = os.path.join(CACHE_DIR, "stock_industries_resolved.csv")
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={"code": str, "industry": str})
            return df.set_index("code")["industry"].to_dict()
        except Exception:
            pass

    ind_dict = {}
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            for item in r.json():
                c = str(item.get("公司代號", "")).strip()
                raw_ind = str(item.get("產業別", "")).strip()
                ind_dict[c] = TWSE_INDUSTRY_CODES.get(raw_ind, raw_ind)
    except Exception:
        pass

    try:
        r = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            for item in r.json():
                c = str(item.get("SecuritiesCompanyCode", "")).strip()
                raw_ind = str(item.get("Industry", "")).strip()
                ind_dict[c] = TWSE_INDUSTRY_CODES.get(raw_ind, raw_ind)
    except Exception:
        pass

    if ind_dict:
        pd.DataFrame(list(ind_dict.items()), columns=["code", "industry"]).to_csv(cache_path, index=False)
    return ind_dict

INDUSTRY_MAP = get_industry_mapping()

def get_stock_industry(code):
    c = str(code).strip()
    val = str(INDUSTRY_MAP.get(c, "")).strip()
    if val in TWSE_INDUSTRY_CODES:
        return TWSE_INDUSTRY_CODES[val]
    if val and val not in ["None", "nan", ""] and not val.isdigit():
        return val
    return PREFIX_FALLBACK.get(c[:2], "其他電子業")

def is_valid_target(code, name):
    c = str(code).strip()
    n = str(name).strip()
    if c.startswith("00"):
        if "主動" in n or (len(c) == 5 and c[-1].isalpha()):
            return True
        return False
    return len(c) >= 4

def calc_rr_targets(price, stop_loss_pct):
    sl = round(price * (1 - stop_loss_pct / 100), 2)
    tp_1_3 = round(price * (1 + (stop_loss_pct * 3) / 100), 2)
    tp_1_5 = round(price * (1 + (stop_loss_pct * 5) / 100), 2)
    return sl, tp_1_3, tp_1_5

# ----------------- 官方數據爬蟲 (硬碟快取保護) -----------------
def fetch_twse_day(date_str):
    cache_path = os.path.join(CACHE_DIR, f"twse_{date_str}.csv")
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={"code": str, "date": str})
            df["date"] = df["date"].astype(str)
            return df
        except Exception:
            pass
        
    url_p = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={date_str}&type=ALLBUT0999"
    try:
        res_p = requests.get(url_p, headers=HEADERS, timeout=8)
        lines = [line for line in res_p.text.split("\n") if len(line.split('",')) > 10]
        if not lines:
            return pd.DataFrame()
        df_p = pd.read_csv(io.StringIO("\n".join(lines)))
        df_p.columns = [c.replace('"', '').strip() for c in df_p.columns]
        df_p = df_p[["證券代號", "證券名稱", "成交股數", "收盤價"]].copy()
        df_p.columns = ["code", "name", "volume", "close"]
    except Exception:
        return pd.DataFrame()

    url_f = f"https://www.twse.com.tw/fund/T86?response=csv&date={date_str}&selectType=ALLBUT0999"
    df_f = pd.DataFrame()
    try:
        res_f = requests.get(url_f, headers=HEADERS, timeout=8)
        lines_f = [line for line in res_f.text.split("\n") if len(line.split('",')) > 5]
        if lines_f:
            df_f = pd.read_csv(io.StringIO("\n".join(lines_f)))
            df_f.columns = [c.replace('"', '').strip() for c in df_f.columns]
            sitc_cols = [c for c in df_f.columns if "投信" in c and "買賣超" in c]
            if sitc_cols:
                df_f = df_f[["證券代號", sitc_cols[0]]].copy()
                df_f.columns = ["code", "sitc_buy"]
    except Exception:
        pass

    if not df_f.empty:
        df = pd.merge(df_p, df_f, on="code", how="left")
    else:
        df = df_p.copy()
        df["sitc_buy"] = 0

    for col in ["volume", "close", "sitc_buy"]:
        df[col] = df[col].astype(str).str.replace('"', '').str.replace(',', '').str.replace('--', '').str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df[df["close"] > 0]
    df["code"] = df["code"].astype(str).str.replace('=', '').str.replace('"', '').str.strip()
    
    valid_mask = [is_valid_target(c, n) for c, n in zip(df["code"], df["name"])]
    df = df[valid_mask].copy()

    df["volume"] = df["volume"] // 1000
    df["sitc_buy"] = df["sitc_buy"] // 1000
    df["date"] = str(date_str)
    
    if not df.empty:
        df.to_csv(cache_path, index=False)
    return df

def fetch_tpex_day(date_str):
    cache_path = os.path.join(CACHE_DIR, f"tpex_{date_str}.csv")
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={"code": str, "date": str})
            df["date"] = df["date"].astype(str)
            return df
        except Exception:
            pass
        
    year = int(date_str[:4]) - 1911
    roc_date = f"{year}/{date_str[4:6]}/{date_str[6:]}"
    
    url_p = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_download.php?l=zh-tw&d={roc_date}&s=0,asc,0"
    try:
        res = requests.get(url_p, headers=HEADERS, timeout=8)
        lines = [line for line in res.text.split("\n") if len(line.split(",")) > 10]
        if not lines:
            return pd.DataFrame()
        df = pd.read_csv(io.StringIO("\n".join(lines)))
        df.columns = [c.strip() for c in df.columns]
        df = df[["證券代號", "名稱", "成交股數", "收盤"]].copy()
        df.columns = ["code", "name", "volume", "close"]
    except Exception:
        return pd.DataFrame()

    url_f = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_download.php?l=zh-tw&se=EW&t=D&d={roc_date}&s=0,asc"
    try:
        res_f = requests.get(url_f, headers=HEADERS, timeout=8)
        lines_f = [line for line in res_f.text.split("\n") if len(line.split(",")) > 10]
        if lines_f:
            df_f = pd.read_csv(io.StringIO("\n".join(lines_f)))
            df_f.columns = [c.strip() for c in df_f.columns]
            sitc_col = [c for c in df_f.columns if "投信" in c and "買賣超" in c]
            if sitc_col:
                df_f = df_f[["證券代號", sitc_col[0]]].copy()
                df_f.columns = ["code", "sitc_buy"]
                df = pd.merge(df, df_f, on="code", how="left")
            else:
                df["sitc_buy"] = 0
        else:
            df["sitc_buy"] = 0
    except Exception:
        df["sitc_buy"] = 0

    for col in ["volume", "close", "sitc_buy"]:
        df[col] = df[col].astype(str).str.replace(",", "").str.replace("---", "").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df[df["close"] > 0]
    df["code"] = df["code"].astype(str).strip()
    
    valid_mask = [is_valid_target(c, n) for c, n in zip(df["code"], df["name"])]
    df = df[valid_mask].copy()

    df["volume"] = df["volume"] // 1000
    df["sitc_buy"] = df["sitc_buy"] // 1000
    df["date"] = str(date_str)
    
    if not df.empty:
        df.to_csv(cache_path, index=False)
    return df

def get_market_history(target_date, days_needed=50):
    all_dfs = []
    cur = target_date
    count = 0
    attempts = 0
    progress_box = st.status(f"正在載入歷史資料 (目標 {days_needed} 交易日)...", expanded=True)
    
    max_lookback = days_needed * 3 + 30
    while count < days_needed and attempts < max_lookback:
        attempts += 1
        if cur.weekday() < 5:
            d_s = cur.strftime("%Y%m%d")
            cached = os.path.exists(os.path.join(CACHE_DIR, f"twse_{d_s}.csv"))
            if not cached:
                progress_box.write(f"正在下載 {d_s} 盤後數據...")
            tw = fetch_twse_day(d_s)
            tp = fetch_tpex_day(d_s)
            
            if not tw.empty or not tp.empty:
                combined = pd.concat([tw, tp], ignore_index=True)
                all_dfs.append(combined)
                count += 1
                if not cached:
                    time.sleep(0.15)
        cur -= datetime.timedelta(days=1)
        
    if count < 20:
        progress_box.update(label=f"天數不足：僅取得 {count} 天", state="error")
        return pd.DataFrame()
    else:
        progress_box.update(label=f"歷史資料就緒！(成功載入 {count} 個交易日)", state="complete")
        total_df = pd.concat(all_dfs, ignore_index=True)
        total_df["date"] = total_df["date"].astype(str)
        return total_df

# ----------------- 報酬率區間分類 (每 10% 為一單位) -----------------
def get_return_tier(ret):
    if ret >= 30:
        return "🔥 > +30%"
    elif ret >= 20:
        return "🚀 +20% ~ +30%"
    elif ret >= 10:
        return "🟢 +10% ~ +20%"
    elif ret >= 0:
        return "🌱 0% ~ +10%"
    elif ret >= -10:
        return "🔻 -10% ~ 0%"
    else:
        return "💀 < -10%"

def render_backtest_with_filters(target_df, title_prefix, is_backtest):
    if target_df.empty:
        st.info(f"回測區間內無符合 {title_prefix} 的訊號。")
        return
        
    target_df["產業別"] = target_df["代號"].apply(get_stock_industry)
    
    if is_backtest:
        st.markdown(f"### 📊 {title_prefix} - 全樣本滾動回測 (共觸發 {len(target_df)} 筆訊號)")
        
        # 持有期整體統計
        stats = []
        for d in range(1, 6):
            col = f"+{d}日報酬(%)"
            wins = (target_df[col] > 0).sum()
            w_rate = (wins / len(target_df)) * 100
            avg_r = target_df[col].mean()
            stats.append({
                "持有天數": f"跟單 {d} 天",
                "勝率 (%)": f"{round(w_rate, 1)} %",
                "平均報酬率 (%)": f"{round(avg_r, 2)} %"
            })
        st.table(pd.DataFrame(stats))
        
        # 產業別族群表現排行榜
        st.markdown("#### 🏭 產業族群表現排行")
        ind_summary = []
        for ind, group in target_df.groupby("產業別"):
            ind_count = len(group)
            win_5d = (group["+5日報酬(%)"] > 0).sum()
            win_rate_5d = (win_5d / ind_count) * 100
            avg_ret_5d = group["+5日報酬(%)"].mean()
            ind_summary.append({
                "產業類別": ind,
                "觸發次數": ind_count,
                "+5日勝率 (%)": f"{round(win_rate_5d, 1)} %",
                "+5日平均報酬 (%)": round(avg_ret_5d, 2)
            })
        ind_df = pd.DataFrame(ind_summary).sort_values(by="觸發次數", ascending=False)
        st.dataframe(ind_df, use_container_width=True)
        
        # 雙下拉篩選器
        st.markdown("---")
        st.subheader("🔍 精準條件過濾")
        col_ind, col_ret = st.columns(2)
        
        with col_ind:
            all_industries = ["全部產業"] + sorted(list(target_df["產業別"].unique()))
            selected_ind = st.selectbox(f"選擇產業別", all_industries, key=f"ind_{title_prefix}")
            
        target_df["報酬區間(+5日)"] = target_df["+5日報酬(%)"].apply(get_return_tier)
        tier_order = [
            "全部區間", "🔥 > +30%", "🚀 +20% ~ +30%", "🟢 +10% ~ +20%",
            "🌱 0% ~ +10%", "🔻 -10% ~ 0%", "💀 < -10%"
        ]
        with col_ret:
            selected_ret = st.selectbox("選擇 +5 日報酬率區間 (每10%一單位)", tier_order, key=f"ret_{title_prefix}")
            
        filtered_df = target_df.copy()
        if selected_ind != "全部產業":
            filtered_df = filtered_df[filtered_df["產業別"] == selected_ind]
        if selected_ret != "全部區間":
            filtered_df = filtered_df[filtered_df["報酬區間(+5日)"] == selected_ret]
            
        st.markdown(f"**符合篩選之標的明細 (共 {len(filtered_df)} 筆，依 +5 日報酬排序)**")
        st.dataframe(filtered_df.sort_values(by="+5日報酬(%)", ascending=False), use_container_width=True)
    else:
        st.success(f"當日共找到 {len(target_df)} 檔標的")
        all_industries = ["全部產業"] + sorted(list(target_df["產業別"].unique()))
        selected_ind = st.selectbox("依產業別檢視：", all_industries)
        show_df = target_df if selected_ind == "全部產業" else target_df[target_df["產業別"] == selected_ind]
        st.dataframe(show_df, use_container_width=True)

# ----------------- 側邊欄控制項 -----------------
st.sidebar.header("⚙️ 篩選與策略選擇")

strategy_choice = st.sidebar.radio(
    "選擇選股模式",
    [
        "🔥 1. 投信常規買進 (首買 / 連買3天)",
        "⚡ 2. 投信 x 布林低基期共振 (主力剛點火)",
        "💎 3. 投信買超佔成交量高比例 (籌碼鎖定)",
        "🗜️ 4. 布林通道極致壓縮爆發 (帶量突破)",
        "📈 5. 布林通道突破上軌 (動能噴出)",
        "📉 6. 跌破布林下軌 (超跌反彈)",
        "⚠️ 7. 投信連買轉賣出 (出場避險訊號)"
    ]
)

target_date = st.sidebar.date_input("查詢基準日期", datetime.date.today())
min_vol = st.sidebar.number_input("最低成交量門檻 (張)", value=300, step=100)

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 風報比設定")
stop_loss_pct = st.sidebar.slider("停損基準幅度 (%)", min_value=3.0, max_value=15.0, value=10.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("📊 回測模式設定")
backtest_mode = st.sidebar.radio("選擇回測範圍", ["單季全樣本滾動回測 (約 45~55 交易日)", "僅看當日盤後訊號 (不回測)"])
is_backtest = backtest_mode.startswith("單季")

# ----------------- 策略執行本體 -----------------
days_to_pull = 55 if is_backtest else 25

if st.button("🚀 開始執行策略掃描與回測"):
    df_raw = get_market_history(target_date, days_needed=days_to_pull)
    if not df_raw.empty:
        results = []
        tab1_list, tab2_list = [], []  # 用於首買與連買3天
        
        for code, group in df_raw.groupby("code"):
            group = group.sort_values("date").reset_index(drop=True)
            n_rows = len(group)
            if n_rows < (26 if is_backtest else 20):
                continue
                
            close_series = group["close"]
            vol_series = group["volume"]
            sitc_series = group["sitc_buy"]
            
            # 技術指標預先計算
            ma20 = close_series.rolling(20).mean()
            std20 = close_series.rolling(20).std()
            upper20 = ma20 + (std20 * 2.0)
            lower20 = ma20 - (std20 * 2.0)
            bandwidth = (upper20 - lower20) / ma20
            vol_ma5 = vol_series.rolling(5).mean()
            vol_ma20 = vol_series.rolling(20).mean()
            
            max_valid_t = (n_rows - 7) if is_backtest else (n_rows - 1)
            start_t = 20
            if max_valid_t < start_t:
                continue
                
            scan_range = range(start_t, max_valid_t + 1) if is_backtest else [n_rows - 1]
            
            for t_idx in scan_range:
                t_vol = vol_series.iloc[t_idx]
                if t_vol < min_vol:
                    continue
                    
                c = close_series.iloc[t_idx]
                t_sitc = sitc_series.iloc[t_idx]
                name = group["name"].iloc[t_idx]
                sig_date = str(group["date"].iloc[t_idx])
                
                # ----------------- 7 大策略條件判定 -----------------
                match = False
                sub_type = ""
                
                if "1. 投信常規買進" in strategy_choice:
                    t1, t2, t3 = sitc_series.iloc[t_idx - 1], sitc_series.iloc[t_idx - 2], sitc_series.iloc[t_idx - 3]
                    is_first = (t_sitc >= 100) and (max(t1, t2, t3) <= 10)
                    is_c3 = (t_sitc >= 80) and (t1 >= 80) and (t2 >= 80) and (t3 <= 30)
                    if is_first:
                        match, sub_type = True, "🔥 首日買進"
                    elif is_c3:
                        match, sub_type = True, "🚀 連買 3 天"
                        
                elif "2. 投信 x 布林低基期共振" in strategy_choice:
                    # 投信買超 > 80張 + 站穩中軌(MA20)且離中軌不超過3% + 成交量大於5日均量
                    near_ma20 = (c >= ma20.iloc[t_idx]) and (c <= ma20.iloc[t_idx] * 1.03)
                    vol_up = t_vol >= vol_ma5.iloc[t_idx]
                    if (t_sitc >= 80) and near_ma20 and vol_up:
                        match = True
                        
                elif "3. 投信買超佔成交量高比例" in strategy_choice:
                    # 當日投信買超佔成交量 10% 以上 (法人全力吃貨)
                    sitc_vol_ratio = (t_sitc / t_vol) * 100 if t_vol > 0 else 0
                    if (t_sitc >= 150) and (sitc_vol_ratio >= 10.0):
                        match = True
                        
                elif "4. 布林通道極致壓縮爆發" in strategy_choice:
                    # 過去5天頻寬平均 < 10%，今日帶量突破上軌且量大於20日均量 1.5 倍
                    is_squeeze = bandwidth.iloc[t_idx - 5 : t_idx].mean() < 0.12
                    break_up = c >= upper20.iloc[t_idx] * 0.995
                    vol_blast = t_vol >= vol_ma20.iloc[t_idx] * 1.5
                    if is_squeeze and break_up and vol_blast:
                        match = True
                        
                elif "5. 布林通道突破上軌" in strategy_choice:
                    if c >= upper20.iloc[t_idx] * 0.995:
                        match = True
                        
                elif "6. 跌破布林下軌" in strategy_choice:
                    if c <= lower20.iloc[t_idx] * 1.005:
                        match = True
                        
                elif "7. 投信連買轉賣出" in strategy_choice:
                    # 前3天投信天天買超 > 50張，今日首度賣超 > 100張 (出場避險)
                    t1, t2, t3 = sitc_series.iloc[t_idx - 1], sitc_series.iloc[t_idx - 2], sitc_series.iloc[t_idx - 3]
                    prior_buying = (t1 >= 50) and (t2 >= 50) and (t3 >= 50)
                    turn_to_sell = t_sitc <= -100
                    if prior_buying and turn_to_sell:
                        match = True

                # ----------------- 封裝資料與回測 -----------------
                if match:
                    sl_p, tp3_p, tp5_p = calc_rr_targets(c, stop_loss_pct)
                    item = {
                        "代號": str(code), "名稱": name, "訊號日(T)": sig_date,
                        "基準收盤": c,
                        f"停損(-{stop_loss_pct}%)": sl_p,
                        f"1:3停利(+{stop_loss_pct*3}%)": tp3_p,
                        f"1:5停利(+{stop_loss_pct*5}%)": tp5_p,
                        "T日投信買賣超(張)": int(t_sitc),
                        "成交量": int(t_vol)
                    }
                    if is_backtest:
                        entry_p = close_series.iloc[t_idx + 1]
                        item["進場日(T+1)"] = str(group["date"].iloc[t_idx + 1])
                        item["進場價"] = entry_p
                        for d in range(1, 6):
                            day_close = close_series.iloc[t_idx + 1 + d]
                            ret = ((day_close - entry_p) / entry_p) * 100
                            item[f"+{d}日報酬(%)"] = round(ret, 2)
                            
                    if "1. 投信常規買進" in strategy_choice:
                        if sub_type == "🔥 首日買進":
                            tab1_list.append(item)
                        else:
                            tab2_list.append(item)
                    else:
                        results.append(item)

        # ----------------- 結果呈現 -----------------
        if "1. 投信常規買進" in strategy_choice:
            tab1, tab2 = st.tabs(["🔥 首日買進分析", "🚀 連買 3 天分析"])
            with tab1:
                render_backtest_with_filters(pd.DataFrame(tab1_list), "首日買進", is_backtest)
            with tab2:
                render_backtest_with_filters(pd.DataFrame(tab2_list), "連續買進 3 天", is_backtest)
        else:
            render_backtest_with_filters(pd.DataFrame(results), strategy_choice, is_backtest)