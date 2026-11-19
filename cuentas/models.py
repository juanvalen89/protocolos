"""Usuarios del sistema. El ROL decide los permisos, sin casillas sueltas.

- Dirección: ve todo (carga, pagos a médicos, cobros al sponsor y reparto).
- Coordinadora: carga pacientes, visitas y quién hizo cada procedimiento.
  No ve ningún importe: ni tarifas, ni precios del sponsor, ni liquidaciones.
"""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra):
        extra.setdefault("rol", Usuario.Rol.DIRECCION)
        return super().create_superuser(username, email, password, **extra)


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        DIRECCION = "direccion", "Dirección"
        COORDINADORA = "coordinadora", "Coordinadora de estudios"

    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.COORDINADORA)
    debe_cambiar_clave = models.BooleanField(
        "debe cambiar la contraseña al ingresar", default=False,
        help_text="Se destilda solo cuando el usuario cambia su contraseña.",
    )

    objects = UsuarioManager()

    @property
    def ve_numeros(self) -> bool:
        """Única regla de quién ve dinero: Dirección. Nunca una coordinadora."""
        return self.is_active and self.rol == self.Rol.DIRECCION

    def save(self, *args, **kwargs):
        # Los permisos salen del rol: solo Dirección entra a Configuración.
        es_direccion = self.rol == self.Rol.DIRECCION
        self.is_staff = es_direccion
        self.is_superuser = es_direccion
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username
