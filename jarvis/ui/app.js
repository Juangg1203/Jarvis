// Interfaz de Jarvis: cambia la expresión del mono según lo que está haciendo.
(function () {
  const $ = (id) => document.getElementById(id);
  const avatar = $("avatar"), onda = $("onda"), ondaTexto = $("ondaTexto");
  const chat = $("chat"), lista = $("resultados"), punto = $("punto"), estadoTexto = $("estadoTexto");

  // Estado -> expresión por defecto, texto de la barra y del encabezado.
  const ESTADOS = {
    esperando:  { cara: "normal",      barra: "En espera",     cabecera: "Di «Jarvis»", clase: "" },
    escuchando: { cara: "sorprendido", barra: "Escuchando…",   cabecera: "Escuchando",  clase: "escucha" },
    pensando:   { cara: "pensando",    barra: "Pensando…",     cabecera: "Procesando",  clase: "escucha" },
    hablando:   { cara: "riendo",      barra: "Hablando…",     cabecera: "Respondiendo", clase: "activa" },
    dormido:    { cara: "dormido",     barra: "Durmiendo",     cabecera: "Dormido",     clase: "" },
    sin_voz:    { cara: "triste",      barra: "Voz no disponible", cabecera: "Solo texto", clase: "" },
  };

  // Barras de la onda de voz, como en el diseño.
  for (const lado of [$("ondaIzq"), $("ondaDer")]) {
    for (let i = 0; i < 14; i++) {
      const b = document.createElement("i");
      b.style.setProperty("--h", 6 + Math.round(Math.random() * 20) + "px");
      b.style.animationDelay = (Math.random() * 0.8).toFixed(2) + "s";
      lado.appendChild(b);
    }
  }

  let caraActual = "normal";
  function ponerCara(nombre) {
    if (nombre === caraActual) return;
    caraActual = nombre;
    avatar.classList.add("cambiando");
    setTimeout(() => {
      avatar.src = "assets/expresiones/" + nombre + ".png";
      avatar.classList.remove("cambiando");
    }, 150);
  }

  function mensaje(texto, quien, error) {
    const d = document.createElement("div");
    d.className = "msg " + quien + (error ? " error" : "");
    d.textContent = texto;
    chat.appendChild(d);
    while (chat.children.length > 40) chat.firstChild.remove();
    chat.scrollTop = chat.scrollHeight;
  }

  function mostrarResultados(res) {
    lista.innerHTML = "";
    res.forEach((r, i) => {
      const li = document.createElement("li");
      li.title = r.ruta;
      li.innerHTML = "<b></b><span></span><small></small>";
      li.children[0].textContent = i + 1;
      li.children[1].textContent = r.nombre;
      li.children[2].textContent = r.ruta;
      li.onclick = () => window.pywebview.api.abrir_resultado(i);
      lista.appendChild(li);
    });
  }

  let expresionRespuesta = null;
  window.jarvis = {
    actualizar(d) {
      const e = ESTADOS[d.estado] || ESTADOS.esperando;
      onda.className = "onda " + e.clase;
      ondaTexto.textContent = d.parcial ? "«" + d.parcial + "»" : e.barra;
      estadoTexto.textContent = e.cabecera;
      punto.className = "estado-punto " + (d.estado === "sin_voz" ? "error" : d.estado === "dormido" ? "" : "vivo");
      $("btnMic").classList.toggle("activo", d.estado === "escuchando");

      if (d.orden) mensaje(d.orden, "yo");
      if (d.respuesta) mensaje(d.respuesta, "jarvis", d.expresion === "triste" || d.expresion === "enojado");
      if (d.mensaje) mensaje(d.mensaje, "jarvis", true);
      if (d.resultados) mostrarResultados(d.resultados);

      if (d.estado === "hablando" && d.expresion) expresionRespuesta = d.expresion;
      let cara = e.cara;
      if (d.estado === "hablando") cara = expresionRespuesta || "riendo";
      ponerCara(cara);
    },
  };

  $("formulario").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const t = $("texto").value.trim();
    if (!t || !window.pywebview) return;
    $("texto").value = "";
    window.pywebview.api.enviar_texto(t);
  });
  $("btnMic").onclick = () => window.pywebview && window.pywebview.api.escuchar();
  $("btnOcultar").onclick = () => window.pywebview && window.pywebview.api.ocultar();

  // Si no hay voz aún, la ventana arranca en espera.
  window.addEventListener("pywebviewready", () => window.jarvis.actualizar({ estado: "esperando" }));
  // Modo demostración al abrir index.html en un navegador normal.
  setTimeout(() => {
    if (!window.pywebview) {
      window.pywebview = { api: { enviar_texto: (t) => {
        jarvis.actualizar({ estado: "pensando", orden: t });
        setTimeout(() => jarvis.actualizar({ estado: "hablando", expresion: "guino", respuesta: "(Demo) Recibí: " + t }), 600);
        setTimeout(() => jarvis.actualizar({ estado: "esperando" }), 2400);
      }, escuchar: () => jarvis.actualizar({ estado: "escuchando" }), ocultar() {}, abrir_resultado() {} } };
      jarvis.actualizar({ estado: "esperando" });
    }
  }, 1500);
})();
