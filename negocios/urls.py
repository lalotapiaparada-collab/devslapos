from django.urls import path
from . import views

urlpatterns = [
    # Panel Master de Rodrigo Tapia (Dueño de Plataforma devsla.cl)
    path('master/', views.panel_master, name='panel_master'),
    path('master/crear-negocio/', views.master_crear_negocio, name='master_crear_negocio'),
    path('master/toggle/<int:negocio_id>/', views.master_toggle_negocio, name='master_toggle_negocio'),
    path('master/eliminar/<int:negocio_id>/', views.master_eliminar_negocio, name='master_eliminar_negocio'),
    path('master/conmutar/<int:negocio_id>/', views.master_conmutar_negocio, name='master_conmutar_negocio'),
    path('master/salir-conmutacion/', views.master_salir_conmutacion, name='master_salir_conmutacion'),
    path('master/cambiar-plan/<int:negocio_id>/', views.master_cambiar_plan, name='master_cambiar_plan'),

    # Rutas para clientes / administradores de cada negocio
    path('registro/', views.registro_negocio, name='registro'),
    path('mi-negocio/', views.mi_negocio, name='mi_negocio'),
    path('mi-negocio/crear-usuario/', views.crear_segundo_usuario, name='crear_segundo_usuario'),
    path('mi-negocio/eliminar-usuario/<int:user_id>/', views.eliminar_usuario_negocio, name='eliminar_usuario_negocio'),
    path('cuota/', views.cuota_negocio, name='cuota'),
]
