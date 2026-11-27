"""Leer y resumir documentos (PDF, Word, texto). La lectura es local; con Claude el resumen es mejor
y puedes hacerle preguntas sobre el documento."""
import collections
import os
import re

from .texto import normalizar

EXTENSIONES = {".pdf", ".docx", ".txt", ".md", ".csv", ".rtf", ".json", ".html", ".htm", ".pptx"}
MAX_CARACTERES_CLAUDE = 300_000  # unas 75 000 palabras; si es más largo, se avisa que se recortó

_VACIAS = set("""a al algo algunas algunos ante antes como con contra cual cuando de del desde donde dos el ella
ellas ellos en entre era eran es esa esas ese eso esos esta estas este esto estos fue fueron ha han hasta hay la
las le les lo los mas me mi mis muy no nos o otra otro para pero por porque que se sea ser si sin sobre son su
sus tambien te tiene tienen todo todos tu un una uno unos y ya yo the of and to in is for on that with as are be
this by it or an from at""".split())


def es_documento(ruta: str) -> bool:
    return os.path.splitext(ruta)[1].lower() in EXTENSIONES


def extraer_texto(ruta: str) -> tuple[str, str]:
    """Devuelve (texto, nota). La nota explica si algo no se pudo leer."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        if lector.is_encrypted:
            try:
                lector.decrypt("")
            except Exception:
                return "", "el PDF tiene contraseña"
        paginas = [(p.extract_text() or "") for p in lector.pages]
        texto = "\n\n".join(f"[Página {i}]\n{t.strip()}" for i, t in enumerate(paginas, 1) if t.strip())
        if not texto:
            return "", "el PDF parece escaneado (solo imágenes) y no tiene texto que pueda leer"
        return texto, f"{len(lector.pages)} páginas"
    if ext == ".docx":
        import docx
        d = docx.Document(ruta)
        partes = [p.text for p in d.paragraphs if p.text.strip()]
        for tabla in d.tables:
            for fila in tabla.rows:
                partes.append(" | ".join(c.text.strip() for c in fila.cells))
        return "\n".join(partes), ""
    if ext == ".pptx":
        from pptx import Presentation
        partes = []
        for i, diapo in enumerate(Presentation(ruta).slides, 1):
            textos = [s.text_frame.text for s in diapo.shapes if getattr(s, "has_text_frame", False) and s.text_frame.text.strip()]
            if textos:
                partes.append(f"[Diapositiva {i}]\n" + "\n".join(textos))
        return "\n\n".join(partes), ""
    if ext in {".txt", ".md", ".csv", ".rtf", ".json", ".html", ".htm"}:
        for codificacion in ("utf-8", "latin-1"):
            try:
                with open(ruta, encoding=codificacion) as f:
                    texto = f.read()
                break
            except UnicodeDecodeError:
                continue
        if ext in (".html", ".htm"):
            texto = re.sub(r"<[^>]+>", " ", texto)
        return texto, ""
    return "", "ese tipo de archivo no lo sé leer"


def para_claude(ruta: str) -> str:
    """Texto listo para mandar a Claude, avisando si hubo que recortarlo."""
    texto, nota = extraer_texto(ruta)
    if not texto:
        return f"No pude leer {os.path.basename(ruta)}: {nota or 'está vacío'}."
    cabecera = f"Documento: {os.path.basename(ruta)}" + (f" ({nota})" if nota else "")
    if len(texto) > MAX_CARACTERES_CLAUDE:
        texto = texto[:MAX_CARACTERES_CLAUDE]
        cabecera += (f". AVISO: el documento es muy largo; solo se leyeron los primeros {MAX_CARACTERES_CLAUDE:,} "
                     "caracteres. Díselo al usuario.")
    return f"{cabecera}\n\n{texto}"


def _frases(texto):
    texto = re.sub(r"\[(Página|Diapositiva) \d+\]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if 40 <= len(f.strip()) <= 400]


def resumen_local(texto: str, n=4) -> str:
    """Resumen sin internet: elige las frases con las palabras más importantes del documento."""
    frases = _frases(texto)
    if not frases:
        return ""
    palabras = [w for w in normalizar(texto).split() if len(w) > 3 and w not in _VACIAS and w.isalpha()]
    frecuencia = collections.Counter(palabras)
    if not frecuencia:
        return " ".join(frases[:n])
    maximo = frecuencia.most_common(1)[0][1]

    def puntaje(i, f):
        ws = [w for w in normalizar(f).split() if w in frecuencia]
        base = sum(frecuencia[w] / maximo for w in ws) / (len(f.split()) ** 0.6)
        return base * (1.25 if i < 3 else 1.0)  # el inicio suele presentar el tema

    mejores = sorted(sorted(enumerate(frases), key=lambda x: puntaje(*x), reverse=True)[:n])
    return " ".join(f for _, f in mejores)


def temas(texto: str, n=5) -> list:
    palabras = [w for w in normalizar(texto).split() if len(w) > 4 and w not in _VACIAS and w.isalpha()]
    return [w for w, _ in collections.Counter(palabras).most_common(n)]
