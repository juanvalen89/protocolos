"""Protocolos, visitas y la carga de quién hizo cada procedimiento.

La carga (Visita + Realizacion) es lo único que toca la coordinadora. Los
importes viven en campos de configuración (tarifa del médico, precio del
sponsor) que ninguna pantalla de la coordinadora muestra.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models

CERO = Decimal("0")


class Protocolo(models.Model):
    codigo = models.CharField("código", max_length=40, unique=True)          # MK-8748-002
    nombre = models.CharField("nombre corto", max_length=60)                 # MALBEC
    codigo_cro = models.CharField("código de la CRO", max_length=40, blank=True)   # EYEB1014
    sponsor = models.CharField(max_length=80, blank=True)
    cro = models.CharField("CRO que paga", max_length=80, blank=True)
    sitio = models.CharField("número de sitio", max_length=20, blank=True)
    investigador = models.CharField("investigador principal", max_length=80, blank=True)
    viatico_usd = models.DecimalField("viático por visita (USD)", max_digits=10, decimal_places=2, default=CERO)
    derivacion_usd = models.DecimalField(
        "pago al médico que deriva (USD)", max_digits=10, decimal_places=2, default=CERO,
        help_text="Se le debe al derivador cuando el paciente entra al estudio (Day 1).")
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class Medico(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    externo = models.BooleanField(
        "externo (no se liquida por tarifa)", default=False,
        help_text="Laboratorio u otro prestador que factura por su cuenta: se registra quién lo hizo, sin importe.")
    hace_procedimientos = models.BooleanField(
        "hace procedimientos del estudio", default=True,
        help_text="Destildar para quien solo deriva pacientes: no aparece en la carga de visitas.")
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "médico"

    def __str__(self):
        return self.nombre


class Procedimiento(models.Model):
    protocolo = models.ForeignKey(Protocolo, on_delete=models.CASCADE, related_name="procedimientos")
    nombre = models.CharField(max_length=60)
    orden = models.PositiveIntegerField(default=0)
    tarifa_usd = models.DecimalField(
        "tarifa al médico (USD)", max_digits=10, decimal_places=2, default=CERO)
    precio_sponsor_usd = models.DecimalField(
        "precio condicional al sponsor (USD)", max_digits=10, decimal_places=2, default=CERO,
        help_text="Solo para ítems que el sponsor paga aparte de la visita (OCTA, FAF…). Si no, 0.")

    class Meta:
        ordering = ["orden", "nombre"]
        unique_together = [("protocolo", "nombre")]

    def __str__(self):
        return self.nombre


class TipoVisita(models.Model):
    """Una visita del cronograma del protocolo (Screening, Day 1, Week 4…)."""
    protocolo = models.ForeignKey(Protocolo, on_delete=models.CASCADE, related_name="tipos_visita")
    nombre = models.CharField(max_length=40)
    orden = models.PositiveIntegerField(default=0)
    semana = models.IntegerField(
        null=True, blank=True,
        help_text="Semanas desde el Day 1 (Day 1 = 0). Vacío para Screening y no programadas.")
    precio_usd = models.DecimalField(
        "precio que paga el sponsor (USD)", max_digits=10, decimal_places=2, default=CERO)
    procedimientos = models.ManyToManyField(Procedimiento, blank=True, related_name="tipos_visita",
                                            help_text="Los que se esperan en esta visita.")

    class Meta:
        ordering = ["orden"]
        unique_together = [("protocolo", "nombre")]
        verbose_name = "visita del cronograma"
        verbose_name_plural = "visitas del cronograma"

    def __str__(self):
        return self.nombre


class Paciente(models.Model):
    class Estado(models.TextChoices):
        SCREENING = "screening", "En screening"
        ACTIVO = "activo", "En el estudio"
        FALLA = "falla", "Falla de screening"
        FINALIZADO = "finalizado", "Finalizó o salió"

    protocolo = models.ForeignKey(Protocolo, on_delete=models.PROTECT, related_name="pacientes")
    codigo = models.CharField("código de sujeto", max_length=30)   # 312-21165 (nunca el nombre)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.SCREENING)
    derivado_por = models.ForeignKey(Medico, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="derivados", verbose_name="derivado por")
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["codigo"]
        unique_together = [("protocolo", "codigo")]

    def __str__(self):
        return self.codigo

    def fecha_day1(self):
        for v in self.visitas.all():
            if v.tipo.semana == 0 and v.completa:
                return v.fecha
        return None

    def visitas_esperadas(self, hoy, ventana_dias=21):
        """Visitas del cronograma que ya deberían estar (o están por caer) y no se cargaron.
        Devuelve [(tipo, fecha_esperada, atrasada)]. Sin importes: lo ve la coordinadora."""
        if self.estado != self.Estado.ACTIVO:
            return []
        d1 = self.fecha_day1()
        if not d1:
            return []
        hechas = {v.tipo_id for v in self.visitas.all()}
        salida = []
        for t in self.protocolo.tipos_visita.all():
            if t.semana is None or t.semana <= 0 or t.id in hechas:
                continue
            esperada = d1 + timedelta(weeks=t.semana)
            if esperada <= hoy + timedelta(days=ventana_dias):
                salida.append((t, esperada, esperada < hoy - timedelta(days=7)))
        return salida


class Visita(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="visitas")
    tipo = models.ForeignKey(TipoVisita, on_delete=models.PROTECT, related_name="visitas")
    fecha = models.DateField()
    completa = models.BooleanField(
        "visita completa", default=True,
        help_text="Destildar si es una repetición parcial de una visita ya hecha (por ejemplo, repetir una extracción).")
    nota = models.CharField(max_length=200, blank=True)
    cargada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]

    def __str__(self):
        return f"{self.paciente} · {self.tipo} · {self.fecha:%d/%m/%Y}"


class Realizacion(models.Model):
    """Un procedimiento hecho en una visita, y quién lo hizo."""
    visita = models.ForeignKey(Visita, on_delete=models.CASCADE, related_name="realizaciones")
    procedimiento = models.ForeignKey(Procedimiento, on_delete=models.PROTECT, related_name="realizaciones")
    medico = models.ForeignKey(Medico, on_delete=models.PROTECT, related_name="realizaciones")
    # Importe que le corresponde al médico, congelado al cargar (la tarifa puede cambiar después).
    monto_usd = models.DecimalField(max_digits=10, decimal_places=2, default=CERO)

    class Meta:
        unique_together = [("visita", "procedimiento")]
        ordering = ["procedimiento__orden"]

    def __str__(self):
        return f"{self.procedimiento} — {self.medico}"
