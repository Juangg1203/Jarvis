"""Dictar documentos de Word y borradores de correo. Jarvis nunca envía un correo solo: lo deja listo para ti."""
import datetime
import os
import re
import sys
import urllib.parse
import webbrowser

from . import config


def carpeta_documentos():
    from . import organizar
    real = organizar.carpeta("documentos")  # la que usa Windows (también dentro de OneDrive)
    if real:
        return real / "Jarvis"
    for n in ("Documents", "Documentos"):
        for base in (config.HOME / "OneDrive", config.HOME):
            if (base / n).is_dir():
                return base / n / "Jarvis"
    return config.HOME / "Documentos" / "Jarvis"


def nombre_archivo(titulo: str) -> str:
    limpio = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", titulo).strip()[:60] or "Documento"
    return limpio


def crear_documento(titulo: str, texto: str, abrir=True) -> str:
    """Guarda un .docx en Documentos\\Jarvis y lo abre en Word. Devuelve la ruta."""
    from docx import Document
    doc = Document()
    if titulo:
        doc.add_heading(titulo, level=1)
    for parrafo in re.split(r"\n\s*\n|\n", texto.strip()):
        if parrafo.strip():
            doc.add_paragraph(parrafo.strip())
    carpeta = carpeta_documentos()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre_archivo(titulo)} {datetime.datetime.now():%Y-%m-%d %H%M}.docx"
    doc.save(ruta)
    if abrir and sys.platform == "win32":
        try:
            os.startfile(str(ruta))
        except OSError:  # sin Word instalado: muestra el archivo en su carpeta
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(ruta)])
    return str(ruta)


def separar_titulo(texto: str, respaldo: str = "Documento"):
    """La primera línea corta del texto es el título; el resto, el cuerpo."""
    lineas = [l.strip(" #*") for l in texto.strip().splitlines()]
    if lineas and 0 < len(lineas[0]) <= 90 and len(lineas) > 1:
        return lineas[0].rstrip(".:"), "\n".join(lineas[1:]).strip()
    return respaldo, texto.strip()


def borrador_correo(para="", asunto="", cuerpo="") -> str:
    """Abre tu programa de correo con el mensaje escrito. Tú revisas y le das Enviar."""
    partes = {k: v for k, v in (("subject", asunto), ("body", cuerpo)) if v}
    url = "mailto:" + urllib.parse.quote(para.strip(), safe="@,.") + \
          ("?" + urllib.parse.urlencode(partes, quote_via=urllib.parse.quote) if partes else "")
    webbrowser.open(url)
    return url


def puntuar(texto: str) -> str:
    """Convierte la puntuación dictada en símbolos: 'coma', 'punto', 'punto y aparte'..."""
    reemplazos = [(r"\s*\bpunto y aparte\b\s*", ".\n"), (r"\s*\bnueva l[ií]nea\b\s*", "\n"),
                  (r"\s*\bpunto y coma\b", ";"), (r"\s*\bdos puntos\b", ":"), (r"\s*\bpunto\b", "."),
                  (r"\s*\bcoma\b", ","), (r"\s*\bsigno de pregunta\b", "?"), (r"\s*\bsigno de exclamaci[oó]n\b", "!")]
    for patron, simbolo in reemplazos:
        texto = re.sub(patron, simbolo, texto, flags=re.I)
    # mayúscula al empezar y después de cada punto
    texto = re.sub(r"(^|[.!?]\s+|\n)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), texto.strip())
    return texto
