from .models import Negocio, PerfilUsuario

class NegocioMiddleware:
    """Asigna automáticamente el negocio del usuario autenticado a request.negocio."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.negocio = None
        request.es_dueno_saas = False

        if request.user.is_authenticated:
            if request.user.is_superuser:
                request.es_dueno_saas = True
                # Si el Dueño SaaS está inspeccionando un negocio específico:
                impersonate_id = request.session.get('impersonate_negocio_id')
                if impersonate_id:
                    request.negocio = Negocio.objects.filter(id=impersonate_id, activo=True).first()
                else:
                    request.negocio = None
            else:
                perfil = getattr(request.user, 'perfil', None)
                if perfil and perfil.negocio and perfil.negocio.activo:
                    request.negocio = perfil.negocio
                else:
                    request.negocio = None

        response = self.get_response(request)
        return response
