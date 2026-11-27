"""Voz 100 % local: oye con Vosk, entiende cada orden con Whisper (si está) y habla con Piper, Edge o Windows."""
import json
import queue
import re
import threading
import time

from . import config
from .texto import normalizar


class Hablante:
    """Texto a voz en un hilo propio, frase por frase, con nivel de audio para animar el avatar.

    Motores (se usa el primero que funcione):
      - piper:   voz neuronal masculina, natural y 100 % local.
      - edge:    voz de Microsoft aún más natural (es-CO-GonzaloNeural); necesita internet.
      - windows: la voz del sistema (respaldo).
    """

    def __init__(self, motor="piper", voz_edge="es-CO-GonzaloNeural", al_nivel=None):
        self._cola: queue.Queue = queue.Queue()
        self.hablando = threading.Event()
        self._cortar = threading.Event()
        self.motor = motor
        self.voz_edge = voz_edge
        self.al_nivel = al_nivel or (lambda n: None)
        self._piper = None
        self._pyttsx3 = None
        threading.Thread(target=self._bucle, daemon=True, name="tts").start()

    # ---------- API pública ----------
    def decir(self, texto: str, al_terminar=None):
        """Encola una frase. al_terminar se llama cuando esa frase acaba de sonar."""
        texto = texto.strip()
        if texto:
            self._cortar.clear()
            self.hablando.set()
            self._cola.put(("texto", texto, al_terminar))
        elif al_terminar:
            self.despues(al_terminar)

    def despues(self, funcion):
        """Ejecuta funcion cuando termine todo lo que hay en cola."""
        self._cola.put(("fin", None, funcion))

    def callar(self):
        """Interrumpe lo que esté diciendo y descarta lo que quedaba en cola."""
        self._cortar.set()
        while True:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                break

    # ---------- motores ----------
    def _sintetizar_piper(self, texto):
        if self._piper is None:
            from piper import PiperVoice
            ruta = config.CARPETA_VOCES / f"{config.VOZ_PIPER}.onnx"
            if not ruta.exists():
                raise FileNotFoundError(ruta)
            self._piper = PiperVoice.load(str(ruta))
        for chunk in self._piper.synthesize(texto):
            yield chunk.sample_rate, chunk.audio_int16_bytes

    def _sintetizar_edge(self, texto):
        import asyncio

        import edge_tts
        import miniaudio

        async def bajar():
            mp3 = bytearray()
            async for parte in edge_tts.Communicate(texto, self.voz_edge, rate="+5%").stream():
                if parte["type"] == "audio":
                    mp3.extend(parte["data"])
            return bytes(mp3)

        mp3 = asyncio.run(bajar())
        pcm = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
        yield 24000, pcm.samples.tobytes()

    def _reproducir(self, generador):
        import numpy as np
        import sounddevice as sd

        stream, tasa = None, None
        try:
            for sr, datos in generador:
                if self._cortar.is_set():
                    return
                if stream is None or sr != tasa:
                    if stream:
                        stream.stop(); stream.close()
                    tasa = sr
                    stream = sd.OutputStream(samplerate=sr, channels=1, dtype="int16")
                    stream.start()
                audio = np.frombuffer(datos, dtype=np.int16)
                paso = max(1, sr // 25)  # bloques de 40 ms -> 25 actualizaciones por segundo
                for i in range(0, len(audio), paso):
                    if self._cortar.is_set():
                        return
                    bloque = audio[i:i + paso]
                    nivel = float(np.sqrt(np.mean((bloque.astype(np.float32) / 32768) ** 2))) if len(bloque) else 0.0
                    self.al_nivel(min(1.0, nivel * 4))
                    stream.write(bloque)
        finally:
            self.al_nivel(0.0)
            if stream:
                stream.stop(); stream.close()

    def _decir_windows(self, texto):
        if self._pyttsx3 is None:
            import pyttsx3
            self._pyttsx3 = pyttsx3.init()
            for v in self._pyttsx3.getProperty("voices"):
                desc = f"{v.name} {v.id}".lower()
                if ("spanish" in desc or "español" in desc) and ("raul" in desc or "pablo" in desc or "jorge" in desc):
                    self._pyttsx3.setProperty("voice", v.id)
                    break
            else:
                for v in self._pyttsx3.getProperty("voices"):
                    if "spanish" in f"{v.name} {v.id}".lower() or "español" in v.name.lower():
                        self._pyttsx3.setProperty("voice", v.id)
                        break
            self._pyttsx3.setProperty("rate", 175)
        self.al_nivel(0.5)
        self._pyttsx3.say(texto)
        self._pyttsx3.runAndWait()
        self.al_nivel(0.0)

    def _hablar(self, texto):
        orden = {"piper": ["piper", "windows"], "edge": ["edge", "piper", "windows"]}.get(self.motor, ["windows"])
        for motor in orden:
            try:
                if motor == "piper":
                    self._reproducir(self._sintetizar_piper(texto))
                elif motor == "edge":
                    self._reproducir(self._sintetizar_edge(texto))
                else:
                    self._decir_windows(texto)
                return
            except Exception as e:
                print(f"[voz] El motor {motor} falló ({e}); pruebo el siguiente.")
        time.sleep(min(4, 0.06 * len(texto)))  # sin voz: al menos deja ver la animación

    def _bucle(self):
        try:
            import pythoncom  # parte de pywin32, solo en Windows (lo necesita la voz de Windows)
            pythoncom.CoInitialize()
        except ImportError:
            pass
        while True:
            tipo, texto, al_terminar = self._cola.get()
            if tipo == "texto" and not self._cortar.is_set():
                self.hablando.set()
                try:
                    self._hablar(texto)
                except Exception as e:
                    print(f"[voz] Error al hablar: {e}")
            if self._cola.empty():
                time.sleep(0.25)  # evita que el micrófono capte el final de la frase
                if self._cola.empty():
                    self.hablando.clear()
            if al_terminar:
                try:
                    al_terminar()
                except Exception as e:
                    print(f"[voz] Error en callback: {e}")


class Oyente:
    """Escucha el micrófono sin parar, detecta 'Jarvis' y entrega la orden que sigue."""

    def __init__(self, al_cambiar_estado, al_recibir_orden, esta_hablando, al_oir_parcial=None):
        self.al_cambiar_estado = al_cambiar_estado  # fn(estado) -> 'esperando' | 'escuchando'
        self.al_recibir_orden = al_recibir_orden    # fn(texto)
        self.al_oir_parcial = al_oir_parcial or (lambda t: None)
        self.esta_hablando = esta_hablando          # fn() -> bool
        self._escuchar_ya = threading.Event()
        self.disponible = False
        self.reconoce_hablante = False
        self.error = ""
        self.transcriptor = None  # oido.Transcriptor: Whisper para entender mejor cada orden

    def _entregar(self, texto, huella=None):
        # En otro hilo, para seguir oyendo (y poder interrumpir) mientras Jarvis piensa y habla.
        # huella = (vector de la voz, cuadros) si está el modelo de hablantes, para saber si eres tú.
        threading.Thread(target=self.al_recibir_orden, args=(texto, huella), daemon=True).start()

    def escuchar_ahora(self):
        """Como si hubieras dicho 'Jarvis' (botón del micrófono)."""
        self._escuchar_ya.set()

    def iniciar(self):
        threading.Thread(target=self._bucle, daemon=True, name="stt").start()
        from .oido import Transcriptor
        self.transcriptor = Transcriptor()
        threading.Thread(target=self.transcriptor.cargar, daemon=True, name="whisper").start()

    def _quitar_activacion(self, texto: str):
        """Si el texto contiene la palabra de activación, devuelve lo que viene después ('' si nada)."""
        palabras = normalizar(texto).split()
        for i, p in enumerate(palabras):
            if p in config.VARIANTES_ACTIVACION:
                return " ".join(palabras[i + 1:])
        return None

    def _texto_final(self, vosk_texto, audio, escuchando):
        """Lo que se entrega: Whisper (más preciso) si está, si no lo que oyó Vosk. None si no era para Jarvis."""
        resto_vosk = self._quitar_activacion(vosk_texto)
        if not escuchando and resto_vosk is None:
            return None  # hablabas con otra persona, no con Jarvis
        if self.transcriptor and self.transcriptor.disponible and audio:
            self.al_cambiar_estado("pensando")
            preciso = self.transcriptor.transcribir(bytes(audio))
            if preciso:
                preciso = re.sub(r"\s+", " ", re.sub(r"(?<!\d)[.…](?!\d)", " ", preciso)).strip()
                resto = self._quitar_activacion(preciso)
                if resto is not None:
                    return resto
                if escuchando or resto_vosk is None:
                    return normalizar(preciso)
                # Vosk oyó «Jarvis» pero Whisper lo escribió distinto: quita las primeras palabras equivalentes
                n = len(normalizar(vosk_texto).split()) - len(resto_vosk.split())
                return " ".join(normalizar(preciso).split()[n:])
        return resto_vosk if resto_vosk is not None else vosk_texto

    def _bucle(self):
        try:
            import numpy as np
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
        self.reconoce_hablante = False
        try:
            from vosk import SpkModel
            from .identidad import ruta_modelo_voz
            if ruta_modelo_voz().exists():
                rec.SetSpkModel(SpkModel(str(ruta_modelo_voz())))
                self.reconoce_hablante = True
        except Exception as e:
            print(f"[voz] Sin reconocimiento de hablante: {e}")
        audio: queue.Queue = queue.Queue()

        def callback(datos, frames, tiempo, estado):
            audio.put(bytes(datos))

        try:
            # bloques de 0,1 s: así se nota enseguida cuando dejas de hablar
            stream = sd.RawInputStream(samplerate=16000, blocksize=1600, dtype="int16", channels=1, callback=callback)
            stream.start()
        except Exception as e:
            self.error = f"No pude abrir el micrófono: {e}"
            self.al_cambiar_estado("sin_voz")
            return

        self.disponible = True
        activo_hasta = 0.0
        frase = bytearray()            # audio desde que empezó la frase actual (para Whisper)
        ruido = 200.0                   # nivel del ruido de fondo, se ajusta solo
        hablo, ultimo_sonido, inicio = False, 0.0, 0.0
        maximo = 16000 * 2 * config.MAX_ORDEN_SEG
        self.al_cambiar_estado("esperando")

        def empezar_a_escuchar():
            nonlocal activo_hasta, hablo, inicio
            activo_hasta = time.monotonic() + config.ESPERA_ORDEN_SEG
            hablo, inicio = False, time.monotonic()
            self.al_cambiar_estado("escuchando")

        while True:
            if self._escuchar_ya.is_set():
                self._escuchar_ya.clear()
                rec.Reset()
                frase.clear()
                empezar_a_escuchar()

            try:
                bloque = audio.get(timeout=0.5)
            except queue.Empty:
                bloque = None

            if self.esta_hablando():
                rec.Reset()
                frase.clear()
                continue

            ahora = time.monotonic()
            escuchando = ahora < activo_hasta
            if activo_hasta and not escuchando:
                activo_hasta = 0.0
                self.al_cambiar_estado("esperando")
            if bloque is None:
                continue

            # ¿Hay voz en este pedacito? Se compara con el ruido de fondo medido.
            nivel = float(np.sqrt(np.mean(np.frombuffer(bloque, dtype=np.int16).astype(np.float32) ** 2)))
            if nivel < ruido * 1.6:
                ruido = 0.97 * ruido + 0.03 * max(nivel, 50.0)
            hay_voz = nivel > max(config.NIVEL_VOZ_MIN, ruido * 2.5)
            frase += bloque
            if len(frase) > maximo:
                del frase[:len(frase) - maximo]

            fin = False
            if escuchando:
                if hay_voz:
                    hablo, ultimo_sonido = True, ahora
                    activo_hasta = max(activo_hasta, ahora + 3)  # no te corta mientras sigues hablando
                fin = hablo and (ahora - ultimo_sonido > config.SILENCIO_FIN_SEG or ahora - inicio > config.MAX_ORDEN_SEG)

            if rec.AcceptWaveform(bloque) or fin:
                resultado = json.loads(rec.Result() if not fin else rec.FinalResult())
                if fin:
                    rec.Reset()
                texto = resultado.get("text", "").strip()
                audio_frase, frase = frase, bytearray()
                if not texto:
                    hablo = False
                    continue
                huella = (resultado["spk"], resultado.get("spk_frames", 0)) if resultado.get("spk") else None
                if escuchando and self._quitar_activacion(texto) == "":  # solo dijiste "Jarvis": sigo esperando
                    empezar_a_escuchar()
                    continue
                if not escuchando and self._quitar_activacion(texto) == "":
                    empezar_a_escuchar()
                    continue
                orden = self._texto_final(texto, audio_frase, escuchando)
                if orden is None:
                    continue
                activo_hasta, hablo = 0.0, False
                if orden.strip():
                    self._entregar(orden, huella)
                else:
                    self.al_cambiar_estado("esperando")
            else:
                parcial = json.loads(rec.PartialResult()).get("partial", "")
                if escuchando and parcial:
                    self.al_oir_parcial(parcial)
                elif not escuchando and re.search(r"\b(" + "|".join(config.VARIANTES_ACTIVACION) + r")\b", parcial):
                    # Reacciona en cuanto oye su nombre, sin esperar a que termines la frase.
                    empezar_a_escuchar()
                    hablo, ultimo_sonido = True, ahora
