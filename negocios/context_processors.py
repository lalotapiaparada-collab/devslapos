def negocio_context(request):
    """Hace disponible 'negocio_actual', 'es_dueno_saas' e 'inspeccionando_negocio' en todas las plantillas."""
    es_dueno = bool(request.user.is_authenticated and request.user.is_superuser)
    inspeccionando = bool(es_dueno and request.session.get('impersonate_negocio_id'))
    return {
        'negocio_actual': getattr(request, 'negocio', None),
        'es_dueno_saas': es_dueno,
        'inspeccionando_negocio': inspeccionando,
    }
