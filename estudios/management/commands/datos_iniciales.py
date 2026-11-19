"""Carga MALBEC y el usuario inicial, SOLO si la base está vacía. Corre en cada
deploy y no pisa ni borra nada: si ya hay un protocolo cargado, no hace nada."""
from datetime import date
from decimal import Decimal as D

from django.core.management.base import BaseCommand
from django.db import transaction

from cuentas.models import Usuario
from cuentas.views import CLAVE_GENERICA
from estudios import malbec
from estudios.models import Medico, Paciente, Procedimiento, Protocolo, Realizacion, TipoVisita, Visita
from finanzas.models import CartaPago, Factura, Gasto, ItemFactura, PagoMedico, Socio


class Command(BaseCommand):
    help = "Carga inicial (protocolo MALBEC, historial y usuario de Dirección) si la base está vacía."

    @transaction.atomic
    def handle(self, *args, **opciones):
        if not Usuario.objects.filter(rol=Usuario.Rol.DIRECCION).exists():
            u = Usuario(username="jvalenzuela", first_name="Juan", last_name="Valenzuela",
                        rol=Usuario.Rol.DIRECCION, debe_cambiar_clave=True)
            u.set_password(CLAVE_GENERICA)
            u.save()
            self.stdout.write("Usuario inicial creado: jvalenzuela")
        if Protocolo.objects.exists():
            self.stdout.write("Ya hay protocolos cargados: no se toca nada.")
            return

        protocolo = Protocolo.objects.create(**malbec.PROTOCOLO)
        procs = {}
        for orden, (nombre, tarifa, sponsor) in enumerate(malbec.PROCEDIMIENTOS):
            procs[nombre] = Procedimiento.objects.create(
                protocolo=protocolo, nombre=nombre, orden=orden, tarifa_usd=D(tarifa), precio_sponsor_usd=D(sponsor))
        tipos = {}
        for orden, (nombre, semana, precio, esperados) in enumerate(malbec.tipos_visita()):
            t = TipoVisita.objects.create(protocolo=protocolo, nombre=nombre, orden=orden, semana=semana, precio_usd=D(precio))
            t.procedimientos.set([procs[n] for n in esperados])
            tipos[nombre] = t
        medicos = {clave: Medico.objects.get_or_create(nombre=nombre, defaults={"externo": clave in malbec.EXTERNOS})[0]
                   for clave, nombre in malbec.MEDICOS.items()}
        por_nombre = {m.nombre: m for m in medicos.values()}
        for nombre in malbec.SOLO_DERIVAN:
            por_nombre[nombre] = Medico.objects.get_or_create(nombre=nombre, defaults={"hace_procedimientos": False})[0]
        pacientes = {codigo: Paciente.objects.create(protocolo=protocolo, codigo=codigo, estado=estado,
                                                     derivado_por=por_nombre.get(derivador), nota=nota)
                     for codigo, (estado, derivador, nota) in malbec.PACIENTES.items()}

        visitas = {}
        for tipo, fecha, codigo, quienes, completa in malbec.VISITAS:
            v = Visita.objects.create(paciente=pacientes[codigo], tipo=tipos[tipo], fecha=fecha, completa=completa)
            if completa:
                visitas[(codigo, tipo)] = v
            for nombre, clave in quienes.items():
                m = medicos[clave]
                Realizacion.objects.create(visita=v, procedimiento=procs[nombre], medico=m,
                                           monto_usd=0 if m.externo else procs[nombre].tarifa_usd)

        socios = {nombre: Socio.objects.create(nombre=nombre, porcentaje=D(pct), es_comision=comision, orden=i)
                  for i, (nombre, pct, comision) in enumerate(malbec.SOCIOS)}
        for clave, periodo, usd, cotizacion, quien in malbec.PAGOS:
            PagoMedico.objects.create(protocolo=protocolo, medico=medicos[clave], periodo=periodo, monto_usd=D(usd),
                                      cotizacion=D(cotizacion) if cotizacion else None, pagado_por=socios[quien],
                                      nota="Cargado desde la planilla de balance")
        for concepto, usd, quien in malbec.GASTOS:
            Gasto.objects.create(protocolo=protocolo, concepto=concepto, monto_usd=D(usd), pagado_por=socios[quien])

        cartas = {periodo: CartaPago.objects.create(protocolo=protocolo, periodo=periodo, fecha=date.fromisoformat(fecha),
                                                    request_id=rid, monto_usd=D(monto))
                  for periodo, fecha, rid, monto in malbec.CARTAS}
        C = ItemFactura.Concepto
        for numero, fecha, vence, carta, rid, cobrada, de_visitas, de_viaticos, fijo in malbec.FACTURAS:
            f = Factura.objects.create(protocolo=protocolo, numero=numero, fecha=date.fromisoformat(fecha),
                                       vencimiento=date.fromisoformat(vence), carta=cartas.get(carta),
                                       request_id=rid, cobrada=cobrada)
            for codigo, tipo in de_visitas:
                v = visitas[(codigo, tipo)]
                ItemFactura.objects.create(factura=f, concepto=C.VISITA, visita=v, monto_usd=v.tipo.precio_usd,
                                           descripcion=f"{codigo} · {tipo} · Visita")
            for codigo, tipo in de_viaticos:
                ItemFactura.objects.create(factura=f, concepto=C.VIATICO, visita=visitas[(codigo, tipo)],
                                           monto_usd=protocolo.viatico_usd, descripcion=f"{codigo} · {tipo} · Viático")
            if fijo:
                ItemFactura.objects.create(factura=f, concepto=C.FIJO, descripcion=fijo[0], monto_usd=D(fijo[1]))
        self.stdout.write(self.style.SUCCESS(
            f"MALBEC cargado: {len(pacientes)} pacientes, {Visita.objects.count()} visitas, "
            f"{Realizacion.objects.count()} procedimientos, {Factura.objects.count()} facturas."))
