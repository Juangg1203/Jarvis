import os

import pytest

from jarvis import archivos, comandos, seguridad
from jarvis.texto import extraer_numero, normalizar


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    (tmp_path / "Tarea de Matemáticas.pdf").write_text("x")
    (tmp_path / "tarea_fisica.docx").write_text("x")
    (tmp_path / "foto playa.jpg").write_text("x")
    monkeypatch.setattr(archivos.config, "CARPETAS_BUSQUEDA", [tmp_path])
    monkeypatch.setattr(seguridad.config, "CARPETA_DATOS", tmp_path / "_datos")
    abiertos = []
    monkeypatch.setattr(archivos, "abrir", abiertos.append)
    monkeypatch.setattr(archivos, "buscar_app", lambda n: ("Calculadora", "calc") if "calculadora" in normalizar(n) else None)
    return tmp_path, abiertos


def test_normalizar_y_numeros():
    assert normalizar("¿Qué HORA es?") == "que hora es"
    assert extraer_numero("el número dos") == 2
    assert extraer_numero("el 3") == 3
    assert extraer_numero("el primero") == 1
    assert extraer_numero("tarea") is None


def test_buscar_y_abrir_por_numero(carpeta):
    _, abiertos = carpeta
    c = comandos.Cerebro()
    r = c.procesar("Jarvis, busca el archivo tarea")
    assert len(r.resultados) == 2
    r = c.procesar("abre el número dos")
    assert abiertos and abiertos[0] in c.ultimos_resultados


def test_abrir_app(carpeta):
    _, abiertos = carpeta
    r = comandos.Cerebro().procesar("abre la calculadora")
    assert abiertos == ["calc"] and "Calculadora" in r.texto


def test_abrir_archivo_unico_directo(carpeta):
    _, abiertos = carpeta
    comandos.Cerebro().procesar("abre la foto playa")
    assert abiertos and abiertos[0].endswith("foto playa.jpg")


def test_borrar_pide_confirmacion(carpeta, monkeypatch):
    tmp, _ = carpeta
    borrados = []
    monkeypatch.setattr(archivos, "enviar_a_papelera", borrados.append)
    c = comandos.Cerebro()
    r = c.procesar("elimina la foto playa")
    assert r.expresion == "preocupado" and not borrados
    r = c.procesar("no")
    assert not borrados and "Cancelado" in r.texto
    c.procesar("borra foto playa")
    c.procesar("sí")
    assert borrados == [str(tmp / "foto playa.jpg")]


def test_respuesta_confusa_no_borra(carpeta, monkeypatch):
    borrados = []
    monkeypatch.setattr(archivos, "enviar_a_papelera", borrados.append)
    c = comandos.Cerebro()
    c.procesar("elimina foto playa")
    c.procesar("pues no sé")
    assert not borrados


def test_rutas_protegidas(tmp_path):
    ok, _ = seguridad.puede_eliminar(seguridad.config.RAIZ / "jarvis" / "main.py")
    assert not ok
    ok, _ = seguridad.puede_eliminar(os.path.abspath(os.sep))
    assert not ok
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert seguridad.puede_eliminar(f)[0]


def test_orden_desconocida():
    assert comandos.Cerebro().procesar("haz una pirueta").expresion == "pensando"


def test_palabra_activacion():
    from jarvis.voz import Oyente
    o = Oyente(lambda e: None, lambda t: None, lambda: False)
    assert o._quitar_activacion("jarvis abre la calculadora") == "abre la calculadora"
    assert o._quitar_activacion("oye jarvis") == ""
    assert o._quitar_activacion("abre la calculadora") is None
