from types import SimpleNamespace as NS

from jarvis import archivos, ia, seguridad


class FakeStream:
    def __init__(self, textos, final):
        self.textos, self.final = textos, final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(NS(type="text", text=t) for t in self.textos)

    def get_final_message(self):
        return self.final


class FakeCliente:
    def __init__(self, rondas):
        self.rondas, self.llamadas = list(rondas), []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **kw):
        self.llamadas.append(kw)
        return self.rondas.pop(0)


def _conv(monkeypatch, tmp_path, rondas):
    monkeypatch.setattr(seguridad.config, "CARPETA_DATOS", tmp_path / "_datos")
    c = ia.Conversador(ia.Cerebro())
    cli = FakeCliente(rondas)
    monkeypatch.setattr(c, "_cliente_api", lambda: cli)
    return c, cli


def test_conversacion_con_emocion_y_frases(monkeypatch, tmp_path):
    final = NS(content=[NS(type="text", text="...")], stop_reason="end_turn")
    c, cli = _conv(monkeypatch, tmp_path, [FakeStream(["[rie", "ndo] ¡Muy bien, Juan! ", "Aquí andamos. ¿Y", " tú qué tal?"], final)])
    frases, caras = [], []
    total = c.responder("cómo estás", lambda t: None, frases.append, caras.append, lambda r: None)
    assert caras == ["riendo"]
    assert frases == ["¡Muy bien, Juan!", "Aquí andamos.", "¿Y tú qué tal?"]
    assert "[" not in total
    kw = cli.llamadas[0]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
    assert len(c.historial) == 2


def test_herramienta_buscar(monkeypatch, tmp_path):
    (tmp_path / "fotos galeria playa.jpg").write_text("x")
    monkeypatch.setattr(archivos.config, "CARPETAS_BUSQUEDA", [tmp_path])
    uso = NS(type="tool_use", id="t1", name="buscar_archivos", input={"consulta": "galeria"})
    r1 = FakeStream(["[pensando] Déjame buscar."], NS(content=[uso], stop_reason="tool_use"))
    r2 = FakeStream(["[riendo] Encontré una foto de la playa."], NS(content=[NS(type="text", text="")], stop_reason="end_turn"))
    c, cli = _conv(monkeypatch, tmp_path, [r1, r2])
    vistos = []
    c.responder("búscame las fotos de la galería", lambda t: None, lambda f: None, lambda e: None, vistos.append)
    assert vistos and vistos[0][0].endswith("fotos galeria playa.jpg")
    resultado = c.historial[2]["content"][0]
    assert resultado["type"] == "tool_result" and resultado["tool_use_id"] == "t1"
    assert len(cli.llamadas) == 2


def test_eliminar_por_claude_queda_pendiente(monkeypatch, tmp_path):
    f = tmp_path / "viejo.txt"
    f.write_text("x")
    monkeypatch.setattr(archivos.config, "CARPETAS_BUSQUEDA", [tmp_path])
    borrados = []
    monkeypatch.setattr(archivos, "enviar_a_papelera", borrados.append)
    uso = NS(type="tool_use", id="t1", name="eliminar", input={"objetivo": "viejo"})
    r1 = FakeStream([], NS(content=[uso], stop_reason="tool_use"))
    r2 = FakeStream(["[preocupado] ¿Seguro que lo borro?"], NS(content=[], stop_reason="end_turn"))
    c, _ = _conv(monkeypatch, tmp_path, [r1, r2])
    c.responder("borra el archivo viejo", lambda t: None, lambda f: None, lambda e: None, lambda r: None)
    assert not borrados and c.cerebro.pendiente_borrar == str(f)
    c.cerebro.procesar("sí")
    assert borrados == [str(f)]


def test_error_reinicia_historial(monkeypatch, tmp_path):
    c, cli = _conv(monkeypatch, tmp_path, [])
    try:
        c.responder("hola", lambda t: None, lambda f: None, lambda e: None, lambda r: None)
    except IndexError:
        pass
    assert c.historial == []


def test_herramientas_de_agenda_y_memoria(monkeypatch, tmp_path):
    import datetime as dt
    futuro = (dt.datetime.now() + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    usos = [NS(type="tool_use", id="a", name="crear_recordatorio", input={"fecha_hora": futuro, "mensaje": "llamar a Ana"}),
            NS(type="tool_use", id="b", name="recordar_dato", input={"dato": "Su hermana se llama Ana"})]
    r1 = FakeStream([], NS(content=usos, stop_reason="tool_use"))
    r2 = FakeStream(["[guino] Listo."], NS(content=[], stop_reason="end_turn"))
    c, cli = _conv(monkeypatch, tmp_path, [r1, r2])
    c.responder("recuérdame en una hora llamar a mi hermana Ana", lambda t: None, lambda f: None, lambda e: None, lambda r: None)
    assert c.cerebro.agenda.pendientes()[0]["mensaje"] == "llamar a Ana"
    assert c.cerebro.memoria.datos[0]["texto"] == "Su hermana se llama Ana"
    assert len(c.historial[2]["content"]) == 2          # ambos resultados en un solo mensaje


def test_memoria_entra_en_el_contexto(monkeypatch, tmp_path):
    final = NS(content=[NS(type="text", text="ok")], stop_reason="end_turn")
    c, cli = _conv(monkeypatch, tmp_path, [FakeStream(["[normal] Hola."], final)])
    c.cerebro.memoria.recordar("Le gusta el fútbol")
    c.responder("hola", lambda t: None, lambda f: None, lambda e: None, lambda r: None)
    sistema = cli.llamadas[0]["system"]
    assert len(sistema) == 2 and "fútbol" in sistema[1]["text"]


def test_resumen_al_terminar(monkeypatch, tmp_path):
    final = NS(content=[NS(type="text", text="[riendo] Bien.")], stop_reason="end_turn")
    c, cli = _conv(monkeypatch, tmp_path, [FakeStream(["[riendo] Bien."], final), FakeStream(["[normal] Claro."], final)])
    for t in ("hola", "cómo estás"):
        c.responder(t, lambda t: None, lambda f: None, lambda e: None, lambda r: None)
    cli.beta.messages.create = lambda **kw: NS(stop_reason="end_turn", content=[NS(type="text", text="Charlaron un rato.")])
    c._resumir(c.historial)
    assert c.cerebro.memoria.resumenes[-1]["resumen"] == "Charlaron un rato."
