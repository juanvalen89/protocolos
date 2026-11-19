from django import forms

from .models import Paciente


class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ["codigo", "estado", "derivador", "nota"]
        help_texts = {"codigo": "El código de sujeto del estudio (por ejemplo 312-21165). Nunca el nombre."}
