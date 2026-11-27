"""Utilidades de texto en español."""
import re
import unicodedata

NUMEROS = {
    "uno": 1, "una": 1, "primero": 1, "primera": 1,
    "dos": 2, "segundo": 2, "segunda": 2,
    "tres": 3, "tercero": 3, "tercera": 3,
    "cuatro": 4, "cuarto": 4, "cuarta": 4,
    "cinco": 5, "quinto": 5, "quinta": 5,
    "seis": 6, "sexto": 6, "sexta": 6,
    "siete": 7, "septimo": 7, "septima": 7,
    "ocho": 8, "octavo": 8, "octava": 8,
    "nueve": 9, "noveno": 9, "novena": 9,
    "diez": 10, "decimo": 10, "decima": 10,
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos, espacios simples."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[¿?¡!,;:\"']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def extraer_numero(texto: str):
    """'el numero dos' -> 2, 'el 3' -> 3, 'el primero' -> 1. None si no hay número."""
    t = normalizar(texto)
    m = re.fullmatch(r"(?:el |la )?(?:resultado |archivo |opcion )?(?:numero |n )?(\w+)", t)
    if not m:
        return None
    palabra = m.group(1)
    if palabra.isdigit():
        return int(palabra)
    return NUMEROS.get(palabra)


# ---------- peticiones dichas de forma natural -> orden directa ----------
_SALUDO = r"(?:hola|oye|hey|ey|buenos dias|buenas tardes|buenas noches|buenas|ok|okey|bueno|porfa|por favor|" \
          r"jarvis|yarvis|jarbis|yarbis|harvis|charvis|jarvi|yervis|garbis|yerbas|jarbas|yarbas|jervis)"
_CORTESIA = r"(?:(?:yo )?(?:quiero|quisiera|necesito|me gustaria) que (?:tu )?|(?:tu )?(?:puedes|podrias|pudieras)|" \
            r"ayudame a|hazme el favor de|por favor|porfa)"
# subjuntivo o infinitivo -> imperativo ("que abras" / "puedes abrir" -> "abre")
_VERBOS = {
    "abre": ("abras", "abrir"), "cierra": ("cierres", "cerrar"), "busca": ("busques", "buscar"),
    "organiza": ("organices", "organizar"), "ordena": ("ordenes", "ordenar"), "acomoda": ("acomodes", "acomodar"),
    "pon": ("pongas", "poner"), "lee": ("leas", "leer"), "resume": ("resumas", "resumir"),
    "apaga": ("apagues", "apagar"), "reinicia": ("reinicies", "reiniciar"), "bloquea": ("bloquees", "bloquear"),
    "sube": ("subas", "subir"), "baja": ("bajes", "bajar"), "escribe": ("escribas", "escribir"),
    "muestra": ("muestres", "mostrar"), "di": ("digas", "decir"), "vigila": ("vigiles", "vigilar"),
    "borra": ("borres", "borrar"), "elimina": ("elimines", "eliminar"), "crea": ("crees", "crear"),
    "mira": ("mires", "mirar"), "revisa": ("revises", "revisar"), "quita": ("quites", "quitar"),
    "recuerda": ("recuerdes", "recordar"), "silencia": ("silencies", "silenciar"), "dicta": ("dictes", "dictar"),
    "reproduce": ("reproduzcas", "reproducir"), "deshaz": ("deshagas", "deshacer"), "analiza": ("analices", "analizar"),
}
_A_IMPERATIVO = {forma: imp for imp, formas in _VERBOS.items() for forma in formas}
_CON_ME = {"di": "dime", "recuerda": "recuerdame", "pon": "ponme", "muestra": "muestrame", "lee": "leeme",
           "busca": "buscame", "resume": "resumeme"}


def limpiar_peticion(t: str) -> str:
    """'hola jarvis quiero que me abras la carpeta de documentos' -> 'abre la carpeta de documentos'.

    Recibe un texto ya normalizado. Si solo era un saludo, lo devuelve igual."""
    limpio = t
    while True:
        nuevo = re.sub(r"^(?:tu )?me (?:puedes|podrias|pudieras) ", "me ", limpio)
        nuevo = re.sub(rf"^(?:{_SALUDO}|{_CORTESIA})\b\s*", "", nuevo)
        if nuevo == limpio:
            break
        limpio = nuevo
    limpio = re.sub(r"\s+(?:por favor|porfa|porfavor|gracias)$", "", limpio)
    m = re.match(r"^(me |te )?(\w+)\b(.*)$", limpio)
    if m and (m.group(2) in _A_IMPERATIVO or (m.group(1) and m.group(2) in _VERBOS)):
        verbo = _A_IMPERATIVO.get(m.group(2), m.group(2))
        if m.group(1) == "me ":
            verbo = _CON_ME.get(verbo, verbo)
        limpio = verbo + m.group(3)
    return limpio.strip() or t
