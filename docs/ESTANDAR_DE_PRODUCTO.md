# Estándar de producto KORE Agro

Este documento es la referencia obligatoria para toda pantalla nueva o rediseñada. KORE es una herramienta de trabajo para fincas ganaderas ecuatorianas: se consulta con prisa, con sol y desde un teléfono. No es un sistema corporativo ni un tablero genérico.

## Principios

1. La finca primero. Cada pantalla debe contestar "qué hago ahora" antes de mostrar indicadores o administración.
2. Cinco destinos máximos. La navegación principal es: `Tu hacienda`, `Hato y bodega`, `Registrar en campo`, `Producción y cuentas`, `Guías y documentos`.
3. Una tarea por decisión. El botón principal indica la acción concreta: `Registrar ordeño`, `Añadir animal`, `Cerrar guía`. No se usa `Enviar`, `Procesar` o `Crear` sin contexto.
4. Datos antes que decoración. Una ilustración nunca puede competir con una alerta, cifra o etiqueta de animal.
5. Siempre se declara el alcance. Las listas, cifras y alertas indican hacienda, período y fecha de actualización cuando aplique.

## Paleta única

| Token | Color | Uso |
| --- | --- | --- |
| `forest-900` | `#1F4D31` | Navegación activa, acción principal, encabezados fuertes. |
| `forest-700` | `#2F6B42` | Enlaces, estados correctos y gráficos positivos. |
| `leaf-100` | `#E5EDDB` | Fondos de contexto, filtros y bloques de jornada. |
| `paper` | `#F5F1E7` | Fondo general. |
| `surface` | `#FFFEFA` | Tarjetas, formularios y tablas. |
| `line` | `#D8DECE` | Bordes, divisores y controles inactivos. |
| `ink` | `#193326` | Texto principal. |
| `muted` | `#68766A` | Texto auxiliar, fechas y ayuda. |
| `sun` | `#E9B44C` | Solo llamada a registrar en campo y avisos informativos. |
| `warning` | `#A86422` | Precaución que requiere revisión, sin bloquear. |
| `danger` | `#B33A32` | Retiro de leche, vencimiento o riesgo sanitario. |

Reglas de color:

- No se usan fondos negros o `neutral-900` en módulos de negocio. El modo oscuro solo existe si se diseña como una experiencia completa y aprobada.
- `sun` nunca representa error o urgencia. `danger` no se usa para acciones destructivas sin confirmación.
- El verde oscuro lleva texto blanco; en fondos claros se usa `ink`. Todo texto normal debe mantener contraste AA.
- Las categorías no reciben un color arbitrario. Leche usa verde, reproducción usa verde claro, sanidad usa ámbar para revisión y rojo solo para riesgo real.
- Las variables anteriores deben sustituir progresivamente colores hexadecimales y clases `neutral-*` heredadas.

## Tipografía y composición

- Interfaz y formularios: sans serif legible, tamaño base mínimo de 16 px en campo y 14 px en escritorio.
- Títulos de sección: serif sobria, solo para jerarquía; nunca para tablas, cifras, fechas o formularios.
- Una pantalla tiene un título, una frase de ayuda y una acción principal. El filtro de hacienda acompaña el título, no lo desplaza.
- Tarjetas: fondo `surface`, borde `line`, radio de 16 px. No se combinan en la misma vista tarjetas oscuras y claras.
- En móvil, la acción de campo es persistente y grande; los detalles y análisis se consultan después.

## Patrones por tipo de módulo

### Tu hacienda

Propósito: iniciar la jornada. Orden obligatorio: alertas críticas, tareas de hoy, estado rápido del hato, resumen económico breve e información externa relevante. No contiene formularios largos ni tablas de administración.

### Hato y bodega

Propósito: encontrar y mantener los recursos de la finca. Usa listas buscables de animales, lotes e insumos; en escritorio puede usar tabla y en móvil tarjetas. El botón `Añadir` abre un formulario corto o un panel lateral. Las configuraciones de hacienda se agrupan al final, no son la primera pantalla.

### Registrar en campo

Propósito: registrar un hecho en menos de un minuto. Usa tarjetas grandes con icono y lenguaje de finca: ordeño, celo o servicio, tratamiento, movimiento y consumo. Debe funcionar sin señal y confirmar claramente que quedó guardado en el equipo o sincronizado.

### Producción y cuentas

Propósito: decidir con datos. Abre con tres a cinco indicadores comparables y después tendencias, costos y movimientos. Las tablas completas están detrás de un enlace `Ver detalle`; nunca son el primer bloque.

### Guías y documentos

Propósito: preparar, revisar y enviar documentos. Usa lista con estado, fecha, hacienda y siguiente acción. Los borradores se distinguen visualmente de documentos enviados. La acción de envío requiere confirmación y evidencia del resultado.

## Listas, formularios y reportes

| Necesidad | Patrón obligatorio |
| --- | --- |
| Ver muchos registros | Lista con búsqueda, filtros visibles y contador. Tabla solo en escritorio. |
| Añadir un hecho diario | Botón contextual `Registrar ...` y formulario corto. |
| Crear un recurso durable | Botón `Añadir ...`, formulario completo en panel o página separada. |
| Corregir un dato | Acción `Editar` secundaria, con historial cuando afecte dinero, sanidad o trazabilidad. |
| Revisar resultados | Resumen primero, tendencia después, detalle exportable al final. |
| Sin registros | Mensaje claro y una acción útil: `Añadir primer animal`, no una tabla vacía. |

## Roles y experiencia

| Rol | Su objetivo | Lo que ve primero | Puede hacer |
| --- | --- | --- | --- |
| Mayordomo | Ejecutar bien la jornada | Tareas, animales por atender, registro rápido y sincronización | Registrar eventos de campo, consultar su hato y confirmar tareas. No ve costos, margen, facturación ni configuración de usuarios. |
| Dueño | Saber cómo está y decidir | Alertas críticas, producción, estado del hato, caja y documentos por aprobar | Todo lo anterior, revisar análisis, administrar haciendas, precios, usuarios y documentos. |
| Administrador | Mantener la operación ordenada | Igual que el dueño, sin decisiones reservadas de propiedad | Gestionar hato, bodega y registros; acceso a cuentas según autorización del dueño. |

La interfaz debe reconocer el rol con lenguaje, no solo con permisos. Un mayordomo no debe encontrarse con botones bloqueados ni cifras financieras que no necesita.

## Criterios de aceptación visual

Una pantalla no está lista si incumple alguno:

1. Usa colores fuera de la paleta sin token semántico.
2. Tiene más de una acción principal visible.
3. Muestra cifras de un período diferente al que declara.
4. No indica qué hacer cuando no hay datos.
5. Mezcla fondos oscuros heredados con la superficie clara de KORE.
6. Requiere leer terminología técnica para registrar una acción de finca.
