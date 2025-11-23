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

# --- CSS (Tablo ve Link Görünümü) ---
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

# --- SABİTLER ---
YENILEME_HIZI = 15
LIMIT_1S = 240
LIMIT_4S = 960

# --- HAFIZA ---
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

# --- URL OLUŞTURUCU (Borsaların Link Yapısı) ---
def get_paribu_url(coin):
    # Paribu link yapısı: https://www.paribu.com/markets/btc-tl
    return f"https://www.paribu.com/markets/{coin.lower()}-tl"

def get_btcturk_url(coin):
    # BtcTurk link yapısı: https://pro.btcturk.com/pro/al-sat/BTC_TRY
    return f"https://pro.btcturk.com/pro/al-sat/{coin}_TRY"

def get_binance_url(coin):
    # Binance link yapısı: https://www.binance.com/en-TR/trade/BTC_USDT
    return f"https://www.binance.com/en-TR/trade/{coin}_USDT"

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
    # PARIBU
    paribu_dict = {}
    try:
        resp = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        for sym, val in resp.items():
            if "_TL" in sym:
                coin = sym.replace("_TL", "")
                paribu_dict[coin] = {"price": float(val['last']), "change": float(val['percentChange'])}
    except: pass

    # BTCTURK
    btcturk_dict = {}
    try:
        resp = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=2).json()
        for item in resp['data']:
            if item['pair'].endswith("TRY"):
                coin = item['pair'].replace("TRY", "")
                btcturk_dict[coin] = {"price": float(item['last']), "change": float(item['dailyPercent'])}
    except: pass

    # BINANCE
    binance_dict = {}
    try:
        resp = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=3).json()
        for item in resp:
            if item['symbol'].endswith("USDT"):
                coin = item['symbol'].replace("USDT", "")
                binance_dict[coin] = {
                    "price": float(item['lastPrice']) * usdt_rate_binance,
                    "change": float(item['priceChangePercent'])
                }
    except: pass
    return paribu_dict, btcturk_dict, binance_dict

# --- ANA PROGRAM ---

st.title("💎 Kripto Borsa Terminali")

# KURLAR
usdt_kurlar = get_usdt_rates()
k1, k2, k3 = st.columns(3)
k1.metric("Paribu USDT", f"{usdt_kurlar['Paribu']:.2f} ₺")
k2.metric("BtcTurk USDT", f"{usdt_kurlar['BtcTurk']:.2f} ₺")
k3.metric("Binance USDT", f"{usdt_kurlar['Binance']:.2f} ₺")

st.markdown("---")

# SEÇİMLER
col_borsa, col_zaman = st.columns([1, 1])
with col_borsa:
    ana_borsa = st.radio("BORSA SEÇİMİ:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
with col_zaman:
    zaman_dilimi = st.radio("ZAMAN DİLİMİ:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)

# VERİ İŞLEME
p_data, b_data, bin_data = get_all_market_data(usdt_kurlar['Binance'])

if ana_borsa == "Paribu":
    hedef_coin_listesi = list(p_data.keys())
elif ana_borsa == "BtcTurk":
    hedef_coin_listesi = list(b_data.keys())
else:
    filtrelenmis_kume = set(p_data.keys()) | set(b_data.keys())
    hedef_coin_listesi = list(filtrelenmis_kume)

tablo_satirlari = []

for coin in hedef_coin_listesi:
    # Fiyat Belirleme
    base_fiyat = 0
    base_24h_degisim = 0.0
    
    if ana_borsa == "Paribu":
        base_fiyat = p_data.get(coin, {}).get('price', 0)
        base_24h_degisim = p_data.get(coin, {}).get('change', 0)
    elif ana_borsa == "BtcTurk":
        base_fiyat = b_data.get(coin, {}).get('price', 0)
        base_24h_degisim = b_data.get(coin, {}).get('change', 0)
    else:
        bin_veri = bin_data.get(coin, {})
        base_fiyat = bin_veri.get('price', 0)
        base_24h_degisim = bin_veri.get('change', 0)

    # Hafıza
    if coin not in st.session_state.hafiza: st.session_state.hafiza[coin] = []
    if base_fiyat > 0: st.session_state.hafiza[coin].append(base_fiyat)
    if len(st.session_state.hafiza[coin]) > LIMIT_4S + 10: st.session_state.hafiza[coin].pop(0)

    gecmis = st.session_state.hafiza[coin]
    gosterilecek_degisim = 0.0
    
    if zaman_dilimi == "24 Saat":
        gosterilecek_degisim = base_24h_degisim
    elif zaman_dilimi == "1 Saat":
        idx = -LIMIT_1S if len(gecmis) >= LIMIT_1S else 0
        if len(gecmis) > 0 and gecmis[idx] > 0:
            gosterilecek_degisim = ((gecmis[-1] - gecmis[idx]) / gecmis[idx]) * 100
    elif zaman_dilimi == "4 Saat":
        idx = -LIMIT_4S if len(gecmis) >= LIMIT_4S else 0
        if len(gecmis) > 0 and gecmis[idx] > 0:
            gosterilecek_degisim = ((gecmis[-1] - gecmis[idx]) / gecmis[idx]) * 100

    # Diğer Borsalar
    p_fiyat = p_data.get(coin, {}).get('price', 0)
    bt_fiyat = b_data.get(coin, {}).get('price', 0)
    bin_fiyat = bin_data.get(coin, {}).get('price', 0)

    # --- TABLOYA LİNKLERİ EKLEME ---
    tablo_satirlari.append({
        "Coin": coin,
        f"{ana_borsa} Fiyat": kesin_format(base_fiyat), 
        "Değişim %": gosterilecek_degisim,
        
        "Paribu (TL)": kesin_format(p_fiyat),
        "P_Link": get_paribu_url(coin) if p_fiyat > 0 else None, # Fiyat varsa link ver
        
        "BtcTurk (TL)": kesin_format(bt_fiyat),
        "BT_Link": get_btcturk_url(coin) if bt_fiyat > 0 else None,
        
        "Binance (TL)": kesin_format(bin_fiyat),
        "Bin_Link": get_binance_url(coin) if bin_fiyat > 0 else None
    })

if tablo_satirlari:
    df = pd.DataFrame(tablo_satirlari)
    df = df.sort_values(by="Değişim %", ascending=False)
    
    # String Dönüşümleri
    df[f"{ana_borsa} Fiyat"] = df[f"{ana_borsa} Fiyat"].astype(str)
    df["Paribu (TL)"] = df["Paribu (TL)"].astype(str)
    df["BtcTurk (TL)"] = df["BtcTurk (TL)"].astype(str)
    df["Binance (TL)"] = df["Binance (TL)"].astype(str)

    def stil_ver(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #00ff00; font-weight: bold;'
            elif val < 0: return 'color: #ff4444; font-weight: bold;'
        return 'color: white;'
    
    # --- SÜTUN AYARLARI VE LİNKLER ---
    # LinkColumn: display_text="🔗" diyerek sadece simge gösteriyoruz, yer kaplamıyor.
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman_dilimi} Değişim", format="%.2f %%"),
        f"{ana_borsa} Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        
        "P_Link": st.column_config.LinkColumn("Git", display_text="🔗"),
        "BT_Link": st.column_config.LinkColumn("Git", display_text="🔗"),
        "Bin_Link": st.column_config.LinkColumn("Git", display_text="🔗"),
    }

    # Sütun Sıralaması (Hangi veri nereden sonra gelecek)
    # Örnek: Paribu Fiyat -> Paribu Link -> BtcTurk Fiyat -> BtcTurk Link...
    sutun_sirasi = [
        "Coin", f"{ana_borsa} Fiyat", "Değişim %",
        "Paribu (TL)", "P_Link", 
        "BtcTurk (TL)", "BT_Link", 
        "Binance (TL)", "Bin_Link"
    ]

    st.dataframe(
        df[sutun_sirasi].style.map(stil_ver, subset=["Değişim %"]),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Linklere tıklayarak borsalara gidebilirsiniz.")

else:
    st.error("Veri oluşturulamadı.")

time.sleep(15)
st.rerun()