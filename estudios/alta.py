"""Alta de un protocolo nuevo a partir del presupuesto del sitio. Solo Dirección."""
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from cuentas.permisos import solo_direccion

from . import presupuesto
from .models import Procedimiento, Protocolo, TipoVisita

_SESION = "presupuesto_leido"


@solo_direccion
def protocolo_subir(request):
    error = None
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        nombre = " ".join(request.POST.get("nombre", "").split())
        if not archivo or not nombre:
            error = "Faltan el nombre corto del estudio o el archivo del presupuesto."
        elif archivo.size > 5 * 1024 * 1024:
            error = "El archivo pesa más de 5 MB: no parece un presupuesto."
        else:
            try:
                leido = presupuesto.leer(archivo)
            except presupuesto.PresupuestoIlegible as problema:
                error = str(problema)
            else:
                leido.update(nombre=nombre, base=request.POST.get("base") or "", codigo_cro=request.POST.get("codigo_cro", "").strip())
                request.session[_SESION] = leido
                return redirect("protocolo_revisar")
    return render(request, "estudios/protocolo_subir.html", {"error": error, "protocolos": Protocolo.objects.all()})


@solo_direccion
def protocolo_revisar(request):
    leido = request.session.get(_SESION)
    if not leido:
        return redirect("protocolo_subir")
    base = Protocolo.objects.filter(pk=leido["base"] or 0).first()
    existe = Protocolo.objects.filter(codigo=leido["codigo"]).exists()
    if request.method == "POST" and not existe and leido["codigo"]:
        with transaction.atomic():
            protocolo = Protocolo.objects.create(
                codigo=leido["codigo"], nombre=leido["nombre"], codigo_cro=leido["codigo_cro"], sponsor=leido["sponsor"],
                sitio=leido["sitio"], investigador=leido["investigador"], viatico_usd=Decimal(leido["viatico"]),
                cro=base.cro if base else "", derivacion_usd=base.derivacion_usd if base else 0,
                datos_sitio=base.datos_sitio if base else "", datos_bancarios=base.datos_bancarios if base else "")
            procs = {}
            if base:
                for p in base.procedimientos.all():
                    procs[p.nombre] = Procedimiento.objects.create(protocolo=protocolo, nombre=p.nombre, orden=p.orden,
                                                                   tarifa_usd=p.tarifa_usd)
            for visita in leido["visitas"]:
                for nombre in visita["esperados"]:
                    if nombre not in procs:
                        procs[nombre] = Procedimiento.objects.create(protocolo=protocolo, nombre=nombre, orden=len(procs))
            for nombre, precio in leido["condicionales"].items():
                if nombre not in procs:
                    procs[nombre] = Procedimiento.objects.create(protocolo=protocolo, nombre=nombre, orden=len(procs))
                procs[nombre].precio_sponsor_usd = Decimal(precio)
                procs[nombre].save(update_fields=["precio_sponsor_usd"])
            for orden, visita in enumerate(leido["visitas"]):
                tipo = TipoVisita.objects.create(protocolo=protocolo, nombre=visita["nombre"], orden=orden,
                                                 semana=visita["semana"], precio_usd=Decimal(visita["precio"]))
                tipo.procedimientos.set([procs[n] for n in visita["esperados"]])
            TipoVisita.objects.create(protocolo=protocolo, nombre="No programada", orden=len(leido["visitas"]))
        del request.session[_SESION]
        request.session["protocolo_id"] = protocolo.id
        messages.success(request, f"Protocolo {protocolo.nombre} creado con {len(leido['visitas'])} visitas. "
                                  "Revisá las tarifas de los médicos en Configuración → Protocolos.")
        return redirect("tablero")
    return render(request, "estudios/protocolo_revisar.html", {"leido": leido, "base": base, "existe": existe})
