/* ==============================================================================
   APP UTILS — ESTILO INSTITUCIONAL INACAP (ROJO, BLANCO Y NEGRO)
   Formateo de RUT, badges de estado sobrios, barra superior limpia y alertas.
   ============================================================================== */

window.AppUtils = {
  // Limpia el RUT dejando solo números y dígito verificador
  cleanRut(rut) {
    return typeof rut === 'string' ? rut.replace(/[^0-9kK]/g, '').toUpperCase() : '';
  },

  // Formatea un RUT chileno con puntos y guion (ej: 18.452.910-6)
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

  // Barra de progreso de la orden: 6 fases que resumen los 9 pasos del proceso
  renderProgreso(estado, faseForzada) {
    const fases = ['Pre-inscripción', 'Recepción', 'Taller', 'V°B° Calidad', 'Entrega', 'Cierre'];
    // Fase actual según el estado de la orden (6 = todo terminado); faseForzada permite fijarla a mano
    const faseActual = faseForzada ?? {
      'Preinscrito': 0,
      'Recepcionado': 1,
      'En Taller': 2,
      'Pausado': 2,
      'Listo para Entrega': 4,
      'En Custodia': 4,
      'Entregado Conforme': 6
    }[estado] ?? 0;

    return `<div class="progreso-orden" title="Estado: ${estado}">` + fases.map((nombre, i) => {
      const clase = i < faseActual ? 'hecho' : (i === faseActual ? 'actual' : '');
      return `<div class="progreso-paso ${clase}"><div class="progreso-punto">${i < faseActual ? '&#10003;' : i + 1}</div>${nombre}</div>`;
    }).join('') + '</div>';
  },

  // Ventana de confirmación (reemplaza al confirm() del navegador). Retorna una promesa true/false.
  confirmar(mensaje, opciones = {}) {
    const { titulo = 'Confirmar acción', textoOk = 'Confirmar', textoCancelar = 'Cancelar' } = opciones;
    return new Promise(resolver => {
      const fondo = document.createElement('div');
      fondo.className = 'modal-overlay active';
      fondo.style.zIndex = '2000';
      fondo.innerHTML = `
        <div class="modal-content" style="max-width:440px;" role="dialog" aria-modal="true">
          <div class="modal-header"><h3 class="modal-title"></h3></div>
          <p class="confirmar-mensaje" style="font-size:0.92rem; line-height:1.5; color:var(--text-secondary);"></p>
          <div class="modal-footer" style="display:flex; justify-content:flex-end; gap:0.5rem;">
            <button class="btn btn-outline btn-sm" data-r="0"></button>
            <button class="btn btn-primary btn-sm" data-r="1"></button>
          </div>
        </div>`;
      // textContent evita inyectar HTML con datos de la base de datos
      fondo.querySelector('.modal-title').textContent = titulo;
      fondo.querySelector('.confirmar-mensaje').textContent = mensaje;
      fondo.querySelector('[data-r="0"]').textContent = textoCancelar;
      fondo.querySelector('[data-r="1"]').textContent = textoOk;

      const alTeclear = e => { if (e.key === 'Escape') cerrar(false); };
      const cerrar = respuesta => {
        document.removeEventListener('keydown', alTeclear);
        fondo.remove();
        resolver(respuesta);
      };
      fondo.addEventListener('click', e => {
        if (e.target === fondo) return cerrar(false);
        const boton = e.target.closest('[data-r]');
        if (boton) cerrar(boton.dataset.r === '1');
      });
      document.addEventListener('keydown', alTeclear);
      document.body.appendChild(fondo);
      fondo.querySelector('[data-r="1"]').focus();
    });
  },

  // Selector de servicios (varias opciones con casillas). Se usa en pre-inscripción y mesón.
  SERVICIOS: [
    { nombre: 'Mantención Física', detalle: 'Limpieza de ventiladores, cambio de pasta térmica' },
    { nombre: 'Mantención Lógica', detalle: 'Optimización, limpieza de malware y temporales' },
    { nombre: 'Formateo', detalle: 'Formateo e instalación de sistema operativo' }
  ],

  renderSelectorServicios(contenedorId, seleccionados = []) {
    const cont = document.getElementById(contenedorId);
    cont.innerHTML = '';
    cont.classList.add('selector-servicios');
    this.SERVICIOS.forEach(serv => {
      const etiqueta = document.createElement('label');
      etiqueta.className = 'servicio-opcion';
      const casilla = document.createElement('input');
      casilla.type = 'checkbox';
      casilla.value = serv.nombre;
      casilla.checked = seleccionados.includes(serv.nombre);
      casilla.addEventListener('change', () => etiqueta.classList.toggle('marcado', casilla.checked));
      etiqueta.classList.toggle('marcado', casilla.checked);
      const texto = document.createElement('span');
      const titulo = document.createElement('strong');
      titulo.textContent = serv.nombre;
      const detalle = document.createElement('small');
      detalle.textContent = serv.detalle;
      texto.append(titulo, detalle);
      etiqueta.append(casilla, texto);
      cont.appendChild(etiqueta);
    });
  },

  leerServicios(contenedorId) {
    return [...document.querySelectorAll(`#${contenedorId} input:checked`)].map(c => c.value);
  },

  // Texto "Mantención Física + Formateo" a partir de una orden
  textoServicios(orden) {
    return (orden.servicios && orden.servicios.length ? orden.servicios : [orden.tipoServicio]).join(' + ');
  },

  escapar(texto) {
    return String(texto ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  // Texto del estado de encendido (null = todavía no lo verifica el técnico)
  textoEncendido(valor) {
    if (valor === null || valor === undefined) return 'Sin verificar';
    return valor ? 'Sí enciende' : 'No enciende';
  },

  // Pide un texto en una ventana propia (reemplaza al prompt() del navegador).
  // Retorna el texto escrito, o null si la persona cancela.
  pedirTexto(titulo, mensaje, opciones = {}) {
    const { textoOk = 'Guardar', textoCancelar = 'Cancelar', valorInicial = '', obligatorio = true, placeholder = '' } = opciones;
    return new Promise(resolver => {
      const fondo = document.createElement('div');
      fondo.className = 'modal-overlay active';
      fondo.style.zIndex = '2000';
      fondo.innerHTML = `
        <div class="modal-content" style="max-width:480px;" role="dialog" aria-modal="true">
          <div class="modal-header"><h3 class="modal-title"></h3></div>
          <p class="pedir-mensaje" style="font-size:0.88rem; color:var(--text-secondary); margin-bottom:0.75rem; line-height:1.45;"></p>
          <textarea class="form-control pedir-texto" rows="3"></textarea>
          <div class="pedir-error" style="display:none; color:var(--inacap-rojo); font-size:0.8rem; font-weight:600; margin-top:0.4rem;">Este dato es obligatorio.</div>
          <div class="modal-footer" style="display:flex; justify-content:flex-end; gap:0.5rem;">
            <button class="btn btn-outline btn-sm" data-r="0"></button>
            <button class="btn btn-primary btn-sm" data-r="1"></button>
          </div>
        </div>`;
      fondo.querySelector('.modal-title').textContent = titulo;
      fondo.querySelector('.pedir-mensaje').textContent = mensaje;
      const caja = fondo.querySelector('.pedir-texto');
      caja.placeholder = placeholder;
      caja.value = valorInicial;
      fondo.querySelector('[data-r="0"]').textContent = textoCancelar;
      fondo.querySelector('[data-r="1"]').textContent = textoOk;

      const alTeclear = e => { if (e.key === 'Escape') cerrar(null); };
      const cerrar = valor => {
        document.removeEventListener('keydown', alTeclear);
        fondo.remove();
        resolver(valor);
      };
      const aceptar = () => {
        const texto = caja.value.trim();
        if (obligatorio && !texto) {
          fondo.querySelector('.pedir-error').style.display = 'block';
          caja.style.borderColor = 'var(--inacap-rojo)';
          caja.focus();
          return;
        }
        cerrar(texto);
      };
      fondo.addEventListener('click', e => {
        if (e.target === fondo) return cerrar(null);
        const boton = e.target.closest('[data-r]');
        if (boton) boton.dataset.r === '1' ? aceptar() : cerrar(null);
      });
      document.addEventListener('keydown', alTeclear);
      document.body.appendChild(fondo);
      caja.focus();
      caja.select();
    });
  },

  // Bitácora: resumen automático de todo lo registrado en la orden (no son notas manuales)
  renderResumenBitacora(orden) {
    const e = t => this.escapar(t);
    const items = Object.entries(orden.checklists || {}).map(([codigo, v]) => ({ codigo, ...v }));
    const cuenta = r => items.filter(i => i.res === r).length;
    const revisados = items.filter(i => i.res !== 'PENDIENTE').length;
    const fallas = items.filter(i => i.res === 'FALLA');
    const observaciones = orden.observaciones || [];
    const esEvento = o => o.texto.startsWith('[PAUSA') || o.texto.startsWith('[ENVÍO') || o.texto.startsWith('[HALLAZGO');
    const traspasos = observaciones.filter(esEvento);
    const notas = observaciones.filter(o => !esEvento(o));
    const d = orden.dispositivo || {};

    const filas = [
      ['Equipo', `${e(d.tipo)} ${e(d.marca)} ${e(d.modelo)}`],
      ['Servicios', e(this.textoServicios(orden))],
      ['Técnico', e(orden.tecnicoAsignado || 'Sin asignar')],
      ['N° de serie', e(d.numeroSerie || 'Sin registrar')],
      ['Encendido', e(this.textoEncendido(orden.encendidoInicial))],
      ['Checklist', items.length
        ? `${revisados} de ${items.length} revisados — OK: ${cuenta('OK')} · Falla: ${cuenta('FALLA')} · N/A: ${cuenta('NO_APLICA')} · Pendientes: ${cuenta('PENDIENTE')}`
        : 'Sin checklist'],
      ['Estado', this.getStatusBadge(orden.estado)]
    ];

    let html = `<div style="display:grid; grid-template-columns:minmax(90px,130px) 1fr; gap:0.35rem 0.85rem; font-size:0.84rem; align-items:start;">
      ${filas.map(([k, v]) => `<div style="color:var(--gris-medio); font-weight:700;">${k}</div><div>${v}</div>`).join('')}
    </div>`;

    if (fallas.length) {
      html += `<div style="margin-top:0.85rem; font-size:0.84rem;"><strong style="color:var(--inacap-rojo);">Fallas detectadas (${fallas.length})</strong>
        <ul style="margin:0.35rem 0 0; padding-left:1.1rem; line-height:1.55;">
          ${fallas.map(f => `<li><strong>${e(f.codigo)}</strong> ${e(f.desc)}<br><span style="color:var(--text-secondary);">Motivo: ${e(f.motivo || 'Sin motivo registrado')}</span></li>`).join('')}
        </ul></div>`;
    }
    if (traspasos.length) {
      html += `<div style="margin-top:0.85rem; font-size:0.84rem;"><strong>Eventos del proceso (${traspasos.length})</strong>
        <ul style="margin:0.35rem 0 0; padding-left:1.1rem; line-height:1.55;">
          ${traspasos.map(t => `<li>${e(t.fecha)} — ${e(t.autor)}: ${e(t.texto)}</li>`).join('')}
        </ul></div>`;
    }
    if (notas.length) {
      html += `<div style="margin-top:0.85rem; font-size:0.84rem;"><strong>Notas anteriores</strong>
        <ul style="margin:0.35rem 0 0; padding-left:1.1rem; line-height:1.55;">
          ${notas.map(n => `<li>${e(n.fecha)} — ${e(n.autor)} [${e(n.criticidad)}]: ${e(n.texto)}</li>`).join('')}
        </ul></div>`;
    }
    return html;
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
        <li class="nav-item"><a href="/administracion/" class="${claveActiva === 'adm' ? 'active' : ''}">Administración</a></li>
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
        <li class="nav-item"><a href="/control-calidad/" class="${claveActiva === 'qc' ? 'active' : ''}">V°B° Calidad</a></li>
        <li class="nav-item"><a href="/estudiantes/" class="${claveActiva === 'est' ? 'active' : ''}">Estudiantes</a></li>
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

// Aviso breve cuando el sistema devolvió al usuario a su área de trabajo (?aviso=sin-acceso)
document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('aviso') === 'sin-acceso') {
    AppUtils.showToast('Esa sección no corresponde a tu perfil. Te devolvimos a tu área de trabajo.', 'warning');
    params.delete('aviso');
    const resto = params.toString();
    history.replaceState(null, '', window.location.pathname + (resto ? '?' + resto : ''));
  }
});
