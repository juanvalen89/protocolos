from django import forms
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm

# La clave con la que arrancan las cuentas nuevas: el sistema obliga a cambiarla.
CLAVE_GENERICA = "Loria.Protocolos.2026"


class CambioClaveForm(PasswordChangeForm):
    def clean_new_password1(self):
        nueva = self.cleaned_data.get("new_password1")
        if nueva and nueva == self.cleaned_data.get("old_password"):
            raise forms.ValidationError("La contraseña nueva tiene que ser distinta de la actual.")
        if nueva == CLAVE_GENERICA:
            raise forms.ValidationError("No se puede usar la contraseña genérica: elegí una propia.")
        return nueva


class CambiarClaveView(auth_views.PasswordChangeView):
    """Cambio de contraseña que, además, destilda `debe_cambiar_clave`."""
    template_name = "registration/cambiar_clave.html"
    success_url = "/cambiar-clave/listo/"
    form_class = CambioClaveForm

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        usuario = self.request.user
        if usuario.debe_cambiar_clave:
            usuario.debe_cambiar_clave = False
            usuario.save(update_fields=["debe_cambiar_clave"])
        return respuesta
