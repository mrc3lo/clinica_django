/* ==============================================================================
   APP UTILS — ESTILO INSTITUCIONAL INACAP (ROJO, BLANCO Y NEGRO)
   Formateo de RUT, badges de estado sobrios, barra superior limpia y alertas.
   ============================================================================== */

window.AppUtils = {
  // Limpia el RUT dejando solo números y dígito verificador
  cleanRut(rut) {
    return typeof rut === 'string' ? rut.replace(/[^0-9kK]/g, '').toUpperCase() : '';
  },

  // Formatea un RUT chileno con puntos y guion (ej: 18.452.910-3)
  formatRut(rut) {
    let clean = this.cleanRut(rut);
    if (clean.length < 2) return clean;
    let cuerpo = clean.slice(0, -1);
    let dv = clean.slice(-1);
    let formatted = "";
    while (cuerpo.length > 3) {
      formatted = "." + cuerpo.slice(-3) + formatted;
      cuerpo = cuerpo.slice(0, -3);
    }
    return cuerpo + formatted + "-" + dv;
  },

  // Validador matemático de RUT Chileno usando el algoritmo Módulo 11
  validateRut(rut) {
    let clean = this.cleanRut(rut);
    if (clean.length < 8 || clean.length > 9) return false;
    let cuerpo = clean.slice(0, -1);
    let dv = clean.slice(-1);
    
    let suma = 0;
    let multiplo = 2;
    for (let i = 1; i <= cuerpo.length; i++) {
      let index = multiplo * parseInt(clean.charAt(cuerpo.length - i), 10);
      suma += index;
      multiplo = multiplo < 7 ? multiplo + 1 : 2;
    }
    let dvEsperado = 11 - (suma % 11);
    dvEsperado = dvEsperado === 11 ? "0" : dvEsperado === 10 ? "K" : dvEsperado.toString();
    return dvEsperado === dv;
  },

  // Generador de etiquetas con diseño sobrio y punto indicador sutil
  getStatusBadge(estado) {
    const mapaEstados = {
      'Preinscrito': { clase: 'badge-preinscrito', texto: 'Pre-inscrito (QR)' },
      'Recepcionado': { clase: 'badge-recepcionado', texto: 'Recepcionado Mesón' },
      'En Taller': { clase: 'badge-taller', texto: 'En Taller Técnico' },
      'Pausado': { clase: 'badge-pausado', texto: 'Pausado / Traspaso' },
      'Listo para Entrega': { clase: 'badge-listo', texto: 'Listo para Entrega' },
      'Entregado Conforme': { clase: 'badge-entregado', texto: 'Entregado Conforme' },
      'En Custodia': { clase: 'badge-custodia', texto: 'En Custodia / Pañol' }
    };
    const item = mapaEstados[estado] || { clase: 'badge-custodia', texto: estado };
    return `<span class="badge ${item.clase}"><span style="width:6px; height:6px; border-radius:50%; background-color:currentColor; display:inline-block; opacity:0.85;"></span>${item.texto}</span>`;
  },

  // Notificaciones Toast sobrias
  showToast(mensaje, tipo = 'success') {
    let contenedor = document.getElementById('toast-container');
    if (!contenedor) {
      contenedor = document.createElement('div');
      contenedor.id = 'toast-container';
      contenedor.style.cssText = 'position:fixed;top:20px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none;';
      document.body.appendChild(contenedor);
    }

    const toast = document.createElement('div');
    const colorBorde = tipo === 'danger' ? '#D3122A' : tipo === 'warning' ? '#F59E0B' : '#111827';

    toast.style.cssText = `
      background: #121214;
      color: #FFFFFF;
      padding: 12px 18px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      border-left: 4px solid ${colorBorde};
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
      opacity: 0;
      transform: translateY(-10px);
      transition: all 0.22s ease;
      display: flex;
      align-items: center;
      gap: 10px;
      pointer-events: auto;
    `;
    toast.innerHTML = `<span>${mensaje}</span>`;
    contenedor.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';
    }, 10);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-8px)';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  },

  // Manejo de Modales
  openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
  },

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  },

  // Sesión en navegador
  getUsuarioEnSesion() {
    try {
      const raw = sessionStorage.getItem('clinica_usuario_activo');
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  },

  guardarUsuarioEnSesion(usuario) {
    try {
      sessionStorage.setItem('clinica_usuario_activo', JSON.stringify(usuario));
    } catch (e) {}
  },

  // Barra de Navegación Limpia y Elegante
  renderHeader(claveActiva) {
    const usuario = this.getUsuarioEnSesion();
    const rol = usuario ? usuario.rol : 'publico';
    const nombre = usuario ? (usuario.nombre_completo || usuario.nombre_usuario) : '';

    let enlacesNav = '';

    if (rol === 'admin') {
      enlacesNav = `
        <li class="nav-item"><a href="/" class="${claveActiva === 'dashboard' ? 'active' : ''}">Panel</a></li>
        <li class="nav-item"><a href="/preinscripcion/" class="${claveActiva === 'pre' ? 'active' : ''}">1. Pre-inscripción</a></li>
        <li class="nav-item"><a href="/recepcion/" class="${claveActiva === 'rec' ? 'active' : ''}">2-3. Mesón</a></li>
        <li class="nav-item"><a href="/taller/" class="${claveActiva === 'tal' ? 'active' : ''}">4-5. Taller</a></li>
        <li class="nav-item"><a href="/control-calidad/" class="${claveActiva === 'qc' ? 'active' : ''}">6. V°B° Calidad</a></li>
        <li class="nav-item"><a href="/entrega/" class="${claveActiva === 'ent' ? 'active' : ''}">7-9. Entrega</a></li>
        <li class="nav-item"><a href="/metricas/" class="${claveActiva === 'met' ? 'active' : ''}">Métricas</a></li>
      `;
    } else if (rol === 'tecnico') {
      // El Alumno Técnico trabaja exclusivamente en su mesa de taller
      enlacesNav = `
        <li class="nav-item"><a href="/taller/" class="${claveActiva === 'tal' ? 'active' : ''}">Mesa de Taller</a></li>
      `;
    } else if (rol === 'recepcion') {
      // El Mesón de Recepción atiende preinscripciones/recepciones y entregas
      enlacesNav = `
        <li class="nav-item"><a href="/recepcion/" class="${claveActiva === 'rec' ? 'active' : ''}">2-3. Mesón</a></li>
        <li class="nav-item"><a href="/entrega/" class="${claveActiva === 'ent' ? 'active' : ''}">7-9. Entrega</a></li>
      `;
    } else if (rol === 'docente') {
      enlacesNav = `
        <li class="nav-item"><a href="/" class="${claveActiva === 'dashboard' ? 'active' : ''}">Panel</a></li>
        <li class="nav-item"><a href="/taller/" class="${claveActiva === 'tal' ? 'active' : ''}">Supervisión Taller</a></li>
        <li class="nav-item"><a href="/control-calidad/" class="${claveActiva === 'qc' ? 'active' : ''}">6. V°B° Calidad</a></li>
        <li class="nav-item"><a href="/metricas/" class="${claveActiva === 'met' ? 'active' : ''}">Métricas</a></li>
      `;
    } else {
      enlacesNav = `
        <li class="nav-item"><a href="/preinscripcion/" class="${claveActiva === 'pre' ? 'active' : ''}">Pre-inscripción QR</a></li>
        <li class="nav-item"><a href="/login/" class="${claveActiva === 'login' ? 'active' : ''}">Ingresar al Sistema</a></li>
      `;
    }

    const bloqueUsuario = usuario ? `
      <div style="display:flex; align-items:center; gap:0.65rem; margin-left:0.85rem; padding-left:0.85rem; border-left:1px solid var(--border-card);">
        <span style="font-size:0.8rem; font-weight:700; color:var(--text-main);">
          ${nombre} <span style="font-size:0.72rem; color:var(--inacap-rojo); font-weight:800; text-transform:uppercase;">[${rol}]</span>
        </span>
        <button onclick="ClinicaAPI.logout()" class="btn btn-outline btn-sm" style="padding:0.25rem 0.6rem; font-size:0.75rem;">
          Salir
        </button>
      </div>
    ` : `
      <a href="/login/" class="btn btn-primary btn-sm" style="margin-left:0.75rem;">Ingresar</a>
    `;

    return `
    <header class="topbar">
      <a href="/" class="brand">
        <span class="brand-badge">INACAP</span>
        <div>
          <span class="brand-title">Clínica del PC</span>
          <span class="brand-subtitle">Sede San Pedro de la Paz • TI3043</span>
        </div>
      </a>
      <nav>
        <ul class="nav-links">
          ${enlacesNav}
          ${bloqueUsuario}
        </ul>
      </nav>
    </header>
    `;
  },

  renderFooter() {
    return `
    <footer class="footer">
      <div style="max-width: 1240px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div style="font-weight: 700; letter-spacing: -0.01em;">Clínica del PC — Universidad Tecnológica de Chile INACAP</div>
        <div style="font-size: 0.76rem; color: #9CA3AF;">Sede San Pedro de la Paz • Asignatura TI3043 • Plataforma Local Django</div>
      </div>
    </footer>
    `;
  }
};

// Sincronización automática de sesión
(async function inicializarSesionUsuario() {
  try {
    const res = await ClinicaAPI.getUsuarioActual();
    if (res.autenticado && res.usuario) {
      AppUtils.guardarUsuarioEnSesion(res.usuario);
    } else {
      sessionStorage.removeItem('clinica_usuario_activo');
    }
  } catch (e) {}
})();
