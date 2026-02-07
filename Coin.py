import ccxt
import pandas as pd
import pandas_ta as ta
import time
import math
import requests
import os
from threading import Thread
from datetime import datetime

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

# --- STRATEJİ ---
TIMEFRAME = '5m'
BAKIYE_ORANI = 0.90
SABIT_STOP = 0.015
TAKIP_TETIK = 0.018
RSI_ESIK = 42

# --- HAFIZA ---
bellek = {
    "aktif": False, 
    "symbol": None, 
    "ort": 0, 
    "adet": 0, 
    "zirve": 0, 
    "son_tarama": [],
    "islem_gecmisi": [], # Günlük işlemler burada tutulur
    "gun_tarihi": datetime.now().strftime("%d/%m/%Y")
}

def tg_mesaj(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        print("SİSTEM: Telegram mesajı gönderilemedi.")

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
                    tg_mesaj(f"📊 RSI & POTANSİYEL RAPORU\n\n{t_list}")
                
                elif text == "/durum":
                    if bellek["aktif"]:
                        curr = exchange.fetch_ticker(bellek["symbol"])['last']
                        kz = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                        tg_mesaj(f"🛰 İŞLEMDE: {bellek['symbol']}\n📍 Giriş: {bellek['ort']}\n💰 Güncel: {curr}\n📈 K/Z: %{kz:.2f}\n🔝 Zirve: {bellek['zirve']}")
                    else:
                        tg_mesaj("🤖 Boşta, fırsat kolluyor.")

                elif text == "/gunsonu":
                    if not bellek["islem_gecmisi"]:
                        tg_mesaj(f"📅 {bellek['gun_tarihi']}\nHenüz tamamlanmış bir işlem yok.")
                    else:
                        toplam_kz = sum(x['kz'] for x in bellek["islem_gecmisi"])
                        rapor = f"📅 GÜN SONU RAPORU ({bellek['gun_tarihi']})\n"
                        rapor += "--------------------------\n"
                        for islem in bellek["islem_gecmisi"]:
                            emoji = "✅" if islem['kz'] > 0 else "❌"
                            rapor += f"{emoji} {islem['symbol']}: %{islem['kz']:.2f}\n"
                        rapor += "--------------------------\n"
                        rapor += f"💰 TOPLAM NET: %{toplam_kz:.2f}"
                        tg_mesaj(rapor)
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
    print("SİSTEM: Robot Gün Sonu Raporu özelliğiyle başladı.")
    tg_mesaj("🚀 Robot Gün Sonu + Kâr/Zarar Takibiyle Aktif!")
    
    while True:
        try:
            # Yeni güne geçildiyse geçmişi temizle
            bugun = datetime.now().strftime("%d/%m/%Y")
            if bugun != bellek["gun_tarihi"]:
                bellek["islem_gecmisi"] = []
                bellek["gun_tarihi"] = bugun

            # İŞLEMDEYSE
            if bellek["aktif"]:
                curr = exchange.fetch_ticker(bellek["symbol"])['last']
                if curr > bellek["zirve"]: bellek["zirve"] = curr
                stop = max(bellek["ort"] * (1-SABIT_STOP), bellek["zirve"] * (1-TAKIP_TETIK))
                
                if curr <= stop:
                    exchange.create_market_sell_order(bellek["symbol"], bellek["adet"])
                    kar_zarar = ((curr - bellek["ort"]) / bellek["ort"]) * 100
                    
                    # İşlemi geçmişe kaydet
                    bellek["islem_gecmisi"].append({"symbol": bellek["symbol"], "kz": kar_zarar})
                    
                    tg_mesaj(f"📉 SATILDI: {bellek['symbol']}\nKâr/Zarar: %{kar_zarar:.2f}")
                    bellek["aktif"] = False
                    bellek["symbol"] = None
                
                time.sleep(30)
                continue

            # BOŞTAYSA TARAMA
            watchlist = en_hareketli_15_coin()
            yeni_tarama = []
            
            for s in watchlist:
                try:
                    ticker = exchange.fetch_ticker(s)
                    price = ticker['last']
                    # Günlük değişim yüzdesi (Borsa verisinden çekilir)
                    degisim = ticker.get('percentage', 0)
                    
                    bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=50)
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                    rsi = ta.rsi(df['c'], length=14).iloc[-1]
                    
                    # Rapor formatı: Coin | RSI | Günlük Değişim %
                    yeni_tarama.append(f"{s}: {price} | RSI: {rsi:.1f} | 24h: %{degisim:.2f}")
                    
                    if rsi < RSI_ESIK:
                        bal = exchange.fetch_balance()['total'].get('USDT', 0) * BAKIYE_ORANI
                        if bal > 10:
                            market = exchange.market(s)
                            prec = market['precision']['amount']
                            qty = math.floor(bal / price * (10**prec)) / (10**prec)
                            
                            exchange.create_market_buy_order(s, qty)
                            bellek.update({"aktif": True, "symbol": s, "ort": price, "adet": qty, "zirve": price})
                            tg_mesaj(f"✅ ALINDI: {s}\nFiyat: {price}\nRSI: {rsi:.1f}")
                            break
                except:
                    continue
            
            bellek["son_tarama"] = yeni_tarama
            time.sleep(30)

        except Exception as e:
            tg_mesaj(f"🚨 KRİTİK HATA: {str(e)[:100]}")
            time.sleep(60)

if __name__ == "__main__":
    Thread(target=telegram_dinle, daemon=True).start()
    run_bot()
