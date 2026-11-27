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


if __name__ == "__main__":
    descargar_oido()
    descargar_voz()
