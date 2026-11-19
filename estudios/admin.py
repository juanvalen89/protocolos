from django.contrib import admin

from .models import Medico, Paciente, Procedimiento, Protocolo, TipoVisita


class ProcedimientoInline(admin.TabularInline):
    model = Procedimiento
    extra = 0


@admin.register(Protocolo)
class ProtocoloAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo", "sponsor", "sitio", "activo"]
    inlines = [ProcedimientoInline]


@admin.register(TipoVisita)
class TipoVisitaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "protocolo", "semana", "precio_usd"]
    list_filter = ["protocolo"]
    filter_horizontal = ["procedimientos"]


@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "externo", "activo"]


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ["codigo", "protocolo", "estado", "derivador"]
    list_filter = ["protocolo", "estado"]
