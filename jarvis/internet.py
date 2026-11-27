"""Búsquedas en internet sin clave de Claude: clima, noticias y preguntas generales.

Con la clave de Claude, Jarvis busca con Claude (mejores respuestas). Esto es el plan B, que solo
usa servicios gratuitos y sin registro: Open-Meteo (clima), Google Noticias (RSS) y Wikipedia.
"""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config

_CABECERAS = {"User-Agent": "Jarvis-asistente/1.0"}


def _leer(url, tiempo=8):
    req = urllib.request.Request(url, headers=_CABECERAS)
    with urllib.request.urlopen(req, timeout=tiempo) as r:
        return r.read()


def _json(url):
    return json.loads(_leer(url).decode("utf-8"))


# ---------- clima ----------
_CODIGOS = {
    0: "despejado", 1: "casi despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "con niebla", 48: "con niebla", 51: "con llovizna", 53: "con llovizna", 55: "con llovizna fuerte",
    61: "con lluvia ligera", 63: "con lluvia", 65: "con lluvia fuerte", 66: "con lluvia helada", 67: "con lluvia helada",
    71: "con nieve ligera", 73: "con nieve", 75: "con nieve fuerte", 77: "con granizo fino",
    80: "con chubascos", 81: "con chubascos", 82: "con aguaceros fuertes", 85: "con nieve", 86: "con nieve fuerte",
    95: "con tormenta", 96: "con tormenta y granizo", 99: "con tormenta y granizo",
}


def describir_clima(lugar, datos, manana=False) -> str:
    """Convierte la respuesta de Open-Meteo en una frase para decir en voz alta."""
    d = datos.get("daily", {})
    if manana and len(d.get("time", [])) > 1:
        cielo = _CODIGOS.get(d["weather_code"][1], "variable")
        lluvia = d.get("precipitation_probability_max", [None, None])[1]
        frase = (f"Mañana en {lugar} estará {cielo}, con máxima de {round(d['temperature_2m_max'][1])} "
                 f"y mínima de {round(d['temperature_2m_min'][1])} grados")
    else:
        c = datos["current"]
        cielo = _CODIGOS.get(c.get("weather_code"), "variable")
        lluvia = (d.get("precipitation_probability_max") or [None])[0]
        frase = f"En {lugar} hay {round(c['temperature_2m'])} grados y está {cielo}"
        sensacion = c.get("apparent_temperature")
        if sensacion is not None and abs(sensacion - c["temperature_2m"]) >= 2:
            frase += f", con sensación de {round(sensacion)}"
        if d.get("temperature_2m_max"):
            frase += f". Hoy la máxima es de {round(d['temperature_2m_max'][0])} grados"
    if lluvia is not None:
        frase += f", y la probabilidad de lluvia es del {lluvia} por ciento" if lluvia >= 20 else ", sin lluvia a la vista"
    return frase + "."


def clima(lugar: str = "", manana=False) -> str:
    lugar = (lugar or config.CIUDAD).strip()
    if not lugar:
        return "¿De qué ciudad? Dime por ejemplo «qué clima hace en Bogotá»."
    geo = _json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&name="
                + urllib.parse.quote(lugar))
    if not geo.get("results"):
        return f"No encontré la ciudad {lugar}."
    g = geo["results"][0]
    datos = _json(
        "https://api.open-meteo.com/v1/forecast?timezone=auto&forecast_days=2"
        f"&latitude={g['latitude']}&longitude={g['longitude']}"
        "&current=temperature_2m,apparent_temperature,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max")
    return describir_clima(g.get("name", lugar), datos, manana)


# ---------- noticias ----------
def leer_rss(xml_bytes, n=3):
    titulares = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        titulo = (item.findtext("title") or "").strip()
        titulo = re.sub(r"\s+-\s+[^-]+$", "", titulo)  # quita " - Nombre del periódico"
        if titulo:
            titulares.append(titulo)
        if len(titulares) >= n:
            break
    return titulares


def noticias(tema: str = "") -> str:
    pais = config.PAIS_NOTICIAS
    base = "https://news.google.com/rss"
    sufijo = f"hl=es-419&gl={pais}&ceid={pais}:es-419"
    url = f"{base}/search?q={urllib.parse.quote(tema)}&{sufijo}" if tema else f"{base}?{sufijo}"
    titulares = leer_rss(_leer(url))
    if not titulares:
        return "No encontré noticias" + (f" sobre {tema}." if tema else " ahora mismo.")
    inicio = f"Lo último sobre {tema}: " if tema else "Estos son los titulares: "
    return inicio + " ... ".join(t.rstrip(".") + "." for t in titulares)


# ---------- preguntas generales ----------
def _primeras_frases(texto, n=2):
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    return " ".join(frases[:n])


def preguntar(consulta: str) -> str:
    """Respuesta corta a una pregunta general: primero DuckDuckGo, luego Wikipedia en español."""
    try:
        d = _json("https://api.duckduckgo.com/?format=json&no_html=1&skip_disambig=1&kl=es-es&q="
                  + urllib.parse.quote(consulta))
        texto = d.get("Answer") or d.get("AbstractText")
        if texto:
            return _primeras_frases(str(texto))
    except Exception:
        pass
    busqueda = _json("https://es.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch="
                     + urllib.parse.quote(consulta))
    resultados = busqueda.get("query", {}).get("search", [])
    if not resultados:
        return ""
    titulo = resultados[0]["title"]
    resumen = _json("https://es.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(titulo.replace(" ", "_")))
    return _primeras_frases(resumen.get("extract", ""))


def abrir_en_navegador(consulta: str):
    import webbrowser
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(consulta))
