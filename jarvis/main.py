"""Arranca Jarvis: ventana con el avatar, voz local e icono en la bandeja del sistema."""
import json
import os
import sys
import threading
from pathlib import Path

if __package__ in (None, ""):  # permite ejecutar "python jarvis/main.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "jarvis"

import webview

from jarvis import config
from jarvis.comandos import Cerebro
from jarvis.voz import Hablante, Oyente

UI = Path(__file__).resolve().parent / "ui"


class Jarvis:
    def __init__(self):
        self.ventana = None
        self.cerebro = Cerebro()
        self.hablante = Hablante()
        self.dormido = False
        self._lock = threading.Lock()
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

    def _estado_voz(self, estado):
        if estado == "escuchando":
            self.dormido = False
            if self.ventana:
                self.mostrar()
        if estado == "sin_voz":
            self._ui(estado="sin_voz", mensaje=self.oyente.error)
            return
        if estado == "esperando" and self.dormido:
            estado = "dormido"
        self._ui(estado=estado)

    def ejecutar(self, texto: str):
        with self._lock:
            self._ui(estado="pensando", orden=texto)
            try:
                r = self.cerebro.procesar(texto)
            except Exception as e:
                print(f"[jarvis] Error: {e}")
                from jarvis.comandos import Respuesta
                r = Respuesta("Algo salió mal al hacer eso.", "triste")
            self.dormido = r.dormir
            self._ui(estado="hablando", expresion=r.expresion, respuesta=r.texto,
                     resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in r.resultados])
            fin = "dormido" if r.dormir else "esperando"
            self.hablante.decir(r.texto, al_terminar=lambda: self._ui(estado=fin))

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
            width=460, height=760, min_size=(380, 600), background_color="#03070f",
        )
        self.ventana.events.closing += self._al_cerrar

        def al_arrancar():
            self._bandeja()
            self.oyente.iniciar()
            self.hablante.decir(f"Hola {config.NOMBRE_USUARIO}, estoy listo.")

        webview.start(al_arrancar, debug="--debug" in sys.argv)


class Api:
    """Funciones que la interfaz (JavaScript) puede llamar."""

    def __init__(self, jarvis: Jarvis):
        self._j = jarvis

    def enviar_texto(self, texto):
        threading.Thread(target=self._j.ejecutar, args=(texto,), daemon=True).start()

    def escuchar(self):
        self._j.oyente.escuchar_ahora()

    def abrir_resultado(self, indice):
        self.enviar_texto(f"abre el {int(indice) + 1}")

    def ocultar(self):
        self._j.ventana.hide()

    def salir(self):
        self._j.salir()

    def info(self):
        return {"nombre": config.NOMBRE_USUARIO, "activacion": config.PALABRA_ACTIVACION}


def main():
    Jarvis().iniciar()


if __name__ == "__main__":
    main()
