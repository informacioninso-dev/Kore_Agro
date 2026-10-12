# AGENTS.md

Guía operativa para cualquier agente o colaborador que trabaje en KORE Agro.
El objetivo es mantener decisiones, código y documentación coherentes sin crear
archivos redundantes.

## Orden de lectura

Antes de modificar el repositorio:

1. Leer `AGENTS.md`.
2. Leer `MEMORY.md` para conocer decisiones permanentes y aprendizajes vigentes.
3. Leer `README.md` para alcance, arquitectura, estado y roadmap.
4. Consultar `docs/README.md` y abrir solo la guía relevante para la tarea.
5. Revisar `git status` y trabajar con los cambios existentes sin descartarlos.

## Fuentes de verdad

- Código remoto: `origin/main` es la referencia autoritativa del repositorio.
- Producto y roadmap: `README.md`.
- Navegación documental: `docs/README.md`.
- Decisiones y aprendizajes duraderos: `MEMORY.md`.
- Implementación real: código, migraciones y pruebas automatizadas.

Si la documentación contradice al código probado, verificar la intención antes de
actualizar ambos. Nunca ocultar una divergencia documental.

## Reglas de arquitectura

- Python 3.12+, Django, Poetry y PostgreSQL con `django-tenants`.
- HTMX + Tailwind para administración; PWA + IndexedDB para campo.
- UUIDv4 para entidades transaccionales y eventos creados offline.
- La PWA transmite eventos idempotentes; no muta estados finales directamente.
- Las reglas de negocio viven en servicios de aplicación, no dispersas en vistas.
- El aislamiento tenant, los permisos y las capacidades se validan en servidor.
- Toda acción con impacto económico debe conservar trazabilidad a inventario y P&L.
- Preferir un monolito modular; no crear microservicios sin una necesidad demostrada.
- Reutilizar motores compartidos entre cadenas productivas y evitar duplicar dominios.

## Política documental

- Actualizar un documento existente antes de crear uno nuevo.
- No crear archivos para notas temporales, bitácoras de conversación o planes de una
  sola tarea.
- Un documento nuevo requiere audiencia clara, propósito estable y dueño temático.
- `README.md` resume el producto; no debe convertirse en manual operativo detallado.
- `MEMORY.md` guarda decisiones estables, no estados efímeros ni secretos.
- `docs/README.md` debe enlazar cualquier documento permanente nuevo.
- Las decisiones sustituidas se actualizan o eliminan; no acumular versiones obsoletas.

## Flujo de cambio

1. Confirmar alcance y dominio afectado.
2. Buscar patrones existentes antes de introducir una abstracción.
3. Implementar el cambio mínimo completo, incluidas migraciones cuando apliquen.
4. Agregar pruebas proporcionales al riesgo y al aislamiento multi-tenant.
5. Ejecutar las validaciones relevantes.
6. Actualizar `README.md`, la guía temática o `MEMORY.md` solo si cambió una verdad
   duradera del sistema.

## Validación base

```powershell
poetry run ruff check apps config manage.py tests
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run pytest -q
```

Para cambios de frontend, validar además la experiencia responsive, los estados de
carga/vacío/error, accesibilidad básica y funcionamiento offline cuando corresponda.

## Git y seguridad

- No sobrescribir cambios locales ajenos.
- No ejecutar `reset --hard`, limpiezas destructivas ni eliminar datos sin autorización
  explícita.
- Comparar con `origin/main` antes de integrar cambios; actualizar referencias con
  `git fetch` cuando exista acceso de red.
- No registrar secretos, certificados SRI, credenciales, datos personales ni dumps de
  producción.
- No asumir que ocultar un control en la interfaz equivale a autorización.

## Criterio de cierre

Una tarea termina cuando el comportamiento está implementado, probado, documentado en
el lugar correcto y el estado de Git es comprendido. El resumen final debe indicar qué
cambió, qué se validó y cualquier riesgo o paso pendiente real.
