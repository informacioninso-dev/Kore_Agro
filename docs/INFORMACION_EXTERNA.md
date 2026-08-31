# Información externa para KORE Agro

## Objetivo

KORE puede informar a la finca sobre clima, campañas sanitarias y cambios regulatorios. No reemplaza a Agrocalidad, INAMHI, SRI, un veterinario ni asesoría legal. La información externa orienta y enlaza a la fuente; no ejecuta tratamientos, movimientos o declaraciones automáticamente.

## Fuentes candidatas verificadas

| Tema | Fuente oficial | Forma disponible | Uso propuesto | Estado |
| --- | --- | --- | --- | --- |
| Clima y alertas | [INAMHI](https://servicios.inamhi.gob.ec/) | Boletines, visores, predicción, alertas y productos agrometeorológicos publicados | Tarjeta por provincia o coordenada de la hacienda: lluvia, alerta y enlace al boletín | Fase 1: enlace y curación; no hay API pública estable documentada para integrar directamente. |
| Pronóstico agroclimático | [INAMHI agrometeorología](https://servicios.inamhi.gob.ec/pronostico-agrometeorologico-bisemanal-2026-julio-diciembre/) | Boletines publicados periódicamente | Aviso no urgente para planificación de pasto, agua y trabajo de campo | Fase 1: extracción editorial o carga administrada; guardar fecha y URL. |
| Campaña de aftosa y rabia | [Datos Abiertos Ecuador / Agrocalidad](https://www.datosabiertos.gob.ec/dataset/datos-vacunacion-fiebre-aftosa-mas-rabia/resource/870fcb8b-2b7e-470d-adbd-b690f6996cec) | Recursos descargables CSV/XLS y metadatos | Indicador de cobertura histórica y enlace a la fuente; no determina si una finca está al día | Fase 2: importador programado, sujeto a formato y licencia del recurso. |
| Insumos registrados | [Datos Abiertos Ecuador / Agrocalidad](https://www.datosabiertos.gob.ec/dataset/changes/6114eb68-5e43-465d-a753-456a9e379f06) | Conjunto de archivos publicados y actualizados | Validación informativa de insumos contra listado oficial | Fase 2: importación y normalización; nunca bloquear una operación solo por coincidencia incompleta. |
| Resoluciones y normativa | [Registro Oficial](https://www.registroficial.gob.ec/) | Buscador y publicaciones oficiales | Bandeja de novedades seleccionadas por tema ganadero, con documento original | Fase 1: curación humana. No se ha identificado API pública estable para un lector automático confiable. |

## Arquitectura propuesta

1. `Source`: fuente, URL oficial, tipo, licencia conocida, frecuencia y responsable.
2. `External bulletin`: título, resumen humano, zona, tema, vigencia, URL, fecha de publicación y fecha de revisión en KORE.
3. `Farm relevance`: relación calculada por provincia, cantón o coordenada. No se asume relevancia nacional sin declararlo.
4. `Information card`: aparece en `Tu hacienda` después de tareas críticas. Muestra fuente, fecha y enlace `Ver fuente oficial`.
5. `Review queue`: un administrador revisa nuevas importaciones antes de publicarlas a las fincas.

## Reglas de integración

- Consumir solo fuentes oficiales o proveedores autorizados con atribución visible.
- Guardar el archivo o respuesta original, checksum y fecha de consulta cuando la licencia lo permita.
- Usar caché y tareas programadas; nunca consultar una fuente externa durante la carga normal de la jornada.
- Si una fuente falla, conservar el último dato con la marca `actualizado el ...`; no inventar una alerta.
- Todo aviso de salud o normativa debe incluir fuente y fecha. Los avisos críticos requieren revisión humana antes de notificar.
- No almacenar claves de API de un proveedor dentro del repositorio. Se usan variables de entorno y límites de consumo.

## Fases recomendadas

### Fase 1: información útil sin riesgo

- Configurar provincia, cantón y coordenada opcional de cada hacienda.
- Mostrar enlaces oficiales de INAMHI y un boletín revisado en `Tu hacienda`.
- Crear bandeja administrable de novedades regulatorias y sanitarias con fuente y vigencia.

### Fase 2: importaciones controladas

- Añadir conectores de descarga para conjuntos de datos abiertos de Agrocalidad.
- Normalizar campañas, cobertura e insumos registrados en tablas propias.
- Registrar ejecuciones, errores, fecha de fuente y cambios de estructura.

### Fase 3: alertas contextualizadas

- Evaluar relevancia por ubicación y especie.
- Proponer una tarea a un responsable, sin crearla automáticamente.
- Medir lectura, confirmación y falsos positivos antes de habilitar notificaciones masivas.

## Decisión pendiente

Antes de construir conectores se debe confirmar con Agrocalidad e INAMHI si existe un servicio oficial autenticado o una licencia de redistribución aplicable. El portal público permite consulta y descarga, pero eso no equivale a un API estable ni a autorización para redistribuir avisos sin atribución.
