from types import SimpleNamespace as P

import pytest

from jarvis import comandos, control, documentos, gestos


# ---------- control del PC ----------
@pytest.fixture
def pc(monkeypatch):
    llamadas = []
    monkeypatch.setattr(control, "volumen", lambda **kw: llamadas.append(("volumen", kw)) or "ok volumen")
    monkeypatch.setattr(control, "brillo", lambda **kw: llamadas.append(("brillo", kw)) or "ok brillo")
    monkeypatch.setattr(control, "wifi", lambda on: llamadas.append(("wifi", on)) or "ok wifi")
    monkeypatch.setattr(control, "apagar", lambda reiniciar=False: llamadas.append(("apagar", reiniciar)) or "apagando")
    monkeypatch.setattr(control, "cancelar_apagado", lambda: llamadas.append(("cancelar",)) or "cancelado")
    monkeypatch.setattr(control, "buscar_procesos", lambda n: ["chrome.exe"] if "chrome" in n else [])
    monkeypatch.setattr(control, "cerrar", lambda p, forzar=False: llamadas.append(("cerrar", p, forzar)) or True)
    monkeypatch.setattr(control, "colgados", lambda: ["Juego.exe"])
    monkeypatch.setattr(control, "cerrar_colgados", lambda l: llamadas.append(("colgados", l)) or 1)
    return llamadas


def test_volumen_y_brillo(pc):
    c = comandos.Cerebro()
    c.procesar("sube el volumen")
    c.procesar("baja el volumen 20")
    c.procesar("pon el volumen al cincuenta")
    c.procesar("silencia")
    c.procesar("sube el brillo")
    c.procesar("brillo al 30")
    assert pc == [("volumen", {"cambio": 10, "nivel": None}), ("volumen", {"cambio": -20, "nivel": None}),
                  ("volumen", {"nivel": 50}), ("volumen", {"silenciar": True}),
                  ("brillo", {"cambio": 20, "nivel": None}), ("brillo", {"nivel": 30})]


def test_wifi(pc):
    c = comandos.Cerebro()
    c.procesar("apaga el wifi")
    c.procesar("conecta el wifi")
    assert pc == [("wifi", False), ("wifi", True)]


def test_apagar_pide_confirmacion(pc):
    c = comandos.Cerebro()
    r = c.procesar("apaga el computador")
    assert "Seguro" in r.texto and pc == []
    c.procesar("no")
    assert pc == []
    c.procesar("reinicia el pc")
    c.procesar("sí")
    assert pc == [("apagar", True)]
    c.procesar("cancela el apagado")
    assert pc[-1] == ("cancelar",)


def test_cerrar_programas(pc):
    c = comandos.Cerebro()
    assert "Cerrando" in c.procesar("cierra chrome").texto
    assert pc[-1] == ("cerrar", "chrome.exe", False)
    assert "No veo" in c.procesar("cierra photoshop").texto
    c.procesar("fuerza el cierre de chrome")
    assert pc[-1] == ("cerrar", "chrome.exe", False)           # aún no: falta el sí
    c.procesar("sí")
    assert pc[-1] == ("cerrar", "chrome.exe", True)
    assert "Juego" in c.procesar("cierra las aplicaciones que no responden").texto
    c.procesar("sí")
    assert pc[-1] == ("colgados", ["Juego.exe"])


# ---------- documentos ----------
def test_resumir_documento_word_sin_internet(tmp_path, monkeypatch):
    import docx
    d = docx.Document()
    texto = ("Los paneles solares convierten la energía del sol en electricidad para las casas. "
             "La energía solar es renovable y reduce la factura de electricidad de las familias. "
             "El clima estuvo nublado algunos días de la semana pasada en la ciudad. "
             "Instalar paneles solares requiere una inversión inicial que se recupera con el ahorro de energía. ")
    for parrafo in texto.split(". "):
        d.add_paragraph(parrafo + ".")
    ruta = tmp_path / "Informe Energia Solar.docx"
    d.save(ruta)
    monkeypatch.setattr(comandos.archivos.config, "CARPETAS_BUSQUEDA", [tmp_path])
    c = comandos.Cerebro()
    r = c.procesar("resume el documento informe energía solar")
    assert "Informe Energia Solar.docx" in r.texto and "solar" in r.texto.lower()
    assert c.documento == str(ruta)
    # con Claude disponible se lo deja a Claude (herramienta leer_documento)
    assert not c.procesar("resume el documento informe", solo_ordenes=True).entendida


def test_para_claude_avisa_si_recorta(tmp_path, monkeypatch):
    ruta = tmp_path / "largo.txt"
    ruta.write_text("hola mundo. " * 10)
    assert "hola mundo" in documentos.para_claude(str(ruta))
    monkeypatch.setattr(documentos, "MAX_CARACTERES_CLAUDE", 20)
    assert "AVISO" in documentos.para_claude(str(ruta))


def test_resumen_local_elige_frases_importantes():
    texto = ("Python es un lenguaje de programación muy popular entre estudiantes. "
             "Python permite crear programas de inteligencia artificial y páginas web. "
             "Ayer llovió bastante en Medellín durante toda la tarde completa. "
             "Muchos cursos de programación enseñan Python como primer lenguaje.")
    r = documentos.resumen_local(texto, n=2)
    assert "llovió" not in r and "Python" in r


# ---------- gestos ----------
def mano(extendidos, pulgar="fuera"):
    """Mano vertical sintética (21 puntos). y crece hacia abajo como en la imagen."""
    p = [P(x=0.5, y=0.8)] + [None] * 20
    xs = {"indice": 0.42, "medio": 0.48, "anular": 0.54, "menique": 0.6}
    ids = {"indice": (5, 6, 7, 8), "medio": (9, 10, 11, 12), "anular": (13, 14, 15, 16), "menique": (17, 18, 19, 20)}
    for dedo, (mcp, pip, dip, tip) in ids.items():
        x = xs[dedo]
        p[mcp] = P(x=x, y=0.6)
        if dedo in extendidos:
            p[pip], p[dip], p[tip] = P(x=x, y=0.5), P(x=x, y=0.43), P(x=x, y=0.36)
        else:
            p[pip], p[dip], p[tip] = P(x=x, y=0.53), P(x=x, y=0.6), P(x=x, y=0.64)
    p[1], p[2], p[3] = P(x=0.44, y=0.75), P(x=0.38, y=0.7), P(x=0.34, y=0.65)
    p[4] = {"fuera": P(x=0.28, y=0.6), "dentro": P(x=0.45, y=0.66),
            "arriba": P(x=0.36, y=0.45), "abajo": P(x=0.36, y=0.95)}[pulgar]
    if pulgar in ("arriba", "abajo"):
        p[3] = P(x=0.37, y=0.6 if pulgar == "arriba" else 0.82)
    return p


def test_clasificar_gestos():
    todos = {"indice", "medio", "anular", "menique"}
    assert gestos.clasificar(mano(todos)) == "palma"
    assert gestos.clasificar(mano(set(), "dentro")) == "puno"
    assert gestos.clasificar(mano(set(), "arriba")) == "pulgar_arriba"
    assert gestos.clasificar(mano(set(), "abajo")) == "pulgar_abajo"
    assert gestos.clasificar(mano({"indice"}, "dentro")) == "indice"
    assert gestos.clasificar(mano({"indice", "medio"}, "dentro")) == "dos"
    assert gestos.clasificar(mano({"indice", "menique"})) == "te_quiero"
    assert gestos.clasificar(None) is None


def test_estabilizador():
    e = gestos.Estabilizador(sostener=0.8, espera=2.0)
    assert e.ver("palma", 0.0) is None
    assert e.ver("palma", 0.5) is None
    assert e.ver("palma", 0.9) == "palma"          # sostenido casi un segundo
    assert e.ver("palma", 1.5) is None              # no se repite mientras lo sostienes
    assert e.ver(None, 1.6) is None
    assert e.ver("palma", 1.7) is None
    assert e.ver("palma", 2.6) is None              # aún en la espera de 2 s
    assert e.ver("palma", 3.2) == "palma"


def test_olvidar_todo_pide_confirmacion():
    c = comandos.Cerebro()
    c.procesar("recuerda que me gusta el café")
    c.procesar("olvida todo lo que sabes de mí")
    assert c.memoria.datos
    c.procesar("sí")
    assert c.memoria.datos == []
