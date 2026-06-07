/* ============================================================
     ACUEDUCTO RINCÓN SANTO — script.js
     ============================================================ */

  // ── PAGE LOADER ──
  (function(){
    var bar = document.getElementById('loaderBarFill');
    var pct = document.getElementById('loaderPercent');
    var loader = document.getElementById('pageLoader');
    var p = 0;
    var interval = setInterval(function(){
      var inc = p < 60 ? Math.random()*4+1.5 : p < 85 ? Math.random()*2+0.8 : Math.random()*0.4+0.1;
      p = Math.min(p + inc, 99);
      bar.style.width = p + '%';
      pct.textContent = Math.floor(p) + '%';
    }, 80);
    window.addEventListener('load', function(){
      clearInterval(interval);
      bar.style.transition = 'width 0.3s ease';
      bar.style.width = '100%';
      pct.textContent = '100%';
      setTimeout(function(){
        loader.classList.add('loader-hide');
        setTimeout(function(){ loader.style.display='none'; }, 900);
      }, 1200);
    });
  })();

  // ── WATER CANVAS ──
  const canvas = document.getElementById('waterCanvas');
  const ctx = canvas.getContext('2d');
  function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
  resize();
  window.addEventListener('resize', resize);
  const waves = [
    { y:0.75, amp:40, freq:0.008, speed:0.015, phase:0, opacity:0.07 },
    { y:0.82, amp:30, freq:0.012, speed:0.020, phase:2, opacity:0.05 },
    { y:0.90, amp:20, freq:0.018, speed:0.025, phase:4, opacity:0.04 },
  ];
  function drawWaves(t) {
    ctx.clearRect(0,0,canvas.width,canvas.height);
    const grad = ctx.createLinearGradient(0,0,0,canvas.height);
    grad.addColorStop(0,'#0a2540'); grad.addColorStop(0.6,'#0d3558'); grad.addColorStop(1,'#0a2540');
    ctx.fillStyle = grad; ctx.fillRect(0,0,canvas.width,canvas.height);
    const glow = ctx.createRadialGradient(canvas.width*0.8,canvas.height*0.3,0,canvas.width*0.8,canvas.height*0.3,canvas.width*0.5);
    glow.addColorStop(0,'rgba(26,143,209,0.08)'); glow.addColorStop(1,'transparent');
    ctx.fillStyle = glow; ctx.fillRect(0,0,canvas.width,canvas.height);
    waves.forEach(w => {
      ctx.beginPath(); ctx.moveTo(0,canvas.height);
      for(let x=0;x<=canvas.width;x+=3){
        const y = canvas.height*w.y + Math.sin(x*w.freq+w.phase+t*w.speed)*w.amp + Math.sin(x*w.freq*1.7+w.phase*1.3+t*w.speed*0.7)*(w.amp*0.4);
        ctx.lineTo(x,y);
      }
      ctx.lineTo(canvas.width,canvas.height); ctx.closePath();
      const wg = ctx.createLinearGradient(0,canvas.height*w.y-w.amp,0,canvas.height);
      wg.addColorStop(0,`rgba(26,143,209,${w.opacity})`); wg.addColorStop(1,'rgba(10,37,64,0.2)');
      ctx.fillStyle=wg; ctx.fill();
    });
  }
  let t=0; function animateCanvas(){ t++; drawWaves(t); requestAnimationFrame(animateCanvas); } animateCanvas();

  // ── FLOATING DROPS ──
  const dropContainer = document.getElementById('dropContainer');
  const dropColors = ['rgba(26,143,209,0.6)','rgba(0,200,150,0.5)','rgba(126,206,244,0.55)','rgba(245,197,24,0.4)'];
  function createFloatingDrop(){
    const el=document.createElement('div'); el.className='drop';
    const size=8+Math.random()*30;
    el.style.cssText=`width:${size}px;height:${size*1.3}px;left:${Math.random()*100}%;background:${dropColors[Math.floor(Math.random()*dropColors.length)]};box-shadow:inset 0 0 ${size/2}px rgba(255,255,255,0.2);animation-duration:${8+Math.random()*14}s;animation-delay:${Math.random()*-20}s;`;
    dropContainer.appendChild(el);
  }
  for(let i=0;i<18;i++) createFloatingDrop();

  // ── SCROLL REVEAL ──
  const revealObserver = new IntersectionObserver(entries=>{
    entries.forEach(e=>{ if(e.isIntersecting) e.target.classList.add('visible'); });
  },{ threshold:0.1 });
  document.querySelectorAll('.reveal').forEach(el=>revealObserver.observe(el));

  // ── NAVBAR SCROLL ──
  const navbar = document.getElementById('navbar');
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 50);
    let current = '';
    document.querySelectorAll('section[id]').forEach(s => {
      if (window.scrollY >= s.offsetTop - 200) current = s.id;
    });
    document.querySelectorAll('.nav-links a').forEach(l => {
      l.classList.toggle('active', l.getAttribute('href') === '#' + current);
    });
  }, { passive: true });

  // ── HAMBURGER ──
  const hamburger = document.getElementById('hamburger');
  const navLinks = document.getElementById('navLinks');
  hamburger.addEventListener('click', () => {
    navLinks.classList.toggle('open');
    hamburger.classList.toggle('active');
  });
  document.querySelectorAll('.nav-links a').forEach(l => {
    l.addEventListener('click', () => navLinks.classList.remove('open'));
  });

  // ── COUNTER ANIMATION ──
  function animateCount(el, target) {
    let startTs;
    const step = ts => {
      if(!startTs) startTs=ts;
      const prog = Math.min((ts-startTs)/1800,1);
      const ease = 1-Math.pow(1-prog,3);
      el.textContent = Math.floor(ease*target);
      if(prog<1) requestAnimationFrame(step);
      else el.textContent = target;
    };
    requestAnimationFrame(step);
  }
  const statsObserver = new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        const nums = e.target.querySelectorAll('[data-target]');
        nums.forEach(n => animateCount(n, parseInt(n.dataset.target)));
        statsObserver.unobserve(e.target);
      }
    });
  },{ threshold:0.4 });
  const strip = document.querySelector('.stats-strip');
  if(strip) statsObserver.observe(strip);

  // ── MODAL (cierre y teclas — el modal ya no se abre desde aquí) ──
  const overlay = document.getElementById('modalOverlay');
  const modalClose = document.getElementById('modalClose');
  function closeModal() { overlay.classList.remove('open'); document.body.style.overflow=''; }
  if(modalClose) modalClose.addEventListener('click', closeModal);
  if(overlay) overlay.addEventListener('click', e => { if(e.target===overlay) closeModal(); });
  document.addEventListener('keydown', e => { if(e.key==='Escape') closeModal(); });
  document.querySelectorAll('.modal .tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.modal .tab').forEach(t=>t.classList.remove('active'));
      tab.classList.add('active');
    });
  });

  function togglePw() {
    const pw = document.getElementById('pwInput');
    if(pw) pw.type = pw.type==='password' ? 'text' : 'password';
  }
  window.togglePw = togglePw;

  // ── FUNCIÓN CENTRAL DE REDIRECCIÓN A LOGIN ──
  // Todos los accesos protegidos usan esta función.
  // Puedes agregar un parámetro ?next= para redirigir de vuelta después del login.
  function irALogin(motivo) {
    const url = motivo ? `/login?next=${encodeURIComponent(motivo)}` : '/login';
    window.location.href = url;
  }
  window.irALogin = irALogin;

  // ── BOTÓN NAVBAR — "Iniciar Sesión" ──
  const btnLogin = document.getElementById('btnLogin');
  if(btnLogin) {
    btnLogin.addEventListener('click', () => irALogin('navbar'));
  }

  // ── BOTÓN HERO — "Consultar factura" ──
  // El botón es el segundo .btn-secondary dentro del hero
  const btnConsultarHero = document.querySelector('#inicio .btn-secondary');
  if(btnConsultarHero) {
    btnConsultarHero.addEventListener('click', () => irALogin('consultar-factura'));
  }

  // ── BOTONES DE MÓDULOS — los 6 "Acceder" ──
  // Cada tarjeta tiene data-color; usamos el número de módulo como referencia
  const moduloDestinos = [
    'pago',           // Módulo 01 — Paga Aquí
    'factura',        // Módulo 02 — Todo sobre mi factura
    'acuerdos',       // Módulo 03 — Acuerdos de Pago
    'cortes',         // Módulo 04 — Programación de cortes
    'puntos-pago',    // Módulo 05 — Puntos de pago
    'pqrs',           // Módulo 06 — PQRS
  ];
  document.querySelectorAll('.module-btn').forEach((btn, i) => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      irALogin(moduloDestinos[i] || 'modulo');
    });
  });

  document.querySelectorAll('.modules-section .module-card[data-next]').forEach(card => {
    const abrirModulo = () => irALogin(card.dataset.next || 'modulo');
    card.addEventListener('click', abrirModulo);
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        abrirModulo();
      }
    });
  });

  // ── SECCIÓN ACCESO RÁPIDO — botones "Consultar factura", "Iniciar sesión", "Radicar PQRS" ──
  const qaBtns = document.querySelectorAll('.qa-btn');
  // qa-btn[0] = Consultar factura  |  qa-btn[1] = Iniciar sesión  |  qa-btn[2] = Radicar PQRS
  const qaDestinos = ['/facturas/consultar', 'login', 'pqrs'];
  qaBtns.forEach((btn, i) => {
    // Remover onclick inline si existía
    btn.removeAttribute('onclick');
    btn.addEventListener('click', () => {
      if (qaDestinos[i] && qaDestinos[i].charAt(0) === '/') window.location.href = qaDestinos[i];
      else irALogin(qaDestinos[i] || 'acceso-rapido');
    });
  });

  // ── LINKS DE MÓDULOS EN EL FOOTER ──
  // Los 6 primeros <li><a> del primer .footer-links-group
  const footerModuloLinks = document.querySelectorAll('.footer-links-group:first-of-type a');
  const footerModuloDestinos = ['facturacion','gestion-usuarios','registro-pagos','morosidad','pqrs','reportes'];
  footerModuloLinks.forEach((a, i) => {
    a.addEventListener('click', e => {
      e.preventDefault();
      irALogin(footerModuloDestinos[i] || 'footer-modulo');
    });
  });

  // ── LINKS DE SERVICIOS EN EL FOOTER ──
  // "Consultar factura", "Puntos de pago", "Solicitud de corte", "Paz y salvo"
  const footerServicioLinks = document.querySelectorAll('.footer-links-group:nth-of-type(2) a');
  const footerServicioDestinos = ['consultar-factura','puntos-pago','solicitud-corte','paz-y-salvo'];
  footerServicioLinks.forEach((a, i) => {
    a.addEventListener('click', e => {
      e.preventDefault();
      irALogin(footerServicioDestinos[i] || 'footer-servicio');
    });
  });

  // ── FORM CONTACTO ──
  function handleForm(e) {
    e.preventDefault();
    const btn = e.target.querySelector('.form-submit');
    const success = document.getElementById('formSuccess');
    btn.textContent='Enviando...'; btn.style.opacity='0.7';
    setTimeout(() => {
      btn.style.display='none';
      success.classList.add('show');
      e.target.reset();
      setTimeout(() => {
        success.classList.remove('show');
        btn.style.display='';
        btn.style.opacity='';
        btn.innerHTML=`Enviar solicitud <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
      }, 4000);
    }, 1400);
  }
  window.handleForm = handleForm;

  // ── TYPING EFFECT ──
  (function heroTyping() {
    const em = document.getElementById('heroTyping');
    if (!em) return;
    const phrases = ['Gestión inteligente.', 'Facturación digital.', 'Transparencia total.'];
    let idx=0, charIdx=0, deleting=false;
    function type() {
      const phrase = phrases[idx];
      if (!deleting) {
        em.textContent = phrase.slice(0, charIdx+1); charIdx++;
        if (charIdx===phrase.length) { deleting=true; setTimeout(type,2400); return; }
      } else {
        em.textContent = phrase.slice(0, charIdx-1); charIdx--;
        if (charIdx===0) { deleting=false; idx=(idx+1)%phrases.length; }
      }
      setTimeout(type, deleting ? 40 : 80);
    }
    setTimeout(type, 2000);
  })();

  // ── SMOOTH SCROLL (solo anclas internas) ──
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', e => {
      const id = link.getAttribute('href');
      if (id==='#') return;
      const target = document.querySelector(id);
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior:'smooth', block:'start' }); }
    });
  });

  // ── THEME TOGGLE (dark / light) ──────────
  (function initTheme() {
    const toggle = document.getElementById('themeToggle');
    const html = document.documentElement;
    const stored = localStorage.getItem('aquarincon-theme');
    if (stored === 'light') html.classList.add('light-mode');
    if (toggle) {
      toggle.addEventListener('click', () => {
        html.classList.toggle('light-mode');
        localStorage.setItem('aquarincon-theme', html.classList.contains('light-mode') ? 'light' : 'dark');
      });
    }
  })();

  console.log('%c💧 Acueducto Rincón Santo', 'color:#4FC3F7;font-size:18px;font-weight:bold;');
  console.log('%c Sistema de Gestión v2.0 — ITFIP 2026', 'color:#B0BEC5;');
