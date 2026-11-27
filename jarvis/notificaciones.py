"""Leer las notificaciones de Windows (WhatsApp, correo, etc.) para contártelas en voz alta.

Windows pide permiso la primera vez («¿Permitir que acceda a tus notificaciones?»). Jarvis solo LEE: para
responder, deja el texto copiado y abre la app; el envío lo haces tú.
"""
import asyncio
import re
import subprocess
import sys

APPS_MENSAJES = ("whatsapp", "telegram", "messenger", "instagram", "signal", "teams", "discord")
APPS_CORREO = ("correo", "mail", "outlook", "gmail", "thunderbird")


def _leer_async():
    from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
    from winrt.windows.ui.notifications.management import (UserNotificationListener,
                                                            UserNotificationListenerAccessStatus)

    async def leer():
        oyente = UserNotificationListener.current
        acceso = await oyente.request_access_async()
        if acceso != UserNotificationListenerAccessStatus.ALLOWED:
            return None
        salida = []
        for n in await oyente.get_notifications_async(NotificationKinds.TOAST):
            try:
                app = n.app_info.display_info.display_name
            except Exception:
                app = "Una aplicación"
            enlace = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
            textos = [t.text for t in enlace.get_text_elements()] if enlace else []
            if textos:
                salida.append({"app": app, "titulo": textos[0], "texto": " ".join(textos[1:]),
                               "hora": n.creation_time})
        return salida

    return asyncio.run(leer())


def leer(filtro=None):
    """Lista de {app, titulo, texto}, la más reciente primero. None si no hay permiso; [] si no hay nada."""
    if sys.platform != "win32":
        return []
    try:
        lista = _leer_async()
    except ImportError:
        raise RuntimeError("Falta instalar el lector de notificaciones. Vuelve a ejecutar instalar.bat.")
    if lista is None:
        return None
    lista.sort(key=lambda n: n["hora"], reverse=True)
    if filtro:
        claves = APPS_MENSAJES if filtro == "mensajes" else APPS_CORREO if filtro == "correo" else (filtro,)
        lista = [n for n in lista if any(k in n["app"].lower() for k in claves)]
    return lista


def resumen(lista, maximo=5) -> str:
    if lista is None:
        return ("Windows no me dio permiso para leer tus notificaciones. Ve a Configuración, Privacidad, "
                "Notificaciones, y permite el acceso.")
    if not lista:
        return "No tienes notificaciones nuevas de eso."
    partes = []
    for n in lista[:maximo]:
        texto = re.sub(r"\s+", " ", n["texto"]).strip()[:160]
        partes.append(f"{n['app']}, de {n['titulo']}: {texto}" if texto else f"{n['app']}: {n['titulo']}")
    extra = f" Y {len(lista) - maximo} más." if len(lista) > maximo else ""
    return (f"Tienes {len(lista)} {'notificación' if len(lista) == 1 else 'notificaciones'}. " +
            ". ".join(partes) + "." + extra)


def copiar(texto: str):
    """Copia al portapapeles (para pegar la respuesta en WhatsApp con Ctrl+V)."""
    if sys.platform == "win32":
        subprocess.run(["clip"], input=texto.encode("utf-16-le"), check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def abrir_whatsapp():
    import os
    try:
        os.startfile("whatsapp:")
    except OSError:
        import webbrowser
        webbrowser.open("https://web.whatsapp.com/")
