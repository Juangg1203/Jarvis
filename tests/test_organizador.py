import datetime as dt

from jarvis import comandos, recordatorios, rutinas
from jarvis.memoria import Memoria

AHORA = dt.datetime(2026, 11, 27, 10, 0)


def cuando(frase):
    r = recordatorios.interpretar(frase, AHORA)
    return r and (r["cuando"].strftime("%d %H:%M"), r["mensaje"], r["tipo"])


def test_frases_de_tiempo():
    assert cuando("avísame en 20 minutos que saque la ropa") == ("27 10:20", "saque la ropa", "recordatorio")
    assert cuando("recuérdame en veinte minutos sacar la ropa")[0] == "27 10:20"
    assert cuando("pon un temporizador de cinco minutos") == ("27 10:05", "", "temporizador")
    assert cuando("Recuérdame mañana a las 8 llamar a mamá") == ("28 08:00", "llamar a mamá", "recordatorio")
    assert cuando("recuérdame a las 3 de la tarde la reunión")[0] == "27 15:00"
    assert cuando("recuérdame a las 3 la reunión")[0] == "27 15:00"      # la próxima vez que sean las 3
    assert cuando("avísame en una hora y media")[0] == "27 11:30"
    assert cuando("despiértame mañana a las siete y cuarto") == ("28 07:15", "", "alarma")
    assert cuando("pon una alarma a las 7")[0] == "28 07:00"             # alarma sin "de la tarde" = mañana temprano
    assert cuando("recuérdame a las ocho menos cuarto de la noche ver el partido")[0] == "27 19:45"
    assert cuando("recuérdame en treinta y cinco minutos apagar el horno")[0] == "27 10:35"
    assert cuando("pon una alarma para las 6 de la mañana") == ("28 06:00", "", "alarma")
    assert cuando("abre chrome") is None
    assert cuando("recuérdame comprar pan") is None


def test_agenda_suena_y_persiste():
    sonados = []
    a = recordatorios.Agenda(al_sonar=sonados.append)
    a.agregar(AHORA + dt.timedelta(minutes=5), "pan")
    a.agregar(AHORA + dt.timedelta(hours=2), "reunión")
    assert len(recordatorios.Agenda().pendientes()) == 2          # se guardó en disco
    a.revisar(AHORA + dt.timedelta(minutes=6))
    assert [x["mensaje"] for x in sonados] == ["pan"]
    assert len(recordatorios.Agenda().pendientes()) == 1
    assert "pan" in recordatorios.texto_aviso(sonados[0])


def test_ordenes_de_recordatorio_sin_internet():
    c = comandos.Cerebro()
    assert "Listo" in c.procesar("recuérdame en 10 minutos estudiar").texto
    c.procesar("pon una alarma a las 6 de la mañana")
    assert c.procesar("qué recordatorios tengo").texto.startswith("Tienes 2")
    assert "Dime cuál" in c.procesar("cancela el recordatorio").texto
    assert c.procesar("cancela el recordatorio dos").texto == "Cancelado."
    assert len(c.agenda.pendientes()) == 1
    # sin hora: si hay Claude, se lo deja a él
    assert not c.procesar("recuérdame comprar pan", solo_ordenes=True).entendida


def test_rutina_estudio(monkeypatch):
    abiertos, silencio = [], []
    monkeypatch.setattr(rutinas.archivos, "buscar_app", lambda n: (n, n))
    monkeypatch.setattr(rutinas.archivos, "abrir", abiertos.append)
    monkeypatch.setattr(rutinas, "silenciar_notificaciones", silencio.append)
    c = comandos.Cerebro()
    r = c.procesar("activa el modo estudio")
    assert abiertos == ["word", "chrome", "spotify"] and silencio == [True]
    assert "Modo estudio" in r.texto
    assert c.agenda.pendientes()[0]["tipo"] == "temporizador"
    c.procesar("termina el modo estudio")
    assert silencio == [True, False]


def test_crear_rutina_y_persistir():
    r = rutinas.Rutinas()
    nombre = r.crear("Modo Juego", abrir=["steam", "discord"], minutos=60, silenciar=True)
    assert nombre == "juego"
    assert "juego" in rutinas.Rutinas().nombres()
    assert comandos.Cerebro().rutinas.buscar("pon el modo juego") == "juego"


def test_memoria_local():
    c = comandos.Cerebro()
    assert "Anotado" in c.procesar("recuerda que mi equipo favorito es el Nacional").texto
    assert "Nacional" in c.procesar("qué sabes de mí").texto
    assert "Nacional" in Memoria().contexto()                     # sobrevive a un reinicio
    c.procesar("olvida que mi equipo favorito es el nacional")
    assert Memoria().datos == []


def test_buscar_conversaciones():
    m = Memoria()
    m.anotar("Juan", "mañana tengo examen de cálculo")
    m.anotar("Jarvis", "¡Mucha suerte en el examen!")
    assert any("cálculo" in x for x in m.buscar_conversaciones("examen calculo"))
