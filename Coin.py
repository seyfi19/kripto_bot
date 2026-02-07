import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from threading import Thread

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_KEY = os.getenv('BTCTURK_API_KEY')
API_SECRET = os.getenv('BTCTURK_API_SECRET')

# BtcTurk Bağlantısı
exchange = ccxt.btcturk({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True
})

# --- STRATEJİ ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90
SABIT_STOP = 0.015
TAKIP_TETIK = 0.02
RSI_ESIK = 40

bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0, "son_tarama": []}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

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
                    tg_mesaj(f"📊 RSI RAPORU (Eşik: {RSI_ESIK})\n\n{t_list}")
                elif text == "/durum":
                    if bellek["aktif"]:
                        tg_mesaj(f"🛰 İŞLEMDE: {bellek['symbol']}\n📍 Giriş: {bellek['ort']}")
                    else:
                        tg_mesaj("🤖 Boşta, fırsat kolluyor.")
        except:
            time.sleep(5)

def en_hareketli_15_coin():
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [t for t in tickers if '/USDT' in t]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['baseVolume'] or 0, reverse=True)
        return sorted_pairs[:15]
    except:
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT', 'XRP/USDT']

def run_bot():
    print("SİSTEM: Robot RSI 40 modunda başladı.")
    tg_mesaj("🚀 Robot RSI 40 Modunda Aktif!")
    while True:
        try:
            watchlist = en_hareketli_15_coin()
            yeni_tarama = []
            for s in watchlist:
                bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                rsi = ta.rsi(df['c'], length=14).iloc[-1]
                yeni_tarama.append(f"{s}: {rsi:.1f}")
                
                if not bellek["aktif"] and rsi < RSI_ESIK:
                    ticker = exchange.fetch_ticker(s)
                    price = ticker['last']
                    bal = exchange.fetch_balance()['total'].get('USDT', 0) * BAKIYE_ORANI
                    if bal > 10:
                        market = exchange.market(s)
                        prec = market['precision']['amount']
                        qty = math.floor(bal / price * (10**prec)) / (10**prec)
                        exchange.create_market_buy_order(s, qty)
                        bellek.update({"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price})
                        tg_mesaj(f"✅ ALINDI: {s}\nFiyat: {price}")
                        break
            bellek["son_tarama"] = yeni_tarama
            
            if bellek["aktif"]:
                curr = exchange.fetch_ticker(bellek["symbol"])['last']
                if curr > bellek["zirve"]: bellek["zirve"] = curr
                stop = max(bellek["ort"] * (1-SABIT_STOP), bellek["zirve"] * (1-TAKIP_TETIK))
                if curr <= stop:
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    tg_mesaj(f"📉 SATILDI: {bellek['symbol']}")
                    bellek["aktif"] = False
            time.sleep(30)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(30)

if __name__ == "__main__":
    Thread(target=telegram_dinle, daemon=True).start()
    run_bot()
