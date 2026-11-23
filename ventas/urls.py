from django.urls import path
from . import views

urlpatterns = [
    path('', views.venta_list, name='venta_list'),
    path('reporte/por-dia/', views.ventas_reporte_por_dia, name='ventas_reporte_por_dia'),
    path('reporte/por-dia/detalle/', views.ventas_reporte_dia_detalle, name='ventas_reporte_dia_detalle'),
    path('reporte/por-metodo/', views.ventas_reporte_por_metodo, name='ventas_reporte_por_metodo'),
    path('create/', views.venta_create, name='venta_create'),
    path('agregar-producto/', views.agregar_producto_ajax, name='agregar_producto_ajax'),
    path('asociar-codigo-rapido/', views.asociar_codigo_barra_rapido, name='asociar_codigo_barra_rapido'),
    path('<int:pk>/', views.venta_detail, name='venta_detail'),
    path('<int:pk>/comprobante/', views.venta_comprobante, name='venta_comprobante'),
    path('<int:pk>/exists/', views.venta_exists, name='venta_exists'),
]
