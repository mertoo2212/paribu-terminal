import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading
import streamlit.components.v1 as components

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Borsa Terminali vFinal",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded" # Admin panelini görmek için açık başlatıyoruz
)

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.0rem; }
    a { text-decoration: none !important; color: inherit !important; transition: all 0.2s; }
    a:hover { text-decoration: underline !important; color: #4CAF50 !important; }
    
    /* Sohbet Kutusu */
    .chat-box { height: 300px; overflow-y: auto; background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px; font-size: 0.9rem; }
    .chat-msg { margin-bottom: 4px; border-bottom: 1px solid #21262d; padding-bottom: 2px; }
    .chat-user { font-weight: bold; color: #58a6ff; }
    .chat-time { font-size: 0.7rem; color: #8b949e; margin-right: 5px; }
    
    /* Admin Paneli Kartları */
    .stat-card { background-color: #21262d; padding: 15px; border-radius: 8px; border-left: 4px solid #8b949e; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
LIMIT_4S = 960
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# --- MOTOR ---
@st.cache_resource
class DataEngine:
    def __init__(self):
        self.data = {}
        self.latest_prices = {}
        self.chat_log = []
        self.lock = threading.Lock()
        self.running = True
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.start_time = datetime.now()
        
        # Admin Ayarları
        self.config = {
            "active": {"Paribu": True, "BtcTurk": True, "Binance": True},
            "alarm_percent": 5.0
        }
        # Gecikme Takibi
        self.latency = {"Paribu": 0, "BtcTurk": 0, "Binance": 0}
        
        self.thread = threading.Thread(target=self._background_worker, daemon=True)
        self.thread.start()

    def _safe_get(self, url, source):
        start = time.time()
        try:
            response = self.session.get(url, timeout=4)
            lat = round((time.time() - start) * 1000)
            self.latency[source] = lat
            if response.status_code == 200: return response.json()
        except: 
            self.latency[source] = -1 # Hata
            return None
        return None

    def _background_worker(self):
        while self.running:
            try:
                usdt_rates = {"Binance": 34.50, "Paribu": 0, "BtcTurk": 0}
                # Binance Kurunu her zaman çekmeye çalış
                r = self._safe_get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY", "Binance")
                if r: usdt_rates["Binance"] = float(r['price'])
                
                temp_prices = {}

                # PARIBU
                if self.config["active"]["Paribu"]:
                    p_raw = self._safe_get("https://www.paribu.com/ticker", "Paribu")
                    if p_raw:
                        if "USDT_TL" in p_raw: usdt_rates["Paribu"] = float(p_raw["USDT_TL"]['last'])
                        for s, v in p_raw.items():
                            if "_TL" in s:
                                c = s.replace("_TL", "")
                                if c not in temp_prices: temp_prices[c] = {}
                                temp_prices[c]['paribu'] = {"price": float(v['last']), "change": float(v['percentChange'])}

                # BTCTURK
                if self.config["active"]["BtcTurk"]:
                    b_raw = self._safe_get("https://api.btcturk.com/api/v2/ticker", "BtcTurk")
                    if b_raw:
                        for i in b_raw.get('data', []):
                            if i['pair'] == "USDTTRY": usdt_rates["BtcTurk"] = float(i['last'])
                            if i['pair'].endswith("TRY"):
                                c = i['pair'].replace("TRY", "")
                                if c not in temp_prices: temp_prices[c] = {}
                                temp_prices[c]['btcturk'] = {"price": float(i['last']), "change": float(i['dailyPercent'])}

                # BINANCE
                if self.config["active"]["Binance"]:
                    bin_raw = self._safe_get("https://data-api.binance.vision/api/v3/ticker/24hr", "Binance")
                    if bin_raw:
                        active_usdt = usdt_rates["Binance"]
                        for i in bin_raw:
                            if i['symbol'].endswith("USDT"):
                                c = i['symbol'].replace("USDT", "")
                                if c in temp_prices:
                                    temp_prices[c]['binance'] = {
                                        "price": float(i['lastPrice']) * active_usdt,
                                        "change": float(i['priceChangePercent'])
                                    }

                with self.lock:
                    self.latest_prices = temp_prices
                    self.usdt_rates = usdt_rates
                    
                    for coin, markets in temp_prices.items():
                        price = 0
                        if 'paribu' in markets: price = markets['paribu']['price']
                        elif 'btcturk' in markets: price = markets['btcturk']['price']
                        elif 'binance' in markets: price = markets['binance']['price']
                        
                        if price > 0:
                            if coin not in self.data: self.data[coin] = []
                            self.data[coin].append(price)
                            if len(self.data[coin]) > LIMIT_4S + 20:
                                self.data[coin] = self.data[coin][-(LIMIT_4S + 20):]

            except Exception as e: print(f"Hata: {e}")
            time.sleep(15)

    # --- API Metodları ---
    def get_snapshot(self):
        with self.lock: return self.latest_prices.copy(), getattr(self, 'usdt_rates', {}), self.data.copy()

    def add_message(self, user, msg):
        with self.lock:
            t = datetime.now().strftime("%H:%M")
            self.chat_log.append({"time": t, "user": user, "msg": msg})
            if len(self.chat_log) > 50: self.chat_log.pop(0)
    
    def get_messages(self): return self.chat_log
    
    def clear_chat(self):
        with self.lock: self.chat_log = []
        
    def reset_memory(self):
        with self.lock: self.data = {}

    def get_uptime(self):
        return str(datetime.now() - self.start_time).split('.')[0]
    
    def get_latency(self): return self.latency
    
    def get_config(self): return self.config
    
    def update_config(self, key, val):
        with self.lock: self.config[key] = val

engine = DataEngine()

# --- FORMATLAMA ---
def fmt_price(val):
    if not val: return "-"
    if val < 1: return f"{val:.8f} ₺"
    if val < 10: return f"{val:.6f} ₺"
    return f"{val:.2f} ₺"

def make_link(base, price_str):
    if price_str == "-" or price_str is None: return None
    return f"{base}#etiket={price_str.replace(' ', '_')}"

# --- ARAYÜZ ---
st.title("💎 Ultra Borsa Terminali")

# NAVİGASYON (SORUN BURADAYDI - DÜZELDİ)
page = st.sidebar.radio("Menü", ["📊 Terminal", "🛠️ Admin Paneli"])

prices, usdt, history = engine.get_snapshot()
config = engine.get_config()

# ==================================================
# SAYFA 1: TERMİNAL (ANA EKRAN)
# ==================================================
if page == "📊 Terminal":
    if usdt:
        c1, c2, c3, c4 = st.columns(4)
        c1.info(f"📡 **Uptime:** {engine.get_uptime()}")
        c2.metric("Paribu USDT", f"{usdt.get('Paribu', 0):.2f} ₺")
        c3.metric("BtcTurk USDT", f"{usdt.get('BtcTurk', 0):.2f} ₺")
        c4.metric("Binance USDT", f"{usdt.get('Binance', 34.5):.2f} ₺")
    else:
        st.warning("Veriler yükleniyor...")

    st.markdown("---")

    col_main, col_side = st.columns([3, 1])

    with col_side:
        st.subheader("💬 Sohbet")
        msgs = engine.get_messages()
        chat_html = "<div class='chat-box'>"
        for m in reversed(msgs):
            chat_html += f"<div class='chat-msg'><span class='chat-time'>{m['time']}</span> <span class='chat-user'>{m['user']}:</span> {m['msg']}</div>"
        chat_html += "</div>"
        st.markdown(chat_html, unsafe_allow_html=True)
        
        with st.form("chat_form", clear_on_submit=True):
            u_name = st.text_input("İsim", "Anonim", label_visibility="collapsed", placeholder="İsim")
            u_msg = st.text_input("Mesaj", label_visibility="collapsed", placeholder="Mesaj yaz...")
            if st.form_submit_button("Gönder"):
                if u_msg: engine.add_message(u_name, u_msg)
                st.rerun()

    with col_main:
        tv_coin = st.text_input("Grafik Sembolü:", "BTC").upper()
        html_code = f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%", "height": 450, "symbol": "BINANCE:{tv_coin}USDT",
            "interval": "60", "timezone": "Etc/UTC", "theme": "dark", "style": "1",
            "locale": "tr", "enable_publishing": false, "allow_symbol_change": true,
            "container_id": "tradingview_chart"
          }});
          </script>
        </div>
        """
        components.html(html_code, height=460)

    st.markdown("---")

    c1, c2, c3 = st.columns([2, 2, 4])
    with c1: ana_borsa = st.radio("Borsa:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
    with c2: zaman = st.radio("Zaman:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)
    with c3: arama = st.text_input("Filtrele", placeholder="Coin ara (Örn: AVAX)", label_visibility="collapsed").upper()

    rows = []
    alarm_coins = []
    coin_list = sorted(prices.keys()) if prices else []

    for c in coin_list:
        if arama and arama not in c: continue

        p_data = prices[c].get('paribu', {})
        bt_data = prices[c].get('btcturk', {})
        bin_data = prices[c].get('binance', {})

        main_price = 0
        disp_change = 0.0
        
        if ana_borsa == "Paribu":
            main_price = p_data.get('price', 0)
            disp_change = p_data.get('change', 0)
        elif ana_borsa == "BtcTurk":
            main_price = bt_data.get('price', 0)
            disp_change = bt_data.get('change', 0)
        else:
            main_price = bin_data.get('price', 0)
            disp_change = bin_data.get('change', 0)

        chart_data = []
        if c in history and len(history[c]) > 0:
            hist = history[c]
            limit = 240 if zaman == "1 Saat" else 960
            if zaman != "24 Saat":
                idx = -limit if len(hist) >= limit else 0
                if len(hist) > 0 and hist[idx] > 0:
                    disp_change = ((main_price - hist[idx]) / hist[idx]) * 100
                chart_data = hist[idx:]
            else:
                chart_data = hist

        if abs(disp_change) >= config["alarm_percent"]: alarm_coins.append(c)

        rows.append({
            "Coin": c,
            "Ana Fiyat": fmt_price(main_price),
            "Değişim %": disp_change,
            "Trend": chart_data,
            "Paribu": make_link(f"https://www.paribu.com/markets/{c.lower()}_tl", fmt_price(p_data.get('price', 0))),
            "BtcTurk": make_link(f"https://kripto.btcturk.com/pro/al-sat/{c}_TRY", fmt_price(bt_data.get('price', 0))),
            "Binance": make_link(f"https://www.binance.com/en-TR/trade/{c}_USDT", fmt_price(bin_data.get('price', 0)))
        })

    if rows:
        df = pd.DataFrame(rows).sort_values(by="Değişim %", ascending=False)
        
        def style_row(row):
            s = [''] * len(row)
            ch = row["Değişim %"]
            s[1] = 'color: white; font-weight: bold;'
            if ch > 0: s[2] = 'color: #00ff00; font-weight: bold;'
            elif ch < 0: s[2] = 'color: #ff4444; font-weight: bold;'
            s[4] = 'color: #2e7d32; font-weight: bold;'
            s[5] = 'color: #1565c0; font-weight: bold;'
            s[6] = 'color: #ffd700; font-weight: bold;'
            return s

        st.dataframe(
            df[["Coin", "Ana Fiyat", "Değişim %", "Trend", "Paribu", "BtcTurk", "Binance"]].style.apply(style_row, axis=1),
            column_config={
                "Coin": st.column_config.TextColumn("Coin"),
                "Değişim %": st.column_config.NumberColumn(f"{zaman} %", format="%.2f %%"),
                "Trend": st.column_config.LineChartColumn("Trend", y_min=0, y_max=None),
                "Ana Fiyat": st.column_config.TextColumn(f"🔥 {ana_borsa}"),
                "Paribu": st.column_config.LinkColumn("Paribu", display_text=r"#etiket=(.*)"),
                "BtcTurk": st.column_config.LinkColumn("BtcTurk", display_text=r"#etiket=(.*)"),
                "Binance": st.column_config.LinkColumn("Binance", display_text=r"#etiket=(.*)"),
            },
            use_container_width=True, height=800, hide_index=True
        )
        
        if alarm_coins:
            st.toast(f"🚨 Hareket: {', '.join(alarm_coins[:5])}", icon="🔥")
    else:
        st.info("Veriler hazırlanıyor...")

# ==================================================
# SAYFA 2: ADMIN PANELİ
# ==================================================
elif page == "🛠️ Admin Paneli":
    st.header("🛠️ Yönetim Merkezi")
    
    tab1, tab2 = st.tabs(["📡 Sistem Sağlığı", "⚙️ Ayarlar"])
    
    lat = engine.get_latency()
    
    with tab1:
        c1, c2, c3 = st.columns(3)
        
        def metric_card(label, val):
            color = "green" if val < 500 and val != -1 else "red"
            status = f"{val} ms" if val != -1 else "HATA"
            st.markdown(f"""<div class='stat-card' style='border-left: 4px solid {color}'><div style='color:#888'>{label}</div><div style='font-size:20px;font-weight:bold'>{status}</div></div>""", unsafe_allow_html=True)

        with c1: metric_card("Paribu Gecikme", lat["Paribu"])
        with c2: metric_card("BtcTurk Gecikme", lat["BtcTurk"])
        with c3: metric_card("Binance Gecikme", lat["Binance"])
        
        st.divider()
        st.markdown("### 🧹 Temizlik İşlemleri")
        c_chat, c_mem = st.columns(2)
        if c_chat.button("Sohbet Geçmişini Sil"):
            engine.clear_chat()
            st.success("Sohbet temizlendi.")
        if c_mem.button("⚠️ Hafızayı Sıfırla"):
            engine.reset_memory()
            st.warning("Hafıza sıfırlandı.")

    with tab2:
        st.markdown("### 🔔 Alarm Ayarı")
        new_pct = st.slider("Genel Alarm Yüzdesi", 1.0, 20.0, config["alarm_percent"])
        
        st.markdown("### 🔌 Borsa Bağlantıları")
        act = config["active"]
        p_act = st.toggle("Paribu", value=act["Paribu"])
        bt_act = st.toggle("BtcTurk", value=act["BtcTurk"])
        bin_act = st.toggle("Binance", value=act["Binance"])
        
        if st.button("Ayarları Kaydet"):
            engine.update_config("alarm_percent", new_pct)
            engine.update_config("active", {"Paribu": p_act, "BtcTurk": bt_act, "Binance": bin_act})
            st.success("Ayarlar kaydedildi!")

time.sleep(1) 
st.rerun()