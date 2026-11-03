# M-AUTO: образ для хостинга с Docker (RelaxDev и т.п.).
# Этап 1 собирает prod из исходников, этап 2 отдаёт его через Apache + PHP 8.3.
# Секреты не в образе: BOT_TOKEN, TG_CHAT_IDS и др. задаются переменными окружения проекта.
FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
RUN python3 scripts/build.py --env prod

FROM php:8.3-apache
RUN a2enmod rewrite headers expires deflate remoteip \
 && sed -ri 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
 && mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini" \
 && printf 'expose_php = Off\npost_max_size = 64K\n' > "$PHP_INI_DIR/conf.d/m-auto.ini" \
 && printf 'Listen 80\nListen 3000\nListen 8000\nListen 8080\n' > /etc/apache2/ports.conf \
 && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:*>/' /etc/apache2/sites-available/000-default.conf \
 && echo 'ServerName localhost' > /etc/apache2/conf-enabled/servername.conf
# платформа может проксировать на свой порт из $PORT: добавляем его при старте
COPY deploy/docker/start.sh /usr/local/bin/m-auto-start
COPY deploy/docker/apache-m-auto.conf /etc/apache2/conf-enabled/m-auto.conf
COPY --from=build /src/dist/ /var/www/html/
COPY deploy/docker/config.php /var/www/html/api/config.php
RUN rm -rf /var/www/html/api/config.example.php /var/www/html/api/storage \
 && mkdir -p /var/lib/m-auto/storage \
 && chown -R www-data:www-data /var/lib/m-auto \
 && chmod 750 /var/lib/m-auto/storage
EXPOSE 80
CMD ["m-auto-start"]
