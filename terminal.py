import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Terminal",
    page_icon="🚀",
    layout="wide"
)

# --- SABİTLER ---
YENILEME_HIZI = 15
LIMIT_1S = 240
LIMIT_4S = 960

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    /* Tablo yazı tipini biraz daha okunur yapalım */
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.05rem; }
    </style>
    """, unsafe_allow_html=True)

# --- HAFIZA ---
if 'hafiza' not in st.session_state:
    st.session_state.hafiza = {}
if 'son_guncelleme' not in st.session_state:
    st.session_state.son_guncelleme = time.time()

# --- FORMATLAMA FONKSİYONU ---
def kesin_format(fiyat):
    if fiyat is None or fiyat == 0:
        return "0.000000 ₺"
    
    # Çok küçük sayılar (BONK, PEPE vb) -> 8 basamak
    if fiyat < 1:
        return "{:.8f} ₺".format(fiyat)
    # Orta küçük sayılar (10 TL altı) -> 6 basamak
    elif fiyat < 10:
        return "{:.6f} ₺".format(fiyat)
    # Normal sayılar -> 2 basamak
    else:
        return "{:,.2f} ₺".format(fiyat)

# --- VERİ ÇEKME ---
def get_usdt_try():
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY", timeout=2).json()
        return float(resp['price'])
    except:
        return 34.50

def get_binance_prices(usdt_try):
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=2).json()
        data = {}
        for item in resp:
            if item['symbol'].endswith("USDT"):
                coin = item['symbol'].replace("USDT", "")
                data[coin] = float(item['price']) * usdt_try
        return data
    except:
        return {}

def get_btcturk_prices():
    try:
        resp = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=2).json()
        data = {}
        for item in resp['data']:
            if item['pair'].endswith("TRY"):
                coin = item['pair'].replace("TRY", "")
                data[coin] = float(item['last'])
        return data
    except:
        return {}

def get_paribu_data():
    try:
        resp = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        return resp
    except:
        return None

# --- ANA PROGRAM ---
st.title("🚀 Kripto Arbitraj & Takip Terminali")

col1, col2 = st.columns([3, 1])
with col1:
    secilen_zaman = st.radio("Zaman Dilimi:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)
with col2:
    st.metric("Sistem Durumu", "Aktif 🟢")

paribu_raw = get_paribu_data()
usdt_kur = get_usdt_try()
binance_dict = get_binance_prices(usdt_kur)
btcturk_dict = get_btcturk_prices()

if paribu_raw:
    tablo_listesi = []
    
    for symbol, values in paribu_raw.items():
        if "_TL" in symbol:
            coin = symbol.replace("_TL", "")
            guncel_fiyat = float(values['last'])
            paribu_24h_degisim = float(values['percentChange'])

            # Hafıza
            if coin not in st.session_state.hafiza:
                st.session_state.hafiza[coin] = []
            st.session_state.hafiza[coin].append(guncel_fiyat)
            if len(st.session_state.hafiza[coin]) > LIMIT_4S + 10:
                st.session_state.hafiza[coin].pop(0)
            
            gecmis = st.session_state.hafiza[coin]

            # Hesaplama
            idx_1s = -LIMIT_1S if len(gecmis) >= LIMIT_1S else 0
            f1 = gecmis[idx_1s]
            degisim_1s = ((guncel_fiyat - f1) / f1) * 100 if f1 > 0 else 0

            idx_4s = -LIMIT_4S if len(gecmis) >= LIMIT_4S else 0
            f4 = gecmis[idx_4s]
            degisim_4s = ((guncel_fiyat - f4) / f4) * 100 if f4 > 0 else 0

            if secilen_zaman == "1 Saat":
                gosterilecek_degisim = degisim_1s
            elif secilen_zaman == "4 Saat":
                gosterilecek_degisim = degisim_4s
            else: 
                gosterilecek_degisim = paribu_24h_degisim

            b_fiyat = binance_dict.get(coin, 0)
            bt_fiyat = btcturk_dict.get(coin, 0)

            # LİSTEYE EKLE
            tablo_listesi.append({
                "Coin": coin,
                "Fiyat (TL)": kesin_format(guncel_fiyat), 
                "Değişim %": gosterilecek_degisim,
                "Binance (TL)": kesin_format(b_fiyat),
                "BtcTurk (TL)": kesin_format(bt_fiyat)
            })

    df = pd.DataFrame(tablo_listesi)
    
    # 1. Önce Sıralama Yap (Sayılar bozulmadan)
    df = df.sort_values(by="Değişim %", ascending=False)

    # 2. KRİTİK HAMLE: Sütunları zorla String (Yazı) tipine çeviriyoruz
    # Bu işlem Streamlit'in "Sayı mı acaba?" diye tahmin yürütmesini engeller.
    df["Fiyat (TL)"] = df["Fiyat (TL)"].astype(str)
    df["Binance (TL)"] = df["Binance (TL)"].astype(str)
    df["BtcTurk (TL)"] = df["BtcTurk (TL)"].astype(str)

    # Renklendirme
    def stil_ver(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #00ff00; font-weight: bold;'
            elif val < 0: return 'color: #ff4444; font-weight: bold;'
        return 'color: white;'

    # Sütun Ayarları
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        # TextColumn kullanarak açıkça belirtiyoruz
        "Fiyat (TL)": st.column_config.TextColumn("Paribu Fiyat"),
        "Değişim %": st.column_config.NumberColumn(f"{secilen_zaman} Değişim", format="%.2f %%"),
        "Binance (TL)": st.column_config.TextColumn("Binance"),
        "BtcTurk (TL)": st.column_config.TextColumn("BtcTurk"),
    }

    st.dataframe(
        df.style.map(stil_ver, subset=["Değişim %"]),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Tam Hassasiyet Modu")

else:
    st.error("Paribu verisi alınamadı.")

time.sleep(YENILEME_HIZI)
st.rerun()