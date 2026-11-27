"""Ordenar una carpeta (por ejemplo Descargas) en subcarpetas por tipo o por fecha. Siempre se puede deshacer."""
import datetime
import json
import os
import shutil
import time
from pathlib import Path

from . import config, seguridad

TIPOS = {
    "Imágenes": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".svg", ".ico", ".tiff"},
    "Documentos": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".ppt", ".pptx", ".odp",
                   ".xls", ".xlsx", ".ods", ".csv", ".epub"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"},
    "Música": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "Comprimidos": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Instaladores": {".exe", ".msi", ".msix", ".appx", ".apk", ".iso"},
    "Código": {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".json", ".xml", ".ipynb", ".sql"},
}
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
SIN_TERMINAR = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}

CARPETAS = {
    "descargas": ("Downloads", "Descargas"), "escritorio": ("Desktop", "Escritorio"),
    "documentos": ("Documents", "Documentos"), "imagenes": ("Pictures", "Imágenes"),
    "fotos": ("Pictures", "Imágenes"), "videos": ("Videos", "Vídeos"), "musica": ("Music", "Música"),
}


def _DESHACER():
    return config.CARPETA_DATOS / "ultimo_orden.json"


def carpeta(nombre: str):
    """'descargas' -> Path real (también dentro de OneDrive)."""
    for n in CARPETAS.get(nombre, ()):
        for base in (config.HOME, config.HOME / "OneDrive"):
            if (base / n).is_dir():
                return base / n
    p = Path(nombre).expanduser()
    return p if p.is_absolute() and p.is_dir() else None


def tipo_de(archivo: Path) -> str:
    ext = archivo.suffix.lower()
    return next((t for t, exts in TIPOS.items() if ext in exts), "Otros")


def planear(origen: Path, modo="tipo") -> list:
    """Lista de (archivo, carpeta_destino). Solo archivos sueltos; no toca subcarpetas ni descargas a medias."""
    plan, ahora = [], time.time()
    for a in sorted(origen.iterdir()):
        try:
            if not a.is_file() or a.name.startswith(".") or a.name.lower() in ("desktop.ini", "thumbs.db"):
                continue
            if a.suffix.lower() in SIN_TERMINAR or ahora - a.stat().st_mtime < 60:
                continue  # se está descargando o se acaba de crear
            if modo == "fecha":
                f = datetime.datetime.fromtimestamp(a.stat().st_mtime)
                destino = origen / f"{f.year}-{f.month:02d} {MESES[f.month - 1]}"
            else:
                destino = origen / tipo_de(a)
            plan.append((a, destino))
        except OSError:
            continue
    return plan


def describir(plan) -> str:
    conteo = {}
    for _, d in plan:
        conteo[d.name] = conteo.get(d.name, 0) + 1
    partes = [f"{n} a {c}" for c, n in sorted(conteo.items(), key=lambda x: -x[1])[:5]]
    return ", ".join(partes)


def _libre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    for i in range(1, 1000):
        otro = destino.with_name(f"{destino.stem} ({i}){destino.suffix}")
        if not otro.exists():
            return otro
    raise OSError("demasiados archivos con el mismo nombre")


def ejecutar(plan) -> int:
    movidos = []
    for archivo, carpeta_destino in plan:
        try:
            carpeta_destino.mkdir(exist_ok=True)
            final = _libre(carpeta_destino / archivo.name)
            shutil.move(str(archivo), str(final))
            movidos.append([str(archivo), str(final)])
        except OSError as e:
            print(f"[ordenar] {archivo}: {e}")
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    _DESHACER().write_text(json.dumps(movidos, ensure_ascii=False), encoding="utf-8")
    seguridad.registrar("ordenar", f"{len(movidos)} archivos")
    return len(movidos)


def deshacer() -> int:
    try:
        movidos = json.loads(_DESHACER().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    n = 0
    for antes, despues in reversed(movidos):
        try:
            if os.path.exists(despues) and not os.path.exists(antes):
                shutil.move(despues, antes)
                n += 1
        except OSError:
            pass
    for _, despues in movidos:  # borra las carpetas que quedaron vacías
        try:
            os.rmdir(os.path.dirname(despues))
        except OSError:
            pass
    _DESHACER().unlink(missing_ok=True)
    seguridad.registrar("deshacer_orden", str(n))
    return n
