from django.contrib import admin

from .models import CartaPago, Factura, Gasto, ItemFactura, PagoMedico, Socio


@admin.register(Socio)
class SocioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "porcentaje", "es_comision", "orden"]


@admin.register(CartaPago)
class CartaPagoAdmin(admin.ModelAdmin):
    list_display = ["periodo", "protocolo", "fecha", "request_id", "monto_usd"]


class ItemInline(admin.TabularInline):
    model = ItemFactura
    extra = 0
    raw_id_fields = ["visita", "realizacion"]


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ["numero", "protocolo", "fecha", "vencimiento", "cobrada"]
    inlines = [ItemInline]


@admin.register(PagoMedico)
class PagoMedicoAdmin(admin.ModelAdmin):
    list_display = ["medico", "periodo", "fecha", "monto_usd", "monto_ars", "pagado_por"]


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ["concepto", "fecha", "monto_usd", "pagado_por"]
