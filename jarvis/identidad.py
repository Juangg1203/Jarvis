"""Reconocer al dueño por la voz y por la cara, sin internet.

- Voz: el modelo de hablantes de Vosk da una "huella" (vector de 128 números) de cada frase.
- Cara: OpenCV detecta la cara (YuNet) y saca su huella (SFace).
Las huellas se guardan solo en tu portátil (%LOCALAPPDATA%\\Jarvis\\identidad.json). Nunca se guardan
grabaciones ni fotos tuyas.
"""
import json
import math

from . import config


def _ARCHIVO():
    return config.CARPETA_DATOS / "identidad.json"


def ruta_modelo_voz():
    return config.RAIZ / "modelos" / "vosk-model-spk-0.4"


def ruta_detector_caras():
    return config.RAIZ / "modelos" / "face_detection_yunet_2023mar.onnx"


def ruta_reconocedor_caras():
    return config.RAIZ / "modelos" / "face_recognition_sface_2021dec.onnx"


def coseno(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def promedio(vectores):
    n = len(vectores)
    return [sum(v[i] for v in vectores) / n for i in range(len(vectores[0]))]


class Identidad:
    MIN_CUADROS_VOZ = 40  # frases muy cortas no dan una huella fiable

    def __init__(self):
        self.voz: list[list[float]] = []
        self.cara: list[list[float]] = []
        try:
            datos = json.loads(_ARCHIVO().read_text(encoding="utf-8"))
            self.voz, self.cara = datos.get("voz", []), datos.get("cara", [])
        except (OSError, ValueError):
            pass

    def _guardar(self):
        config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
        _ARCHIVO().write_text(json.dumps({"voz": self.voz, "cara": self.cara}), encoding="utf-8")

    @property
    def conoce_voz(self):
        return bool(self.voz)

    @property
    def conoce_cara(self):
        return bool(self.cara)

    def guardar_voz(self, huellas):
        self.voz = [list(map(float, h)) for h in huellas]
        self._guardar()

    def guardar_cara(self, huellas):
        self.cara = [list(map(float, h)) for h in huellas]
        self._guardar()

    def olvidar(self, que="todo"):
        if que in ("voz", "todo"):
            self.voz = []
        if que in ("cara", "todo"):
            self.cara = []
        self._guardar()

    def parecido_voz(self, huella) -> float:
        if not self.voz or not huella:
            return 0.0
        return max(coseno(huella, promedio(self.voz)), max(coseno(huella, v) for v in self.voz))

    def es_mi_voz(self, huella, cuadros=999) -> bool:
        return cuadros >= self.MIN_CUADROS_VOZ and self.parecido_voz(huella) >= config.UMBRAL_VOZ

    def parecido_cara(self, huella) -> float:
        if not self.cara or huella is None:
            return 0.0
        return max(coseno(huella, c) for c in self.cara)

    def es_mi_cara(self, huella) -> bool:
        return self.parecido_cara(huella) >= config.UMBRAL_CARA


class Caras:
    """Detecta caras en un cuadro de la cámara y saca su huella. Si faltan los modelos de reconocimiento,
    al menos detecta caras con el detector clásico de OpenCV (sin saber de quién son)."""

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.detector = self.reconocedor = self.clasico = None
        if ruta_detector_caras().exists() and ruta_reconocedor_caras().exists():
            self.detector = cv2.FaceDetectorYN.create(str(ruta_detector_caras()), "", (320, 240), 0.8)
            self.reconocedor = cv2.FaceRecognizerSF.create(str(ruta_reconocedor_caras()), "")
        else:
            self.clasico = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    @property
    def reconoce(self):
        return self.reconocedor is not None

    def huellas(self, cuadro):
        """Lista de (caja, huella o None), la cara más grande primero."""
        if self.detector is not None:
            alto, ancho = cuadro.shape[:2]
            self.detector.setInputSize((ancho, alto))
            _, caras = self.detector.detect(cuadro)
            if caras is None:
                return []
            salida = []
            for c in sorted(caras, key=lambda c: -c[2] * c[3]):
                alineada = self.reconocedor.alignCrop(cuadro, c)
                huella = self.reconocedor.feature(alineada).flatten().tolist()
                salida.append((tuple(int(x) for x in c[:4]), huella))
            return salida
        gris = self.cv2.cvtColor(cuadro, self.cv2.COLOR_BGR2GRAY)
        cajas = self.clasico.detectMultiScale(gris, 1.2, 6, minSize=(70, 70))
        return [(tuple(int(x) for x in c), None) for c in sorted(cajas, key=lambda c: -c[2] * c[3])]
