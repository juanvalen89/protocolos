"""Lectura de la carta de pago (payment letter) de la CRO y conciliación con lo cargado."""
import re
from datetime import date, timedelta
from decimal import Decimal

from estudios.models import Visita

from .models import ItemFactura

MESES = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class CartaIlegible(Exception):
    pass


def texto_de_pdf(archivo):
    from pypdf import PdfReader
    try:
        return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(archivo).pages)
    except Exception as error:
        raise CartaIlegible("El archivo no es un PDF que se pueda leer.") from error


def leer(texto, sitio):
    """Devuelve {request_id, fecha, monto, items:[(secuencia, código, visita, monto)]}.

    El PDF de la CRO sale con las palabras partidas en renglones, así que se
    trabaja sobre el texto sin espacios y se usa el número de sitio para
    separar la secuencia del código de sujeto ("4" + "312-21165")."""
    junto = re.sub(r"\s+", "", texto)
    # El Request ID y la fecha se buscan en el texto original: pegados quedarían unidos.
    pedido = re.search(r"Request\s*ID\s*:?\s*(PYRQ)\s*-\s*(\d+)", texto, re.I)
    if not pedido:
        raise CartaIlegible("No encontré el Request ID (PYRQ-…): ¿es una carta de pago de la CRO?")
    cuando = re.search(r"\b(\d{1,2})\s*-\s*([A-Za-z]{3})\s*-\s*(\d{4})\b", texto)
    if not cuando or cuando.group(2).lower() not in MESES:
        raise CartaIlegible("No encontré la fecha de la carta.")
    fecha = date(int(cuando.group(3)), MESES[cuando.group(2).lower()], int(cuando.group(1)))
    total = re.search(r"amountofUSD([\d,]+\.\d{2})", junto, re.I)
    cuerpo = junto.split("Amount", 2)[-1] if "Amount" in junto else junto
    cuerpo = re.split(r"InvoiceRequestForm|Pleaseinclude", cuerpo)[0]
    sitio = re.escape(sitio) if sitio else r"\d{3}"
    items = [(m.group(1), m.group(2), _con_espacio(m.group(3)), _decimal(m.group(4)))
             for m in re.finditer(rf"(\d{{1,2}})({sitio}-\d{{5}})(.+?)USD([\d,]+\.\d{{2}})", cuerpo)]
    if not items:
        raise CartaIlegible("No encontré renglones de visitas en la carta.")
    monto = _decimal(total.group(1)) if total else sum((i[3] for i in items), Decimal("0"))
    return {"request_id": f"PYRQ-{pedido.group(2)}", "fecha": fecha, "monto": monto, "items": items}


def _decimal(texto):
    return Decimal(texto.replace(",", ""))


def _con_espacio(nombre):
    """'Week12' → 'Week 12', 'Day1' → 'Day 1'."""
    return re.sub(r"(?<=[A-Za-z])(?=\d)", " ", nombre).strip()


def periodo(fecha):
    """La carta llega a mediados del mes siguiente al trimestre que cubre."""
    f = fecha - timedelta(days=20)
    return f"Q{(f.month - 1) // 3 + 1} {f.year}"


def fin_del_periodo(fecha):
    """Último día del trimestre que cubre una carta con esa fecha."""
    f = fecha - timedelta(days=20)
    mes_fin = ((f.month - 1) // 3 + 1) * 3
    return date(f.year + (mes_fin == 12), mes_fin % 12 + 1, 1) - timedelta(days=1)


def _clave(nombre):
    return re.sub(r"\s+", "", nombre).lower()


def conciliar(carta):
    """Compara cada renglón de la carta con las visitas cargadas.
    Devuelve (filas, afuera): `afuera` son visitas hechas dentro del trimestre
    de la carta, todavía sin facturar, que la carta no trae."""
    protocolo = carta.protocolo
    visitas = {}
    for v in (Visita.objects.filter(paciente__protocolo=protocolo, completa=True)
              .select_related("paciente", "tipo").prefetch_related("items_factura__factura")):
        visitas[(v.paciente.codigo, _clave(v.tipo.nombre))] = v
    filas, en_carta = [], set()
    for item in carta.items.all():
        v = visitas.get((item.codigo_paciente, _clave(item.nombre_visita)))
        factura = None
        if v is None:
            estado, detalle = "falta", "La carta la paga, pero no está cargada."
        else:
            en_carta.add(v.id)
            factura = next((i.factura for i in v.items_factura.all() if i.concepto == ItemFactura.Concepto.VISITA), None)
            if v.tipo.precio_usd != item.monto_usd:
                estado, detalle = "monto", f"El presupuesto dice USD {v.tipo.precio_usd}."
            elif factura:
                estado, detalle = "facturada", f"Ya está en la factura {factura.numero}."
            else:
                estado, detalle = "ok", "Lista para facturar."
        filas.append({"item": item, "visita": v, "estado": estado, "detalle": detalle, "factura": factura})
    limite = fin_del_periodo(carta.fecha)
    afuera = [v for v in visitas.values()
              if v.id not in en_carta and v.fecha <= limite and v.tipo.precio_usd
              and not any(i.concepto == ItemFactura.Concepto.VISITA for i in v.items_factura.all())]
    afuera.sort(key=lambda v: (v.fecha, v.paciente.codigo))
    return filas, afuera
