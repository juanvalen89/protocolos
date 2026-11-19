"""Ir a una pantalla por su nombre de ruta, no por una dirección escrita a
mano: si mañana cambia la dirección, no hay que salir a buscarla por el código."""
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


def direccion(nombre, *args, ancla="", **consulta) -> str:
    url = reverse(nombre, args=args)
    consulta = {k: v for k, v in consulta.items() if v not in (None, "")}
    if consulta:
        url += "?" + urlencode(consulta)
    return url + (f"#{ancla}" if ancla else "")


def ir(nombre, *args, ancla="", **consulta):
    return redirect(direccion(nombre, *args, ancla=ancla, **consulta))
