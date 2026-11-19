"""Decoradores de permisos. Los permisos se verifican acá, en el servidor."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def solo_direccion(vista):
    """Todo lo que muestra dinero: pagos a médicos, cobros al sponsor y reparto."""
    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if not request.user.ve_numeros:
            raise PermissionDenied("Esta pantalla es solo de Dirección.")
        return vista(request, *args, **kwargs)
    return envoltura
