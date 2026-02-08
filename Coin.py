import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from threading import Thread
from flask import Flask

# --- WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "🤖 BOT AKTIF"

def run_web():
    # Render portu için 10000 varsayılanını kullan
    app.run(host='0.0.0.0', port=10000)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_KEY = os.getenv('BTCTURK_API_KEY')
API_SECRET = os.getenv('BTCTURK_API_SECRET')

# Borsa Bağlantısı - Zaman hatasını önlemek için 'adjustForTimeDifference' ekli
exchange = ccxt.btcturk({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True}
})

bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except: pass

def kesin_bakiye():
    """Bakiye çekmeyi zorlayan fonksiyon"""
    try:
        bal = exchange.fetch_balance()
        # Btcturk'ün farklı formatlarını tara
        usdt = bal.get('USDT', {}).get('total', 0)
        if usdt == 0 and 'total' in bal:
            usdt = bal['total'].get('USDT', 0)
        return float(usdt)
    except Exception as e:
        return f"🚨 API Hatası: {str(e)[:30]}"

def telegram_dinle():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            r = requests.get(url, timeout=15).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                txt = update.get("message", {}).get("text", "")
                if txt == "/bakiye":
                    b = kesin_bakiye()
                    tg_mesaj(f"💰 Cüzdan: {b} USDT")
                elif txt == "/durum":
                    tg_mesaj("🤖 Bot Çalışıyor, Dalga Bekliyor..." if not bellek["aktif"] else f"🛰 İşlemde: {bellek['symbol']}")
        except: time.sleep(5)

def run_bot():
    tg_mesaj("🛡️ Dalga Avcısı V5 Başlatıldı! /bakiye yazarak test et.")
    while True:
        try:
            if bellek["aktif"]:
                # Stop Kontrolü (Hızlı EMA 3/7)
                ticker = exchange.fetch_ticker(bellek["symbol"])
                curr = ticker['last']
                if curr > bellek["zirve"]: bellek["zirve"] = curr
                stop = max(bellek["ort"] * 0.985, bellek["zirve"] * 0.993)
                if curr <= stop:
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    tg_mesaj(f"🛑 SATILDI: {bellek['symbol']} | Kar/Zarar Kontrol Et.")
                    bellek["aktif"] = False
                time.sleep(15); continue

            # En Oynak 5 Coini Bul
            tickers = exchange.fetch_tickers()
            v_list = []
            for s, t in tickers.items():
                if '/USDT' in s and t['high'] and t['low']:
                    v_list.append({'s': s, 'd': (t['high'] - t['low']) / t['low']})
            
            top_5 = [x['s'] for x in sorted(v_list, key=lambda x: x['d'], reverse=True)[:5]]

            for s in top_5:
                bars = exchange.fetch_ohlcv(s, timeframe='5m', limit=20)
                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                e3 = ta.ema(df['c'], length=3).iloc[-1]
                e7 = ta.ema(df['c'], length=7).iloc[-1]

                if e3 > e7:
                    u_bal = kesin_bakiye()
                    if isinstance(u_bal, float) and u_bal > 10:
                        p = tickers[s]['last']
                        mkt = exchange.market(s)
                        amt = math.floor((u_bal * 0.95 / p) * (10**mkt['precision']['amount'])) / (10**mkt['precision']['amount'])
                        exchange.create_market_buy_order(s, amt)
                        bellek.update({"aktif": True, "symbol": s, "ort": p, "adet": amt, "zirve": p})
                        tg_mesaj(f"🚀 ALINDI: {s}\nFiyat: {p}")
                        break
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=telegram_dinle, daemon=True).start()
    run_bot()
