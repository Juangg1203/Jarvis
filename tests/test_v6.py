"""Pruebas de la v6: ordenar carpetas, dictado, música, señas con letras, Ollama y notificaciones."""
import io
import json
import os
import time

from jarvis import gestos, notificaciones, ollama, organizar, redactar
from jarvis.comandos import Cerebro
from tests.test_v4 import P, mano


# ---------- ordenar carpetas ----------
def test_ordenar_por_tipo_y_deshacer(tmp_path):
    viejo = time.time() - 3600
    for nombre in ["foto.JPG", "tarea.pdf", "cancion.mp3", "setup.exe", "raro.xyz", "bajando.crdownload"]:
        f = tmp_path / nombre
        f.write_text("x")
        os.utime(f, (viejo, viejo))
    (tmp_path / "Imágenes").mkdir()
    (tmp_path / "Imágenes" / "foto.JPG").write_text("ya estaba")  # mismo nombre: no se pisa
    plan = organizar.planear(tmp_path)
    destinos = {a.name: d.name for a, d in plan}
    assert destinos == {"foto.JPG": "Imágenes", "tarea.pdf": "Documentos", "cancion.mp3": "Música",
                        "setup.exe": "Instaladores", "raro.xyz": "Otros"}  # la descarga a medias no se toca
    assert organizar.ejecutar(plan) == 5
    assert (tmp_path / "Imágenes" / "foto (1).JPG").exists() and (tmp_path / "bajando.crdownload").exists()
    assert organizar.deshacer() == 5
    assert (tmp_path / "foto.JPG").exists() and not (tmp_path / "Documentos").exists()
    assert (tmp_path / "Imágenes" / "foto.JPG").read_text() == "ya estaba"


def test_ordenar_pide_confirmacion(tmp_path, monkeypatch):
    viejo = time.time() - 3600
    f = tmp_path / "a.png"
    f.write_text("x")
    os.utime(f, (viejo, viejo))
    monkeypatch.setattr(organizar, "carpeta", lambda n: tmp_path)
    c = Cerebro()
    r = c.procesar("ordena mis descargas por fecha")
    assert "Voy a mover" in r.texto and c.pendiente_accion and f.exists()
    r = c.procesar("sí")
    assert "ordené 1" in r.texto and not f.exists()


def test_puntuar_dictado():
    assert redactar.puntuar("hola profe coma le escribo para pedir permiso punto y aparte gracias punto") == \
        "Hola profe, le escribo para pedir permiso.\nGracias."


def test_crear_documento(tmp_path, monkeypatch):
    monkeypatch.setattr(redactar, "carpeta_documentos", lambda: tmp_path)
    ruta = redactar.crear_documento("Carta: permiso", "Primer párrafo.\nSegundo.", abrir=False)
    from docx import Document
    textos = [p.text for p in Document(ruta).paragraphs]
    assert textos == ["Carta: permiso", "Primer párrafo.", "Segundo."] and ":" not in os.path.basename(ruta)


def test_correo_es_solo_borrador(monkeypatch):
    abiertos = []
    monkeypatch.setattr(redactar.webbrowser, "open", abiertos.append)
    url = redactar.borrador_correo("profe@colegio.edu", "Permiso", "Hola, ¿puedo salir?")
    assert url.startswith("mailto:profe@colegio.edu?subject=Permiso&body=Hola%2C") and abiertos == [url]


# ---------- música ----------
def test_ordenes_de_musica(monkeypatch):
    llamadas = []
    monkeypatch.setattr("jarvis.musica.reproducir", lambda c, d="youtube": llamadas.append((c, d)) or "ok")
    monkeypatch.setattr("jarvis.musica.tecla", lambda n: llamadas.append(n) or True)
    c = Cerebro()
    c.procesar("pon música para estudiar")
    c.procesar("pon Bad Bunny en spotify")
    c.procesar("siguiente canción")
    c.procesar("pausa")
    assert llamadas == [("música para estudiar lofi", "youtube"), ("bad bunny", "spotify"), "siguiente", "pausa"]
    assert "alarma" in c.procesar("pon una alarma a las 7").texto.lower() or c.agenda.pendientes()


# ---------- señas: letras ----------
def test_letras_del_alfabeto_manual():
    assert gestos.letra(mano({"indice", "medio", "anular", "menique"}, "dentro")) == "B"
    assert gestos.letra(mano({"indice", "medio", "anular", "menique"})) == "espacio"
    assert gestos.letra(mano({"menique"}, "dentro")) == "I"
    assert gestos.letra(mano({"menique"})) == "Y"
    assert gestos.letra(mano({"indice"})) == "L"
    assert gestos.letra(mano({"indice", "medio", "anular"}, "dentro")) == "W"
    assert gestos.letra(mano(set(), "dentro")) == "S"
    v = mano({"indice", "medio"}, "dentro")
    assert gestos.letra(v) == "U"
    v[8] = P(x=0.30, y=0.36)  # índice abierto hacia un lado
    assert gestos.letra(v) == "V"


# ---------- Ollama ----------
def test_ollama_conversa_con_herramienta(monkeypatch):
    from jarvis import ajustes
    conv = ollama.ConversadorOllama(Cerebro())
    trozos = [
        [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "recordar_dato", "arguments": {"dato": "Le gusta el rock"}}}]}, "done": True}],
        [{"message": {"content": "[guino] Anotado, "}}, {"message": {"content": "te gusta el rock. ¿Algo más?"}},
         {"done": True}],
    ]
    cuerpos = []

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def chat(cuerpo):
        cuerpos.append(cuerpo)
        return R("\n".join(json.dumps(t) for t in trozos.pop(0)).encode())

    monkeypatch.setattr(conv, "_chat", chat)
    frases = []
    total = conv.responder("me gusta el rock", lambda t: None, frases.append, lambda e: None, lambda r: None)
    assert "Le gusta el rock" in [d["texto"] for d in conv.cerebro.memoria.datos]
    assert "rock" in total and frases[0].startswith("Anotado")
    assert cuerpos[1]["messages"][-1]["role"] == "tool"
    nombres = {h["function"]["name"] for h in cuerpos[0]["tools"]}
    assert "buscar_internet" in nombres and "volumen" not in nombres  # menos herramientas para un modelo pequeño
    assert ajustes.cargar()["proveedor"] == "gemini"


def test_ollama_no_disponible_sin_servidor(monkeypatch):
    monkeypatch.setattr(ollama, "modelos_instalados", lambda: [])
    ollama.ConversadorOllama._cache = (0.0, False)
    assert not ollama.ConversadorOllama(Cerebro()).disponible()
    assert ollama.tiene("qwen2.5:3b", ["qwen2.5:3b"]) and ollama.tiene("llava", ["llava:latest"])


# ---------- notificaciones y pantalla ----------
def test_resumen_de_notificaciones():
    lista = [{"app": "WhatsApp", "titulo": "Mamá", "texto": "¿Vienes a almorzar?", "hora": 2},
             {"app": "Correo", "titulo": "Profe", "texto": "", "hora": 1}]
    texto = notificaciones.resumen(lista)
    assert texto.startswith("Tienes 2 notificaciones") and "WhatsApp, de Mamá: ¿Vienes a almorzar?" in texto
    assert "permiso" in notificaciones.resumen(None)


def test_ordenes_de_notificaciones_y_pantalla(monkeypatch):
    c = Cerebro()
    monkeypatch.setattr(c, "leer_notificaciones", lambda filtro=None: c.__class__.__mro__ and __import__(
        "jarvis.comandos", fromlist=["Respuesta"]).Respuesta(f"notif {filtro}"))
    monkeypatch.setattr(c, "mirar_pantalla", lambda p="": __import__(
        "jarvis.comandos", fromlist=["Respuesta"]).Respuesta("pantalla"))
    assert c.procesar("léeme mis mensajes de WhatsApp").texto == "notif mensajes"
    assert c.procesar("¿tengo correos nuevos?").texto == "notif correo"
    assert c.procesar("¿qué es este error?", solo_ordenes=True).texto == "pantalla"
    copiado = []
    monkeypatch.setattr(notificaciones, "copiar", copiado.append)
    monkeypatch.setattr(notificaciones, "abrir_whatsapp", lambda: None)
    r = c.procesar("respóndele a Mamá que sí voy a almorzar")
    assert copiado == ["sí voy a almorzar"] and "pega" in r.texto
