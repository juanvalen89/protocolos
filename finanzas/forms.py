from django import forms

from .models import Gasto, PagoMedico


class FechaInput(forms.DateInput):
    input_type = "date"

    def format_value(self, value):
        return value.isoformat() if hasattr(value, "isoformat") else value


class PagoMedicoForm(forms.ModelForm):
    class Meta:
        model = PagoMedico
        fields = ["medico", "fecha", "periodo", "monto_usd", "cotizacion", "pagado_por", "nota"]
        widgets = {"fecha": FechaInput}
        help_texts = {
            "cotizacion": "Dólar vendedor del Banco Nación del día del pago. Dejar vacío si se paga en dólares.",
            "periodo": "Por ejemplo: octubre 2026.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medico"].queryset = self.fields["medico"].queryset.filter(externo=False)


class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ["fecha", "concepto", "monto_usd", "pagado_por"]
        widgets = {"fecha": FechaInput}
