"""Pruebas de la v5: internet, identidad, app del celular y seguridad."""
import json
import time
import urllib.error
import urllib.request

import pytest

from jarvis import celular, config, identidad, internet, vigilancia
from jarvis.comandos import Cerebro


# ---------- internet ----------
def test_describir_clima_hoy_y_manana():
    datos = {"current": {"temperature_2m": 18.4, "apparent_temperature": 15.9, "weather_code": 61},
             "daily": {"time": ["a", "b"], "weather_code": [61, 0], "temperature_2m_max": [21.2, 24],
                       "temperature_2m_min": [12, 11.6], "precipitation_probability_max": [70, 5]}}
    hoy = internet.describir_clima("Bogotá", datos)
    assert "18 grados" in hoy and "lluvia ligera" in hoy and "sensación de 16" in hoy and "70 por ciento" in hoy
    manana = internet.describir_clima("Bogotá", datos, manana=True)
    assert manana.startswith("Mañana en Bogotá estará despejado") and "sin lluvia" in manana


def test_leer_rss_quita_el_periodico():
    xml = b"""<rss><channel><item><title>Sube el dolar - El Tiempo</title></item>
              <item><title>Gana el equipo - Diario</title></item></channel></rss>"""
    assert internet.leer_rss(xml) == ["Sube el dolar", "Gana el equipo"]


def test_cerebro_internet_sin_claude(monkeypatch):
    llamadas = {}
    monkeypatch.setattr(internet, "clima", lambda lugar, manana=False: llamadas.setdefault("clima", (lugar, manana)) and "ok")
    monkeypatch.setattr(internet, "noticias", lambda tema="": f"noticias {tema}")
    monkeypatch.setattr(internet, "preguntar", lambda c: f"respuesta {c}")
    c = Cerebro()
    c.memoria.recordar("Vive en Medellín")
    assert c.procesar("¿qué clima hace en Cali mañana?").texto == "ok"
    assert llamadas["clima"] == ("cali", True)
    llamadas.clear()
    c.procesar("cómo está el clima")
    assert llamadas["clima"][0] == "Medellín"  # la ciudad sale de la memoria
    assert c.procesar("dame las noticias de fútbol").texto == "noticias futbol"
    assert c.procesar("busca en internet la capital de Australia").texto == "respuesta la capital de australia"
    assert c.procesar("quién es Shakira").texto.startswith("respuesta")
    assert c.procesar("qué hora es").texto.startswith("Son las")


def test_con_claude_las_busquedas_van_a_claude():
    r = Cerebro().procesar("qué clima hace en Bogotá", solo_ordenes=True)
    assert r.entendida is False


def test_claude_tiene_buscador_web():
    from jarvis import ia
    web = [h for h in ia.HERRAMIENTAS if h.get("type", "").startswith("web_search")]
    assert web and "eager_input_streaming" not in web[0]


# ---------- identidad ----------
def test_identidad_voz_y_cara():
    yo = identidad.Identidad()
    assert not yo.conoce_voz
    yo.guardar_voz([[1, 0, 0.1], [0.9, 0.1, 0]])
    yo.guardar_cara([[0, 1, 0]])
    otra = identidad.Identidad()  # se guardó en disco
    assert otra.conoce_voz and otra.conoce_cara
    assert otra.es_mi_voz([1, 0.05, 0.05], cuadros=100)
    assert not otra.es_mi_voz([1, 0.05, 0.05], cuadros=10)  # frase muy corta
    assert not otra.es_mi_voz([0, 0, 1], cuadros=100)
    assert otra.es_mi_cara([0.1, 1, 0]) and not otra.es_mi_cara([1, 0, 0])
    otra.olvidar("voz")
    assert not identidad.Identidad().conoce_voz and identidad.Identidad().conoce_cara


# ---------- app del celular ----------
@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setattr(config, "PUERTO_CELULAR", 18765)
    recibidos = []
    srv = celular.Servidor(lambda t: recibidos.append(t) or {"respuesta": "hecho: " + t, "expresion": "guino"},
                           lambda: {"estado": "esperando", "vigilando": False}, "codigo-secreto")
    assert srv.iniciar()
    yield srv, recibidos
    srv.detener()


def _pedir(ruta, codigo=None, cuerpo=None):
    req = urllib.request.Request("http://127.0.0.1:18765" + ruta, data=json.dumps(cuerpo).encode() if cuerpo else None,
                                 headers={"X-Jarvis-Codigo": codigo or "", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_celular_pide_codigo(servidor):
    srv, recibidos = servidor
    estado, pagina = _pedir("/")
    assert estado == 200 and b"J.A.R.V.I.S" in pagina
    assert _pedir("/api/hablar", "malo", {"texto": "apaga el pc"})[0] == 403
    assert recibidos == []
    estado, cuerpo = _pedir("/api/hablar", "codigo-secreto", {"texto": "hola"})
    assert estado == 200 and json.loads(cuerpo)["respuesta"] == "hecho: hola" and recibidos == ["hola"]
    srv.alerta("USB conectada")
    datos = json.loads(_pedir("/api/estado?desde=0", "codigo-secreto")[1])
    assert datos["alertas"][0]["texto"] == "USB conectada"
    assert _pedir("/caras/normal.png")[0] == 200
    assert _pedir("/caras/..%2Fapp.png")[0] == 404


def test_celular_bloquea_tras_muchos_errores(servidor):
    srv, _ = servidor
    for _ in range(10):
        _pedir("/api/estado", "malo")
    # bloqueado aunque ahora ponga el código bueno
    assert _pedir("/api/estado", "codigo-secreto")[0] == 403


def test_qr_del_celular():
    svg = celular.qr_svg("http://192.168.1.5:8765/#c=abc")
    assert svg == "" or "<svg" in svg


# ---------- USB, disco y vigilancia ----------
def test_monitor_avisa_usb_nueva_y_disco_lleno(monkeypatch):
    alertas = []
    m = vigilancia.Monitor(lambda tipo, texto, dato: alertas.append((tipo, dato)))
    unidades = {"C:\\": "C:"}
    monkeypatch.setattr(vigilancia, "unidades_removibles", lambda: dict(unidades))
    m.revisar_usb()  # la primera vez solo aprende lo que ya estaba
    unidades["E:\\"] = "E:"
    m.revisar_usb()
    assert alertas == [("usb", "E:\\")]
    monkeypatch.setattr(vigilancia, "discos_llenos", lambda umbral=None: [("C:", 95, 3.2)])
    m.revisar_discos()
    m.revisar_discos()  # una sola vez al día
    assert alertas[-1] == ("disco", "C:") and len(alertas) == 2
    assert vigilancia.nombre_unidad("E:\\") == "E"


class _CamaraFalsa:
    ultimo_cuadro = None

    def suscribir(self, *a, **k):
        pass

    def desuscribir(self, *a):
        pass


class _CarasFalsas:
    reconoce = True

    def __init__(self, huellas):
        self.lista = huellas

    def huellas(self, cuadro):
        return [((0, 0, 10, 10), h) for h in self.lista]


def test_vigilante_foto_al_extrano_y_se_apaga_con_el_dueno(monkeypatch, tmp_path):
    yo = identidad.Identidad()
    yo.guardar_cara([[0, 1, 0]])
    fotos, volvio = [], []
    v = vigilancia.Vigilante(_CamaraFalsa(), yo, al_intruso=fotos.append, al_volver=volvio.append)
    monkeypatch.setattr(identidad, "Caras", lambda: _CarasFalsas([[1, 0, 0]]))
    monkeypatch.setattr(v, "_vigilar_teclado", lambda: None)
    v.activar()
    v._desde = time.monotonic() - 1  # sin esperar los 20 segundos
    guardadas = []
    monkeypatch.setattr(v, "_foto", lambda cuadro: (guardadas.append(1), v.fotos.append("x.jpg")))
    v._mirar("cuadro")
    assert guardadas == [1]
    v._caras = _CarasFalsas([[0, 0.9, 0.1]])  # ahora aparece el dueño
    v._mirar("cuadro")
    assert not v.activa and volvio == [["x.jpg"]]
