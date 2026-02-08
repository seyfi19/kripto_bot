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
def home(): return "🤖 BOT DURUMU: AKTIF - ANALIZ YAPILIYOR"

def run_web():
    app.run(host='0.0.0.0', port=10000)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_KEY = os.getenv('BTCTURK_API_KEY')
API_SECRET = os.getenv('BTCTURK_API_SECRET')

# Borsa Bağlantısı - En Agresif Zaman Ayarı ile
exchange = ccxt.btcturk({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True, # Zaman kaymasını otomatik düzelt
        'recvWindow': 10000 # İstek süresini 10 saniyeye yay (hata payı bırakmaz)
    }
})

bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except: pass

def kesin_bakiye():
    """Bakiye çekmeyi 3 farklı yöntemle zorlar."""
    try:
        # Zamanı tekrar senkronize et
        exchange.load_markets()
        bal = exchange.fetch_balance()
        
        usdt = 0
        # Btcturk'ün kullandığı 3 farklı formatı da kontrol et
        if 'USDT' in bal: usdt = bal['USDT'].get('total', 0)
        if usdt == 0 and 'total' in bal: usdt = bal['total'].get('USDT', 0)
        if usdt == 0 and 'info' in bal:
            for item in bal['info']:
                if item.get('asset') == 'USDT': usdt = float(item.get('total', 0))
        
        return float(usdt)
    except Exception as e:
        # Hatanın ne olduğunu Telegram'a sızdır
        error_msg = str(e).lower()
        if "invalid" in error_msg: return "❌ HATA: Gecersiz API Anahtari"
        if "timestamp" in error_msg or "time" in error_msg: return "⚠️ HATA: Zaman Senkronizasyonu"
        return f"🚨 HATA: {str(e)[:40]}"

def telegram_dinle():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            r = requests.get(url, timeout=15).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                msg_text = update.get("message", {}).get("text", "")
                
                if msg_text == "/bakiye":
                    b = kesin_bakiye()
                    tg_mesaj(f"💰 Cüzdan: {b} USDT")
                elif msg_text == "/durum":
                    if bellek["aktif"]: tg_mesaj(f"🛰 Islem: {bellek['symbol']}\nFiyat: {bellek['ort']}")
                    else: tg_mesaj("🤖 Pusu kuruldu, en oynak coinler taraniyor...")
        except: time.sleep(5)

def run_bot():
    tg_mesaj("⚔️ Komando Modu Devrede. Bakiyeni gormek icin /bakiye yaz.")
    while True:
        try:
            if bellek["aktif"]:
                ticker = exchange.fetch_ticker(bellek["symbol"])
                curr = ticker['last']
                if curr > bellek["zirve"]: bellek["zirve"] = curr
                stop = max(bellek["ort"] * 0.985, bellek["zirve"] * 0.993) # %1.5 Sabit, %0.7 Takip
                if curr <= stop:
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    tg_mesaj(f"🛑 SATILDI: {bellek['symbol']}")
                    bellek["aktif"] = False
                time.sleep(20); continue

            # Volatility (Oynaklik) Taraması
            all_tickers = exchange.fetch_tickers()
            v_list = []
            for s, t in all_tickers.items():
                if '/USDT' in s and t['high'] and t['low']:
                    diff = (t['high'] - t['low']) / t['low']
                    v_list.append({'s': s, 'd': diff})
            
            top_5 = [x['s'] for x in sorted(v_list, key=lambda x: x['d'], reverse=True)[:5]]

            for s in top_5:
                bars = exchange.fetch_ohlcv(s, timeframe='5m', limit=30)
                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                e3 = ta.ema(df['c'], length=3).iloc[-1]
                e7 = ta.ema(df['c'], length=7).iloc[-1]

                if e3 > e7:
                    u_bal = kesin_bakiye()
                    if isinstance(u_bal, float) and u_bal > 10:
                        p = all_tickers[s]['last']
                        mkt = exchange.market(s)
                        # Miktar hassasiyetini ayarla
                        amt = math.floor((u_bal * 0.95 / p) * (10**mkt['precision']['amount'])) / (10**mkt['precision']['amount'])
                        exchange.create_market_buy_order(s, amt)
                        bellek.update({"aktif": True, "symbol": s, "ort": p, "adet": amt, "zirve": p})
                        tg_mesaj(f"🚀 ALINDI: {s}\nFiyat: {p}")
                        break
            time.sleep(30)
        except: time.sleep(15)

if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=telegram_dinle, daemon=True).start()
    run_bot()
