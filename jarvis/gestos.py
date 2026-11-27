"""Lenguaje de señas básico con la cámara, 100 % local (MediaPipe). No se guarda ninguna imagen.

Gestos que entiende (mantenlos un segundo frente a la cámara):
  ✋ palma abierta   -> Jarvis te escucha
  ✊ puño            -> silencio (calla a Jarvis y silencia el sonido)
  👍 pulgar arriba   -> «sí» (confirma)
  👎 pulgar abajo    -> «no» (cancela)
  ☝️ índice arriba   -> sube el volumen
  ✌️ dos dedos (V)   -> baja el volumen
  🤟 «te quiero»     -> muestra u oculta la ventana de Jarvis

Modo deletrear (di «vamos a deletrear»): letras del alfabeto manual A B D F I L O S U V W Y,
✋ mano abierta = espacio, y al bajar la mano 3 segundos Jarvis dice la palabra y la usa como orden.
"""
import math
import threading
import time

from . import config

NOMBRES = {
    "palma": "✋ Te escucho",
    "puno": "✊ Silencio",
    "pulgar_arriba": "👍 Sí",
    "pulgar_abajo": "👎 No",
    "indice": "☝️ Subir volumen",
    "dos": "✌️ Bajar volumen",
    "te_quiero": "🤟 Mostrar / ocultar",
}

# Índices de los 21 puntos de la mano de MediaPipe
MUNECA = 0
DEDOS = {  # punta, articulación media, nudillo
    "indice": (8, 6, 5),
    "medio": (12, 10, 9),
    "anular": (16, 14, 13),
    "menique": (20, 18, 17),
}


def _d(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def dedos_extendidos(p):
    """p: lista de 21 puntos con .x .y. Devuelve dict dedo->bool (incluye 'pulgar')."""
    m = p[MUNECA]
    res = {}
    for dedo, (punta, medio, nudillo) in DEDOS.items():
        res[dedo] = _d(m, p[punta]) > _d(m, p[medio]) * 1.12 and _d(m, p[punta]) > _d(m, p[nudillo]) * 1.3
    tamano = _d(m, p[9]) or 1e-6
    # pulgar: extendido si la punta se aleja del nudillo del índice y del meñique
    res["pulgar"] = (_d(p[4], p[5]) > _d(p[3], p[5]) * 1.15 and _d(p[4], p[17]) > _d(p[2], p[17])
                     and _d(p[4], p[5]) > tamano * 0.45)
    return res


def clasificar(p):
    """Devuelve el nombre del gesto o None."""
    if not p or len(p) < 21:
        return None
    e = dedos_extendidos(p)
    tamano = _d(p[MUNECA], p[9]) or 1e-6
    otros = [e["indice"], e["medio"], e["anular"], e["menique"]]
    if all(otros) and e["pulgar"]:
        return "palma"
    if not any(otros):
        vertical = (p[2].y - p[4].y) / tamano  # positivo = pulgar hacia arriba (y crece hacia abajo)
        if e["pulgar"] and vertical > 0.6:
            return "pulgar_arriba"
        if e["pulgar"] and vertical < -0.6:
            return "pulgar_abajo"
        if not e["pulgar"] or abs(vertical) < 0.4:
            return "puno"
        return None
    if e["indice"] and not e["medio"] and not e["anular"] and e["menique"] and e["pulgar"]:
        return "te_quiero"
    if e["indice"] and not e["medio"] and not e["anular"] and not e["menique"]:
        return "indice"
    if e["indice"] and e["medio"] and not e["anular"] and not e["menique"]:
        return "dos"
    return None


LETRAS = "ABDFILOSUVWY"


def letra(p):
    """Letra del alfabeto manual (formas estáticas sencillas) o 'espacio' o None."""
    if not p or len(p) < 21:
        return None
    e = dedos_extendidos(p)
    t = _d(p[MUNECA], p[9]) or 1e-6
    toca = {dedo: _d(p[4], p[punta]) < t * 0.38 for dedo, (punta, _, _) in DEDOS.items()}
    i, m, a, n, pu = e["indice"], e["medio"], e["anular"], e["menique"], e["pulgar"]
    if i and m and a and n:
        return "espacio" if pu else "B"
    if toca["indice"] and m and a and n:
        return "F"
    if not (i or m or a or n):
        # O: las puntas se curvan hasta el pulgar formando un aro (en el puño quedan pegadas a los nudillos)
        if toca["indice"] and toca["medio"] and _d(p[8], p[5]) > t * 0.4:
            return "O"
        if pu and _d(p[4], p[6]) < t * 0.7:
            return "A"
        return "S" if not pu else None
    if i and not (m or a or n):
        if pu:
            return "L"
        return "D" if toca["medio"] or toca["anular"] else None
    if n and not (i or m or a):
        return "Y" if pu else "I"
    if i and m and not (a or n):
        return "V" if _d(p[8], p[12]) > t * 0.42 else "U"
    if i and m and a and not n:
        return "W"
    return None


class Estabilizador:
    """Solo acepta un gesto si se mantiene un rato, y no lo repite enseguida."""

    def __init__(self, sostener=0.8, espera=2.0):
        self.sostener, self.espera = sostener, espera
        self._actual, self._desde, self._ultimo = None, 0.0, {}

    def ver(self, gesto, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        if gesto != self._actual:
            self._actual, self._desde = gesto, ahora
            return None
        if gesto is None or ahora - self._desde < self.sostener:
            return None
        if ahora - self._ultimo.get(gesto, -1e9) < self.espera:
            return None
        self._ultimo[gesto] = ahora
        self._desde = ahora + 10  # exige soltar el gesto antes de repetirlo
        return gesto


def ruta_modelo():
    return config.RAIZ / "modelos" / "hand_landmarker.task"


class Camara:
    """Una sola cámara compartida: gestos de la mano, verificar tu cara y la vigilancia.

    Cada uso se enciende y apaga por separado; la cámara se apaga sola cuando ningún uso la necesita.
    """

    def __init__(self, al_gesto, al_estado=None):
        self.al_gesto = al_gesto
        self.al_estado = al_estado or (lambda activo, error="": None)
        self._usos = set()
        self._suscritos = {}  # nombre -> [función(cuadro_bgr), cada_seg, última_vez]
        self._parar = threading.Event()
        self._hilo = None
        self.ultimo_cuadro = None  # último cuadro BGR (sin espejo), para fotos y verificar caras
        self.modo = "gestos"       # "gestos" o "letras" (deletrear)

    @property
    def activa(self):
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def gestos_activos(self):
        return self.activa and "gestos" in self._usos

    def iniciar(self, uso="gestos"):
        self._usos.add(uso)
        self._parar.clear()
        if uso == "gestos" and self.activa:
            self.al_estado(True)
        if self.activa:
            return
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="camara")
        self._hilo.start()

    def detener(self, uso="gestos"):
        self._usos.discard(uso)
        if uso == "gestos":
            self.al_estado(False)
        if not self._usos:
            self._parar.set()

    def suscribir(self, nombre, funcion, cada=1.0):
        self._suscritos[nombre] = [funcion, cada, 0.0]
        self.iniciar(nombre)

    def desuscribir(self, nombre):
        self._suscritos.pop(nombre, None)
        self.detener(nombre)

    def foto(self, espera=4.0):
        """Devuelve un cuadro BGR actual (enciende la cámara un momento si hace falta)."""
        propia = not self.activa
        if propia:
            self.ultimo_cuadro = None
            self.iniciar("foto")
        fin = time.monotonic() + espera
        try:
            # deja pasar unos cuadros para que la cámara ajuste la luz
            time.sleep(0.8 if propia else 0)
            while time.monotonic() < fin:
                if self.ultimo_cuadro is not None:
                    return self.ultimo_cuadro.copy()
                if not self.activa:
                    return None
                time.sleep(0.05)
            return None
        finally:
            if propia:
                self.detener("foto")

    def _detector_manos(self):
        try:
            import mediapipe  # noqa: F401
            from mediapipe.tasks.python import BaseOptions, vision
        except ImportError as e:
            return None, f"Falta instalar {e.name}. Vuelve a ejecutar instalar.bat."
        if not ruta_modelo().exists():
            return None, "Falta el modelo de manos. Vuelve a ejecutar instalar.bat."
        opciones = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ruta_modelo())),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=0.6, min_tracking_confidence=0.5)
        return vision.HandLandmarker.create_from_options(opciones), ""

    def _bucle(self):
        try:
            import cv2
        except ImportError as e:
            self._usos.clear()
            self.al_estado(False, f"Falta instalar {e.name}. Vuelve a ejecutar instalar.bat.")
            return
        camara = cv2.VideoCapture(0, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(0)
        if not camara.isOpened():
            self._usos.clear()
            self.al_estado(False, "No pude abrir la cámara. ¿La está usando otra aplicación?")
            return
        camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        estable, detector, inicio = Estabilizador(), None, time.monotonic()
        letras, ultima_mano, hubo_letra = Estabilizador(sostener=0.7, espera=0.0), time.monotonic(), False
        if "gestos" in self._usos:
            self.al_estado(True)
        try:
            while not self._parar.is_set():
                ok, cuadro = camara.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                self.ultimo_cuadro = cuadro
                ahora = time.monotonic()
                for nombre, s in list(self._suscritos.items()):
                    if ahora - s[2] >= s[1]:
                        s[2] = ahora
                        try:
                            s[0](cuadro)
                        except Exception as e:
                            print(f"[camara] {nombre}: {e}")
                if "gestos" in self._usos:
                    if detector is None:
                        detector, error = self._detector_manos()
                        if detector is None:
                            self._usos.discard("gestos")
                            self.al_estado(False, error)
                            if not self._usos:
                                break
                            continue
                    import mediapipe as mp
                    rgb = cv2.cvtColor(cv2.flip(cuadro, 1), cv2.COLOR_BGR2RGB)
                    imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    r = detector.detect_for_video(imagen, int((ahora - inicio) * 1000))
                    mano = r.hand_landmarks[0] if r.hand_landmarks else None
                    if self.modo == "letras":
                        if mano:
                            ultima_mano = ahora
                        elif hubo_letra and ahora - ultima_mano > 3.0:
                            hubo_letra = False
                            self.al_gesto("fin_deletreo")
                        final = letras.ver(letra(mano) if mano else None)
                        if final:
                            hubo_letra = True
                            self.al_gesto("letra_" + final)
                        time.sleep(1 / 20)
                        continue
                    gesto = clasificar(mano) if mano else None
                    final = estable.ver(gesto)
                    if final:
                        try:
                            self.al_gesto(final)
                        except Exception as e:
                            print(f"[gestos] {e}")
                time.sleep(1 / 20)
        finally:
            camara.release()
            if detector is not None:
                detector.close()
            self.ultimo_cuadro = None
            self.al_estado(False)
