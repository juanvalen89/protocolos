"""Dinero: cobros al sponsor, pagos a médicos, gastos y reparto. Solo Dirección."""
from decimal import Decimal

from django.db import models

from estudios.models import Medico, Protocolo, Realizacion, Visita

CERO = Decimal("0")


class Socio(models.Model):
    """Quién participa del reparto. Regla fija para todos los estudios: primero
    la comisión (sobre el neto) y el resto se divide por porcentaje."""
    nombre = models.CharField(max_length=60, unique=True)
    es_comision = models.BooleanField(
        "cobra comisión sobre el neto", default=False,
        help_text="Quien trae los estudios: su porcentaje se saca primero, del neto.")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return self.nombre


class CartaPago(models.Model):
    """Payment letter trimestral de la CRO: lista las visitas que hay que facturar."""
    protocolo = models.ForeignKey(Protocolo, on_delete=models.PROTECT, related_name="cartas")
    periodo = models.CharField("período", max_length=20)          # Q3 2026
    fecha = models.DateField()
    request_id = models.CharField("Request ID", max_length=30)
    monto_usd = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["fecha"]
        verbose_name = "carta de pago"
        verbose_name_plural = "cartas de pago"

    def __str__(self):
        return f"{self.periodo} · {self.request_id}"


class ItemCarta(models.Model):
    """Un renglón de la carta de pago, tal como vino en el PDF."""
    carta = models.ForeignKey(CartaPago, on_delete=models.CASCADE, related_name="items")
    secuencia = models.CharField(max_length=5, blank=True)
    codigo_paciente = models.CharField(max_length=30)
    nombre_visita = models.CharField(max_length=60)
    monto_usd = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]


class Factura(models.Model):
    protocolo = models.ForeignKey(Protocolo, on_delete=models.PROTECT, related_name="facturas")
    numero = models.CharField("número", max_length=20)
    fecha = models.DateField()
    vencimiento = models.DateField()
    carta = models.ForeignKey(CartaPago, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="facturas", verbose_name="carta de pago")
    request_id = models.CharField("Request ID impreso en la factura", max_length=30, blank=True)
    cobrada = models.BooleanField(default=False)
    fecha_cobro = models.DateField(null=True, blank=True)
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["fecha", "numero"]
        unique_together = [("protocolo", "numero")]

    def __str__(self):
        return f"Factura {self.numero}"

    @property
    def total(self):
        return sum((i.monto_usd for i in self.items.all()), CERO)

    @property
    def request_id_no_coincide(self):
        return bool(self.carta and self.request_id and self.request_id != self.carta.request_id)


class ItemFactura(models.Model):
    class Concepto(models.TextChoices):
        VISITA = "visita", "Visita"
        VIATICO = "viatico", "Viático"
        CONDICIONAL = "condicional", "Condicional"
        FIJO = "fijo", "Fijo del sitio"
        AJUSTE = "ajuste", "Ajuste de la CRO"

    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name="items")
    concepto = models.CharField(max_length=12, choices=Concepto.choices)
    visita = models.ForeignKey(Visita, null=True, blank=True, on_delete=models.PROTECT, related_name="items_factura")
    realizacion = models.ForeignKey(Realizacion, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="items_factura")
    descripcion = models.CharField(max_length=120)
    monto_usd = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]


class PagoMedico(models.Model):
    protocolo = models.ForeignKey(Protocolo, on_delete=models.PROTECT, related_name="pagos_medicos")
    medico = models.ForeignKey(Medico, on_delete=models.PROTECT, related_name="pagos")
    fecha = models.DateField(null=True, blank=True)
    periodo = models.CharField("período que cubre", max_length=40, blank=True)
    monto_usd = models.DecimalField("importe (USD)", max_digits=12, decimal_places=2)
    cotizacion = models.DecimalField("dólar BNA vendedor del día", max_digits=10, decimal_places=2,
                                     null=True, blank=True)
    monto_ars = models.DecimalField("importe en pesos", max_digits=14, decimal_places=2, null=True, blank=True)
    pagado_por = models.ForeignKey(Socio, on_delete=models.PROTECT, related_name="pagos_medicos",
                                   help_text="Quién puso la plata: se le devuelve en el reparto.")
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["fecha", "id"]
        verbose_name = "pago a médico"
        verbose_name_plural = "pagos a médicos"

    def save(self, *args, **kwargs):
        if self.cotizacion and self.monto_ars is None:
            self.monto_ars = (self.monto_usd * self.cotizacion).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class Gasto(models.Model):
    protocolo = models.ForeignKey(Protocolo, on_delete=models.PROTECT, related_name="gastos")
    fecha = models.DateField(null=True, blank=True)
    concepto = models.CharField(max_length=120)
    monto_usd = models.DecimalField("importe (USD)", max_digits=12, decimal_places=2)
    pagado_por = models.ForeignKey(Socio, on_delete=models.PROTECT, related_name="gastos",
                                   help_text="Quién puso la plata: se le devuelve en el reparto.")

    class Meta:
        ordering = ["fecha", "id"]
