#!/bin/bash
# CIERRE AUTOMÁTICO DE DÍA
# Añadir a crontab: 0 8 * * * /root/bot-transporte/Botttttt/cierre_automatico.sh >> /var/log/cierre_dia.log 2>&1

# Directorio del bot
BOT_DIR="/root/bot-transporte/Botttttt"
VENV_PYTHON="/root/bot-transporte/venv/bin/python3"

# Cambiar al directorio
cd "$BOT_DIR" || exit 1

# Cargar variables de entorno
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Ejecutar cierre
echo ""
echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') - CIERRE AUTOMÁTICO"
echo "=========================================="

$VENV_PYTHON cierre_dia.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Cierre completado"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ❌ Error en cierre (código: $EXIT_CODE)"
fi

echo "=========================================="
