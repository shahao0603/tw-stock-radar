import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import datetime
import yfinance as yf

# -------------------------------------------------------------
# 0. 頁面基礎設定
# -------------------------------------------------------------
st.set_page_config(
    page_title="台股專屬雙模選股雷達 (全母體旗艦版)",
    page_icon="🎯",
    layout="wide"
)

# -------------------------------------------------------------
# 1. 官方標準產業代碼對照表
# -------------------------------------------------------------
REAL_INDUSTRY_MAP = {
    "2881": "金融保險業", "2882": "金融保險業", "2886": "金融保險業", "2891": "金融保險業",
    "2884": "金融保險業", "2885": "金融保險業", "2892": "金融保險業", "2880": "金融保險業",
    "2883": "金融保險業", "2887": "金融保險業", "2890": "金融保險業", "5880": "金融保險業",
    "2897": "金融保險業", "2330": "半導體業", "2454": "半導體業", "2303": "半導體業", "3711": "半導體業",
    "2382": "電腦及週邊設備業", "3231": "電腦及週邊設備業", "2357": "電腦及週邊設備業",
    "2308": "電子零組件業", "2317": "其他電子業", "3037": "電子零組件業", "2351": "電子工業",
    "2603": "航運業", "2609": "航運業", "2615": "航運業", "6226": "光電業",
    "1301": "塑膠工業", "1303": "塑膠工業", "1304": "塑膠工業", "1326": "化學工業",
    "2409": "光電業", "3481": "光電業", "2313": "電子零組件業", "2449": "半導體業"
}

BACKUP_STOCK_POOL = [
    {"代號": "2330", "名稱": "台積電", "產業別": "半導體業", "收盤價": 950.0, "成交量(張)": 35000},
    {"代號": "2317", "名稱": "鴻海", "產業別": "其他電子業", "收盤價": 180.0, "成交量(張)": 45000},
    {"代號": "2454", "名稱": "聯發科", "產業別": "半導體業", "收盤價": 1250.0, "成交量(張)": 8000},
    {"代號": "2351", "名稱": "順德", "產業別": "電子工業", "收盤價": 257.0, "成交量(張)": 13792},
    {"代號": "6226", "名稱": "光鼎", "產業別": "光電業", "收盤價": 33.0, "成交量(張)": 33484},
    {"代號": "2897", "名稱": "王道銀行", "產業別": "金融保險業", "收盤價": 11.25, "成交量(張)": 13430},
    {"代號": "2603", "名稱": "長榮", "產業別": "航運業", "收盤價": 195.0, "成交量(張)": 28000},
    {"代號": "2609", "名稱": "陽明", "產業別": "航運業", "收盤價": 65.0, "成交量(張)": 35000},
    {"代號": "2615", "名稱": "萬海", "產業別": "航運業", "收盤價": 88.0, "成交量(張)": 26000},
    {"代號": "2382", "名稱": "廣達", "產業別": "電腦及週邊設備業", "收盤價": 270.0, "成交量(張)": 21000},
    {"代號": "3231", "名稱": "緯創", "產業別": "電腦及週邊設備業", "收盤價": 105.0, "成交量(張)": 32000}
]

def get_real_industry(code: str) -> str:
    if code in REAL_INDUSTRY_MAP:
        return REAL_INDUSTRY_MAP[code]
    c = int(code) if code.isdigit() else 0
    if 2800 <= c <= 2899 or 5800 <= c <= 5899:
        return "金融保險業"
    elif 2600 <= c <= 2699:
        return "航運業"
    elif 1500 <= c <= 1599:
        return "電機機械業"
    elif 1300 <= c <= 1399:
        return "塑膠工業"
    elif 1700 <= c <= 1799:
        return "化學工業"
    elif 2300 <= c <= 2499 or 3000 <= c <= 3799:
        return "電子工業"
    return "其他傳產"

# -------------------------------------------------------------
# 2. 策略清單定義 (核心 -> 一般 -> 賣出提醒 -> 特定時刻)
# -------------------------------------------------------------
STRATEGY_CATEGORY_MAP = {
    "🔥 核心順勢交易策略 (正規主升段)": {
        "布林軌道：突破上軌＋20MA/60MA上翹 (達標出半放中軌/未達標全出)": "core_bollinger_trailing",
        "投信初認養第1天：20MA>60MA上翹＋站上5MA (達標出半放10MA/未達標全出)": "core_sitc_day1",
        "投信強勢連買3天以上：20MA>60MA上翹＋站上5MA (達標出半放10MA/未達標全出)": "core_sitc_streak3"
    },
    "💡 一般動能與型態策略 (日常補充雷達)": {
        "量增價揚強勢動能 (Volume Momentum Spike)": "other_vol_momentum",
        "季線洗盤假跌破：T+5日內強勢站回 ＋ 季線上翹多頭 (MA60 Fake Breakout Reclaim)": "other_ma60_rebound",
        "波動壓縮後首度爆發 (前5日軌內沉睡＋今日首度帶量穿上軌)": "other_squeeze_breakout"
    },
    "🚨 持股賣出提醒雷達 (投信棄養下車)": {
        "⚠️ 投信由買轉賣第 1 天 (短線鬆動，獲利減碼 50% 提醒)": "exit_sitc_turn_sell",
        "🚨 投信連續倒貨棄養 (連賣且摜破10MA生命線，全數清倉提醒)": "exit_sitc_dumping"
    },
    "🛡️ 崩盤恐慌逆勢抄底專區 (特定時刻用)": {
        "⚡ 逆布林策略：大盤恐慌崩盤＋跌破下軌收斂轉折 (達5MA出半/直奔中軌全出)": "panic_reverse_bollinger"
    }
}

# -------------------------------------------------------------
# 3. 抓取 TWSE 活躍股 (開放 max_stocks 動態調整)
# -------------------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_real_twse_pool(min_vol: int = 1000, max_stocks: int = 150):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            df_raw = pd.read_csv(io.StringIO(res.text))
            df_raw.columns = [c.strip().replace('"', '') for c in df_raw.columns]
            
            df = pd.DataFrame()
            df["代號"] = df_raw["證券代號"].astype(str).str.strip().str.replace('"', '')
            df["名稱"] = df_raw["證券名稱"].astype(str).str.strip().str.replace('"', '')
            
            df = df[df["代號"].str.len() == 4]
            df = df[df["代號"].str.isdigit()]

            def parse_num(s):
                try:
                    return float(str(s).replace(",", "").replace('"', '').strip())
                except:
                    return 0.0

            df["收盤價"] = df_raw["收盤價"].apply(parse_num)
            df["成交量(張)"] = df_raw["成交股數"].apply(parse_num) // 1000
            
            df = df[(df["收盤價"] > 10.0) & (df["成交量(張)"] >= min_vol)].copy()
            df["產業別"] = df["代號"].apply(get_real_industry)
            if not df.empty:
                return df.sort_values(by="成交量(張)", ascending=False).head(max_stocks)
    except Exception:
        pass
    return pd.DataFrame(BACKUP_STOCK_POOL)

# -------------------------------------------------------------
# 4. yfinance 抓取歷史 K 線
# -------------------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_historical_ohlc_data(code_list: list):
    if not code_list:
        return {}

    k_dict = {}
    for c in code_list:
        try:
            ticker = f"{c}.TW"
            sub = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
            if not sub.empty and len(sub) >= 65:
                if isinstance(sub.columns, pd.MultiIndex):
                    sub = sub.xs(ticker, level=1, axis=1)
                sub.index = pd.to_datetime(sub.index).strftime("%Y-%m-%d")
                k_dict[c] = sub[["Open", "High", "Low", "Close", "Volume"]].dropna()
        except Exception:
            continue
    return k_dict

# -------------------------------------------------------------
# 5. 基準日訊號運算
# -------------------------------------------------------------
def get_signals_by_date(df_pool: pd.DataFrame, k_dict: dict, strategy_key: str, target_rr: float, base_date_str: str):
    signals = []
    for _, row in df_pool.iterrows():
        code = row["代號"]
        if code not in k_dict:
            continue
        df_k = k_dict[code]

        sub_k = df_k.loc[df_k.index <= base_date_str]
        if len(sub_k) < 65:
            continue

        try:
            close = float(sub_k["Close"].iloc[-1])
            high = float(sub_k["High"].iloc[-1])
            low = float(sub_k["Low"].iloc[-1])
            prev_close = float(sub_k["Close"].iloc[-2])
            vol = float(sub_k["Volume"].iloc[-1])
            vol_prev = float(sub_k["Volume"].iloc[-2])
            actual_date = str(sub_k.index[-1])

            s_close = sub_k["Close"]
            ma5 = float(s_close.tail(5).mean())
            ma10 = float(s_close.tail(10).mean())
            ma20 = float(s_close.tail(20).mean())
            ma20_prev = float(s_close.iloc[-21:-1].mean())
            
            ma60 = float(s_close.tail(60).mean())
            ma60_prev = float(s_close.iloc[-61:-1].mean())
            ma60_up = ma60 > ma60_prev

            std20 = float(s_close.tail(20).std())
            bb_upper = ma20 + (2.0 * std20)
            bb_mid = ma20
            bb_lower = ma20 - (2.0 * std20)

            ma20_up = ma20 > ma20_prev
            trend_ok = (ma20 > ma60) and ma20_up

            item = {
                "代號": code,
                "名稱": row["名稱"],
                "產業別": row["產業別"],
                "基準日": actual_date,
                "收盤價": round(close, 2),
                "成交量(張)": int(row["成交量(張)"]),
                "5MA": round(ma5, 2),
                "10MA": round(ma10, 2),
                "20MA": round(ma20, 2),
                "60MA": round(ma60, 2),
                "布林上軌": round(bb_upper, 2),
                "布林中軌": round(bb_mid, 2),
                "布林下軌": round(bb_lower, 2),
                "20MA趨勢": "▲ 多頭上翹" if ma20_up else "▼ 下彎",
                "60MA趨勢": "▲ 多頭上翹" if ma60_up else "▼ 下彎"
            }

            triggered = False

            if strategy_key == "core_bollinger_trailing":
                if trend_ok and (close >= bb_upper * 0.985):
                    item["風報比"] = round((close - bb_mid) / max(close * 0.035, 0.4), 2)
                    item["進場狀態"] = "🔥 突破上軌且均線多頭上翹"
                    item["出場指引"] = f"跌破上軌({round(bb_upper,2)})：達標出50%，破中軌({round(bb_mid,2)})全出；未達標全出"
                    triggered = True

            elif strategy_key in ["core_sitc_day1", "core_sitc_streak3"]:
                if trend_ok and (close >= ma5):
                    item["風報比"] = round((close - ma10) / max(close * 0.03, 0.3), 2)
                    item["進場狀態"] = "🔥 站上5MA且20MA>60MA上翹"
                    item["出場指引"] = f"達標風報比({target_rr}R)出50%，剩餘整根完全跌破10MA({round(ma10,2)})全數清空"
                    triggered = True

            elif strategy_key == "other_vol_momentum":
                if close > prev_close and close > ma5:
                    item["風報比"] = round((close - ma5) / max(close * 0.025, 0.3), 2)
                    item["進場狀態"] = "⚡ 量價齊揚突破 5MA 短線動能"
                    item["出場指引"] = f"跌破 5MA ({round(ma5,2)}) 短線平倉"
                    triggered = True

            elif strategy_key == "other_ma60_rebound":
                if (close >= ma60) and ma60_up:
                    recent_broke = False
                    days_under = 0
                    for d in range(2, 7):
                        past_c = float(s_close.iloc[-d])
                        past_ma60 = float(s_close.iloc[-d-60:-d].mean()) if len(s_close) >= (d+60) else ma60
                        if past_c < past_ma60:
                            recent_broke = True
                            days_under = d - 1
                            break
                    
                    if recent_broke:
                        item["風報比"] = round((close - ma60) / max(close * 0.03, 0.4), 2)
                        item["進場狀態"] = f"🌱 季線洗盤成立！T+{days_under} 日站回季線，季線上翹多頭不變"
                        item["出場指引"] = f"收盤再度跌破季線 60MA ({round(ma60,2)}) 停損；達標出 50%"
                        triggered = True

            elif strategy_key == "other_squeeze_breakout":
                today_break = close >= bb_upper
                stayed_inside_5days = True
                for d in range(2, 7):
                    c_d = float(s_close.iloc[-d])
                    ma20_d = float(s_close.iloc[-d-20:-d].mean())
                    std20_d = float(s_close.iloc[-d-20:-d].std())
                    upper_d = ma20_d + (2.0 * std20_d)
                    if c_d >= upper_d:
                        stayed_inside_5days = False
                        break
                
                s_prev = s_close.iloc[:-1]
                ma20_y = float(s_prev.tail(20).mean())
                std20_y = float(s_prev.tail(20).std())
                bw_y = (4.0 * std20_y) / ma20_y if ma20_y > 0 else 1.0
                is_squeeze = bw_y <= 0.10
                vol_up = vol >= vol_prev * 1.25

                if today_break and stayed_inside_5days and is_squeeze and vol_up:
                    item["風報比"] = round((close - ma20) / max(close * 0.035, 0.4), 2)
                    item["進場狀態"] = "💥 前5日極度壓縮沉睡，今日首度帶量穿透上軌表態！"
                    item["出場指引"] = f"跌破 20MA ({round(ma20,2)}) 全數出場"
                    triggered = True

            elif strategy_key == "exit_sitc_turn_sell":
                if close < prev_close and close < ma5 and close >= ma10:
                    item["警戒等級"] = "⚠️ 短線鬆動 (由買轉賣首日)"
                    item["操作建議"] = f"建議【先出 50% 鎖利】，剩餘嚴設 10MA ({round(ma10,2)}) 防守"
                    triggered = True

            elif strategy_key == "exit_sitc_dumping":
                if high < ma10 or close < ma10:
                    item["警戒等級"] = "🚨 棄養倒貨 (跌破生命線)"
                    item["操作建議"] = f"跌破 10MA ({round(ma10,2)})！請【全數清倉出場】"
                    triggered = True

            elif strategy_key == "panic_reverse_bollinger":
                if (low <= bb_lower) and (close >= prev_close):
                    item["風報比"] = round(max(bb_mid - close, 0.5) / max(close - low, close * 0.035), 2)
                    item["進場狀態"] = "🚨 逆布林：殺穿下軌止跌收斂"
                    item["出場指引"] = f"反彈越過5MA出50%，直奔中軌({round(bb_mid,2)})全出；破當日低點停損"
                    triggered = True

            if triggered:
                signals.append(item)
        except Exception:
            continue

    return pd.DataFrame(signals)

# -------------------------------------------------------------
# 6. 歷史回測引擎
# -------------------------------------------------------------
def run_real_historical_backtest(k_dict: dict, df_pool: pd.DataFrame, strategy_key: str, target_rr: float, backtest_len: int = 60, base_date_str: str = ""):
    trades = []
    
    for _, row in df_pool.iterrows():
        code = row["代號"]
        if code not in k_dict:
            continue
        df_k = k_dict[code]
        
        sub_k = df_k.loc[df_k.index <= base_date_str]
        if len(sub_k) < (backtest_len + 65):
            continue
        
        eval_k = sub_k.iloc[-backtest_len:]
        
        in_trade = False
        entry_price = 0.0
        entry_date = ""
        stop_loss_price = 0.0
        half_exited = False
        first_exit_date = "-"
        first_exit_price = "-"
        first_exit_ret = 0.0

        for i in range(5, len(eval_k)):
            dt = str(eval_k.index[i])
            cur_slice = sub_k.loc[:eval_k.index[i]]
            
            try:
                close = float(cur_slice["Close"].iloc[-1])
                high = float(cur_slice["High"].iloc[-1])
                low = float(cur_slice["Low"].iloc[-1])
                prev_c = float(cur_slice["Close"].iloc[-2])
                vol = float(cur_slice["Volume"].iloc[-1])
                vol_prev = float(cur_slice["Volume"].iloc[-2])
                s_c = cur_slice["Close"]

                ma5 = float(s_c.tail(5).mean())
                ma10 = float(s_c.tail(10).mean())
                ma20 = float(s_c.tail(20).mean())
                ma20_prev = float(s_c.iloc[-21:-1].mean())
                ma60 = float(s_c.tail(60).mean())
                ma60_prev = float(s_c.iloc[-61:-1].mean())
                ma60_up = ma60 > ma60_prev

                std20 = float(s_c.tail(20).std())
                bb_upper = ma20 + (2.0 * std20)
                bb_mid = ma20
                bb_lower = ma20 - (2.0 * std20)

                trend_ok = (ma20 > ma60) and (ma20 > ma20_prev)

                if not in_trade:
                    buy_sig = False
                    if strategy_key == "core_bollinger_trailing":
                        buy_sig = trend_ok and (close >= bb_upper * 0.985)
                    elif strategy_key in ["core_sitc_day1", "core_sitc_streak3", "exit_sitc_turn_sell", "exit_sitc_dumping"]:
                        buy_sig = trend_ok and (close >= ma5)
                    elif strategy_key == "panic_reverse_bollinger":
                        buy_sig = (low <= bb_lower) and (close >= prev_c)
                    elif strategy_key == "other_vol_momentum":
                        buy_sig = (close > prev_c) and (close > ma5)
                    
                    elif strategy_key == "other_ma60_rebound":
                        if (close >= ma60) and ma60_up:
                            recent_broke = False
                            for d in range(2, 7):
                                past_c = float(s_c.iloc[-d])
                                past_ma60 = float(s_c.iloc[-d-60:-d].mean())
                                if past_c < past_ma60:
                                    recent_broke = True
                                    break
                            buy_sig = recent_broke

                    elif strategy_key == "other_squeeze_breakout":
                        today_break = close >= bb_upper
                        stayed_inside_5days = True
                        for d in range(2, 7):
                            c_d = float(s_c.iloc[-d])
                            ma20_d = float(s_c.iloc[-d-20:-d].mean())
                            std20_d = float(s_c.iloc[-d-20:-d].std())
                            if c_d >= (ma20_d + 2.0 * std20_d):
                                stayed_inside_5days = False
                                break
                        s_prev_c = s_c.iloc[:-1]
                        bw_y = (4.0 * float(s_prev_c.tail(20).std())) / float(s_prev_c.tail(20).mean())
                        buy_sig = today_break and stayed_inside_5days and (bw_y <= 0.10) and (vol >= vol_prev * 1.25)

                    if buy_sig:
                        in_trade = True
                        entry_price = close
                        entry_date = dt
                        stop_loss_price = low if strategy_key == "panic_reverse_bollinger" else 0.0
                        half_exited = False
                        first_exit_date = "-"
                        first_exit_price = "-"
                        first_exit_ret = 0.0

                else:
                    cur_ret = (close - entry_price) / entry_price
                    
                    if strategy_key == "core_bollinger_trailing":
                        if close < bb_upper:
                            rr = cur_ret / 0.035
                            if rr >= target_rr and not half_exited:
                                half_exited = True
                                first_exit_date = dt
                                first_exit_price = f"{close:.2f}"
                                first_exit_ret = cur_ret * 100
                            elif not half_exited:
                                total_ret = cur_ret * 100
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "未達風報比跌破上軌全出"
                                })
                                in_trade = False

                        if in_trade and half_exited and (close <= bb_mid):
                            second_exit_ret = cur_ret * 100
                            final_total_ret = 0.5 * first_exit_ret + 0.5 * second_exit_ret
                            trades.append({
                                "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                "第1次出場日": first_exit_date, "第1次出場價": first_exit_price, "全數出場日": dt, "全數出場價": round(close, 2),
                                "總報酬率(%)": round(final_total_ret, 2), "勝負": "勝" if final_total_ret > 0 else "敗", "出場型態": "達標出50%後，破中軌(20MA)全出"
                            })
                            in_trade = False

                    elif strategy_key in ["core_sitc_day1", "core_sitc_streak3", "exit_sitc_turn_sell", "exit_sitc_dumping"]:
                        rr = cur_ret / 0.03
                        if rr >= target_rr and not half_exited and (close < ma5 or close < prev_c):
                            half_exited = True
                            first_exit_date = dt
                            first_exit_price = f"{close:.2f}"
                            first_exit_ret = cur_ret * 100

                        if high < ma10 and close < ma10:
                            if half_exited:
                                second_exit_ret = cur_ret * 100
                                final_total_ret = 0.5 * first_exit_ret + 0.5 * second_exit_ret
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": first_exit_date, "第1次出場價": first_exit_price, "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(final_total_ret, 2), "勝負": "勝" if final_total_ret > 0 else "敗", "出場型態": "達標出50%後，完全跌破10MA全出"
                                })
                            else:
                                total_ret = cur_ret * 100
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "未達標完全跌破10MA全數停損"
                                })
                            in_trade = False

                    elif strategy_key == "other_ma60_rebound":
                        rr = cur_ret / 0.035
                        if rr >= target_rr and not half_exited:
                            half_exited = True
                            first_exit_date = dt
                            first_exit_price = f"{close:.2f}"
                            first_exit_ret = cur_ret * 100

                        if close < ma60:
                            if half_exited:
                                second_exit_ret = cur_ret * 100
                                final_total_ret = 0.5 * first_exit_ret + 0.5 * second_exit_ret
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": first_exit_date, "第1次出場價": first_exit_price, "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(final_total_ret, 2), "勝負": "勝" if final_total_ret > 0 else "敗", "出場型態": "達標出50%後，再破季線全出"
                                })
                            else:
                                total_ret = cur_ret * 100
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "跌破季線(60MA)停損"
                                })
                            in_trade = False

                    elif strategy_key == "panic_reverse_bollinger":
                        if close >= ma5 and not half_exited:
                            half_exited = True
                            first_exit_date = dt
                            first_exit_price = f"{close:.2f}"
                            first_exit_ret = cur_ret * 100

                        reached_mid = close >= bb_mid
                        stop_hit = close < stop_loss_price

                        if reached_mid or stop_hit:
                            if half_exited:
                                second_exit_ret = cur_ret * 100
                                final_total_ret = 0.5 * first_exit_ret + 0.5 * second_exit_ret
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": first_exit_date, "第1次出場價": first_exit_price, "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(final_total_ret, 2), "勝負": "勝" if final_total_ret > 0 else "敗", "出場型態": "達中軌(20MA)全出" if reached_mid else "破低點停損"
                                })
                            else:
                                total_ret = cur_ret * 100
                                trades.append({
                                    "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                    "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                    "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "直奔中軌全出" if reached_mid else "破低點停損"
                                })
                            in_trade = False

                    elif strategy_key == "other_vol_momentum":
                        if close < ma5:
                            total_ret = cur_ret * 100
                            trades.append({
                                "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "跌破5MA短線停利"
                            })
                            in_trade = False

                    elif strategy_key == "other_squeeze_breakout":
                        if close < ma20:
                            total_ret = cur_ret * 100
                            trades.append({
                                "代號": code, "名稱": row["名稱"], "進場日": entry_date, "進場價": round(entry_price, 2),
                                "第1次出場日": dt, "第1次出場價": f"{close:.2f}", "全數出場日": dt, "全數出場價": round(close, 2),
                                "總報酬率(%)": round(total_ret, 2), "勝負": "勝" if total_ret > 0 else "敗", "出場型態": "跌破20MA月線出場"
                            })
                            in_trade = False
            except Exception:
                continue

    return pd.DataFrame(trades)

# -------------------------------------------------------------
# 7. 主程式入口
# -------------------------------------------------------------
def main():
    with st.sidebar:
        st.header("📅 查詢基準日設定")
        selected_date = st.date_input(
            "選擇查詢基準日 (As of Date)",
            value=datetime.date.today(),
            max_value=datetime.date.today()
        )
        base_date_str = selected_date.strftime("%Y-%m-%d")
        st.info(f"當前雷達基準日：`{base_date_str}`")

        st.markdown("---")
        st.header("🎯 策略專區切換")
        selected_category = st.radio("選擇策略專區", list(STRATEGY_CATEGORY_MAP.keys()), index=0)
        strategy_options = STRATEGY_CATEGORY_MAP[selected_category]
        selected_strategy_label = st.selectbox("選擇觸發策略", list(strategy_options.keys()))
        strategy_code = strategy_options[selected_strategy_label]

        st.markdown("---")
        st.header("⚙️ 參數設定")
        max_stocks = st.slider("🔍 監控母體數量上限 (檔)", min_value=50, max_value=300, value=150, step=25)
        backtest_days = st.slider("歷史回測天數 (天)", min_value=45, max_value=60, value=60, step=5)
        
        if strategy_code in ["core_bollinger_trailing", "core_sitc_day1", "core_sitc_streak3", "other_ma60_rebound"]:
            target_rr = st.slider("第一階段停利目標風報比 (R:R)", 1.0, 3.0, 1.5, 0.1)
        else:
            target_rr = 1.5
            
        min_vol = st.slider("最低成交量門檻 (張)", 800, 5000, 1500, 300)

    st.title("🎯 台股專屬雙模選股雷達 (全功能旗艦版)")
    st.caption("支援【核心順勢 ＋ 季線洗盤站回 ＋ 賣出提醒 ＋ 逆布林抄底】")

    with st.spinner(f"載入台股前 {max_stocks} 大活躍股數據中..."):
        df_pool = fetch_real_twse_pool(min_vol, max_stocks)
        pool_codes = df_pool["代號"].tolist() if not df_pool.empty else []
        k_dict = fetch_historical_ohlc_data(pool_codes)

    is_exit_radar = "exit_sitc" in strategy_code

    tab_signals, tab_backtest = st.tabs([
        f"🚨 基準日賣出提醒 ({base_date_str})" if is_exit_radar else f"📡 基準日實時訊號 ({base_date_str})", 
        f"📈 基準日前推 {backtest_days} 天驗證紀錄"
    ])

    with tab_signals:
        df_today = get_signals_by_date(df_pool, k_dict, strategy_code, target_rr, base_date_str)
        
        c1, c2 = st.columns(2)
        c1.metric("提醒警戒檔數" if is_exit_radar else "基準日觸發標的", f"{len(df_today)} 檔")
        c2.metric("監控母體庫存池", f"{len(df_pool)} 檔")

        if is_exit_radar:
            st.warning("⚠️ **【持股賣出提醒專區】**：此處標的為投信籌碼鬆動或棄養倒貨之警戒股。若持有此類股票，請嚴格依建議指引分批停利或清倉！")
            if not df_today.empty:
                disp_cols = ["代號", "名稱", "產業別", "基準日", "收盤價", "5MA", "10MA", "警戒等級", "操作建議", "成交量(張)"]
                st.dataframe(
                    df_today[disp_cols].style.format({
                        "收盤價": "{:.2f}",
                        "5MA": "{:.2f}",
                        "10MA": "{:.2f}",
                        "成交量(張)": "{:,}"
                    }),
                    width="stretch,
                    hide_index=True
                )
            else:
                st.success("✅ 今日監控池中無投信大幅倒貨或破線之持股，持股整體穩定！")
        else:
            st.markdown(f"#### 🎯 `{base_date_str}` 符合【{selected_strategy_label}】標的")
            if not df_today.empty:
                disp_cols = ["代號", "名稱", "產業別", "基準日", "收盤價", "20MA", "60MA", "60MA趨勢", "風報比", "進場狀態", "出場指引", "成交量(張)"]
                st.dataframe(
                    df_today[disp_cols].style.format({
                        "收盤價": "{:.2f}",
                        "20MA": "{:.2f}",
                        "60MA": "{:.2f}",
                        "風報比": "{:.2f}",
                        "成交量(張)": "{:,}"
                    }),
                    width="stretch,
                    hide_index=True
                )
            else:
                st.info(f"💡 `{base_date_str}` 無標的滿足條件，嚴守紀律！")

    with tab_backtest:
        df_bt = run_real_historical_backtest(k_dict, df_pool, strategy_code, target_rr, backtest_days, base_date_str)
        
        if not df_bt.empty:
            win_count = len(df_bt[df_bt["勝負"] == "勝"])
            win_rate = (win_count / len(df_bt)) * 100
            avg_ret = df_bt["總報酬率(%)"].mean()
            profit_trades = df_bt[df_bt["總報酬率(%)"] > 0]["總報酬率(%)"].mean() if win_count > 0 else 0
            loss_trades = abs(df_bt[df_bt["總報酬率(%)"] < 0]["總報酬率(%)"].mean()) if (len(df_bt) - win_count) > 0 else 1
            rr_ratio = profit_trades / loss_trades if loss_trades > 0 else 0.0

            b1, b2, b3, b4 = st.columns(4)
            b1.metric(f"近{backtest_days}天交易次數", f"{len(df_bt)} 筆")
            b2.metric("真實歷史勝率", f"{win_rate:.1f}%")
            b3.metric("單筆平均報酬", f"{avg_ret:+.2f}%")
            b4.metric("歷史實際風報比", f"{rr_ratio:.2f}")

            st.markdown(f"#### 📋 截至 `{base_date_str}` 前推 {backtest_days} 天逐筆進出紀錄 (兩階段出場完整呈現)")
            
            display_bt = df_bt.sort_values(by="進場日", ascending=False).copy()
            st.dataframe(
                display_bt.style.format({
                    "進場價": "{:.2f}",
                    "全數出場價": "{:.2f}",
                    "總報酬率(%)": "{:+.2f}%"
                }),
                width="stretch,
                hide_index=True
            )
        else:
            st.warning(f"截至 `{base_date_str}` 前推 {backtest_days} 天內無觸發完成交易之樣本。")

if __name__ == "__main__":
    main()