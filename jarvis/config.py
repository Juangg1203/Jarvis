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

# Voz de Jarvis (Piper, sin internet). Voz masculina en español latino.
VOZ_PIPER = "es_MX-claude-high"
CARPETA_VOCES = RAIZ / "modelos" / "voces"

# Gemini (conversación GRATIS): clave en aistudio.google.com. "gemini-flash-latest" es siempre el Flash más nuevo.
MODELO_GEMINI = "gemini-flash-latest"
MODELO_GEMINI_RESPALDO = "gemini-2.5-flash"

# Ollama (conversación GRATIS y SIN INTERNET, en tu propio portátil). Se instala con instalar_ollama.bat.
MODELO_OLLAMA = "qwen2.5:3b"            # unos 2 GB; si tu portátil tiene 16 GB de RAM puedes probar "qwen2.5:7b"
MODELO_OLLAMA_RAPIDO = "qwen2.5:1.5b"   # 1 GB: responde más o menos el doble de rápido, pero entiende menos
MODELO_OLLAMA_VISION = "qwen2.5vl:3b"   # opcional, para «mira mi pantalla» sin internet (unos 3 GB)

# Claude (conversación, de pago). Necesita internet y una clave de API de console.anthropic.com.
MODELO_CLAUDE = "claude-opus-5-5"
ESFUERZO_CLAUDE = "low"      # low = responde más rápido; sube a "medium" si quieres respuestas más pensadas
MAX_MENSAJES_HISTORIAL = 40  # al pasar de aquí, Jarvis empieza una conversación nueva
MINUTOS_NUEVA_CONVERSACION = 30  # tras este rato sin hablar, la charla se resume y empieza otra

# Búsquedas en internet sin Claude. Tu ciudad para el clima (si la dejas vacía, Jarvis la busca en lo que
# recuerda de ti: di «recuerda que vivo en Bogotá») y el país de las noticias (CO, MX, AR, ES, US...).
CIUDAD = ""
PAIS_NOTICIAS = "CO"

# App del celular: puerto de la página que abre el teléfono en el wifi de tu casa.
PUERTO_CELULAR = 8765

# Seguridad: parecido mínimo (0 a 1) para aceptar tu voz o tu cara. Súbelo si alguien más logra engañarlo;
# bájalo si a ti no te reconoce.
UMBRAL_VOZ = 0.50
UMBRAL_CARA = 0.40
DISCO_LLENO_PORCENTAJE = 90

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
