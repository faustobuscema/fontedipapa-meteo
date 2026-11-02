import re


_WIND_RE = re.compile(r"^(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(KT|MPS|KMH)$")
_CLOUD_RE = re.compile(r"^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)?(CB|TCU)?$")
_WEATHER_CODES = {
    "DZ": "pioviggine",
    "RA": "pioggia",
    "SN": "neve",
    "SG": "neve granulosa",
    "IC": "cristalli di ghiaccio",
    "PL": "granuli di ghiaccio",
    "GR": "grandine",
    "GS": "piccola grandine",
    "UP": "precipitazione non identificata",
    "BR": "foschia",
    "FG": "nebbia",
    "FU": "fumo",
    "VA": "cenere vulcanica",
    "DU": "polvere",
    "SA": "sabbia",
    "HZ": "caligine",
    "PY": "spruzzi d'acqua",
    "PO": "turbini di polvere o sabbia",
    "SQ": "groppo",
    "FC": "tromba d'aria",
    "SS": "tempesta di sabbia",
    "DS": "tempesta di polvere",
}
_WEATHER_DESCRIPTORS = {
    "MI": "bassa",
    "PR": "parziale",
    "BC": "banchi di",
    "DR": "sollevamento basso di",
    "BL": "sollevamento alto di",
    "SH": "rovesci di",
    "TS": "temporale con",
    "FZ": "gelante",
}
_CLOUD_AMOUNTS = {
    "FEW": "copertura nuvolosa scarsa (1-2/8)",
    "SCT": "nubi sparse (3-4/8)",
    "BKN": "nubi estese (5-7/8)",
    "OVC": "cielo coperto (8/8)",
    "VV": "visibilità verticale",
}


def _format_signed_temperature(value: str) -> str:
    if value.startswith("M"):
        return f"-{int(value[1:])} °C"
    return f"{int(value)} °C"


def _decode_wind(token: str) -> str | None:
    match = _WIND_RE.fullmatch(token)
    if not match:
        return None

    direction, speed, gust, unit = match.groups()
    unit_name = {"KT": "nodi", "MPS": "m/s", "KMH": "km/h"}[unit]
    if direction == "000" and int(speed) == 0:
        return "Calma"

    direction_text = "variabile" if direction == "VRB" else f"{direction}°"
    wind = f"{direction_text} a {speed} {unit_name}"
    if gust:
        wind += f", raffiche fino a {gust} {unit_name}"
    return wind


def _decode_visibility(token: str) -> str | None:
    if token == "CAVOK":
        return "Oltre 10 km (CAVOK)"
    if token.isdigit() and len(token) == 4:
        visibility = int(token)
        if visibility == 9999:
            return "10 km o più"
        if visibility == 0:
            return "Meno di 50 m"
        return f"{visibility} m"
    if token.endswith("SM"):
        return f"{token[:-2]} miglia statutarie"
    return None


def _decode_cloud(token: str) -> str | None:
    match = _CLOUD_RE.fullmatch(token)
    if not match:
        return None

    amount, height, cloud_type = match.groups()
    if amount == "VV":
        description = _CLOUD_AMOUNTS[amount]
    else:
        description = _CLOUD_AMOUNTS[amount]
    if height and height.isdigit():
        description += f" a {int(height) * 100} ft"
    if cloud_type:
        description += f" ({cloud_type})"
    return description


def _decode_weather(token: str) -> str | None:
    if token == "NSW":
        return "Nessun fenomeno significativo"
    match = re.fullmatch(r"([+-]?)(MI|PR|BC|DR|BL|SH|TS|FZ)?(DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS){1,3}", token)
    if not match:
        return None

    intensity, descriptor, *_ = match.groups()
    phenomena = re.findall(
        r"DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS",
        token[1:] if token.startswith(("+", "-")) else token,
    )
    description = ", ".join(_WEATHER_CODES[code] for code in phenomena)
    if descriptor:
        description = f"{_WEATHER_DESCRIPTORS[descriptor]} {description}"
    if intensity == "+":
        description = f"forte: {description}"
    elif intensity == "-":
        description = f"debole: {description}"
    return description


def decode_metar(raw_metar: str) -> dict[str, str]:
    tokens = raw_metar.upper().replace("=", " ").split()
    if not tokens:
        raise ValueError("Il METAR è vuoto.")

    if tokens[0] in {"METAR", "SPECI"}:
        tokens.pop(0)

    decoded = {
        "time": "N/D",
        "temperature": "N/D",
        "dewpoint": "N/D",
        "wind": "N/D",
        "visibility": "N/D",
        "press": "N/D",
        "sky": "N/D",
        "weather": "Nessun fenomeno significativo",
    }
    clouds = []
    weather = []
    visibility_tokens = []

    for token in tokens:
        if re.fullmatch(r"\d{6}Z", token):
            decoded["time"] = f"Giorno {token[:2]} alle {token[2:4]}:{token[4:6]} UTC"
            continue

        wind = _decode_wind(token)
        if wind:
            decoded["wind"] = wind
            continue

        temperature_match = re.fullmatch(r"(M?\d{2}|//)/(M?\d{2}|//)", token)
        if temperature_match:
            temperature, dewpoint = temperature_match.groups()
            if temperature != "//":
                decoded["temperature"] = _format_signed_temperature(temperature)
            if dewpoint != "//":
                decoded["dewpoint"] = _format_signed_temperature(dewpoint)
            continue

        if token.startswith("Q") and token[1:].isdigit():
            decoded["press"] = f"{int(token[1:])} hPa"
            continue
        if token.startswith("A") and re.fullmatch(r"A\d{4}", token):
            pressure_hpa = round(int(token[1:]) * 33.8639 / 100)
            decoded["press"] = f"{pressure_hpa} hPa"
            continue

        visibility = _decode_visibility(token)
        if visibility:
            visibility_tokens.append(visibility)
            continue

        cloud = _decode_cloud(token)
        if cloud:
            clouds.append(cloud)
            continue

        phenomenon = _decode_weather(token)
        if phenomenon:
            weather.append(phenomenon)

    if visibility_tokens:
        decoded["visibility"] = ", ".join(visibility_tokens)
    if clouds:
        decoded["sky"] = ", ".join(clouds)
    elif any(token in {"SKC", "CLR", "NSC", "NCD", "CAVOK"} for token in tokens):
        decoded["sky"] = "Nubi non significative"
    else:
        decoded["sky"] = "N/D"
    if weather:
        decoded["weather"] = ", ".join(weather)
    return decoded


def _format_taf_time(token: str) -> str:
    match = re.fullmatch(r"(\d{2})(\d{2})(\d{2})?", token)
    if not match:
        return token
    day, hour, minute = match.groups()
    return f"giorno {day} alle {hour}:{minute or '00'} UTC"


def _format_taf_period(token: str) -> str:
    match = re.fullmatch(r"(\d{4})/(\d{4})", token)
    if not match:
        return token
    start, end = match.groups()
    return f"{_format_taf_time(start)} – {_format_taf_time(end)}"


def _decode_taf_conditions(tokens: list[str]) -> dict[str, str]:
    conditions = {
        "wind": "Non specificato",
        "visibility": "Non specificata",
        "weather": "Nessun fenomeno significativo indicato",
        "clouds": "Nubi non specificate",
    }
    clouds = []
    weather = []
    visibility = []

    for token in tokens:
        wind = _decode_wind(token)
        if wind:
            conditions["wind"] = wind
            continue

        decoded_visibility = _decode_visibility(token)
        if decoded_visibility:
            visibility.append(decoded_visibility)
            continue

        cloud = _decode_cloud(token)
        if cloud:
            clouds.append(cloud)
            continue

        phenomenon = _decode_weather(token)
        if phenomenon:
            weather.append(phenomenon)

    if visibility:
        conditions["visibility"] = ", ".join(visibility)
    if clouds:
        conditions["clouds"] = ", ".join(clouds)
    elif "CAVOK" in tokens:
        conditions["clouds"] = "Nubi non significative (CAVOK)"
    if weather:
        conditions["weather"] = ", ".join(weather)
    return conditions


def decode_taf(raw_taf: str) -> dict[str, object]:
    tokens = raw_taf.upper().replace("=", " ").split()
    if not tokens:
        raise ValueError("Il TAF è vuoto.")

    if tokens[0] == "TAF":
        tokens.pop(0)

    modifiers = []
    while tokens and tokens[0] in {"AMD", "COR"}:
        modifiers.append(tokens.pop(0))

    if len(tokens) < 3 or not re.fullmatch(r"[A-Z]{4}", tokens[0]):
        raise ValueError("Il TAF non contiene un identificativo ICAO valido.")
    station = tokens.pop(0)
    issued = tokens.pop(0)
    validity = tokens.pop(0)
    if not re.fullmatch(r"\d{6}Z", issued):
        raise ValueError("Orario di emissione del TAF non riconosciuto.")
    if not re.fullmatch(r"\d{4}/\d{4}", validity):
        raise ValueError("Periodo di validità del TAF non riconosciuto.")

    forecast = [{
        "change": "Condizioni iniziali",
        "period": _format_taf_period(validity),
        "tokens": [],
    }]
    current = forecast[0]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        fm_match = re.fullmatch(r"FM(\d{6})", token)
        if fm_match:
            current = {
                "change": "Da",
                "period": _format_taf_time(fm_match.group(1)),
                "tokens": [],
            }
            forecast.append(current)
            index += 1
            continue

        if token in {"BECMG", "TEMPO"} or re.fullmatch(r"PROB\d{2}", token):
            change = token
            index += 1
            if change.startswith("PROB") and index < len(tokens) and tokens[index] == "TEMPO":
                change = f"{change} TEMPO"
                index += 1
            period = ""
            if index < len(tokens) and re.fullmatch(r"\d{4}/\d{4}", tokens[index]):
                period = _format_taf_period(tokens[index])
                index += 1
            current = {
                "change": change,
                "period": period or "Periodo non specificato",
                "tokens": [],
            }
            forecast.append(current)
            continue

        current["tokens"].append(token)
        index += 1

    for group in forecast:
        conditions = _decode_taf_conditions(group.pop("tokens"))
        group.update(conditions)

    return {
        "station": station,
        "type": "TAF " + " ".join(modifiers) if modifiers else "TAF",
        "issued": _format_taf_time(issued),
        "validity": _format_taf_period(validity),
        "forecast": forecast,
    }
