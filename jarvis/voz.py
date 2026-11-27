"""Voz 100 % local: escucha con Vosk (sin internet) y habla con la voz de Windows."""
import json
import queue
import re
import threading
import time

from . import config
from .texto import normalizar


class Hablante:
    """Texto a voz en un hilo propio (las voces de Windows necesitan su propio hilo)."""

    def __init__(self):
        self._cola: queue.Queue = queue.Queue()
        self.hablando = threading.Event()
        threading.Thread(target=self._bucle, daemon=True, name="tts").start()

    def decir(self, texto: str, al_terminar=None):
        self._cola.put((texto, al_terminar))

    def _bucle(self):
        try:
            import pythoncom  # parte de pywin32, solo en Windows
            pythoncom.CoInitialize()
        except ImportError:
            pass
        motor = None
        try:
            import pyttsx3
            motor = pyttsx3.init()
            for v in motor.getProperty("voices"):
                desc = f"{v.name} {v.id} {getattr(v, 'languages', '')}".lower()
                if "spanish" in desc or "español" in desc or "es-" in desc or "helena" in desc or "sabina" in desc:
                    motor.setProperty("voice", v.id)
                    break
            motor.setProperty("rate", 175)
        except Exception as e:
            print(f"[voz] Sin texto a voz: {e}")
        while True:
            texto, al_terminar = self._cola.get()
            self.hablando.set()
            try:
                if motor:
                    motor.say(texto)
                    motor.runAndWait()
                else:
                    time.sleep(min(4, 0.06 * len(texto)))
            except Exception as e:
                print(f"[voz] Error al hablar: {e}")
            finally:
                time.sleep(0.3)  # evita que el micrófono capte el final de la frase
                self.hablando.clear()
                if al_terminar:
                    al_terminar()


class Oyente:
    """Escucha el micrófono sin parar, detecta 'Jarvis' y entrega la orden que sigue."""

    def __init__(self, al_cambiar_estado, al_recibir_orden, esta_hablando, al_oir_parcial=None):
        self.al_cambiar_estado = al_cambiar_estado  # fn(estado) -> 'esperando' | 'escuchando'
        self.al_recibir_orden = al_recibir_orden    # fn(texto)
        self.al_oir_parcial = al_oir_parcial or (lambda t: None)
        self.esta_hablando = esta_hablando          # fn() -> bool
        self._escuchar_ya = threading.Event()
        self.disponible = False
        self.error = ""

    def escuchar_ahora(self):
        """Como si hubieras dicho 'Jarvis' (botón del micrófono)."""
        self._escuchar_ya.set()

    def iniciar(self):
        threading.Thread(target=self._bucle, daemon=True, name="stt").start()

    def _quitar_activacion(self, texto: str):
        """Si el texto contiene la palabra de activación, devuelve lo que viene después ('' si nada)."""
        palabras = normalizar(texto).split()
        for i, p in enumerate(palabras):
            if p in config.VARIANTES_ACTIVACION:
                return " ".join(palabras[i + 1:])
        return None

    def _bucle(self):
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as e:
            self.error = f"Falta instalar una librería de voz ({e.name})."
            self.al_cambiar_estado("sin_voz")
            return
        if not config.CARPETA_MODELO.exists():
            self.error = "Falta el modelo de voz. Ejecuta instalar.bat otra vez."
            self.al_cambiar_estado("sin_voz")
            return
        SetLogLevel(-1)
        modelo = Model(str(config.CARPETA_MODELO))
        rec = KaldiRecognizer(modelo, 16000)
        audio: queue.Queue = queue.Queue()

        def callback(datos, frames, tiempo, estado):
            audio.put(bytes(datos))

        try:
            stream = sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16", channels=1, callback=callback)
            stream.start()
        except Exception as e:
            self.error = f"No pude abrir el micrófono: {e}"
            self.al_cambiar_estado("sin_voz")
            return

        self.disponible = True
        activo_hasta = 0.0
        self.al_cambiar_estado("esperando")
        while True:
            if self._escuchar_ya.is_set():
                self._escuchar_ya.clear()
                rec.Reset()
                activo_hasta = time.monotonic() + config.ESPERA_ORDEN_SEG
                self.al_cambiar_estado("escuchando")

            try:
                bloque = audio.get(timeout=0.5)
            except queue.Empty:
                bloque = None

            if self.esta_hablando():
                rec.Reset()
                continue

            escuchando = time.monotonic() < activo_hasta
            if activo_hasta and not escuchando:
                activo_hasta = 0.0
                self.al_cambiar_estado("esperando")
            if bloque is None:
                continue

            if rec.AcceptWaveform(bloque):
                texto = json.loads(rec.Result()).get("text", "").strip()
                if not texto:
                    continue
                resto = self._quitar_activacion(texto)
                if escuchando:
                    if resto == "":  # solo dijiste "Jarvis": sigo esperando la orden
                        activo_hasta = time.monotonic() + config.ESPERA_ORDEN_SEG
                        continue
                    activo_hasta = 0.0
                    self.al_recibir_orden(resto if resto is not None else texto)
                elif resto is not None:
                    if resto:
                        self.al_recibir_orden(resto)
                    else:
                        activo_hasta = time.monotonic() + config.ESPERA_ORDEN_SEG
                        self.al_cambiar_estado("escuchando")
            else:
                parcial = json.loads(rec.PartialResult()).get("partial", "")
                if escuchando and parcial:
                    self.al_oir_parcial(parcial)
                elif not escuchando and re.search(r"\b(" + "|".join(config.VARIANTES_ACTIVACION) + r")\b", parcial):
                    # Reacciona en cuanto oye su nombre, sin esperar a que termines la frase.
                    activo_hasta = time.monotonic() + config.ESPERA_ORDEN_SEG
                    self.al_cambiar_estado("escuchando")
