import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from transformers import pipeline

# --- AYARLAR ---
# Render panelinden girilecekse os.getenv kullanacağız, 
# ama şimdilik direkt buraya da yazabilirsin:
TELEGRAM_TOKEN = "BURAYA_TOKEN_YAZ"
TELEGRAM_CHAT_ID = "BURAYA_CHAT_ID_YAZ"
API_KEY = "BTCTURK_API_KEY"
API_SECRET = "BTCTURK_API_SECRET"

# FinBERT AI Modeli (Haber analizi için hazırda bekler)
sentiment_analyzer = pipeline("sentiment-analysis", model="ProsusAI/finbert")

# Borsa Bağlantısı
exchange = ccxt.btcturk({'apiKey': API_KEY, 'secret': API_SECRET})

# --- STRATEJİ PARAMETRELERİ ---
TIMEFRAME = '5m'         # 5 dakikalık hızlı scalping
BAKIYE_ORANI = 0.90      # Bakiyenin %90'ını kullan (%10 komisyon için kalır)
SABIT_STOP = 0.015       # %1.5 Zarar Kes
TAKIP_TETIK = 0.02       # %2 Kar Takibi (Zirveden %2 düşerse sat)

# HAFIZA (Pozisyon takibi için)
bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}
son_rapor_vakti = time.time()

def tg_mesaj(msg):
    """Telegram üzerinden bildirim gönderir."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print(f"Telegram hatası: {e}")

def en_hareketli_20_coin():
    """Borsada hacmi en yüksek 20 USDT çiftini bulur."""
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [t for t in tickers if '/USDT' in t]
        # Hacme göre büyükten küçüğe sırala
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['baseVolume'], reverse=True)
        return sorted_pairs[:20]
    except:
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT']

def run_bot():
    global bellek, son_rapor_vakti
    tg_mesaj("🚀 Robot 7/24 Modunda Başlatıldı!\nEn hareketli 20 coin izleniyor.")
    
    while True:
        try:
            # 1 SAATLİK HAYAT SİNYALİ
            if time.time() - son_rapor_vakti > 3600:
                bal = exchange.fetch_balance()['total']['USDT']
                tg_mesaj(f"🔔 SİSTEM AKTİF\nBakiye: {bal:.2f} USDT\nTarama devam ediyor...")
                son_rapor_vakti = time.time()

            if not bellek["aktif"]:
                # ALIM FIRSATI ARA
                watchlist = en_hareketli_20_coin()
                for s in watchlist:
                    bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                    rsi = ta.rsi(df['c'], length=7).iloc[-1]
                    
                    if rsi < 30: # Aşırı satış bölgesi (Alım fırsatı)
                        ticker = exchange.fetch_ticker(s)
                        price = ticker['last']
                        
                        # Bakiye Kontrolü
                        balance = exchange.fetch_balance()
                        usdt_bal = balance['total']['USDT'] * BAKIYE_ORANI
                        
                        # Miktar ve Hassasiyet Ayarı
                        market = exchange.market(s)
                        prec = market['precision']['amount']
                        qty = math.floor(usdt_bal / price * (10**prec)) / (10**prec)
                        
                        if qty > 0:
                            # exchange.create_market_buy_order(s, qty) # GERÇEK İŞLEM İÇİN AÇ
                            bellek = {"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price}
                            tg_mesaj(f"✅ ALIM YAPILDI\nCoin: {s}\nFiyat: {price}\nRSI: {rsi:.2f}\nMiktar: {qty}")
                            break
            
            else:
                # SATIŞ VE TAKİPLİ STOP KONTROLÜ
                curr_ticker = exchange.fetch_ticker(bellek["symbol"])
                curr_price = curr_ticker['last']
                
                if curr_price > bellek["zirve"]:
                    bellek["zirve"] = curr_price
                
                # Dinamik Stop Seviyesi
                stop_limit = max(bellek["ort"] * (1 - SABIT_STOP), bellek["zirve"] * (1 - TAKIP_TETIK))
                
                if curr_price <= stop_limit:
                    kar_zarar = ((curr_price - bellek["ort"]) / bellek["ort"]) * 100
                    # exchange.create_market_sell_order(bellek["symbol"], bellek["adet"]) # GERÇEK SATIŞ
                    
                    emoji = "💰" if kar_zarar > 0 else "📉"
                    tg_mesaj(f"{emoji} SATIŞ YAPILDI\nCoin: {bellek['symbol']}\nFiyat: {curr_price}\nKar/Zarar: %{kar_zarar:.2f}")
                    
                    # Belleği Sıfırla
                    bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}

            time.sleep(20) # 20 saniyede bir döngü
            
        except Exception as e:
            print(f"Hata oluştu: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_bot()
