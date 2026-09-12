import os
import re
import sys
import warnings

# Clean terminal output: ignore future/deprecation warnings
warnings.filterwarnings('ignore')

import requests
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from datetime import datetime

# Windows terminal UTF-8 encoding support for emojis
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==========================================
# GEMINI API CONFIGURATION
# ==========================================
def get_env_var(key, default=""):
    val = os.environ.get(key)
    if val:
        return val
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default

GEMINI_API_KEY = get_env_var("GEMINI_API_KEY")

if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_API_KEY_HERE":
    genai.configure(api_key=GEMINI_API_KEY)


def fetch_psx_historical_data(symbol):
    """
    Fetch historical OHLCV data from PSX Data Portal (dps.psx.com.pk).
    Returns a pandas DataFrame sorted by Date ascending (Oldest to Newest)
    so that indicators can be accurately computed chronologically.
    """
    symbol = symbol.upper().strip()
    print(f"Fetching data for {symbol}...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'https://dps.psx.com.pk/company/{symbol}'
    }

    # Approach 1: POST to /historical provides complete OHLCV (Open, High, Low, Close, Volume)
    try:
        url = "https://dps.psx.com.pk/historical"
        response = requests.post(url, data={'symbol': symbol}, headers=headers, timeout=15)

        if response.status_code == 200 and 'tbl__body' in response.text:
            pattern = re.compile(
                r'<tr[^>]*>\s*<td[^>]*data-order="(\d+)"[^>]*>(.*?)</td>\s*'
                r'<td[^>]*>(.*?)</td>\s*'
                r'<td[^>]*>(.*?)</td>\s*'
                r'<td[^>]*>(.*?)</td>\s*'
                r'<td[^>]*>(.*?)</td>\s*'
                r'<td[^>]*>(.*?)</td>\s*</tr>'
            )
            matches = pattern.findall(response.text)

            if matches:
                rows = []
                for m in matches:
                    unix_time, date_str, open_p, high_p, low_p, close_p, vol = m
                    try:
                        rows.append({
                            'Date': pd.to_datetime(int(unix_time), unit='s').date(),
                            'Open': float(open_p.replace(',', '').strip()),
                            'High': float(high_p.replace(',', '').strip()),
                            'Low': float(low_p.replace(',', '').strip()),
                            'Close': float(close_p.replace(',', '').strip()),
                            'Volume': int(vol.replace(',', '').strip())
                        })
                    except (ValueError, TypeError):
                        continue

                if rows:
                    df = pd.DataFrame(rows)
                    # IMPORTANT: Indicators ke liye data Purane se Naye (Oldest to Newest) sort hona chahiye
                    df = df.sort_values(by='Date', ascending=True).reset_index(drop=True)
                    print(f"Data fetched successfully! Total records: {len(df)}")
                    return df

    except Exception as e:
        print(f"Primary endpoint error: {e}. Trying fallback endpoint...")

    # Approach 2: Fallback to PSX JSON timeseries endpoint (/timeseries/eod/{symbol})
    try:
        ts_url = f"https://dps.psx.com.pk/timeseries/eod/{symbol}"
        ts_res = requests.get(ts_url, headers=headers, timeout=15)

        if ts_res.status_code == 200:
            json_data = ts_res.json()
            raw_data = json_data.get('data', [])
            if raw_data:
                rows = []
                for item in raw_data:
                    t, close_val, vol, open_val = item
                    rows.append({
                        'Date': pd.to_datetime(t, unit='s').date(),
                        'Open': float(open_val),
                        'High': float(close_val) if float(close_val) > float(open_val) else float(open_val),
                        'Low': float(open_val) if float(close_val) > float(open_val) else float(close_val),
                        'Close': float(close_val),
                        'Volume': int(vol)
                    })
                df = pd.DataFrame(rows)
                df = df.sort_values(by='Date', ascending=True).reset_index(drop=True)
                print(f"Data fetched successfully from timeseries! Total records: {len(df)}")
                return df
    except Exception as e:
        print(f"Fallback endpoint error: {e}")

    print(f"No data found for symbol: {symbol}")
    return None


def apply_technical_analysis(df):
    """
    Apply RSI and MACD indicators to the dataframe.
    """
    # 1. Calculate RSI (14 periods)
    df['RSI_14'] = ta.rsi(df['Close'], length=14)

    # 2. Calculate MACD (Fast 12, Slow 26, Signal 9)
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    # Data wapas Naye se Purane (Newest to Oldest) sort kar dete hain
    df = df.sort_values(by='Date', ascending=False).reset_index(drop=True)
    return df


def generate_ai_report(symbol, latest_data):
    """
    Send technical data to Gemini API and get a professional trading report.
    """
    print("\n⏳ Generating AI Analysis Report (Please wait...)")

    # Extracting values
    date = latest_data['Date']
    close = round(latest_data['Close'], 2)
    rsi = round(latest_data['RSI_14'], 2)
    macd_line = round(latest_data['MACD_12_26_9'], 2)
    macd_signal = round(latest_data['MACDs_12_26_9'], 2)
    volume = latest_data['Volume']

    # Prompt Engineering: Giving context and instructions to the AI
    prompt = f"""
    You are an expert stock market analyst specializing in the Pakistan Stock Exchange (PSX).
    Analyze the following technical parameters for the stock '{symbol}':
    
    - Date: {date}
    - Current Close Price: Rs. {close}
    - Volume: {volume:,}
    - RSI (14 Days): {rsi}
    - MACD Line: {macd_line}
    - MACD Signal Line: {macd_signal}
    
    Based on these purely technical parameters, provide a short, crisp, and professional trading signal report. 
    Your report must include:
    1. Overall Trend Analysis (Bullish, Bearish, or Neutral).
    2. Estimated Fair Target Price for a short-term trade.
    3. Suggested Strict Stop-Loss price.
    4. Final Verdict (BUY, SELL, or HOLD) in bold.
    
    Keep the tone professional and concise. Do not use generic warnings.
    """

    # Model resolution with fallback to available flash versions
    model_candidates = ['gemini-3.6-flash', 'gemini-3.8-flash', 'gemini-1.5-flash', 'gemini-flash-latest']
    response = None
    last_err = None

    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                break
        except Exception as err:
            last_err = err
            continue

    if response and response.text:
        report_text = response.text.strip()
        print("\n" + "=" * 50)
        print(f"🤖 AI TRADING SIGNAL FOR {symbol}")
        print("=" * 50)
        print(report_text)
        print("=" * 50)
        return report_text
    else:
        err_msg = f"AI Generation Failed: {last_err}"
        print(err_msg)
        return err_msg


def analyze_stock(symbol):
    """
    End-to-end analysis pipeline:
    1. Fetch PSX data
    2. Calculate technical indicators (RSI, MACD)
    3. Generate Gemini AI Trading Report
    Returns a dictionary with data, indicators, and report.
    """
    df = fetch_psx_historical_data(symbol)
    if df is None or df.empty:
        return None
    analyzed_df = apply_technical_analysis(df)
    latest = analyzed_df.iloc[0]
    report = generate_ai_report(symbol, latest)
    return {
        'symbol': symbol.upper(),
        'latest': latest,
        'report': report,
        'df': analyzed_df
    }


# --- Execution ---
if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_symbol = sys.argv[1].upper().strip()
    else:
        target_symbol = "OGDC"

    raw_df = fetch_psx_historical_data(target_symbol)

    if raw_df is not None:
        analyzed_df = apply_technical_analysis(raw_df)
        latest = analyzed_df.iloc[0]

        # Displaying Raw Technicals first
        print(f"\n[Raw Data] Close: Rs. {latest['Close']} | RSI: {round(latest['RSI_14'], 2)} | MACD: {round(latest['MACD_12_26_9'], 2)}")

        # Basic Signal Logic Check
        rsi_val = round(latest['RSI_14'], 2)
        macd_val = round(latest['MACD_12_26_9'], 2)
        macd_sig = round(latest['MACDs_12_26_9'], 2)

        print("\n--- QUICK BOT OBSERVATION ---")
        if rsi_val < 30:
            print("🟢 RSI is Oversold (Possible Buy Opportunity)")
        elif rsi_val > 70:
            print("🔴 RSI is Overbought (Possible Sell Opportunity)")
        else:
            print("⚪ RSI is Neutral")

        if macd_val > macd_sig:
            print("🟢 MACD is Bullish (MACD Line above Signal)")
        else:
            print("🔴 MACD is Bearish (MACD Line below Signal)")

        # Calling AI to generate the report
        if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_API_KEY_HERE":
            generate_ai_report(target_symbol, latest)
        else:
            print("\n⚠️ Please insert your Gemini API Key in the script to see the AI report.")
