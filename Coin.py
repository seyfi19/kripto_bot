import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from threading import Thread
from datetime import datetime
from flask import Flask

# --- WEB SUNUCUSU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Aktif: Odaklanmış 5 Coin & Hassas Takip Stop!"

def run_web():
    app.run(host='0.0.0.0', port=10000)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_KEY = os.getenv('BTCTURK_API_KEY')
API_SECRET = os.getenv('BTCTURK_API_SECRET')

exchange = ccxt.btcturk({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True
})

# --- STRATEJİ AYARLARI ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90
SABIT_STOP = 0.015    # %1.5 Sabit Zarar Durdur
TAKIP_TETIK = 0.007   # %0.7 (Hassas takip stop tetikleyicisi)

bellek = {
    "aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0, 
    "son_tarama": [], "islem_gecmisi": [], "gun_tarihi": datetime.now().strftime("%d/%m/%Y")
}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except: pass

def telegram_dinle():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            r = requests.get(url, timeout=15).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                
                if text == "/rapor":
                    t_list = "\n".join(bellek["son_tarama"]) if bellek["son_tarama"] else "Tarama yapılıyor..."
                    tg_mesaj(f"⚡️ ODAKLI TREND RAPORU (5 COIN)\n\n{t_list}")
                
                elif text == "/durum":
                    if bellek["aktif"]:
                        curr = exchange.fetch_ticker(bellek["symbol"])['last']
                        kz = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                        tg_mesaj(f"🛰 İŞLEMDE: {bellek['symbol']}\n📍 Giriş: {bellek['ort']}\n💰 Güncel: {curr}\n📈 K/Z: %{kz:.2f}")
                    else: tg_mesaj("🤖 Boşta, 5 ana coinde sinyal bekliyor.")

                elif text == "/bakiye":
                    balance = exchange.fetch_balance()
                    msg = "💰 GÜNCEL BAKİYE\n"
                    for coin, value in balance['total'].items():
                        if value > 0: msg += f"🔹 {coin}: {value:.4f}\n"
                    tg_mesaj(msg)
        except: time.sleep(5)

def run_bot():
    tg_mesaj("🚀 Hassas Takip Stop & 5 Coin Modu Aktif!")
    while True:
        try:
            if bellek["aktif"]:
                curr = exchange.fetch_ticker(bellek["symbol"])['last']
                if curr > bellek["zirve"]: bellek["zirve"] = curr
                
                # Hassas Takip Stop Mantığı: Zirveden %0.7 aşağı düşerse sat
                stop = max(bellek["ort"] * (1-SABIT_STOP), bellek["zirve"] * (1-TAKIP_TETIK))
                
                if curr <= stop:
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    kz = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                    bellek["islem_gecmisi"].append({"symbol": bellek["symbol"], "kz": kz})
                    tg_mesaj(f"📉 KAR ALINDI/STOPLANDI: {bellek['symbol']}\nK/Z: %{kz:.2f}")
                    bellek["aktif"] = False; bellek["symbol"] = None
                time.sleep(30); continue

            # Değişken ama odaklanmış tarama (En hacimli 5 coin)
            tickers = exchange.fetch_tickers()
            watchlist = sorted([t for t in tickers if '/USDT' in t], key=lambda x: tickers[x]['baseVolume'] or 0, reverse=True)[:5]
            yeni_tarama = []

            for s in watchlist:
                try:
                    ticker = tickers[s]; price = ticker['last']
                    bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                    
                    ema3 = ta.ema(df['c'], length=3).iloc[-1]
                    ema8 = ta.ema(df['c'], length=8).iloc[-1]
                    
                    yukselis = ema3 > ema8
                    yeni_tarama.append(f"{s}: {price} | Trend: {'✅' if yukselis else '❌'}")

                    if yukselis:
                        bal = exchange.fetch_balance()['total'].get('USDT', 0) * BAKIYE_ORANI
                        if bal > 10:
                            market = exchange.market(s); prec = market['precision']['amount']
                            qty = math.floor(bal / price * (10**prec)) / (10**prec)
                            exchange.create_market_buy_order(s, qty)
                            bellek.update({"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price})
                            tg_mesaj(f"✅ ALINDI: {s}\nFiyat: {price}")
                            break
                except: continue
            
            bellek["son_tarama"] = yeni_tarama
            time.sleep(30)
        except Exception as e:
            time.sleep(60)

if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=telegram_dinle, daemon=True).start()
    run_bot()
