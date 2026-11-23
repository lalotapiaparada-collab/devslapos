# DevSLa POS 🛒
Sistema integral de Punto de Venta (POS), Gestión de Inventario Multi-código, Control de Turnos de Caja y Cuentas Corrientes para Almacenes y Minimarkets.

Dominio oficial en producción: **[devsla.cl](https://devsla.cl)**

---

## 🚀 Características Principales
- **Punto de Venta Ultra-Rápido**: Búsqueda instantánea, múltiples códigos de barra por producto y atajos de teclado.
- **Control de Caja y Turnos**: Arqueo ciego, desglose por métodos de pago (efectivo, débito, transferencia) y comprobantes imprimibles.
- **Libreta de Fiados / Cuentas Corrientes**: Gestión de créditos a vecinos con historial de compras y registro de abonos.
- **Métricas y Ganancias Diarias**: Reporte diario con desglose detallado de ventas, ticket promedio y productos más vendidos.
- **Multi-Tenant SaaS con Límites de Cuota**: Monitoreo de uso de productos, usuarios, almacenamiento y ventas por plan (Basic, Plus, Pro).

---

## 🛠️ Instalación y Ejecución Local

1. Crear y activar el entorno virtual:
```bash
python -m venv venv
# En Windows:
venv\Scripts\activate
# En Linux / macOS:
source venv/bin/activate
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Aplicar migraciones y ejecutar servidor:
```bash
python manage.py migrate
python manage.py runserver
```

El sistema estará disponible en `http://127.0.0.1:8000/`.
