"""Las derivaciones ya pagadas a Palacio estaban cargadas como un gasto: pasan a
ser un pago a médico, para que su saldo cierre. El reparto no cambia."""
from django.db import migrations


def gasto_a_pago(apps, schema_editor):
    Gasto = apps.get_model("finanzas", "Gasto")
    PagoMedico = apps.get_model("finanzas", "PagoMedico")
    Medico = apps.get_model("estudios", "Medico")
    palacio = Medico.objects.filter(nombre="Palacio").first()
    for g in Gasto.objects.filter(concepto="Derivaciones (Palacio)"):
        if palacio is None:
            return
        PagoMedico.objects.create(protocolo=g.protocolo, medico=palacio, fecha=g.fecha,
                                  periodo="derivaciones (3 pacientes)", monto_usd=g.monto_usd,
                                  pagado_por=g.pagado_por, nota="Cargado desde la planilla de balance")
        g.delete()


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0001_initial"), ("estudios", "0002_derivaciones")]
    operations = [migrations.RunPython(gasto_a_pago, migrations.RunPython.noop)]
