import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from threading import Thread

# --- AYARLAR (Render Environment Variables'dan çeker) ---
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

# --- STRATEJİ PARAMETRELERİ ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90
SABIT_STOP = 0.015       # %1.5 Zarar Kes
TAKIP_TETIK = 0.02       # %2 Kar Takibi (Trailing)
RSI_ESIK = 40            # Alım için RSI 40'ın altı

# Global Bellek (Botun o anki durumunu tutar)
bellek = {
    "aktif": False, 
    "symbol": None, 
    "ort": 0, 
    "adet": 0, 
    "zirve": 0, 
    "son_tarama": []
}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        print("Telegram iletisi gönderilemedi.")

# --- TELEGRAM ETKİLEŞİM (Ayrı bir kolda çalışır) ---
def telegram_dinle():
    offset = 0
    print("SİSTEM: Telegram dinleyici başlatıldı.")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            r = requests.get(url, timeout=15).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                
                if text == "/rapor":
                    # Hafızadaki son tarama sonuçlarını gönderir (Hızlı yanıt)
                    t_list = "\n".join(bellek["son_tarama"][-15:]) if bellek["son_tarama"] else "Henüz tarama yapılmadı."
                    tg_mesaj(f"📊 GÜNCEL RSI RAPORU (Eşik: {RSI_ESIK})\n\n{t_list}")
                
                elif text == "/durum":
                    if bellek["aktif"]:
                        curr = exchange.fetch_ticker(bellek["symbol"])['last']
                        kz = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                        tg_mesaj(f"🛰 İŞLEM: {bellek['symbol']}\n📈 Kâr/Zarar: %{kz:.2f}\n📍 Giriş: {bellek['ort']}\n🔝 Zirve: {bellek['zirve']}")
                    else:
                        tg_mesaj("🤖 Bot Çalışıyor: Şu an boşta, fırsat kolluyor.")
        except Exception as e:
            print(f"Telegram Hatası: {e}")
            time.sleep(5)

def en_hareketli_15_coin():
    try:
        tickers = exchange.fetch_tickers()
        # Sadece USDT paritelerini hacme göre sırala
        usdt_pairs = [t for t in tickers if '/USDT' in t]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['baseVolume'] or 0, reverse=True)
        return sorted_pairs[:15]
    except:
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT', 'XRP/USDT']

def run_bot():
    global bellek
    print(f"SİSTEM: Robot RSI {RSI_ESIK} modunda taramaya başlıyor...")
    tg_mesaj(f"🚀 Robot RSI {RSI_ESIK} Modunda Aktif Edildi!\n\nKomutlar:\n/rapor - RSI listesini gör\n/durum - İşlem durumunu gör")
    
    while True:
        try:
            watchlist = en_hareketli_15_coin()
            yeni_tarama = []
            
            for s in watchlist:
                # RSI Hesaplama
                bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                rsi = ta.rsi(df['c'], length=14).iloc[-1]
                yeni_tarama.append(f"{s}: {rsi:.1f}")
                
                # ALIM KOŞULU
                if not bellek["aktif"] and rsi < RSI_ESIK:
                    ticker = exchange.fetch_ticker(s)
                    price
