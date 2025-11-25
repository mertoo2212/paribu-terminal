import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading
import concurrent.futures 

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Borsa Terminali v2.0",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS OPTİMİZASYONU ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    /* Tablo yazı tipi ve hizalaması */
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.02rem; }
    /* Linkler */
    a { text-decoration: none !important; color: inherit !important; transition: all 0.2s; }
    a:hover { text-decoration: underline !important; color: #4CAF50 !important; }
    /* Metrik Kutuları */
    div[data-testid="stMetric"] { background-color: #161b22; border-radius: 8px; padding: 10px; border: 1px solid #30363d; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    /* Grafik Başlıkları */
    .chart-title { text-align: center; font-size: 0.9rem; font-weight: bold; margin-bottom: 5px; color: #8b949e; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
YENILEME_HIZI = 15 
LIMIT_1S = 240     
LIMIT_4S = 960     

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# --- ORTAK HAVUZ (Thread-Safe Singleton) ---
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
            # 14 saniye kuralı (Çakışma ve Gereksiz Yazma Önleyici)
            if coin in self.last_update:
                if (now - self.last_update[coin]) < 14: return 

            if coin not in self.data: self.data[coin] = []
            
            if fiyat > 0:
                self.data[coin].append(fiyat)
                self.last_update[coin] = now 
            
            # RAM Temizliği: Gereksiz veriyi tutma
            limit = LIMIT_4S + 20
            if len(self.data[coin]) > limit:
                # Performans için dilimleme kullanıyoruz
                self.data[coin] = self.data[coin][-limit:]

    def get_gecmis(self, coin):
        return self.data.get(coin, [])
    
    def get_uptime(self):
        delta = datetime.now() - self.baslangic
        return str(delta).split('.')[0] 

havuz = OrtakHafiza()

# --- FORMATLAMA YARDIMCILARI ---
def kesin_format(fiyat):
    if not isinstance(fiyat, (int, float)) or fiyat == 0: return "-" 
    if fiyat < 1: return "{:.8f} ₺".format(fiyat)
    elif fiyat < 10: return "{:.6f} ₺".format(fiyat)
    else: return "{:,.2f} ₺".format(fiyat)

def make_link(base_url, price_str):
    if price_str == "-" or price_str is None: return None
    return f"{base_url}#etiket={price_str.replace(' ', '_')}"

def get_paribu_link(coin): return f"https://www.paribu.com/markets/{coin.lower()}_tl"
def get_btcturk_link(coin): return f"https://kripto.btcturk.com/pro/al-sat/{coin.upper()}_TRY"
def get_binance_link(coin): return f"https://www.binance.com/en-TR/trade/{coin.upper()}_USDT"

# --- AĞ İŞLEMLERİ (NETWORK LAYER) ---
def safe_get(url):
    """Hata korumalı, zaman aşımlı HTTP isteği."""
    try:
        # Timeout 5sn idealdir, fazlası siteyi dondurur
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200: return response.json()
    except: 
        return None

def fetch_market_data_parallel():
    """Tüm borsa verilerini paralel (aynı anda) çeker."""
    p_dict, bt_dict, bin_dict = {}, {}, {}
    usdt_rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}

    # Alt fonksiyonlar (İşçiler)
    def fetch_paribu():
        r = safe_get("https://www.paribu.com/ticker")
        d, u = {}, 0
        if r:
            u = float(r.get("USDT_TL", {}).get('last', 0))
            for s, v in r.items():
                if "_TL" in s: d[s.replace("_TL", "")] = {"price": float(v['last']), "change": float(v['percentChange'])}
        return d, u

    def fetch_btcturk():
        r = safe_get("https://api.btcturk.com/api/v2/ticker")
        d, u = {}, 0
        if r:
            for i in r.get('data', []):
                if i['pair'].endswith("TRY"): d[i['pair'].replace("TRY", "")] = {"price": float(i['last']), "change": float(i['dailyPercent'])}
                if i['pair'] == "USDTTRY": u = float(i['last'])
        return d, u

    def fetch_binance():
        r = safe_get("https://data-api.binance.vision/api/v3/ticker/24hr")
        d = {}
        if r:
            for i in r:
                if i['symbol'].endswith("USDT"):
                    d[i['symbol'].replace("USDT", "")] = {"price_usd": float(i['lastPrice']), "change": float(i['priceChangePercent'])}
        return d
    
    def fetch_binance_usdt():
        r = safe_get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY")
        return float(r['price']) if r else 34.50

    # Paralel Yürütme
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(fetch_paribu)
        f2 = executor.submit(fetch_btcturk)
        f3 = executor.submit(fetch_binance)
        f4 = executor.submit(fetch_binance_usdt)

        p_dict, usdt_rates["Paribu"] = f1.result()
        bt_dict, usdt_rates["BtcTurk"] = f2.result()
        raw_binance = f3.result()
        usdt_rates["Binance"] = f4.result()

    # Binance TL Çevrimi
    active_usdt = usdt_rates["Binance"] if usdt_rates["Binance"] > 0 else 34.50
    for c, v in raw_binance.items():
        bin_dict[c] = {"price": v["price_usd"] * active_usdt, "change": v["change"]}

    return p_dict, bt_dict, bin_dict, usdt_rates

@st.cache_data(ttl=300)
def get_chart_data(coin_symbol):
    charts = {"Paribu": [], "BtcTurk": [], "Binance": []}
    
    def get_bin():
        r = safe_get(f"https://data-api.binance.vision/api/v3/klines?symbol={coin_symbol}USDT&interval=1h&limit=24")
        return [float(x[4]) for x in r] if r else []
    def get_btc():
        ts = int(time.time())
        r = safe_get(f"https://graph-api.btcturk.com/v1/klines/history?symbol={coin_symbol}TRY&resolution=60&from={ts-86400}&to={ts}")
        return [float(x) for x in r['c']] if r and 'c' in r else []
    def get_par():
        r = safe_get(f"https://www.paribu.com/dapi/v1/chart/{coin_symbol.lower()}_tl")
        return [float(x[5]) for x in r[-24:]] if r else []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        charts["Binance"] = ex.submit(get_bin).result()
        charts["BtcTurk"] = ex.submit(get_btc).result()
        charts["Paribu"] = ex.submit(get_par).result()
    return charts

# --- ARAYÜZ (UI) ---
st.title("💎 Kripto Borsa Terminali")

# Veri Çekme
p_d, b_d, bin_d, usdt = fetch_market_data_parallel()

# Üst Bilgi
c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
c1.info(f"📡 **Uptime:** {havuz.get_uptime()}")
c2.metric("Paribu USDT", f"{usdt['Paribu']:.2f} ₺")
c3.metric("BtcTurk USDT", f"{usdt['BtcTurk']:.2f} ₺")
c4.metric("Binance USDT", f"{usdt['Binance']:.2f} ₺")

st.markdown("---")

# Grafik Alanı
grafik_col1, grafik_col2 = st.columns([1, 4])
with grafik_col1:
    secilen_grafik_coin = st.radio("Grafik:", ["BTC", "ETH"], horizontal=True)

charts = get_chart_data(secilen_grafik_coin)
g1, g2, g3 = st.columns(3)
for col, borsa in zip([g1, g2, g3], ["Paribu", "BtcTurk", "Binance"]):
    with col:
        label = f"{borsa} ({secilen_grafik_coin})"
        st.markdown(f"<div class='chart-title'>{label}</div>", unsafe_allow_html=True)
        if charts[borsa]: st.line_chart(charts[borsa], height=120)
        else: st.warning("-")

st.markdown("---")

# Kontrol Paneli
col_b, col_z = st.columns([1, 1])
with col_b: ana_borsa = st.radio("ANA BORSA:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
with col_z: zaman = st.radio("PERİYOT:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)

arama = st.text_input("🔍 Filtrele:", placeholder="Coin ara...").upper().strip()

# Liste Oluşturma
if ana_borsa == "Paribu": full_list = list(p_d.keys())
elif ana_borsa == "BtcTurk": full_list = list(b_d.keys())
else: full_list = list(set(p_d.keys()) | set(b_d.keys()))

rows = []
for c in full_list:
    try:
        # Verileri Güvenli Al
        data_ana = (p_d if ana_borsa == "Paribu" else b_d if ana_borsa == "BtcTurk" else bin_d).get(c, {})
        ana_fiyat = data_ana.get('price', 0)
        hazir_degisim = data_ana.get('change', 0)

        # Havuza Kayıt (Filtreden Bağımsız)
        if ana_fiyat > 0: havuz.veri_ekle(c, ana_fiyat)

        # Filtre Kontrolü
        if arama and (arama not in c): continue

        # Hesaplamalar
        gosterilecek_degisim = 0.0
        gecmis = havuz.get_gecmis(c)
        grafik_data = []

        if zaman == "24 Saat":
            gosterilecek_degisim = hazir_24s_degisim
            grafik_data = gecmis
        else:
            limit = LIMIT_1S if zaman == "1 Saat" else LIMIT_4S
            idx = -limit if len(gecmis) >= limit else 0
            grafik_data = gecmis[idx:]
            
            if len(gecmis) > 0 and gecmis[idx] > 0:
                gosterilecek_degisim = ((ana_fiyat - gecmis[idx]) / gecmis[idx]) * 100

        # Diğer Fiyatlar
        pf = p_d.get(c, {}).get('price', 0)
        btf = b_d.get(c, {}).get('price', 0)
        binf = bin_d.get(c, {}).get('price', 0)

        rows.append({
            "Coin": c,
            "Ana Fiyat": kesin_format(ana_fiyat),
            "Değişim %": gosterilecek_degisim,
            "Trend": grafik_data,
            "Paribu": make_link(get_paribu_link(c), kesin_format(pf)),
            "BtcTurk": make_link(get_btcturk_link(c), kesin_format(btf)),
            "Binance": make_link(get_binance_link(c), kesin_format(binf))
        })
    except: continue

if rows:
    df = pd.DataFrame(rows).sort_values(by="Değişim %", ascending=False)
    
    def style_row(row):
        s = [''] * len(row)
        ch = row["Değişim %"]
        s[1] = 'color: white; font-weight: bold;' # Ana Fiyat
        if ch > 0: s[2] = 'color: #00ff00; font-weight: bold;'
        elif ch < 0: s[2] = 'color: #ff4444; font-weight: bold;'
        s[4] = 'color: #2e7d32; font-weight: bold;' # Paribu
        s[5] = 'color: #1565c0; font-weight: bold;' # BtcTurk
        s[6] = 'color: #ffd700; font-weight: bold;' # Binance
        return s

    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} %", format="%.2f %%"),
        "Trend": st.column_config.LineChartColumn(f"Grafik", y_min=0, y_max=None),
        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa}"),
        "Paribu": st.column_config.LinkColumn("Paribu", display_text=r"#etiket=(.*)"),
        "BtcTurk": st.column_config.LinkColumn("BtcTurk", display_text=r"#etiket=(.*)"),
        "Binance": st.column_config.LinkColumn("Binance", display_text=r"#etiket=(.*)"),
    }
    
    st.dataframe(
        df[["Coin", "Ana Fiyat", "Değişim %", "Trend", "Paribu", "BtcTurk", "Binance"]].style.apply(style_row, axis=1),
        column_config=column_config,
        use_container_width=True,
        height=800,
        hide_index=True
    )
    
    cnt = len(havuz.get_gecmis(rows[0]["Coin"])) if rows else 0
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Havuz: {cnt} Veri")
else:
    st.info("Veriler yükleniyor... (Eğer uzun sürerse sayfayı yenileyin)")

time.sleep(YENILEME_HIZI)
st.rerun()