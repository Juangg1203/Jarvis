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
