"""Carga: pacientes, visitas y quién hizo cada procedimiento.

Ninguna vista de este archivo manda importes a la plantilla: es lo único que
ve la coordinadora (verificado en estudios/tests.py)."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PacienteForm
from .models import Medico, Paciente, Protocolo, Realizacion, TipoVisita, Visita


def protocolo_actual(request):
    """El protocolo con el que se está trabajando (se elige en el encabezado)."""
    pid = request.session.get("protocolo_id")
    activos = Protocolo.objects.filter(activo=True)
    return activos.filter(pk=pid).first() or activos.first()


@login_required
def inicio(request):
    return redirect("tablero" if request.user.ve_numeros else "pacientes")


@require_POST
@login_required
def cambiar_protocolo(request):
    p = get_object_or_404(Protocolo, pk=request.POST.get("protocolo"), activo=True)
    request.session["protocolo_id"] = p.id
    return redirect("inicio")


@login_required
def pacientes(request):
    protocolo = protocolo_actual(request)
    hoy = timezone.localdate()
    filas, atrasadas = [], 0
    if protocolo:
        qs = (Paciente.objects.filter(protocolo=protocolo)
              .prefetch_related("visitas__tipo", "protocolo__tipos_visita"))
        for p in qs:
            esperadas = p.visitas_esperadas(hoy)
            atrasadas += sum(1 for e in esperadas if e[2])
            filas.append({"paciente": p, "visitas": sorted(p.visitas.all(), key=lambda v: (v.fecha, v.id)),
                          "esperadas": esperadas})
        orden = {"activo": 0, "screening": 1, "falla": 2, "finalizado": 3}
        filas.sort(key=lambda f: (orden[f["paciente"].estado], f["paciente"].codigo))
    return render(request, "estudios/pacientes.html",
                  {"protocolo": protocolo, "filas": filas, "atrasadas": atrasadas})


@login_required
def paciente_form(request, pk=None):
    protocolo = protocolo_actual(request)
    paciente = get_object_or_404(Paciente, pk=pk, protocolo=protocolo) if pk else Paciente(protocolo=protocolo)
    form = PacienteForm(request.POST or None, instance=paciente)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Paciente {paciente.codigo} guardado.")
        return redirect("pacientes")
    return render(request, "estudios/paciente_form.html", {"form": form, "paciente": paciente, "protocolo": protocolo})


@login_required
def elegir_visita(request, pk):
    """Paso 1 de la carga: qué visita del cronograma se hizo."""
    protocolo = protocolo_actual(request)
    paciente = get_object_or_404(Paciente, pk=pk, protocolo=protocolo)
    hechas = {v.tipo_id for v in paciente.visitas.all()}
    tipos = [{"tipo": t, "hecha": t.id in hechas} for t in protocolo.tipos_visita.all()]
    return render(request, "estudios/elegir_visita.html", {"paciente": paciente, "tipos": tipos, "protocolo": protocolo})


@login_required
def visita_form(request, paciente_id=None, tipo_id=None, pk=None):
    """Paso 2: fecha y, por cada procedimiento, qué médico lo hizo."""
    protocolo = protocolo_actual(request)
    if pk:
        visita = get_object_or_404(Visita, pk=pk, paciente__protocolo=protocolo)
        paciente, tipo = visita.paciente, visita.tipo
    else:
        paciente = get_object_or_404(Paciente, pk=paciente_id, protocolo=protocolo)
        tipo = get_object_or_404(TipoVisita, pk=tipo_id, protocolo=protocolo)
        visita = None
    medicos = list(Medico.objects.filter(activo=True))
    actuales = {r.procedimiento_id: r for r in visita.realizaciones.all()} if visita else {}
    esperados_ids = set(tipo.procedimientos.values_list("id", flat=True))
    error = None

    if request.method == "POST":
        try:
            fecha = date.fromisoformat(request.POST.get("fecha", ""))
        except ValueError:
            fecha, error = None, "Falta la fecha de la visita."
        if fecha and fecha > timezone.localdate():
            error = "La fecha no puede ser futura."
        if not error:
            with transaction.atomic():
                if visita is None:
                    visita = Visita(paciente=paciente, tipo=tipo, cargada_por=request.user)
                visita.fecha = fecha
                visita.completa = request.POST.get("parcial") != "1"
                visita.nota = request.POST.get("nota", "").strip()[:200]
                visita.save()
                validos = {str(m.id): m for m in medicos}
                for proc in protocolo.procedimientos.all():
                    elegido = validos.get(request.POST.get(f"medico_{proc.id}", ""))
                    actual = actuales.get(proc.id)
                    if elegido is None:
                        if actual and not actual.items_factura.exists():
                            actual.delete()
                        continue
                    if actual:
                        if actual.medico_id != elegido.id:
                            actual.medico = elegido
                            actual.monto_usd = 0 if elegido.externo else proc.tarifa_usd
                            actual.save()
                    else:
                        Realizacion.objects.create(
                            visita=visita, procedimiento=proc, medico=elegido,
                            monto_usd=0 if elegido.externo else proc.tarifa_usd)
                # Con el Day 1 el paciente pasa a estar en el estudio.
                if tipo.semana == 0 and paciente.estado == Paciente.Estado.SCREENING:
                    paciente.estado = Paciente.Estado.ACTIVO
                    paciente.save(update_fields=["estado"])
            messages.success(request, f"Visita {tipo.nombre} de {paciente.codigo} guardada.")
            return redirect("pacientes")

    filas = []
    for proc in protocolo.procedimientos.all():
        actual = actuales.get(proc.id)
        elegido = request.POST.get(f"medico_{proc.id}") if request.method == "POST" else (
            str(actual.medico_id) if actual else "")
        filas.append({"proc": proc, "elegido": elegido,
                      "esperado": proc.id in esperados_ids or bool(actual)})
    return render(request, "estudios/visita_form.html", {
        "protocolo": protocolo, "paciente": paciente, "tipo": tipo, "visita": visita, "medicos": medicos,
        "esperados": [f for f in filas if f["esperado"]], "otros": [f for f in filas if not f["esperado"]],
        "fecha": request.POST.get("fecha") or (visita.fecha.isoformat() if visita else ""),
        "parcial": (request.POST.get("parcial") == "1") if request.method == "POST" else bool(visita and not visita.completa),
        "nota": request.POST.get("nota") if request.method == "POST" else (visita.nota if visita else ""),
        "error": error,
    })
