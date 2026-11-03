#!/bin/sh
# Слушаем $PORT, если платформа его задала и его нет в ports.conf
if [ -n "${PORT:-}" ] && ! grep -qx "Listen ${PORT}" /etc/apache2/ports.conf; then
  echo "Listen ${PORT}" >> /etc/apache2/ports.conf
fi
exec apache2-foreground
