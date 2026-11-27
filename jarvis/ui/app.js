// Interfaz de Jarvis: escena 3D, expresiones con transición suave, onda de voz real y chat en vivo.
(function () {
  const $ = (id) => document.getElementById(id);
  const raiz = document.documentElement;
  const chat = $("chat"), lista = $("resultados"), punto = $("punto"), estadoTexto = $("estadoTexto"), pista = $("pista");
  const api = () => window.pywebview && window.pywebview.api;

  const ESTADOS = {
    esperando:  { cara: "normal",      pista: "Di «Jarvis» o toca el micrófono", cabecera: "En línea" },
    escuchando: { cara: "sorprendido", pista: "Te escucho…",                      cabecera: "Escuchando" },
    pensando:   { cara: "pensando",    pista: "Pensando…",                        cabecera: "Procesando" },
    hablando:   { cara: "riendo",      pista: "Toca el micrófono para interrumpir", cabecera: "Hablando" },
    dormido:    { cara: "dormido",     pista: "Durmiendo. Di «Jarvis» para despertarme", cabecera: "Dormido" },
    sin_voz:    { cara: "triste",      pista: "Micrófono no disponible: escríbeme", cabecera: "Solo texto" },
  };
  let estado = "esperando";

  // ---------- colores (tema) ----------
  let colores = ["#22d3ee", "#8b5cf6", "#ec4899"];
  function leerColores() {
    const cs = getComputedStyle(document.body);
    colores = ["--c1", "--c2", "--c3"].map((v) => cs.getPropertyValue(v).trim() || "#1fa3ff");
  }
  function ponerTema(tema) {
    document.body.dataset.tema = tema || "aurora";
    try { localStorage.setItem("jarvisTema", document.body.dataset.tema); } catch (e) {}
    leerColores();
  }
  try { ponerTema(localStorage.getItem("jarvisTema")); } catch (e) { ponerTema("aurora"); }
  const hexRgb = (h) => { const n = parseInt(h.replace("#", ""), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
  function mezcla(f) { // color en el degradado c1 -> c2 -> c3, f de 0 a 1
    const [a, b] = f < 0.5 ? [colores[0], colores[1]] : [colores[1], colores[2]];
    const k = f < 0.5 ? f * 2 : (f - 0.5) * 2, A = hexRgb(a), B = hexRgb(b);
    return A.map((x, i) => Math.round(x + (B[i] - x) * k));
  }

  // ---------- partículas 3D de fondo ----------
  const fondo = $("fondo"), fctx = fondo.getContext("2d");
  let W = 0, H = 0, particulas = [];
  function redimensionar() {
    const dpr = window.devicePixelRatio || 1;
    W = innerWidth; H = innerHeight;
    fondo.width = W * dpr; fondo.height = H * dpr;
    fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    particulas = Array.from({ length: Math.round(W * H / 4500) }, () => ({
      x: Math.random() * W, y: Math.random() * H, z: Math.random() * 0.9 + 0.1, v: Math.random() * 0.25 + 0.05,
      c: Math.floor(Math.random() * 3), fase: Math.random() * 6.3,
    }));
  }
  addEventListener("resize", redimensionar);
  redimensionar();

  // ---------- inclinación 3D con el ratón ----------
  let objetivoX = 0, objetivoY = 0, actualX = 0, actualY = 0;
  addEventListener("mousemove", (e) => {
    objetivoY = (e.clientX / W - 0.5) * 18;
    objetivoX = -(e.clientY / H - 0.5) * 12;
  });
  addEventListener("mouseleave", () => { objetivoX = objetivoY = 0; });

  // ---------- movimiento natural del holograma ----------
  // Respira, se balancea, mira a los lados y parpadea solo; cambia de postura según lo que esté haciendo.
  const caja = $("avatarCaja"), parpadeo = $("parpadeo");
  const mov = { x: 0, y: 0, rz: 0, ry: 0, objX: 0, objY: 0, cambio: 0 };
  let proximoParpadeo = 2.5;
  function moverHolograma(n) {
    if (t > mov.cambio) { // elige otro punto al que mirar
      const quieto = estado === "dormido";
      mov.objX = quieto ? 0 : (Math.random() * 2 - 1) * (estado === "escuchando" ? 3 : 9);
      mov.objY = quieto ? 5 : (Math.random() * 2 - 1) * 3 + (estado === "pensando" ? -6 : 0);
      mov.cambio = t + 2 + Math.random() * 4;
    }
    const suave = estado === "dormido" ? 0.01 : 0.035;
    mov.x += (mov.objX - mov.x) * suave;
    mov.y += (mov.objY - mov.y) * suave;
    const ritmo = estado === "dormido" ? 0.6 : 1.7;
    const respira = Math.sin(t * ritmo) * (estado === "dormido" ? 0.02 : 0.012);
    const inclina = estado === "pensando" ? 6 : estado === "dormido" ? -5 : 0;
    mov.rz += (Math.sin(t * 0.55) * 1.6 + Math.sin(t * 0.23) * 0.9 + inclina - mov.rz) * 0.04;
    const flota = Math.sin(t * 0.9) * 5 + Math.sin(t * 2.1) * 1.2;
    const habla = estado === "hablando" ? Math.sin(t * 11) * n * 2.5 : 0;
    const cerca = estado === "escuchando" ? 0.04 : 0;
    raiz.style.setProperty("--ax", (mov.x).toFixed(2) + "px");
    raiz.style.setProperty("--ay", (mov.y * 0.6 + flota - n * 3 + habla).toFixed(2) + "px");
    raiz.style.setProperty("--az", mov.rz.toFixed(2) + "deg");
    raiz.style.setProperty("--ay-rot", (mov.x * 1.1).toFixed(2) + "deg");
    raiz.style.setProperty("--as", (1 + respira + cerca + n * 0.035).toFixed(4));
    // parpadeo: solo con la cara normal, cada 2,5 a 6 segundos (a veces doble)
    if (t > proximoParpadeo) {
      if (caraActual === "normal" && estado !== "dormido") {
        parpadeo.classList.add("cerrado");
        setTimeout(() => parpadeo.classList.remove("cerrado"), 120);
        if (Math.random() < 0.2) setTimeout(() => { parpadeo.classList.add("cerrado"); setTimeout(() => parpadeo.classList.remove("cerrado"), 110); }, 260);
      }
      proximoParpadeo = t + 2.5 + Math.random() * 3.5;
    }
  }

  // ---------- onda de voz ----------
  const onda = $("onda"), octx = onda.getContext("2d");
  let nivelObjetivo = 0, nivel = 0, t = 0;

  function dibujar() {
    t += 1 / 60;
    // suavizado: la voz sube rápido y baja despacio, como un medidor real
    nivel += (nivelObjetivo - nivel) * (nivelObjetivo > nivel ? 0.45 : 0.12);
    const extra = estado === "escuchando" ? 0.18 + Math.sin(t * 3) * 0.06 : estado === "pensando" ? 0.1 : 0;
    const n = Math.max(nivel, extra);
    raiz.style.setProperty("--nivel", n.toFixed(3));

    actualX += (objetivoX + Math.sin(t * 0.6) * 2 - actualX) * 0.06;
    actualY += (objetivoY + Math.sin(t * 0.4) * 4 - actualY) * 0.06;
    raiz.style.setProperty("--rx", actualX.toFixed(2) + "deg");
    raiz.style.setProperty("--ry", actualY.toFixed(2) + "deg");
    moverHolograma(n);

    // partículas con profundidad: las cercanas son más grandes, rápidas y se mueven más con el ratón
    fctx.clearRect(0, 0, W, H);
    for (const p of particulas) {
      p.y -= p.v * p.z * (1 + n * 3);
      if (p.y < -4) { p.y = H + 4; p.x = Math.random() * W; }
      const px = p.x + actualY * p.z * 3, py = p.y - actualX * p.z * 3;
      fctx.globalAlpha = (0.15 + p.z * 0.55) * (0.75 + 0.25 * Math.sin(t * 2 + p.fase));
      fctx.fillStyle = p.z > 0.85 ? "#ffffff" : colores[p.c];
      fctx.beginPath(); fctx.arc(px, py, p.z * 1.7, 0, 7); fctx.fill();
    }
    fctx.globalAlpha = 1;

    // barras simétricas de la onda
    const dpr = window.devicePixelRatio || 1;
    const ow = onda.clientWidth, oh = onda.clientHeight;
    if (onda.width !== ow * dpr) { onda.width = ow * dpr; onda.height = oh * dpr; }
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.clearRect(0, 0, ow, oh);
    const barras = 48, ancho = ow / barras, mitad = barras / 2;
    for (let i = 0; i < barras; i++) {
      const d = Math.abs(i - mitad + 0.5) / mitad;             // 0 en el centro, 1 en los bordes
      const ruido = Math.sin(t * 9 + i * 0.9) * 0.5 + Math.sin(t * 5.3 + i * 1.7) * 0.5;
      const h = 2 + (oh - 6) * n * (1 - d * 0.75) * (0.55 + 0.45 * Math.abs(ruido));
      const x = i * ancho + ancho * 0.3, y = (oh - h) / 2;
      const [r, gg, b] = mezcla(i / (barras - 1));
      const g = octx.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, `rgba(${r},${gg},${b},.95)`); g.addColorStop(1, `rgba(${r},${gg},${b},.45)`);
      octx.fillStyle = g;
      octx.shadowColor = `rgb(${r},${gg},${b})`; octx.shadowBlur = 8;
      octx.fillRect(x, y, ancho * 0.4, h);
    }
    requestAnimationFrame(dibujar);
  }
  requestAnimationFrame(dibujar);

  // ---------- expresiones con fundido cruzado ----------
  const caras = [$("caraA"), $("caraB")];
  let visible = 0, caraActual = "normal";
  // precarga para que el cambio sea instantáneo
  ["normal", "riendo", "guino", "sorprendido", "pensando", "preocupado", "enojado", "dormido", "triste", "parpadeo"]
    .forEach((n) => { const i = new Image(); i.src = "assets/expresiones/" + n + ".png"; });
  function ponerCara(nombre) {
    if (!nombre || nombre === caraActual) return;
    caraActual = nombre;
    const siguiente = 1 - visible;
    caras[siguiente].src = "assets/expresiones/" + nombre + ".png";
    caras[siguiente].classList.add("visible");
    caras[visible].classList.remove("visible");
    visible = siguiente;
  }

  // ---------- chat ----------
  let burbujaViva = null;
  function mensaje(texto, quien, error) {
    const d = document.createElement("div");
    d.className = "msg " + quien + (error ? " error" : "");
    d.textContent = texto;
    chat.appendChild(d);
    while (chat.children.length > 60) chat.firstChild.remove();
    chat.scrollTop = chat.scrollHeight;
    return d;
  }

  function mostrarResultados(res) {
    lista.innerHTML = "";
    res.forEach((r, i) => {
      const li = document.createElement("li");
      li.title = r.ruta;
      li.style.animationDelay = i * 0.03 + "s";
      li.innerHTML = "<b></b><span></span><small></small>";
      li.children[0].textContent = i + 1;
      li.children[1].textContent = r.nombre;
      li.children[2].textContent = r.ruta;
      li.onclick = () => api() && api().abrir_resultado(i);
      lista.appendChild(li);
    });
  }

  let expresionRespuesta = null;
  window.jarvis = {
    nivel(n) { nivelObjetivo = n; },
    actualizar(d) {
      if (d.estado) {
        estado = d.estado;
        document.body.dataset.estado = estado;
        const e = ESTADOS[estado] || ESTADOS.esperando;
        estadoTexto.textContent = e.cabecera;
        pista.textContent = e.pista;
        punto.className = "estado-punto " + (estado === "sin_voz" ? "error" : estado === "dormido" ? "" : "vivo");
        if (estado === "hablando") ponerCara(d.expresion || expresionRespuesta || "riendo");
        else ponerCara(e.cara);
        if (estado !== "hablando") nivelObjetivo = 0;
        if (estado === "pensando") expresionRespuesta = null;
      }
      if (d.expresion) { expresionRespuesta = d.expresion; if (estado === "hablando") ponerCara(d.expresion); }
      if (d.parcial) pista.textContent = "«" + d.parcial + "»";
      if (d.orden) { mensaje(d.orden, "yo"); burbujaViva = null; lista.innerHTML = ""; }
      if (d.respuesta_parcial !== undefined) {
        if (!burbujaViva) { burbujaViva = mensaje("", "jarvis"); burbujaViva.classList.add("escribiendo"); }
        burbujaViva.textContent = d.respuesta_parcial;
        chat.scrollTop = chat.scrollHeight;
      }
      if (d.respuesta_fin && burbujaViva) { burbujaViva.classList.remove("escribiendo"); burbujaViva = null; }
      if (d.respuesta) mensaje(d.respuesta, "jarvis", d.expresion === "triste" || d.expresion === "enojado");
      if (d.mensaje) mensaje(d.mensaje, "jarvis", true);
      if (d.resultados) mostrarResultados(d.resultados);
      if (d.avisos !== undefined) {
        const ins = $("insignia");
        ins.hidden = !d.avisos; ins.textContent = d.avisos;
        if (!$("panelAgenda").hidden) abrirAgenda();
      }
      if (d.gestos_activos !== undefined) $("btnGestos").classList.toggle("activo", !!d.gestos_activos);
      if (d.vigilando !== undefined) { $("btnVigilar").classList.toggle("activo", !!d.vigilando); document.body.classList.toggle("vigilando", !!d.vigilando); }
      if (d.gesto) {
        const g = $("gesto"); g.textContent = d.gesto; g.hidden = false;
        clearTimeout(window._tGesto); window._tGesto = setTimeout(() => { g.hidden = true; }, 1600);
      }
      if (d.aviso) { document.body.classList.add("alerta"); setTimeout(() => document.body.classList.remove("alerta"), 2000); }
    },
  };

  // ---------- controles ----------
  $("formulario").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const t = $("texto").value.trim();
    if (!t || !api()) return;
    $("texto").value = "";
    api().enviar_texto(t);
  });
  $("btnMic").onclick = () => {
    if (!api()) return;
    if (estado === "hablando") api().callar();
    api().escuchar();
  };
  $("btnOcultar").onclick = () => api() && api().ocultar();
  $("btnVigilar").onclick = async () => {
    if (!api() || !api().vigilancia) return;
    const activa = await api().vigilancia();
    $("btnVigilar").classList.toggle("activo", !!activa);
    document.body.classList.toggle("vigilando", !!activa);
  };
  $("btnGestos").onclick = async () => {
    if (!api() || !api().gestos) return;
    const activos = await api().gestos();
    $("btnGestos").classList.toggle("activo", !!activos);
    mensaje(activos ? "Gestos activados: ✋ hablar · ✊ silencio · 👍 sí · 👎 no · ☝️/✌️ volumen · 🤟 mostrar/ocultar"
                    : "Gestos desactivados.", "jarvis");
  };
  // Arrastrar un documento: Python recibe la ruta; aquí solo se muestra el aviso visual.
  let arrastres = 0;
  addEventListener("dragenter", (e) => { e.preventDefault(); arrastres++; document.body.classList.add("soltando"); });
  addEventListener("dragleave", () => { if (--arrastres <= 0) { arrastres = 0; document.body.classList.remove("soltando"); } });
  addEventListener("dragover", (e) => e.preventDefault());
  addEventListener("drop", (e) => { e.preventDefault(); arrastres = 0; document.body.classList.remove("soltando"); });
  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && api()) { api().callar(); $("panelAjustes").hidden = true; $("panelAgenda").hidden = true; }
  });

  // ---------- ajustes ----------
  const panel = $("panelAjustes");
  async function abrirAjustes() {
    if (!api()) return;
    const a = await api().leer_ajustes();
    $("clave").value = "";
    $("claveEstado").textContent = a.tiene_clave
      ? "Clave guardada (termina en " + a.clave_final + "). Escribe otra solo si quieres cambiarla."
      : "Sin clave: Jarvis solo hace las órdenes del computador.";
    $("motor").value = a.voz_motor;
    $("conversacion").checked = !!a.modo_conversacion;
    $("gestosInicio").checked = !!a.gestos_al_iniciar;
    pintarSeguridad(a);
    panel.hidden = false;
  }
  function pintarSeguridad(a) {
    $("tema").value = a.tema || "aurora";
    $("soloDueno").checked = !!a.solo_dueno;
    $("avisosSeguridad").checked = a.avisos_seguridad !== false;
    $("celular").checked = !!a.celular;
    const sabe = [a.conoce_voz && "tu voz", a.conoce_cara && "tu cara"].filter(Boolean);
    $("identidadEstado").textContent = sabe.length ? "Ya conozco " + sabe.join(" y ") + "." : "Aún no te conozco: enséñame tu voz o tu cara.";
    $("btnVoz").textContent = (a.conoce_voz ? "🔁 Volver a aprender" : "🎙️ Aprender") + " mi voz";
    $("btnCara").textContent = (a.conoce_cara ? "🔁 Volver a aprender" : "🙂 Aprender") + " mi cara";
    $("soloDueno").disabled = !(a.conoce_voz || a.conoce_cara);
    $("qrCaja").hidden = !(a.celular_activo && a.celular_qr);
    if (a.celular_qr) $("qr").innerHTML = a.celular_qr; // SVG generado en Python a partir de la dirección local
    $("direccion").textContent = a.celular_direccion || "";
  }
  document.querySelectorAll("[data-orden]").forEach((b) => b.onclick = () => {
    panel.hidden = true; api() && api().orden(b.dataset.orden);
  });
  $("celular").onchange = async () => pintarSeguridad(await api().guardar_ajustes({ celular: $("celular").checked }));
  $("btnCodigo").onclick = async () => pintarSeguridad(await api().nuevo_codigo_celular());
  $("tema").onchange = () => ponerTema($("tema").value);
  $("btnAjustes").onclick = abrirAjustes;
  panel.addEventListener("click", (e) => { if (e.target === panel) panel.hidden = true; });
  $("btnGuardar").onclick = async () => {
    await api().guardar_ajustes({
      anthropic_api_key: $("clave").value.trim(),
      voz_motor: $("motor").value,
      modo_conversacion: $("conversacion").checked,
      gestos_al_iniciar: $("gestosInicio").checked,
      tema: $("tema").value,
      solo_dueno: $("soloDueno").checked,
      avisos_seguridad: $("avisosSeguridad").checked,
      celular: $("celular").checked,
    });
    panel.hidden = true;
    mensaje("Ajustes guardados.", "jarvis");
  };
  $("btnNueva").onclick = () => { api() && api().nueva_conversacion(); chat.innerHTML = ""; lista.innerHTML = ""; panel.hidden = true; };

  // ---------- agenda ----------
  const panelAgenda = $("panelAgenda");
  function itemLista(texto, extra, alQuitar) {
    const li = document.createElement("li");
    li.innerHTML = "<span></span><em></em><button title='Quitar' aria-label='Quitar'>✕</button>";
    li.children[0].textContent = texto;
    li.children[1].textContent = extra || "";
    li.children[2].onclick = alQuitar;
    return li;
  }
  function pintarAgenda(p) {
    const avisos = $("listaAvisos"), rutinas = $("listaRutinas"), datos = $("listaDatos");
    avisos.innerHTML = ""; rutinas.innerHTML = ""; datos.innerHTML = "";
    const iconos = { alarma: "⏰ ", temporizador: "⏱ ", recordatorio: "🔔 " };
    p.avisos.forEach((a) => avisos.appendChild(itemLista((iconos[a.tipo] || "") + (a.mensaje || a.tipo), a.cuando,
      async () => pintarAgenda(await api().cancelar_aviso(a.id)))));
    p.rutinas.forEach((r) => {
      const b = document.createElement("button");
      b.textContent = "▶ " + r;
      b.onclick = () => { panelAgenda.hidden = true; api().ejecutar_rutina(r); };
      rutinas.appendChild(b);
    });
    p.datos.forEach((d, i) => datos.appendChild(itemLista(d, "", async () => pintarAgenda(await api().olvidar_dato(i)))));
    $("infoResumenes").textContent = p.resumenes
      ? "Además recuerda " + p.resumenes + (p.resumenes === 1 ? " conversación anterior." : " conversaciones anteriores.")
      : "Di «recuerda que…» para que lo guarde.";
    $("insignia").hidden = !p.avisos.length; $("insignia").textContent = p.avisos.length;
  }
  async function abrirAgenda() {
    if (!api() || !api().leer_panel) return;
    pintarAgenda(await api().leer_panel());
    panelAgenda.hidden = false;
  }
  $("btnAgenda").onclick = abrirAgenda;
  $("btnCerrarAgenda").onclick = () => { panelAgenda.hidden = true; };
  panelAgenda.addEventListener("click", (e) => { if (e.target === panelAgenda) panelAgenda.hidden = true; });

  window.addEventListener("pywebviewready", async () => {
    window.jarvis.actualizar({ estado: "esperando" });
    try { const a = await api().leer_ajustes(); ponerTema(a.tema); window.jarvis.actualizar({ vigilando: a.vigilando }); } catch (e) {}
  });

  // Modo demostración al abrir index.html en un navegador normal.
  setTimeout(() => {
    if (window.pywebview) return;
    const hablar = (texto, cara) => {
      jarvis.actualizar({ estado: "hablando", expresion: cara });
      let i = 0; const palabras = texto.split(" ");
      const iv = setInterval(() => {
        i++; jarvis.actualizar({ respuesta_parcial: palabras.slice(0, i).join(" ") });
        jarvis.nivel(0.3 + Math.random() * 0.6);
        if (i >= palabras.length) { clearInterval(iv); jarvis.nivel(0); jarvis.actualizar({ respuesta_fin: true, estado: "esperando" }); }
      }, 140);
    };
    window.pywebview = { api: {
      enviar_texto: (t) => { jarvis.actualizar({ estado: "pensando", orden: t }); setTimeout(() => hablar("(Demo) Hola, soy Jarvis. Recibí: " + t, "guino"), 700); },
      escuchar: () => jarvis.actualizar({ estado: "escuchando" }), callar() {}, ocultar() {}, abrir_resultado() {},
      leer_ajustes: async () => ({ tiene_clave: false, voz_motor: "piper", modo_conversacion: true, tema: document.body.dataset.tema,
        conoce_voz: true, conoce_cara: false, solo_dueno: true, avisos_seguridad: true, celular: true, celular_activo: true,
        celular_direccion: "http://192.168.1.20:8765/",
        celular_qr: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21"><path d="M1 1h7v7H1zM13 1h7v7h-7zM1 13h7v7H1zM10 3h2v2h-2zM10 9h3v2h-3zM15 11h2v3h-2zM10 14h2v5h-2zM14 16h5v2h-5z"/></svg>' }),
      vigilancia: async () => !document.body.classList.contains("vigilando"), orden() {}, nuevo_codigo_celular: async () => window.pywebview.api.leer_ajustes(),
      guardar_ajustes: async () => ({}), nueva_conversacion() {},
      leer_panel: async () => ({ avisos: [{ id: "a", tipo: "recordatorio", mensaje: "sacar la ropa", cuando: "en 20 minutos" },
        { id: "b", tipo: "alarma", mensaje: "", cuando: "mañana a las 06:30" }], rutinas: ["estudio", "normal", "buenos dias"],
        datos: ["Su equipo favorito es el Nacional", "Estudia ingeniería de sistemas"], resumenes: 3 }),
      cancelar_aviso: async () => window.pywebview.api.leer_panel(), olvidar_dato: async () => window.pywebview.api.leer_panel(),
      ejecutar_rutina() {}, gestos: async () => true,
    } };
    jarvis.actualizar({ estado: "esperando", avisos: 2 });
  }, 1200);
})();
