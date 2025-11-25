import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading # Aynı anda veri yazılmasını yönetmek için

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
YENILEME_HIZI = 15 # Her 15 saniyede bir veri topla ve havuza at
LIMIT_1S = 240     # 1 saat (60dk * 60sn / 15sn = 240)
LIMIT_4S = 960     # 4 saat

# --- ORTAK HAVUZ (SUNUCU HAFIZASI) ---
# Bu kısım SİHİRLİDİR. @st.cache_resource sayesinde bu sınıf
# kullanıcıya özel değil, SUNUCUYA özel olur.
# Yani siteyi kim açarsa açsın, herkes buradaki veriyi okur ve yazar.

@st.cache_resource
class OrtakHafiza:
    def __init__(self):
        self.data = {} # Tüm coinlerin fiyat geçmişi burada duracak
        self.lock = threading.Lock() # Aynı anda iki kişi yazarsa karışmasın diye kilit
        self.baslangic = datetime.now() # Sunucunun ne zaman başladığı

    def veri_ekle(self, coin, fiyat):
        with self.lock:
            if coin not in self.data:
                self.data[coin] = []
            
            # Fiyatı listeye ekle
            if fiyat > 0:
                self.data[coin].append(fiyat)
            
            # Listeyi temizle (4 Saatten fazlasını tutma - RAM şişmesin)
            # LIMIT_4S + 100 kadar tampon bellek bırakıyoruz
            if len(self.data[coin]) > LIMIT_4S + 100:
                self.data[coin].pop(0)

    def get_gecmis(self, coin):
        # Coinin geçmişini ver
        return self.data.get(coin, [])
    
    def get_uptime(self):
        # Sunucu ne kadar süredir açık?
        delta = datetime.now() - self.baslangic
        return str(delta).split('.')[0] # Saniye küsuratını at

# Sunucudaki Tekil Nesneyi Oluştur (Singleton)
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

# Üst Bilgi Paneli (Ortak Havuz Durumu)
uptime = havuz.get_uptime()
st.info(f"📡 **Ortak Veri Havuzu Aktif** | Sunucu Çalışma Süresi: **{uptime}** | Bu süre boyunca toplanan veriler tüm cihazlarda ortaktır.")

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
    # 1. Ana Fiyatı Belirle
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

    # 2. ORTAK HAVUZA VERİ GÖNDER!
    # Hangi cihazda açık olursa olsun, veriyi sunucuya yazıyoruz.
    if ana_fiyat > 0:
        havuz.veri_ekle(c, ana_fiyat)

    # 3. DEĞİŞİM HESAPLAMA (Ortak Havuzdan Okuyarak)
    gosterilecek_degisim = 0.0
    
    # Sunucudaki ortak listeden veriyi çek
    gecmis_liste = havuz.get_gecmis(c)

    if zaman == "24 Saat":
        gosterilecek_degisim = hazir_24s_degisim
    
    elif zaman == "1 Saat":
        if len(gecmis_liste) > 0:
            index = -LIMIT_1S if len(gecmis_liste) >= LIMIT_1S else 0
            eski_fiyat = gecmis_liste[index]
            if eski_fiyat > 0:
                gosterilecek_degisim = ((ana_fiyat - eski_fiyat) / eski_fiyat) * 100
    
    elif zaman == "4 Saat":
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

    # Sayaç Bilgisi
    kayit_sayisi = 0
    if len(rows) > 0:
        ornek_coin = rows[0]["Coin"]
        kayit_sayisi = len(havuz.get_gecmis(ornek_coin))
    
    not_bilgisi = f"Havuzda {kayit_sayisi} adet veri birikti. (PC veya Telefon fark etmez, sunucu hafızası kullanılır)"

    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Trendi", format="%.2f %%", help=not_bilgisi),
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
    
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | {not_bilgisi}")
else:
    st.error("Veri yok.")

time.sleep(YENILEME_HIZI)
st.rerun()