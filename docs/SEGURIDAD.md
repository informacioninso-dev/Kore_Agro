# Seguridad de KORE Agro

## Controles incluidos

- HTTPS obligatorio, HSTS, cookies seguras y validacion de `SECRET_KEY` en produccion.
- CSP, `Permissions-Policy`, proteccion anti-frame y recursos frontend servidos localmente.
- CSRF en formularios y API de campo, con redirecciones posteriores al login limitadas al dominio.
- Bloqueo temporal tras intentos repetidos de acceso, compartido entre workers mediante Redis.
- Permisos por rol, capacidad, tenant y hacienda para vistas y sincronizacion offline.
- Maximo de 5 dispositivos por usuario y 100 eventos por lote de sincronizacion.
- Almacenamiento offline separado por tenant y usuario.
- Descargas externas limitadas por HTTPS, dominio, tamano y parser XML seguro.
- Contenedores de aplicacion sin privilegios, sin capacidades Linux y con sistema de archivos de solo lectura.

## Antes de publicar

1. Crear `.env.production` desde el ejemplo y generar valores unicos para `SECRET_KEY`, usuario y contrasena de PostgreSQL.
2. No usar `dueno / dueno1234` ni las credenciales de demostracion en produccion.
3. Publicar solo `80/443`; el contenedor web queda ligado a `127.0.0.1` para recibir trafico desde Nginx o Caddy.
4. Configurar TLS valido y mantener `CSRF_TRUSTED_ORIGINS` y `ALLOWED_HOSTS` con el dominio exacto.
5. Proteger copias de seguridad con cifrado, acceso restringido y una prueba periodica de restauracion.
6. Mantener PostgreSQL y Redis sin puertos publicos y restringir SSH mediante llaves y firewall.

## Verificacion periodica

```powershell
poetry install
python manage.py check --deploy --settings=config.settings.production
python -m pytest -q
py -3.12 -m pip_audit --path .venv\Lib\site-packages
npm audit
py -3.12 -m bandit -r apps config -x "*/migrations/*" -q
```

Revisar dependencias al menos una vez al mes y antes de cada despliegue. Rotar inmediatamente secretos o sesiones si existe sospecha de acceso no autorizado.
