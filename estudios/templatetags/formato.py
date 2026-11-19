from decimal import Decimal

from django import template

register = template.Library()

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _miles(valor, decimales=2):
    valor = Decimal(valor or 0)
    texto = f"{abs(valor):,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if valor < 0 else "") + texto


@register.filter
def usd(valor):
    return f"USD {_miles(valor)}"


@register.filter
def pesos(valor):
    return "" if valor is None else f"$ {_miles(valor)}"


@register.filter
def mes(numero):
    return MESES[int(numero)]


@register.filter
def clave(diccionario, k):
    return diccionario.get(k)
