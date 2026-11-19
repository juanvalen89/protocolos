"""Middleware que obliga a cambiar la contraseña genérica en el primer ingreso.

Un usuario con `debe_cambiar_clave` tildado solo puede ver la pantalla de
cambio de contraseña (y salir): el resto del sistema queda bloqueado hasta
que elija una contraseña propia.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class ObligarCambioClaveMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and usuario.debe_cambiar_clave:
            permitidas = {reverse("password_change"), reverse("password_change_done"),
                          reverse("logout")}
            if request.path not in permitidas and not request.path.startswith("/static/"):
                messages.warning(
                    request,
                    "Tu usuario tiene la contraseña inicial: elegí una propia para empezar a usar el sistema.")
                return redirect("password_change")
        return self.get_response(request)
