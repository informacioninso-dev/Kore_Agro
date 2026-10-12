# Memoria Permanente de KORE Agro

Este archivo conserva decisiones y aprendizajes que deben sobrevivir entre sesiones.
No es una bitácora cronológica ni reemplaza al roadmap de `README.md`.

## Identidad y objetivo

- El nombre del producto es **KORE Agro**, bajo la marca BINNSO.
- Es una plataforma agroproductiva modular; ganadería y leche son la primera vertical,
  no una aplicación separada.
- El mercado inicial son haciendas ganaderas y lecheras medianas de Ecuador, con
  operación andina y tropical.
- El valor principal del MVP es conectar control biológico, inventario y costo real en
  un P&L operativo comprensible para el dueño.

## Decisiones permanentes

- Un solo producto y un solo código para varias cadenas productivas.
- Monolito modular antes que microservicios.
- PostgreSQL multi-tenant por schemas para aislamiento organizacional.
- UUIDv4 universal en transacciones y eventos originados en campo.
- Sincronización offline basada en eventos idempotentes y una cola FIFO local.
- Django conserva la autoridad sobre reglas, permisos, capacidades y resolución de
  conflictos.
- Cada consumo de inventario con impacto económico debe llegar al P&L mediante una
  trazabilidad auditable.
- Los motores compartidos no dependen de verticales específicas.
- Las integraciones externas deben degradar de forma controlada y no bloquear la
  operación principal.
- El repositorio remoto `origin/main` es la fuente autoritativa del código compartido.

## Experiencia de producto

- Administración: interfaz ejecutiva, sobria, densa y orientada a decisiones con HTMX
  y Tailwind.
- Campo: interfaz móvil de mínima fricción, usable sin conexión y con estados de
  sincronización explícitos.
- Modo oscuro de alto contraste y tipografía Atkinson Hyperlegible servida localmente.
- Evitar tarjetas anidadas, decoración gratuita y patrones visuales genéricos que
  reduzcan la lectura operativa.
- Las funciones visibles dependen de perfil, capacidad, permiso y alcance asignado.
- Toda acción destructiva o que retire datos de la operación diaria debe explicar su
  consecuencia y pedir confirmación antes de enviarse.
- Una función fiscal no configurada debe presentarse como no disponible; nunca simular
  autorización ni confundir un borrador con un documento enviado.

## Reglas de dominio que no deben perderse

- La leche bajo retiro sanitario se registra biológicamente, pero no genera ingreso.
- El consumo de bodega descuenta stock y reconoce el costo en el mismo flujo trazable.
- Los eventos offline se procesan una sola vez mediante `event_id`.
- La hacienda o unidad operativa forma parte del alcance de autorización, no es solo un
  filtro visual.
- P&L, listas de atención e inventario se calculan desde hechos del dominio, no desde
  cifras manuales desconectadas.

## Aprendizajes de ingeniería

- Verificar migraciones faltantes con `makemigrations --check --dry-run` antes de cerrar
  una entrega.
- Probar aislamiento tenant e idempotencia como contratos, no como detalles internos.
- Mantener adaptadores externos detrás de límites de tiempo, tamaño y cache.
- Preferir servicios de aplicación transaccionales para acciones que cruzan dominios.
- Consolidar documentación: primero actualizar `README.md`, `MEMORY.md` o una guía
  temática existente; crear otro archivo solo si ninguno tiene el propósito correcto.
- Antes de una demostración, ejecutar `check_pilot_readiness` contra el dominio del
  tenant; una pantalla accesible no basta si faltan usuario, capacidades o datos base.

## Decisiones aún abiertas

- Catálogo comercial definitivo de perfiles y capacidades.
- Primer producto para validar el motor común de centro de acopio.
- Versionado de calidad, conversiones y reglas de liquidación.
- Política de conflictos para recepciones, pesajes y lotes compartidos.
- Migración de `Farm` hacia una estructura común de sedes y ubicaciones.
- Alcance jurídico final de guías de movilización y firma electrónica SRI.

## Cómo mantener esta memoria

- Agregar solo decisiones confirmadas, restricciones duraderas o lecciones repetibles.
- Actualizar una entrada cuando cambie; no añadir otra versión contradictoria.
- No guardar contraseñas, tokens, datos personales, puertos temporales, PIDs ni estados
  locales que caduquen.
- Los avances de implementación pertenecen a la tabla de estado y al roadmap de
  `README.md`; los procedimientos pertenecen a `docs/`.
