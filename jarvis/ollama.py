"""Conversación con Ollama: una IA que corre en tu propio portátil, gratis y sin internet.

Instálalo con instalar_ollama.bat (descarga Ollama y el modelo, unos 2 GB). Es más lento y menos listo
que Gemini, pero nada sale de tu computador.
"""
import json
import re
import time
import urllib.error
import urllib.request

from . import config
from .gemini import BUSCAR_INTERNET, ConversadorGemini, ErrorGemini, Frases
from .ia import HERRAMIENTAS, SISTEMA

BASE = "http://127.0.0.1:11434"

# Un modelo pequeño se confunde con muchas herramientas: solo le damos las útiles para conversar
# (las órdenes del PC las sigue entendiendo Jarvis por su cuenta antes de preguntarle a la IA).
HERRAMIENTAS_OLLAMA = {"abrir", "buscar_archivos", "crear_recordatorio", "listar_recordatorios", "recordar_dato",
                       "buscar_en_conversaciones", "leer_documento", "redactar_documento", "redactar_correo",
                       "reproducir_musica"}

SISTEMA_OLLAMA = SISTEMA.replace(
    "Tienes búsqueda en internet:",
    "Tienes búsqueda en internet con la herramienta buscar_internet (solo si hay conexión):") + \
    "\nUsa las herramientas solo cuando de verdad haga falta; para charlar, responde directo."


class ErrorOllama(ErrorGemini):
    pass


def herramientas():
    salida = []
    for h in HERRAMIENTAS + [BUSCAR_INTERNET]:
        if h.get("name") not in HERRAMIENTAS_OLLAMA | {"buscar_internet"} or "input_schema" not in h:
            continue
        salida.append({"type": "function", "function": {
            "name": h["name"], "description": h["description"], "parameters": h["input_schema"]}})
    return salida


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
            ok = tiene(config.MODELO_OLLAMA, modelos_instalados())
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
                raise ErrorOllama(f"Falta el modelo {config.MODELO_OLLAMA}. Ejecuta instalar_ollama.bat.") from e
            print(f"[ollama] {e.code}: {detalle[:400]}")
            raise ErrorOllama("Ollama tuvo un problema al pensar la respuesta.") from e
        except urllib.error.URLError as e:
            ConversadorOllama._cache = (0.0, False)
            raise ErrorOllama("Ollama no está abierto. Ábrelo desde el menú Inicio o ejecuta instalar_ollama.bat.",
                              "preocupado") from e

    def _ronda(self, cliente, al_texto, al_frase, al_expresion, previo):
        sistema = SISTEMA_OLLAMA + ("\n\n" + self._contexto if self._contexto else "")
        cuerpo = {"model": config.MODELO_OLLAMA, "stream": True, "tools": herramientas(),
                  "messages": [{"role": "system", "content": sistema}] + self.historial,
                  "options": {"num_ctx": 8192, "temperature": 0.7}, "keep_alive": "30m"}
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
            cuerpo = {"model": config.MODELO_OLLAMA, "stream": False, "messages": [
                {"role": "system", "content": "Resume la conversación en dos o tres frases en español, con los datos "
                                              "útiles sobre el usuario. Solo el resumen."},
                {"role": "user", "content": charla}]}
            with self._chat(cuerpo) as r:
                resumen = json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "").strip()
            if resumen:
                self.cerebro.memoria.agregar_resumen(resumen)
        except Exception as e:
            print(f"[memoria] No se pudo resumir con Ollama: {e}")
