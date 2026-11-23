#!/bin/bash
# ==============================================================================
# DevSLa POS - Script de Actualización Rápida en 1 Comando
# Ruta en VPS: /var/www/pos/update.sh
# ==============================================================================
set -e

APP_DIR="/var/www/pos"
VENV_DIR="$APP_DIR/venv"

echo ">>> [1/5] Obteniendo últimos cambios de GitHub (main)..."
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
cd "$APP_DIR"
git pull origin main

echo ">>> [2/5] Actualizando dependencias de Python..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

echo ">>> [3/5] Aplicando migraciones de base de datos..."
"$VENV_DIR/bin/python" manage.py migrate --noinput

echo ">>> [4/5] Recopilando archivos estáticos de producción..."
"$VENV_DIR/bin/python" manage.py collectstatic --noinput

echo ">>> [5/5] Ajustando permisos y reiniciando servicio systemd 'pos'..."
sudo mkdir -p /var/log/pos
sudo chown -R www-data:www-data /var/log/pos
sudo chown -R www-data:www-data "$APP_DIR"
sudo chmod 664 "$APP_DIR/db.sqlite3" 2>/dev/null || true
sudo chmod 775 "$APP_DIR"

sudo systemctl restart pos
sudo systemctl status pos --no-pager

echo ""
echo "======================================================================"
echo ">>> ¡Actualización completada con éxito!"
echo ">>> POS activo en: https://pos.devsla.cl"
echo "======================================================================"
