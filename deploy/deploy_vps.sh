#!/bin/bash
# ==============================================================================
# Script de Despliegue Automatizado para DevSLa POS en VPS Ubuntu/Debian
# ==============================================================================
set -e

APP_DIR="/var/www/devsla_pos"
VENV_DIR="$APP_DIR/venv"

echo ">>> [1/5] Actualizando directorio de trabajo..."
cd "$APP_DIR"

echo ">>> [2/5] Verificando entorno virtual e instalando dependencias..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

echo ">>> [3/5] Ejecutando migraciones de base de datos..."
"$VENV_DIR/bin/python" manage.py migrate --noinput

echo ">>> [4/5] Recopilando archivos estáticos de producción..."
"$VENV_DIR/bin/python" manage.py collectstatic --noinput

echo ">>> [5/5] Ajustando permisos y reiniciando servicio Gunicorn..."
sudo mkdir -p /var/log/gunicorn
sudo chown -R www-data:www-data /var/log/gunicorn
sudo chown -R www-data:www-data "$APP_DIR"
sudo chmod 664 "$APP_DIR/db.sqlite3" || true
sudo chmod 775 "$APP_DIR" || true

sudo systemctl daemon-reload
sudo systemctl restart devsla_pos
sudo systemctl status devsla_pos --no-pager

echo ""
echo "======================================================================"
echo ">>> ¡Despliegue de DevSLa POS completado con éxito!"
echo ">>> Sitio disponible en: http://devsla.cl (o con SSL https://devsla.cl)"
echo "======================================================================"
