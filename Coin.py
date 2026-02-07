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

exchange = ccxt.btcturk({'apiKey': API_KEY, 'secret': API_SECRET})

# --- STRATEJİ PARAMETRELERİ ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90
SABIT_STOP = 0.015       # %1.5 Zarar Kes
TAKIP_TETIK = 0.02       # %2 Kar Takibi
RSI_ESIK = 40            # Piyasa toparlandığı için eşiği 40 yaptık (35-40 aralığını kapsar)

bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0, "son_tarama": []}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: print("Telegram hatası.")

def telegram_dinle():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            r = requests.get(url, timeout=10).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                text = update.get("message", {}).get("text", "")
                
                if text == "/rapor":
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    t_list = "\n".join(bellek["son_tarama"][-15:])
                    tg_mesaj(f"📊 GÜNCEL RAPOR (Eşik: {RSI_ESIK})\n💰 Bakiye: {bal:.2f} USDT\n🔍 Taramalar:\n{t_list}")
                elif text == "/durum":
                    if bellek["aktif"]:
                        curr = exchange.fetch_ticker(bellek["symbol"])['last']
                        kz = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                        tg_mesaj(f"🛰 İŞLEM: {bellek['symbol']}\n📈 Kâr/Zarar: %{kz:.2f}\n📍 Giriş: {bellek['ort']}")
                    else:
                        tg_mesaj("Boşta, fırsat kolluyor.")
        except: time.sleep(5)

def en_hareketli_15_coin():
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [t for t in tickers if '/USDT' in t]
        return sorted(usdt_pairs, key=lambda x: tickers[x]['baseVolume'] or 0, reverse=True)[:15]
    except: return ['BTC/USDT', 'ETH/USDT']

def run_bot():
    global bellek
    tg_mesaj(f"🚀 Robot RSI {RSI_ESIK} (Toparlanma Modu) Başladı!")
    
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
                    price = exchange.fetch_ticker(s)['last']
                    bal = exchange.fetch_balance()['total'].get('USDT', 0) * BAKIYE_ORANI
                    if bal > 10:
                        market = exchange.market(s)
                        prec = market['precision']['amount']
                        qty = math.floor(bal / price * (10**prec)) / (10**prec)
                        exchange.create_market_buy_order(s, qty)
                        bellek = {"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price, "son_tarama": yeni_tarama}
                        tg_mesaj(f"✅ ALIM YAPILDI: {s}\nFiyat: {price}\nRSI: {rsi:.1f}")
                        break
            bellek["son_tarama"] = yeni_tarama
            if bellek["aktif"]:
                curr_price = exchange.fetch_ticker(bellek["symbol"])['last']
                if curr_price > bellek["zirve"]: bellek["zirve"] = curr_price
                stop_limit = max(bellek["ort"] * (1 - SABIT_STOP), bellek["zirve"] * (1 - TAKIP_TETIK))
                if curr_price <= stop_limit:
                    kar_zarar = ((curr_price - bellek["ort"]) / bellek["ort"]) * 100
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    tg_mesaj(f"💰 SATIŞ YAPILDI: {bellek['symbol']}\nK/Z: %{kar_zarar:.2f}")
                    bellek["aktif"] = False
            time.sleep(30)
        except Exception as e:
            print(f"Hata: {e}"); time.sleep(30)

if __name__ == "__main__":
    Thread(target=telegram_dinle).start()
    run_bot()


