import streamlit as st
import pandas as pd
import requests
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import datetime
import os
import base64
import importlib
import urllib.request
import re

# ---------------------------------------------------------
# Configurazione Pagina Streamlit
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dashboard Meteo - Fonte di Papa (RM)",
    page_icon="🌤️",
    layout="wide"
)

# --- Stile CSS Globale e Responsive per Mobile ---
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    /* Sfondo azzurro chiaro sfumato per tutte le card */
    .aero-card {
        background: linear-gradient(135deg, #56b4f8, #86d0f9);
        color: #ffffff;
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.15);
        margin-bottom: 15px;
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    div[data-testid="stCode"] pre,
    div[data-testid="stExpander"] details {
        background: linear-gradient(135deg, #56b4f8, #86d0f9);
        color: #ffffff;
        border-radius: 12px;
    }
    div[data-testid="stCode"] pre code,
    div[data-testid="stExpander"] details,
    div[data-testid="stExpander"] details summary,
    div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
        color: #ffffff;
    }
    .stMetric {
        background-color: transparent !important;
        padding: 0px;
    }
    /* Ottimizzazione per dispositivi mobili */
    @media (max-width: 768px) {
        .weather-card-content {
            flex-direction: column !important;
            text-align: center !important;
        }
        .weather-details-mobile {
            text-align: center !important;
            margin-top: 15px;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Funzione per convertire l'icona locale in Base64
def get_image_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded}"
    return ""

# Mappatura codici WMO ai file icona personalizzati nella cartella assets/
def get_weather_icon(w_code):
    if w_code == 0:
        return "assets/sun.png", "Cielo Sereno"
    elif w_code in [1, 2]:
        return "assets/sun_cloud.png", "Parzialmente Nuvoloso"
    elif w_code == 3:
        return "assets/cloud.png", "Coperto"
    elif w_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "assets/rain.png", "Pioggia"
    elif w_code >= 95:
        return "assets/storm.png", "Temporale"
    else:
        return "assets/cloud.png", "Nuvoloso"

# Gestione del pulsante di aggiornamento globale in alto a destra
c_title, c_btn = st.columns([5, 1])
with c_title:
    st.title("🌤️ Dashboard Meteo - Fonte di Papa (RM)")
    st.caption("📍 Fonte di Papa (RM) • Lat: 42.05667 | Lon: 12.57507")
with c_btn:
    st.write("") 
    if st.button("🔄 Aggiorna Tutto", key="refresh_all", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------
# Funzione per recuperare METAR e TAF
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def get_weather_aero_data(icao_code):
    checkwx_key = st.secrets.get("CHECKWX_API_KEY", "")
    result = {
        "metar_raw": "N/D", 
        "taf_raw": "TAF non disponibile o non emesso per questa stazione", 
        "metar_decoded": {}, 
        "taf_decoded": {}, 
        "is_checkwx": False
    }
    
    if checkwx_key and checkwx_key != "la_tua_api_key_checkwx_qui":
        try:
            headers = {"X-API-Key": checkwx_key}
            res_m = requests.get(f"https://api.checkwx.com/metar/{icao_code}/decoded", headers=headers, timeout=5)
            if res_m.status_code == 200:
                data_m = res_m.json()
                if "data" in data_m and len(data_m["data"]) > 0:
                    result["metar_decoded"] = data_m["data"][0]
                    result["metar_raw"] = data_m["data"][0].get("raw_text", "N/D")
                    result["is_checkwx"] = True

            res_t = requests.get(f"https://api.checkwx.com/taf/{icao_code}/decoded", headers=headers, timeout=5)
            if res_t.status_code == 200:
                data_t = res_t.json()
                if "data" in data_t and len(data_t["data"]) > 0:
                    result["taf_decoded"] = data_t["data"][0]
                    result["taf_raw"] = data_t["data"][0].get("raw_text", "TAF non disponibile o non emesso per questa stazione")
            return result
        except Exception:
            pass

    try:
        res_m = requests.get(f"https://aviationweather.gov/api/data/metar?ids={icao_code}&format=raw", timeout=5)
        if res_m.status_code == 200 and res_m.text.strip():
            raw_m = res_m.text.strip()
            result["metar_raw"] = raw_m
            try:
                metar_parser = importlib.import_module("metar").Metar
                obs = metar_parser.Metar(raw_m)
                result["metar_decoded"] = {
                    "time": obs.time.strftime("%d/%m/%Y %H:%M UTC") if obs.time else "N/D",
                    "temperature": f"{obs.temp.value()} °C" if obs.temp else "N/D",
                    "dewpoint": f"{obs.dewpt.value()} °C" if obs.dewpt else "N/D",
                    "wind": f"{obs.wind_dir.value()}° a {obs.wind_speed.value()} nodi" if obs.wind_speed else "Calma / N/D",
                    "visibility": f"{obs.vis.value()} {obs.vis.unit}" if obs.vis else "N/D",
                    "press": f"{obs.press.value()} hPa" if obs.press else "N/D",
                    "sky": ", ".join([f"{c[0]} a {c[1].value()}ft" if c[1] else c[0] for c in obs.sky]) if obs.sky else "Sereno"
                }
            except ImportError:
                result["metar_decoded"] = {"info": "Decodifica METAR non disponibile: installare il pacchetto metar."}

        res_t = requests.get(f"https://aviationweather.gov/api/data/taf?ids={icao_code}&format=raw", timeout=5)
        if res_t.status_code == 200 and res_t.text.strip():
            result["taf_raw"] = res_t.text.strip()
            result["taf_decoded"] = {"info": "Decodifica testuale disponibile tramite CheckWX API Key"}

        return result
    except Exception as e:
        return {"error": f"Impossibile recuperare i dati per {icao_code}: {str(e)}"}


# ---------------------------------------------------------
# Layout a Tre Colonne (Su mobile Streamlit le dispone verticalmente)
# Ordine consigliato: LIRF (Sinistra), Condizioni Attuali (Centro), LIRU (Destra)
# ---------------------------------------------------------
col_left, col_center, col_right = st.columns([1, 1.2, 1], gap="medium")

# --- Riquadro Centrale: Dati Attuali Open-Meteo (Posizionato per primo logicamente se preferisci priorità visiva su mobile) ---
with col_center:
    st.markdown("""
        <div class="aero-card">
            <h3 style="margin: 0 0 10px 0; color: #ffffff;">📍 Condizioni Attuali</h3>
        </div>
    """, unsafe_allow_html=True)
    
    try:
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        url_current = "https://api.open-meteo.com/v1/forecast"
        params_current = {
            "latitude": 42.05667,
            "longitude": 12.57507,
            "current": [
                "temperature_2m", "relative_humidity_2m", "surface_pressure",
                "precipitation", "weather_code", "wind_speed_10m", 
                "wind_direction_10m", "cloud_cover"
            ],
            "timezone": "auto",
        }
        
        responses = openmeteo.weather_api(url_current, params=params_current)
        response_cur = responses[0]
        current = response_cur.Current()
        
        current_time_unix = current.Time()
        current_dt = pd.to_datetime(current_time_unix, unit="s", utc=True).tz_convert("Europe/Rome")
        
        giorni_ita = {0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì", 4: "Venerdì", 5: "Sabato", 6: "Domenica"}
        mesi_ita = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
                     7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}
        
        nome_giorno = giorni_ita[current_dt.weekday()]
        data_estesa = f"{current_dt.day} {mesi_ita[current_dt.month]}"
        
        temp = current.Variables(0).Value()
        humidity = current.Variables(1).Value()
        pressure = current.Variables(2).Value()
        precip = current.Variables(3).Value()
        w_code = int(current.Variables(4).Value())
        wind_speed = current.Variables(5).Value()
        wind_dir = current.Variables(6).Value()
        cloud = current.Variables(7).Value()

        icon_path, desc_weather = get_weather_icon(w_code)
        img_src = get_image_base64(icon_path)

        card_html = f"""
        <div class="aero-card weather-card-content" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; flex-direction: column;">
                <span style="font-size: 26px; font-weight: 700; line-height: 1.1;">{nome_giorno}</span>
                <span style="font-size: 19px; margin-bottom: 12px; opacity: 0.95;">{data_estesa}</span>
                <span style="font-size: 42px; font-weight: 300; line-height: 1; margin: 0;">{temp:.0f}°C</span>
                <span style="font-size: 16px; margin-top: 5px; text-transform: lowercase; opacity: 0.9;">{desc_weather}</span>
            </div>
            <div style="text-align: center; margin: 0 10px;">
                <img src="{img_src}" style="height: 300px; max-width: 300px; object-fit: contain; filter: drop-shadow(0px 4px 8px rgba(0,0,0,0.25));" alt="{desc_weather}">
            </div>
            <div class="weather-details-mobile" style="text-align: left; font-size: 14px; line-height: 1.7; font-weight: 400;">
                Pressione &nbsp;<b>{pressure:.0f} hPa</b><br>
                Umidità &nbsp;<b>{humidity:.0f}%</b><br>
                Vento &nbsp;<b>{wind_dir:.0f}° ({wind_speed:.0f} km/h)</b><br>
                Pioggia &nbsp;<b>{precip:.1f} mm</b><br>
                Copertura nuvole &nbsp;<b>{cloud:.0f}%</b>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        st.caption(f"🕒 Rilevato il: {current_dt.strftime('%d/%m/%Y %H:%M')}")

    except Exception as e:
        st.error(f"Errore nel recupero dati Open-Meteo attuali: {e}")

# --- Riquadro Sinistro: LIRF (Fiumicino) ---
with col_left:
    st.markdown("""
        <div class="aero-card">
            <h3 style="margin: 0 0 10px 0; color: #ffffff;">✈️ LIRF — Fiumicino</h3>
        </div>
    """, unsafe_allow_html=True)
    
    data_lirf = get_weather_aero_data("LIRF")
    if "error" in data_lirf:
        st.error(data_lirf["error"])
    else:
        st.markdown("**METAR (Attuale)**")
        st.code(data_lirf["metar_raw"], language="text")
        
        with st.expander("🔍 Decodifica METAR LIRF"):
            m_dec = data_lirf["metar_decoded"]
            if data_lirf["is_checkwx"]:
                st.write(f"- **Ora:** {m_dec.get('observed', 'N/D')}")
                st.write(f"- **Temperatura:** {m_dec.get('temperature', {}).get('celsius', 'N/D')} °C")
                st.write(f"- **Vento:** {m_dec.get('wind', {}).get('degrees', 'N/D')}° / {m_dec.get('wind', {}).get('speed_kts', 'N/D')} kts")
                st.write(f"- **QNH:** {m_dec.get('barometer', {}).get('hpa', 'N/D')} hPa")
                st.write(f"- **Visibilità:** {m_dec.get('visibility', {}).get('meters', 'N/D')} m")
            else:
                st.write(f"- **Ora:** {m_dec.get('time')}")
                st.write(f"- **Temperatura:** {m_dec.get('temperature')}")
                st.write(f"- **Punto di rugiada:** {m_dec.get('dewpoint')}")
                st.write(f"- **Vento:** {m_dec.get('wind')}")
                st.write(f"- **Pressione:** {m_dec.get('press')}")
                st.write(f"- **Visibilità:** {m_dec.get('visibility')}")
                st.write(f"- **Nubi:** {m_dec.get('sky')}")

        st.markdown("**TAF (Previsione)**")
        st.code(data_lirf["taf_raw"], language="text")
        
        with st.expander("🔍 Decodifica TAF LIRF"):
#            t_dec = data_lirf.get("taf_decoded", {})
#            if data_lirf["is_checkwx"] and "forecast" in t_dec:
#                st.write(f"- **Emesso il:** {t_dec.get('timestamp', 'N/D')}")
#                for f in t_dec.get("forecast", []):
#                    time_from = f.get('from', {}).get('repr', 'N/D')
#                    time_to = f.get('to', {}).get('repr', 'N/D')
#                    wind_f = f.get('wind', {})
#                    st.markdown(f"• *Da {time_from} a {time_to}:* Vento {wind_f.get('degrees', 'N/D')}° / {wind_f.get('speed_kts', 'N/D')} kts")
#            else:
#                st.info("Decodifica dettagliata disponibile con CheckWX API Key.")
    # 1. Scarica il TAF dall'API ufficiale
            url = "https://aviationweather.gov/api/data/taf?ids=LIRF"

            try:
                with urllib.request.urlopen(url) as response:
                    taf_raw = response.read().decode('utf-8').strip()
            except Exception as e:
                print(f"Errore di connessione: {e}")
                taf_raw = ""

            if taf_raw:
                print(f"=== TAF GREZZO SCARICATO ===\n{taf_raw}\n")
                print("=== DECODIFICA PASSO DOPO PASSO ===")
    
                parts = taf_raw.split()
    
                # 1. Identificatore del tipo
                taf_type = parts[0]
                print(f"1. Tipo bollettino: {taf_type} ({'Modificato/AMD' if 'AMD' in taf_type else 'Standard'})")
    
                # 2. Stazione ICAO
                station = parts[1]
                print(f"2. Stazione ICAO: {station} (Aeroporto di Roma Fiumicino)")
    
                # 3. Data/Ora di emissione
                issue_time = parts[2]
                day = issue_time[:2]
                hour = issue_time[2:4]
                minute = issue_time[4:6]
                print(f"3. Emissione: Giorno {day} alle ore {hour}:{minute} UTC")
    
                # 4. Validità
                validity = parts[3]
                print(f"4. Periodo di validità: {validity}")
    
                # 5. Vento (cerchiamo il blocco con KT o MPS)
                wind = next((p for p in parts if 'KT' in p or 'MPS' in p), "Non trovato")
                print(f"5. Vento principale: {wind}")
    
                # 6. Visibilità (cifre esatte o CAVOK)
                visib = next((p for p in parts if p.isdigit() and len(p) == 4 or p == 'CAVOK'), "Non trovata")
                print(f"6. Visibilità: {visib}")
    
                # 7 & 8. Nubi e Fenomeni (Analizziamo i gruppi principali)
                print("7-8. Condizioni meteorologiche e Nubi principali:")
                for p in parts:
                    if any(cloud in p for cloud in ['FEW', 'SCT', 'BKN', 'OVC', 'NSC', 'SKC', 'CAVOK']):
                        print(f"   - Nubi: {p}")
            
                # 9. Indicatori di variazione (TEMPO, BECMG, PROB)
                print("9. Indicatori di variazione e trend:")
                # Ricostruiamo dividendo per i gruppi di cambiamento
                current_trend = []
                trends_list = []
                for p in parts[4:]:
                    if p in ['TEMPO', 'BECMG', 'PROB30', 'PROB40', 'FM']:
                        if current_trend:
                            trends_list.append(" ".join(current_trend))
                            current_trend = []
                    current_trend.append(p)
                if current_trend:
                    trends_list.append(" ".join(current_trend))
        
                for t in trends_list[1:]: # Esclude il primo blocco che è il meteo base
                    print(f"   -> {t}")


# --- Riquadro Destro: LIRU (Roma Urbe) ---
with col_right:
    st.markdown("""
        <div class="aero-card">
            <h3 style="margin: 0 0 10px 0; color: #ffffff;">✈️ LIRU — Roma Urbe</h3>
        </div>
    """, unsafe_allow_html=True)
    
    data_liru = get_weather_aero_data("LIRU")
    if "error" in data_liru:
        st.error(data_liru["error"])
    else:
        st.markdown("**METAR (Attuale)**")
        st.code(data_liru["metar_raw"], language="text")
        
        with st.expander("🔍 Decodifica METAR LIRU"):
            m_dec_u = data_liru["metar_decoded"]
            if data_liru["is_checkwx"]:
                st.write(f"- **Ora:** {m_dec_u.get('observed', 'N/D')}")
                st.write(f"- **Temperatura:** {m_dec_u.get('temperature', {}).get('celsius', 'N/D')} °C")
                st.write(f"- **Vento:** {m_dec_u.get('wind', {}).get('degrees', 'N/D')}° / {m_dec_u.get('wind', {}).get('speed_kts', 'N/D')} kts")
                st.write(f"- **QNH:** {m_dec_u.get('barometer', {}).get('hpa', 'N/D')} hPa")
                st.write(f"- **Visibilità:** {m_dec_u.get('visibility', {}).get('meters', 'N/D')} m")
            else:
                st.write(f"- **Ora:** {m_dec_u.get('time')}")
                st.write(f"- **Temperatura:** {m_dec_u.get('temperature')}")
                st.write(f"- **Punto di rugiada:** {m_dec_u.get('dewpoint')}")
                st.write(f"- **Vento:** {m_dec_u.get('wind')}")
                st.write(f"- **Pressione:** {m_dec_u.get('press')}")
                st.write(f"- **Visibilità:** {m_dec_u.get('visibility')}")
                st.write(f"- **Nubi:** {m_dec_u.get('sky')}")

        st.markdown("**TAF (Previsione)**")
        st.code(data_liru["taf_raw"], language="text")
        
        with st.expander("🔍 Decodifica TAF LIRU"):
            t_dec_u = data_liru.get("taf_decoded", {})
            if data_liru["is_checkwx"] and "forecast" in t_dec_u:
                st.write(f"- **Emesso il:** {t_dec_u.get('timestamp', 'N/D')}")
                for f in t_dec_u.get("forecast", []):
                    time_from = f.get('from', {}).get('repr', 'N/D')
                    time_to = f.get('to', {}).get('repr', 'N/D')
                    wind_f = f.get('wind', {})
                    st.markdown(f"• *Da {time_from} a {time_to}:* Vento {wind_f.get('degrees', 'N/D')}° / {wind_f.get('speed_kts', 'N/D')} kts")
            else:
                st.info("Decodifica dettagliata disponibile con CheckWX API Key.")

st.divider()

# ---------------------------------------------------------
# Sezione Inferiore: Previsioni ed Estese Open-Meteo
# ---------------------------------------------------------
st.subheader("📊 Previsioni Dettagliate & Ensemble")

@st.cache_data(ttl=1800)
def fetch_extended_forecast():
    try:
        url_ensemble = "https://ensemble-api.open-meteo.com/v1/ensemble"
        params = {
            "latitude": 42.056747,
            "longitude": 12.574791,
            "hourly": [
                "temperature_2m", "relative_humidity_2m", "dew_point_2m", 
                "precipitation_probability", "precipitation", "weather_code", 
                "wind_speed_10m", "cloud_cover", "wind_direction_10m"
            ],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "sunrise", "sunset"],
            "models": "google_weathernext2_ensemble",
            "timezone": "auto"
        }
        res = requests.get(url_ensemble, params=params, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

forecast_data = fetch_extended_forecast()

if forecast_data:
    hourly = forecast_data.get("hourly", {})
    daily = forecast_data.get("daily", {})
    
    df_hourly = pd.DataFrame({
        "Ora": hourly.get("time", []),
        "Temp (°C)": hourly.get("temperature_2m", []),
        "Umidità (%)": hourly.get("relative_humidity_2m", []),
        "Punto Rugiada (°C)": hourly.get("dew_point_2m", []),
        "Prob. Pioggia (%)": hourly.get("precipitation_probability", []),
        "Pioggia (mm)": hourly.get("precipitation", []),
        "Vento (km/h)": hourly.get("wind_speed_10m", []),
        "Dir. Vento (°)": hourly.get("wind_direction_10m", []),
        "Nuvole (%)": hourly.get("cloud_cover", [])
    })

    df_daily = pd.DataFrame({
        "Giorno": daily.get("time", []),
        "Temp Max (°C)": daily.get("temperature_2m_max", []),
        "Temp Min (°C)": daily.get("temperature_2m_min", []),
        "Alba": daily.get("sunrise", []),
        "Tramonto": daily.get("sunset", [])
    })

    tab1, tab2, tab3 = st.tabs(["📈 Grafico Orario", "📋 Tabella Oraria", "📅 Previsioni Giornaliere"])
    
    with tab1:
        if not df_hourly.empty:
            st.line_chart(df_hourly.set_index("Ora")[["Temp (°C)", "Pioggia (mm)", "Umidità (%)"]])
    with tab2:
        if not df_hourly.empty:
            st.dataframe(df_hourly, width='stretch', height=400)
    with tab3:
        if not df_daily.empty:
            st.dataframe(df_daily, width='stretch', height=300)
else:
    st.error("Errore nel recupero delle previsioni estese da Open-Meteo.")

st.divider()
st.markdown(
    "<p style='text-align: center; opacity: 0.7;'>"
    "Icone meteo: © <a href='https://www.magnific.com' target='_blank' "
    "rel='noopener noreferrer'>www.magnific.com</a>"
    "</p>",
    unsafe_allow_html=True
)
