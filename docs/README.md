# Documentación de KORE Agro

Índice único de documentación permanente. La visión, arquitectura, estado y roadmap
general viven en el [`README.md`](../README.md) raíz.

## Mapa documental

| Documento | Propósito | Actualizar cuando |
| --- | --- | --- |
| [`README.md`](../README.md) | Visión, arquitectura, alcance, estado y roadmap | Cambie el producto, una capacidad o el estado general |
| [`AGENTS.md`](../AGENTS.md) | Reglas de trabajo para agentes y colaboradores | Cambie el flujo de desarrollo o gobierno documental |
| [`MEMORY.md`](../MEMORY.md) | Decisiones y aprendizajes permanentes | Se confirme o sustituya una decisión duradera |
| [`ESTANDAR_DE_PRODUCTO.md`](ESTANDAR_DE_PRODUCTO.md) | Sistema visual y criterios de experiencia | Cambien tokens, patrones o criterios visuales |
| [`OPERACION_PRODUCCION.md`](OPERACION_PRODUCCION.md) | Despliegue, actualización, backup y monitoreo | Cambie la operación de producción |
| [`SEGURIDAD.md`](SEGURIDAD.md) | Controles y verificaciones de seguridad | Cambie un control, riesgo o requisito de publicación |
| [`INFORMACION_EXTERNA.md`](INFORMACION_EXTERNA.md) | Fuentes oficiales e integraciones externas | Cambie una fuente, adaptador o política de integración |

## Dónde documentar

- Decisión de producto o arquitectura: `README.md`.
- Lección reutilizable o restricción permanente: `MEMORY.md`.
- Convención de trabajo de agentes: `AGENTS.md`.
- Operación, seguridad, UI o integraciones: guía temática existente en `docs/`.
- Detalle cercano al código: docstring, comentario breve o prueba ejecutable.

## Regla de crecimiento

Antes de crear otro archivo Markdown, comprobar que la información no cabe en uno de
los documentos anteriores. Un documento nuevo solo se justifica si tiene propósito,
audiencia y ciclo de mantenimiento propios. Cuando se cree, debe añadirse a esta tabla
en el mismo cambio.

No se conservan en el repositorio notas de sesión, borradores temporales, copias de
planes, reportes generados ni documentación duplicada por sprint o módulo.
