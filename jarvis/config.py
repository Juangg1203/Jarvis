"""Configuración de Jarvis. Cambia aquí lo que quieras personalizar."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOME = Path.home()

# Cómo te llama Jarvis.
NOMBRE_USUARIO = "Juan"

# Palabra de activación y variantes que el reconocedor suele escuchar en español.
PALABRA_ACTIVACION = "jarvis"
VARIANTES_ACTIVACION = {"jarvis", "yarvis", "jarbis", "yarbis", "harvis", "charvis", "jarvi", "yervis", "garbis"}

# Modelo de voz offline (Vosk). Se descarga con scripts/descargar_modelo.py
CARPETA_MODELO = RAIZ / "modelos" / "vosk-model-small-es-0.42"

# Segundos que Jarvis espera una orden después de oír su nombre.
ESPERA_ORDEN_SEG = 8

# Carpetas donde Jarvis busca archivos.
CARPETAS_BUSQUEDA = [
    HOME / "Desktop", HOME / "Escritorio",
    HOME / "Documents", HOME / "Documentos",
    HOME / "Downloads", HOME / "Descargas",
    HOME / "Pictures", HOME / "Imágenes",
    HOME / "Music", HOME / "Música",
    HOME / "Videos", HOME / "Vídeos",
    HOME / "OneDrive",
]
CARPETAS_IGNORADAS = {"node_modules", ".git", "__pycache__", "appdata", "venv", ".venv", "$recycle.bin"}
MAX_RESULTADOS = 15
TIEMPO_MAX_BUSQUEDA_SEG = 8

# Datos locales de Jarvis (registro de acciones). Nada sale de tu computador.
CARPETA_DATOS = Path(os.environ.get("LOCALAPPDATA", HOME / ".local" / "share")) / "Jarvis"
