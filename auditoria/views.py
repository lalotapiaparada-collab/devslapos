from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Actividad
from ventas.models import Venta
from django.db.models import Sum
from django.utils import timezone
from django import forms
from django.shortcuts import redirect
from django.db.models import Q

from core.authz import admin_required


@login_required
@admin_required
def auditoria_list(request):
    """List activities. If ?ventas_mes=1 is provided, show ventas of current month and total."""
    negocio = getattr(request, 'negocio', None)
    show_ventas_mes = request.GET.get('ventas_mes') in ('1', 'true', 'yes')
    context = {}
    if show_ventas_mes:
        now = timezone.now()
        year = now.year
        month = now.month
        ventas_qs = Venta.objects.filter(negocio=negocio, fecha__year=year, fecha__month=month).select_related('usuario').order_by('-fecha')
        total_agg = ventas_qs.aggregate(total_mes=Sum('total'))
        total_mes = total_agg.get('total_mes') or 0
        context.update({
            'ventas_mes': True,
            'ventas_list': ventas_qs,
            'ventas_total': total_mes,
        })

    actividades = (
        Actividad.objects.filter(negocio=negocio).exclude(
            Q(tipo_accion='CREACION_REGISTRO')
            & (
                Q(descripcion__startswith='Creado IngresoStockDetalle')
                | Q(descripcion__startswith='Creado IngresoStock')
            )
        )
        .order_by('-fecha_hora')[:100]
    )
    context['actividades'] = actividades
    return render(request, 'auditoria/auditoria_list.html', context)


class FechaRangeForm(forms.Form):
    fecha_desde = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    fecha_hasta = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))


@login_required
@admin_required
def ventas_por_fecha(request):
    """View that shows ventas filtered by date range and total sold in that range."""
    negocio = getattr(request, 'negocio', None)
    if request.method == 'POST' or (request.method == 'GET' and request.GET.get('fecha_desde') and request.GET.get('fecha_hasta')):
        data = request.POST if request.method == 'POST' else request.GET
        form = FechaRangeForm(data)
        if form.is_valid():
            fd = form.cleaned_data['fecha_desde']
            fh = form.cleaned_data['fecha_hasta']
            from datetime import datetime, time
            fd_dt = datetime.combine(fd, time.min).astimezone(timezone.get_current_timezone())
            fh_dt = datetime.combine(fh, time.max).astimezone(timezone.get_current_timezone())
            ventas_qs = Venta.objects.filter(negocio=negocio, fecha__gte=fd_dt, fecha__lte=fh_dt).select_related('usuario').order_by('-fecha')
            total_agg = ventas_qs.aggregate(total_mes=Sum('total'))
            total = total_agg.get('total_mes') or 0
            filtros = {'fecha_desde': fd.isoformat(), 'fecha_hasta': fh.isoformat()}
            return render(request, 'auditoria/ventas_por_fecha.html', {'form': form, 'ventas_list': ventas_qs, 'ventas_total': total, 'rango': (fd, fh), 'filtros': filtros})

    form = FechaRangeForm()
    filtros = {}
    return render(request, 'auditoria/ventas_por_fecha.html', {'form': form, 'filtros': filtros})
