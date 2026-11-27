"""Descarga el modelo de voz (oído) y la voz de Jarvis. Solo se necesita internet esta vez."""
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis import config  # noqa: E402

URL_VOSK = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
URL_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/{nombre}"


def progreso(etiqueta):
    def _p(bloques, tam, total):
        if total > 0:
            print(f"\r  {etiqueta}... {min(100, bloques * tam * 100 // total)}%", end="", flush=True)
    return _p


def descargar_oido():
    destino = config.CARPETA_MODELO
    if destino.exists():
        print("El reconocimiento de voz ya está instalado.")
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    zip_path = destino.parent / "modelo.zip"
    urllib.request.urlretrieve(URL_VOSK, zip_path, progreso("Descargando reconocimiento de voz"))
    print("\n  Descomprimiendo...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino.parent)
    zip_path.unlink()
    print("Reconocimiento de voz listo.")


def descargar_voz():
    config.CARPETA_VOCES.mkdir(parents=True, exist_ok=True)
    for ext in (".onnx.json", ".onnx"):
        nombre = config.VOZ_PIPER + ext
        destino = config.CARPETA_VOCES / nombre
        if destino.exists():
            continue
        tmp = destino.with_suffix(destino.suffix + ".part")
        urllib.request.urlretrieve(URL_PIPER.format(nombre=nombre) + "?download=true", tmp,
                                   progreso(f"Descargando la voz de Jarvis ({ext})"))
        tmp.rename(destino)
        print()
    print("Voz de Jarvis lista.")


URL_MANOS = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/"
             "float16/latest/hand_landmarker.task")


def descargar_manos():
    destino = config.RAIZ / "modelos" / "hand_landmarker.task"
    if destino.exists():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".part")
    try:
        urllib.request.urlretrieve(URL_MANOS, tmp, progreso("Descargando el modelo de manos para los gestos"))
        tmp.rename(destino)
        print("\nModelo de gestos listo.")
    except Exception as e:  # los gestos son opcionales
        print(f"\nAviso: no se pudo descargar el modelo de gestos ({e}).")


URL_VOCES = "https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip"
URL_CARAS = "https://github.com/opencv/opencv_zoo/raw/main/models/{carpeta}/{nombre}"
CARAS = [("face_detection_yunet", "face_detection_yunet_2023mar.onnx"),
         ("face_recognition_sface", "face_recognition_sface_2021dec.onnx")]


def descargar_reconocer_voz():
    """Modelo que distingue tu voz de la de otros (para «solo obedéceme a mí»). Opcional."""
    destino = config.RAIZ / "modelos" / "vosk-model-spk-0.4"
    if destino.exists():
        return
    zip_path = destino.parent / "spk.zip"
    try:
        urllib.request.urlretrieve(URL_VOCES, zip_path, progreso("Descargando el reconocedor de tu voz"))
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(destino.parent)
        print("\nReconocedor de voz listo.")
    except Exception as e:
        print(f"\nAviso: no se pudo descargar el reconocedor de voz ({e}).")
    finally:
        if zip_path.exists():
            zip_path.unlink()


def descargar_caras():
    """Modelos para reconocer tu cara (seguridad y vigilancia). Opcionales."""
    for carpeta, nombre in CARAS:
        destino = config.RAIZ / "modelos" / nombre
        if destino.exists():
            continue
        tmp = destino.with_suffix(".part")
        try:
            urllib.request.urlretrieve(URL_CARAS.format(carpeta=carpeta, nombre=nombre), tmp,
                                       progreso(f"Descargando el reconocimiento de caras ({nombre[:14]})"))
            if tmp.stat().st_size < 50_000:  # GitHub devolvió una página en vez del modelo
                raise OSError("archivo incompleto")
            tmp.rename(destino)
            print()
        except Exception as e:
            tmp.unlink(missing_ok=True)
            print(f"\nAviso: no se pudo descargar {nombre} ({e}).")


if __name__ == "__main__":
    descargar_oido()
    descargar_voz()
    descargar_manos()
    descargar_reconocer_voz()
    descargar_caras()
