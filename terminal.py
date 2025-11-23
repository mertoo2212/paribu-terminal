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

# --- CSS (Görünüm) ---
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

# --- LİNK OLUŞTURUCULAR (Güncellenmiş Adresler) ---
def make_link(base_url, price_str):
    if price_str == "-": return None
    # Boşlukları _ ile değiştiriyoruz ki URL bozulmasın
    clean_price = price_str.replace(" ", "_") 
    return f"{base_url}#etiket={clean_price}"

def get_paribu_link(coin):
    # DÜZELTME: -tl yerine _tl yapıldı
    return f"https://www.paribu.com/markets/{coin.lower()}_tl"

def get_btcturk_link(coin):
    # DÜZELTME: pro.btcturk yerine kripto.btcturk yapıldı
    return f"https://kripto.btcturk.com/pro/al-sat/{coin.upper()}_TRY"

def get_binance_link(coin):
    return f"https://www.binance.com/en-TR/trade/{coin.upper()}_USDT"

# --- VERİ ÇEKME ---
def get_usdt_rates():
    rates = {"Binance": 0, "Paribu": 0, "BtcTurk": 0}
    try:
        rates["Binance"] = float(requests.get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY", timeout=2).json()['price'])
    except: rates["Binance"] = 34.50
    try:
        resp = requests.get("https://www.paribu.com/ticker", timeout=2).json()
        rates["Paribu"] = float(resp["USDT_TL"]['last'])
    except: rates["Paribu"] = 0
    try:
        resp = requests.get("https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY", timeout=2).json()
        rates["BtcTurk"] = float(resp['data'][0]['last'])
    except: rates["BtcTurk"] = 0
    return rates

def get_all_market_data(usdt_rate_binance):
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
                    "price": float(i['lastPrice']) * usdt_rate_binance,
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

p_d, b_d, bin_d = get_all_market_data(usdt['Binance'])

# Liste Belirleme
if ana_borsa == "Paribu": lst = list(p_d.keys())
elif ana_borsa == "BtcTurk": lst = list(b_d.keys())
else: lst = list(set(p_d.keys()) | set(b_d.keys()))

rows = []
for c in lst:
    bf, bch = 0, 0.0
    if ana_borsa == "Paribu": bf, bch = p_d.get(c, {}).get('price', 0), p_d.get(c, {}).get('change', 0)
    elif ana_borsa == "BtcTurk": bf, bch = b_d.get(c, {}).get('price', 0), b_d.get(c, {}).get('change', 0)
    else: bf, bch = bin_d.get(c, {}).get('price', 0), bin_d.get(c, {}).get('change', 0)

    # Hafıza
    if c not in st.session_state.hafiza: st.session_state.hafiza[c] = []
    if bf > 0: st.session_state.hafiza[c].append(bf)
    if len(st.session_state.hafiza[c]) > LIMIT_4S+10: st.session_state.hafiza[c].pop(0)

    mem = st.session_state.hafiza[c]
    show_ch = 0.0
    if zaman == "24 Saat": show_ch = bch
    elif zaman == "1 Saat": 
        idx = -LIMIT_1S if len(mem) >= LIMIT_1S else 0
        if len(mem)>0 and mem[idx]>0: show_ch = ((mem[-1]-mem[idx])/mem[idx])*100
    elif zaman == "4 Saat":
        idx = -LIMIT_4S if len(mem) >= LIMIT_4S else 0
        if len(mem)>0 and mem[idx]>0: show_ch = ((mem[-1]-mem[idx])/mem[idx])*100

    # Diğer Borsa Fiyatları
    pf = p_d.get(c, {}).get('price', 0)
    btf = b_d.get(c, {}).get('price', 0)
    binf = bin_d.get(c, {}).get('price', 0)

    # String Formatlar
    str_pf = kesin_format(pf)
    str_btf = kesin_format(btf)
    str_binf = kesin_format(binf)

    rows.append({
        "Coin": c,
        "Ana Fiyat": kesin_format(bf),
        "Değişim %": show_ch,
        "Paribu": make_link(get_paribu_link(c), str_pf),
        "BtcTurk": make_link(get_btcturk_link(c), str_btf),
        "Binance": make_link(get_binance_link(c), str_binf)
    })

if rows:
    df = pd.DataFrame(rows).sort_values(by="Değişim %", ascending=False)
    
    # --- RENKLENDİRME ---
    def style_row(row):
        styles = [''] * len(row)
        ch = row["Değişim %"]
        
        # 1. Ana Fiyat: DAİMA BEYAZ
        styles[1] = 'color: white; font-weight: bold;'
        
        # 2. Değişim: Yeşil/Kırmızı
        if ch > 0: styles[2] = 'color: #00ff00; font-weight: bold;'
        elif ch < 0: styles[2] = 'color: #ff4444; font-weight: bold;'
        
        # 3. Paribu: Koyu Yeşil
        styles[3] = 'color: #2e7d32; font-weight: bold;'
        
        # 4. BtcTurk: Koyu Mavi (#1976D2 veya #1565C0)
        styles[4] = 'color: #1976d2; font-weight: bold;'
        
        # 5. Binance: Sarı / Gold
        styles[5] = 'color: #ffd700; font-weight: bold;'
        
        return styles

    # --- SÜTUN AYARLARI ---
    column_config = {
        "Coin": st.column_config.TextColumn("Coin"),
        "Değişim %": st.column_config.NumberColumn(f"{zaman} Değişim", format="%.2f %%"),
        "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa} (Ana)"),
        
        # Linklerin Görünümü (#etiket kısmını okuyup fiyatı yazdırıyoruz)
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
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')} | Fiyatlara tıklayarak borsaya gidebilirsiniz.")
else:
    st.error("Veri yok.")

time.sleep(YENILEME_HIZI)
st.rerun()