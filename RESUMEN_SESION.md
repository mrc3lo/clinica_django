# 📋 Resumen de Sesión — Prototipo Clínica del PC INACAP

> **Fecha de guardado:** 22 de Noviembre de 2026  
> **Proyecto:** Sistema de Gestión y Trazabilidad para la Jornada "Clínica del PC"  
> **Institución:** INACAP Sede San Pedro de la Paz (TI3043)  
> **Tecnologías:** Python 3.13, Django 6.1, SQLite, HTML5, CSS3 modular, Fetch API REST (100% Local)

---

## 🎯 1. Resumen Ejecutivo del Estado del Proyecto

Se ha implementado con éxito el prototipo real en **Django** con arquitectura por módulos, base de datos local SQLite y API REST JSON, cumpliendo estrictamente con los 9 pasos del informe técnico de INACAP y las directrices de diseño y acceso:

1. **Autenticación 100% Local Propia:**
   - Se removió por completo el panel de administración estándar de Django (`django.contrib.admin`) y su modelo de usuarios por defecto.
   - Se creó una tabla propia `Usuario` en SQLite (`autenticacion/models.py`) gestionada directamente por el código del proyecto.
   - La sesión se almacena limpiamente en `request.session` (`usuario_id`, `usuario_rol`, `usuario_nombre`).

2. **Control de Acceso por Roles (RBAC) y Redirecciones Inteligentes:**
   - **Administrador (`admin`):** Acceso universal a todos los módulos.
   - **Docente Supervisor (`docente`):** Acceso exclusivo al **Panel Principal (`/`)**, Supervisión de Taller, Control de Calidad (firma de Visto Bueno) y Métricas.
   - **Mesón de Recepción (`recepcion`):** Acceso a Mesón (recepción de equipos) y Entrega (retiro con encuesta). No tiene acceso al Panel; al ingresar a `/` o loguearse, el sistema lo redirige automáticamente a `/recepcion/`.
   - **Alumno Técnico (`tecnico`):** Confinado exclusivamente a su **Mesa de Taller (`/taller/`)**. No tiene acceso a pre-inscripción ni al Panel Principal (ambos lo redirigen a `/taller/`). No puede firmar vistos buenos.

3. **Diseño Visual Institucional INACAP:**
   - Paleta sobria y elegante: Rojo INACAP (`#D3122A`), Negro grafito (`#121214`), Gris (`#F4F5F7`), Blanco (`#FFFFFF`).
   - Archivos CSS separados e independientes: `static/css/main.css`, `static/css/components.css`, `static/css/login.css`.
   - Interfaz limpia, sin saturación de colores ni emojis innecesarios.

4. **Código con estilo de estudiante de alto promedio:**
   - Variables, clases, funciones y rutas en **español**.
   - Código ampliamente comentado de manera didáctica y ordenada.
   - 100% funcional sin sobre-ingeniería de librerías externas complejas.

---

## 🔑 2. Cuentas de Acceso de Demostración

La base de datos SQLite local ya se encuentra poblada con los usuarios y datos de prueba:

| Rol | Usuario | Contraseña | Destino al iniciar sesión | Permisos principales |
| :--- | :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin123` | `/` (Panel Principal) | Acceso total a los 9 pasos y métricas |
| **Docente Supervisor** | `docente` | `docente123` | `/` (Panel Principal) | Panel, Supervisión, Calidad (V°B°), Métricas |
| **Mesón de Recepción** | `recepcion` | `recepcion123` | `/recepcion/` | Búsqueda por RUT, Ficha de ingreso, Entrega |
| **Alumno Técnico** | `tecnico1` | `tecnico123` | `/taller/` | Mesa de taller, Checklists técnicos, Bitácora |

*(También existe `tecnico2` con clave `tecnico123` para probar cambios de turno en taller).*

---

## 🚀 3. Comandos Rápidos para Retomar el Proyecto

Todos los comandos se ejecutan desde la carpeta del proyecto:

```bash
# 1. Navegar a la carpeta del proyecto
cd clinica_del_pc/clinica_django

# 2. Iniciar el servidor local de desarrollo
python3 manage.py runserver

# 3. Acceder en el navegador
# Abre: http://127.0.0.1:8000/
```

### Comandos de mantenimiento:
```bash
# Ejecutar la suite completa de pruebas automatizadas (6 tests RBAC + API)
python3 manage.py test

# Repoblar o restaurar la base de datos a su estado demo inicial
python3 manage.py poblar_datos

# Generar o aplicar migraciones ante cualquier cambio de modelo
python3 manage.py makemigrations
python3 manage.py migrate
```

---

## 📂 4. Mapa de Archivos Clave del Proyecto

```text
clinica_del_pc/clinica_django/
├── manage.py                          # Gestor de comandos de Django
├── db.sqlite3                         # Base de datos local SQLite
│
├── config/                            # Configuración del proyecto
│   ├── settings.py                    # Configuración sin django.contrib.admin
│   └── urls.py                        # Enrutador principal de páginas y API
│
├── autenticacion/                     # Módulo de usuarios y permisos
│   ├── models.py                      # Modelo propio 'Usuario' (sin auth.User)
│   └── decoradores.py                 # Decorador @roles_permitidos para RBAC
│
├── gestion/                           # Módulo de base de datos del negocio
│   ├── models.py                      # Propietario, Dispositivo, OrdenServicio, Checklists...
│   ├── tests.py                       # 6 tests automatizados de RBAC y API (100% pasando)
│   └── management/commands/
│       └── poblar_datos.py            # Comando CLI para sembrar datos demo
│
├── api/                               # Módulo de la API REST Local
│   └── views.py                       # Login, Logout, Órdenes, Checklists, V°B°, Encuesta
│
├── portal/                            # Módulo de vistas web
│   └── views.py                       # Vistas HTML protegidas con redirecciones por rol
│
├── static/                            # Recursos estáticos
│   ├── css/
│   │   ├── main.css                   # Variables de color INACAP, tipografía y layout
│   │   ├── components.css             # Botones, tablas, tarjetas, badges, modales
│   │   └── login.css                  # Estilo de la pantalla de inicio de sesión
│   └── js/
│       ├── api_cliente.js             # Capa cliente Fetch para hablar con la API
│       └── app.js                     # Renderizador de cabecera dinámica, sesión y toasts
│
└── templates/                         # Plantillas HTML con diseño institucional
    ├── login.html                     # Acceso al sistema
    ├── index.html                     # Panel de Control (Docente y Admin)
    ├── preinscripcion.html            # Paso 1: Registro QR comunitario
    ├── recepcion.html                 # Pasos 2-3: Mesón y constatación inicial
    ├── taller.html                    # Pasos 4-5: Mesa técnica y checklists
    ├── control_calidad.html           # Paso 6: Visto Bueno del Docente
    ├── entrega.html                   # Pasos 7-9: Retiro, comprobación y encuesta
    ├── metricas.html                  # Panel estadístico y gráficos
    └── acceso_denegado.html           # Pantalla 403 con redirección según rol
```

---

## 🧪 5. Estado de Verificación y Pruebas

Se ejecutó la suite `python3 manage.py test`:
- `test_01_administrador_acceso_total`: **OK** (Admin tiene acceso 200 a todas las vistas).
- `test_02_tecnico_acceso_restringido`: **OK** (Taller 200; Panel y Preinscripción redirigen 302 a Taller; Mesón, Calidad y Entrega retornan 403).
- `test_03_recepcion_acceso_restringido`: **OK** (Mesón y Entrega 200; Panel redirige 302 a Mesón; Taller, Calidad y Métricas retornan 403).
- `test_04_docente_acceso_restringido`: **OK** (Panel, Calidad, Métricas y Taller 200; Mesón y Entrega retornan 403).
- `test_05_api_seguridad_visto_bueno`: **OK** (Técnico rechazado con 403 al intentar firmar V°B°; Docente aceptado con 200).
- `test_06_login_api_local`: **OK** (Autenticación contra tabla propia SQLite).

---

## 💡 6. Posibles Próximas Mejoras (Para la próxima sesión)

1. **Generación e impresión real de comprobantes:**
   - Botón de imprimir ticket de recepción para el cliente con su etiqueta física (`CLI-PC-2026-XXXX`).
   - Acta de entrega final con firma presencial.
2. **Exportación de Métricas:**
   - Botón para descargar el consolidado de órdenes y notas de satisfacción en formato CSV o reporte para el informe final de la asignatura.
3. **Filtros avanzados en Taller:**
   - Búsqueda rápida por etiqueta de taller o técnico asignado en la mesa de trabajo.
