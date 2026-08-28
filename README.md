# KORE AGRO

ERP agricola integral para haciendas ganaderas y lecheras medianas en la region andina y tropical, desarrollado bajo la marca Binnso: "Soluciones a tu medida".

Este repositorio sera el roadmap tecnico y funcional del producto. Aunque los modulos aun no esten construidos, este documento define la direccion arquitectonica, las restricciones de stack y el criterio de desarrollo para KORE AGRO.

## Vision Del Producto

KORE AGRO busca democratizar la toma de decisiones basada en datos para haciendas de 30 a 250 cabezas, con foco inicial en Ecuador.

El objetivo es igualar la profundidad biologica de soluciones como UNIFORM-Agri o DairyComp, pero superarlas al integrar:

- Gestion biologica del hato.
- P&L financiero real por animal, lote, potrero y hacienda.
- Operacion offline-first para trabajo de campo.
- Cumplimiento local: LOPDP, SRI Ecuador, Agrocalidad.
- Contexto andino y tropical: clima, pastoreo rotacional, doble proposito y sanidad local.

## Principios Arquitectonicos

- **Multi-tenant por schemas PostgreSQL:** aislamiento fuerte de datos por cliente/hacienda para cumplimiento LOPDP.
- **UUIDv4 en tablas transaccionales:** prohibido depender de IDs autoincrementales para entidades creadas desde campo.
- **Offline-first real:** la PWA registra eventos en una cola local FIFO y sincroniza cuando existe conectividad.
- **Event-driven para acciones de campo:** la aplicacion movil no debe mutar estados finales directamente; envia eventos que el backend valida, aplica y audita.
- **Costeo real en tiempo real:** toda accion biologica con impacto economico debe descontar inventario y registrar costo.
- **Automatizacion asincrona:** Celery + Redis para integraciones gubernamentales, procesos de sync, alertas y calculos pesados.
- **Interfaces sobrias:** frontend administrativo con HTMX + Tailwind CSS, dark mode ejecutivo, alta densidad de informacion y minima friccion operativa.

## Stack Tecnologico Obligatorio

- **Backend:** Python 3.12+, Django ultima version estable.
- **Dependencias:** Poetry.
- **Base de datos:** PostgreSQL con arquitectura multi-tenant basada en schemas.
- **Frontend administrativo:** HTMX + Tailwind CSS.
- **Frontend campo:** PWA offline-first con Service Workers.
- **Base local movil:** IndexedDB usando Dexie.js o equivalente.
- **API de sincronizacion PWA:** Django Ninja o endpoints REST equivalentes.
- **Asincronia:** Celery + Redis.
- **Automatizacion y scraping:** Playwright con Python cuando no existan APIs oficiales.

## Dominios Funcionales

### Core Biologico

- Gestion de hato y genealogia.
- Reproduccion: celos, IA, monta natural, diagnosticos de prenez, secados, partos y dias abiertos.
- Produccion lechera: registros por jornada, curvas de lactancia, RCS y calidad.
- Salud y veterinaria: historiales clinicos, vacunacion, podologia y tratamientos.
- Inventario y bodega: medicamentos, semen, balanceados, concentrados y suplementos.

### Diferenciadores KORE AGRO

- Costeo real y P&L por animal, lote, potrero y hacienda.
- Clima y pastoreo con temporadas lluviosa/seca, rotacion de potreros y aforos.
- Genetica adaptada para doble proposito Bos taurus x Bos indicus.
- Alertas de retiro de leche y eventos sanitarios obligatorios.
- Integraciones asincronas con INAMHI, MAG y Agrocalidad.
- Preparacion para facturacion electronica SRI Ecuador.
- Cumplimiento LOPDP desde el diseno de datos, auditoria y tenancy.

## Arquitectura Objetivo

```text
apps/
  tenants/          # Clientes, haciendas, schemas y contexto tenant-aware
  identity/         # Usuarios, roles, permisos y auditoria
  herd/             # Animales, genealogia, lotes, potreros y ciclo de vida
  reproduction/     # Eventos reproductivos, proyecciones y listas de atencion
  milk/             # Ordenos, lactancias, calidad y RCS
  health/           # Clinica, tratamientos, vacunacion y retiro de leche
  inventory/        # Stock, movimientos, costos unitarios y lotes de insumo
  finance/          # P&L operativo, centros de costo y trazabilidad economica
  grazing/          # Potreros, aforos, rotaciones, carga animal y clima
  integrations/     # INAMHI, MAG, Agrocalidad, SRI
  sync/             # Action Queue, eventos offline, resolucion de conflictos
```

## Modelo De Sincronizacion Offline

La PWA de campo debe capturar acciones como eventos inmutables:

```json
{
  "event_id": "uuid-v4",
  "tenant_id": "uuid-v4",
  "device_id": "uuid-v4",
  "actor_id": "uuid-v4",
  "occurred_at": "2026-08-28T10:30:00-05:00",
  "event_type": "reproduction.birth_registered",
  "payload": {
    "dam_id": "uuid-v4",
    "calf_id": "uuid-v4",
    "birth_type": "single",
    "calf_sex": "female"
  },
  "client_sequence": 128,
  "schema_version": 1
}
```

El backend debe:

- Validar idempotencia por `event_id`.
- Aplicar reglas de negocio por tipo de evento.
- Resolver conflictos con politica explicita por dominio.
- Registrar auditoria completa.
- Devolver ack, errores recuperables o conflictos al cliente.

## Roadmap De Desarrollo

### Fase 0 - Fundacion Tecnica

- Scaffold Django + Poetry.
- Configuracion PostgreSQL multi-tenant por schemas.
- Modelo base UUID, auditoria, timestamps y soft delete cuando aplique.
- Middleware tenant-aware.
- Celery + Redis.
- Tailwind + HTMX.
- PWA base con Service Worker, Dexie.js y cola local de eventos.
- Pipeline inicial de pruebas y convenciones de calidad.

### Fase 1 - MVP: Control y Costo Real

Objetivo de negocio: demostrar en el primer mes que KORE AGRO puede pagar su propia suscripcion al reducir perdida operativa, mejorar disciplina reproductiva y mostrar costo real por litro.

El MVP se divide en dos frentes funcionales cerrados:

1. Frontend de campo para el mayordomo.
2. Frontend administrativo para el dueno.

#### A. Frontend De Campo - PWA Offline

Objetivo: reemplazar el cuaderno de campo con minima friccion y operacion sin internet.

Alcance funcional:

- Gestion de hato base:
  - Ficha simplificada del animal.
  - Arete.
  - Estado.
  - Dias en leche.
  - Lote.
- Action Queue offline:
  - Cada accion se guarda primero en IndexedDB.
  - Cada evento usa UUIDv4 generado en cliente.
  - La cola se transmite FIFO cuando vuelve la conectividad.
  - El backend valida idempotencia, aplica reglas de negocio y responde ack/conflicto/error recuperable.
- Eventos core del MVP:
  - Ordeno diario: litros por vaca o por lote.
  - Celo.
  - Inseminacion o monta.
  - Parto.
  - Secado.
  - Tratamiento sanitario con alerta de retiro en leche.
- Bodega operativa:
  - Consumo de insumos desde campo.
  - Ejemplos: sacos de balanceado, dosis de vacunas, medicamentos, pajuelas.
  - Cada consumo descuenta inventario y genera costo asociado al animal, lote o hacienda.

#### B. Frontend Administrativo - Django/HTMX

Objetivo: entregar visibilidad ejecutiva del P&L biologico-operativo sin esperar a un modulo contable completo.

Alcance funcional:

- Multi-tenant base:
  - PostgreSQL con schemas usando `django-tenants`.
  - Aislamiento por cliente/hacienda desde el dia 1.
  - Modelos transaccionales con UUIDv4.
- Dashboard de P&L:
  - Litros registrados x precio de venta.
  - Menos balanceado consumido.
  - Menos medicinas consumidas.
  - Resultado: costo por litro, margen bruto operativo y utilidad neta operativa.
  - Corte minimo por hacienda, lote y periodo.
- Listas de accion diaria:
  - Vacas para secar hoy.
  - Vacas para chequeo de prenez.
  - Vacas con retiro de leche activo.
  - Animales con tratamientos pendientes.
- Cumplimiento SRI basico:
  - Facturacion electronica solo para venta de leche a planta acopiadora.
  - Guias de movilizacion de animales.
  - Sin compras, retenciones complejas ni contabilidad completa en MVP.

#### Criterios De Aceptacion Del MVP

- Un mayordomo puede registrar eventos esenciales sin internet y sincronizarlos luego.
- El dueno puede ver litros, costos, costo por litro y utilidad operativa sin consolidaciones manuales.
- Un consumo de bodega impacta inventario y P&L en la misma trazabilidad.
- Una accion sanitaria puede activar retiro de leche visible en campo y oficina.
- El sistema puede operar con multiples tenants aislados por schema.
- Las listas de accion diaria se generan desde reglas reproductivas y sanitarias, no desde tareas manuales aisladas.

#### Arquitectura Del Primer Sprint

Construccion de adentro hacia afuera:

1. Semana 1:
   - Setup Django + Poetry.
   - PostgreSQL multi-tenant con `django-tenants`.
   - Configuracion base HTMX/Tailwind.
   - Celery + Redis.
2. Semana 2:
   - Modelos core: Tenant, Hacienda, Animal, Lote, Insumo, Inventario y Evento.
   - Base UUID, auditoria y timestamps.
   - Primeras migraciones tenant-aware.
   - CRUD HTMX para cargar haciendas, lotes, animales, insumos y stock inicial.
   - Pruebas de aislamiento tenant, idempotencia offline, P&L y retiro de leche.
3. Semanas 3-4:
   - Motor financiero y de costos.
   - Cruce de litros, consumos biologicos, inventario y P&L.
   - Servicios de aplicacion para registrar eventos con impacto economico.
4. Semanas 5-6:
   - PWA de campo.
   - IndexedDB con Dexie.js.
   - Service Worker.
   - UI movil.
   - Endpoints REST/Django Ninja para recibir cola de eventos.
5. Semana 7:
   - Integracion SRI basica para venta de leche.
   - Guias de movilizacion de animales.

### Fuera Del MVP

Estas capacidades quedan explicitamente fuera de la Fase 1 para proteger time-to-market:

- Integracion de hardware de ordeno.
- Lectura de CSVs o APIs de medidores DeLaval, Lely o BouMatic.
- Microservicios de datos publicos con INAMHI, MAG y Agrocalidad.
- Alertas predictivas basadas en datos publicos.
- Modulo avanzado de pasturas, biomasa, aforos y rotacion inteligente.
- Genealogia profunda de 4 generaciones.
- Genomica y calculos avanzados de consanguinidad.
- Nomina agricola, destajo, horas extras y seguridad social.

### Fase 2 - Profundizacion Biologica

- Curvas de lactancia.
- RCS y calidad de leche.
- Protocolos veterinarios parametrizables.
- Calendarios sanitarios.
- Podologia.
- Integracion de hardware de ordeno o importacion CSV/API.
- Microservicios de datos publicos: INAMHI, MAG y Agrocalidad.
- Pasturas y clima: biomasa, aforos y rotacion inteligente.
- Reportes reproductivos comparables con software especializado.

### Fase 3 - Contexto Andino Y Regulacion

- Eventos sanitarios obligatorios.
- Tiempos de retiro de leche.
- Genealogia profunda.
- Genomica y cruces consanguineos.
- Nomina agricola.
- Ampliacion de facturacion electronica SRI.
- Reporteria LOPDP y auditoria avanzada.

### Fase 4 - Inteligencia Operativa

- Prediccion de riesgo reproductivo.
- Alertas por desviacion productiva.
- Recomendaciones de descarte.
- Simulacion de carga animal y rotacion de potreros.
- Analitica economica avanzada por centro de costo.

## Criterios De Diseno De Software

- Modelos de dominio explicitos y auditables.
- Servicios de aplicacion para reglas complejas; evitar logica critica dispersa en vistas.
- Vistas administrativas HTMX simples, rapidas y orientadas a decision.
- Tareas Celery idempotentes.
- Integraciones externas desacopladas mediante adaptadores.
- Eventos offline versionados y compatibles hacia atras.
- Pruebas focalizadas en reglas reproductivas, costos, inventario, tenancy y sincronizacion.

## Desarrollo Local

El proyecto usa un entorno virtual local en `.venv` con Python 3.12.

Comandos base:

```powershell
py -3.12 -m venv .venv
poetry config virtualenvs.in-project true --local
poetry env use .\.venv\Scripts\python.exe
poetry install
```

Base de datos local:

```powershell
poetry run python -c "import psycopg; conn=psycopg.connect('postgresql://postgres:postgres@localhost:5432/postgres', autocommit=True); conn.execute('CREATE DATABASE kore_agro'); conn.close()"
poetry run python manage.py migrate_schemas --shared
poetry run python manage.py bootstrap_demo_tenant
```

Servidor:

```powershell
poetry run python manage.py runserver 127.0.0.1:8000
# Si 8000 esta ocupado:
poetry run python manage.py runserver 127.0.0.1:8010
# En esta sesion se uso:
poetry run python manage.py runserver 127.0.0.1:8020
```

URLs locales:

- Dashboard administrativo: `http://localhost:8000/`
- Finanzas P&L: `http://localhost:8000/finanzas/`
- Datos MVP: `http://localhost:8000/datos/`
- PWA de campo: `http://localhost:8000/field/`
- API bootstrap campo: `http://localhost:8000/api/field/bootstrap`
- API sync eventos: `http://localhost:8000/api/sync/events`
- Servidor activo en esta sesion: `http://localhost:8020/`

Validaciones:

```powershell
poetry run ruff check apps config manage.py tests
poetry run python -m compileall apps config manage.py tests
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run pytest -q
```

Estado actual:

- `.venv` creado con Python 3.12.
- Dependencias instaladas con Poetry.
- PostgreSQL local contiene la base `kore_agro`.
- Tenant demo creado en schema `demo` con dominio `localhost`.
- Datos demo: hacienda, lote de produccion, 3 animales, 3 insumos y stock inicial.
- Flujo validado: evento offline de ordeno genera litros e ingreso operativo.
- Flujo validado: consumo de bodega descuenta stock y actualiza P&L.
- Semana 2 aplicada: CRUD HTMX en `/datos/` para datos maestros del MVP.
- Semana 2 aplicada: suite inicial de pruebas automatizadas con 5 casos core.
- Semana 3 aplicada: motor financiero por periodo, hacienda, lote y animal.
- Semana 3 aplicada: P&L diario, breakdown de costos y trazabilidad por evento offline.
- Semana 3 aplicada: pantalla ejecutiva HTMX en `/finanzas/`.
- Semana 4 aplicada: servicios de aplicacion para todo evento con impacto economico.
- Semana 4 aplicada: recepcion de insumos con costo promedio ponderado por lote.
- Semana 4 aplicada: ajuste de inventario; el faltante se reconoce como merma en el P&L.
- Semana 4 aplicada: gasto operativo directo y venta de animal desde `/finanzas/`.
- Semana 4 aplicada: el retiro de leche descarta el ingreso y reporta litros y valor perdido.
- Semana 4 aplicada: cierre de periodo automatizado con Celery, idempotente por tenant.
- Semana 4 aplicada: kardex de movimientos de bodega en `/datos/`.
- Semana 4 corregida: migracion faltante de `OperatingPeriodSnapshot` (venia rota de Semana 3).

## Eventos Con Impacto Economico

El backend acepta estos `event_type` desde la cola offline en `/api/sync/events`.
Todos son idempotentes por `event_id` y quedan trazados en `/finanzas/`.

| `event_type` | Efecto biologico | Efecto economico |
| --- | --- | --- |
| `milk.milking_recorded` | Registra litros por vaca o lote | Ingreso, salvo retiro de leche activo |
| `reproduction.*_recorded` | Celo, servicio, parto, secado | Ninguno directo |
| `health.treatment_recorded` | Tratamiento y retiro de leche | Consumo de insumo y costo |
| `inventory.input_consumed` | Descuenta stock FIFO | Costo por categoria de insumo |
| `inventory.input_received` | Ingresa stock y repondera costo | Ninguno: el costo llega al consumir |
| `inventory.stock_adjusted` | Corrige conteo fisico | Faltante = merma; sobrante = solo stock |
| `finance.expense_recorded` | Ninguno | Mano de obra, servicios y fletes |
| `herd.animal_sold` | Marca el animal como vendido | Ingreso por venta de animal |

### Regla De Retiro De Leche

La leche de un animal con retiro activo se registra para trazabilidad biologica
pero **nunca** genera ingreso: queda marcada como descartada y el motor financiero
reporta `discarded_liters` y `discarded_value`. Por eso el P&L expone dos costos
por litro: `cost_per_liter` sobre lo producido y `cost_per_saleable_liter` sobre
lo realmente vendible.

## Decisiones Pendientes

- Politicas de conflicto por dominio offline.
- Estructura comercial por tenant: hacienda unica, multi-hacienda o grupo empresarial.
- Precio de leche y estructura de costos inicial para pilotos.
- Alcance juridico final de guias de movilizacion y firma electronica SRI.
