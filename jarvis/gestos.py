"""Lenguaje de señas básico con la cámara, 100 % local (MediaPipe). No se guarda ninguna imagen.

Gestos que entiende (mantenlos un segundo frente a la cámara):
  ✋ palma abierta   -> Jarvis te escucha
  ✊ puño            -> silencio (calla a Jarvis y silencia el sonido)
  👍 pulgar arriba   -> «sí» (confirma)
  👎 pulgar abajo    -> «no» (cancela)
  ☝️ índice arriba   -> sube el volumen
  ✌️ dos dedos (V)   -> baja el volumen
  🤟 «te quiero»     -> muestra u oculta la ventana de Jarvis
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
    """Mira la cámara en segundo plano y llama al_gesto(nombre) cuando reconoce uno."""

    def __init__(self, al_gesto, al_estado=None):
        self.al_gesto = al_gesto
        self.al_estado = al_estado or (lambda activo, error="": None)
        self._parar = threading.Event()
        self._hilo = None

    @property
    def activa(self):
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self):
        if self.activa:
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="gestos")
        self._hilo.start()

    def detener(self):
        self._parar.set()

    def _bucle(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision
        except ImportError as e:
            self.al_estado(False, f"Falta instalar {e.name}. Vuelve a ejecutar instalar.bat.")
            return
        if not ruta_modelo().exists():
            self.al_estado(False, "Falta el modelo de manos. Vuelve a ejecutar instalar.bat.")
            return
        opciones = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ruta_modelo())),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=0.6, min_tracking_confidence=0.5)
        camara = cv2.VideoCapture(0, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(0)
        if not camara.isOpened():
            self.al_estado(False, "No pude abrir la cámara. ¿La está usando otra aplicación?")
            return
        camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        estable = Estabilizador()
        self.al_estado(True)
        inicio = time.monotonic()
        try:
            with vision.HandLandmarker.create_from_options(opciones) as detector:
                while not self._parar.is_set():
                    ok, cuadro = camara.read()
                    if not ok:
                        time.sleep(0.05)
                        continue
                    rgb = cv2.cvtColor(cv2.flip(cuadro, 1), cv2.COLOR_BGR2RGB)
                    imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    r = detector.detect_for_video(imagen, int((time.monotonic() - inicio) * 1000))
                    gesto = clasificar(r.hand_landmarks[0]) if r.hand_landmarks else None
                    final = estable.ver(gesto)
                    if final:
                        try:
                            self.al_gesto(final)
                        except Exception as e:
                            print(f"[gestos] {e}")
                    time.sleep(1 / 20)
        finally:
            camara.release()
            self.al_estado(False)
