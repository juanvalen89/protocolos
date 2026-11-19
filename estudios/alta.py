"""Alta de un protocolo nuevo a partir del presupuesto del sitio. Solo Dirección."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cuentas.permisos import solo_direccion

from . import presupuesto
from .views import protocolo_actual
from .models import Documento, Procedimiento, Protocolo, TipoVisita

_SESION = "presupuesto_leido"
_MAXIMO_PDF = 25 * 1024 * 1024


def _guardar_documento(archivo, tipo, protocolo=None):
    archivo.seek(0)
    contenido = archivo.read()
    return Documento.objects.create(protocolo=protocolo, tipo=tipo, nombre=archivo.name[:160], contenido=contenido,
                                    peso=len(contenido))


def _es_pdf(archivo):
    archivo.seek(0)
    cabeza = archivo.read(5)
    archivo.seek(0)
    return cabeza == b"%PDF-"


def _leer_cartas(archivos, sitio, codigo_cro):
    """Lee las cartas de pago subidas junto con el presupuesto.
    Devuelve (cartas aptas para la sesión, código de la CRO, error)."""
    from finanzas import cartas
    leidas, vistos = [], set()
    for archivo in archivos:
        if archivo.size > _MAXIMO_PDF:
            return [], codigo_cro, f"{archivo.name} pesa más de 25 MB: no parece una carta de pago."
        try:
            c = cartas.leer(cartas.texto_de_pdf(archivo), sitio)
        except cartas.CartaIlegible as problema:
            return [], codigo_cro, f"{archivo.name}: {problema}"
        if c["protocolo_cro"]:
            if codigo_cro and c["protocolo_cro"].lower() != codigo_cro.replace(" ", "").lower():
                return [], codigo_cro, (f"{archivo.name} es una carta del estudio {c['protocolo_cro']}, "
                                        f"y el código de la CRO de este protocolo es {codigo_cro}.")
            codigo_cro = codigo_cro or c["protocolo_cro"]
        if c["request_id"] in vistos:
            continue
        vistos.add(c["request_id"])
        suma = sum((i[3] for i in c["items"]), Decimal("0"))
        leidas.append({"archivo": archivo.name, "request_id": c["request_id"], "fecha": c["fecha"].isoformat(),
                       "periodo": cartas.periodo(c["fecha"]), "monto": str(c["monto"]), "suma": str(suma),
                       "cierra": suma == c["monto"], "items": [[s, cod, n, str(m)] for s, cod, n, m in c["items"]],
                       "documento": _guardar_documento(archivo, Documento.Tipo.CARTA).id})
    leidas.sort(key=lambda c: c["fecha"])
    return leidas, codigo_cro, None


def _comparar_con_presupuesto(leido):
    """Cuenta, por carta, las visitas cuyo importe no es el del presupuesto."""
    precios = {v["nombre"].replace(" ", "").lower(): Decimal(v["precio"]) for v in leido["visitas"]}
    for c in leido["cartas"]:
        visitas = [i for i in c["items"] if i[0]]
        c["visitas"] = len(visitas)
        c["ajustes"] = len(c["items"]) - len(visitas)
        c["distintas"] = [f"{i[1]} {i[2]} (USD {i[3]})" for i in visitas
                          if precios.get(i[2].replace(" ", "").lower()) != Decimal(i[3])]


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
            pdf = request.FILES.get("protocolo_pdf")
            pdfs_cartas = request.FILES.getlist("cartas")
            try:
                leido = presupuesto.leer(archivo)
            except presupuesto.PresupuestoIlegible as problema:
                error = str(problema)
            else:
                if pdf and (pdf.size > _MAXIMO_PDF or not _es_pdf(pdf)):
                    error = "El protocolo tiene que ser un PDF de hasta 25 MB."
                elif len(pdfs_cartas) > 20:
                    error = "Subí hasta 20 cartas de pago por vez; el resto se sube después en Cobros."
            if not error:
                # Lo que quedó de un intento anterior que no se terminó.
                Documento.objects.filter(protocolo=None, subido__lt=timezone.now() - timedelta(days=1)).delete()
                with transaction.atomic():
                    leidas, codigo_cro, error = _leer_cartas(pdfs_cartas, leido["sitio"],
                                                             request.POST.get("codigo_cro", "").strip())
                    if error:
                        transaction.set_rollback(True)
                    else:
                        documentos = [_guardar_documento(archivo, Documento.Tipo.PRESUPUESTO).id]
                        if pdf:
                            documentos.append(_guardar_documento(pdf, Documento.Tipo.PROTOCOLO).id)
                        leido.update(nombre=nombre, base=request.POST.get("base") or "", codigo_cro=codigo_cro,
                                     cartas=leidas, documentos=documentos + [c["documento"] for c in leidas],
                                     protocolo_pdf=pdf.name if pdf else "")
                        _comparar_con_presupuesto(leido)
            if not error:
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
            Documento.objects.filter(protocolo=None, id__in=leido.get("documentos", [])).update(protocolo=protocolo)
            from finanzas import cartas
            for c in leido.get("cartas", []):
                cartas.guardar(protocolo, {
                    "request_id": c["request_id"], "fecha": date.fromisoformat(c["fecha"]), "monto": Decimal(c["monto"]),
                    "items": [(s, cod, n, Decimal(m)) for s, cod, n, m in c["items"]]})
        del request.session[_SESION]
        request.session["protocolo_id"] = protocolo.id
        con_cartas = f" y {len(leido['cartas'])} carta{'s' if len(leido['cartas']) != 1 else ''} de pago" if leido.get("cartas") else ""
        messages.success(request, f"Protocolo {protocolo.nombre} creado con {len(leido['visitas'])} visitas{con_cartas}. "
                                  "Revisá las tarifas de los médicos en Configuración → Protocolos.")
        return redirect("tablero")
    return render(request, "estudios/protocolo_revisar.html", {"leido": leido, "base": base, "existe": existe})


@solo_direccion
def protocolo_documentos(request):
    """Archivos guardados del estudio actual, y alta de alguno más."""
    protocolo = protocolo_actual(request)
    error = None
    if request.method == "POST":
        archivo, tipo = request.FILES.get("archivo"), request.POST.get("tipo")
        if not archivo or tipo not in Documento.Tipo.values:
            error = "Elegí el archivo y qué tipo de documento es."
        elif archivo.size > _MAXIMO_PDF:
            error = "El archivo pesa más de 25 MB."
        else:
            _guardar_documento(archivo, tipo, protocolo)
            messages.success(request, f"{archivo.name} guardado.")
            return redirect("protocolo_documentos")
    return render(request, "estudios/protocolo_documentos.html", {
        "protocolo": protocolo, "error": error, "tipos": Documento.Tipo.choices,
        "documentos": Documento.objects.filter(protocolo=protocolo).defer("contenido")})


@solo_direccion
def documento_descargar(request, pk):
    documento = get_object_or_404(Documento, pk=pk, protocolo=protocolo_actual(request))
    es_pdf = documento.nombre.lower().endswith(".pdf")
    respuesta = HttpResponse(bytes(documento.contenido), content_type="application/pdf" if es_pdf else "application/octet-stream")
    nombre = documento.nombre.replace('"', "").encode("ascii", "ignore").decode() or "documento"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta
