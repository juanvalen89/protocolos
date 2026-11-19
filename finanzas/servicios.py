"""Cálculos de dinero. Todo sale de la carga (quién hizo qué) más la configuración."""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from estudios.models import Medico, Paciente, Realizacion, Visita

from .models import Factura, Gasto, ItemFactura, PagoMedico, Socio

CERO = Decimal("0")
CENT = Decimal("0.01")


def redondear(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- médicos

def derivaciones(protocolo):
    """Pacientes derivados que ya entraron al estudio (tienen Day 1): al médico
    que derivó se le debe el importe fijo del protocolo, igual que un procedimiento.
    Devuelve [{paciente, medico, fecha (la del Day 1), monto}]."""
    if not protocolo.derivacion_usd:
        return []
    salida = []
    qs = (Paciente.objects.filter(protocolo=protocolo, derivado_por__isnull=False)
          .select_related("derivado_por").prefetch_related("visitas__tipo"))
    for p in qs:
        fecha = p.fecha_day1()
        if fecha:
            salida.append({"paciente": p, "medico": p.derivado_por, "fecha": fecha, "monto": protocolo.derivacion_usd})
    return salida


def saldos_medicos(protocolo):
    """Por médico: lo que le corresponde por lo cargado, lo pagado y el saldo."""
    devengado = defaultdict(lambda: CERO)
    for r in Realizacion.objects.filter(visita__paciente__protocolo=protocolo).select_related("medico"):
        devengado[r.medico_id] += r.monto_usd
    for d in derivaciones(protocolo):
        devengado[d["medico"].id] += d["monto"]
    pagado = defaultdict(lambda: CERO)
    for p in PagoMedico.objects.filter(protocolo=protocolo):
        pagado[p.medico_id] += p.monto_usd
    filas = []
    for m in Medico.objects.filter(externo=False):
        d, p = devengado[m.id], pagado[m.id]
        if d or p:
            filas.append({"medico": m, "devengado": d, "pagado": p, "saldo": d - p})
    return filas


def detalle_por_mes(protocolo):
    """{(año, mes): {medico: {tipo_visita: importe}}} para la liquidación mensual."""
    meses = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: CERO)))
    qs = (Realizacion.objects.filter(visita__paciente__protocolo=protocolo, medico__externo=False)
          .select_related("medico", "visita__tipo"))
    for r in qs:
        if r.monto_usd:
            f = r.visita.fecha
            meses[(f.year, f.month)][r.medico][r.visita.tipo.nombre] += r.monto_usd
    for d in derivaciones(protocolo):
        meses[(d["fecha"].year, d["fecha"].month)][d["medico"]]["Derivación"] += d["monto"]
    salida = []
    for clave in sorted(meses, reverse=True):
        filas = []
        for medico in sorted(meses[clave], key=lambda m: m.nombre):
            por_visita = meses[clave][medico]
            filas.append({"medico": medico, "por_visita": dict(por_visita), "total": sum(por_visita.values(), CERO)})
        salida.append({"anio": clave[0], "mes": clave[1], "filas": filas,
                       "total": sum((f["total"] for f in filas), CERO)})
    return salida


# ---------------------------------------------------------------- cobros al sponsor

def pendientes_de_facturar(protocolo):
    """Lo realizado que todavía no está en ninguna factura: visitas, viáticos y condicionales."""
    visitas = (Visita.objects.filter(paciente__protocolo=protocolo, completa=True)
               .select_related("paciente", "tipo").prefetch_related("items_factura"))
    sin_visita, sin_viatico = [], []
    for v in visitas:
        conceptos = {i.concepto for i in v.items_factura.all()}
        if ItemFactura.Concepto.VISITA not in conceptos and v.tipo.precio_usd:
            sin_visita.append({"visita": v, "monto": v.tipo.precio_usd})
        if ItemFactura.Concepto.VIATICO not in conceptos and protocolo.viatico_usd:
            sin_viatico.append({"visita": v, "monto": protocolo.viatico_usd})
    condicionales = []
    qs = (Realizacion.objects.filter(visita__paciente__protocolo=protocolo,
                                     procedimiento__precio_sponsor_usd__gt=0, items_factura__isnull=True)
          .select_related("visita__paciente", "visita__tipo", "procedimiento"))
    for r in qs:
        condicionales.append({"realizacion": r, "monto": r.procedimiento.precio_sponsor_usd})
    total = sum((x["monto"] for x in sin_visita + sin_viatico + condicionales), CERO)
    return {"visitas": sin_visita, "viaticos": sin_viatico, "condicionales": condicionales, "total": total,
            "total_visitas": sum((x["monto"] for x in sin_visita), CERO),
            "total_viaticos": sum((x["monto"] for x in sin_viatico), CERO),
            "total_condicionales": sum((x["monto"] for x in condicionales), CERO)}


def resumen_facturas(protocolo, hoy):
    facturas = list(Factura.objects.filter(protocolo=protocolo).select_related("carta").prefetch_related("items"))
    cobrado = sum((f.total for f in facturas if f.cobrada), CERO)
    por_cobrar = sum((f.total for f in facturas if not f.cobrada), CERO)
    vencidas = [f for f in facturas if not f.cobrada and f.vencimiento < hoy]
    return {"facturas": facturas, "cobrado": cobrado, "por_cobrar": por_cobrar, "vencidas": vencidas,
            "vencido": sum((f.total for f in vencidas), CERO)}


# ---------------------------------------------------------------- reparto

def reparto(protocolo):
    """Sobre lo COBRADO: neto = cobrado − gastos − pagos a médicos. Del neto sale
    primero la comisión; el resto se divide por porcentaje. A cada socio se le
    suma lo que adelantó de su bolsillo. Es la misma cuenta de la planilla."""
    cobrado = sum((f.total for f in Factura.objects.filter(protocolo=protocolo, cobrada=True)
                   .prefetch_related("items")), CERO)
    adelantado = defaultdict(lambda: CERO)
    for g in Gasto.objects.filter(protocolo=protocolo):
        adelantado[g.pagado_por_id] += g.monto_usd
    for p in PagoMedico.objects.filter(protocolo=protocolo):
        adelantado[p.pagado_por_id] += p.monto_usd
    egresos = sum(adelantado.values(), CERO)
    neto = cobrado - egresos
    socios = list(Socio.objects.all())
    comision = sum((neto * s.porcentaje / 100 for s in socios if s.es_comision), CERO)
    a_dividir = neto - comision
    filas = []
    for s in socios:
        parte = neto * s.porcentaje / 100 if s.es_comision else a_dividir * s.porcentaje / 100
        filas.append({"socio": s, "parte": redondear(parte), "adelantado": adelantado[s.id],
                      "total": redondear(parte + adelantado[s.id])})
    return {"cobrado": cobrado, "egresos": egresos, "neto": neto, "comision": redondear(comision),
            "a_dividir": redondear(a_dividir), "filas": filas}
