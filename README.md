# 🖥️ Sistema de Gestión — Clínica del PC INACAP (Django + API REST + RBAC)

> **Asignatura:** Fundamentos de Hardware y Software / Ingeniería de Software (TI3043)  
> **Sede:** INACAP San Pedro de la Paz  
> **Profesor:** Pablo Pesce Sánchez  
> **Tecnologías:** Python 3.13, Django 6.1, SQLite, HTML5, CSS3, JavaScript (Fetch API REST)

---

## 🔐 1. Control de Acceso por Roles (RBAC)

El sistema implementa una **matriz de permisos estricta** según el documento de levantamiento y diseño del proyecto:

| Módulo / Ruta | Paso Operativo | Administrador (`admin`) | Docente Supervisor (`docente`) | Mesón Recepción (`recepcion`) | Alumno Técnico (`tecnico1`) | Público General |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Pre-inscripción** (`/preinscripcion/`) | Paso 1 (QR) | ✅ | 🔄 *(Va a Panel)* | 🔄 *(Va a Mesón)* | ❌ *(Redirige a Taller)* | ✅ *(Sin Login)* |
| **Mesón de Recepción** (`/recepcion/`) | Pasos 2 y 3 | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Mesa de Taller** (`/taller/`) | Pasos 3 a 5 | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Control de Calidad** (`/control-calidad/`) | Paso 6 (V°B°) | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Retiro y Entrega** (`/entrega/`) | Pasos 7, 8 y 9 | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Métricas y Reportes** (`/metricas/`) | Transversal | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Panel de Control** (`/`) | General | ✅ | ✅ *(Exclusivo)* | 🔄 *(Va a Mesón)* | 🔄 *(Va a Taller)* | ❌ |

### ¿Cómo funciona la seguridad?
1. **Autenticación Local Propia:** No depende de `django.contrib.admin` ni de `auth.User`. Se utiliza la tabla propia `Usuario` en SQLite y el almacenamiento directo en `request.session`.
2. **Decoradores en Backend:** Las vistas en `portal/views.py` utilizan el decorador `@roles_permitidos([...])` definido en `autenticacion/decoradores.py`. Si un usuario intenta forzar la URL a una sección no autorizada, el sistema lo **devuelve automáticamente a su área de trabajo** con un aviso breve (ya no se muestra una pantalla de módulo restringido).
3. **Seguridad en la API REST:** Los endpoints críticos (`/api/ordenes/<id>/visto-bueno/`, `/api/ordenes/<id>/entrega/`) verifican el rol del usuario autenticado en la sesión y retornan código `403 Forbidden` si no tiene los privilegios requeridos.
4. **Barra de Navegación Dinámica:** `AppUtils.renderHeader()` en `static/js/app.js` solo muestra los botones y enlaces correspondientes al rol de la sesión activa, junto al nombre del usuario y su insignia de rol.
5. **Redirección Inteligente tras el Login:** Al iniciar sesión, el usuario es dirigido directamente a su lugar de trabajo:
   - Técnico ➔ `/taller/`
   - Recepción ➔ `/recepcion/`
   - Docente ➔ `/` (Panel Principal con Supervisión y Calidad)
   - Administrador ➔ `/` (Panel Principal con acceso universal)

---

## 🏗️ 2. Estructura Modular del Proyecto

```text
clinica_django/
├── manage.py                          # Gestor de comandos de Django
├── db.sqlite3                         # Base de datos relacional local
├── RESUMEN_SESION.md                  # Bitácora y guía rápida para retomar el trabajo
├── config/                            # Configuración global del proyecto
│   ├── settings.py                    # Ajustes principales (sin django.contrib.admin)
│   ├── urls.py                        # Enrutador general de rutas
│   └── wsgi.py
│
├── autenticacion/                     # MÓDULO 1: Gestión de usuarios y roles propios
│   ├── models.py                      # Modelo propio Usuario (admin, docente, recepcion, tecnico)
│   └── decoradores.py                 # Decorador @roles_permitidos y helpers de sesión
│
├── gestion/                           # MÓDULO 2: Entidades del negocio (Base de Datos)
│   ├── models.py                      # Propietario, Dispositivo, OrdenServicio, ItemChecklist, Observacion...
│   ├── tests.py                       # Pruebas automatizadas de RBAC, Login y ciclo de vida (6 tests OK)
│   └── management/commands/
│       └── poblar_datos.py            # Comando para sembrar datos iniciales de prueba
│
├── api/                               # MÓDULO 3: Endpoints REST (Controladores JSON)
│   ├── views.py                       # Vistas de autenticación local, CRUD de órdenes, checklists y métricas
│   └── urls.py                        # Rutas bajo el prefijo /api/...
│
├── portal/                            # MÓDULO 4: Vistas Web (Frontend)
│   ├── views.py                       # Vistas protegidas con decoradores de rol
│   └── urls.py                        # Rutas web (/ , /preinscripcion/ , /taller/ , etc.)
│
├── static/                            # Archivos Estáticos Independientes
│   ├── css/
│   │   ├── main.css                   # Variables de color, tipografía y layout general
│   │   ├── components.css             # Botones, tarjetas, modales, badges y tablas
│   │   └── login.css                  # Estilo exclusivo de la pantalla de acceso
│   └── js/
│       ├── api_cliente.js             # Cliente JavaScript que consume la API REST (Fetch)
│       └── app.js                     # Validaciones de RUT chileno, toasts y barra superior RBAC
│
└── templates/                         # Plantillas HTML
    ├── login.html                     # Pantalla de inicio de sesión con chips de roles
    ├── acceso_denegado.html           # Pantalla 403 amigable para roles no autorizados
    ├── index.html                     # Panel de control con tarjetas habilitadas según rol
    ├── preinscripcion.html            # Portal público móvil para escanear QR (Paso 1)
    ├── recepcion.html                 # Mesón de entrada (Pasos 2-3) [Recepción y Admin]
    ├── taller.html                    # Tablero Kanban (Pasos 4-5) [Técnico, Docente y Admin]
    ├── control_calidad.html           # Certificación Docente (Paso 6) [Docente y Admin]
    ├── entrega.html                   # Retiro y Encuesta (Pasos 7-9) [Recepción y Admin]
    └── metricas.html                  # Consola estadística [Docente y Admin]
```

---

## 🚀 3. Instrucciones de Puesta en Marcha

```bash
# 1. Entrar a la carpeta del proyecto
cd /Users/marcelodiazflores/Desktop/ingenieria_de_software/clinica_del_pc/clinica_django

# 2. Iniciar el servidor local
python3 manage.py runserver
```

Abre en tu navegador:
- [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🔑 4. Cuentas para Probar los Roles

| Perfil | Usuario | Contraseña | Módulos a los que puede entrar |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin123` | **Acceso total a todo el sistema y al panel `/admin/`** |
| **Docente Supervisor** | `docente` | `docente123` | **Control de Calidad (V°B°), Métricas, Taller y Dashboard** |
| **Mesón de Recepción** | `recepcion` | `recepcion123` | **Mesón de Recepción, Retiro/Entrega y Dashboard** |
| **Alumno Técnico** | `tecnico1` | `tecnico123` | **Mesa de Trabajo en Taller y Checklists únicamente** |

---

## 🧪 5. Pruebas Automatizadas

Para validar que la matriz de roles y permisos opera al 100%:
```bash
python3 manage.py test
```
Salida esperada:
```text
Ran 5 tests in 10.3s - OK
```

---

## 🗂️ 6. Administración y Carga Masiva por CSV (solo `admin`)

Ruta: `/administracion/` (menú **Administración**).

- **Usuarios:** sube un CSV con `nombre_usuario;nombre_completo;correo;rol;telefono;contrasena`. Roles permitidos: `docente` y `tecnico`. Los usuarios que ya existen se omiten; si no hay contraseña se genera una clave inicial y se puede descargar un CSV con las claves.
- **Checklists:** sube un CSV con `tipo_servicio;codigo;descripcion`. La lista de cada servicio incluido **reemplaza** a la anterior y se aplica a las **órdenes nuevas** (las existentes no cambian). Sin plantilla cargada se usa el catálogo por defecto.
- Ambas cargas muestran una **vista previa** antes de guardar. Cada pantalla ofrece una plantilla CSV descargable (la de checklists trae la lista vigente).

Instalación rápida: `pip install -r requirements.txt`, luego `python manage.py migrate` y `python manage.py poblar_datos`.

## 🔧 7. Perfil Técnico, Recepción y Taller (reglas vigentes)

- **Recepción** registra accesorios e inspección visual. **No** verifica el encendido ni pide número de serie: eso lo hace el técnico.
- **Una orden se recepciona una sola vez.** Después, la ficha del mesón queda en solo lectura.
- **Técnico:** ve solo los equipos *recepcionados en espera* y los que él mismo atiende ("Mis equipos atendidos"). No ve los de otros técnicos. Al tomar un equipo queda asignado a su nombre.
- En taller el técnico verifica **si el equipo enciende**, registra el **número de serie** y completa el checklist. Si un punto **falla**, debe escribir **por qué falló**.
- La **bitácora** es un resumen automático (equipo, técnico, serie, encendido, checklist, fallas con su motivo y eventos de pausa/envío a V°B°), no notas manuales.
- Al enviar a V°B° docente, el técnico permanece en su mesa de taller.

## 🎓 8. Perfil Docente

El docente solo ve **Panel**, **V°B° Calidad**, **Estudiantes** y **Métricas**. En **Estudiantes** (`/estudiantes/`) revisa los equipos que atendió cada estudiante técnico, con su estado, fallas y bitácora. No accede a Pre-inscripción, Mesón de Recepción, Taller ni Retiro y Cierre (este último es del mesón de recepción: llamada al titular, prueba de entrega y encuesta). Su panel muestra únicamente los módulos que le corresponden.
