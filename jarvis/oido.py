"""Oído preciso con Whisper (faster-whisper), 100 % sin internet.

Vosk sigue escuchando siempre (es ligero y oye «Jarvis» al instante). Cuando terminas una orden, Whisper vuelve a
escuchar ese pedazo de audio y lo transcribe mucho mejor. Si Whisper no está instalado, se usa lo que entendió Vosk.
"""
import os
import re
import threading

from . import ajustes, config

# Palabras que Whisper debe esperar: así escribe bien los nombres propios.
PISTA = ("Jarvis, abre la carpeta de Documentos. Pon música en YouTube o Spotify. Recuérdame mañana a las 8. "
         "Léeme mis mensajes de WhatsApp. Crea un documento en Word.")
# Frases que Whisper a veces "oye" en el silencio
FANTASMAS = re.compile(r"(?i)subt[ií]tul|amara\.org|gracias por ver|suscr[ií]b|^\W*$")


class Transcriptor:
    def __init__(self):
        self._modelo = None
        self._lock = threading.Lock()
        self.disponible = False
        self.nombre = ""

    def cargar(self):
        """Carga el modelo (la primera vez lo descarga, unos 250-500 MB). Se llama en segundo plano."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("[oido] faster-whisper no está instalado: uso solo Vosk.")
            return False
        from .equipo import poca_ram
        nombre = ajustes.cargar().get("oido") or ("base" if poca_ram() else config.MODELO_WHISPER)
        try:
            hilos = max(2, (os.cpu_count() or 4) - 1)
            modelo = WhisperModel(nombre, device="cpu", compute_type="int8", cpu_threads=hilos,
                                  download_root=str(config.CARPETA_WHISPER))
        except Exception as e:
            print(f"[oido] No pude cargar Whisper {nombre}: {e}")
            return False
        with self._lock:
            self._modelo, self.nombre, self.disponible = modelo, nombre, True
        print(f"[oido] Whisper {nombre} listo.")
        return True

    def transcribir(self, pcm16: bytes):
        """Audio de 16 kHz, 16 bits, mono -> texto (o None si no se pudo)."""
        if not self.disponible or len(pcm16) < 16000 * 2 * 0.4:
            return None
        import numpy as np
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            with self._lock:
                segmentos, _ = self._modelo.transcribe(
                    audio, language="es", beam_size=1, initial_prompt=PISTA, condition_on_previous_text=False,
                    without_timestamps=True, vad_filter=False)
                texto = " ".join(s.text.strip() for s in segmentos).strip()
        except Exception as e:
            print(f"[oido] Whisper falló: {e}")
            return None
        return None if FANTASMAS.search(texto) else texto
