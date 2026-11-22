from django import forms
from decimal import Decimal
from .models import Cliente, MovimientoCuenta
from core.enums import MetodoPago


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'telefono', 'direccion', 'limite_credito', 'notas', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Don Carlos, Sra. María casa 14'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56 9 1234 5678'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pasaje Los Aromos #120'}),
            'limite_credito': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000', 'min': '0'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Notas sobre horarios, familiares autorizados, etc.'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AbonoForm(forms.Form):
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('1.00'),
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Monto a abonar (CLP)', 'step': '100'})
    )
    metodo_pago = forms.ChoiceField(
        choices=[
            (MetodoPago.EFECTIVO, 'Efectivo (Entra a caja)'),
            (MetodoPago.TARJETA, 'Tarjeta / Débito'),
            (MetodoPago.TRANSFERENCIA, 'Transferencia Bancaria'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    descripcion = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nota u observación (opcional)'})
    )
