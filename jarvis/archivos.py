"""Buscar, abrir y eliminar archivos y aplicaciones."""
import os
import subprocess
import sys
import time
from pathlib import Path

from . import config
from .texto import normalizar

# Nombres que puedes decir -> programa de Windows.
ALIAS_APPS = {
    "bloc de notas": "notepad", "notas": "notepad",
    "calculadora": "calc",
    "explorador": "explorer", "explorador de archivos": "explorer", "mis archivos": "explorer",
    "paint": "mspaint",
    "configuracion": "ms-settings:", "ajustes": "ms-settings:",
    "administrador de tareas": "taskmgr",
    "terminal": "wt", "consola": "cmd", "simbolo del sistema": "cmd",
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "navegador": "msedge",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "visual studio code": "code", "vs code": "code", "codigo": "code",
    "spotify": "spotify:",
    "camara": "microsoft.windows.camera:",
    "correo": "outlookmail:",
}


def _carpetas_menu_inicio():
    rutas = []
    for var in ("ProgramData", "APPDATA"):
        base = os.environ.get(var)
        if base:
            rutas.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return rutas


_cache_apps = None


def apps_instaladas() -> dict:
    """Lee los accesos directos del menú Inicio: {nombre normalizado: ruta}."""
    global _cache_apps
    if _cache_apps is None:
        _cache_apps = {}
        for carpeta in _carpetas_menu_inicio():
            if carpeta.exists():
                for lnk in carpeta.rglob("*.lnk"):
                    _cache_apps.setdefault(normalizar(lnk.stem), str(lnk))
    return _cache_apps


def buscar_app(nombre: str):
    """Devuelve (etiqueta, destino) o None."""
    n = normalizar(nombre)
    if n in ALIAS_APPS:
        return nombre, ALIAS_APPS[n]
    apps = apps_instaladas()
    if n in apps:
        return Path(apps[n]).stem, apps[n]
    candidatos = [k for k in apps if n and n in k]
    if candidatos:
        mejor = min(candidatos, key=len)
        return Path(apps[mejor]).stem, apps[mejor]
    return None


def buscar_archivos(consulta: str, carpetas=None, limite=None, tiempo_max=None) -> list[str]:
    """Busca archivos y carpetas cuyo nombre contenga todas las palabras de la consulta."""
    palabras = normalizar(consulta).split()
    if not palabras:
        return []
    carpetas = carpetas if carpetas is not None else config.CARPETAS_BUSQUEDA
    limite = limite or config.MAX_RESULTADOS
    tiempo_max = tiempo_max or config.TIEMPO_MAX_BUSQUEDA_SEG
    inicio = time.monotonic()
    vistos, resultados = set(), []
    for base in carpetas:
        base = Path(base)
        if not base.exists():
            continue
        real = os.path.realpath(base)
        if real in vistos:
            continue
        vistos.add(real)
        for raiz, dirs, archivos in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in config.CARPETAS_IGNORADAS]
            for nombre in dirs + archivos:
                n = normalizar(nombre).replace(".", " ").replace("_", " ").replace("-", " ")
                if all(p in n for p in palabras):
                    resultados.append(os.path.join(raiz, nombre))
                    if len(resultados) >= limite:
                        return resultados
            if time.monotonic() - inicio > tiempo_max:
                return resultados
    return resultados


def abrir(destino: str) -> None:
    """Abre un archivo, carpeta, app o enlace con el programa predeterminado."""
    if sys.platform == "win32":
        try:
            os.startfile(destino)  # noqa: S606 - es la forma estándar de abrir en Windows
        except OSError:
            subprocess.Popen(["cmd", "/c", "start", "", destino],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", destino])
    else:
        subprocess.Popen(["xdg-open", destino])


def enviar_a_papelera(ruta: str) -> None:
    """Nunca borra de forma permanente: manda a la Papelera de reciclaje."""
    from send2trash import send2trash
    send2trash(ruta)
