import streamlit as st
import pandas as pd
import requests
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import datetime
import os
import base64
from decode_taf import decode_metar, decode_taf

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
    .stApp {
        background: linear-gradient(145deg, #fff8ee 0%, #fff1e8 58%, #eef7ff 100%);
    }
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background: transparent;
    }
    [data-testid="stHeader"] {
        background: rgba(255, 248, 238, 0.75);
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
TAF_NOT_AVAILABLE = "TAF non disponibile o non emesso per questa stazione"


def decode_aeronautical_reports(result):
    if result["metar_raw"] != "N/D":
        try:
            result["metar_decoded"] = decode_metar(result["metar_raw"])
        except ValueError as error:
            result["metar_decoded"] = {"error": str(error)}

    if result["taf_raw"] != TAF_NOT_AVAILABLE:
        try:
            result["taf_decoded"] = decode_taf(result["taf_raw"])
        except ValueError as error:
            result["taf_decoded"] = {"error": str(error)}

    return result


@st.cache_data(ttl=600)
def get_weather_aero_data(icao_code):
    checkwx_key = st.secrets.get("CHECKWX_API_KEY", "")
    result = {
        "metar_raw": "N/D",
        "taf_raw": TAF_NOT_AVAILABLE,
        "metar_decoded": {},
        "taf_decoded": {},
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

            res_t = requests.get(f"https://api.checkwx.com/taf/{icao_code}/decoded", headers=headers, timeout=5)
            if res_t.status_code == 200:
                data_t = res_t.json()
                if "data" in data_t and len(data_t["data"]) > 0:
                    result["taf_decoded"] = data_t["data"][0]
                    result["taf_raw"] = data_t["data"][0].get("raw_text", "TAF non disponibile o non emesso per questa stazione")
            return decode_aeronautical_reports(result)
        except Exception:
            pass

    try:
        res_m = requests.get(f"https://aviationweather.gov/api/data/metar?ids={icao_code}&format=raw", timeout=5)
        if res_m.status_code == 200 and res_m.text.strip():
            result["metar_raw"] = res_m.text.strip()

        res_t = requests.get(f"https://aviationweather.gov/api/data/taf?ids={icao_code}&format=raw", timeout=5)
        if res_t.status_code == 200 and res_t.text.strip():
            result["taf_raw"] = res_t.text.strip()

        return decode_aeronautical_reports(result)
    except Exception as e:
        return {"error": f"Impossibile recuperare i dati per {icao_code}: {str(e)}"}


def display_decoded_metar(decoded):
    if decoded.get("error"):
        st.warning(f"Decodifica METAR non disponibile: {decoded['error']}")
        return
    st.write(f"- **Ora:** {decoded.get('time', 'N/D')}")
    st.write(f"- **Temperatura:** {decoded.get('temperature', 'N/D')}")
    st.write(f"- **Punto di rugiada:** {decoded.get('dewpoint', 'N/D')}")
    st.write(f"- **Vento:** {decoded.get('wind', 'N/D')}")
    st.write(f"- **Pressione:** {decoded.get('press', 'N/D')}")
    st.write(f"- **Visibilità:** {decoded.get('visibility', 'N/D')}")
    st.write(f"- **Nubi:** {decoded.get('sky', 'N/D')}")
    st.write(f"- **Fenomeni:** {decoded.get('weather', 'N/D')}")


def display_decoded_taf(decoded):
    if decoded.get("error"):
        st.warning(f"Decodifica TAF non disponibile: {decoded['error']}")
        return
    if not decoded:
        st.info("TAF non disponibile per questa stazione.")
        return

    st.write(f"- **Tipo:** {decoded.get('type', 'TAF')}")
    st.write(f"- **Stazione:** {decoded.get('station', 'N/D')}")
    st.write(f"- **Emesso:** {decoded.get('issued', 'N/D')}")
    st.write(f"- **Validità:** {decoded.get('validity', 'N/D')}")
    for period in decoded.get("forecast", []):
        st.markdown(f"**{period['change']} — {period['period']}**")
        st.write(f"- Vento: {period['wind']}")
        st.write(f"- Visibilità: {period['visibility']}")
        st.write(f"- Fenomeni: {period['weather']}")
        st.write(f"- Nubi: {period['clouds']}")


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
        st.markdown(
            "Dati meteo forniti da [Open-Meteo.com](https://open-meteo.com/), "
            "con presentazione adattata. "
            "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)."
        )

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
            display_decoded_metar(data_lirf["metar_decoded"])

        st.markdown("**TAF (Previsione)**")
        st.code(data_lirf["taf_raw"], language="text")
        
        with st.expander("🔍 Decodifica TAF LIRF"):
            display_decoded_taf(data_lirf["taf_decoded"])


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
            display_decoded_metar(data_liru["metar_decoded"])

        st.markdown("**TAF (Previsione)**")
        st.code(data_liru["taf_raw"], language="text")
        
        with st.expander("🔍 Decodifica TAF LIRU"):
            display_decoded_taf(data_liru["taf_decoded"])

st.divider()

# ---------------------------------------------------------
# Sezione Inferiore: Previsioni ed Estese Open-Meteo
# ---------------------------------------------------------
st.subheader("📊 Previsioni Dettagliate & Ensemble")
st.markdown(
    "Previsioni fornite da [Open-Meteo.com](https://open-meteo.com/), "
    "con presentazione adattata. "
    "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)."
)

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
