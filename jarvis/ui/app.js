// Interfaz de Jarvis: escena 3D, expresiones con transición suave, onda de voz real y chat en vivo.
(function () {
  const $ = (id) => document.getElementById(id);
  const raiz = document.documentElement;
  const chat = $("chat"), lista = $("resultados"), punto = $("punto"), estadoTexto = $("estadoTexto"), pista = $("pista");
  const api = () => window.pywebview && window.pywebview.api;

  const ESTADOS = {
    esperando:  { cara: "normal",      pista: "Mantén presionado para hablar · o di «Jarvis»", cabecera: "En línea" },
    escuchando: { cara: "sorprendido", pista: "Te escucho…",                      cabecera: "Escuchando" },
    pensando:   { cara: "pensando",    pista: "Pensando…",                        cabecera: "Procesando" },
    hablando:   { cara: "riendo",      pista: "Presiona el micrófono para interrumpir", cabecera: "Hablando" },
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
    document.body.dataset.tema = tema || "holograma";
    try { localStorage.setItem("jarvisTema", document.body.dataset.tema); } catch (e) {}
    leerColores();
  }
  try { ponerTema(localStorage.getItem("jarvisTema")); } catch (e) { ponerTema("holograma"); }
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

  // ---------- inclinación con el ratón ----------
  let objetivoX = 0, objetivoY = 0, actualX = 0, actualY = 0;
  addEventListener("mousemove", (e) => {
    objetivoY = (e.clientX / W - 0.5) * 18;
    objetivoX = -(e.clientY / H - 0.5) * 12;
  });
  addEventListener("mouseleave", () => { objetivoX = objetivoY = 0; });

  // =====================================================================
  // El orbe holográfico: esfera de cristal, anillos en órbita, base de luz,
  // onda de sonido dentro, caras según el ánimo y partículas al hablar.
  // =====================================================================
  const orbe = $("orbe"), ctx = orbe.getContext("2d");
  let OW = 0, OH = 0;
  function tamOrbe() {
    const dpr = window.devicePixelRatio || 1, r = orbe.getBoundingClientRect();
    OW = r.width; OH = r.height;
    orbe.width = Math.max(1, OW * dpr); orbe.height = Math.max(1, OH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  if (window.ResizeObserver) new ResizeObserver(tamOrbe).observe(orbe);
  addEventListener("resize", tamOrbe);
  tamOrbe();

  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const claro = (c, k) => c.map((x) => Math.round(x + (255 - x) * k));
  // puntitos de luz fijos dentro de la esfera (en coordenadas de -1 a 1)
  const brillos = Array.from({ length: 46 }, () => {
    const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * 0.9;
    return { x: Math.cos(a) * r, y: Math.sin(a) * r, s: Math.random() * 1.3 + 0.4, f: Math.random() * 6.3 };
  });
  const ANILLOS = [
    { incl: -0.30, rx: 1.30, ry: 0.34, vel: 0.55, largo: 4.0, ancho: 5.0, dy: 0.16 },
    { incl: 0.20, rx: 1.18, ry: 0.26, vel: -0.8, largo: 2.8, ancho: 3.4, dy: 0.10 },
    { incl: -0.10, rx: 1.46, ry: 0.46, vel: 0.32, largo: 2.0, ancho: 2.2, dy: 0.05 },
  ];
  let chispas = [], ondas = [], ultimaOnda = 0;
  let cara = "normal", caraAntes = "normal", mezclaCara = 1, modoOnda = 0, proximoParpadeo = 2, parpadeando = 0;

  function ponerCara(nombre) {
    if (!nombre || nombre === cara) return;
    caraAntes = cara; cara = nombre; mezclaCara = 0;
  }

  // dibuja una parte del anillo: atras=true solo la mitad de atrás (va detrás de la esfera)
  function anillo(cx, cy, R, a, atras, col, velocidad) {
    const pasos = 70, ini = t * a.vel * velocidad;
    cy += (a.dy || 0) * R;
    for (let i = 0; i < pasos; i++) {
      const f = i / pasos, ang = ini + f * a.largo;
      const delante = Math.sin(ang) > 0;
      if (delante === atras) continue;
      const p = (q) => {
        const x = Math.cos(q) * a.rx * R, y = Math.sin(q) * a.ry * R;
        return [cx + x * Math.cos(a.incl) - y * Math.sin(a.incl), cy + x * Math.sin(a.incl) + y * Math.cos(a.incl)];
      };
      const [x1, y1] = p(ang), [x2, y2] = p(ang + a.largo / pasos + 0.01);
      ctx.strokeStyle = rgba(claro(col, 0.15 + f * 0.6), (atras ? 0.4 : 1) * Math.pow(f, 1.2));
      ctx.lineWidth = a.ancho * (0.4 + f);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
  }

  // ---------- caras ----------
  function ojos(nombre, cx, cy, R, alfa, col, soloMarcas) {
    if (alfa <= 0.01) return;
    const s = R * 0.13, dx = R * 0.3, y = cy - R * 0.1, c = rgba(claro(col, 0.55), alfa);
    ctx.save();
    ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = R * 0.05;
    ctx.shadowColor = rgba(col, alfa); ctx.shadowBlur = R * 0.12;
    const oval = (x, k = 1, abre = 1) => { if (!ojo) return; ctx.beginPath(); ctx.ellipse(x, y, s * 0.42 * k, Math.max(s * 0.06, s * 0.72 * k * abre), 0, 0, 6.283); ctx.fill(); };
    const feliz = (x) => { if (!ojo) return; ctx.beginPath(); ctx.arc(x, y + s * 0.35, s * 0.62, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); };
    const risa = (x, d) => { if (!ojo) return; ctx.beginPath(); ctx.moveTo(x - s * 0.45 * d, y - s * 0.5); ctx.lineTo(x + s * 0.4 * d, y); ctx.lineTo(x - s * 0.45 * d, y + s * 0.5); ctx.stroke(); };
    const linea = (x) => { if (!ojo) return; ctx.beginPath(); ctx.moveTo(x - s * 0.55, y); ctx.lineTo(x + s * 0.55, y); ctx.stroke(); };
    const ceja = (x, inclina, alto = 1) => {
      if (!ojo) return;
      ctx.save(); ctx.lineWidth = R * 0.035; ctx.translate(x, y - s * 1.15 * alto); ctx.rotate(inclina);
      ctx.beginPath(); ctx.moveTo(-s * 0.5, 0); ctx.lineTo(s * 0.5, 0); ctx.stroke(); ctx.restore();
    };
    const marca = (texto, x, yy, tam) => {
      if (!soloMarcas) return;
      ctx.save(); ctx.font = `700 ${tam}px "Segoe UI", sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(texto, x, yy); ctx.restore();
    };
    const abre = parpadeando > 0 ? 0.08 : 1;
    // Se llama dos veces: dentro de la esfera (ojos) y fuera (signos ?, !, zzz, rayitas, remolino).
    const ojo = !soloMarcas;
    switch (nombre) {
      case "guino": case "feliz":
        feliz(cx - dx); feliz(cx + dx);
        marca("✧", cx + R * 0.95, cy - R * 0.95, R * 0.22); break;
      case "riendo":
        risa(cx - dx, 1); risa(cx + dx, -1);
        if (soloMarcas) ctx.lineWidth = R * 0.035;
        if (soloMarcas) [[0.82, -0.98, 0.98, -1.12], [0.95, -0.82, 1.15, -0.86], [0.68, -1.06, 0.7, -1.24]].forEach(([a, b, c2, d]) => {
          ctx.beginPath(); ctx.moveTo(cx + R * a, cy + R * b); ctx.lineTo(cx + R * c2, cy + R * d); ctx.stroke(); });
        break;
      case "sorprendido":
        oval(cx - dx, 1.25); oval(cx + dx, 1.25);
        marca("!", cx + R * 0.95, cy - R * 0.95, R * 0.34); break;
      case "pensando":
        oval(cx - dx, 0.8, abre); oval(cx + dx, 1.05, abre); ceja(cx - dx, -0.35, 1.05);
        marca("?", cx + R * 0.95 + Math.sin(t * 2) * 2, cy - R * 1.0, R * 0.34); break;
      case "preocupado": case "triste":
        oval(cx - dx, 0.9, abre); oval(cx + dx, 0.9, abre); ceja(cx - dx, -0.4); ceja(cx + dx, 0.4);
        if (nombre === "preocupado" && soloMarcas) {
          ctx.lineWidth = R * 0.03; ctx.beginPath();
          for (let k = 0; k < 40; k++) { const q = k / 40 * 12.5, rr = R * 0.012 * k * 0.18 + R * 0.02;
            const px = cx + R * 0.95 + Math.cos(q + t * 3) * rr * 3, py = cy - R * 1.0 + Math.sin(q + t * 3) * rr * 1.2 + k * R * 0.004;
            k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
          ctx.stroke();
        }
        break;
      case "enojado":
        oval(cx - dx, 0.9, abre); oval(cx + dx, 0.9, abre); ceja(cx - dx, 0.45); ceja(cx + dx, -0.45); break;
      case "dormido":
        linea(cx - dx); linea(cx + dx);
        for (let k = 0; k < 3; k++) {
          const f = (t * 0.35 + k / 3) % 1;
          ctx.globalAlpha = alfa * Math.sin(f * Math.PI);
          marca("z", cx + R * (0.7 + f * 0.5), cy - R * (0.7 + f * 0.6), R * (0.14 + f * 0.14));
        }
        break;
      default:
        oval(cx - dx, 1, abre); oval(cx + dx, 1, abre);
    }
    ctx.restore();
  }

  // onda de sonido dentro de la esfera (grande al escuchar, de "boca" al hablar o en reposo)
  function onditas(cx, cy, ancho, alto, barras, col, alfa, n, rapidez) {
    if (alfa <= 0.01) return;
    ctx.save();
    ctx.lineCap = "round"; ctx.shadowColor = rgba(col, alfa); ctx.shadowBlur = alto * 0.25;
    const paso = ancho / barras;
    for (let i = 0; i < barras; i++) {
      const d = Math.abs(i - (barras - 1) / 2) / ((barras - 1) / 2);
      const ruido = 0.55 + 0.45 * Math.abs(Math.sin(t * rapidez + i * 1.31) * Math.cos(t * rapidez * 0.63 + i * 0.7));
      const h = Math.max(alto * 0.08, alto * (1 - d * d * 0.85) * ruido * (0.25 + n));
      const x = cx - ancho / 2 + paso * (i + 0.5);
      const g = ctx.createLinearGradient(0, cy - h / 2, 0, cy + h / 2);
      g.addColorStop(0, rgba(claro(col, 0.7), alfa)); g.addColorStop(0.5, rgba(claro(col, 0.3), alfa)); g.addColorStop(1, rgba(claro(col, 0.7), alfa));
      ctx.strokeStyle = g; ctx.lineWidth = Math.max(1.5, paso * 0.42);
      ctx.beginPath(); ctx.moveTo(x, cy - h / 2); ctx.lineTo(x, cy + h / 2); ctx.stroke();
    }
    ctx.restore();
  }

  function dibujarOrbe(n) {
    if (!OW || !OH) return;
    ctx.clearRect(0, 0, OW, OH);
    const col = hexRgb(colores[0]), col2 = hexRgb(colores[1]), col3 = hexRgb(colores[2]);
    const util = OH - 130;                                  // deja sitio abajo para el botón de hablar
    const R = Math.max(40, Math.min(OW * 0.2, util / 3.25));
    // si el panel del equipo está a la izquierda, el orbe se corre un poco para no quedar debajo
    const panel = $("sistema"), libre = panel && panel.offsetWidth ? panel.offsetLeft + panel.offsetWidth + R * 1.35 : 0;
    const cx = Math.min(Math.max(OW * 0.5, libre), OW - R * 1.5) + actualY * 1.6, baseY = util * 0.43 + R * 1.62;
    const cy = util * 0.43 + Math.sin(t * 1.1) * R * 0.035 - actualX * 1.2 - n * R * 0.04;
    const velAnillos = estado === "pensando" ? 3 : estado === "dormido" ? 0.25 : 1 + n * 1.5;
    const enEscucha = estado === "escuchando";
    modoOnda += ((enEscucha ? 1 : 0) - modoOnda) * 0.1;
    mezclaCara = Math.min(1, mezclaCara + 0.08);
    if (t > proximoParpadeo) { parpadeando = 0.13; proximoParpadeo = t + 2.5 + Math.random() * 3.5; }
    parpadeando = Math.max(0, parpadeando - 1 / 60);

    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    // halo
    const halo = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 2.3);
    const tinte = enEscucha ? [52, 211, 153] : estado === "pensando" ? [167, 139, 250] : col;
    halo.addColorStop(0, rgba(tinte, 0.22 + n * 0.25)); halo.addColorStop(1, rgba(tinte, 0));
    ctx.fillStyle = halo; ctx.fillRect(0, 0, OW, OH);

    // base holográfica: anillos de luz en el suelo
    for (let k = 4; k >= 0; k--) {
      const rx = R * (0.32 + k * 0.26) * (1 + Math.sin(t * 1.6 + k) * 0.015 + n * 0.05), ry = rx * 0.17;
      ctx.lineWidth = k === 1 ? 3 : 1.6;
      ctx.strokeStyle = rgba(claro(col, k < 2 ? 0.4 : 0), 0.75 - k * 0.12);
      ctx.shadowColor = rgba(col, 1); ctx.shadowBlur = 14;
      if (k === 3) { ctx.setLineDash([R * 0.25, R * 0.12]); ctx.lineDashOffset = -t * 30; }
      ctx.beginPath(); ctx.ellipse(cx, baseY, rx, ry, 0, 0, 6.283); ctx.stroke();
      ctx.setLineDash([]);
    }
    const centro = ctx.createRadialGradient(cx, baseY, 0, cx, baseY, R * 0.45);
    centro.addColorStop(0, rgba(claro(col, 0.6), 0.9)); centro.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = centro; ctx.beginPath(); ctx.ellipse(cx, baseY, R * 0.45, R * 0.09, 0, 0, 6.283); ctx.fill();
    // haz de luz hacia la esfera
    const haz = ctx.createLinearGradient(0, baseY, 0, cy + R * 0.6);
    haz.addColorStop(0, rgba(col, 0.38 + n * 0.2)); haz.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = haz; ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.moveTo(cx - R * 0.42, baseY); ctx.lineTo(cx + R * 0.42, baseY);
    ctx.lineTo(cx + R * 0.85, cy + R * 0.55); ctx.lineTo(cx - R * 0.85, cy + R * 0.55); ctx.closePath(); ctx.fill();

    // anillos (mitad de atrás)
    ctx.shadowColor = rgba(col, 1); ctx.shadowBlur = 10; ctx.lineCap = "round";
    ANILLOS.forEach((a) => anillo(cx, cy, R, a, true, col, velAnillos));
    ctx.restore();

    // esfera de cristal
    ctx.save();
    const cuerpo = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.3, R * 0.1, cx, cy, R);
    cuerpo.addColorStop(0, "rgba(10,20,60,.55)"); cuerpo.addColorStop(0.75, "rgba(6,14,44,.72)"); cuerpo.addColorStop(1, rgba(col, 0.38));
    ctx.fillStyle = cuerpo; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.283); ctx.fill();
    ctx.globalCompositeOperation = "lighter";
    ctx.strokeStyle = rgba(claro(col, 0.35), 0.95); ctx.lineWidth = R * 0.028;
    ctx.shadowColor = rgba(col, 1); ctx.shadowBlur = R * 0.22 * (1 + n);
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.283); ctx.stroke();
    ctx.shadowBlur = R * 0.08;
    ctx.strokeStyle = "rgba(255,255,255,.4)"; ctx.lineWidth = R * 0.05;
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.84, Math.PI * 1.12, Math.PI * 1.36); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,.18)"; ctx.lineWidth = R * 0.018;
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.88, Math.PI * 0.12, Math.PI * 0.38); ctx.stroke();
    ctx.shadowBlur = 0;
    for (const b of brillos) {
      ctx.fillStyle = rgba(claro(col3, 0.5), 0.25 + 0.35 * Math.sin(t * 2 + b.f) ** 2);
      ctx.beginPath(); ctx.arc(cx + b.x * R, cy + b.y * R, b.s, 0, 6.283); ctx.fill();
    }
    // contenido: onda grande al escuchar; cara + boca de onda el resto del tiempo
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.93, 0, 6.283); ctx.clip();
    const escucha = Math.max(0.35, 0.45 + Math.sin(t * 4) * 0.15);
    onditas(cx, cy, R * 1.25, R * 0.95, 25, col3, modoOnda, enEscucha ? escucha : n, 7);
    const alfaCara = 1 - modoOnda;
    ojos(caraAntes, cx, cy, R, alfaCara * (1 - mezclaCara), col3);
    ojos(cara, cx, cy, R, alfaCara * mezclaCara, col3);
    const habla = estado === "hablando";
    onditas(cx, cy + R * 0.36, R * (habla ? 0.62 : 0.42), R * (habla ? 0.12 + n * 0.32 : 0.1), 11, col3, alfaCara,
      habla ? 0.3 + n : estado === "dormido" ? 0.05 : 0.2, habla ? 12 : 2.5);
    ctx.restore();
    ojos(caraAntes, cx, cy, R, alfaCara * (1 - mezclaCara), col3, true);
    ojos(cara, cx, cy, R, alfaCara * mezclaCara, col3, true);

    // anillos (mitad de delante), ondas de sonido y partículas
    ctx.save();
    ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
    ctx.shadowColor = rgba(col, 1); ctx.shadowBlur = 12;
    ANILLOS.forEach((a) => anillo(cx, cy, R, a, false, col, velAnillos));
    if (estado === "hablando" && n > 0.35 && t - ultimaOnda > 0.28) { ondas.push({ r: R * 1.02, a: 0.55 * n + 0.15 }); ultimaOnda = t; }
    ondas = ondas.filter((o) => o.a > 0.01);
    for (const o of ondas) {
      o.r += R * 0.018; o.a *= 0.955;
      ctx.strokeStyle = rgba(claro(col, 0.3), o.a); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(cx, cy, o.r, 0, 6.283); ctx.stroke();
    }
    const nuevas = estado === "hablando" ? n * 7 + 0.6 : estado === "escuchando" ? 0.5 : 0.08;
    for (let k = 0; k < nuevas || Math.random() < nuevas - k; k++) {
      if (k > 12) break;
      const ang = Math.random() * 6.283, v = (estado === "hablando" ? 1.2 + n * 3.5 : 0.5) * (0.6 + Math.random());
      const c = [col, col2, col3, [255, 255, 255]][Math.floor(Math.random() * 4)];
      chispas.push({ x: cx + Math.cos(ang) * R, y: cy + Math.sin(ang) * R, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v - 0.15,
        vida: 1, s: Math.random() * 2.2 + 0.8, c });
    }
    chispas = chispas.filter((p) => p.vida > 0).slice(-420);
    ctx.shadowBlur = 6;
    for (const p of chispas) {
      p.x += p.vx; p.y += p.vy; p.vx *= 0.985; p.vy *= 0.985; p.vida -= 0.012;
      ctx.fillStyle = rgba(p.c, p.vida * 0.9); ctx.shadowColor = rgba(p.c, 1);
      ctx.beginPath(); ctx.arc(p.x, p.y, p.s * (0.5 + p.vida * 0.5), 0, 6.283); ctx.fill();
    }
    ctx.restore();
  }

  // ---------- onda de voz y fondo ----------
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

    // estrellas de fondo con profundidad
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
    dibujarOrbe(n);

    // barras de la onda a los lados del botón
    const dpr = window.devicePixelRatio || 1;
    const ow = onda.clientWidth, oh = onda.clientHeight;
    if (onda.width !== Math.round(ow * dpr)) { onda.width = ow * dpr; onda.height = oh * dpr; }
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.clearRect(0, 0, ow, oh);
    const barras = 64, ancho = ow / barras, mitad = barras / 2;
    for (let i = 0; i < barras; i++) {
      const d = Math.abs(i - mitad + 0.5) / mitad;
      const ruido = Math.sin(t * 9 + i * 0.9) * 0.5 + Math.sin(t * 5.3 + i * 1.7) * 0.5;
      const h = 2 + (oh - 6) * n * (1 - d * 0.75) * (0.55 + 0.45 * Math.abs(ruido));
      const x = i * ancho + ancho * 0.3, y = (oh - h) / 2;
      const [r, gg, b] = mezcla(i / (barras - 1));
      octx.fillStyle = `rgba(${r},${gg},${b},.85)`;
      octx.shadowColor = `rgb(${r},${gg},${b})`; octx.shadowBlur = 8;
      octx.fillRect(x, y, ancho * 0.4, h);
    }
    requestAnimationFrame(dibujar);
  }
  requestAnimationFrame(dibujar);

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
  // ---------- mantener presionado para hablar ----------
  // Presionas: Jarvis escucha (y se calla si estaba hablando). Sueltas: termina la orden al instante.
  // Un toque corto sigue funcionando como antes: escucha hasta que te quedas callado.
  const mic = $("btnMic");
  let pttActivo = false, pttDesde = 0;
  function pttEmpezar() {
    if (!api() || pttActivo) return;
    pttActivo = true; pttDesde = performance.now();
    mic.classList.add("presionado");
    pista.textContent = "Te escucho… suelta para terminar";
    if (api().hablar_presionado) api().hablar_presionado();
    else { if (estado === "hablando") api().callar(); api().escuchar(); }
  }
  function pttSoltar() {
    if (!pttActivo) return;
    pttActivo = false;
    mic.classList.remove("presionado");
    const corto = performance.now() - pttDesde < 350;
    if (api() && api().hablar_soltado) api().hablar_soltado(corto);
  }
  mic.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try { mic.setPointerCapture(e.pointerId); } catch (err) {}
    pttEmpezar();
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((ev) => mic.addEventListener(ev, pttSoltar));
  mic.addEventListener("keydown", (e) => { if (e.key === "Enter" && api()) { if (estado === "hablando") api().callar(); api().escuchar(); } });
  const escribiendo = () => ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement && document.activeElement.tagName);
  addEventListener("keydown", (e) => {
    if (e.code === "Space" && !e.repeat && !escribiendo() && $("panelAjustes").hidden && $("panelAgenda").hidden) { e.preventDefault(); pttEmpezar(); }
  });
  addEventListener("keyup", (e) => { if (e.code === "Space" && pttActivo) { e.preventDefault(); pttSoltar(); } });
  addEventListener("blur", pttSoltar);

  // ---------- panel del equipo ----------
  const DIAS = { weekday: "long", day: "numeric", month: "long" };
  function reloj() {
    const d = new Date();
    $("sisHora").textContent = d.toLocaleTimeString("es", { hour: "numeric", minute: "2-digit" });
    const f = d.toLocaleDateString("es", DIAS);
    $("sisFecha").textContent = f.charAt(0).toUpperCase() + f.slice(1);
  }
  reloj(); setInterval(reloj, 1000);
  function barra(id, texto, pct, alto, extraClase) {
    const f = $(id); if (!f) return;
    f.querySelector("em").textContent = texto;
    f.querySelector("u").style.width = Math.max(0, Math.min(100, pct || 0)) + "%";
    f.classList.toggle("alto", !!alto);
    if (extraClase !== undefined) f.classList.toggle("cargando", !!extraClase);
  }
  function pintarSistema(s) {
    if (!s) return;
    if (s.equipo) $("sisEquipo").textContent = s.equipo;
    const b = s.bateria;
    if (b) barra("sisBateria", b.porcentaje + "%" + (b.cargando ? "" : b.minutos ? " · " + b.minutos : ""), b.porcentaje, !b.cargando && b.porcentaje <= 20, b.cargando);
    else barra("sisBateria", "Enchufado", 100, false, false);
    barra("sisCpu", Math.round(s.cpu) + "%", s.cpu, s.cpu >= 85);
    barra("sisRam", s.ram.usada + " / " + s.ram.total + " GB", s.ram.porcentaje, s.ram.porcentaje >= 88);
    barra("sisDisco", s.disco.libre + " GB libres", s.disco.porcentaje, s.disco.porcentaje >= 90);
    const datos = $("sisDatos"); datos.innerHTML = "";
    (s.datos || []).forEach(([k, v]) => {
      const li = document.createElement("li");
      li.innerHTML = "<span></span><b></b>"; li.children[0].textContent = k; li.children[1].textContent = v; li.children[1].title = v;
      datos.appendChild(li);
    });
    if (s.cerebro) $("cerebro").textContent = "Cerebro: " + s.cerebro;
  }
  async function leerSistema() {
    try { if (api() && api().sistema) pintarSistema(await api().sistema()); } catch (e) {}
  }
  setInterval(leerSistema, 3000);
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
    $("proveedor").value = a.proveedor || "gemini";
    $("ollamaModelo").value = a.ollama_modelo || "qwen2.5:3b";
    $("claveGemini").value = "";
    $("geminiEstado").textContent = a.tiene_gemini
      ? "Clave guardada (termina en " + a.gemini_final + "). Escribe otra solo si quieres cambiarla."
      : "Sin clave: Jarvis solo hace las órdenes del computador.";
    mostrarProveedor();
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
  async function mostrarProveedor() {
    const p = $("proveedor").value;
    $("campoClaude").hidden = p !== "claude"; $("campoGemini").hidden = p !== "gemini" && p !== "auto";
    $("campoOllama").hidden = p !== "ollama" && p !== "auto";
    if ((p !== "ollama" && p !== "auto") || !api() || !api().estado_ollama) return;
    $("ollamaEstado").textContent = "Revisando Ollama…";
    const o = await api().estado_ollama();
    const rapido = $("ollamaModelo").value === (o.modelo_rapido || "qwen2.5:1.5b");
    const listo = o.modelo_rapido ? (rapido ? o.rapido : o.normal) : o.modelo;
    $("btnOllama").hidden = listo || (o.instalado && o.abierto);
    $("btnOllamaRapido").hidden = !(o.abierto && rapido && !o.rapido);
    $("ollamaEstado").textContent = listo
      ? "✅ Ollama está listo" + (rapido ? " con el cerebro rápido." : " con el cerebro más listo.") + " Todo se queda en tu portátil."
      : o.abierto && rapido ? "Falta el cerebro rápido: toca el botón para descargarlo (1 GB)."
      : o.instalado && !o.abierto ? "Ollama está instalado pero cerrado. Ábrelo desde el menú Inicio, o toca el botón para terminar la instalación."
      : o.abierto ? "Falta el cerebro más listo: toca el botón para descargarlo."
      : "Ollama no está instalado. Toca el botón: se abre una ventana que lo instala y descarga el cerebro (unos minutos).";
  }
  $("ollamaModelo").onchange = mostrarProveedor;
  $("btnOllamaRapido").onclick = async () => {
    if (await api().instalar_ollama(true)) $("ollamaEstado").textContent = "Descargando el cerebro rápido en otra ventana. Cuando termine, vuelve a abrir Ajustes.";
  };
  $("btnOllama").onclick = async () => {
    if (await api().instalar_ollama()) $("ollamaEstado").textContent = "Se abrió la ventana del instalador. Cuando termine, vuelve a abrir Ajustes.";
  };
  $("proveedor").onchange = mostrarProveedor;
  $("btnAjustes").onclick = abrirAjustes;
  panel.addEventListener("click", (e) => { if (e.target === panel) panel.hidden = true; });
  $("btnGuardar").onclick = async () => {
    await api().guardar_ajustes({
      anthropic_api_key: $("clave").value.trim(),
      gemini_api_key: $("claveGemini").value.trim(),
      proveedor: $("proveedor").value,
      ollama_modelo: $("ollamaModelo").value,
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
    leerSistema();
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
      leer_ajustes: async () => ({ tiene_clave: false, proveedor: "gemini", tiene_gemini: true, gemini_final: "x9Qk", voz_motor: "piper", modo_conversacion: true, tema: document.body.dataset.tema, nombre: "Juan",
        conoce_voz: true, conoce_cara: false, solo_dueno: true, avisos_seguridad: true, celular: true, celular_activo: true,
        celular_direccion: "http://192.168.1.20:8765/",
        celular_qr: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21"><path d="M1 1h7v7H1zM13 1h7v7h-7zM1 13h7v7H1zM10 3h2v2h-2zM10 9h3v2h-3zM15 11h2v3h-2zM10 14h2v5h-2zM14 16h5v2h-5z"/></svg>' }),
      vigilancia: async () => !document.body.classList.contains("vigilando"), orden() {}, nuevo_codigo_celular: async () => window.pywebview.api.leer_ajustes(),
      estado_ollama: async () => ({ instalado: false, abierto: false, modelo: false, vision: false, nombre: "qwen2.5:3b" }), instalar_ollama: async () => true,
      guardar_ajustes: async () => ({}), nueva_conversacion() {},
      leer_panel: async () => ({ avisos: [{ id: "a", tipo: "recordatorio", mensaje: "sacar la ropa", cuando: "en 20 minutos" },
        { id: "b", tipo: "alarma", mensaje: "", cuando: "mañana a las 06:30" }], rutinas: ["estudio", "normal", "buenos dias"],
        datos: ["Su equipo favorito es el Nacional", "Estudia ingeniería de sistemas"], resumenes: 3 }),
      cancelar_aviso: async () => window.pywebview.api.leer_panel(), olvidar_dato: async () => window.pywebview.api.leer_panel(),
      ejecutar_rutina() {}, gestos: async () => true,
      hablar_presionado: () => jarvis.actualizar({ estado: "escuchando" }),
      hablar_soltado: (corto) => { if (!corto) window.pywebview.api.enviar_texto("abre la carpeta de documentos"); },
      sistema: async () => ({ equipo: "LAPTOP-JUAN", cpu: 18 + Math.random() * 20, cerebro: "Gemini (con internet)",
        bateria: { porcentaje: 76, cargando: false, minutos: "3 h 10 min" }, ram: { usada: 5.2, total: 8, porcentaje: 65 },
        disco: { libre: 112, total: 237, porcentaje: 53 },
        datos: [["Procesador", "Intel Core i5-1135G7"], ["Sistema", "Windows 11"], ["Encendido", "2 h 14 min"], ["Internet", "Conectado"]] }),
    } };
    leerSistema();
    jarvis.actualizar({ estado: "esperando", avisos: 2 });
  }, 1200);
})();
