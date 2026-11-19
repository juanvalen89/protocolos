"""La coordinadora carga y no ve números; los cálculos coinciden con las planillas."""
from datetime import date
from decimal import Decimal as D

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Usuario
from estudios.models import Medico, Paciente, Protocolo, Realizacion, TipoVisita, Visita
from finanzas import servicios

PANTALLAS_CON_DINERO = ["tablero", "medicos", "pago_nuevo", "cobros", "factura_nueva", "reparto", "gasto_nuevo",
                        "protocolo_subir", "protocolo_documentos"]


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("datos_iniciales", verbosity=0)
        cls.protocolo = Protocolo.objects.get()
        cls.coordinadora = Usuario.objects.create_user("coordinadora", password="x", rol=Usuario.Rol.COORDINADORA)
        cls.direccion = Usuario.objects.get(username="jvalenzuela")
        cls.direccion.debe_cambiar_clave = False
        cls.direccion.save()


class CoordinadoraSinNumeros(Base):
    def setUp(self):
        self.client.force_login(self.coordinadora)

    def test_no_entra_a_ninguna_pantalla_con_dinero(self):
        for nombre in PANTALLAS_CON_DINERO:
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)
        self.assertEqual(self.client.get(reverse("medico_detalle", args=[Medico.objects.first().id])).status_code, 403)
        self.assertEqual(self.client.post(reverse("factura_cobrada", args=[1])).status_code, 403)
        self.assertNotEqual(self.client.get("/administracion/").status_code, 200)

    def test_sus_pantallas_no_muestran_importes(self):
        paciente = Paciente.objects.get(codigo="312-21165")
        tipo = TipoVisita.objects.get(nombre="Week 16")
        visita = paciente.visitas.first()
        urls = [reverse("pacientes"), reverse("paciente_nuevo"), reverse("paciente_editar", args=[paciente.id]),
                reverse("elegir_visita", args=[paciente.id]), reverse("visita_nueva", args=[paciente.id, tipo.id]),
                reverse("visita_editar", args=[visita.id])]
        for url in urls:
            html = self.client.get(url, follow=True).content.decode()
            for prohibido in ["USD", "2.896", "2896", "2.535", "tarifa", "Tablero", "Reparto", "Cobros", "Schlottman"]:
                self.assertNotIn(prohibido, html, f"{prohibido!r} en {url}")

    def test_inicio_la_lleva_a_la_carga(self):
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("pacientes"))

    def test_carga_una_visita_y_el_importe_se_calcula_solo(self):
        paciente = Paciente.objects.get(codigo="312-21165")
        tipo = TipoVisita.objects.get(nombre="Week 16")
        procs = {p.nombre: p for p in self.protocolo.procedimientos.all()}
        grundy, palacio = Medico.objects.get(nombre="Grundy"), Medico.objects.get(nombre="Palacio")
        datos = {"fecha": "2026-10-13", f"medico_{procs['AV'].id}": grundy.id, f"medico_{procs['OCT'].id}": grundy.id,
                 f"medico_{procs['SI (médico)'].id}": palacio.id, f"medico_{procs['Inyección'].id}": palacio.id}
        self.assertRedirects(self.client.post(reverse("visita_nueva", args=[paciente.id, tipo.id]), datos), reverse("pacientes"))
        visita = Visita.objects.get(paciente=paciente, tipo=tipo)
        self.assertEqual(visita.cargada_por, self.coordinadora)
        self.assertEqual(sum(r.monto_usd for r in visita.realizaciones.all()), D("355"))   # 25 + 30 + 150 + 150
        # Corregir: saca la inyección y cambia quién hizo la AV.
        datos.pop(f"medico_{procs['Inyección'].id}")
        datos[f"medico_{procs['AV'].id}"] = palacio.id
        self.client.post(reverse("visita_editar", args=[visita.id]), datos)
        self.assertEqual(visita.realizaciones.count(), 3)
        self.assertEqual(Realizacion.objects.get(visita=visita, procedimiento=procs["AV"]).medico, palacio)

    def test_no_acepta_fecha_futura(self):
        paciente = Paciente.objects.get(codigo="312-21165")
        tipo = TipoVisita.objects.get(nombre="Week 16")
        r = self.client.post(reverse("visita_nueva", args=[paciente.id, tipo.id]), {"fecha": "2099-01-01"})
        self.assertContains(r, "no puede ser futura")
        self.assertFalse(Visita.objects.filter(paciente=paciente, tipo=tipo).exists())


class CalculosContraLasPlanillas(Base):
    def test_reparto_igual_a_la_planilla_de_balance(self):
        r = servicios.reparto(self.protocolo)
        self.assertEqual(r["cobrado"], D("35365.83"))
        self.assertEqual(r["neto"], D("22485.83"))
        partes = {f["socio"].nombre: (f["parte"], f["total"]) for f in r["filas"]}
        self.assertEqual(partes["Schlottman"], (D("2248.58"), D("2248.58")))
        self.assertEqual(partes["Palacio"], (D("10118.62"), D("17928.62")))
        self.assertEqual(partes["Rosendi"], (D("8094.90"), D("13164.90")))
        self.assertEqual(partes["Loria"], (D("2023.72"), D("2023.72")))
        self.assertEqual(sum(t for _, t in partes.values()), D("35365.82"))   # un centavo de redondeo

    def test_liquidacion_de_palacio_igual_a_la_planilla(self):
        # Solo procedimientos: las derivaciones van en su propio renglón.
        meses = {(m["anio"], m["mes"]): {f["medico"].nombre: f["total"] - f["por_visita"].get("Derivación", 0)
                                         for f in m["filas"]}
                 for m in servicios.detalle_por_mes(self.protocolo)}
        junio = {f["medico"].nombre: f["por_visita"] for m in servicios.detalle_por_mes(self.protocolo)
                 if (m["anio"], m["mes"]) == (2026, 6) for f in m["filas"]}
        self.assertEqual(junio["Palacio"]["Derivación"], D("2000"))
        self.assertEqual(junio["Stortini"], {"Derivación": D("1000")})
        self.assertEqual(meses[(2026, 6)]["Palacio"], D("2360"))
        self.assertEqual(meses[(2026, 7)]["Palacio"], D("900"))
        self.assertEqual(meses[(2026, 8)]["Palacio"], D("900"))
        self.assertEqual(meses[(2026, 9)]["Palacio"], D("650"))
        self.assertEqual(meses[(2026, 6)]["Silveyra"], D("700"))

    def test_derivaciones_mil_dolares_al_entrar_al_estudio(self):
        saldos = {x["medico"].nombre: x for x in servicios.saldos_medicos(self.protocolo)}
        # Palacio derivó 3 que entraron (21165, 21185, 21787): 3.000, ya cobrados según el balance.
        self.assertEqual(saldos["Palacio"]["devengado"], D("8210"))
        self.assertEqual(saldos["Palacio"]["saldo"], D("400"))
        self.assertEqual(saldos["Stortini"]["saldo"], D("1000"))
        self.assertEqual(saldos["Cenoz"]["saldo"], D("1000"))
        self.assertNotIn("Troncoso", saldos)   # su paciente todavía está en screening

    def test_quien_solo_deriva_no_aparece_en_la_carga(self):
        self.client.force_login(self.coordinadora)
        paciente = Paciente.objects.get(codigo="312-21165")
        tipo = TipoVisita.objects.get(nombre="Week 16")
        html = self.client.get(reverse("visita_nueva", args=[paciente.id, tipo.id])).content.decode()
        self.assertIn("Grundy", html)
        self.assertNotIn("Stortini", html)
        # La coordinadora anota un derivador nuevo por nombre: se crea como médico que solo deriva.
        self.client.post(reverse("paciente_nuevo"), {"codigo": "312-30000", "estado": "screening", "derivador": "  gómez "})
        nuevo = Paciente.objects.get(codigo="312-30000")
        self.assertEqual(nuevo.derivado_por.nombre, "Gómez")
        self.assertFalse(nuevo.derivado_por.hace_procedimientos)

    def test_facturas_y_pendientes(self):
        f = servicios.resumen_facturas(self.protocolo, date(2026, 11, 18))
        self.assertEqual(f["por_cobrar"], D("21804.00"))
        self.assertEqual(f["vencido"], D("21804.00"))
        self.assertEqual({x.numero for x in f["facturas"] if x.request_id_no_coincide}, {"004", "005"})
        p = servicios.pendientes_de_facturar(self.protocolo)
        self.assertEqual(p["total_visitas"], D("29738.82"))
        self.assertEqual(p["total_viaticos"], D("1100"))
        self.assertEqual(p["total_condicionales"], D("3640"))

    def test_visitas_del_cronograma_sin_cargar(self):
        paciente = Paciente.objects.prefetch_related("visitas__tipo").get(codigo="312-21165")
        esperadas = {t.nombre: atrasada for t, _, atrasada in paciente.visitas_esperadas(date(2026, 11, 18))}
        self.assertEqual(esperadas, {"Week 16": True, "Week 20": True, "Week 24": False})


class CoordinadorasIniciales(Base):
    def test_caro_y_ceci_entran_solo_a_la_carga(self):
        for usuario in ["caro", "ceci"]:
            u = Usuario.objects.get(username=usuario)
            self.assertFalse(u.ve_numeros)
            self.assertFalse(u.is_staff)
            self.assertTrue(u.debe_cambiar_clave)
            self.assertTrue(self.client.login(username=usuario, password="Loria.Protocolos.2026"))
            self.assertRedirects(self.client.get(reverse("pacientes")), reverse("password_change"))
            u.debe_cambiar_clave = False
            u.save()
            self.assertEqual(self.client.get(reverse("pacientes")).status_code, 200)
            self.assertEqual(self.client.get(reverse("tablero")).status_code, 403)


class DireccionVeTodo(Base):
    def test_todas_las_pantallas_abren(self):
        self.client.force_login(self.direccion)
        for nombre in PANTALLAS_CON_DINERO + ["pacientes"]:
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)
        self.assertEqual(self.client.get(reverse("medico_detalle", args=[Medico.objects.first().id])).status_code, 200)
        self.assertContains(self.client.get(reverse("tablero")), "USD 35.365,83")

    def test_registrar_factura_y_cobrarla(self):
        self.client.force_login(self.direccion)
        p = servicios.pendientes_de_facturar(self.protocolo)
        elegidos = [f"v:{x['visita'].id}" for x in p["visitas"]]
        r = self.client.post(reverse("factura_nueva"), {"numero": "006", "fecha": "2027-01-20", "vencimiento": "2027-02-20", "item": elegidos})
        self.assertRedirects(r, reverse("cobros"))
        factura = self.protocolo.facturas.get(numero="006")
        self.assertEqual(factura.total, D("29738.82"))
        self.assertEqual(servicios.pendientes_de_facturar(self.protocolo)["total_visitas"], D("0"))
        self.client.post(reverse("factura_cobrada", args=[factura.id]))
        self.assertEqual(servicios.reparto(self.protocolo)["cobrado"], D("35365.83") + D("29738.82"))

    def test_pago_en_pesos_calcula_el_total(self):
        self.client.force_login(self.direccion)
        grundy = Medico.objects.get(nombre="Grundy")
        socio = self.protocolo.pagos_medicos.first().pagado_por
        self.client.post(reverse("pago_nuevo"), {"medico": grundy.id, "fecha": "2026-11-18", "periodo": "agosto 2026",
                                                 "monto_usd": "165", "cotizacion": "1535", "pagado_por": socio.id})
        pago = grundy.pagos.get(periodo="agosto 2026")
        self.assertEqual(pago.monto_ars, D("253275.00"))

    def test_clave_generica_obliga_a_cambiarla(self):
        u = Usuario.objects.get(username="jvalenzuela")
        u.debe_cambiar_clave = True
        u.save()
        self.client.force_login(u)
        self.assertRedirects(self.client.get(reverse("tablero")), reverse("password_change"))
