import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_KEY = os.getenv('BTCTURK_API_KEY')
API_SECRET = os.getenv('BTCTURK_API_SECRET')

# Borsa Bağlantısı
exchange = ccxt.btcturk({'apiKey': API_KEY, 'secret': API_SECRET})

# --- STRATEJİ PARAMETRELERİ ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90      # %10 komisyon ve küsurat payı bırakır
SABIT_STOP = 0.015       # %1.5 Zarar Kes
TAKIP_TETIK = 0.02       # %2 Kar Takibi

bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}
son_rapor_vakti = time.time()

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: print("Telegram hatası!")

def en_hareketli_20_coin():
    try:
        tickers = exchange.fetch_tickers()
        # USDT paritelerini tara (Senin bakiyen Dolar olduğu için)
        usdt_pairs = [t for t in tickers if '/USDT' in t]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['baseVolume'] if tickers[x]['baseVolume'] else 0, reverse=True)
        return sorted_pairs[:15]
    except Exception as e: 
        print(f"Piyasa tarama hatası: {e}")
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

def run_bot():
    global bellek, son_rapor_vakti
    tg_mesaj("🎯 Robot HAFİF MODDA (USDT) Başlatıldı!\n7/24 Takip aktif.")
    
    while True:
        try:
            # 1 Saatlik Durum Raporu
            if time.time() - son_rapor_vakti > 3600:
                bal = exchange.fetch_balance()
                usdt_bal = bal['total'].get('USDT', 0)
                tg_mesaj(f"🔔 SİSTEM AKTİF\nGüncel Bakiye: {usdt_bal:.2f} USDT")
                son_rapor_vakti = time.time()

            if not bellek["aktif"]:
                watchlist = en_hareketli_20_coin()
                for s in watchlist:
                    bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                    rsi = ta.rsi(df['c'], length=14).iloc[-1]
                    
                    if rsi < 30: # RSI 30 Altı (Aşırı Satım)
                        ticker = exchange.fetch_ticker(s)
                        price = ticker['last']
                        
                        # USDT bakiyesini kontrol et
                        balance = exchange.fetch_balance()['total'].get('USDT', 0) * BAKIYE_ORANI
                        
                        if balance > 10: # Minimum 10 USDT ile işlem başlasın
                            market = exchange.market(s)
                            prec = market['precision']['amount']
                            qty = math.floor(balance / price * (10**prec)) / (10**prec)
                            
                            # GERÇEK ALIM EMRİ
                            exchange.create_market_buy_order(s, qty) 
                            
                            bellek = {"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price}
                            tg_mesaj(f"✅ ALIM YAPILDI\nCoin: {s}\nFiyat: {price}\nMiktar: {qty}")
                            break
            
            else:
                curr_price = exchange.fetch_ticker(bellek["symbol"])['last']
                if curr_price > bellek["zirve"]: bellek["zirve"] = curr_price
                
                stop_limit = max(bellek["ort"] * (1 - SABIT_STOP), bellek["zirve"] * (1 - TAKIP_TETIK))
                
                if curr_price <= stop_limit:
                    kar_zarar = ((curr_price - bellek["ort"]) / bellek["ort"]) * 100
                    
                    # GERÇEK SATIŞ EMRİ
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    
                    emoji = "💰" if kar_zarar > 0 else "📉"
                    tg_mesaj(f"{emoji} SATIŞ YAPILDI\nCoin: {bellek['symbol']}\nKar/Zarar: %{kar_zarar:.2f}")
                    bellek = {"aktif": False, "symbol": None, "ort": 0, "adet": 0, "zirve": 0}

            time.sleep(30) # 30 saniyede bir kontrol et
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()


