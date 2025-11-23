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

# --- CSS (Görünüm İyileştirmeleri) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.05rem; }
    /* Linklerin altındaki varsayılan çizgiyi kaldır */
    a { text-decoration: none !important; }
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

# --- FORMATLAMA ---
def kesin_format(fiyat):
    if fiyat is None or fiyat == 0:
        return "-" 
    if fiyat < 1:
        return "{:.8f} ₺".format(fiyat)
    elif fiyat < 10:
        return "{:.6f} ₺".format(fiyat)
    else:
        return "{:,.2f} ₺".format(fiyat)

# --- LİNK OLUŞTURUCULAR (Standart Yapı) ---
def make_link(base_url, price_str):
    """
    URL'in sonuna ?label=FIYAT ekleyerek Streamlit'in
    bunu okumasını ve ekranda sadece fiyatı göstermesini sağlıyoruz.
    """
    if price_str == "-":
        return None
    # Boşlukları ve ₺ işaretini temizleyip URL dostu yapalım ama görüntüde kalsın
    clean_price = price_str.replace(" ", "_") 
    return f"{base_url}?label={clean_price}"

def get_paribu_base(coin):
    return f"https://www.paribu.com/markets/{coin.lower()}-tl"

def get_btcturk_base(coin):
    return f"https://pro.btcturk.com/pro/al-sat/{coin.upper()}_TRY"

def get_binance_base(coin):
    return f"https://www.binance.com/en-TR/trade/{coin.upper()}_USDT"

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

# Listeyi Belirle
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

    # String Formatlar
    str_ana = kesin_format(base_fiyat)
    str_p = kesin_format(p_fiyat)
    str_bt = kesin_format(bt_fiyat)
    str_bin = kesin_format(bin_fiyat)

    tablo_satirlari.append({
        "Coin": coin,
        f"Ana Fiyat": str_ana, # Sadece Yazı (Link Yok)
        "Değişim %": gosterilecek_degisim,
        "Paribu": make_link(get_paribu_base(coin), str_p),
        "BtcTurk": make_link(get_btcturk_base(coin), str_bt),
        "Binance": make_link(get_binance_base(coin), str_bin)
    })

if tablo_satirlari:
    df = pd.DataFrame(tablo_satirlari)
    df = df.sort_values(by="Değişim %", ascending=False)
    
    # --- RENKLENDİRME MANTIĞI (PANDAS STYLER) ---
    def renk_uygula(row):
        # Varsayılan renkler
        styles = [''] * len(row)
        
        degisim = row["Değişim %"]
        
        # 2. Sütun (Ana Fiyat) -> Değişime göre Yeşil/Kırmızı
        if degisim > 0:
            styles[1] = 'color: #00ff00; font-weight: bold' # Yeşil
        elif degisim < 0:
            styles[1] = 'color: #ff4444; font-weight: bold' # Kırmızı
        
        # 3. Sütun (Değişim) -> Zaten kendi renklendirmesi var ama manuel de yapabiliriz
        if degisim > 0:
            styles[2] = 'color: #00ff00; font-weight: bold'
        elif degisim < 0:
            styles[2] = 'color: #ff4444; font-weight: bold'

        # 4. Sütun (Paribu) -> Koyu Yeşil
        # Link olduğu için color bazen ezilebilir ama font-weight çalışır
        styles[3] = 'color: #2e7d32; font-weight: bold' 

        # 5. Sütun (BtcTurk) -> Koyu Mavi
        styles[4] = 'color: #1565c0; font-weight: bold'

        # 6. Sütun (Binance) -> Sarı (Okunurluk için Parlak Sarı/Gold)
        styles[5] = 'color: #ffd700; font-weight: bold'
        
        return styles

    # --- SÜTUN AYARLARI ---
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman_dilimi} Değişim", format="%.2f %%"),
        
        # Paribu (Link ve Etiket)
        "Paribu": st.column_config.LinkColumn(
            "Paribu (TL)", 
            display_text=r"label=(.*)" # URL'deki label kısmını göster
        ),
        # BtcTurk
        "BtcTurk": st.column_config.LinkColumn(
            "BtcTurk (TL)", 
            display_text=r"label=(.*)"
        ),
        # Binance
        "Binance": st.column_config.LinkColumn(
            "Binance (TL)", 
            display_text=r"label=(.*)"
        ),
    }
    
    # Sıralama
    cols = ["Coin", "Ana Fiyat", "Değişim %", "Paribu", "BtcTurk", "Binance"]

    st.dataframe(
        df[cols].style.apply(renk_uygula, axis=1), # Renk fonksiyonunu satır satır uygula
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | 🔗 Fiyatlara tıklayarak borsalara gidebilirsiniz.")

else:
    st.error("Veri oluşturulamadı.")

time.sleep(YENILEME_HIZI)
st.rerun()