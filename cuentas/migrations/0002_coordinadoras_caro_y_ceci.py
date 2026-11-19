"""Alta de las dos coordinadoras (pedido de Juan, 18/11/2026). Nacen con la clave
genérica y el sistema las obliga a cambiarla al entrar. Corre una sola vez y no
toca un usuario que ya exista."""
from django.contrib.auth.hashers import make_password
from django.db import migrations

CLAVE_GENERICA = "Loria.Protocolos.2026"


def crear(apps, schema_editor):
    Usuario = apps.get_model("cuentas", "Usuario")
    for usuario, nombre in [("caro", "Caro"), ("ceci", "Ceci")]:
        if not Usuario.objects.filter(username=usuario).exists():
            Usuario.objects.create(username=usuario, first_name=nombre, rol="coordinadora",
                                   is_staff=False, is_superuser=False, debe_cambiar_clave=True,
                                   password=make_password(CLAVE_GENERICA))


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
