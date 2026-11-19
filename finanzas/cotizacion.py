"""Dólar vendedor (billete) del Banco Nación, leído de bna.com.ar.

Si la página no responde o cambia de formato, devuelve None y la cotización se
escribe a mano: nunca se inventa un valor."""
import re
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache

URL = "https://www.bna.com.ar/Personas"
_CLAVE = "cotizacion_bna"


def leer(html):
    """(venta, fecha) de la tabla de billetes, o None si no se reconoce."""
    inicio = html.find('id="billetes"')
    if inicio < 0:
        return None
    tabla = html[inicio:inicio + 4000]
    fila = re.search(r"Dolar\s+U\.S\.A\s*</td>\s*<td[^>]*>\s*([\d.,]+)\s*</td>\s*<td[^>]*>\s*([\d.,]+)\s*</td>", tabla)
    if not fila:
        return None
    try:
        venta = Decimal(fila.group(2).replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None
    if not Decimal("1") < venta < Decimal("1000000"):
        return None
    fecha = re.search(r'class="fechaCot"[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})', tabla)
    return venta.quantize(Decimal("0.01")), (fecha.group(1) if fecha else "")


def dolar_bna_vendedor():
    """(venta, fecha) o None. Se guarda 30 minutos para no pedirla en cada pantalla."""
    if not settings.COTIZACION_EN_LINEA:
        return None
    guardada = cache.get(_CLAVE)
    if guardada:
        return guardada
    try:
        pedido = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (protocolos-loria)"})
        with urllib.request.urlopen(pedido, timeout=6) as respuesta:
            resultado = leer(respuesta.read(600_000).decode("utf-8", "replace"))
    except Exception:  # sin conexión, bloqueo o demora: se carga a mano
        return None
    if resultado:
        cache.set(_CLAVE, resultado, 30 * 60)
    return resultado
