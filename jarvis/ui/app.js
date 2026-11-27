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

    // partículas con profundidad: las cercanas son más grandes, rápidas y se mueven más con el ratón
    fctx.clearRect(0, 0, W, H);
    for (const p of particulas) {
      p.y -= p.v * p.z * (1 + n * 3);
      if (p.y < -4) { p.y = H + 4; p.x = Math.random() * W; }
      const px = p.x + actualY * p.z * 3, py = p.y - actualX * p.z * 3;
      fctx.globalAlpha = 0.15 + p.z * 0.55;
      fctx.fillStyle = p.z > 0.7 ? "#9fdcff" : "#1fa3ff";
      fctx.beginPath(); fctx.arc(px, py, p.z * 1.6, 0, 7); fctx.fill();
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
      const g = octx.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, "rgba(159,220,255,.95)"); g.addColorStop(1, "rgba(31,163,255,.55)");
      octx.fillStyle = g;
      octx.shadowColor = "#1fa3ff"; octx.shadowBlur = 8;
      octx.fillRect(x, y, ancho * 0.4, h);
    }
    requestAnimationFrame(dibujar);
  }
  requestAnimationFrame(dibujar);

  // ---------- expresiones con fundido cruzado ----------
  const caras = [$("caraA"), $("caraB")];
  let visible = 0, caraActual = "normal";
  // precarga para que el cambio sea instantáneo
  ["normal", "riendo", "guino", "sorprendido", "pensando", "preocupado", "enojado", "dormido", "triste"]
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
    panel.hidden = false;
  }
  $("btnAjustes").onclick = abrirAjustes;
  panel.addEventListener("click", (e) => { if (e.target === panel) panel.hidden = true; });
  $("btnGuardar").onclick = async () => {
    await api().guardar_ajustes({
      anthropic_api_key: $("clave").value.trim(),
      voz_motor: $("motor").value,
      modo_conversacion: $("conversacion").checked,
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

  window.addEventListener("pywebviewready", () => window.jarvis.actualizar({ estado: "esperando" }));

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
      leer_ajustes: async () => ({ tiene_clave: false, voz_motor: "piper", modo_conversacion: true }),
      guardar_ajustes: async () => ({}), nueva_conversacion() {},
      leer_panel: async () => ({ avisos: [{ id: "a", tipo: "recordatorio", mensaje: "sacar la ropa", cuando: "en 20 minutos" },
        { id: "b", tipo: "alarma", mensaje: "", cuando: "mañana a las 06:30" }], rutinas: ["estudio", "normal", "buenos dias"],
        datos: ["Su equipo favorito es el Nacional", "Estudia ingeniería de sistemas"], resumenes: 3 }),
      cancelar_aviso: async () => window.pywebview.api.leer_panel(), olvidar_dato: async () => window.pywebview.api.leer_panel(),
      ejecutar_rutina() {},
    } };
    jarvis.actualizar({ estado: "esperando", avisos: 2 });
  }, 1200);
})();
