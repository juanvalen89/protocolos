from .models import Protocolo


def protocolos(request):
    """Protocolos activos y el elegido, para el selector del encabezado."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from .views import protocolo_actual
    return {"protocolos_activos": Protocolo.objects.filter(activo=True), "protocolo_actual": protocolo_actual(request)}
