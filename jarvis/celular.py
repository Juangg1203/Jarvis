"""App del celular: una página web que tu teléfono abre por el wifi de tu casa.

- Solo funciona dentro de tu red (no sale a internet).
- Cada petición lleva un código secreto que llega al celular al escanear el QR; sin él no responde.
- Tras 10 códigos equivocados desde un mismo aparato, lo bloquea 10 minutos.
"""
import hmac
import json
import mimetypes
import secrets
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config

UI = Path(__file__).resolve().parent / "ui"
PAGINAS = {
    "/": UI / "celular" / "index.html",
    "/manifest.webmanifest": UI / "celular" / "manifest.webmanifest",
    "/icono.png": UI / "assets" / "icono.png",
}


def nuevo_codigo() -> str:
    return secrets.token_urlsafe(18)


def ip_local() -> str:
    """La IP del portátil en el wifi (no envía nada: solo pregunta qué interfaz se usaría)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def qr_svg(texto: str) -> str:
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding="unicode")


class Servidor:
    """responder(texto) -> {"respuesta", "expresion"}; estado() -> dict con el estado de Jarvis."""

    def __init__(self, responder, estado, codigo):
        self.responder, self.estado, self.codigo = responder, estado, codigo
        self.alertas = deque(maxlen=20)  # (id, texto)
        self._id_alerta = 0
        self._fallos = {}  # ip -> (fallos, bloqueado_hasta)
        self._http = None

    @property
    def activo(self):
        return self._http is not None

    @property
    def direccion(self):
        return f"http://{ip_local()}:{config.PUERTO_CELULAR}/"

    def enlace(self):
        # El código va después de '#': el navegador del celular lo guarda y no aparece en ningún registro.
        return f"{self.direccion}#c={self.codigo}"

    def alerta(self, texto):
        self._id_alerta += 1
        self.alertas.append((self._id_alerta, texto))

    def iniciar(self):
        if self._http:
            return True
        servidor = self
        try:
            self._http = ThreadingHTTPServer(("0.0.0.0", config.PUERTO_CELULAR), _crear_manejador(servidor))
        except OSError as e:
            print(f"[celular] No pude abrir el puerto {config.PUERTO_CELULAR}: {e}")
            self._http = None
            return False
        self._http.daemon_threads = True
        threading.Thread(target=self._http.serve_forever, daemon=True, name="celular").start()
        return True

    def detener(self):
        if self._http:
            self._http.shutdown()
            self._http.server_close()
            self._http = None

    # ---------- control de acceso ----------
    def bloqueado(self, ip) -> bool:
        fallos, hasta = self._fallos.get(ip, (0, 0.0))
        return time.monotonic() < hasta

    def autorizado(self, ip, codigo) -> bool:
        if self.bloqueado(ip):
            return False
        if codigo and hmac.compare_digest(str(codigo), self.codigo):
            self._fallos.pop(ip, None)
            return True
        fallos, _ = self._fallos.get(ip, (0, 0.0))
        fallos += 1
        self._fallos[ip] = (0, time.monotonic() + 600) if fallos >= 10 else (fallos, 0.0)
        return False


def _crear_manejador(srv: Servidor):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "Jarvis"
        sys_version = ""

        def log_message(self, *args):  # sin registros en la consola
            pass

        def _enviar(self, codigo, cuerpo: bytes, tipo="application/json; charset=utf-8"):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(cuerpo)

        def _json(self, codigo, datos):
            self._enviar(codigo, json.dumps(datos, ensure_ascii=False).encode("utf-8"))

        def _permitido(self):
            if srv.autorizado(self.client_address[0], self.headers.get("X-Jarvis-Codigo", "")):
                return True
            self._json(403, {"error": "Código no válido. Escanea otra vez el QR en los Ajustes de Jarvis."})
            return False

        def do_GET(self):
            ruta = self.path.split("?", 1)[0]
            if ruta in PAGINAS:
                archivo = PAGINAS[ruta]
                tipo = "application/manifest+json" if archivo.suffix == ".webmanifest" else \
                    (mimetypes.guess_type(archivo.name)[0] or "application/octet-stream")
                if tipo.startswith("text/"):
                    tipo += "; charset=utf-8"
                return self._enviar(200, archivo.read_bytes(), tipo)
            if ruta.startswith("/caras/") and ruta.endswith(".png"):
                nombre = ruta[len("/caras/"):-4]
                archivo = UI / "assets" / "expresiones" / f"{nombre}.png"
                if nombre.isalpha() and archivo.exists():
                    return self._enviar(200, archivo.read_bytes(), "image/png")
            if ruta == "/api/estado":
                if not self._permitido():
                    return
                try:
                    desde = int(self.path.split("desde=", 1)[1]) if "desde=" in self.path else 0
                except ValueError:
                    desde = 0
                datos = dict(srv.estado())
                datos["alertas"] = [{"id": i, "texto": t} for i, t in srv.alertas if i > desde]
                return self._json(200, datos)
            self._json(404, {"error": "No existe"})

        def do_POST(self):
            if self.path != "/api/hablar":
                return self._json(404, {"error": "No existe"})
            if not self._permitido():
                return
            largo = min(int(self.headers.get("Content-Length") or 0), 8000)
            try:
                texto = str(json.loads(self.rfile.read(largo) or b"{}").get("texto", "")).strip()[:1000]
            except ValueError:
                texto = ""
            if not texto:
                return self._json(400, {"error": "Escribe algo."})
            self._json(200, srv.responder(texto))

    return Manejador
