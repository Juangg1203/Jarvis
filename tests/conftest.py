import pytest

from jarvis import config


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
    """Cada prueba usa su propia carpeta de datos (no toca la de Jarvis real)."""
    monkeypatch.setattr(config, "CARPETA_DATOS", tmp_path / "_jarvis_datos")
