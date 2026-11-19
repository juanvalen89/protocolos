"""Pantallas con dinero. Todas son solo de Dirección (cuentas.permisos.solo_direccion)."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.permisos import solo_direccion
from estudios.models import Medico, Paciente, Realizacion, Visita
from estudios.views import protocolo_actual

from . import cartas, cotizacion, servicios
from .forms import GastoForm, PagoMedicoForm
from .models import CartaPago, Factura, Gasto, ItemCarta, ItemFactura, PagoMedico
from .pdf import factura_pdf

CERO = Decimal("0")


@solo_direccion
def tablero(request):
    protocolo = protocolo_actual(request)
    if not protocolo:
        return render(request, "finanzas/tablero.html", {"protocolo": None})
    hoy = timezone.localdate()
    facturas = servicios.resumen_facturas(protocolo, hoy)
    pendientes = servicios.pendientes_de_facturar(protocolo)
    saldos = servicios.saldos_medicos(protocolo)
    atrasadas = []
    for p in Paciente.objects.filter(protocolo=protocolo).prefetch_related("visitas__tipo", "protocolo__tipos_visita"):
        for tipo, esperada, atrasada in p.visitas_esperadas(hoy):
            if atrasada:
                atrasadas.append({"paciente": p, "tipo": tipo, "esperada": esperada, "monto": tipo.precio_usd})
    return render(request, "finanzas/tablero.html", {
        "protocolo": protocolo, "facturas": facturas, "pendientes": pendientes,
        "saldo_medicos": sum((s["saldo"] for s in saldos if s["saldo"] > 0), CERO),
        "medicos_con_saldo": [s for s in saldos if s["saldo"] > 0],
        "atrasadas": atrasadas, "monto_atrasadas": sum((a["monto"] for a in atrasadas), CERO),
        "mal_request": [f for f in facturas["facturas"] if f.request_id_no_coincide and not f.cobrada],
        "reparto": servicios.reparto(protocolo),
    })


@solo_direccion
def medicos(request):
    protocolo = protocolo_actual(request)
    return render(request, "finanzas/medicos.html", {
        "protocolo": protocolo,
        "saldos": servicios.saldos_medicos(protocolo),
        "meses": servicios.detalle_por_mes(protocolo),
        "pagos": PagoMedico.objects.filter(protocolo=protocolo).select_related("medico", "pagado_por"),
    })


@solo_direccion
def medico_detalle(request, pk):
    protocolo = protocolo_actual(request)
    medico = get_object_or_404(Medico, pk=pk)
    realizaciones = (Realizacion.objects.filter(medico=medico, visita__paciente__protocolo=protocolo)
                     .select_related("visita__paciente", "visita__tipo", "procedimiento")
                     .order_by("-visita__fecha", "visita__paciente__codigo", "procedimiento__orden"))
    derivaciones = [d for d in servicios.derivaciones(protocolo) if d["medico"].id == medico.id]
    return render(request, "finanzas/medico_detalle.html", {
        "protocolo": protocolo, "medico": medico, "realizaciones": realizaciones, "derivaciones": derivaciones,
        "total": sum((r.monto_usd for r in realizaciones), CERO) + sum((d["monto"] for d in derivaciones), CERO),
        "pagos": PagoMedico.objects.filter(protocolo=protocolo, medico=medico),
    })


@solo_direccion
def pago_nuevo(request):
    protocolo = protocolo_actual(request)
    inicial = {"fecha": timezone.localdate(), "medico": request.GET.get("medico"), "monto_usd": request.GET.get("monto")}
    bna = cotizacion.dolar_bna_vendedor()
    if bna:
        inicial["cotizacion"] = bna[0]
    form = PagoMedicoForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        pago = form.save(commit=False)
        pago.protocolo = protocolo
        pago.save()
        messages.success(request, f"Pago a {pago.medico} registrado.")
        return redirect("medicos")
    return render(request, "finanzas/formulario.html", {
        "form": form, "titulo": "Registrar pago a un médico", "volver": "medicos",
        "ayuda": "El importe se guarda en dólares. Si se paga en pesos, poné la cotización y el sistema calcula el total.",
        "bna": True, "cotizacion_bna": bna})


@solo_direccion
def cobros(request):
    protocolo = protocolo_actual(request)
    hoy = timezone.localdate()
    return render(request, "finanzas/cobros.html", {
        "protocolo": protocolo, "hoy": hoy,
        "resumen": servicios.resumen_facturas(protocolo, hoy),
        "pendientes": servicios.pendientes_de_facturar(protocolo),
        "cartas": CartaPago.objects.filter(protocolo=protocolo),
    })


@solo_direccion
def factura_nueva(request):
    protocolo = protocolo_actual(request)
    pendientes = servicios.pendientes_de_facturar(protocolo)
    error = None
    if request.method == "POST":
        try:
            fecha = date.fromisoformat(request.POST.get("fecha", ""))
            vencimiento = date.fromisoformat(request.POST.get("vencimiento", ""))
        except ValueError:
            fecha = vencimiento = None
            error = "Faltan la fecha o el vencimiento."
        numero = request.POST.get("numero", "").strip()
        if not numero:
            error = "Falta el número de factura."
        elif Factura.objects.filter(protocolo=protocolo, numero=numero).exists():
            error = f"Ya existe la factura {numero}."
        elegidos = request.POST.getlist("item")
        extra_desc = request.POST.get("extra_descripcion", "").strip()
        extra_monto = None
        if extra_desc:
            try:
                extra_monto = Decimal(request.POST.get("extra_monto", "").replace(",", "."))
            except InvalidOperation:
                error = "El importe del ítem adicional no es un número."
        if not error and not elegidos and not extra_desc:
            error = "Elegí al menos un ítem para facturar."
        if not error:
            carta = CartaPago.objects.filter(protocolo=protocolo, pk=request.POST.get("carta") or 0).first()
            with transaction.atomic():
                factura = Factura.objects.create(
                    protocolo=protocolo, numero=numero, fecha=fecha, vencimiento=vencimiento, carta=carta,
                    request_id=carta.request_id if carta else request.POST.get("request_id", "").strip())
                C = ItemFactura.Concepto
                # Los importes se recalculan acá: no se confía en lo que manda el formulario.
                por_clave = {f"v:{x['visita'].id}": (C.VISITA, x["visita"], None, x["monto"]) for x in pendientes["visitas"]}
                por_clave.update({f"t:{x['visita'].id}": (C.VIATICO, x["visita"], None, x["monto"]) for x in pendientes["viaticos"]})
                por_clave.update({f"c:{x['realizacion'].id}": (C.CONDICIONAL, x["realizacion"].visita, x["realizacion"], x["monto"])
                                  for x in pendientes["condicionales"]})
                for clave in elegidos:
                    if clave not in por_clave:
                        continue
                    concepto, visita, realizacion, monto = por_clave[clave]
                    detalle = realizacion.procedimiento.nombre if realizacion else C(concepto).label
                    ItemFactura.objects.create(
                        factura=factura, concepto=concepto, visita=visita, realizacion=realizacion, monto_usd=monto,
                        descripcion=f"{visita.paciente.codigo} · {visita.tipo.nombre} · {detalle}")
                if extra_desc:
                    ItemFactura.objects.create(factura=factura, concepto=C.FIJO, descripcion=extra_desc[:120],
                                               monto_usd=extra_monto)
            messages.success(request, f"Factura {numero} registrada por USD {factura.total}.")
            return redirect("cobros")
    return render(request, "finanzas/factura_form.html", {
        "protocolo": protocolo, "pendientes": pendientes, "error": error,
        "cartas": CartaPago.objects.filter(protocolo=protocolo).order_by("-fecha"),
        "hoy": timezone.localdate().isoformat(), "post": request.POST,
        "marcados": set(request.POST.getlist("item")),
    })


@require_POST
@solo_direccion
def factura_cobrada(request, pk):
    factura = get_object_or_404(Factura, pk=pk, protocolo=protocolo_actual(request))
    factura.cobrada = not factura.cobrada
    factura.fecha_cobro = timezone.localdate() if factura.cobrada else None
    factura.save(update_fields=["cobrada", "fecha_cobro"])
    messages.success(request, f"Factura {factura.numero} marcada como {'cobrada' if factura.cobrada else 'pendiente de cobro'}.")
    return redirect("cobros")


@solo_direccion
def reparto(request):
    protocolo = protocolo_actual(request)
    return render(request, "finanzas/reparto.html", {
        "protocolo": protocolo, "reparto": servicios.reparto(protocolo),
        "gastos": Gasto.objects.filter(protocolo=protocolo).select_related("pagado_por"),
        "pagos": PagoMedico.objects.filter(protocolo=protocolo).select_related("medico", "pagado_por"),
    })


@solo_direccion
def gasto_nuevo(request):
    protocolo = protocolo_actual(request)
    form = GastoForm(request.POST or None, initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        gasto = form.save(commit=False)
        gasto.protocolo = protocolo
        gasto.save()
        messages.success(request, "Gasto registrado.")
        return redirect("reparto")
    return render(request, "finanzas/formulario.html", {
        "form": form, "titulo": "Registrar un gasto del estudio", "volver": "reparto",
        "ayuda": "Lo que alguien pagó de su bolsillo se le devuelve antes de repartir."})


@solo_direccion
def factura_descargar(request, pk):
    factura = get_object_or_404(Factura, pk=pk, protocolo=protocolo_actual(request))
    p = factura.protocolo
    nombre = f"Invoice {factura.numero} Protocol {p.codigo}{'_' + p.codigo_cro if p.codigo_cro else ''}.pdf"
    respuesta = HttpResponse(factura_pdf(factura), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


# ---------------------------------------------------------------- cartas de pago

@solo_direccion
def carta_subir(request):
    protocolo = protocolo_actual(request)
    error = None
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if not archivo:
            error = "Elegí el PDF de la carta de pago."
        elif archivo.size > 5 * 1024 * 1024:
            error = "El archivo pesa más de 5 MB: no parece una carta de pago."
        else:
            try:
                leida = cartas.leer(cartas.texto_de_pdf(archivo), protocolo.sitio)
            except cartas.CartaIlegible as problema:
                error = f"{problema} Si es otro formato, cargala a mano en Configuración → Cartas de pago."
            else:
                with transaction.atomic():
                    carta, nueva = CartaPago.objects.get_or_create(
                        protocolo=protocolo, request_id=leida["request_id"],
                        defaults={"fecha": leida["fecha"], "monto_usd": leida["monto"],
                                  "periodo": cartas.periodo(leida["fecha"])})
                    if not carta.items.exists():
                        ItemCarta.objects.bulk_create([
                            ItemCarta(carta=carta, secuencia=sec, codigo_paciente=codigo, nombre_visita=visita, monto_usd=monto)
                            for sec, codigo, visita, monto in leida["items"]])
                        messages.success(request, f"Carta {carta.periodo} leída: {len(leida['items'])} renglones por USD {leida['monto']}.")
                    else:
                        messages.warning(request, f"La carta {carta.request_id} ya estaba cargada: te muestro su conciliación.")
                return redirect("carta_detalle", carta.id)
    return render(request, "finanzas/carta_subir.html", {"protocolo": protocolo, "error": error})


def _numero_siguiente(protocolo):
    numeros = [int(n) for n in Factura.objects.filter(protocolo=protocolo).values_list("numero", flat=True) if n.isdigit()]
    return f"{max(numeros, default=0) + 1:03d}"


@solo_direccion
def carta_detalle(request, pk):
    protocolo = protocolo_actual(request)
    carta = get_object_or_404(CartaPago, pk=pk, protocolo=protocolo)
    filas, afuera = cartas.conciliar(carta)
    C = ItemFactura.Concepto
    listas = [f for f in filas if f["estado"] == "ok"]
    con_visita = [f["visita"] for f in filas if f["visita"] is not None]
    viaticos = [v for v in con_visita if protocolo.viatico_usd and not any(i.concepto == C.VIATICO for i in v.items_factura.all())]
    if request.method == "POST":
        que = request.POST.get("que")
        hoy = timezone.localdate()
        elegidas = [(C.VISITA, f["visita"], f["item"].monto_usd) for f in listas] if que == "visitas" else (
            [(C.VIATICO, v, protocolo.viatico_usd) for v in viaticos] if que == "viaticos" else [])
        if not elegidas:
            messages.warning(request, "No hay nada para facturar de esta carta.")
        else:
            with transaction.atomic():
                factura = Factura.objects.create(
                    protocolo=protocolo, numero=_numero_siguiente(protocolo), fecha=hoy,
                    vencimiento=hoy + timedelta(days=30), carta=carta, request_id=carta.request_id)
                for concepto, visita, monto in elegidas:
                    ItemFactura.objects.create(
                        factura=factura, concepto=concepto, visita=visita, monto_usd=monto,
                        descripcion=f"{visita.paciente.codigo} · {visita.tipo.nombre} · {C(concepto).label}")
            messages.success(request, f"Factura {factura.numero} generada por USD {factura.total}. Ya podés descargar el PDF.")
            return redirect("cobros")
    return render(request, "finanzas/carta_detalle.html", {
        "protocolo": protocolo, "carta": carta, "filas": filas, "afuera": afuera, "listas": listas, "viaticos": viaticos,
        "total_listas": sum((f["item"].monto_usd for f in listas), CERO),
        "total_viaticos": protocolo.viatico_usd * len(viaticos),
        "problemas": [f for f in filas if f["estado"] in ("falta", "monto")],
        "suma": sum((f["item"].monto_usd for f in filas), CERO),
    })
