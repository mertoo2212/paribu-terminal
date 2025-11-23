import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Borsa Terminali",
    page_icon="💎",
    layout="wide"
)

# --- SABİTLER ---
YENILEME_HIZI = 15  # Saniye
LIMIT_1S = 240      # 1 Saat için gereken veri sayısı (15sn x 240 = 60dk)
LIMIT_4S = 960      # 4 Saat için gereken veri sayısı

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.05rem; }
    div[data-testid="stMetric"] {
        background-color: #1c1f26;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #333;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HAFIZA BAŞLATMA ---
if 'hafiza' not in st.session_state:
    st.session_state.hafiza = {}
if 'son_guncelleme' not in st.session_state:
    st.session_state.son_guncelleme = time.time()

# --- FORMATLAMA FONKSİYONU ---
def kesin_format(fiyat):
    if fiyat is None or fiyat == 0:
        return "-" 
    
    if fiyat < 1:
        return "{:.8f} ₺".format(fiyat)
    elif fiyat < 10:
        return "{:.6f} ₺".format(fiyat)
    else:
        return "{:,.2f} ₺".format(fiyat)

# --- VERİ ÇEKME ---

def get_usdt_rates():
    rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}
    try:
        url = "https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY"
        rates["Binance"] = float(requests.get(url, timeout=2).json()['price'])
    except: rates["Binance"] = 34.50

    try:
        url = "https://www.paribu.com/ticker"
        resp = requests.get(url, timeout=2).json()
        rates["Paribu"] = float(resp["USDT_TL"]['last'])
    except: rates["Paribu"] = 0

    try:
        url = "https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY"
        resp = requests.get(url, timeout=2).json()
        rates["BtcTurk"] = float(resp['data'][0]['last'])
    except: rates["BtcTurk"] = 0
    
    return rates

def get_all_market_data(usdt_rate_binance):
    # 1. PARIBU
    paribu_dict = {}
    try:
        resp = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        for sym, val in resp.items():
            if "_TL" in sym:
                coin = sym.replace("_TL", "")
                paribu_dict[coin] = {
                    "price": float(val['last']),
                    "change": float(val['percentChange'])
                }
    except: pass

    # 2. BTCTURK
    btcturk_dict = {}
    try:
        resp = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=2).json()
        for item in resp['data']:
            if item['pair'].endswith("TRY"):
                coin = item['pair'].replace("TRY", "")
                btcturk_dict[coin] = {
                    "price": float(item['last']),
                    "change": float(item['dailyPercent'])
                }
    except: pass

    # 3. BINANCE
    binance_dict = {}
    try:
        resp = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=3).json()
        for item in resp:
            if item['symbol'].endswith("USDT"):
                coin = item['symbol'].replace("USDT", "")
                tl_price = float(item['lastPrice']) * usdt_rate_binance
                binance_dict[coin] = {
                    "price": tl_price,
                    "change": float(item['priceChangePercent'])
                }
    except: pass

    return paribu_dict, btcturk_dict, binance_dict

# --- ANA PROGRAM ---

st.title("💎 Kripto Borsa Terminali")

# 1. BÖLÜM: USDT KURLARI
usdt_kurlar = get_usdt_rates()
k1, k2, k3 = st.columns(3)
k1.metric("Paribu USDT", f"{usdt_kurlar['Paribu']:.2f} ₺")
k2.metric("BtcTurk USDT", f"{usdt_kurlar['BtcTurk']:.2f} ₺")
k3.metric("Binance USDT", f"{usdt_kurlar['Binance']:.2f} ₺")

st.markdown("---")

# 2. BÖLÜM: FİLTRELER (YAN YANA)
col_borsa, col_zaman = st.columns([1, 1])

with col_borsa:
    ana_borsa = st.radio("BORSA SEÇİMİ:", 
                         ["Paribu", "BtcTurk", "Binance"], 
                         horizontal=True)

with col_zaman:
    zaman_dilimi = st.radio("ZAMAN DİLİMİ:", 
                            ["1 Saat", "4 Saat", "24 Saat"], 
                            horizontal=True)

# 3. BÖLÜM: VERİ İŞLEME VE HAFIZA
p_data, b_data, bin_data = get_all_market_data(usdt_kurlar['Binance'])

# Hedef Listeyi Belirle
if ana_borsa == "Paribu":
    hedef_coin_listesi = list(p_data.keys())
elif ana_borsa == "BtcTurk":
    hedef_coin_listesi = list(b_data.keys())
else: # Binance (Sadece TR'de olanlar)
    filtrelenmis_kume = set(p_data.keys()) | set(b_data.keys())
    hedef_coin_listesi = list(filtrelenmis_kume)

tablo_satirlari = []

for coin in hedef_coin_listesi:
    # --- FİYAT BELİRLEME ---
    base_fiyat = 0
    base_24h_degisim = 0.0

    if ana_borsa == "Paribu":
        base_fiyat = p_data.get(coin, {}).get('price', 0)
        base_24h_degisim = p_data.get(coin, {}).get('change', 0)
    elif ana_borsa == "BtcTurk":
        base_fiyat = b_data.get(coin, {}).get('price', 0)
        base_24h_degisim = b_data.get(coin, {}).get('change', 0)
    else: # Binance
        bin_veri = bin_data.get(coin, {})
        base_fiyat = bin_veri.get('price', 0)
        base_24h_degisim = bin_veri.get('change', 0)

    # --- HAFIZA KAYDI (1S ve 4S Hesaplamak İçin) ---
    # Eğer bu coin hafızada yoksa ekle
    if coin not in st.session_state.hafiza:
        st.session_state.hafiza[coin] = []
    
    # Şu anki fiyatı hafızaya ekle (0 değilse)
    if base_fiyat > 0:
        st.session_state.hafiza[coin].append(base_fiyat)
    
    # Hafızayı sınırlı tut (4 Saatlik veri kadar)
    if len(st.session_state.hafiza[coin]) > LIMIT_4S + 10:
        st.session_state.hafiza[coin].pop(0)

    gecmis = st.session_state.hafiza[coin]

    # --- DEĞİŞİM HESAPLAMA ---
    gosterilecek_degisim = 0.0
    
    if zaman_dilimi == "24 Saat":
        gosterilecek_degisim = base_24h_degisim
    
    elif zaman_dilimi == "1 Saat":
        # 1 Saat önceki veriye git
        idx = -LIMIT_1S if len(gecmis) >= LIMIT_1S else 0
        if len(gecmis) > 0:
            eski_fiyat = gecmis[idx]
            guncel = gecmis[-1]
            if eski_fiyat > 0:
                gosterilecek_degisim = ((guncel - eski_fiyat) / eski_fiyat) * 100

    elif zaman_dilimi == "4 Saat":
        # 4 Saat önceki veriye git
        idx = -LIMIT_4S if len(gecmis) >= LIMIT_4S else 0
        if len(gecmis) > 0:
            eski_fiyat = gecmis[idx]
            guncel = gecmis[-1]
            if eski_fiyat > 0:
                gosterilecek_degisim = ((guncel - eski_fiyat) / eski_fiyat) * 100

    # Diğer Borsa Fiyatları
    p_fiyat = p_data.get(coin, {}).get('price', 0)
    bt_fiyat = b_data.get(coin, {}).get('price', 0)
    bin_fiyat = bin_data.get(coin, {}).get('price', 0)

    tablo_satirlari.append({
        "Coin": coin,
        f"{ana_borsa} Fiyat": kesin_format(base_fiyat), 
        "Değişim %": gosterilecek_degisim,
        "Paribu (TL)": kesin_format(p_fiyat),
        "BtcTurk (TL)": kesin_format(bt_fiyat),
        "Binance (TL)": kesin_format(bin_fiyat)
    })

if tablo_satirlari:
    df = pd.DataFrame(tablo_satirlari)
    
    # Sıralama
    df = df.sort_values(by="Değişim %", ascending=False)
    
    # String Dönüşümü
    df[f"{ana_borsa} Fiyat"] = df[f"{ana_borsa} Fiyat"].astype(str)
    df["Paribu (TL)"] = df["Paribu (TL)"].astype(str)
    df["BtcTurk (TL)"] = df["BtcTurk (TL)"].astype(str)
    df["Binance (TL)"] = df["Binance (TL)"].astype(str)

    def stil_ver(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #00ff00; font-weight: bold;'
            elif val < 0: return 'color: #ff4444; font-weight: bold;'
        return 'color: white;'
    
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman_dilimi} Değişim", format="%.2f %%"),
        f"{ana_borsa} Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)", help="Seçili Borsa"),
    }

    st.dataframe(
        df.style.map(stil_ver, subset=["Değişim %"]),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Mod: {ana_borsa} - {zaman_dilimi}")
    if zaman_dilimi != "24 Saat":
        st.info("ℹ️ Not: 1 Saatlik ve 4 Saatlik veriler program açık kaldıkça hesaplanır. İlk açılışta %0 görünmesi normaldir.")

else:
    st.error("Veri oluşturulamadı.")

time.sleep(15)
st.rerun()