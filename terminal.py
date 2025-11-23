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

# 2. BÖLÜM: ANA BORSA SEÇİMİ
col_secim, col_bosluk = st.columns([2, 3])
with col_secim:
    ana_borsa = st.radio("ANA BORSA (Tabloyu buna göre kur):", 
                         ["Paribu", "BtcTurk", "Binance"], 
                         horizontal=True)

# 3. BÖLÜM: VERİ FİLTRELEME MANTIĞI
p_data, b_data, bin_data = get_all_market_data(usdt_kurlar['Binance'])

hedef_coin_listesi = []
kaynak_isim = ana_borsa

if ana_borsa == "Paribu":
    # Sadece Paribu'daki coinler
    hedef_coin_listesi = list(p_data.keys())

elif ana_borsa == "BtcTurk":
    # Sadece BtcTurk'teki coinler
    hedef_coin_listesi = list(b_data.keys())

else: # Binance Seçildiyse
    # MANTIK DEĞİŞİKLİĞİ: Tüm Binance'i getirme.
    # Sadece (Paribu Listesi + BtcTurk Listesi) toplamını getir.
    # set() kullanarak mükerrerleri engelliyoruz ve iki kümeyi birleştiriyoruz (| işareti)
    filtrelenmis_kume = set(p_data.keys()) | set(b_data.keys())
    hedef_coin_listesi = list(filtrelenmis_kume)

# Tabloyu Doldur
tablo_satirlari = []

for coin in hedef_coin_listesi:
    # Ana borsa verisini belirle
    base_fiyat = 0
    base_degisim = 0.0

    if ana_borsa == "Paribu":
        base_fiyat = p_data.get(coin, {}).get('price', 0)
        base_degisim = p_data.get(coin, {}).get('change', 0)
    elif ana_borsa == "BtcTurk":
        base_fiyat = b_data.get(coin, {}).get('price', 0)
        base_degisim = b_data.get(coin, {}).get('change', 0)
    else: # Binance Modu
        # Eğer coin Binance'de varsa onun verisini al, yoksa 0
        bin_veri = bin_data.get(coin, {})
        base_fiyat = bin_veri.get('price', 0)
        base_degisim = bin_veri.get('change', 0)

    # Diğer borsaların fiyatları
    p_fiyat = p_data.get(coin, {}).get('price', 0)
    bt_fiyat = b_data.get(coin, {}).get('price', 0)
    bin_fiyat = bin_data.get(coin, {}).get('price', 0)

    # Eğer ana borsa verisi 0 ise (örneğin Paribu+BtcTurk listesinde var ama Binance'de o coin listelenmemiş)
    # Listeye ekleyip eklememek sana kalmış, şimdilik boş fiyatla ekliyorum ki eksik görme.
    
    tablo_satirlari.append({
        "Coin": coin,
        f"{kaynak_isim} Fiyat": kesin_format(base_fiyat), 
        "24s Değişim %": base_degisim,
        "Paribu (TL)": kesin_format(p_fiyat),
        "BtcTurk (TL)": kesin_format(bt_fiyat),
        "Binance (TL)": kesin_format(bin_fiyat)
    })

if tablo_satirlari:
    df = pd.DataFrame(tablo_satirlari)
    
    # Sıralama
    df = df.sort_values(by="24s Değişim %", ascending=False)
    
    # String Dönüşümü (Yuvarlama hatasını önlemek için)
    df[f"{kaynak_isim} Fiyat"] = df[f"{kaynak_isim} Fiyat"].astype(str)
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
        "24s Değişim %": st.column_config.NumberColumn("24s Değişim", format="%.2f %%"),
        f"{kaynak_isim} Fiyat": st.column_config.TextColumn(f"🔥 {kaynak_isim} (Ana)", help="Seçili Borsa"),
    }

    st.dataframe(
        df.style.map(stil_ver, subset=["24s Değişim %"]),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Binance Modu Filtresi: Sadece TR Borsalarında Olanlar")

else:
    st.error("Veri oluşturulamadı.")

time.sleep(15)
st.rerun()