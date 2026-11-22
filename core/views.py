from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Q, F, Avg
import json

from inventario.models import Producto, Categoria, bajo_stock_queryset
from ventas.models import Venta, VentaDetalle
from caja.models import Caja
from auditoria.models import Actividad
from clientes.models import Cliente
from core.enums import MetodoPago
from negocios.models import Negocio


@login_required
def home(request):
    # Si es el Dueño de la plataforma (Rodrigo) y no está inspeccionando un negocio específico, mostrar Panel Master
    if request.user.is_superuser and not request.session.get('impersonate_negocio_id'):
        return redirect('panel_master')

    # Estadísticas para el dashboard aisladas por negocio
    hoy = timezone.now().date()
    negocio = getattr(request, 'negocio', None)
 
    # Ventas desde apertura de caja del negocio
    cajas_qs = Caja.objects.filter(negocio=negocio) if negocio else Caja.objects.none()
    ultima_caja = cajas_qs.filter(abierta=True).order_by('-hora_apertura').first()
    if ultima_caja:
        ventas_hoy = Venta.objects.filter(caja=ultima_caja, negocio=negocio).count()
        total_ventas = Venta.objects.filter(caja=ultima_caja, negocio=negocio).aggregate(total_sum=Sum('total'))['total_sum'] or 0
    else:
        ventas_hoy = 0
        total_ventas = 0
 
    # Productos con stock bajo del negocio
    prod_qs = Producto.objects.filter(negocio=negocio) if negocio else Producto.objects.none()
    productos_stock_bajo = bajo_stock_queryset(prod_qs).count()
 
    # Estado de caja del negocio
    cajas_abiertas_count = cajas_qs.filter(abierta=True).count()
    caja_abierta = cajas_abiertas_count > 0

    # Fiados / Deudas de clientes del negocio
    cli_qs = Cliente.objects.filter(negocio=negocio, activo=True) if negocio else Cliente.objects.none()
    resumen_fiados = cli_qs.aggregate(total_deuda=Sum('saldo_deudor'))
    total_deuda_fiados = resumen_fiados.get('total_deuda') or 0
    clientes_con_deuda_count = cli_qs.filter(saldo_deudor__gt=0).count()
 
    # Últimas actividades del negocio
    act_qs = Actividad.objects.filter(negocio=negocio) if negocio else Actividad.objects.none()
    ultimas_actividades = (
        act_qs.select_related('usuario')
        .exclude(
            Q(tipo_accion='CREACION_REGISTRO')
            & (
                Q(descripcion__startswith='Creado IngresoStockDetalle')
                | Q(descripcion__startswith='Creado IngresoStock')
            )
        )
        .order_by('-fecha_hora')[:10]
    )

    context = {
        'hoy_fecha': hoy,
        'ventas_hoy': ventas_hoy,
        'total_ventas': total_ventas,
        'productos_stock_bajo': productos_stock_bajo,
        'caja_abierta': caja_abierta,
        'cajas_abiertas_count': cajas_abiertas_count,
        'total_deuda_fiados': total_deuda_fiados,
        'clientes_con_deuda_count': clientes_con_deuda_count,
        'ultimas_actividades': ultimas_actividades,
    }

    return render(request, 'home.html', context)


@login_required
def dashboard_analiticas(request):
    """Sección de Dashboard Analítico de Negocio con métricas de ventas, márgenes, productos más y menos vendidos y filtros."""
    # Resolver negocio activo (permite a Rodrigo seleccionar negocio vía GET si es superuser)
    negocio = getattr(request, 'negocio', None)
    negocios_disponibles = None

    if request.user.is_superuser:
        negocios_disponibles = Negocio.objects.all().order_by('nombre')
        neg_param = request.GET.get('negocio_id')
        if neg_param:
            try:
                negocio = Negocio.objects.get(id=int(neg_param))
            except Exception:
                pass
        if not negocio:
            negocio = Negocio.objects.filter(activo=True).first()

    if not negocio:
        return redirect('home')

    ahora = timezone.now()
    hoy = ahora.date()

    # 1. Parámetros de Filtro
    periodo = request.GET.get('periodo', 'mes')  # 'hoy', 'ayer', 'semana', 'mes', 'anio', 'todo', 'custom'
    fecha_desde_str = request.GET.get('fecha_desde', '')
    fecha_hasta_str = request.GET.get('fecha_hasta', '')
    producto_filtro = request.GET.get('producto', '')
    categoria_filtro = request.GET.get('categoria', '')
    metodo_filtro = request.GET.get('metodo_pago', '')

    # Construir rango de fechas según período
    fecha_inicio = None
    fecha_fin = None

    if periodo == 'hoy':
        fecha_inicio = datetime.combine(hoy, time.min).astimezone(timezone.get_current_timezone())
        fecha_fin = datetime.combine(hoy, time.max).astimezone(timezone.get_current_timezone())
    elif periodo == 'ayer':
        ayer = hoy - timedelta(days=1)
        fecha_inicio = datetime.combine(ayer, time.min).astimezone(timezone.get_current_timezone())
        fecha_fin = datetime.combine(ayer, time.max).astimezone(timezone.get_current_timezone())
    elif periodo == 'semana':
        inicio_semana = hoy - timedelta(days=7)
        fecha_inicio = datetime.combine(inicio_semana, time.min).astimezone(timezone.get_current_timezone())
        fecha_fin = datetime.combine(hoy, time.max).astimezone(timezone.get_current_timezone())
    elif periodo == 'mes':
        inicio_mes = hoy.replace(day=1)
        fecha_inicio = datetime.combine(inicio_mes, time.min).astimezone(timezone.get_current_timezone())
        fecha_fin = datetime.combine(hoy, time.max).astimezone(timezone.get_current_timezone())
    elif periodo == 'anio':
        inicio_anio = hoy.replace(month=1, day=1)
        fecha_inicio = datetime.combine(inicio_anio, time.min).astimezone(timezone.get_current_timezone())
        fecha_fin = datetime.combine(hoy, time.max).astimezone(timezone.get_current_timezone())
    elif periodo == 'custom' and fecha_desde_str and fecha_hasta_str:
        try:
            fd = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            fh = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
            fecha_inicio = datetime.combine(fd, time.min).astimezone(timezone.get_current_timezone())
            fecha_fin = datetime.combine(fh, time.max).astimezone(timezone.get_current_timezone())
        except Exception:
            pass

    # 2. Filtrado de Ventas
    ventas_qs = Venta.objects.filter(negocio=negocio)
    if fecha_inicio and fecha_fin:
        ventas_qs = ventas_qs.filter(fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
    if metodo_filtro:
        ventas_qs = ventas_qs.filter(metodo_pago=metodo_filtro)

    # Filtrar detalles de ventas
    detalles_qs = VentaDetalle.objects.filter(venta__in=ventas_qs, producto__isnull=False).select_related('producto', 'producto__categoria', 'venta')
    if producto_filtro:
        try:
            detalles_qs = detalles_qs.filter(producto_id=int(producto_filtro))
        except Exception:
            pass
    if categoria_filtro:
        try:
            detalles_qs = detalles_qs.filter(producto__categoria_id=int(categoria_filtro))
        except Exception:
            pass

    # Si se filtró por producto o categoría, restringir ventas al subconjunto correspondiente
    if producto_filtro or categoria_filtro:
        ventas_afectadas_ids = detalles_qs.values_list('venta_id', flat=True).distinct()
        ventas_resumen_qs = ventas_qs.filter(id__in=ventas_afectadas_ids)
        total_dinero = detalles_qs.aggregate(t=Sum('subtotal'))['t'] or Decimal('0.00')
    else:
        ventas_resumen_qs = ventas_qs
        total_dinero = ventas_resumen_qs.aggregate(t=Sum('total'))['t'] or Decimal('0.00')

    cantidad_ventas = ventas_resumen_qs.count()
    ticket_promedio = (total_dinero / cantidad_ventas) if cantidad_ventas > 0 else Decimal('0.00')

    # 3. Cálculo de Costos, Ganancias y Margen Comercial en el Periodo
    def calcular_costo_unitario_base(prod):
        if not prod:
            return Decimal('0.00')
        if prod.tipo_producto == 'PACK' and prod.unidades_por_pack:
            return Decimal(str(prod.precio_compra)) / Decimal(str(prod.unidades_por_pack))
        elif prod.tipo_producto == 'GRANEL' and prod.kg_por_caja:
            return Decimal(str(prod.precio_compra)) / Decimal(str(prod.kg_por_caja))
        return Decimal(str(prod.precio_compra))

    ganancia_total_periodo = Decimal('0.00')
    costo_total_periodo = Decimal('0.00')
    ventas_por_producto = {}

    for det in detalles_qs:
        prod = det.producto
        costo_unit = calcular_costo_unitario_base(prod)
        costo_linea = costo_unit * Decimal(str(det.cantidad_base))
        subtotal_linea = Decimal(str(det.subtotal))
        ganancia_linea = subtotal_linea - costo_linea

        ganancia_total_periodo += ganancia_linea
        costo_total_periodo += costo_linea

        pid = prod.id
        if pid not in ventas_por_producto:
            ventas_por_producto[pid] = {
                'producto': prod,
                'cantidad_vendida': Decimal('0.00'),
                'ingresos': Decimal('0.00'),
                'ganancia': Decimal('0.00'),
            }
        ventas_por_producto[pid]['cantidad_vendida'] += Decimal(str(det.cantidad_base))
        ventas_por_producto[pid]['ingresos'] += subtotal_linea
        ventas_por_producto[pid]['ganancia'] += ganancia_linea

    # Margen comercial en el periodo: % sobre ventas
    if total_dinero > Decimal('0.00'):
        margen_promedio_periodo = (ganancia_total_periodo / total_dinero) * Decimal('100.00')
    else:
        margen_promedio_periodo = Decimal('0.00')

    # Margen promedio del catálogo total del negocio (independiente de si vendió)
    productos_catalogo = Producto.objects.filter(negocio=negocio, activo=True)
    margenes_catalogo = []
    for p in productos_catalogo:
        costo_u = calcular_costo_unitario_base(p)
        pv = Decimal(str(p.precio_venta))
        if pv > Decimal('0.00'):
            margen_pct = ((pv - costo_u) / pv) * Decimal('100.00')
            margenes_catalogo.append(margen_pct)

    margen_promedio_catalogo = (sum(margenes_catalogo) / len(margenes_catalogo)) if margenes_catalogo else Decimal('0.00')

    # 4. Desglose de Métodos de Pago
    desglose_metodos = {
        'EFECTIVO': {'total': Decimal('0.00'), 'count': 0, 'nombre': 'Efectivo', 'color': '#10b981'},
        'TARJETA': {'total': Decimal('0.00'), 'count': 0, 'nombre': 'Tarjeta / Débito', 'color': '#3b82f6'},
        'TRANSFERENCIA': {'total': Decimal('0.00'), 'count': 0, 'nombre': 'Transferencia', 'color': '#6366f1'},
        'FIADO': {'total': Decimal('0.00'), 'count': 0, 'nombre': 'Fiado (Crédito)', 'color': '#f59e0b'},
    }

    metodos_agg = (
        ventas_resumen_qs.values('metodo_pago')
        .annotate(total=Sum('total'), count=Count('id'))
    )
    for m in metodos_agg:
        mp = m['metodo_pago']
        # Compatibilidad legacy 'DEBITO' -> 'TARJETA'
        clave = 'TARJETA' if mp in ('TARJETA', 'DEBITO') else mp
        if clave in desglose_metodos:
            desglose_metodos[clave]['total'] += m['total'] or Decimal('0.00')
            desglose_metodos[clave]['count'] += m['count']

    # 5. Ranking: Productos Más Vendidos (Top 10)
    productos_mas_vendidos = sorted(
        ventas_por_producto.values(),
        key=lambda x: (x['cantidad_vendida'], x['ingresos']),
        reverse=True
    )[:10]

    for item in productos_mas_vendidos:
        ing = item['ingresos']
        gan = item['ganancia']
        item['margen_pct'] = ((gan / ing) * Decimal('100.00')) if ing > 0 else Decimal('0.00')

    # 6. Ranking: Productos Menos Vendidos / Sin Rotación
    # Considera productos del catálogo del negocio
    prod_qs_menos = productos_catalogo
    if categoria_filtro:
        prod_qs_menos = prod_qs_menos.filter(categoria_id=categoria_filtro)
    if producto_filtro:
        prod_qs_menos = prod_qs_menos.filter(id=producto_filtro)

    productos_menos_vendidos = []
    for p in prod_qs_menos:
        v_data = ventas_por_producto.get(p.id)
        cant_vendida = v_data['cantidad_vendida'] if v_data else Decimal('0.00')
        ing_generado = v_data['ingresos'] if v_data else Decimal('0.00')
        costo_u = calcular_costo_unitario_base(p)
        valor_stock_estancado = costo_u * Decimal(str(p.stock_actual_base or 0))

        productos_menos_vendidos.append({
            'producto': p,
            'cantidad_vendida': cant_vendida,
            'ingresos': ing_generado,
            'stock_actual': p.stock_actual_base,
            'valor_stock': valor_stock_estancado,
        })

    # Ordenar ascendente: 0 ventas primero, luego menor cantidad
    productos_menos_vendidos = sorted(
        productos_menos_vendidos,
        key=lambda x: (x['cantidad_vendida'], x['ingresos'])
    )[:10]

    # 7. Datos de Gráficos (Chart.js)
    # Gráfico 1: Evolución de Ventas por Día (últimos 14 días o días del período)
    dias_grafico = []
    totales_grafico = []
    fecha_cursor = (fecha_inicio.date() if fecha_inicio else (hoy - timedelta(days=13)))
    fecha_tope = (fecha_fin.date() if fecha_fin else hoy)

    # Limitar el gráfico diario a un rango manejable (máx 31 días)
    if (fecha_tope - fecha_cursor).days > 31:
        fecha_cursor = fecha_tope - timedelta(days=30)

    ventas_por_dia_map = dict(
        ventas_resumen_qs.values('fecha__date')
        .annotate(total_dia=Sum('total'))
        .values_list('fecha__date', 'total_dia')
    )

    curr = fecha_cursor
    while curr <= fecha_tope:
        dias_grafico.append(curr.strftime('%d/%m'))
        val = ventas_por_dia_map.get(curr, Decimal('0.00'))
        totales_grafico.append(float(val))
        curr += timedelta(days=1)

    # Gráfico 2: Top 5 Productos (Nombres y Unidades)
    top5_nombres = [item['producto'].nombre[:18] for item in productos_mas_vendidos[:5]]
    top5_cantidades = [float(item['cantidad_vendida']) for item in productos_mas_vendidos[:5]]

    # Opciones para selectores de filtro
    categorias_select = Categoria.objects.filter(negocio=negocio).order_by('nombre')
    productos_select = Producto.objects.filter(negocio=negocio, activo=True).order_by('nombre')

    context = {
        'negocio': negocio,
        'negocios_disponibles': negocios_disponibles,
        'periodo': periodo,
        'fecha_desde': fecha_desde_str,
        'fecha_hasta': fecha_hasta_str,
        'producto_filtro': producto_filtro,
        'categoria_filtro': categoria_filtro,
        'metodo_filtro': metodo_filtro,
        'categorias_select': categorias_select,
        'productos_select': productos_select,
        'metodos_choices': MetodoPago.choices,
        'total_dinero': total_dinero,
        'cantidad_ventas': cantidad_ventas,
        'ticket_promedio': ticket_promedio,
        'ganancia_total_periodo': ganancia_total_periodo,
        'costo_total_periodo': costo_total_periodo,
        'margen_promedio_periodo': margen_promedio_periodo,
        'margen_promedio_catalogo': margen_promedio_catalogo,
        'desglose_metodos': desglose_metodos,
        'productos_mas_vendidos': productos_mas_vendidos,
        'productos_menos_vendidos': productos_menos_vendidos,
        # JSON para Chart.js
        'chart_dias_labels': json.dumps(dias_grafico),
        'chart_dias_totales': json.dumps(totales_grafico),
        'chart_top5_nombres': json.dumps(top5_nombres),
        'chart_top5_cantidades': json.dumps(top5_cantidades),
        'chart_metodos_labels': json.dumps([v['nombre'] for v in desglose_metodos.values()]),
        'chart_metodos_valores': json.dumps([float(v['total']) for v in desglose_metodos.values()]),
        'chart_metodos_colores': json.dumps([v['color'] for v in desglose_metodos.values()]),
    }

    return render(request, 'dashboard.html', context)


@require_http_methods(["GET", "POST"])
def logout_view(request):
    logout(request)
    return redirect('login')
