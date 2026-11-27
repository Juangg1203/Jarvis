import pytest

from jarvis import config


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
    """Cada prueba usa su propia carpeta de datos (no toca la de Jarvis real)."""
    monkeypatch.setattr(config, "CARPETA_DATOS", tmp_path / "_jarvis_datos")


@pytest.fixture(autouse=True)
def cerebro_gemini_en_pruebas_viejas(datos_temporales, request):
    """Las pruebas anteriores a v7.4 suponen Gemini como cerebro; el modo «solo local» tiene su propia prueba."""
    from jarvis import ajustes
    ajustes.guardar({"proveedor": "gemini"})
