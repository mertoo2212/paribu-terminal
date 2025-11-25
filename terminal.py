import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import threading
import streamlit.components.v1 as components

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Ultra Borsa Terminali vPro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stDataFrame"] { font-family: 'Consolas', 'Courier New', monospace; font-size: 1.0rem; }
    a { text-decoration: none !important; color: inherit !important; transition: all 0.2s; }
    a:hover { text-decoration: underline !important; color: #4CAF50 !important; }
    
    /* Panel Stilleri */
    .admin-card { background-color: #21262d; padding: 15px; border-radius: 10px; border-left: 4px solid #58a6ff; margin-bottom: 10px; }
    .success-stat { color: #4CAF50; font-weight: bold; font-size: 1.2rem; }
    .chart-title { text-align: center; font-size: 0.9rem; font-weight: bold; margin-bottom: 5px; color: #8b949e; }
    </style>
    """, unsafe_allow_html=True)

# --- SABİTLER ---
LIMIT_4S = 960
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# --- MOTOR VE HAFIZA ---
@st.cache_resource
class DataEngine:
    def __init__(self):
        self.data = {}
        self.latest_prices = {}
        self.lock = threading.Lock()
        self.running = True
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.start_time = datetime.now()
        
        # --- YENİ: ALARM AYARLARI ---
        self.alarm_rules = {
            "percentage": 5.0,        # Varsayılan %5
            "ignored_coins": ["USDT", "USDC", "BUSD"], # Görmezden gelinecekler
            "price_targets": {}       # { 'BTC': 100000 } gibi hedef fiyatlar
        }
        
        self.thread = threading.Thread(target=self._background_worker, daemon=True)
        self.thread.start()

    def _safe_get(self, url):
        try:
            response = self.session.get(url, timeout=4)
            if response.status_code == 200: return response.json()
        except: return None
        return None

    def _background_worker(self):
        while self.running:
            try:
                usdt_rates = {"Binance": 34.50, "Paribu": 0, "BtcTurk": 0}
                r = self._safe_get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTTRY")
                if r: usdt_rates["Binance"] = float(r['price'])
                
                p_raw = self._safe_get("https://www.paribu.com/ticker")
                b_raw = self._safe_get("https://api.btcturk.com/api/v2/ticker")
                bin_raw = self._safe_get("https://data-api.binance.vision/api/v3/ticker/24hr")

                temp_prices = {}

                if p_raw:
                    if "USDT_TL" in p_raw: usdt_rates["Paribu"] = float(p_raw["USDT_TL"]['last'])
                    for s, v in p_raw.items():
                        if "_TL" in s:
                            coin = s.replace("_TL", "")
                            if coin not in temp_prices: temp_prices[coin] = {}
                            temp_prices[coin]['paribu'] = {"price": float(v['last']), "change": float(v['percentChange'])}

                if b_raw:
                    for i in b_raw.get('data', []):
                        if i['pair'] == "USDTTRY": usdt_rates["BtcTurk"] = float(i['last'])
                        if i['pair'].endswith("TRY"):
                            coin = i['pair'].replace("TRY", "")
                            if coin not in temp_prices: temp_prices[coin] = {}
                            temp_prices[coin]['btcturk'] = {"price": float(i['last']), "change": float(i['dailyPercent'])}

                if bin_raw:
                    active_usdt = usdt_rates["Binance"]
                    for i in bin_raw:
                        if i['symbol'].endswith("USDT"):
                            coin = i['symbol'].replace("USDT", "")
                            if coin in temp_prices:
                                temp_prices[coin]['binance'] = {
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

    def get_snapshot(self):
        with self.lock:
            return self.latest_prices.copy(), getattr(self, 'usdt_rates', {}), self.data.copy()

    def get_uptime(self):
        return str(datetime.now() - self.start_time).split('.')[0]

    # --- ALARM YÖNETİMİ ---
    def update_alarm_rules(self, percentage, ignored_list, targets):
        with self.lock:
            self.alarm_rules["percentage"] = percentage
            self.alarm_rules["ignored_coins"] = ignored_list
            self.alarm_rules["price_targets"] = targets

    def get_alarm_rules(self):
        with self.lock:
            return self.alarm_rules.copy()

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

# Yan Menü: Navigasyon
page = st.sidebar.radio("Menü", ["📊 Terminal", "🛠️ Kontrol Paneli"])

prices, usdt, history = engine.get_snapshot()
alarm_config = engine.get_alarm_rules()

# -------------------------
# SAYFA 1: TERMİNAL (ANA EKRAN)
# -------------------------
if page == "📊 Terminal":
    
    # Üst Bilgi
    if usdt:
        c1, c2, c3, c4 = st.columns(4)
        c1.info(f"📡 **Uptime:** {engine.get_uptime()}")
        c2.metric("Paribu USDT", f"{usdt.get('Paribu', 0):.2f} ₺")
        c3.metric("BtcTurk USDT", f"{usdt.get('BtcTurk', 0):.2f} ₺")
        c4.metric("Binance USDT", f"{usdt.get('Binance', 34.5):.2f} ₺")
    else:
        st.warning("Motor başlatılıyor...")

    st.markdown("---")

    # Grafik
    col_main, col_side = st.columns([3, 1])
    with col_main:
        tv_coin = st.text_input("Grafik Sembolü:", "BTC").upper()
        html_code = f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%", "height": 400, "symbol": "BINANCE:{tv_coin}USDT",
            "interval": "60", "timezone": "Etc/UTC", "theme": "dark", "style": "1",
            "locale": "tr", "enable_publishing": false, "allow_symbol_change": true,
            "container_id": "tradingview_chart"
          }});
          </script>
        </div>
        """
        components.html(html_code, height=410)
    
    with col_side:
        st.markdown("### 🔥 Aktif Alarmlar")
        # Alarm Kontrolü ve Listeleme
        active_alarms = []
        limit_pct = alarm_config["percentage"]
        ignored = alarm_config["ignored_coins"]
        targets = alarm_config["price_targets"]

        for c, data in prices.items():
            if c in ignored: continue
            
            # Fiyatı al (Paribu öncelikli)
            p_p = data.get('paribu', {}).get('price', 0)
            price = p_p if p_p > 0 else data.get('binance', {}).get('price', 0)
            
            if price == 0: continue

            # 1. Yüzde Kontrolü
            if c in history and len(history[c]) > 0:
                # Son 1 saati kontrol et
                idx = -240 if len(history[c]) >= 240 else 0
                if history[c][idx] > 0:
                    change = ((price - history[c][idx]) / history[c][idx]) * 100
                    if abs(change) >= limit_pct:
                        icon = "🚀" if change > 0 else "🔻"
                        active_alarms.append(f"{icon} **{c}**: %{change:.2f}")

            # 2. Fiyat Hedefi Kontrolü
            if c in targets:
                target_p = targets[c]
                if price >= target_p:
                    active_alarms.append(f"🎯 **{c}** Hedefi Geçti: {fmt_price(price)}")

        if active_alarms:
            for alarm in active_alarms[:5]: # Max 5 alarm göster
                st.error(alarm)
        else:
            st.success("Şu an kritik bir hareket yok.")
            st.caption(f"Alarm Limiti: %{limit_pct}")

    st.markdown("---")

    # Tablo Kontrolleri
    c1, c2, c3 = st.columns([2, 2, 4])
    with c1: ana_borsa = st.radio("Borsa:", ["Paribu", "BtcTurk", "Binance"], horizontal=True)
    with c2: zaman = st.radio("Zaman:", ["1 Saat", "4 Saat", "24 Saat"], horizontal=True)
    with c3: arama = st.text_input("Filtrele", placeholder="Coin ara...", label_visibility="collapsed").upper()

    # Tablo Oluşturma
    rows = []
    coin_list = sorted(prices.keys()) if prices else []

    for c in coin_list:
        if arama and arama not in c: continue

        p_data = prices[c].get('paribu', {})
        bt_data = prices[c].get('btcturk', {})
        bin_data = prices[c].get('binance', {})

        main_price, disp_change = 0, 0.0
        
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
            if zaman != "24 Saat":
                limit = 240 if zaman == "1 Saat" else 960
                idx = -limit if len(hist) >= limit else 0
                if len(hist) > 0 and hist[idx] > 0:
                    disp_change = ((main_price - hist[idx]) / hist[idx]) * 100
                chart_data = hist[idx:]
            else:
                chart_data = hist

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
    
    time.sleep(1)
    st.rerun()

# -------------------------
# SAYFA 2: KONTROL PANELİ (YENİ)
# -------------------------
elif page == "🛠️ Kontrol Paneli":
    st.header("🛠️ Sistem ve Alarm Kontrol Merkezi")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ⚙️ Genel Alarm Ayarları")
        st.markdown("""<div class='admin-card'>Buradan genel hassasiyeti ayarlayabilirsin.</div>""", unsafe_allow_html=True)
        
        new_pct = st.slider("Genel Tetikleme Yüzdesi (%)", 1.0, 50.0, alarm_config["percentage"])
        
        st.write("---")
        st.markdown("### 🔇 Sessize Alınan Coinler")
        # Mevcut listeyi string olarak al
        current_ignored = ", ".join(alarm_config["ignored_coins"])
        ignored_input = st.text_area("Virgülle ayırarak yaz (Örn: USDT, BUSD)", current_ignored)
        
        # Listeye çevir
        new_ignored = [x.strip().upper() for x in ignored_input.split(",") if x.strip()]

    with col2:
        st.markdown("### 🎯 Özel Fiyat Hedefleri")
        st.caption("Coin belirli bir fiyata gelince haber verir.")
        
        # Hedef Ekleme Formu
        with st.form("target_add"):
            t_coin = st.text_input("Coin Sembolü (Örn: BTC)").upper()
            t_price = st.number_input("Hedef Fiyat (TL)", min_value=0.0, step=0.1)
            add_btn = st.form_submit_button("Hedef Ekle")
            
            if add_btn and t_coin and t_price > 0:
                alarm_config["price_targets"][t_coin] = t_price
                st.success(f"{t_coin} için {t_price} TL hedefi eklendi!")

        # Mevcut Hedefleri Göster ve Sil
        st.write("#### Aktif Hedefler")
        targets_to_remove = []
        for c, p in alarm_config["price_targets"].items():
            c1, c2 = st.columns([3, 1])
            c1.info(f"**{c}** -> {p} TL")
            if c2.button("Sil", key=f"del_{c}"):
                targets_to_remove.append(c)
        
        # Silme işlemini uygula
        for c in targets_to_remove:
            del alarm_config["price_targets"][c]
            st.rerun()

    # AYARLARI KAYDET
    if st.button("💾 Ayarları Kaydet ve Uygula", type="primary"):
        engine.update_alarm_rules(new_pct, new_ignored, alarm_config["price_targets"])
        st.toast("Ayarlar başarıyla güncellendi!", icon="✅")

    st.markdown("---")
    st.markdown("### 📡 Sistem Durumu")
    st.json({
        "Uptime": engine.get_uptime(),
        "Takip Edilen Coin Sayısı": len(prices),
        "Hafıza Kullanımı (Coin Başına Kayıt)": {k: len(v) for k, v in list(history.items())[:5]} # Örnek ilk 5
    })