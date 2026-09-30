# KORE AGRO

Plataforma modular de gestion agroproductiva del ecosistema KORE de BINNSO,
desarrollada bajo una sola marca: **KORE Agro**.

Este repositorio contiene la implementacion actual y el mapa tecnico-funcional del
producto. Ganaderia y leche son la primera solucion operativa, no una aplicacion
separada ni el limite futuro de la plataforma.

## Mapa Del Documento

- [Vision e identidad comercial](#vision-del-producto).
- [Perfiles, capacidades y permisos](#modelo-de-configuracion).
- [Capacidades y flujo compartido](#mapa-de-capacidades).
- [Arquitectura modular](#arquitectura-modular-objetivo).
- [Estado de implementacion](#estado-de-implementacion).
- [Sincronizacion offline](#modelo-de-sincronizacion-offline).
- [Roadmap de plataforma](#roadmap-de-la-plataforma).
- [Desarrollo local](#desarrollo-local).

## Vision Del Producto

KORE Agro centraliza la operacion de empresas, asociaciones y organizaciones del
sector agro sin crear un sistema distinto para cada cadena productiva. Una misma
organizacion puede producir, acopiar, procesar y comercializar uno o varios productos.

El foco inicial es Ecuador y la primera vertical implementada atiende haciendas
ganaderas y lecheras de 30 a 250 cabezas. El nucleo debe crecer hacia cafe, cacao,
leche, granos, frutas y otras cadenas mediante perfiles, capacidades y reglas
configurables.

El objetivo es igualar la profundidad biologica de soluciones como UNIFORM-Agri o DairyComp, pero superarlas al integrar:

- Gestion biologica y economica del hato como primera solucion vertical.
- Operaciones compartidas de productores, recepcion, pesaje, calidad y lotes.
- P&L financiero real por animal, lote, potrero y hacienda.
- Operacion offline-first para trabajo de campo.
- Cumplimiento local: LOPDP, SRI Ecuador, Agrocalidad.
- Contexto andino y tropical: clima, pastoreo rotacional, doble proposito y sanidad local.

## Identidad Comercial

El producto siempre se presenta como **KORE Agro**. Las variantes comerciales son
soluciones configuradas sobre la misma plataforma y el mismo codigo:

- KORE Agro para Ganaderia.
- KORE Agro para Cafe.
- KORE Agro para Cacao.
- KORE Agro para Centros de Acopio.
- KORE Agro para Procesamiento y Comercializacion.

Estas variantes no deben convertirse en repositorios, despliegues o aplicaciones
independientes. Una mejora en un motor compartido debe beneficiar a todas las cadenas
que lo utilizan.

## Modelo De Configuracion

KORE Agro separa explicitamente cuatro conceptos:

| Concepto | Pregunta que responde | Ejemplo |
| --- | --- | --- |
| Organizacion o tenant | Quien es propietario y responsable de los datos | Hacienda, empresa, asociacion o cooperativa |
| Perfil de empresa | Que tipo de operacion realiza | Ganaderia, Cafe, Cacao, Centro de Acopio |
| Capacidad o modulo | Que funcionalidad tiene habilitada o contratada | Calidad, inventario, liquidaciones, ventas |
| Rol y permiso | Que puede consultar o ejecutar una persona | Propietario, administrador, tecnico, trabajador |

Una organizacion puede tener varios perfiles activos al mismo tiempo. Los perfiles
aportan contexto, vocabulario, formularios y reglas predeterminadas; las capacidades
habilitan funciones concretas. Los permisos se aplican despues y nunca sustituyen a
los perfiles ni a las capacidades.

Ejemplos:

- Una finca puede activar `Ganaderia` y `Centro de Acopio` para producir leche y
  recibir leche de terceros.
- Una asociacion puede activar `Cacao` y `Centro de Acopio`, con recepcion, calidad,
  lotes, liquidaciones, inventario y comercializacion.
- Dos centros de acopio pueden compartir perfil, pero contratar capacidades distintas.

La activacion debe validarse en navegacion, vistas, API y servicios de aplicacion. No
basta con ocultar una opcion del menu.

Modelo conceptual minimo para implementar esta capa:

- `ProfileDefinition`: catalogo versionado de perfiles disponibles.
- `OrganizationProfile`: perfiles activos para una organizacion, con vigencia.
- `CapabilityDefinition`: registro estable de capacidades y sus dependencias.
- `OrganizationCapability`: capacidades habilitadas, contratadas o suspendidas.
- `ProfileConfiguration`: parametros tipados por perfil, producto o unidad operativa.

La autorizacion efectiva se resuelve como la interseccion de:

```text
capacidad habilitada
  + compatibilidad con perfiles activos
  + permiso del usuario
  + alcance de finca/sede asignado
  = accion permitida
```

Los nombres comerciales y textos de interfaz pueden cambiar por perfil, pero las
claves internas de capacidades y eventos deben permanecer estables.

## Mapa De Capacidades

### Nucleo Compartido

- Organizaciones, sedes, fincas, ubicaciones y unidades operativas.
- Usuarios, roles, permisos, asignaciones de campo y dispositivos.
- Productores, clientes, proveedores y demas contrapartes.
- Productos, variedades, presentaciones y unidades de medida.
- Inventario, bodegas, movimientos, costos y documentos.
- Lotes, trazabilidad, auditoria, eventos y sincronizacion offline.
- Finanzas operativas, compras, ventas, cobros, pagos y reportes.

### Capacidades Por Perfil

| Perfil | Capacidades propias o especializadas |
| --- | --- |
| Ganaderia | Hato, genealogia, reproduccion, sanidad, pesajes, crecimiento, leche y pastoreo |
| Cafe | Productores, cosecha, recepcion, humedad, calidad, beneficio, lotes y trazabilidad |
| Cacao | Productores, recepcion, fermentacion, secado, calidad, lotes y trazabilidad |
| Centro de Acopio | Turnos, recepcion, pesaje, muestreo, calidad, liquidacion, almacenamiento y despacho |
| Procesamiento | Ordenes, transformaciones, consumos, rendimientos, mermas y subproductos |
| Comercializacion | Precios, contratos, pedidos, ventas, documentos, despacho y cartera |

Las capacidades compartidas se implementan una sola vez. Cada perfil agrega
configuracion y extensiones de dominio solo cuando una regla realmente es especifica.

## Flujo Agroproductivo Comun

El motor operativo objetivo reutiliza este flujo entre productos:

```text
Productor o proveedor
        |
        v
Recepcion -> Pesaje -> Control de calidad -> Lote -> Liquidacion
                                      |                    |
                                      v                    v
                              Inventario/Proceso      Cuenta por pagar
                                      |
                                      v
                            Venta -> Despacho -> Documento
```

Cafe, cacao, leche u otro producto deben compartir las entidades y servicios del
flujo. Las diferencias se expresan con definiciones de producto, unidades, esquemas
de calidad, conversiones, reglas de precio y pasos de proceso versionados. Se deben
evitar copias como `RecepcionCafe`, `RecepcionCacao` y `RecepcionLeche` cuando el
comportamiento base sea el mismo.

## Principios Arquitectonicos

- **Un producto y un codigo:** las cadenas productivas se configuran; no se bifurcan.
- **Monolito modular primero:** dominios cohesionados, contratos internos claros y
  posibilidad de extraer servicios solo cuando exista una necesidad comprobada.
- **Multi-tenant por schemas PostgreSQL:** cada organizacion tiene aislamiento fuerte;
  dentro de su tenant puede administrar varias fincas, sedes o unidades operativas.
- **Perfiles y capacidades combinables:** ninguna regla debe asumir que un tenant tiene
  un unico tipo de operacion.
- **Motores compartidos:** recepcion, pesaje, calidad, lotes, liquidaciones, inventario,
  costos, ventas, documentos y auditoria se reutilizan entre perfiles.
- **UUIDv4 en tablas transaccionales:** prohibido depender de IDs autoincrementales para entidades creadas desde campo.
- **Offline-first real:** la PWA registra eventos en una cola local FIFO y sincroniza cuando existe conectividad.
- **Event-driven para acciones de campo:** la aplicacion movil no debe mutar estados finales directamente; envia eventos que el backend valida, aplica y audita.
- **Costeo real en tiempo real:** toda accion biologica u operativa con impacto
  economico debe actualizar inventario, ingresos o costos segun corresponda.
- **Automatizacion asincrona:** Celery + Redis para integraciones gubernamentales, procesos de sync, alertas y calculos pesados.
- **Experiencia contextual:** menus, formularios, lenguaje, reportes y PWA muestran solo
  lo aplicable a los perfiles, capacidades y permisos del usuario.
- **Reglas en servidor:** ocultar controles no reemplaza la validacion de capacidades,
  permisos y tenant en API y servicios de aplicacion.

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

### Plataforma Compartida

- Tenancy, identidad, perfiles, capacidades, permisos y auditoria.
- Contrapartes: productores, proveedores, clientes, transportistas y asociaciones.
- Estructura territorial: fincas, sedes, parcelas, potreros, bodegas y puntos de acopio.
- Catalogo de productos, variedades, unidades, presentaciones y conversiones.
- Recepcion, pesaje, calidad, lotes, trazabilidad, liquidacion, inventario y despacho.
- Compras, ventas, costos, documentos, cartera y analitica operativa.

### Vertical Ganadera Inicial

- Hato, genealogia, lotes, potreros y ciclo de vida.
- Reproduccion: celos, IA, monta, diagnosticos, secados, partos y dias abiertos.
- Produccion lechera: registros por jornada, curvas de lactancia, RCS y calidad.
- Salud: historial clinico, vacunacion, podologia, tratamientos y retiros.
- Pesajes: condicion corporal, ganancia diaria, proyecciones y costo por kg ganado.
- Inventario ganadero: medicamentos, semen, balanceados y suplementos.

### Verticales Agroproductivas

- Cafe y cacao: productor, cosecha, recepcion, humedad, clasificacion, fermentacion,
  secado, almacenamiento, lotes y calidad.
- Acopio: turnos, recepcion, pesaje bruto/tara/neto, muestreo, descuentos,
  liquidaciones, inventario y despacho.
- Procesamiento: ordenes, transformaciones, rendimientos, mermas y subproductos.
- Comercializacion: listas de precios, contratos, pedidos, ventas, despacho y cartera.

### Diferenciadores KORE AGRO

- Costeo real y P&L por animal, lote, potrero y hacienda.
- Clima y pastoreo con temporadas lluviosa/seca, rotacion de potreros y aforos.
- Genetica adaptada para doble proposito Bos taurus x Bos indicus.
- Alertas de retiro de leche y eventos sanitarios obligatorios.
- Integraciones asincronas con INAMHI, MAG y Agrocalidad.
- Preparacion para facturacion electronica SRI Ecuador.
- Cumplimiento LOPDP desde el diseno de datos, auditoria y tenancy.

## Arquitectura Modular Objetivo

La siguiente estructura es el mapa de dominios, no una afirmacion de que todos los
paquetes ya estan implementados:

```text
apps/
  tenants/           # Organizaciones, schemas y contexto tenant-aware
  identity/          # Usuarios, roles, permisos, asignaciones y dispositivos
  configuration/     # Perfiles, capacidades, parametros y feature registry
  parties/           # Productores, proveedores, clientes y transportistas
  locations/         # Sedes, fincas, parcelas, potreros, bodegas y puntos de acopio
  catalog/           # Productos, variedades, unidades y conversiones
  reception/         # Entregas, turnos, pesaje bruto/tara/neto y comprobantes
  quality/           # Muestreo, esquemas de calidad, resultados y descuentos
  lots/              # Lotes fisicos, mezcla, division y trazabilidad
  settlements/       # Precios, bonificaciones, descuentos y liquidaciones
  inventory/         # Stock, movimientos, costos unitarios y lotes de insumo/producto
  processing/        # Transformaciones, rendimientos, mermas y subproductos
  commerce/          # Compras, ventas, pedidos, cartera y despacho
  documents/         # Comprobantes, guias, facturacion y archivos
  finance/           # P&L, centros de costo y trazabilidad economica
  herd/              # Animales, genealogia, lotes y ciclo de vida
  growth/            # Pesajes, ganancia diaria, proyecciones y comparacion por lote
  reproduction/      # Eventos reproductivos, proyecciones y listas de atencion
  milk/              # Ordenos, lactancias, calidad y RCS
  health/            # Clinica, tratamientos, vacunacion y retiro de leche
  grazing/           # Potreros, aforos, rotaciones, carga animal y clima
  audit/             # Bitacora transversal y trazabilidad de cambios
  integrations/      # INAMHI, MAG, Agrocalidad, SRI y adaptadores externos
  sync/              # Action Queue, eventos offline y resolucion de conflictos
  dashboard/         # Composicion contextual de vistas, menus y reportes
```

### Reglas Entre Dominios

- Cada dominio es propietario de sus modelos y reglas; otros dominios lo invocan por
  servicios de aplicacion o eventos, no escribiendo sus tablas directamente.
- Los modulos comunes no importan verticales especificas. Una extension ganadera o de
  cafe puede depender del nucleo, pero el nucleo no debe depender de ella.
- No se crea un modulo por cadena cuando las diferencias son solo etiquetas,
  parametros, unidades o reglas configurables.
- Las reglas variables por producto usan configuraciones tipadas y versionadas. Se
  evita convertir el dominio completo en campos JSON sin contrato.
- Un evento conserva origen, actor, organizacion, dispositivo, fecha efectiva y
  version de esquema para auditoria e idempotencia.
- Una futura extraccion a microservicio debe preservar estos contratos; no se crean
  microservicios antes de que escala, equipo o integracion lo justifiquen.

## Estado De Implementacion

| Area | Estado actual |
| --- | --- |
| Multi-tenancy por schema | Implementado |
| Roles, permisos por accion y asignacion de trabajador a hacienda | Implementado; configuracion del tenant en autoservicio y compras separadas por accion |
| Hato, lotes y fincas | Implementado en alcance ganadero inicial |
| Ordeño, reproduccion, sanidad y retiro de leche | Implementado |
| Pesajes, ganancia diaria, proyeccion e historial del animal | Implementado |
| Potreros, ocupacion, descanso y rotacion de lotes | Implementado en alcance operativo inicial |
| Personal, tareas, jornadas y costo de mano de obra | Implementado en alcance operativo inicial |
| Inventario, recepcion de insumos, consumos, ajustes y kardex | Implementado |
| P&L por hacienda, lote y animal | Implementado |
| PWA offline, cola FIFO, idempotencia y conflictos | Implementado; recepciones ligadas a orden aprobada |
| Panel superadmin, perfiles y registro de capacidades | Implementado en esquema publico |
| Menus, rutas, API y PWA gobernados por capacidades | Implementado |
| Auditoria transversal de actor, cambios, ruta y evento offline | Implementado |
| Productores y contrapartes compartidas | Base implementada; validada inicialmente con proveedores |
| Recepcion agroproductiva, calidad, lotes y liquidaciones | Por construir |
| Procesamiento, despacho y comercializacion general | Por construir |
| Proveedores, aprobaciones, recepciones, facturas, pagos y devoluciones | Implementado |

### Panel Superadmin

El plano de control de BINNSO vive en el esquema `public` y usa un dominio distinto
al de las organizaciones. Solo admite usuarios `is_superuser` del esquema publico.

Permite:

- Consultar organizaciones activas, en prueba y proximas a vencer.
- Crear el tenant, dominio y propietario inicial de una organizacion.
- Asignar varios perfiles operativos.
- Habilitar capacidades y sus dependencias tecnicas.
- Mantener el catalogo global de perfiles y capacidades.

Las capacidades activas se aplican dentro de cada tenant en cuatro niveles: menu
contextual, proteccion de URLs, catalogo de formularios de la PWA y validacion de cada
evento offline antes de registrarlo. Ocultar una opcion visual no sustituye la regla
del servidor.

Los propietarios creados dentro de un tenant no pueden ingresar al panel de
plataforma. La separacion se valida tanto por schema como por permisos.

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

## Roadmap De La Plataforma

El orden recomendado protege el producto actual y evita duplicar dominios al abrir
nuevas cadenas:

1. **Infraestructura de control:** panel superadmin, perfiles, capacidades,
   aprovisionamiento, permisos por accion y auditoria transversal implementados;
   continuar con observabilidad operativa.
2. **Consolidar Ganaderia:** pesajes, historial, potreros, rotacion, personal, tareas,
   proveedores, aprobaciones, cuentas por pagar y compras offline implementados.
3. **Construir el nucleo agroproductivo compartido:** contrapartes, catalogo,
   recepcion, pesaje, calidad, lotes, trazabilidad, liquidaciones y despacho.
4. **Activar Centro de Acopio:** primer perfil que pruebe el flujo compartido completo,
   inicialmente con una sola familia de producto.
5. **Agregar Cafe y Cacao:** incorporar esquemas de calidad, procesos y reglas de precio
   propias sin duplicar los motores comunes.
6. **Profundizar procesamiento y comercializacion:** transformaciones, rendimientos,
   contratos, cartera, documentos e integraciones regulatorias.

Cada etapa debe entregar un flujo vertical util, con pruebas de aislamiento tenant,
capacidades, trazabilidad y costos. No se deben crear todos los modelos genericos de
una vez sin una operacion real que los valide.

## Roadmap De La Solucion Ganadera Inicial

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
  - La PWA muestra primero el cache local, envia pendientes y despues actualiza sus catalogos.
  - No existe un modo manual online/offline: la transicion es automatica.
- Contexto de hacienda:
  - Cada trabajador de campo puede tener una `FieldAssignment` a una sola hacienda.
  - Con una hacienda asignada, los formularios la usan automaticamente y no la solicitan.
  - Propietarios y administradores con varias haciendas usan un selector global.
  - Bootstrap y sincronizacion validan el acceso a la hacienda en el servidor.
- Eventos core del MVP:
  - Ordeno diario: litros por vaca o por lote.
  - Pesaje con condicion corporal, ganancia diaria y proyeccion a peso objetivo.
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
- Registro central de perfiles y capacidades, sin condicionales de producto repetidos
  en plantillas, vistas y servicios.
- Dependencias orientadas desde verticales hacia motores compartidos, nunca al reves.
- Configuraciones de calidad, unidades y precios tipadas, validadas y versionadas.
- Pruebas de combinaciones de perfiles y capacidades, incluida la denegacion en API.
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
poetry run python manage.py bootstrap_platform --username superadmin --password "cambiar-esta-clave"
```

Servidor:

```powershell
poetry run python manage.py runserver 127.0.0.1:8000
# Si 8000 esta ocupado:
poetry run python manage.py runserver 127.0.0.1:8010
```

URLs locales:

- Panel superadmin: `http://127.0.0.1:8010/`
- Organizacion demo: `http://localhost:8010/`
- Dashboard administrativo: `http://localhost:8010/`
- Finanzas P&L: `http://localhost:8010/finanzas/`
- Pesajes y crecimiento: `http://localhost:8010/crecimiento/`
- Datos MVP: `http://localhost:8010/datos/`
- PWA de campo: `http://localhost:8010/field/`
- API bootstrap campo: `http://localhost:8010/api/field/bootstrap`
- API sync eventos: `http://localhost:8010/api/sync/events`

## Operacion De Piloto

- Liveness: `GET /health/`.
- Readiness de PostgreSQL: `GET /readiness/`.
- Para produccion, configurar `DJANGO_SETTINGS_MODULE=config.settings.production`, un
  `SECRET_KEY` seguro, hosts permitidos, HTTPS, PostgreSQL y Redis administrados.
- Ejecutar un worker con `poetry run celery -A config.celery worker -l info` cuando Redis
  este disponible. No ejecutar tareas de SRI sin el certificado y adaptador configurados.

### Despliegue Con Docker

1. Copiar `.env.production.example` como `.env.production` y completar secretos, dominio y
   conexiones reales.
2. Ejecutar `docker compose -f docker-compose.production.yml up --build -d`.
3. Publicar solo el puerto del servicio `web` detras de un proxy TLS y comprobar
   `GET /health/` y `GET /readiness/` antes de aceptar trafico.
4. Programar backups externos de `postgres_data`; el volumen local no sustituye una copia
   recuperable fuera del servidor.

La guia completa de primer despliegue, actualizaciones, backups, restauracion y monitoreo
esta en [`docs/OPERACION_PRODUCCION.md`](docs/OPERACION_PRODUCCION.md). El repositorio incluye
scripts con verificacion de integridad para backup/restauracion y un smoke test para validar
la aplicacion despues de cada despliegue.

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
- Crecimiento aplicado: pesajes online/offline, ganancia diaria, proyeccion y costo directo/kg.
- Historia del animal aplicada: linea de tiempo unificada de peso, reproduccion, salud,
  leche, inventario y finanzas.
- Vision de plataforma definida: una marca, perfiles combinables, capacidades
  contratables y motores agroproductivos compartidos.
- Panel superadmin aplicado en el esquema publico con aprovisionamiento de tenants.
- Compras aplicado: contrapartes, aprobacion, recepcion parcial online/offline, facturas,
  pagos, devoluciones e ingreso trazable a bodega.
- Auditoria aplicada: actor, entidad, cambios, ruta, IP y evento offline por tenant.
- Permisos aplicados: propietario aprueba y paga; administrador solicita, recibe y factura;
  trabajador de campo recibe ordenes autorizadas desde la PWA.
- Configuracion autoservicio aplicada: el propietario mantiene organizacion, usuarios, roles
  y asignaciones; el administrador actualiza los parametros operativos de la hacienda.

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
| `procurement.purchase_received` | Recibe saldo de una orden aprobada | Activa inventario y conserva la cuenta por pagar |
| `inventory.stock_adjusted` | Corrige conteo fisico | Faltante = merma; sobrante = solo stock |
| `finance.expense_recorded` | Ninguno | Mano de obra, servicios y fletes |
| `herd.animal_sold` | Marca el animal como vendido | Ingreso por venta de animal |
| `growth.weight_recorded` | Registra peso, condicion y lote historico | Permite costo directo por kg ganado |

### Regla De Retiro De Leche

La leche de un animal con retiro activo se registra para trazabilidad biologica
pero **nunca** genera ingreso: queda marcada como descartada y el motor financiero
reporta `discarded_liters` y `discarded_value`. Por eso el P&L expone dos costos
por litro: `cost_per_liter` sobre lo producido y `cost_per_saleable_liter` sobre
lo realmente vendible.

## Decisiones Pendientes

- Catalogo inicial de perfiles y capacidades comercializables.
- Primer producto para validar el motor comun de centro de acopio.
- Modelo de contrapartes y relacion productor-organizacion.
- Versionado de esquemas de calidad, conversiones y reglas de liquidacion.
- Politicas de conflicto offline para recepciones, pesajes y lotes compartidos.
- Estrategia de migracion de `Farm` hacia una estructura comun de sedes y ubicaciones
  sin romper el dominio ganadero existente.
- Precio de leche y estructura de costos inicial para pilotos.
- Alcance juridico final de guias de movilizacion y firma electronica SRI.
