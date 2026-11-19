"""Derivaciones (18/11/2026): al médico que deriva se le pagan USD 1.000, en
pesos como al resto. El derivador pasa de texto libre a ser un médico."""
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def texto_a_medico(apps, schema_editor):
    Medico = apps.get_model("estudios", "Medico")
    Paciente = apps.get_model("estudios", "Paciente")
    Protocolo = apps.get_model("estudios", "Protocolo")
    for p in Paciente.objects.exclude(derivador=""):
        nombre = " ".join(p.derivador.split())
        medico = Medico.objects.filter(nombre__iexact=nombre).first()
        if medico is None:
            medico = Medico.objects.create(nombre=nombre.title(), hace_procedimientos=False)
        p.derivado_por = medico
        p.save(update_fields=["derivado_por"])
    Protocolo.objects.filter(codigo="MK-8748-002").update(derivacion_usd=Decimal("1000"))


class Migration(migrations.Migration):
    dependencies = [("estudios", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="protocolo", name="derivacion_usd",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0"), max_digits=10, verbose_name="pago al médico que deriva (USD)",
                help_text="Se le debe al derivador cuando el paciente entra al estudio (Day 1)."),
        ),
        migrations.AddField(
            model_name="medico", name="hace_procedimientos",
            field=models.BooleanField(
                default=True, verbose_name="hace procedimientos del estudio",
                help_text="Destildar para quien solo deriva pacientes: no aparece en la carga de visitas."),
        ),
        migrations.AddField(
            model_name="paciente", name="derivado_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="derivados", to="estudios.medico", verbose_name="derivado por"),
        ),
        migrations.RunPython(texto_a_medico, migrations.RunPython.noop),
        migrations.RemoveField(model_name="paciente", name="derivador"),
    ]
