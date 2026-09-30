# Operacion De Produccion

Esta guia cubre la entrega tecnica del MVP de KORE Agro. El servidor debe ser Linux con
Docker Engine, Docker Compose v2, un dominio apuntando al servidor y un proxy TLS externo.

## 1. Configuracion

1. Copiar `.env.production.example` como `.env.production`.
2. Generar `SECRET_KEY` con al menos 50 caracteres aleatorios.
3. Cambiar las credenciales de PostgreSQL.
4. Configurar `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` y `HEALTHCHECK_HOST` con el dominio
   real. `HEALTHCHECK_HOST` debe coincidir con un dominio registrado en KORE Agro.
5. Mantener `.env.production` fuera de Git y limitar su lectura al usuario del despliegue.

## 2. Primer Despliegue

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
docker compose --env-file .env.production -f docker-compose.production.yml exec web \
  python manage.py bootstrap_platform \
  --domain admin.agro.example.com \
  --username superadmin \
  --password 'CAMBIAR-POR-UNA-CLAVE-SEGURA'
```

El proxy TLS debe enviar `X-Forwarded-Proto: https` y publicar solamente el servicio web.
PostgreSQL y Redis no deben exponerse a Internet.

Verificar el despliegue:

```bash
BASE_URL=https://admin.agro.example.com scripts/smoke_test.sh
docker compose --env-file .env.production -f docker-compose.production.yml ps
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 web worker
```

## 3. Actualizacion

```bash
scripts/backup_database.sh
git pull --ff-only origin main
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
BASE_URL=https://admin.agro.example.com scripts/smoke_test.sh
```

El servicio `migrate` aplica migraciones y recolecta archivos estaticos antes de iniciar
la nueva version web. No ejecutar dos despliegues al mismo tiempo.

## 4. Backups

Programar `scripts/backup_database.sh` diariamente. El script crea un dump completo de
PostgreSQL, genera SHA-256 y elimina copias locales antiguas segun
`BACKUP_RETENTION_DAYS`. Copiar cada backup a almacenamiento externo cifrado; el disco del
servidor no cuenta como segunda copia.

Ejemplo de cron a las 02:15:

```cron
15 2 * * * cd /opt/kore-agro && BACKUP_RETENTION_DAYS=14 scripts/backup_database.sh >> /var/log/kore-agro-backup.log 2>&1
```

Probar una restauracion al menos una vez por mes en un servidor aislado:

```bash
CONFIRM_RESTORE=RESTORE_KORE_AGRO scripts/restore_database.sh backups/kore_agro_FECHA.dump
```

La restauracion detiene temporalmente web y worker, valida el checksum si existe, restaura
todos los schemas, aplica migraciones y vuelve a iniciar los servicios.

## 5. Monitoreo Minimo

- Consultar `/health/` cada minuto para verificar el proceso web.
- Consultar `/readiness/` para verificar web y PostgreSQL.
- Alertar por estado `unhealthy`, reinicios repetidos, disco mayor al 80% y errores 5xx.
- Conservar los logs fuera del servidor si el piloto se vuelve operacion permanente.
- Revisar que el backup diario exista y tenga tamano mayor a cero.

## 6. Datos Que Debe Entregar El Responsable

- Dominio definitivo y acceso DNS.
- Servidor o proveedor de nube.
- Correo y clave inicial del superadministrador.
- Datos de la primera organizacion y su propietario.
- Certificado, clave y adaptador autorizado antes de activar envios al SRI.

Sin certificado ni `SRI_ADAPTER_CLASS`, KORE Agro conserva las facturas en borrador y
rechaza el envio; no simula autorizaciones fiscales.
