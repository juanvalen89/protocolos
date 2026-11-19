"""Carta de pago, factura en PDF, alta de protocolo desde el presupuesto y cotización."""
from datetime import date
from decimal import Decimal as D
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Usuario
from estudios import presupuesto
from estudios.models import Paciente, Protocolo, TipoVisita, Visita
from finanzas import cartas, cotizacion, servicios
from finanzas.models import CartaPago, Factura

PRUEBAS = Path(__file__).parent / "pruebas"


def pdf_con_texto(renglones):
    from reportlab.pdfgen import canvas
    salida = BytesIO()
    c = canvas.Canvas(salida)
    for n, texto in enumerate(renglones):
        c.drawString(40, 800 - 16 * n, texto)
    c.save()
    return salida.getvalue()


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("datos_iniciales", verbosity=0)
        cls.protocolo = Protocolo.objects.get()
        cls.direccion = Usuario.objects.get(username="jvalenzuela")
        cls.direccion.debe_cambiar_clave = False
        cls.direccion.save()

    def setUp(self):
        self.client.force_login(self.direccion)


class LecturaDeCartas(Base):
    def test_lee_las_dos_cartas_reales(self):
        q3 = cartas.leer((PRUEBAS / "carta_q3.txt").read_text(), "312")
        self.assertEqual((q3["request_id"], q3["fecha"], q3["monto"]), ("PYRQ-004039", date(2026, 10, 13), D("20904.00")))
        self.assertEqual(len(q3["items"]), 9)
        self.assertEqual(q3["items"][0], ("4", "312-21165", "Week 4", D("2535.00")))
        self.assertEqual(q3["items"][-1], ("6", "312-21197", "Week 12", D("1898.00")))
        self.assertEqual(sum(i[3] for i in q3["items"]), q3["monto"])
        q2 = cartas.leer((PRUEBAS / "carta_q2.txt").read_text(), "312")
        self.assertEqual((q2["request_id"], q2["fecha"], q2["monto"]), ("PYRQ-003462", date(2026, 7, 14), D("23969.43")))
        self.assertEqual([i[2] for i in q2["items"][:3]], ["Screening", "Day 1", "Week 1"])
        self.assertEqual(sum(i[3] for i in q2["items"]), q2["monto"])
        self.assertEqual((cartas.periodo(q3["fecha"]), cartas.periodo(q2["fecha"])), ("Q3 2026", "Q2 2026"))

    def test_carta_en_dos_paginas_con_ajustes_negativos(self):
        """Formato de las cartas de BAROLO: la tabla sigue en la página 2 y trae descuentos entre paréntesis."""
        texto = "\n".join([
            "Invoice Request Form", "Request ID: PYRQ-003071", "13-Apr-2026", "Site #: 312",
            "Re: Protocol #: EYEB1010 (Barolo)", "Protocol Entitled: A Randomized Study",
            "Dear Dr. Rosendi", "payable items in the amount of USD 7,709.00. Below",
            "Visit Sequence Subject Name Amount",
            "5 312-13260 Week 12 USD 3,263.00", "6 312-13260 Week 16* USD 2,548.00",
            "Invoice Request Form", "Request ID: PYRQ-003071",
            "10 312-13260 Week 20* USD 2,548.00",
            "   312-13260 Week 16 Post-IVT IOP", "Reconciliation* (USD 65.00)",
            "   312-13260", "Week 20 IVT of study drug", "Reconciliation*", "", "(USD 585.00)",
            "*Reconciliation concerns Subject 312-13260 visit W16 and W20 completed without IP injection",
            "Please include the following items"])
        carta = cartas.leer(texto, "312")
        self.assertEqual((carta["request_id"], carta["monto"], carta["protocolo_cro"]), ("PYRQ-003071", D("7709.00"), "EYEB1010"))
        self.assertEqual(carta["items"], [
            ("5", "312-13260", "Week 12", D("3263.00")), ("6", "312-13260", "Week 16", D("2548.00")),
            ("10", "312-13260", "Week 20", D("2548.00")),
            ("", "312-13260", "Ajuste: Week 16 Post-IVT IOP", D("-65.00")),
            ("", "312-13260", "Ajuste: Week 20 IVT of study drug", D("-585.00"))])
        self.assertEqual(sum(i[3] for i in carta["items"]), carta["monto"])

    def test_los_ajustes_van_en_la_factura_de_visitas(self):
        renglones = ["Request ID: PYRQ-005001", "14-Jan-2027", "in the amount of USD 5,506.81", "Sequence Subject Name Amount",
                     "1 312-21787 Screening USD 2,896.40", "2 312-21787 Day 1 USD 3,195.41",
                     "312-21787 Ad Hoc (USD 585.00)", "Please include"]
        self.client.post(reverse("carta_subir"), {"archivo": SimpleUploadedFile("a.pdf", pdf_con_texto(renglones))})
        carta = CartaPago.objects.get(request_id="PYRQ-005001")
        filas, _ = cartas.conciliar(carta)
        self.assertEqual([f["estado"] for f in filas], ["ok", "ok", "ajuste"])
        self.assertNotContains(self.client.get(reverse("carta_detalle", args=[carta.id])), "Los renglones suman")
        self.client.post(reverse("carta_detalle", args=[carta.id]), {"que": "visitas"})
        factura = Factura.objects.get(carta=carta)
        self.assertEqual(factura.total, carta.monto_usd)
        self.assertEqual(cartas.conciliar(carta)[0][2]["estado"], "ajuste_facturado")
        self.assertEqual(self.client.get(reverse("factura_pdf", args=[factura.id])).status_code, 200)

    def test_no_acepta_la_carta_de_otro_estudio(self):
        renglones = ["Request ID: PYRQ-003481", "14-Jul-2026", "Re: Protocol #: EYEB1010 (Barolo)", "Protocol Entitled: X",
                     "in the amount of USD 2,548.00", "Sequence Subject Name Amount", "9 312-13256 Week 28 USD 2,548.00", "Please include"]
        r = self.client.post(reverse("carta_subir"), {"archivo": SimpleUploadedFile("b.pdf", pdf_con_texto(renglones))})
        self.assertContains(r, "Esta carta es del estudio EYEB1010")
        self.assertFalse(CartaPago.objects.filter(request_id="PYRQ-003481").exists())

    def test_un_pdf_cualquiera_se_rechaza_con_un_mensaje_claro(self):
        archivo = SimpleUploadedFile("otra.pdf", pdf_con_texto(["Hola, esto no es una carta"]), "application/pdf")
        r = self.client.post(reverse("carta_subir"), {"archivo": archivo})
        self.assertContains(r, "No encontré el Request ID")
        r = self.client.post(reverse("carta_subir"), {"archivo": SimpleUploadedFile("x.pdf", b"no soy un pdf")})
        self.assertContains(r, "no es un PDF")

    def _subir_carta_q4(self):
        """Carta nueva: trae 2 visitas hechas, una que no está cargada y una con otro importe."""
        renglones = ["Invoice Request Form", "Request ID: PYRQ-005000", "14-Jan-2027", "Site #: 312",
                     "in the amount of USD 9,989.81", "Visit Sequence Subject Name Amount",
                     "1 312-21787 Screening USD 2,896.40", "2 312-21787 Day 1 USD 3,195.41",
                     "7 312-21165 Week 16 USD 2,535.00", "3 312-21850 Week 1 USD 1,363.00",
                     "Please include the following items"]
        archivo = SimpleUploadedFile("q4.pdf", pdf_con_texto(renglones), "application/pdf")
        r = self.client.post(reverse("carta_subir"), {"archivo": archivo})
        carta = CartaPago.objects.get(request_id="PYRQ-005000")
        self.assertRedirects(r, reverse("carta_detalle", args=[carta.id]))
        return carta

    def test_conciliacion_y_facturas_desde_la_carta(self):
        carta = self._subir_carta_q4()
        self.assertEqual((carta.periodo, carta.monto_usd, carta.items.count()), ("Q4 2026", D("9989.81"), 4))
        filas, afuera = cartas.conciliar(carta)
        self.assertEqual([f["estado"] for f in filas], ["ok", "ok", "falta", "monto"])
        # Hechas antes de la carta y que la carta no trae: el resto de lo pendiente.
        self.assertIn(("312-21850", "Screening"), [(v.paciente.codigo, v.tipo.nombre) for v in afuera])
        html = self.client.get(reverse("carta_detalle", args=[carta.id])).content.decode()
        self.assertIn("no está cargada", html)
        self.assertIn("El presupuesto dice USD 1898.00", html)

        self.client.post(reverse("carta_detalle", args=[carta.id]), {"que": "visitas"})
        factura = Factura.objects.get(numero="006")
        self.assertEqual((factura.total, factura.request_id, factura.carta), (D("6091.81"), "PYRQ-005000", carta))
        self.assertFalse(factura.request_id_no_coincide)
        self.client.post(reverse("carta_detalle", args=[carta.id]), {"que": "viaticos"})
        self.assertEqual(Factura.objects.get(numero="007").total, D("300.00"))   # 3 visitas reconocidas × 100
        # No se factura dos veces lo mismo.
        self.client.post(reverse("carta_detalle", args=[carta.id]), {"que": "visitas"})
        self.assertFalse(Factura.objects.filter(numero="008").exists())

    def test_subir_la_carta_q3_completa_el_detalle_de_la_ya_cargada(self):
        renglones = ["Request ID: PYRQ-004039", "13-Oct-2026", "in the amount of USD 4,433.00", "Sequence Subject Name Amount",
                     "4 312-21165 Week 4 USD 2,535.00", "6 312-21165 Week 12 USD 1,898.00", "Please include"]
        self.client.post(reverse("carta_subir"), {"archivo": SimpleUploadedFile("q3.pdf", pdf_con_texto(renglones))})
        self.assertEqual(CartaPago.objects.filter(request_id="PYRQ-004039").count(), 1)
        carta = CartaPago.objects.get(request_id="PYRQ-004039")
        filas, afuera = cartas.conciliar(carta)
        self.assertEqual([f["estado"] for f in filas], ["facturada", "facturada"])
        # Del trimestre (hasta el 30/09) quedaron afuera los dos screenings de septiembre, nada de octubre.
        self.assertEqual(cartas.fin_del_periodo(carta.fecha), date(2026, 9, 30))
        self.assertEqual(cartas.fin_del_periodo(date(2027, 1, 14)), date(2026, 12, 31))
        self.assertEqual([(v.paciente.codigo, v.tipo.nombre) for v in afuera],
                         [("312-21787", "Screening"), ("312-21850", "Screening")])


class FacturaEnPdf(Base):
    def test_pdf_con_todo_lo_que_pide_la_cro(self):
        from pypdf import PdfReader
        self.protocolo.datos_bancarios = "Bank Name: Banco de Prueba\nAccount #: 000-PRUEBA"
        self.protocolo.save()
        factura = Factura.objects.get(numero="003")
        r = self.client.get(reverse("factura_pdf", args=[factura.id]))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("Invoice 003 Protocol MK-8748-002_EYEB1014.pdf", r["Content-Disposition"])
        texto = " ".join("\n".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages).split())
        for esperado in ["INVOICE # 003", "INVOICE DATE: 25 AUG 2026", "DUE DATE: 25 SEP 2026", "MK-8748-002 / EYEB1014",
                         "Request ID: PYRQ-003462", "Centro de Ojos Loria SRL", "TFS Trial Form Support",
                         "312-21198", "Screen failure", "Completed all screening procedures", "Travel",
                         "USD 2,896.40", "USD 3,896.40", "Banco de Prueba"]:
            self.assertIn(esperado, texto)

    def test_la_coordinadora_no_descarga_facturas_ni_sube_cartas(self):
        self.client.force_login(Usuario.objects.get(username="caro"))
        Usuario.objects.filter(username="caro").update(debe_cambiar_clave=False)
        for url in [reverse("factura_pdf", args=[1]), reverse("carta_subir"), reverse("carta_detalle", args=[1]),
                    reverse("protocolo_subir"), reverse("protocolo_revisar")]:
            self.assertEqual(self.client.get(url).status_code, 403, url)


class ProtocoloDesdePresupuesto(Base):
    def _excel(self):
        from openpyxl import Workbook
        libro = Workbook()
        h = libro.active
        h["A2"], h["B2"], h["G4"], h["H4"] = "Sponsor :", "Sponsor de Prueba", "Overhead Percentage :", 0.25
        h["A3"], h["B3"], h["G5"], h["H5"], h["G7"], h["H7"] = "Protocol # :", "XYZ-001", "Investigator :", "Dra. Prueba", "Site ID :", 77
        cabeza = ["Cost Description", "OH?", "OH", "Total Quantity", "Unit Cost", "Unit Cost + OH", "Screening", "Day 1", "Week 4", "Total"]
        h.append([]); h.append([]); h.append([])
        h.append(cabeza)                                                    # fila 11
        h.append(["Informed Consent Process", "Y", None, None, 100, None, 1, 0, 0])
        h.append(["BCVA", "Y", None, None, 200, None, 1, 1, 1])
        h.append(["Pre-IVT SDOCT", "Y", None, None, 300, None, 1, 1, 1])
        h.append(["IVT of study drug", "Y", None, None, 400, None, None, 1, 1])
        h.append(["Something without overhead", "N", None, None, 10, None, 1, 1, 1])
        h.append([])
        h.append(["Total Costs Per Visit (+ OH)"])
        h.append([])
        h.append(cabeza)
        h.append(["Pre-IVT OCTA (if performed)", "Y", None, None, 400, None, None, 1, 1])
        h.append(["Urine Pregnancy Test", "Y", None, None, 20, None, None, 1, 1])
        h.append(["Subject Travel Reimbursement; Up To 2", "N", None, None, 80, None, 1, 1, 1])
        h.append([])
        h.append(cabeza)
        h.append(["Study Fee: Set-Up; Fixed", "N", None, 1, 5000])
        salida = BytesIO()
        libro.save(salida)
        return salida.getvalue()

    def test_lee_precios_con_overhead_y_crea_el_protocolo(self):
        leido = presupuesto.leer(BytesIO(self._excel()))
        self.assertEqual((leido["codigo"], leido["sponsor"], leido["sitio"], leido["viatico"]), ("XYZ-001", "Sponsor de Prueba", "77", "80.00"))
        self.assertEqual([(v["nombre"], v["semana"], v["precio"]) for v in leido["visitas"]],
                         [("Screening", None, "760.00"), ("Day 1", 0, "1135.00"), ("Week 4", 4, "1135.00")])
        self.assertEqual(leido["visitas"][1]["esperados"], ["AV", "OCT", "Inyección", "OCTA"])
        self.assertEqual(leido["condicionales"], {"OCTA": "500.00"})
        self.assertEqual([x["descripcion"] for x in leido["sin_cargar"]], ["Urine Pregnancy Test"])

        archivo = SimpleUploadedFile("presupuesto.xlsx", self._excel())
        r = self.client.post(reverse("protocolo_subir"), {"nombre": "PRUEBA", "archivo": archivo, "base": self.protocolo.id})
        self.assertRedirects(r, reverse("protocolo_revisar"))
        self.assertContains(self.client.get(reverse("protocolo_revisar")), "USD 1.135,00")
        self.assertFalse(Protocolo.objects.filter(codigo="XYZ-001").exists())      # todavía no creó nada
        self.assertRedirects(self.client.post(reverse("protocolo_revisar")), reverse("tablero"))
        nuevo = Protocolo.objects.get(codigo="XYZ-001")
        self.assertEqual((nuevo.nombre, nuevo.viatico_usd, nuevo.derivacion_usd), ("PRUEBA", D("80.00"), D("1000.00")))
        self.assertEqual(nuevo.tipos_visita.get(nombre="Day 1").precio_usd, D("1135.00"))
        self.assertEqual(nuevo.procedimientos.get(nombre="AV").tarifa_usd, D("25"))          # copiada de MALBEC
        self.assertEqual(nuevo.procedimientos.get(nombre="OCTA").precio_sponsor_usd, D("500.00"))
        # El tablero pasa al estudio nuevo, vacío, y MALBEC queda intacto.
        self.assertContains(self.client.get(reverse("tablero")), "Tablero · PRUEBA")
        self.assertEqual(servicios.reparto(self.protocolo)["cobrado"], D("35365.83"))
        # No se puede crear dos veces.
        self.client.post(reverse("protocolo_subir"), {"nombre": "OTRA", "archivo": SimpleUploadedFile("p.xlsx", self._excel())})
        self.assertContains(self.client.get(reverse("protocolo_revisar")), "Ya hay un protocolo")

    def test_un_excel_cualquiera_se_rechaza(self):
        from openpyxl import Workbook
        salida = BytesIO()
        Workbook().save(salida)
        r = self.client.post(reverse("protocolo_subir"), {"nombre": "X", "archivo": SimpleUploadedFile("x.xlsx", salida.getvalue())})
        self.assertContains(r, "No encontré la tabla de costos")


class CotizacionBancoNacion(Base):
    PAGINA = ('<div id="billetes"><table class="table cotizacion"><thead><tr><th class="fechaCot">18/11/2026</th><th>Compra</th>'
              '<th>Venta</th></tr></thead><tbody><tr><td class="tit">Dolar U.S.A</td> <td>1530,00</td> <td>1580,00</td></tr>'
              '<tr><td class="tit">Euro</td><td>1670,00</td><td>1770,00</td></tr></tbody></table></div><div id="divisas"><table>'
              '<tr><td class="tit">Dolar U.S.A</td><td>1550.5000</td><td>1559.5000</td></tr></table></div>')

    def test_lee_el_vendedor_billete(self):
        self.assertEqual(cotizacion.leer(self.PAGINA), (D("1580.00"), "18/11/2026"))
        self.assertIsNone(cotizacion.leer("<html>mantenimiento</html>"))
        self.assertIsNone(cotizacion.leer('<div id="billetes"><td>Dolar U.S.A</td><td>s/c</td><td>s/c</td></div>'))

    def test_el_pago_viene_con_la_cotizacion_puesta(self):
        with mock.patch("finanzas.cotizacion.dolar_bna_vendedor", return_value=(D("1580.00"), "18/11/2026")):
            r = self.client.get(reverse("pago_nuevo"))
        self.assertContains(r, 'value="1580.00"')
        self.assertContains(r, "Banco Nación vendedor")

    def test_si_el_banco_no_responde_se_carga_a_mano(self):
        r = self.client.get(reverse("pago_nuevo"))
        self.assertContains(r, "No pude leer la cotización")
