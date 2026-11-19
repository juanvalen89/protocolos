from django import forms
from django.contrib import admin

from .models import Usuario
from .views import CLAVE_GENERICA


class UsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "rol", "is_active", "debe_cambiar_clave"]


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    """Alta simple: nombre, usuario y rol. La cuenta nace con la clave genérica
    y el sistema obliga a cambiarla en el primer ingreso."""
    form = UsuarioForm
    list_display = ["username", "first_name", "last_name", "rol", "is_active", "debe_cambiar_clave"]
    list_filter = ["rol", "is_active"]
    actions = ["reiniciar_clave"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_password(CLAVE_GENERICA)
            obj.debe_cambiar_clave = True
        super().save_model(request, obj, form, change)
        if not change:
            self.message_user(request, f"Usuario creado. Clave inicial: {CLAVE_GENERICA} (la cambia al entrar).")

    @admin.action(description="Volver a la clave genérica (la cambia al entrar)")
    def reiniciar_clave(self, request, queryset):
        for u in queryset:
            u.set_password(CLAVE_GENERICA)
            u.debe_cambiar_clave = True
            u.save()
        self.message_user(request, f"Clave reiniciada a {CLAVE_GENERICA}.")

    def has_delete_permission(self, request, obj=None):
        return False  # los usuarios se desactivan, no se borran
