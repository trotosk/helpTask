"""
Ejemplo de uso de la función search_tasks() para buscar tareas con filtros

Este script demuestra cómo usar los diferentes filtros disponibles:
- Filtrar por estado
- Filtrar por rango de fechas
- Filtrar por usuarios asignados
- Ordenar por ID (más reciente primero por defecto)
"""

from tilena_api import TilenaAPI, TASK_STATUS, format_task_for_display
import os

# Configuración de la API
BASE_URL = os.getenv("TILENA_URL", "https://tilena.fooddeliverybrands.com")
USER_TOKEN = os.getenv("TILENA_USER_TOKEN")
APP_TOKEN = os.getenv("TILENA_APP_TOKEN")

# Crear cliente API
api = TilenaAPI(
    base_url=BASE_URL,
    user_token=USER_TOKEN,
    app_token=APP_TOKEN
)

# Iniciar sesión
success, error = api.init_session()
if not success:
    print(f"Error al iniciar sesión: {error}")
    exit(1)

print("=" * 60)
print("EJEMPLOS DE BÚSQUEDA DE TAREAS")
print("=" * 60)

# EJEMPLO 1: Buscar todas las tareas, ordenadas por ID descendente (más recientes primero)
print("\n1. Buscar todas las tareas (primeras 10, más recientes primero):")
print("-" * 60)
tareas = api.search_tasks(
    range_start=0,
    range_end=9,
    sort=2,  # Ordenar por ID
    order="DESC"  # Descendente (más nuevo primero)
)

if tareas:
    print(f"✅ Se encontraron {len(tareas)} tareas")
    for idx, tarea in enumerate(tareas, 1):
        print(f"\n  Tarea {idx}:")
        print(f"    ID: {tarea.get('2')}")
        print(f"    Título: {tarea.get('1')}")
        print(f"    Estado: {tarea.get('3')}")
        print(f"    Asignado: {tarea.get('5')}")
        print(f"    Fecha creación: {tarea.get('9')}")
else:
    print("❌ No se encontraron tareas")

# EJEMPLO 2: Buscar tareas por estado (solo tareas en curso)
print("\n\n2. Buscar tareas EN CURSO:")
print("-" * 60)
tareas_en_curso = api.search_tasks(
    status=[1],  # 1 = En curso
    range_start=0,
    range_end=9
)

if tareas_en_curso:
    print(f"✅ Se encontraron {len(tareas_en_curso)} tareas en curso")
    for idx, tarea in enumerate(tareas_en_curso, 1):
        print(f"\n  Tarea {idx}: #{tarea.get('2')} - {tarea.get('1')}")
        print(f"    Estado: {TASK_STATUS.get(int(tarea.get('3', 0)), 'Desconocido')}")
else:
    print("❌ No se encontraron tareas en curso")

# EJEMPLO 3: Buscar tareas pendientes o en curso (múltiples estados)
print("\n\n3. Buscar tareas PENDIENTES o EN CURSO:")
print("-" * 60)
tareas_activas = api.search_tasks(
    status=[0, 1],  # 0 = Pendiente, 1 = En curso
    range_start=0,
    range_end=9
)

if tareas_activas:
    print(f"✅ Se encontraron {len(tareas_activas)} tareas activas")
    for idx, tarea in enumerate(tareas_activas, 1):
        estado_id = int(tarea.get('3', 0))
        estado_nombre = TASK_STATUS.get(estado_id, 'Desconocido')
        print(f"  {idx}. #{tarea.get('2')} - {tarea.get('1')} - [{estado_nombre}]")
else:
    print("❌ No se encontraron tareas activas")

# EJEMPLO 4: Buscar tareas por rango de fechas
print("\n\n4. Buscar tareas modificadas desde 2024-01-01:")
print("-" * 60)
tareas_recientes = api.search_tasks(
    fecha_inicio="2024-01-01",
    range_start=0,
    range_end=9
)

if tareas_recientes:
    print(f"✅ Se encontraron {len(tareas_recientes)} tareas desde 2024-01-01")
    for idx, tarea in enumerate(tareas_recientes, 1):
        print(f"  {idx}. #{tarea.get('2')} - Modificada: {tarea.get('10')}")
else:
    print("❌ No se encontraron tareas en ese rango")

# EJEMPLO 5: Combinar filtros (estado + rango de fechas)
print("\n\n5. Buscar tareas COMPLETADAS desde 2024-01-01:")
print("-" * 60)
tareas_completadas = api.search_tasks(
    status=[2],  # 2 = Completada
    fecha_inicio="2024-01-01",
    range_start=0,
    range_end=9
)

if tareas_completadas:
    print(f"✅ Se encontraron {len(tareas_completadas)} tareas completadas")
    for idx, tarea in enumerate(tareas_completadas, 1):
        print(f"  {idx}. #{tarea.get('2')} - {tarea.get('1')}")
        print(f"      Completada: {tarea.get('10')}")
else:
    print("❌ No se encontraron tareas completadas en ese rango")

# EJEMPLO 6: Buscar por usuario asignado (requiere conocer el ID del usuario)
# Nota: Los IDs de usuario varían según tu instalación de GLPI
print("\n\n6. Buscar tareas asignadas a usuarios específicos:")
print("-" * 60)
print("(Para este ejemplo necesitas conocer los IDs de usuarios en tu GLPI)")
print("Puedes obtenerlos consultando la API o desde la interfaz de GLPI")

# Ejemplo comentado (descomenta y ajusta los IDs según tu sistema):
# tareas_asignadas = api.search_tasks(
#     asignados=[123, 456],  # IDs de usuarios
#     range_start=0,
#     range_end=9
# )

# Cerrar sesión
api.kill_session()
print("\n" + "=" * 60)
print("Sesión cerrada correctamente")
print("=" * 60)
