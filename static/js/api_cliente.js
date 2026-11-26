/* ==============================================================================
   CLIENTE API REST - CLÍNICA DEL PC INACAP
   Reemplaza el antiguo localStorage por llamadas HTTP asíncronas (fetch)
   directas al backend Django y a la base de datos local SQLite.
   ============================================================================== */

window.ClinicaAPI = {
  // URL base de los endpoints REST
  baseUrl: '/api',

  // Token CSRF (OWASP A01): Django lo entrega en una cookie y toda petición que modifica datos debe devolverlo
  csrfToken() {
    const coincidencia = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return coincidencia ? decodeURIComponent(coincidencia[1]) : '';
  },

  // Cabeceras estándar para enviar JSON con el token CSRF
  cabeceras() {
    return { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken() };
  },

  // --------------------------------------------------------------------------
  // 1. MÓDULO DE AUTENTICACIÓN
  // --------------------------------------------------------------------------
  
  // Inicia sesión en el servidor Django
  async login(usuario, clave) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/autenticacion/login/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify({ usuario, clave })
      });
      const datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'Credenciales incorrectas');
      return datos;
    } catch (error) {
      console.error('Error al iniciar sesión:', error);
      throw error;
    }
  },

  // Cierra la sesión activa
  async logout() {
    try {
      const respuesta = await fetch(`${this.baseUrl}/autenticacion/logout/`, {
        method: 'POST',
        headers: this.cabeceras()
      });
      window.location.href = '/login/';
    } catch (error) {
      console.error('Error al cerrar sesión:', error);
      window.location.href = '/login/';
    }
  },

  // Obtiene los datos del usuario conectado
  async getUsuarioActual() {
    try {
      const respuesta = await fetch(`${this.baseUrl}/autenticacion/usuario-actual/`);
      return await respuesta.json();
    } catch (error) {
      return { autenticado: false, usuario: null };
    }
  },

  // --------------------------------------------------------------------------
  // 2. MÓDULO DE ÓRDENES Y SEGUIMIENTO (Base de Datos Local)
  // --------------------------------------------------------------------------

  // Obtiene todas las órdenes, opcionalmente filtrando por estado, rut o servicio
  async getOrdenes(filtros = {}) {
    try {
      const params = new URLSearchParams();
      if (filtros.estado) params.append('estado', filtros.estado);
      if (filtros.rut) params.append('rut', filtros.rut);
      if (filtros.q) params.append('q', filtros.q);
      if (filtros.servicio) params.append('servicio', filtros.servicio);

      const url = `${this.baseUrl}/ordenes/?${params.toString()}`;
      const respuesta = await fetch(url);
      const data = await respuesta.json();
      return data.ordenes || [];
    } catch (error) {
      console.error('Error al obtener órdenes:', error);
      return [];
    }
  },

  // Obtiene el detalle completo de una orden por su ID
  async getOrdenPorId(ordenId) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/`);
      const data = await respuesta.json();
      return data.orden;
    } catch (error) {
      console.error(`Error al obtener orden ${ordenId}:`, error);
      return null;
    }
  },

  // Crea una nueva orden (Preinscripción o Recepción en Mesón)
  async crearOrden(datosOrden) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify(datosOrden)
      });
      const resultado = await respuesta.json();
      if (!respuesta.ok) throw new Error(resultado.error || 'No se pudo crear la orden');
      return resultado.orden;
    } catch (error) {
      console.error('Error al crear orden:', error);
      throw error;
    }
  },

  // Actualiza el estado de una orden (ej: "En Taller", "Listo para Entrega", etc.)
  async cambiarEstado(ordenId, nuevoEstado, tecnicoAsignado = null) {
    try {
      const payload = { estado: nuevoEstado };
      if (tecnicoAsignado) payload.tecnicoAsignado = tecnicoAsignado;

      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/estado/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify(payload)
      });
      const data = await respuesta.json();
      if (!respuesta.ok) throw new Error(data.error || 'Error al cambiar estado');
      return data.orden;
    } catch (error) {
      console.error('Error al cambiar estado:', error);
      throw error;
    }
  },

  // Actualiza un ítem de checklist técnico (OK, FALLA, PENDIENTE)
  async actualizarChecklist(ordenId, codigoItem, resultado, descripcion = '', motivo = '') {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/checklists/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify({ codigo: codigoItem, resultado, desc: descripcion, motivo })
      });
      const data = await respuesta.json();
      if (!respuesta.ok) throw new Error(data.error || 'Error al actualizar checklist');
      return data;
    } catch (error) {
      console.error('Error al actualizar checklist:', error);
      throw error;
    }
  },

  // Registra una anotación u observación técnica en la bitácora
  async agregarObservacion(ordenId, texto, autor = 'Técnico', criticidad = 'Baja', hallazgoLegal = false) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/observaciones/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify({ texto, autor, criticidad, hallazgoLegal })
      });
      const data = await respuesta.json();
      if (!respuesta.ok) throw new Error(data.error || 'Error al guardar observación');
      return data.observacion;
    } catch (error) {
      console.error('Error al agregar observación:', error);
      throw error;
    }
  },

  // Certificación y firma de V°B° por parte del Docente Supervisor
  async guardarVistoBueno(ordenId, nombreDocente, comentario) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/visto-bueno/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify({ docente: nombreDocente, comentario })
      });
      const data = await respuesta.json();
      if (!respuesta.ok) throw new Error(data.error || 'Error al guardar V°B°');
      return data.orden;
    } catch (error) {
      console.error('Error al certificar orden:', error);
      throw error;
    }
  },

  // Registra la entrega final al usuario con su encuesta de satisfacción
  async registrarEntrega(ordenId, datosEntrega) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/entrega/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify(datosEntrega)
      });
      const data = await respuesta.json();
      if (!respuesta.ok) throw new Error(data.error || 'Error al registrar entrega');
      return data.orden;
    } catch (error) {
      console.error('Error al registrar entrega:', error);
      throw error;
    }
  },

  // Marca si se avisó telefónicamente al propietario
  async marcarLlamada(ordenId, llamadaRealizada = true) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/ordenes/${ordenId}/`, {
        method: 'POST',
        headers: this.cabeceras(),
        body: JSON.stringify({ llamadaRealizada })
      });
      return await respuesta.json();
    } catch (error) {
      console.error('Error al marcar llamada:', error);
    }
  },

  // --------------------------------------------------------------------------
  // 3. PROPIETARIOS
  // --------------------------------------------------------------------------
  async buscarPropietarioPorRut(rut) {
    try {
      const respuesta = await fetch(`${this.baseUrl}/propietarios/?rut=${encodeURIComponent(rut)}`);
      const data = await respuesta.json();
      if (data.propietarios && data.propietarios.length > 0) {
        return data.propietarios[0];
      }
      return null;
    } catch (error) {
      console.error('Error al buscar propietario:', error);
      return null;
    }
  },

  // --------------------------------------------------------------------------
  // 4. MÉTRICAS Y ESTADÍSTICAS
  // --------------------------------------------------------------------------
  async getMetricas() {
    try {
      const respuesta = await fetch(`${this.baseUrl}/metricas/`);
      return await respuesta.json();
    } catch (error) {
      console.error('Error al obtener métricas:', error);
      return {
        total: 0,
        preinscrito: 0,
        recepcionado: 0,
        enTaller: 0,
        listo: 0,
        entregado: 0,
        custodia: 0,
        promedioSatisfaccion: 5.0,
        servicios: {}
      };
    }
  },

  // --------------------------------------------------------------------------
  // 5. RESTAURAR DATOS DE DEMOSTRACIÓN (Semilla Inicial)
  // --------------------------------------------------------------------------
  async resetDB() {
    try {
      const respuesta = await fetch(`${this.baseUrl}/restaurar-datos/`, {
        method: 'POST',
        headers: this.cabeceras()
      });
      const data = await respuesta.json();
      return data;
    } catch (error) {
      console.error('Error al restaurar base de datos:', error);
      throw error;
    }
  }
};
