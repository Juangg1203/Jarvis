"""Conversación con Google Gemini (gratis con la clave de aistudio.google.com).

Usa la API REST de Gemini directamente (sin librerías extra), en streaming, con las mismas
herramientas que Claude: abrir archivos, recordatorios, control del PC, documentos...
"""
import json
import re
import urllib.error
import urllib.request

from . import ajustes, config, internet
from .comandos import Respuesta
from .ia import EXPRESIONES, HERRAMIENTAS, SISTEMA, Conversador

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:{metodo}"


class ErrorGemini(Exception):
    """Error con un mensaje listo para decirle al usuario."""

    def __init__(self, mensaje, cara="triste"):
        super().__init__(mensaje)
        self.mensaje, self.cara = mensaje, cara


SISTEMA_GEMINI = SISTEMA.replace(
    "Tienes búsqueda en internet:",
    "Tienes búsqueda en internet con la herramienta buscar_internet (tipo clima, noticias o pregunta):")

# Herramienta propia para buscar en internet (Claude usa su buscador; Gemini usa esta).
BUSCAR_INTERNET = {
    "name": "buscar_internet",
    "description": "Busca en internet: el clima de una ciudad (hoy o mañana), las noticias (de un tema o generales) "
                   "o la respuesta corta a una pregunta general.",
    "input_schema": {"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["clima", "noticias", "pregunta"]},
        "consulta": {"type": "string", "description": "Ciudad, tema de noticias o pregunta. Vacío para noticias generales."},
        "manana": {"type": "boolean", "description": "Para el clima: true si pregunta por mañana."},
    }, "required": ["tipo"]},
}


def _esquema(s):
    """Convierte el esquema JSON de las herramientas al formato que acepta Gemini."""
    if not isinstance(s, dict):
        return s
    salida = {}
    for k, v in s.items():
        if k in ("additionalProperties", "eager_input_streaming", "$schema", "default"):
            continue
        if k == "properties":
            salida[k] = {n: _esquema(p) for n, p in v.items()}
        elif k == "items":
            salida[k] = _esquema(v)
        else:
            salida[k] = v
    return salida


def declaraciones():
    lista = []
    for h in HERRAMIENTAS + [BUSCAR_INTERNET]:
        if "input_schema" not in h:
            continue  # herramientas de servidor de Claude (su buscador web)
        d = {"name": h["name"], "description": h["description"]}
        if h["input_schema"].get("properties"):
            d["parameters"] = _esquema(h["input_schema"])
        lista.append(d)
    return [{"functionDeclarations": lista}]


def _contenido(m):
    """Mensaje del historial -> formato de Gemini."""
    if "parts" in m:
        return {"role": m["role"], "parts": m["parts"]}
    return {"role": "user", "parts": [{"text": str(m["content"])}]}


def peticion(metodo, cuerpo, modelo=None):
    modelo = modelo or config.MODELO_GEMINI
    url = URL.format(modelo=modelo, metodo=metodo) + ("?alt=sse" if metodo.startswith("stream") else "")
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "x-goog-api-key": ajustes.clave_gemini()})
    try:
        return urllib.request.urlopen(req, timeout=90)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")
        if e.code == 404 and modelo != config.MODELO_GEMINI_RESPALDO:
            return peticion(metodo, cuerpo, config.MODELO_GEMINI_RESPALDO)
        if e.code in (400, 401, 403) and ("API key" in detalle or "API_KEY" in detalle or e.code != 400):
            raise ErrorGemini("Mi clave de Gemini no es válida. Revísala en Ajustes.") from e
        if e.code == 429:
            raise ErrorGemini("Ya usé todas las preguntas gratis de Gemini por ahora. "
                              "Espera un minuto, o hasta mañana si fue el límite del día.", "preocupado") from e
        if e.code >= 500:
            raise ErrorGemini("Gemini está saturado en este momento. Inténtalo en un ratito.", "preocupado") from e
        print(f"[gemini] {e.code}: {detalle[:500]}")
        raise ErrorGemini("Gemini no entendió la petición.") from e
    except urllib.error.URLError as e:
        raise ErrorGemini("No tengo conexión a internet. Las órdenes del computador siguen funcionando.",
                          "preocupado") from e


class Frases:
    """Va juntando el texto que llega y entrega frases completas para la voz."""

    def __init__(self, al_frase, al_texto, al_expresion, previo):
        self.al_frase, self.al_texto, self.al_expresion = al_frase, al_texto, al_expresion
        self.previo, self.pendiente, self.dicho, self.etiqueta = previo, "", "", False

    def agregar(self, texto):
        self.pendiente += texto
        if not self.etiqueta:
            m = re.match(r"\s*\[(\w+)\]\s*", self.pendiente)
            if m:
                if m.group(1).lower() in EXPRESIONES:
                    self.al_expresion(m.group(1).lower())
                self.pendiente = self.pendiente[m.end():]
                self.etiqueta = True
            elif len(self.pendiente) > 15 or (self.pendiente.strip() and not self.pendiente.lstrip().startswith("[")):
                self.etiqueta = True
            else:
                return
        while True:
            m = next((x for x in re.finditer(r"[.!?…:;\n](\s|$)", self.pendiente)
                      if x.end() >= 12 or x.group(0).startswith("\n")), None)
            if not m:
                break
            frase, self.pendiente = self.pendiente[:m.end()], self.pendiente[m.end():]
            self._decir(frase)

    def _decir(self, frase):
        frase = re.sub(r"[*_#`]+", "", frase)  # por si escribe markdown
        if frase.strip():
            self.dicho += frase
            self.al_frase(frase.strip())
            self.al_texto(self.previo + self.dicho)

    def terminar(self):
        if self.pendiente.strip():
            self._decir(self.pendiente)
            self.pendiente = ""
        return self.dicho


class ConversadorGemini(Conversador):
    def disponible(self) -> bool:
        return bool(ajustes.clave_gemini())

    def _peticion(self, metodo, cuerpo, modelo=None):
        return peticion(metodo, cuerpo, modelo)

    def _cuerpo(self, sistema):
        return {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [_contenido(m) for m in self.historial],
            "tools": declaraciones(),
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.8},
        }

    def _ronda(self, cliente, al_texto, al_frase, al_expresion, previo):
        sistema = SISTEMA_GEMINI + ("\n\n" + self._contexto if self._contexto else "")
        frases = Frases(al_frase, al_texto, al_expresion, previo)
        partes, fin = [], ""
        with self._peticion("streamGenerateContent", self._cuerpo(sistema)) as r:
            for linea in r:
                linea = linea.decode("utf-8").strip()
                if not linea.startswith("data:"):
                    continue
                datos = json.loads(linea[5:])
                if datos.get("promptFeedback", {}).get("blockReason"):
                    fin = "bloqueado"
                for c in datos.get("candidates", []):
                    fin = c.get("finishReason", fin)
                    for p in c.get("content", {}).get("parts", []):
                        if p.get("thought"):
                            continue
                        partes.append(p)
                        if "text" in p and "functionCall" not in p:
                            frases.agregar(p["text"])
        return partes, fin, frases.terminar()

    def _conversar(self, al_texto, al_frase, al_expresion, al_resultados):
        total = ""
        for _ in range(6):  # como mucho 6 rondas de herramientas
            partes, fin, dicho = self._ronda(None, al_texto, al_frase, al_expresion, total)
            total += dicho
            if fin in ("SAFETY", "PROHIBITED_CONTENT", "bloqueado"):
                return total or "Prefiero no responder a eso."
            if not partes:
                return total
            self.historial.append({"role": "model", "parts": partes})
            llamadas = [p["functionCall"] for p in partes if "functionCall" in p]
            if not llamadas:
                return total
            respuestas = []
            for ll in llamadas:
                try:
                    r = self._ejecutar(ll.get("name", ""), ll.get("args") or {})
                    if r.resultados:
                        al_resultados(r.resultados)
                    resultado = self._texto_resultado(r)
                except Exception as e:
                    resultado = f"Error: {e}"
                respuestas.append({"functionResponse": {"name": ll.get("name", ""), "response": {"resultado": resultado}}})
            self.historial.append({"role": "user", "parts": respuestas})
            if total and not total.endswith(" "):
                total += " "
        return total

    def _ejecutar(self, nombre, entrada) -> Respuesta:
        if nombre == "buscar_internet":
            tipo = str(entrada.get("tipo", "pregunta"))
            consulta = str(entrada.get("consulta") or "").strip()
            try:
                if tipo == "clima":
                    return Respuesta(internet.clima(consulta or self.cerebro.ciudad(), bool(entrada.get("manana"))))
                if tipo == "noticias":
                    return Respuesta(internet.noticias(consulta))
                return Respuesta(internet.preguntar(consulta) or "No encontré nada sobre eso.")
            except Exception:
                return Respuesta("No pude conectarme a internet para buscar eso.")
        return super()._ejecutar(nombre, entrada)

    def escribir(self, instruccion: str) -> str:
        from .ia import Conversador
        cuerpo = {"systemInstruction": {"parts": [{"text": Conversador.ESCRITOR}]},
                  "contents": [{"role": "user", "parts": [{"text": instruccion}]}],
                  "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.7}}
        with self._peticion("generateContent", cuerpo) as r:
            datos = json.loads(r.read().decode("utf-8"))
        partes = datos["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()

    # ---------- memoria ----------
    @staticmethod
    def _transcripcion(historial):
        lineas = []
        for m in historial:
            if m["role"] == "user" and "content" in m:
                lineas.append(f"{config.NOMBRE_USUARIO}: " + re.sub(r"^\[[^]]*\]\s*", "", str(m["content"])))
            elif m["role"] == "model":
                texto = " ".join(p.get("text", "") for p in m["parts"] if "text" in p and not p.get("thought"))
                texto = re.sub(r"^\s*\[\w+\]\s*", "", texto.strip())
                if texto:
                    lineas.append("Jarvis: " + texto)
        return "\n".join(lineas)

    def _resumir(self, historial):
        try:
            charla = self._transcripcion(historial)
            if not charla:
                return
            cuerpo = {
                "systemInstruction": {"parts": [{"text":
                    "Resume conversaciones para la memoria de un asistente personal. Escribe en español, en dos o "
                    "tres frases, de qué hablaron y cualquier dato útil sobre el usuario. Solo el resumen."}]},
                "contents": [{"role": "user", "parts": [{"text": charla}]}],
                "generationConfig": {"maxOutputTokens": 400},
            }
            with self._peticion("generateContent", cuerpo) as r:
                datos = json.loads(r.read().decode("utf-8"))
            partes = datos["candidates"][0]["content"]["parts"]
            resumen = " ".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
            if resumen:
                self.cerebro.memoria.agregar_resumen(resumen)
        except Exception as e:
            print(f"[memoria] No se pudo resumir con Gemini: {e}")
