from django import forms

from .models import Medico, Paciente


class PacienteForm(forms.ModelForm):
    """El derivador se escribe por nombre: si no existe, se crea como médico que
    solo deriva (no aparece en la carga de visitas)."""
    derivador = forms.CharField(label="Derivado por", max_length=80, required=False,
                                help_text="Apellido del médico que lo derivó. Vacío si no hubo derivación.")

    class Meta:
        model = Paciente
        fields = ["codigo", "estado", "derivador", "nota"]
        help_texts = {"codigo": "El código de sujeto del estudio (por ejemplo 312-21165). Nunca el nombre."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.derivado_por_id:
            self.fields["derivador"].initial = self.instance.derivado_por.nombre
        self.fields["derivador"].widget.attrs["list"] = "medicos-conocidos"
        self.medicos_conocidos = Medico.objects.filter(activo=True, externo=False)

    def save(self, commit=True):
        nombre = " ".join(self.cleaned_data["derivador"].split())
        if nombre:
            medico = Medico.objects.filter(nombre__iexact=nombre).first()
            if medico is None:
                medico = Medico.objects.create(nombre=nombre.title(), hace_procedimientos=False)
            self.instance.derivado_por = medico
        else:
            self.instance.derivado_por = None
        return super().save(commit)
