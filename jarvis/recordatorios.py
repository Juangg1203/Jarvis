"""Recordatorios, alarmas y temporizadores por voz. Funcionan sin internet.

Entiende frases como:
  «avísame en 20 minutos que saque la ropa»     «pon un temporizador de cinco minutos»
  «recuérdame mañana a las 8 llamar a mamá»     «pon una alarma a las seis y media»
  «recuérdame a las 3 de la tarde la reunión»   «avísame en una hora y media»
"""
import datetime as dt
import json
import re
import threading
import time
import uuid

from . import config
from .texto import normalizar

def _ARCHIVO():
    return config.CARPETA_DATOS / "recordatorios.json"


# ---------- números escritos ----------
_UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiun": 21, "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "noventa": 90}


def leer_numero(palabras, i):
    """Lee un número (cifras o palabras) desde palabras[i]. Devuelve (valor, siguiente_i) o (None, i)."""
    if i >= len(palabras):
        return None, i
    p = palabras[i]
    if p.isdigit():
        return int(p), i + 1
    if p in _UNIDADES:
        return _UNIDADES[p], i + 1
    if p in _DECENAS:
        valor = _DECENAS[p]
        if i + 2 < len(palabras) and palabras[i + 1] == "y" and _UNIDADES.get(palabras[i + 2], 99) < 10:
            return valor + _UNIDADES[palabras[i + 2]], i + 3
        return valor, i + 1
    return None, i


def _a_cifras(texto):
    """'en veinte minutos' -> 'en 20 minutos'; 'treinta y cinco' -> '35'."""
    palabras = texto.split()
    salida, i = [], 0
    while i < len(palabras):
        # "un/una" solo cuentan como número delante de una unidad de tiempo
        if palabras[i] in ("un", "una") and not (i + 1 < len(palabras) and re.match(r"(segundo|minuto|hora|dia|semana)s?$", palabras[i + 1])):
            salida.append(palabras[i]); i += 1
            continue
        valor, j = leer_numero(palabras, i)
        if valor is not None and j > i and not palabras[i].isdigit():
            salida.append(str(valor)); i = j
        else:
            salida.append(palabras[i]); i += 1
    return " ".join(salida)


_UNIDAD_SEG = {"segundo": 1, "minuto": 60, "hora": 3600, "dia": 86400, "semana": 604800}

_RE_PREFIJO = re.compile(
    r"^(?:por favor\s+)?(?:avisame|avisarme|recuerdame|recordarme|despiertame|despertarme|"
    r"(?:ponme|pon|crea|programa|configura)\s+(?:un|una)\s+(?:recordatorio|alarma|temporizador|timer|aviso)|"
    r"(?:un|una)\s+(?:recordatorio|alarma|temporizador))\b\s*")
_RE_RELATIVO = re.compile(
    r"\b(?:en|dentro de|de)\s+(?:(\d+)\s+(segundo|minuto|hora|dia|semana)s?(?:\s+y\s+(media|cuarto|\d+\s+minutos?))?"
    r"|media\s+hora|(?:un\s+)?cuarto\s+de\s+hora)\b")
_RE_ABSOLUTO = re.compile(
    r"\b(?:(hoy|manana|pasado manana)\s+)?(?:a\s+)?(?:las|la)\s+(\d{1,2})(?:\s+(?:y\s+)?(media|cuarto|\d{1,2})|\s+menos\s+(cuarto|\d{1,2}))?"
    r"(?:\s+(?:en punto))?(?:\s+(?:de\s+la\s+)?(manana|tarde|noche|madrugada)|\s+(am|pm))?\b(?:\s+(?:de\s+)?(hoy|manana|pasado manana))?")
_RE_PARA = re.compile(r"\b(?:para|a)\s+(?=(?:las|la)\s+\d)")


def interpretar(texto, ahora=None):
    """Devuelve dict {cuando, mensaje, tipo} o None si la frase no es un recordatorio."""
    ahora = ahora or dt.datetime.now()
    t = normalizar(texto)
    m = _RE_PREFIJO.match(t)
    if not m:
        return None
    prefijo = m.group(0)
    tipo = "alarma" if ("alarma" in prefijo or "despierta" in prefijo) else \
           "temporizador" if ("temporizador" in prefijo or "timer" in prefijo) else "recordatorio"
    resto = _a_cifras(re.sub(r"\bla una\b", "la 1", t[m.end():]))
    cuando = None

    r = _RE_RELATIVO.search(resto)
    if r:
        if r.group(1):
            seg = int(r.group(1)) * _UNIDAD_SEG[r.group(2)]
            extra = r.group(3)
            if extra == "media":
                seg += _UNIDAD_SEG[r.group(2)] // 2
            elif extra == "cuarto":
                seg += _UNIDAD_SEG[r.group(2)] // 4
            elif extra:
                seg += int(extra.split()[0]) * 60
        elif "media" in r.group(0):
            seg = 1800
        else:
            seg = 900
        cuando = ahora + dt.timedelta(seconds=seg)
        resto = (resto[:r.start()] + " " + resto[r.end():]).strip()
    else:
        resto = _RE_PARA.sub("a ", resto)
        a = _RE_ABSOLUTO.search(resto)
        if a:
            dia = a.group(1) or a.group(7)
            hora = int(a.group(2))
            minuto = 0
            if a.group(3):
                minuto = 30 if a.group(3) == "media" else 15 if a.group(3) == "cuarto" else int(a.group(3))
            if a.group(4):
                hora -= 1
                minuto = 60 - (15 if a.group(4) == "cuarto" else int(a.group(4)))
            periodo = a.group(5) or a.group(6)
            if hora > 23 or minuto > 59:
                return None
            if periodo in ("tarde", "noche", "pm") and hora < 12:
                hora += 12
            if periodo == "noche" and hora == 24:
                hora = 0
            if periodo in ("manana", "madrugada", "am") and hora == 12:
                hora = 0
            base = ahora.replace(second=0, microsecond=0)
            if dia in ("manana", "pasado manana"):
                fecha = base + dt.timedelta(days=1 if dia == "manana" else 2)
                if not periodo and hora < 7 and tipo != "alarma":
                    hora += 12  # "mañana a las 3" -> 3 de la tarde
                cuando = fecha.replace(hour=hora % 24, minute=minuto)
            else:
                candidatos = [base.replace(hour=hora % 24, minute=minuto)]
                if not periodo and hora < 12 and tipo != "alarma":  # una alarma "a las 7" es de mañana
                    candidatos.append(base.replace(hour=hora + 12, minute=minuto))
                futuros = [c for c in candidatos if c > ahora]
                cuando = min(futuros) if futuros else candidatos[0] + dt.timedelta(days=1)
            resto = (resto[:a.start()] + " " + resto[a.end():]).strip()
    if cuando is None:
        return None

    mensaje = re.sub(r"^(?:que|de|para|a|y)\s+", "", resto).strip()
    mensaje = re.sub(r"\s+(?:por favor)$", "", mensaje)
    # Recupera las tildes de las palabras originales ("mama" -> "mamá").
    originales = {normalizar(w): w.lower() for w in re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", texto)}
    mensaje = " ".join(originales.get(w, w) for w in mensaje.split())
    return {"cuando": cuando, "mensaje": mensaje, "tipo": tipo}


def describir(cuando, ahora=None):
    """'a las 8:30 de mañana', 'en 20 minutos'..."""
    ahora = ahora or dt.datetime.now()
    falta = (cuando - ahora).total_seconds()
    if falta < 3600:
        minutos = max(1, round(falta / 60))
        return f"en {minutos} minuto{'s' if minutos != 1 else ''}"
    hora = cuando.strftime("%H:%M")
    if cuando.date() == ahora.date():
        return f"hoy a las {hora}"
    if cuando.date() == (ahora + dt.timedelta(days=1)).date():
        return f"mañana a las {hora}"
    return f"el {cuando.day}/{cuando.month} a las {hora}"


class Agenda:
    """Guarda los recordatorios en disco y avisa cuando llega la hora."""

    def __init__(self, al_sonar=None):
        self.al_sonar = al_sonar or (lambda r: None)
        self._lock = threading.Lock()
        self.items = self._cargar()

    def _cargar(self):
        try:
            datos = json.loads(_ARCHIVO().read_text(encoding="utf-8"))
            return [d for d in datos if "cuando" in d]
        except (OSError, ValueError):
            return []

    def _guardar(self):
        try:
            config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
            _ARCHIVO().write_text(json.dumps(self.items, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def agregar(self, cuando, mensaje="", tipo="recordatorio"):
        item = {"id": uuid.uuid4().hex[:8], "cuando": cuando.isoformat(timespec="seconds"),
                "mensaje": mensaje, "tipo": tipo}
        with self._lock:
            self.items.append(item)
            self.items.sort(key=lambda x: x["cuando"])
            self._guardar()
        return item

    def pendientes(self):
        with self._lock:
            return list(self.items)

    def cancelar(self, id_=None):
        """Cancela uno (por id o número 1..n) o todos si id_ es None. Devuelve cuántos quitó."""
        with self._lock:
            antes = len(self.items)
            if id_ is None:
                self.items = []
            elif isinstance(id_, int) or str(id_).isdigit():
                n = int(id_)
                if 1 <= n <= len(self.items):
                    self.items.pop(n - 1)
            else:
                self.items = [x for x in self.items if x["id"] != id_]
            self._guardar()
            return antes - len(self.items)

    def revisar(self, ahora=None):
        """Dispara los recordatorios vencidos (también los que vencieron con el PC apagado)."""
        ahora = ahora or dt.datetime.now()
        with self._lock:
            vencidos = [x for x in self.items if dt.datetime.fromisoformat(x["cuando"]) <= ahora]
            if vencidos:
                self.items = [x for x in self.items if x not in vencidos]
                self._guardar()
        for x in vencidos:
            x["atrasado_min"] = int((ahora - dt.datetime.fromisoformat(x["cuando"])).total_seconds() // 60)
            self.al_sonar(x)
        return vencidos

    def iniciar(self):
        def bucle():
            while True:
                try:
                    self.revisar()
                except Exception as e:
                    print(f"[agenda] {e}")
                time.sleep(1)
        threading.Thread(target=bucle, daemon=True, name="agenda").start()


def texto_aviso(item):
    tipo, mensaje = item.get("tipo"), item.get("mensaje") or ""
    if tipo == "temporizador":
        base = "¡Se acabó el tiempo!"
    elif tipo == "alarma":
        base = f"¡Alarma! Son las {dt.datetime.now():%H:%M}."
    else:
        base = "Te recuerdo:"
    if mensaje:
        base = f"{base} {mensaje}." if tipo != "recordatorio" else f"{base} {mensaje}."
    elif tipo == "recordatorio":
        base = "Es la hora que me pediste."
    if item.get("atrasado_min", 0) >= 5:
        base = f"Mientras no estaba encendido venció un aviso. {base}"
    return base
