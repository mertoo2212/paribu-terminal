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
    a { text-decoration: none !important; color: inherit !important; }
    a:hover { text-decoration: underline !important; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
YENILEME_HIZI = 10 # Her 10 saniyede bir veri topla
LIMIT_1S = 360     # 1 saat için kaç veri lazım? (3600sn / 10sn = 360 kayıt)
LIMIT_4S = 1440    # 4 saat için kaç veri lazım? (14400sn / 10sn = 1440 kayıt)

# --- HAFIZA (Session State) ---
# Burası programın beyni. Fiyatları burada biriktireceğiz.
if 'fiyat_gecmisi' not in st.session_state:
    st.session_state.fiyat_gecmisi = {} # { 'BTC': [fiyat1, fiyat2, ...], 'ETH': [...] }

if 'baslangic_zamani' not in st.session_state:
    st.session_state.baslangic_zamani = datetime.now()

# --- FORMATLAMA ---
def kesin_format(fiyat):
    if fiyat is None or fiyat == 0: return "-" 
    if fiyat < 1: return "{:.8f} ₺".format(fiyat)
    elif fiyat < 10: return "{:.6f} ₺".format(fiyat)
    else: return "{:,.2f} ₺".format(fiyat)

# --- LİNK OLUŞTURUCULAR ---
def make_link(base_url, price_str):
    if price_str == "-": return None
    clean_price = price_str.replace(" ", "_") 
    return f"{base_url}#etiket={clean_price}"

def get_paribu_link(coin): return f"https://www.paribu.com/markets/{coin.lower()}_tl"
def get_btcturk_link(coin): return f"https://kripto.btcturk.com/pro/al-sat/{coin.upper()}_TRY"
def get_binance_link(coin): return f"https://www.binance.com/en-TR/trade/{coin.upper()}_USDT"

# --- VERİ ÇEKME ---
def get_usdt_rates():
    rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}
    try: rates["Binance"] = float(requests.get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY", timeout=2).json()['price'])
    except: rates["Binance"] = 34.50
    try: rates["Paribu"] = float(requests.get("https://www.paribu.com/ticker", timeout=2).json()["USDT_TL"]['last'])
    except: rates["Paribu"] = 0
    try: rates["BtcTurk"] = float(requests.get("https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY", timeout=2).json()['data'][0]['last'])
    except: rates["BtcTurk"] = 0
    return rates

def get_live_data(usdt_rate):
    p_dict, bt_dict, bin_dict = {}, {}, {}
    # Paribu
    try:
        r = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        for s, v in r.items():
            if "_TL" in s:
                p_dict[s.replace("_TL", "")] = {"price": float(v['last']), "change": float(v['percentChange'])}
    except: pass
    # BtcTurk
    try:
        r = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=2).json()
        for i in r['data']:
            if i['pair'].endswith("TRY"):
                bt_dict[i['pair'].replace("TRY", "")] = {"price": float(i['last']), "change": float(i['dailyPercent'])}
    except: pass
    # Binance
    try:
        r = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=3).json()
        for i in r:
            if i['symbol'].endswith("USDT"):
                bin_dict[i['symbol'].replace("USDT", "")] = {
                    "price": float(i['lastPrice']) * usdt_rate,
                    "change": float(i['priceChangePercent'])
                }
    except: pass
    
    return p_dict, bt_dict, bin_dict

# --- ANA PROGRAM ---
st.title("💎 Kripto Borsa Terminali")

usdt = get_usdt_rates()
k1, k2, k3 = st.columns(3)
k1.metric("Paribu USDT", f"{usdt['Paribu']:.2f} ₺")
k2.metric("BtcTurk USDT", f"{usdt['BtcTurk']:.2f} ₺")
k3.metric("Binance USDT", f"{usdt['Binance']:.2f} ₺")

st.markdown("---")

col_b, col_z = st.columns([1, 1])
with col_b: ana_borsa = st.radio("BORSA:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
with col_z: zaman = st.radio("ZAMAN:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)

# Verileri Çek
p_d, b_d, bin_d = get_live_data(usdt['Binance'])

# Listeyi Belirle
if ana_borsa == "Paribu": lst = list(p_d.keys())
elif ana_borsa == "BtcTurk": lst = list(b_d.keys())
else: lst = list(set(p_d.keys()) | set(b_d.keys()))

rows = []
for c in lst:
    # 1. Ana Fiyatı Belirle (Hangi borsayı seçtiysek onun fiyatı hafızaya gidecek)
    ana_fiyat = 0
    hazir_24s_degisim = 0.0

    if ana_borsa == "Paribu": 
        ana_fiyat = p_d.get(c, {}).get('price', 0)
        hazir_24s_degisim = p_d.get(c, {}).get('change', 0)
    elif ana_borsa == "BtcTurk": 
        ana_fiyat = b_d.get(c, {}).get('price', 0)
        hazir_24s_degisim = b_d.get(c, {}).get('change', 0)
    else: 
        ana_fiyat = bin_d.get(c, {}).get('price', 0)
        hazir_24s_degisim = bin_d.get(c, {}).get('change', 0)

    # 2. HAFIZA İŞLEMİ (VERİ BİRİKTİRME)
    if c not in st.session_state.fiyat_gecmisi:
        st.session_state.fiyat_gecmisi[c] = []
    
    # Eğer fiyat geçerliyse listeye ekle
    if ana_fiyat > 0:
        st.session_state.fiyat_gecmisi[c].append(ana_fiyat)
    
    # Hafızayı Taşurma (4 Saatten eski veriyi sil - RAM tasarrufu)
    # LIMIT_4S + 50 kadar veri tutuyoruz (biraz pay bıraktık)
    if len(st.session_state.fiyat_gecmisi[c]) > LIMIT_4S + 50:
        st.session_state.fiyat_gecmisi[c].pop(0)

    # 3. DEĞİŞİM HESAPLAMA (Zamana Göre)
    gosterilecek_degisim = 0.0
    gecmis_liste = st.session_state.fiyat_gecmisi[c]

    if zaman == "24 Saat":
        # 24 Saat için borsanın kendi verisi (API) kullanılır, biriktirmeye gerek yok.
        gosterilecek_degisim = hazir_24s_degisim
    
    elif zaman == "1 Saat":
        # 1 Saat (360 kayıt) geriye gitmeye çalış
        if len(gecmis_liste) > 0:
            # Eğer yeterli veri yoksa (örn: program yeni açıldıysa) listenin en başını al
            index = -LIMIT_1S if len(gecmis_liste) >= LIMIT_1S else 0
            eski_fiyat = gecmis_liste[index]
            if eski_fiyat > 0:
                gosterilecek_degisim = ((ana_fiyat - eski_fiyat) / eski_fiyat) * 100
    
    elif zaman == "4 Saat":
        # 4 Saat (1440 kayıt) geriye gitmeye çalış
        if len(gecmis_liste) > 0:
            index = -LIMIT_4S if len(gecmis_liste) >= LIMIT_4S else 0
            eski_fiyat = gecmis_liste[index]
            if eski_fiyat > 0:
                gosterilecek_degisim = ((ana_fiyat - eski_fiyat) / eski_fiyat) * 100

    # Diğer Borsalar
    pf = p_d.get(c, {}).get('price', 0)
    btf = b_d.get(c, {}).get('price', 0)
    binf = bin_d.get(c, {}).get('price', 0)

    rows.append({
        "Coin": c,
        "Ana Fiyat": kesin_format(ana_fiyat),
        "Değişim %": gosterilecek_degisim,
        "Paribu": make_link(get_paribu_link(c), kesin_format(pf)),
        "BtcTurk": make_link(get_btcturk_link(c), kesin_format(btf)),
        "Binance": make_link(get_binance_link(c), kesin_format(binf))
    })

if rows:
    df = pd.DataFrame(rows).sort_values(by="Değişim %", ascending=False)
    
    def style_row(row):
        styles = [''] * len(row)
        ch = row["Değişim %"]
        styles[1] = 'color: white; font-weight: bold;'
        if ch > 0: styles[2] = 'color: #00ff00; font-weight: bold;'
        elif ch < 0: styles[2] = 'color: #ff4444; font-weight: bold;'
        styles[3] = 'color: #2e7d32; font-weight: bold;'
        styles[4] = 'color: #1565c0; font-weight: bold;'
        styles[5] = 'color: #ffd700; font-weight: bold;'
        return styles

    # Bilgilendirme metni (Süre)
    gecen_sure = datetime.now() - st.session_state.baslangic_zamani
    dakika = int(gecen_sure.total_seconds() / 60)
    
    sistem_notu = "Borsa Verisi (24s)"
    if zaman != "24 Saat":
        sistem_notu = f"Canlı Toplanan Veri ({dakika} dakikadır birikiyor)"

    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Değişim", format="%.2f %%", help=sistem_notu),
        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        "Paribu": st.column_config.LinkColumn("Paribu (TL)", display_text=r"#etiket=(.*)"),
        "BtcTurk": st.column_config.LinkColumn("BtcTurk (TL)", display_text=r"#etiket=(.*)"),
        "Binance": st.column_config.LinkColumn("Binance (TL)", display_text=r"#etiket=(.*)"),
    }

    st.dataframe(
        df[["Coin", "Ana Fiyat", "Değişim %", "Paribu", "BtcTurk", "Binance"]].style.apply(style_row, axis=1),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | {sistem_notu}")
    
    if zaman != "24 Saat" and dakika < 60:
        st.warning(f"⚠️ Dikkat: Program yeni başlatıldı ({dakika} dk). 1 Saatlik doğru veriler için sayfanın açık kalması gerekir.")

else:
    st.error("Veri yok.")

# Sayfanın sürekli yenilenip veri toplaması için:
time.sleep(YENILEME_HIZI)
st.rerun()