import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import concurrent.futures # Çoklu işlem için (Hızlandırıcı)

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
    /* Linklerin altındaki çizgi stili ve rengi */
    a { text-decoration: none !important; color: inherit !important; }
    a:hover { text-decoration: underline !important; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
YENILEME_HIZI = 30 # Geçmiş veriyi çekmek maliyetli olduğu için süreyi 30sn yaptık

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

# --- ZAMAN YOLCULUĞU MOTORU (GEÇMİŞ VERİYİ ÇEKME) ---
def get_historical_price(symbol, interval):
    """
    Binance API'sine bağlanıp geçmişteki mumu çeker.
    interval: '1h', '4h'
    """
    try:
        # data-api.binance.vision kullanarak geçmiş veriye erişiyoruz
        # limit=2 diyerek şimdiki ve bir önceki mumu istiyoruz
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit=2"
        resp = requests.get(url, timeout=2).json()
        
        # resp listesi [Eski Mum, Yeni Mum] şeklindedir.
        # Biz eski mumun "Açılış" (Open) fiyatını alıyoruz -> index 1
        # Veri formatı: [Open Time, Open, High, Low, Close, Volume ...]
        old_candle = resp[0]
        open_price = float(old_candle[1]) # Mumun açılış fiyatı
        return open_price
    except:
        return 0

def fetch_history_parallel(coin_list, interval):
    """
    Tek tek sorarsak site donar. Burada 20 işçi (worker) tutup
    hepsini aynı anda geçmişe gönderiyoruz.
    """
    results = {}
    
    def task(coin):
        return coin, get_historical_price(coin, interval)

    # ThreadPool ile paralel işlem
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        # İşleri dağıt
        future_to_coin = {executor.submit(task, coin): coin for coin in coin_list}
        # İşler bittikçe sonuçları topla
        for future in concurrent.futures.as_completed(future_to_coin):
            coin, price = future.result()
            results[coin] = price
            
    return results

# --- ANLIK VERİ ÇEKME ---
def get_usdt_rates():
    rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}
    try: rates["Binance"] = float(requests.get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY", timeout=2).json()['price'])
    except: rates["Binance"] = 34.50
    try: 
        r = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        rates["Paribu"] = float(r["USDT_TL"]['last'])
    except: rates["Paribu"] = 0
    try: 
        r = requests.get("https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY", timeout=2).json()
        rates["BtcTurk"] = float(r['data'][0]['last'])
    except: rates["BtcTurk"] = 0
    return rates

def get_live_data(usdt_rate):
    p_dict, bt_dict, bin_dict = {}, {}, {}
    # Paribu
    try:
        r = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        for s, v in r.items():
            if "_TL" in s:
                p_dict[s.replace("_TL", "")] = float(v['last'])
    except: pass
    # BtcTurk
    try:
        r = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=2).json()
        for i in r['data']:
            if i['pair'].endswith("TRY"):
                bt_dict[i['pair'].replace("TRY", "")] = float(i['last'])
    except: pass
    # Binance (Canlı + 24s Değişim)
    bin_change = {}
    try:
        r = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=3).json()
        for i in r:
            if i['symbol'].endswith("USDT"):
                c = i['symbol'].replace("USDT", "")
                bin_dict[c] = float(i['lastPrice']) * usdt_rate
                bin_change[c] = float(i['priceChangePercent'])
    except: pass
    
    return p_dict, bt_dict, bin_dict, bin_change

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

# Canlı verileri çek
p_prices, bt_prices, bin_prices, bin_24h_change = get_live_data(usdt['Binance'])

# Listeyi Belirle
if ana_borsa == "Paribu": lst = list(p_prices.keys())
elif ana_borsa == "BtcTurk": lst = list(bt_prices.keys())
else: lst = list(set(p_prices.keys()) | set(bt_prices.keys()))

# --- ZAMAN MAKİNESİ MANTIĞI ---
# 1s ve 4s seçilirse geçmiş veriyi Binance'den sorgula
# 24s seçilirse hazır veriyi kullan

trend_data = {} # Her coinin değişim oranını tutacak

if zaman == "24 Saat":
    # 24 Saat için sorguya gerek yok, API zaten veriyor
    trend_data = bin_24h_change
else:
    # 1 veya 4 saat için geçmişe gitmemiz lazım
    interval = "1h" if zaman == "1 Saat" else "4h"
    
    # Session State (Önbellek) kullanarak gereksiz sorguları engelle
    # Sadece zaman dilimi değiştiğinde veya 1 dakika geçtiğinde tekrar sorgula
    cache_key = f"history_{interval}"
    should_refresh = False
    
    if cache_key not in st.session_state:
        should_refresh = True
    elif (time.time() - st.session_state.get(f"{cache_key}_time", 0)) > 60:
        should_refresh = True
    
    if should_refresh:
        with st.spinner(f"🚀 {zaman} önceki fiyatlar arşivden çekiliyor..."):
            st.session_state[cache_key] = fetch_history_parallel(lst, interval)
            st.session_state[f"{cache_key}_time"] = time.time()
            
    history_prices = st.session_state[cache_key]
    
    # Değişimleri Hesapla
    for c in lst:
        current_usd = bin_prices.get(c, 0) / usdt['Binance'] if usdt['Binance'] > 0 else 0
        past_usd = history_prices.get(c, 0)
        
        if current_usd > 0 and past_usd > 0:
            change = ((current_usd - past_usd) / past_usd) * 100
            trend_data[c] = change
        else:
            trend_data[c] = 0.0

# --- TABLOYU OLUŞTUR ---
rows = []
for c in lst:
    # Fiyatları Hazırla
    bf = 0
    if ana_borsa == "Paribu": bf = p_prices.get(c, 0)
    elif ana_borsa == "BtcTurk": bf = bt_prices.get(c, 0)
    else: bf = bin_prices.get(c, 0)

    pf = p_prices.get(c, 0)
    btf = bt_prices.get(c, 0)
    binf = bin_prices.get(c, 0)
    
    # Hesaplanan değişimi al
    show_ch = trend_data.get(c, 0.0)

    rows.append({
        "Coin": c,
        "Ana Fiyat": kesin_format(bf),
        "Değişim %": show_ch,
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

    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Trendi", format="%.2f %%"),
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
    
    # Bilgilendirme notu
    kaynak_notu = "Binance Global Arşivi" if zaman != "24 Saat" else "Borsa Verisi"
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Veri Kaynağı: {kaynak_notu}")
else:
    st.error("Veriler yükleniyor veya API yanıt vermiyor. Lütfen bekleyin...")

time.sleep(YENILEME_HIZI)
st.rerun()