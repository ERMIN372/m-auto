#!/bin/sh
# Слушаем $PORT, если платформа его задала и его нет в ports.conf
if [ -n "${PORT:-}" ] && ! grep -qx "Listen ${PORT}" /etc/apache2/ports.conf; then
  echo "Listen ${PORT}" >> /etc/apache2/ports.conf
fi
# раз в минуту досылаем в Telegram то, что не ушло из-за обрыва связи
(
  while true; do
    sleep 60
    su -p -s /bin/sh www-data -c "php /usr/local/lib/m-auto/tg_retry.php" || true
  done
) &
exec apache2-foreground
