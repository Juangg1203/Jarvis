"""Arranca Jarvis: ventana con el avatar, voz, conversación con Claude e icono en la bandeja."""
import json
import os
import sys
import threading
import time
from pathlib import Path

if __package__ in (None, ""):  # permite ejecutar "python jarvis/main.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "jarvis"

import webview

from jarvis import ajustes, config, recordatorios
from jarvis.comandos import Cerebro, Respuesta
from jarvis.ia import Conversador
from jarvis.memoria import Memoria
from jarvis.rutinas import Rutinas
from jarvis.voz import Hablante, Oyente

UI = Path(__file__).resolve().parent / "ui"


class Jarvis:
    def __init__(self):
        self.ventana = None
        self.ajustes = ajustes.cargar()
        self.agenda = recordatorios.Agenda(al_sonar=self._sonar)
        self.cerebro = Cerebro(agenda=self.agenda, memoria=Memoria(), rutinas=Rutinas())
        self._alarma_activa = None
        self.conversador = Conversador(self.cerebro)
        self.hablante = Hablante(self.ajustes["voz_motor"], self.ajustes["voz_edge"], al_nivel=self._nivel)
        self.dormido = False
        self._lock = threading.Lock()
        self._ultimo_nivel = 0.0
        self.oyente = Oyente(
            al_cambiar_estado=self._estado_voz,
            al_recibir_orden=self.ejecutar,
            esta_hablando=self.hablante.hablando.is_set,
            al_oir_parcial=lambda t: self._ui(estado="escuchando", parcial=t),
        )

    # ---------- comunicación con la interfaz ----------
    def _ui(self, **datos):
        if self.ventana:
            try:
                self.ventana.evaluate_js(f"window.jarvis && window.jarvis.actualizar({json.dumps(datos)})")
            except Exception:
                pass

    def _nivel(self, n):
        # El nivel del audio mueve la boca/brillo del avatar y la onda de voz.
        if abs(n - self._ultimo_nivel) > 0.03 or n == 0:
            self._ultimo_nivel = n
            if self.ventana:
                try:
                    self.ventana.evaluate_js(f"window.jarvis && window.jarvis.nivel({n:.2f})")
                except Exception:
                    pass

    def _estado_voz(self, estado):
        if estado == "escuchando":
            self.dormido = False
        if estado == "sin_voz":
            self._ui(estado="sin_voz", mensaje=self.oyente.error)
            return
        if estado == "esperando" and self.dormido:
            estado = "dormido"
        self._ui(estado=estado)

    def _al_terminar_de_hablar(self):
        if self.dormido:
            self._ui(estado="dormido")
        elif self.ajustes.get("modo_conversacion") and self.oyente.disponible:
            self.oyente.escuchar_ahora()  # sigue la charla sin repetir "Jarvis"
        else:
            self._ui(estado="esperando")

    # ---------- recordatorios ----------
    def _sonar(self, item):
        """Llega la hora de un recordatorio, alarma o temporizador."""
        texto = recordatorios.texto_aviso(item)
        cara = "sorprendido" if item.get("tipo") != "recordatorio" else "guino"
        try:
            self.mostrar()
        except Exception:
            pass
        self.dormido = False
        self._ui(estado="hablando", expresion=cara, respuesta="⏰ " + texto, aviso=True,
                 avisos=len(self.agenda.pendientes()))
        self.hablante.decir(texto)
        self.hablante.despues(lambda: self._ui(estado="esperando"))
        if item.get("tipo") == "alarma":
            # La alarma se repite hasta 3 veces si no le haces caso.
            self._alarma_activa = item["id"]

            def repetir():
                for _ in range(2):
                    time.sleep(25)
                    if self._alarma_activa != item["id"]:
                        return
                    self._ui(estado="hablando", expresion="sorprendido")
                    self.hablante.decir(texto)
                    self.hablante.despues(lambda: self._ui(estado="esperando"))
                self._alarma_activa = None
            threading.Thread(target=repetir, daemon=True).start()

    def _avisos_cambiaron(self):
        self._ui(avisos=len(self.agenda.pendientes()))

    # ---------- cerebro ----------
    def ejecutar(self, texto: str):
        self._alarma_activa = None  # cualquier orden apaga la alarma que esté sonando
        with self._lock:
            self.hablante.callar()
            self._ui(estado="pensando", orden=texto)
            hay_claude = self.conversador.disponible()
            r = self.cerebro.procesar(texto, solo_ordenes=hay_claude)
            if not r.entendida and hay_claude:
                self._conversar(texto)
                return
            if not r.entendida:
                r.texto += " Si quieres conversar conmigo, añade tu clave de Claude en Ajustes."
            self.dormido = r.dormir
            self._ui(estado="hablando", expresion=r.expresion, respuesta=r.texto,
                     resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in r.resultados])
            self.hablante.decir(r.texto)
            self.hablante.despues(self._al_terminar_de_hablar)
            self._avisos_cambiaron()

    def _conversar(self, texto):
        import anthropic

        estado = {"empezo": False}

        def al_frase(frase):
            if not estado["empezo"]:
                estado["empezo"] = True
                self._ui(estado="hablando")
            self.hablante.decir(frase)

        try:
            self.conversador.responder(
                texto,
                al_texto=lambda t: self._ui(respuesta_parcial=t),
                al_frase=al_frase,
                al_expresion=lambda e: self._ui(estado="hablando", expresion=e),
                al_resultados=lambda res: self._ui(resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in res]),
            )
            self._ui(respuesta_fin=True)
            self._avisos_cambiaron()
        except anthropic.AuthenticationError:
            self._avisar("Mi clave de Claude no es válida. Revísala en Ajustes.", "triste")
        except anthropic.PermissionDeniedError:
            self._avisar("Claude no me deja usar esa clave. Revisa tu cuenta en console.anthropic.com.", "triste")
        except anthropic.RateLimitError:
            self._avisar("Claude está saturado en este momento. Inténtalo en un ratito.", "preocupado")
        except anthropic.APIConnectionError:
            self._avisar("No tengo conexión a internet. Las órdenes del computador siguen funcionando.", "preocupado")
        except anthropic.APIStatusError as e:
            msg = "Se me acabó el saldo de Claude." if "credit" in str(e).lower() else "Claude tuvo un problema."
            self._avisar(msg + " Las órdenes del computador siguen funcionando.", "triste")
        except Exception as e:
            print(f"[jarvis] Error con Claude: {e}")
            self._avisar("Algo salió mal al pensar la respuesta.", "triste")
        self.hablante.despues(self._al_terminar_de_hablar)

    def _avisar(self, texto, expresion):
        self._ui(estado="hablando", expresion=expresion, respuesta=texto)
        self.hablante.decir(texto)

    # ---------- bandeja del sistema (segundo plano) ----------
    def mostrar(self):
        self.ventana.show()
        self.ventana.restore()

    def _bandeja(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        icono = pystray.Icon(
            "Jarvis", Image.open(UI / "assets" / "icono.png"), "Jarvis",
            menu=pystray.Menu(
                pystray.MenuItem("Mostrar", lambda: self.mostrar(), default=True),
                pystray.MenuItem("Escuchar ahora", lambda: self.oyente.escuchar_ahora()),
                pystray.MenuItem("Salir", lambda i: (i.stop(), self.salir())),
            ),
        )
        icono.run_detached()

    def salir(self):
        self._saliendo = True
        try:
            self.ventana.destroy()
        finally:
            os._exit(0)

    def _al_cerrar(self):
        # Cerrar la ventana solo la oculta: Jarvis sigue escuchando en segundo plano.
        if getattr(self, "_saliendo", False):
            return True
        self.ventana.hide()
        return False

    def iniciar(self):
        api = Api(self)
        self.ventana = webview.create_window(
            "Jarvis", str(UI / "index.html"), js_api=api,
            width=480, height=840, min_size=(400, 640), background_color="#02050c",
        )
        self.ventana.events.closing += self._al_cerrar

        def al_arrancar():
            self._bandeja()
            self.oyente.iniciar()
            time.sleep(0.5)
            self._avisos_cambiaron()
            self._ui(estado="hablando", expresion="riendo")
            self.hablante.decir(f"Hola {config.NOMBRE_USUARIO}, estoy listo.")
            self.hablante.despues(lambda: (self._ui(estado="esperando"), self.agenda.iniciar()))

        webview.start(al_arrancar, debug="--debug" in sys.argv)


class Api:
    """Funciones que la interfaz (JavaScript) puede llamar."""

    def __init__(self, jarvis: Jarvis):
        self._j = jarvis

    def enviar_texto(self, texto):
        threading.Thread(target=self._j.ejecutar, args=(texto,), daemon=True).start()

    def escuchar(self):
        self._j._alarma_activa = None
        self._j.hablante.callar()
        self._j.oyente.escuchar_ahora()

    def callar(self):
        self._j.hablante.callar()

    def abrir_resultado(self, indice):
        self.enviar_texto(f"abre el {int(indice) + 1}")

    def ocultar(self):
        self._j.ventana.hide()

    def salir(self):
        self._j.salir()

    def nueva_conversacion(self):
        self._j.conversador.olvidar()

    # ---------- panel de recordatorios, rutinas y memoria ----------
    def leer_panel(self):
        import datetime as dt
        c = self._j.cerebro
        return {
            "avisos": [{"id": x["id"], "tipo": x["tipo"], "mensaje": x["mensaje"],
                        "cuando": recordatorios.describir(dt.datetime.fromisoformat(x["cuando"]))}
                       for x in self._j.agenda.pendientes()],
            "rutinas": c.rutinas.nombres(),
            "datos": [d["texto"] for d in c.memoria.datos],
            "resumenes": len(c.memoria.resumenes),
        }

    def cancelar_aviso(self, id_):
        self._j.agenda.cancelar(str(id_))
        self._j._avisos_cambiaron()
        return self.leer_panel()

    def olvidar_dato(self, indice):
        self._j.cerebro.memoria.olvidar(int(indice) + 1)
        return self.leer_panel()

    def ejecutar_rutina(self, nombre):
        self.enviar_texto(f"modo {nombre}")

    def leer_ajustes(self):
        a = ajustes.cargar()
        clave = ajustes.clave_claude()
        return {
            "tiene_clave": bool(clave),
            "clave_final": clave[-4:] if clave else "",
            "voz_motor": a["voz_motor"],
            "modo_conversacion": a["modo_conversacion"],
            "nombre": config.NOMBRE_USUARIO,
        }

    def guardar_ajustes(self, cambios):
        cambios = dict(cambios or {})
        if not cambios.get("anthropic_api_key"):
            cambios.pop("anthropic_api_key", None)  # campo vacío = conservar la clave actual
        a = ajustes.guardar(cambios)
        self._j.ajustes = a
        self._j.hablante.motor = a["voz_motor"]
        return self.leer_ajustes()


def main():
    Jarvis().iniciar()


if __name__ == "__main__":
    main()
