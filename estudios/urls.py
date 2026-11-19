from django.urls import path

from . import alta, views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("protocolo/", views.cambiar_protocolo, name="cambiar_protocolo"),
    path("protocolo/nuevo/", alta.protocolo_subir, name="protocolo_subir"),
    path("protocolo/nuevo/revisar/", alta.protocolo_revisar, name="protocolo_revisar"),
    path("pacientes/", views.pacientes, name="pacientes"),
    path("pacientes/nuevo/", views.paciente_form, name="paciente_nuevo"),
    path("pacientes/<int:pk>/", views.paciente_form, name="paciente_editar"),
    path("pacientes/<int:pk>/visita/", views.elegir_visita, name="elegir_visita"),
    path("pacientes/<int:paciente_id>/visita/<int:tipo_id>/", views.visita_form, name="visita_nueva"),
    path("visitas/<int:pk>/", views.visita_form, name="visita_editar"),
]
