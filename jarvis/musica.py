"""Música: YouTube (busca y reproduce el primer video), Spotify y las teclas multimedia del teclado."""
import re
import sys
import urllib.parse
import urllib.request
import webbrowser

TECLAS = {"pausa": 0xB3, "siguiente": 0xB0, "anterior": 0xB1, "detener": 0xB2}


def tecla(nombre) -> bool:
    """Pulsa una tecla multimedia: sirve para Spotify, YouTube en el navegador y casi cualquier reproductor."""
    if sys.platform != "win32":
        return False
    import ctypes
    codigo = TECLAS[nombre]
    ctypes.windll.user32.keybd_event(codigo, 0, 0, 0)
    ctypes.windll.user32.keybd_event(codigo, 0, 2, 0)
    return True


def primer_video(consulta) -> str:
    """Id del primer video de YouTube para la búsqueda (sin clave ni cuenta)."""
    url = "https://www.youtube.com/results?hl=es&search_query=" + urllib.parse.quote(consulta)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es"})
    with urllib.request.urlopen(req, timeout=8) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'"videoId":"([\w-]{11})"', html)
    return m.group(1) if m else ""


def youtube(consulta) -> str:
    try:
        video = primer_video(consulta)
    except Exception:
        video = ""
    if video:
        webbrowser.open(f"https://www.youtube.com/watch?v={video}")
        return f"Te pongo {consulta} en YouTube."
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(consulta))
    return f"Te abrí la búsqueda de {consulta} en YouTube."


def spotify(consulta) -> str:
    """Abre Spotify (la app si está instalada) con la búsqueda lista: elige y dale play."""
    uri = "spotify:search:" + urllib.parse.quote(consulta)
    try:
        if sys.platform == "win32":
            import os
            os.startfile(uri)
        else:
            webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(consulta))
    except OSError:
        webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(consulta))
    return f"Te abrí Spotify con {consulta}. Elige lo que quieras y dale play."


def reproducir(consulta, donde="youtube") -> str:
    consulta = (consulta or "música para estudiar").strip()
    return spotify(consulta) if donde == "spotify" else youtube(consulta)
