from django.urls import path
from . import views

urlpatterns = [
    path('', views.cliente_list, name='cliente_list'),
    path('nuevo/', views.cliente_create, name='cliente_create'),
    path('<int:pk>/', views.cliente_detail, name='cliente_detail'),
    path('<int:pk>/editar/', views.cliente_update, name='cliente_update'),
    path('<int:pk>/abonar/', views.cliente_abonar, name='cliente_abonar'),
    path('<int:pk>/estado-cuenta/', views.cliente_comprobante_deuda, name='cliente_comprobante_deuda'),
    path('abono/<int:pk>/comprobante/', views.abono_comprobante, name='abono_comprobante'),
    path('ajax/quick-create/', views.cliente_quick_create_ajax, name='cliente_quick_create_ajax'),
]
