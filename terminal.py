import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading
import concurrent.futures # Paralel işlem kütüphanesi

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Borsa Terminali",
    page_icon="💎",
    layout="wide"
)

# --- CSS (Görünüm) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.05rem; }
    a { text-decoration: none !important; color: inherit !important; }
    a:hover { text-decoration: underline !important; }
    .chart-title { text-align: center; font-weight: bold; margin-bottom: 5px; color: #aaa; }
    /* Metrik kutuları için stil */
    div[data-testid="stMetric"] { background-color: #161b22; border-radius: 8px; padding: 10px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
YENILEME_HIZI = 15 
LIMIT_1S = 240     
LIMIT_4S = 960     

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
            # Çakışma Önleyici (14 saniye kuralı)
            if coin in self.last_update:
                if (now - self.last_update[coin]) < 14: return 

            if coin not in self.data: self.data[coin] = []
            
            # HATA KORUMASI: Sadece mantıklı fiyatları ekle
            if fiyat > 0:
                self.data[coin].append(fiyat)
                self.last_update[coin] = now 
            
            # RAM Yönetimi
            if len(self.data[coin]) > LIMIT_4S + 50:
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
    if price_str == "-" or price_str is None: return None
    clean_price = price_str.replace(" ", "_") 
    return f"{base_url}#etiket={clean_price}"

def get_paribu_link(coin): return f"https://www.paribu.com/markets/{coin.lower()}_tl"
def get_btcturk_link(coin): return f"https://kripto.btcturk.com/pro/al-sat/{coin.upper()}_TRY"
def get_binance_link(coin): return f"https://www.binance.com/en-TR/trade/{coin.upper()}_USDT"

# --- GÜVENLİ VERİ ÇEKME ---
def safe_get(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=4)
        if response.status_code == 200: return response.json()
    except: pass
    return None

# --- PARALEL VERİ ÇEKME MOTORU (YENİ OPTİMİZASYON) ---
def fetch_market_data_parallel(usdt_rate):
    """
    Tüm borsalara ve kurlara AYNI ANDA istek atar.
    Bu fonksiyon hızı 3 kat artırır.
    """
    p_dict, bt_dict, bin_dict = {}, {}, {}
    usdt_rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}

    def fetch_paribu():
        r = safe_get("https://www.paribu.com/ticker")
        data = {}
        u_rate = 0
        if r:
            u_rate = float(r.get("USDT_TL", {}).get('last', 0))
            for s, v in r.items():
                if "_TL" in s:
                    data[s.replace("_TL", "")] = {"price": float(v['last']), "change": float(v['percentChange'])}
        return data, u_rate

    def fetch_btcturk():
        r = safe_get("https://api.btcturk.com/api/v2/ticker")
        data = {}
        u_rate = 0 # BtcTurk USDT/TRY ayrıca çekilmesi gerekebilir ama burada basitleştiriyoruz
        if r:
            for i in r['data']:
                if i['pair'].endswith("TRY"):
                    data[i['pair'].replace("TRY", "")] = {"price": float(i['last']), "change": float(i['dailyPercent'])}
                if i['pair'] == "USDTTRY":
                    u_rate = float(i['last'])
        return data, u_rate

    def fetch_binance():
        r = safe_get("https://data-api.binance.vision/api/v3/ticker/24hr")
        data = {}
        if r:
            for i in r:
                if i['symbol'].endswith("USDT"):
                    data[i['symbol'].replace("USDT", "")] = {
                        "price_usd": float(i['lastPrice']),
                        "change": float(i['priceChangePercent'])
                    }
        return data
    
    def fetch_binance_usdt():
        r = safe_get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY")
        if r: return float(r['price'])
        return 34.50

    # Paralel Çalıştırma (Hızın Sırrı)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_paribu = executor.submit(fetch_paribu)
        f_btcturk = executor.submit(fetch_btcturk)
        f_binance = executor.submit(fetch_binance)
        f_usdt = executor.submit(fetch_binance_usdt)

        # Sonuçları Topla
        p_dict, usdt_rates["Paribu"] = f_paribu.result()
        bt_dict, usdt_rates["BtcTurk"] = f_btcturk.result()
        raw_binance = f_binance.result()
        usdt_rates["Binance"] = f_usdt.result()

    # Binance verilerini TL'ye çevir (Çekilen USDT kuruna göre)
    active_usdt_rate = usdt_rates["Binance"] if usdt_rates["Binance"] > 0 else 34.50
    
    for coin, val in raw_binance.items():
        bin_dict[coin] = {
            "price": val["price_usd"] * active_usdt_rate,
            "change": val["change"]
        }

    return p_dict, bt_dict, bin_dict, usdt_rates

# --- GRAFİK VERİSİ (ÜST PANEL) ---
@st.cache_data(ttl=300)
def get_chart_data(coin_symbol):
    charts = {"Paribu": [], "BtcTurk": [], "Binance": []}
    
    def get_bin_chart():
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={coin_symbol}USDT&interval=1h&limit=24"
        r = safe_get(url)
        return [float(x[4]) for x in r] if r else []

    def get_btc_chart():
        end_ts = int(time.time())
        start_ts = end_ts - (24 * 60 * 60)
        url = f"https://graph-api.btcturk.com/v1/klines/history?symbol={coin_symbol}TRY&resolution=60&from={start_ts}&to={end_ts}"
        r = safe_get(url)
        return [float(x) for x in r['c']] if r and 'c' in r else []

    def get_par_chart():
        url = f"https://www.paribu.com/dapi/v1/chart/{coin_symbol.lower()}_tl"
        r = safe_get(url)
        return [float(x[5]) for x in r[-24:]] if r else []

    # Grafikleri de paralel çekelim
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        charts["Binance"] = executor.submit(get_bin_chart).result()
        charts["BtcTurk"] = executor.submit(get_btc_chart).result()
        charts["Paribu"] = executor.submit(get_par_chart).result()

    return charts

# --- ANA PROGRAM ---
st.title("💎 Kripto Borsa Terminali")

uptime = havuz.get_uptime()
st.info(f"📡 **Ortak Veri Havuzu Aktif** | Sunucu Açık Kalma Süresi: **{uptime}** | Veriler kesintisiz biriktiriliyor.")

# Verileri Paralel Çek (Ana Fonksiyon)
p_d, b_d, bin_d, usdt = fetch_market_data_parallel(None) # None çünkü içinde çekiyoruz

# Kurlar
k1, k2, k3 = st.columns(3)
k1.metric("Paribu USDT", f"{usdt['Paribu']:.2f} ₺")
k2.metric("BtcTurk USDT", f"{usdt['BtcTurk']:.2f} ₺")
k3.metric("Binance USDT", f"{usdt['Binance']:.2f} ₺")

# --- GRAFİK ALANI ---
st.markdown("---")
grafik_col1, grafik_col2 = st.columns([1, 3])
with grafik_col1:
    secilen_grafik_coin = st.radio("Grafik Görüntüle:", ["BTC", "ETH"], horizontal=True)

charts = get_chart_data(secilen_grafik_coin)
g1, g2, g3 = st.columns(3)
with g1:
    st.markdown(f"<div class='chart-title'>Paribu ({secilen_grafik_coin}/TL)</div>", unsafe_allow_html=True)
    if charts["Paribu"]: st.line_chart(charts["Paribu"], height=150)
    else: st.caption("Veri Alınamadı")
with g2:
    st.markdown(f"<div class='chart-title'>BtcTurk ({secilen_grafik_coin}/TL)</div>", unsafe_allow_html=True)
    if charts["BtcTurk"]: st.line_chart(charts["BtcTurk"], height=150)
    else: st.caption("Veri Alınamadı")
with g3:
    st.markdown(f"<div class='chart-title'>Binance ({secilen_grafik_coin}/USDT)</div>", unsafe_allow_html=True)
    if charts["Binance"]: st.line_chart(charts["Binance"], height=150)
    else: st.caption("Veri Alınamadı")

st.markdown("---")

# --- KONTROL PANELİ ---
c1, c2 = st.columns([2, 2])
with c1: ana_borsa = st.radio("BORSA LİSTESİ:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
with c2: zaman = st.radio("ZAMAN DİLİMİ:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)

# ARAMA
arama_terimi = st.text_input("🔍 Coin Ara:", placeholder="Örn: BTC, AVAX, PEPE...").upper().strip()

# Listeyi Belirle
if ana_borsa == "Paribu": lst = list(p_d.keys())
elif ana_borsa == "BtcTurk": lst = list(b_d.keys())
else: lst = list(set(p_d.keys()) | set(b_d.keys()))

# Filtreleme
if arama_terimi:
    lst = [coin for coin in lst if arama_terimi in coin]

rows = []
for c in lst:
    try:
        ana_fiyat, hazir_24s_degisim = 0, 0.0
        # Güvenli veri çekimi (Get ile hata önleme)
        if ana_borsa == "Paribu": 
            data = p_d.get(c, {})
            ana_fiyat, hazir_24s_degisim = data.get('price', 0), data.get('change', 0)
        elif ana_borsa == "BtcTurk": 
            data = b_d.get(c, {})
            ana_fiyat, hazir_24s_degisim = data.get('price', 0), data.get('change', 0)
        else: 
            data = bin_d.get(c, {})
            ana_fiyat, hazir_24s_degisim = data.get('price', 0), data.get('change', 0)

        # HAVUZA EKLE (Kritik nokta)
        if ana_fiyat > 0: havuz.veri_ekle(c, ana_fiyat)

        # HESAPLAMA
        gosterilecek_degisim = 0.0
        gecmis_liste = havuz.get_gecmis(c)
        grafik_verisi = [] 

        if zaman == "24 Saat":
            gosterilecek_degisim = hazir_24s_degisim
            grafik_verisi = gecmis_liste
        elif zaman == "1 Saat":
            idx = -LIMIT_1S if len(gecmis_liste) >= LIMIT_1S else 0
            grafik_verisi = gecmis_liste[idx:] 
            if len(gecmis_liste) > 0 and gecmis_liste[idx] > 0:
                gosterilecek_degisim = ((ana_fiyat - gecmis_liste[idx]) / gecmis_liste[idx]) * 100
        elif zaman == "4 Saat":
            idx = -LIMIT_4S if len(gecmis_liste) >= LIMIT_4S else 0
            grafik_verisi = gecmis_liste[idx:] 
            if len(gecmis_liste) > 0 and gecmis_liste[idx] > 0:
                gosterilecek_degisim = ((ana_fiyat - gecmis_liste[idx]) / gecmis_liste[idx]) * 100

        pf = p_d.get(c, {}).get('price', 0)
        btf = b_d.get(c, {}).get('price', 0)
        binf = bin_d.get(c, {}).get('price', 0)

        rows.append({
            "Coin": c,
            "Ana Fiyat": kesin_format(ana_fiyat),
            "Değişim %": gosterilecek_degisim,
            "Trend": grafik_verisi,
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

    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Değişim", format="%.2f %%"),
        "Trend": st.column_config.LineChartColumn(f"Grafik ({zaman})", y_min=0, y_max=None),
        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        "Paribu": st.column_config.LinkColumn("Paribu (TL)", display_text=r"#etiket=(.*)"),
        "BtcTurk": st.column_config.LinkColumn("BtcTurk (TL)", display_text=r"#etiket=(.*)"),
        "Binance": st.column_config.LinkColumn("Binance (TL)", display_text=r"#etiket=(.*)"),
    }
    cols = ["Coin", "Ana Fiyat", "Değişim %", "Trend", "Paribu", "BtcTurk", "Binance"]

    st.dataframe(
        df[cols].style.apply(style_row, axis=1),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    kayit = 0
    if rows:
        ornek = rows[0]["Coin"]
        kayit = len(havuz.get_gecmis(ornek))
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Havuz Verisi: {kayit}")

else:
    if arama_terimi:
        st.warning(f"'{arama_terimi}' bulunamadı.")
    else:
        st.warning("Veriler yükleniyor... Lütfen bekleyin.")

time.sleep(YENILEME_HIZI)
st.rerun()