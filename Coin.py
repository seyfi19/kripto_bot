def run_bot():
    tg_mesaj("🌊 Dalga Avcısı Bot Başlatıldı! (EMA 3/7 + Volatility)")
    while True:
        try:
            # --- BÖLÜM 1: SATIŞ KONTROLÜ (EĞER İŞLEMDEYSEK) ---
            if bellek["aktif"]:
                # Güncel fiyatı borsadan çek
                curr = exchange.fetch_ticker(bellek["symbol"])['last']
                
                # Zirve fiyatı güncelle (Trailing Stop için)
                if curr > bellek["zirve"]: 
                    bellek["zirve"] = curr
                
                # AKILLI STOP HESABI: 
                # 1. Sabit Stop: Giriş fiyatının %1.5 altı
                # 2. Takip Stop: Zirve fiyatının %0.7 altı
                stop_fiyat = max(bellek["ort"] * (1 - SABIT_STOP), bellek["zirve"] * (1 - TAKIP_TETIK))
                
                # Eğer fiyat stop seviyesinin altına indiyse SAT!
                if curr <= stop_fiyat:
                    if akilli_emir_sat(bellek["symbol"], bellek["adet"]):
                        bellek["aktif"] = False # Botu boşa çıkar, yeni av ara
                time.sleep(15); continue

            # --- BÖLÜM 2: ALIM TARAMASI (BOŞTAYSAK) ---
            # 1. Piyasadaki en oynak (dalgalı) 5 coini bul
            tickers = exchange.fetch_tickers()
            volatility_list = []
            for s, t in tickers.items():
                if '/USDT' in s and t['high'] and t['low']:
                    diff = (t['high'] - t['low']) / t['low'] # 24 saatlik oynaklık
                    volatility_list.append({'symbol': s, 'diff': diff})

            # En çok dalgalanan ilk 5'i seç
            watchlist = [x['symbol'] for x in sorted(volatility_list, key=lambda x: x['diff'], reverse=True)[:5]]
            
            # 2. Seçilen 5 coinde EMA 3/7 kesişimi ara
            for s in watchlist:
                try:
                    bars = exchange.fetch_ohlcv(s, timeframe=TIMEFRAME, limit=30)
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                    ema3 = ta.ema(df['c'], length=3).iloc[-1]
                    ema7 = ta.ema(df['c'], length=7).iloc[-1]
                    
                    # ALIM ŞARTI: Hızlı EMA (3), Yavaş EMA'yı (7) yukarı kestiyse
                    if ema3 > ema7:
                        usdt = guvenli_bakiye() # Cüzdanı kontrol et
                        if usdt > 10:
                            # Akıllı emir (Market/Limit) ile alıma dal!
                            sonuc = akilli_emir_al(s, usdt * BAKIYE_ORANI)
                            if sonuc:
                                # Bilgileri belleğe kaydet (Takip başlasın)
                                bellek.update({
                                    "aktif": True, "symbol": s, "ort": sonuc['price'], 
                                    "adet": sonuc['amount'], "zirve": sonuc['price']
                                })
                                break # Tek seferde tek işlem kuralı
                except: continue
            
            time.sleep(30) # Borsayı yormamak için kısa bekleme
        except: 
            time.sleep(10) # Hata durumunda dinlen ve devam et
