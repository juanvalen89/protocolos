from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from cuentas.views import CambiarClaveView

urlpatterns = [
    path("administracion/", admin.site.urls),
    path("ingresar/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cambiar-clave/", CambiarClaveView.as_view(), name="password_change"),
    path("cambiar-clave/listo/", auth_views.PasswordChangeDoneView.as_view(
        template_name="registration/cambiar_clave_listo.html"), name="password_change_done"),
    path("", include("estudios.urls")),
    path("", include("finanzas.urls")),
]

admin.site.site_header = "Configuración · Protocolos de investigación"
admin.site.site_title = "Protocolos Loria"
admin.site.index_title = "Protocolos, tarifas, médicos y usuarios"
