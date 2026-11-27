"""Descarga el modelo de voz en español (unos 40 MB). Solo se necesita internet esta vez."""
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis import config  # noqa: E402

URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"


def progreso(bloques, tam, total):
    if total > 0:
        print(f"\r  Descargando modelo de voz... {min(100, bloques * tam * 100 // total)}%", end="", flush=True)


def main():
    destino = config.CARPETA_MODELO
    if destino.exists():
        print("El modelo de voz ya está instalado.")
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    zip_path = destino.parent / "modelo.zip"
    urllib.request.urlretrieve(URL, zip_path, progreso)
    print("\n  Descomprimiendo...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino.parent)
    zip_path.unlink()
    print("Modelo de voz listo.")


if __name__ == "__main__":
    main()
