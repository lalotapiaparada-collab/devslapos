from django import forms
from django.forms import formset_factory
from .models import VentaDetalle
from inventario.models import Producto
from clientes.models import Cliente
from decimal import Decimal

class VentaForm(forms.Form):
    metodo_pago = forms.ChoiceField(choices=[], widget=forms.Select(attrs={'class':'form-select', 'id':'id_metodo_pago'}))
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.none(),
        required=False,
        empty_label="-- Seleccionar Cliente para Fiado --",
        widget=forms.Select(attrs={'class':'form-select', 'id':'id_cliente'})
    )

    def __init__(self, *args, **kwargs):
        metodo_choices = kwargs.pop('metodo_choices', None)
        negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)
        if metodo_choices is not None:
            self.fields['metodo_pago'].choices = metodo_choices
        if negocio:
            self.fields['cliente'].queryset = Cliente.objects.filter(negocio=negocio, activo=True)
        else:
            self.fields['cliente'].queryset = Cliente.objects.filter(activo=True)


class VentaDetalleForm(forms.Form):
    producto = forms.ModelChoiceField(queryset=Producto.objects.none(), widget=forms.Select(attrs={'class':'form-select'}))
    unidad_venta = forms.ChoiceField(choices=[], widget=forms.Select(attrs={'class':'form-select'}))
    cantidad_ingresada = forms.DecimalField(widget=forms.NumberInput(attrs={'class':'form-control', 'step':'0.001'}), max_digits=10, decimal_places=3, min_value=Decimal('0.001'))

    def __init__(self, *args, **kwargs):
        unidad_choices = kwargs.pop('unidad_choices', None)
        negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)
        if unidad_choices is not None:
            self.fields['unidad_venta'].choices = unidad_choices
        if negocio:
            self.fields['producto'].queryset = Producto.objects.filter(negocio=negocio)
        else:
            self.fields['producto'].queryset = Producto.objects.all()


VentaDetalleFormSet = formset_factory(VentaDetalleForm, extra=1, min_num=1, validate_min=True, can_delete=True)
