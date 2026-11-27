"""Conversación con Ollama: una IA que corre en tu propio portátil, gratis y sin internet.

Instálalo con instalar_ollama.bat (descarga Ollama y el modelo, unos 2 GB). Es más lento y menos listo
que Gemini, pero nada sale de tu computador.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from . import ajustes, config
from .gemini import BUSCAR_INTERNET, ConversadorGemini, ErrorGemini, Frases
from .ia import HERRAMIENTAS

BASE = "http://127.0.0.1:11434"
MANTENER = "60m"  # el modelo se queda en memoria una hora: así no tarda en "despertar" en cada pregunta

# En un portátil sin tarjeta gráfica, cada palabra del mensaje del sistema y de las herramientas cuesta tiempo
# antes de la primera respuesta. Por eso Ollama recibe un mensaje corto y pocas herramientas: las órdenes del PC
# (abrir, buscar, ordenar, volumen...) ya las entiende Jarvis por su cuenta antes de preguntarle a la IA.
HERRAMIENTAS_OLLAMA = {"abrir", "crear_recordatorio", "recordar_dato", "reproducir_musica", "redactar_documento"}

SISTEMA_OLLAMA = f"""Eres Jarvis, el asistente personal de {config.NOMBRE_USUARIO}, un mono holográfico azul que vive en su \
portátil. Hablas español latino, cálido y con algo de humor. Lo que escribes se lee en voz alta: responde en una a \
tres frases cortas, sin markdown, listas, emojis ni enlaces. Empieza siempre con una emoción entre corchetes: \
[normal] [riendo] [guino] [sorprendido] [pensando] [preocupado] [triste]. Ejemplo: "[riendo] ¡Claro!"
El texto viene de un reconocedor de voz y puede tener errores: entiende la intención más probable.
Usa las herramientas solo cuando haga falta (buscar_internet para clima, noticias o datos actuales; \
recordar_dato si te cuenta algo personal que valga la pena guardar). Para charlar, responde directo. \
Nunca envíes mensajes ni correos: solo los dejas listos."""


_LIGERO = {}


def modelo() -> str:
    """El modelo elegido en Ajustes. Sin elegir: en equipos de 8 GB, el rápido si está instalado."""
    elegido = ajustes.cargar().get("ollama_modelo")
    if elegido:
        return elegido
    if "usar" not in _LIGERO:
        from .equipo import poca_ram
        _LIGERO["usar"] = poca_ram() and tiene(config.MODELO_OLLAMA_RAPIDO, modelos_instalados())
    return config.MODELO_OLLAMA_RAPIDO if _LIGERO["usar"] else config.MODELO_OLLAMA


_MARCA_HORA = re.compile(r"^\s*\[\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}\]\s*")


def sin_hora(mensajes: list) -> list:
    """Quita la marca «[27/11/2026 14:40]» de tus mensajes: los modelos pequeños la copiaban en la respuesta."""
    return [dict(m, content=_MARCA_HORA.sub("", m["content"])) if m.get("role") == "user"
            and isinstance(m.get("content"), str) else m for m in mensajes]


class ErrorOllama(ErrorGemini):
    pass


def herramientas():
    salida = []
    for h in HERRAMIENTAS + [BUSCAR_INTERNET]:
        if h.get("name") not in HERRAMIENTAS_OLLAMA | {"buscar_internet"} or "input_schema" not in h:
            continue
        esquema = {k: v for k, v in h["input_schema"].items() if k != "additionalProperties"}
        salida.append({"type": "function", "function": {
            "name": h["name"], "description": h["description"].split(". ")[0], "parameters": esquema}})
    return salida


def opciones():
    # num_ctx pequeño = menos memoria y menos trabajo; num_predict corto porque las respuestas se dicen en voz alta
    return {"num_ctx": 4096, "num_predict": 300, "temperature": 0.7}


def _get(ruta, tiempo=3):
    with urllib.request.urlopen(BASE + ruta, timeout=tiempo) as r:
        return json.loads(r.read().decode("utf-8"))


def modelos_instalados() -> list:
    try:
        return [m["name"] for m in _get("/api/tags").get("models", [])]
    except Exception:
        return []


def tiene(modelo, instalados) -> bool:
    base = modelo if ":" in modelo else modelo + ":latest"
    return any(m == modelo or m == base for m in instalados)


class ConversadorOllama(ConversadorGemini):
    _cache = (0.0, False)

    def disponible(self) -> bool:
        cuando, ok = self._cache
        if time.monotonic() - cuando > 20:
            ok = tiene(modelo(), modelos_instalados())
            ConversadorOllama._cache = (time.monotonic(), ok)
        return ok

    def _chat(self, cuerpo):
        req = urllib.request.Request(BASE + "/api/chat", data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")
            if e.code == 404:
                raise ErrorOllama(f"Falta el modelo {modelo()}. Ejecuta instalar_ollama.bat.") from e
            print(f"[ollama] {e.code}: {detalle[:400]}")
            raise ErrorOllama("Ollama tuvo un problema al pensar la respuesta.") from e
        except urllib.error.URLError as e:
            ConversadorOllama._cache = (0.0, False)
            raise ErrorOllama("Ollama no está abierto. Ábrelo desde el menú Inicio o ejecuta instalar_ollama.bat.",
                              "preocupado") from e

    _por_resumir = None

    def olvidar(self, resumir=True):
        # El resumen se deja para cuando termine de responder: en un portátil sin tarjeta gráfica, resumir y
        # responder a la vez hace que las dos cosas vayan el doble de lentas.
        viejo = self.historial
        super().olvidar(resumir=False)
        if resumir and sum(1 for m in viejo if m["role"] == "user") >= 2:
            self._por_resumir = viejo

    def responder(self, *args, **kwargs):
        try:
            return super().responder(*args, **kwargs)
        finally:
            viejo, self._por_resumir = self._por_resumir, None
            if viejo:
                def despues():
                    self._resumir(viejo)
                    self.precalentar()
                threading.Thread(target=despues, daemon=True, name="ollama-resumen").start()

    def _sistema(self, contexto):
        return SISTEMA_OLLAMA + ("\n\n" + contexto if contexto else "")

    def precalentar(self):
        """Carga el modelo y deja leído el mensaje del sistema, para que la primera pregunta no espere.

        Ollama guarda en caché el principio de la conversación: si el sistema y las herramientas son iguales,
        la siguiente pregunta empieza a responder casi de inmediato."""
        def trabajo():
            try:
                if not self.disponible():
                    return
                cuerpo = {"model": modelo(), "stream": False, "tools": herramientas(), "keep_alive": MANTENER,
                          "messages": [{"role": "system", "content": self._sistema(
                              self._contexto if self.historial else self.cerebro.memoria.contexto())},
                                       {"role": "user", "content": "hola"}],
                          "options": dict(opciones(), num_predict=1)}
                with self._chat(cuerpo) as r:
                    r.read()
            except Exception as e:
                print(f"[ollama] No pude precalentar: {e}")
        threading.Thread(target=trabajo, daemon=True, name="ollama-precalentar").start()

    def escribir(self, instruccion: str) -> str:
        from .ia import Conversador
        cuerpo = {"model": modelo(), "stream": False, "keep_alive": MANTENER,
                  "options": {"num_ctx": 4096, "num_predict": 900, "temperature": 0.7},
                  "messages": [{"role": "system", "content": Conversador.ESCRITOR},
                               {"role": "user", "content": instruccion}]}
        with self._chat(cuerpo) as r:
            return json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "").strip()

    def _ronda(self, cliente, al_texto, al_frase, al_expresion, previo):
        sistema = self._sistema(self._contexto)
        cuerpo = {"model": modelo(), "stream": True, "tools": herramientas(),
                  "messages": [{"role": "system", "content": sistema}] + sin_hora(self.historial),
                  "options": opciones(), "keep_alive": MANTENER}
        frases = Frases(al_frase, al_texto, al_expresion, previo)
        texto, llamadas = "", []
        with self._chat(cuerpo) as r:
            for linea in r:
                if not linea.strip():
                    continue
                datos = json.loads(linea)
                if datos.get("error"):
                    raise ErrorOllama("Ollama tuvo un problema: " + str(datos["error"])[:120])
                m = datos.get("message") or {}
                if m.get("content"):
                    texto += m["content"]
                    frases.agregar(m["content"])
                llamadas += m.get("tool_calls") or []
        return texto, llamadas, frases.terminar()

    def _conversar(self, al_texto, al_frase, al_expresion, al_resultados):
        total = ""
        for _ in range(4):
            texto, llamadas, dicho = self._ronda(None, al_texto, al_frase, al_expresion, total)
            total += dicho
            mensaje = {"role": "assistant", "content": texto}
            if llamadas:
                mensaje["tool_calls"] = llamadas
            self.historial.append(mensaje)
            if not llamadas:
                return total
            for ll in llamadas:
                f = ll.get("function", {})
                args = f.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                try:
                    r = self._ejecutar(f.get("name", ""), args)
                    if r.resultados:
                        al_resultados(r.resultados)
                    resultado = self._texto_resultado(r)
                except Exception as e:
                    resultado = f"Error: {e}"
                self.historial.append({"role": "tool", "content": resultado, "tool_name": f.get("name", "")})
            if total and not total.endswith(" "):
                total += " "
        return total

    @staticmethod
    def _transcripcion(historial):
        lineas = []
        for m in historial:
            if m["role"] == "user":
                lineas.append(f"{config.NOMBRE_USUARIO}: " + re.sub(r"^\[[^]]*\]\s*", "", str(m["content"])))
            elif m["role"] == "assistant" and m.get("content"):
                lineas.append("Jarvis: " + re.sub(r"^\s*\[\w+\]\s*", "", m["content"].strip()))
        return "\n".join(lineas)

    def _resumir(self, historial):
        try:
            charla = self._transcripcion(historial)
            if not charla:
                return
            cuerpo = {"model": modelo(), "stream": False, "keep_alive": MANTENER, "options": opciones(), "messages": [
                {"role": "system", "content": "Resume la conversación en dos o tres frases en español, con los datos "
                                              "útiles sobre el usuario. Solo el resumen."},
                {"role": "user", "content": charla}]}
            with self._chat(cuerpo) as r:
                resumen = json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "").strip()
            if resumen:
                self.cerebro.memoria.agregar_resumen(resumen)
        except Exception as e:
            print(f"[memoria] No se pudo resumir con Ollama: {e}")
