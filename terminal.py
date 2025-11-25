import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading

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
YENILEME_HIZI = 15 
LIMIT_1S = 240     
LIMIT_4S = 960     

# --- ANTI-ROBOT BAŞLIKLARI ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- ORTAK HAVUZ (SUNUCU HAFIZASI) ---
@st.cache_resource
class OrtakHafiza:
    def __init__(self):
        self.data = {} 
        self.last_update = {} 
        self.lock = threading.Lock() 
        self.baslangic = datetime.now()

    def veri_ekle(self, coin, fiyat):
        with self.lock: 
            now = time.time()
            if coin in self.last_update:
                if (now - self.last_update[coin]) < 14: return 

            if coin not in self.data: self.data[coin] = []
            if fiyat > 0:
                self.data[coin].append(fiyat)
                self.last_update[coin] = now 
            
            if len(self.data[coin]) > LIMIT_4S + 20:
                self.data[coin].pop(0)

    def get_gecmis(self, coin):
        return self.data.get(coin, [])
    
    def get_uptime(self):
        delta = datetime.now() - self.baslangic
        return str(delta).split('.')[0] 

havuz = OrtakHafiza()

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

# --- GÜVENLİ VERİ ÇEKME ---
def safe_get(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200: return response.json()
    except: pass
    return None

def get_usdt_rates():
    rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}
    r = safe_get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY")
    rates["Binance"] = float(r['price']) if r else 34.50
    r = safe_get("https://www.paribu.com/ticker")
    rates["Paribu"] = float(r["USDT_TL"]['last']) if r else 0
    r = safe_get("https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY")
    rates["BtcTurk"] = float(r['data'][0]['last']) if r else 0
    return rates

def get_live_data(usdt_rate):
    p_dict, bt_dict, bin_dict = {}, {}, {}
    
    # Paribu
    r = safe_get("https://www.paribu.com/ticker")
    if r:
        for s, v in r.items():
            if "_TL" in s:
                p_dict[s.replace("_TL", "")] = {"price": float(v['last']), "change": float(v['percentChange'])}
    
    # BtcTurk
    r = safe_get("https://api.btcturk.com/api/v2/ticker")
    if r:
        for i in r['data']:
            if i['pair'].endswith("TRY"):
                bt_dict[i['pair'].replace("TRY", "")] = {"price": float(i['last']), "change": float(i['dailyPercent'])}
    
    # Binance
    r = safe_get("https://data-api.binance.vision/api/v3/ticker/24hr")
    if r:
        for i in r:
            if i['symbol'].endswith("USDT"):
                bin_dict[i['symbol'].replace("USDT", "")] = {
                    "price": float(i['lastPrice']) * usdt_rate,
                    "change": float(i['priceChangePercent'])
                }
    return p_dict, bt_dict, bin_dict

# --- ANA PROGRAM ---
st.title("💎 Kripto Borsa Terminali")

uptime = havuz.get_uptime()
st.info(f"📡 **Ortak Veri Havuzu Aktif** | Sunucu Açık Kalma Süresi: **{uptime}** | Mini grafikler toplanan verilerle oluşturulur.")

usdt = get_usdt_rates()
k1, k2, k3 = st.columns(3)
k1.metric("Paribu USDT", f"{usdt['Paribu']:.2f} ₺")
k2.metric("BtcTurk USDT", f"{usdt['BtcTurk']:.2f} ₺")
k3.metric("Binance USDT", f"{usdt['Binance']:.2f} ₺")

st.markdown("---")

col_b, col_z = st.columns([1, 1])
with col_b: ana_borsa = st.radio("BORSA:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
with col_z: zaman = st.radio("ZAMAN:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)

p_d, b_d, bin_d = get_live_data(usdt['Binance'])

if ana_borsa == "Paribu": lst = list(p_d.keys())
elif ana_borsa == "BtcTurk": lst = list(b_d.keys())
else: lst = list(set(p_d.keys()) | set(b_d.keys()))

rows = []
for c in lst:
    try:
        ana_fiyat, hazir_24s_degisim = 0, 0.0
        if ana_borsa == "Paribu": 
            ana_fiyat = p_d.get(c, {}).get('price', 0)
            hazir_24s_degisim = p_d.get(c, {}).get('change', 0)
        elif ana_borsa == "BtcTurk": 
            ana_fiyat = b_d.get(c, {}).get('price', 0)
            hazir_24s_degisim = b_d.get(c, {}).get('change', 0)
        else: 
            ana_fiyat = bin_d.get(c, {}).get('price', 0)
            hazir_24s_degisim = bin_d.get(c, {}).get('change', 0)

        # HAVUZA EKLE
        if ana_fiyat > 0: havuz.veri_ekle(c, ana_fiyat)

        # DEĞİŞİM & GRAFİK VERİSİ
        gosterilecek_degisim = 0.0
        gecmis_liste = havuz.get_gecmis(c)

        if zaman == "24 Saat":
            gosterilecek_degisim = hazir_24s_degisim
        elif zaman == "1 Saat":
            idx = -LIMIT_1S if len(gecmis_liste) >= LIMIT_1S else 0
            if len(gecmis_liste) > 0 and gecmis_liste[idx] > 0:
                gosterilecek_degisim = ((ana_fiyat - gecmis_liste[idx]) / gecmis_liste[idx]) * 100
        elif zaman == "4 Saat":
            idx = -LIMIT_4S if len(gecmis_liste) >= LIMIT_4S else 0
            if len(gecmis_liste) > 0 and gecmis_liste[idx] > 0:
                gosterilecek_degisim = ((ana_fiyat - gecmis_liste[idx]) / gecmis_liste[idx]) * 100

        pf = p_d.get(c, {}).get('price', 0)
        btf = b_d.get(c, {}).get('price', 0)
        binf = bin_d.get(c, {}).get('price', 0)

        rows.append({
            "Coin": c,
            "Ana Fiyat": kesin_format(ana_fiyat),
            "Değişim %": gosterilecek_degisim,
            "Trend": gecmis_liste, # GRAFİK İÇİN HAM LİSTE
            "Paribu": make_link(get_paribu_link(c), kesin_format(pf)),
            "BtcTurk": make_link(get_btcturk_link(c), kesin_format(btf)),
            "Binance": make_link(get_binance_link(c), kesin_format(binf))
        })
    except: continue

if rows:
    df = pd.DataFrame(rows).sort_values(by="Değişim %", ascending=False)
    
    def style_row(row):
        styles = [''] * len(row)
        ch = row["Değişim %"]
        styles[1] = 'color: white; font-weight: bold;'
        if ch > 0: styles[2] = 'color: #00ff00; font-weight: bold;'
        elif ch < 0: styles[2] = 'color: #ff4444; font-weight: bold;'
        styles[4] = 'color: #2e7d32; font-weight: bold;'
        styles[5] = 'color: #1565c0; font-weight: bold;'
        styles[6] = 'color: #ffd700; font-weight: bold;'
        return styles

    # --- SÜTUN AYARLARI (GRAFİK EKLENDİ) ---
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Değişim", format="%.2f %%"),
        
        # YENİ: LineChartColumn (Satır İçi Grafik)
        "Trend": st.column_config.LineChartColumn(
            "Canlı Grafik (4s)",
            y_min=0,
            y_max=None, # Otomatik ölçekleme
        ),

        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        "Paribu": st.column_config.LinkColumn("Paribu (TL)", display_text=r"#etiket=(.*)"),
        "BtcTurk": st.column_config.LinkColumn("BtcTurk (TL)", display_text=r"#etiket=(.*)"),
        "Binance": st.column_config.LinkColumn("Binance (TL)", display_text=r"#etiket=(.*)"),
    }

    # Sıralama: Trend grafiği değişimden hemen sonra gelsin
    cols = ["Coin", "Ana Fiyat", "Değişim %", "Trend", "Paribu", "BtcTurk", "Binance"]

    st.dataframe(
        df[cols].style.apply(style_row, axis=1),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')}")
else:
    st.warning("Veriler yükleniyor...")

time.sleep(YENILEME_HIZI)
st.rerun()