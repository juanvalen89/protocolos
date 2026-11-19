from django.urls import path

from . import views

urlpatterns = [
    path("tablero/", views.tablero, name="tablero"),
    path("medicos/", views.medicos, name="medicos"),
    path("medicos/<int:pk>/", views.medico_detalle, name="medico_detalle"),
    path("medicos/pago/", views.pago_nuevo, name="pago_nuevo"),
    path("cobros/", views.cobros, name="cobros"),
    path("cobros/factura/", views.factura_nueva, name="factura_nueva"),
    path("cobros/factura/<int:pk>/cobrada/", views.factura_cobrada, name="factura_cobrada"),
    path("reparto/", views.reparto, name="reparto"),
    path("reparto/gasto/", views.gasto_nuevo, name="gasto_nuevo"),
]
