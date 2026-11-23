"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


import os
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from . import views

# Ruta segura para el panel de administración (por defecto 'panel-admin' en lugar de 'admin' directo)
ADMIN_PATH = os.environ.get('DJANGO_ADMIN_PATH', 'panel-admin').strip('/') or 'panel-admin'

def redirect_direct_admin(request, subpath=''):
    """Evita el acceso directo a /admin/ redirigiendo a la pantalla de login."""
    return redirect('login')

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard_analiticas, name='dashboard'),

    # Panel de administración seguro
    path(f'{ADMIN_PATH}/', admin.site.urls),

    # Redirección de seguridad: /admin/ ya no expone el panel directamente
    path('admin/', redirect_direct_admin),
    path('admin/<path:subpath>', redirect_direct_admin),

    path('', include('core.auth_urls')),
    path('', include('negocios.urls')),
    path('inventario/', include('inventario.urls')),
    path('ventas/', include('ventas.urls')),
    path('caja/', include('caja.urls')),
    path('auditoria/', include('auditoria.urls')),
    path('clientes/', include('clientes.urls')),
]
