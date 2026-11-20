"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const secret = location.pathname.split("/")[2];
const apiRoot = `/api/catalogo/${secret}/`;
const mediaRoot = `/catalogo-media/${secret}/`;
let state = { publicaciones: [], categorias: [], agenda: [], paginas: [] };
let selectedCategory = "";
let currentView = "catalogo";
let currentPlan = null;
let editorImages = [];
let toastTimer;
const busy = new Set();
const labels = {
  borrador: "Borrador",
  pendiente: "En cola local",
  enviando: "Enviando",
  meta: "En Meta",
  revisar: "Requiere revisión",
  simulado: "Simulado",
  cancelado: "Cancelado",
  vencido: "Horario vencido",
  publicado: "Publicado desde MCP",
};
const occupied = new Set([
  "borrador",
  "pendiente",
  "enviando",
  "meta",
  "revisar",
  "simulado",
  "publicado",
]);
const dateFormat = new Intl.DateTimeFormat("es-HN", {
  timeZone: "America/Tegucigalpa",
  dateStyle: "medium",
  timeStyle: "short",
});

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function button(text, fn, className = "text-button") {
  const el = element("button", className, text);
  el.type = "button";
  el.addEventListener("click", fn);
  return el;
}
function notify(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 7000);
}
async function request(action, data, form = false) {
  const options =
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: form ? {} : { "Content-Type": "application/json" },
          body: form ? data : JSON.stringify(data),
        };
  const response = await fetch(apiRoot + action, options);
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      "El servidor no respondió correctamente. Actualizá la página e intentá de nuevo.",
    );
  }
  if (!response.ok)
    throw new Error(result.error || "No se pudo completar la operación.");
  return result;
}
function catName(id) {
  const c = state.categorias.find((c) => c.id === id);
  return c ? (c.padre ? `${catName(c.padre)} / ` : "") + c.nombre : id;
}
function pageName(id) {
  return state.paginas.find((p) => p.id === id)?.nombre || id;
}
function categoryContains(id, target) {
  while (id) {
    if (id === target) return true;
    id = state.categorias.find((c) => c.id === id)?.padre;
  }
  return false;
}
function used(p) {
  return state.agenda.some(
    (a) =>
      a.publicacion_id === p.id &&
      Boolean(a.simulado) === Boolean(state.simulado) &&
      occupied.has(a.estado),
  );
}
function today() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Tegucigalpa",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
function isReady(p) {
  return Boolean(
    p.activa && p.automatica && (!p.vence || p.vence >= today()) && !used(p),
  );
}
function image(name, alt, lazy = true) {
  const im = element("img");
  im.src = mediaRoot + encodeURIComponent(name);
  im.alt = alt;
  if (lazy) im.loading = "lazy";
  return im;
}
function badge(status, text) {
  return element("span", `badge ${status}`, text);
}
async function load() {
  state = await request("estado");
  $("#mode-banner").hidden = !state.simulado;
  $("#timezone").textContent =
    state.zona === "America/Tegucigalpa"
      ? "Hora de Honduras · UTC−6"
      : state.zona;
  $("#nav-count").textContent = state.publicaciones.filter(
    (p) => p.activa,
  ).length;
  $("#queue-count").textContent = state.agenda.filter((a) =>
    ["pendiente", "enviando", "meta"].includes(a.estado),
  ).length;
  $("#stat-total").textContent = state.publicaciones.filter(
    (p) => p.activa,
  ).length;
  $("#stat-ready").textContent = state.publicaciones.filter(isReady).length;
  $("#stat-agenda").textContent = state.agenda.filter((a) =>
    ["pendiente", "enviando", "meta"].includes(a.estado),
  ).length;
  $("#stat-manual").textContent = state.publicaciones.filter(
    (p) => p.activa && !p.automatica,
  ).length;
  renderCategories();
  categoryOptions($("#filter-category"), false, "Todas las categorías");
  $("#filter-category").value = selectedCategory;
  fillSelect(
    $("#filter-page"),
    state.paginas.map((p) => ({ id: p.id, nombre: p.nombre })),
    "Todas las páginas",
  );
  renderCards();
  renderAgenda();
}
function fillSelect(select, items, emptyLabel) {
  const previous = select.value;
  select.replaceChildren();
  if (emptyLabel !== undefined) select.add(new Option(emptyLabel, ""));
  for (const item of items) select.add(new Option(item.nombre, item.id));
  if ([...select.options].some((o) => o.value === previous))
    select.value = previous;
}
function categoryOptions(select, batchOnly = false, emptyLabel) {
  fillSelect(
    select,
    state.categorias
      .filter((c) => !batchOnly || c.automatica)
      .map((c) => ({ id: c.id, nombre: catName(c.id) })),
    emptyLabel,
  );
}
function renderCategories() {
  const root = $("#categories");
  root.replaceChildren();
  function add(c) {
    const el = button(
      "",
      () => {
        selectedCategory = c.id;
        switchView("catalogo");
      },
      `nav-item category-item${c.padre ? " child" : ""}${selectedCategory === c.id ? " selected" : ""}`,
    );
    el.append(
      element("span", "category-mark"),
      document.createTextNode(c.nombre),
    );
    el.title = catName(c.id);
    root.append(el);
    state.categorias.filter((sub) => sub.padre === c.id).forEach(add);
  }
  state.categorias.filter((c) => !c.padre).forEach(add);
}
function switchView(view) {
  currentView = view;
  $("#filter-category").value = selectedCategory;
  $("#catalogue-section").hidden = view !== "catalogo";
  $("#agenda-section").hidden = view !== "agenda";
  $("#nav-catalogo").classList.toggle("selected", view === "catalogo");
  $("#nav-agenda").classList.toggle("selected", view === "agenda");
  $("#breadcrumb").textContent = view === "agenda" ? "Agenda" : "Catálogo";
  $("#page-title").textContent =
    view === "agenda" ? "Agenda de publicaciones" : "Catálogo de publicaciones";
  $("#page-description").textContent =
    view === "agenda"
      ? "Cada publicación, en su momento. Todo tu calendario en un solo lugar."
      : "Guardá tus ideas hoy. Dejá listas tus próximas publicaciones.";
  renderCategories();
  renderCards();
}
function renderCards() {
  const query = $("#search").value.trim().toLocaleLowerCase("es");
  const status = $("#filter-status").value;
  const pagina = $("#filter-page").value;
  const posts = state.publicaciones.filter(
    (p) =>
      (!selectedCategory || categoryContains(p.categoria, selectedCategory)) &&
      (!pagina || pagina === p.pagina) &&
      `${p.titulo} ${p.texto}`.toLocaleLowerCase("es").includes(query) &&
      (status === "archived" ? !p.activa : p.activa) &&
      (status !== "ready" || isReady(p)) &&
      (status !== "manual" || !p.automatica),
  );
  $("#category-heading").textContent = selectedCategory
    ? catName(selectedCategory)
    : "Todas las publicaciones";
  $("#result-count").textContent =
    `${posts.length} ${posts.length === 1 ? "publicación" : "publicaciones"}`;
  const cards = $("#cards");
  cards.replaceChildren();
  for (const p of posts) {
    const card = element("article", "card");
    const cover = element(
      "div",
      `card-image${p.imagenes.length ? "" : " no-image"}`,
    );
    if (p.imagenes.length) {
      cover.append(image(p.imagenes[0], p.titulo));
      if (p.imagenes.length > 1)
        cover.append(
          element("span", "image-count", `${p.imagenes.length} fotos`),
        );
    } else cover.append(element("span", "text-art", p.titulo));
    const body = element("div", "card-body");
    body.append(
      element("span", "card-category", catName(p.categoria)),
      element("h3", "", p.titulo),
      element("p", "card-text", p.texto || p.link || "Publicación de imágenes"),
    );
    const meta = element("div", "card-meta");
    let statusBadge = badge("manual", "Selección manual");
    if (!p.activa) statusBadge = badge("", "Archivada");
    else if (p.vence && p.vence < today())
      statusBadge = badge("vencido", "Vigencia terminada");
    else if (used(p)) statusBadge = badge("pendiente", "Usada en un plan");
    else if (isReady(p)) statusBadge = badge("ready", "Lista para lotes");
    meta.append(statusBadge, element("span", "", pageName(p.pagina)));
    body.append(meta);
    const actions = element("div", "card-actions");
    actions.append(button("Editar", () => openEditor(p)));
    if (p.activa) actions.append(button("Programar", () => openIndividual(p)));
    card.append(cover, body, actions);
    cards.append(card);
  }
  $("#empty").hidden = posts.length > 0;
  const first = !state.publicaciones.length;
  $("#empty-title").textContent = first
    ? "Tu próxima publicación empieza acá"
    : "No hay publicaciones con estos filtros";
  $("#empty-description").textContent = first
    ? "Guardá una imagen y su texto, elegí una categoría y armá tu biblioteca de contenido."
    : "Probá con otra categoría, cambiá la búsqueda o agregá una nueva publicación.";
}
function renderAgenda() {
  const tbody = $("#agenda-rows");
  tbody.replaceChildren();
  const shownPlans = new Set();
  for (const a of state.agenda) {
    const tr = element("tr");
    const dateCell = element(
      "td",
      "",
      dateFormat.format(new Date(a.fecha * 1000)),
    );
    const postCell = element("td", "", a.contenido.titulo);
    postCell.append(element("small", "", catName(a.contenido.categoria)));
    const statusCell = element("td");
    statusCell.append(badge(a.estado, labels[a.estado] || a.estado));
    if (a.post_id) statusCell.append(element("small", "", `ID: ${a.post_id}`));
    if (a.error) statusCell.append(element("small", "", a.error));
    if (a.simulado) statusCell.append(element("small", "", "Modo de prueba"));
    const actions = element("td");
    if (!shownPlans.has(a.plan_id)) {
      shownPlans.add(a.plan_id);
      if (a.estado === "borrador")
        actions.append(button("Revisar plan", () => openPreview(a.plan_id)));
      const local = state.agenda.filter((p) => p.plan_id === a.plan_id);
      if (
        local.some((p) => ["borrador", "pendiente"].includes(p.estado)) &&
        !local.some((p) => ["meta", "enviando", "revisar"].includes(p.estado))
      ) {
        actions.append(button("Cancelar plan", () => cancelPlan(a.plan_id)));
      }
    }
    tr.append(
      dateCell,
      postCell,
      element("td", "", pageName(a.pagina)),
      statusCell,
      actions,
    );
    tbody.append(tr);
  }
  $("#agenda-empty").hidden = state.agenda.length > 0;
}
function openDialog(id) {
  const dialog = $("#" + id);
  const error = $(".form-error", dialog);
  if (error) error.textContent = "";
  dialog.showModal();
}
function setAutomatic() {
  const form = $("#editor-form");
  const c = state.categorias.find(
    (c) => c.id === form.elements.categoria.value,
  );
  const disabled = !c?.automatica;
  form.elements.automatica.disabled = disabled;
  if (disabled) form.elements.automatica.checked = false;
  $("#automatic-help").textContent = disabled
    ? "Esta categoría requiere selección individual según temporada y tendencia."
    : "El contenido podrá seleccionarse cuando pidas programar esta categoría.";
}
function renderEditorImages() {
  const root = $("#existing-images");
  root.replaceChildren();
  for (const name of editorImages) {
    const wrap = element("div");
    wrap.append(
      image(name, "Foto guardada"),
      button("Quitar", () => {
        editorImages = editorImages.filter((n) => n !== name);
        renderEditorImages();
      }),
    );
    root.append(wrap);
  }
}
function openEditor(p) {
  const form = $("#editor-form");
  form.reset();
  categoryOptions(form.elements.categoria);
  fillSelect(form.elements.pagina, state.paginas);
  editorImages = p ? [...p.imagenes] : [];
  form.elements.id.value = p?.id || "";
  for (const key of [
    "titulo",
    "texto",
    "categoria",
    "pagina",
    "link",
    "vence",
  ]) {
    if (p) form.elements[key].value = p[key] || "";
  }
  if (!p && selectedCategory) form.elements.categoria.value = selectedCategory;
  form.elements.automatica.checked = Boolean(p?.automatica);
  form.elements.activa.checked = p ? Boolean(p.activa) : true;
  $("#editor-title").textContent = p
    ? "Editar publicación"
    : "Nueva publicación";
  setAutomatic();
  renderEditorImages();
  openDialog("editor");
}
function tomorrow() {
  const now = new Date();
  now.setUTCDate(now.getUTCDate() + 1);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Tegucigalpa",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}
function openBatch() {
  const form = $("#batch-form");
  categoryOptions(form.elements.categoria, true);
  fillSelect(form.elements.pagina, state.paginas);
  if (state.categorias.find((c) => c.id === selectedCategory)?.automatica)
    form.elements.categoria.value = selectedCategory;
  form.elements.inicio.value ||= tomorrow();
  openDialog("batch");
}
function openIndividual(p) {
  const form = $("#individual-form");
  form.elements.publicacion_id.value = p.id;
  form.elements.fecha.value = tomorrow() + "T09:00";
  $("#individual-name").textContent = `${p.titulo} · ${pageName(p.pagina)}`;
  openDialog("individual");
}
function openPreview(id) {
  currentPlan = id;
  const posts = state.agenda.filter((p) => p.plan_id === id);
  $("#preview-title").textContent =
    `${posts.length} ${posts.length === 1 ? "publicación para revisar" : "publicaciones para revisar"}`;
  const root = $("#preview-posts");
  root.replaceChildren();
  for (const p of posts) {
    const article = element(
      "article",
      `preview-post${p.contenido.imagenes.length ? "" : " text-only"}`,
    );
    if (p.contenido.imagenes.length)
      article.append(image(p.contenido.imagenes[0], p.contenido.titulo));
    const body = element("div");
    body.append(
      element(
        "span",
        "preview-date",
        dateFormat.format(new Date(p.fecha * 1000)),
      ),
      element("h3", "", p.contenido.titulo),
      element("p", "", p.contenido.texto),
      element(
        "small",
        "",
        `${pageName(p.pagina)} · ${catName(p.contenido.categoria)}`,
      ),
    );
    if (p.contenido.link) body.append(element("p", "", p.contenido.link));
    if (p.contenido.imagenes.length > 1) {
      const images = element("div", "preview-images");
      p.contenido.imagenes
        .slice(1)
        .forEach((n) => images.append(image(n, "Foto de la publicación")));
      body.append(images);
    }
    article.append(body);
    root.append(article);
  }
  $("#confirm-plan").textContent = state.simulado
    ? "Confirmar simulación"
    : "Confirmar programación";
  openDialog("preview");
}
async function cancelPlan(id) {
  try {
    await request("cancelar", { plan_id: id });
    if ($("#preview").open && currentPlan === id) $("#preview").close();
    await load();
    notify("Plan cancelado. El contenido está disponible de nuevo.");
  } catch (error) {
    notify(error.message, true);
  }
}
function handleForm(id, fn) {
  const form = $("#" + id);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy.has(id)) return;
    busy.add(id);
    const submit = $("button[type=submit]", form);
    submit.disabled = true;
    $(".form-error", form).textContent = "";
    try {
      await fn(form);
    } catch (error) {
      $(".form-error", form).textContent = error.message;
    } finally {
      busy.delete(id);
      submit.disabled = false;
    }
  });
}
handleForm("editor-form", async (form) => {
  const fields = form.elements;
  const data = {
    titulo: fields.titulo.value,
    texto: fields.texto.value,
    categoria: fields.categoria.value,
    pagina: fields.pagina.value,
    link: fields.link.value || null,
    vence: fields.vence.value || null,
    automatica: fields.automatica.checked,
    activa: fields.activa.checked,
    imagenes: editorImages,
  };
  if (fields.id.value) data.publicacion_id = fields.id.value;
  const files = [...fields.fotos.files];
  if (files.length + editorImages.length > 10)
    throw new Error("Podés guardar hasta 10 fotos en cada publicación.");
  if (files.some((f) => f.size > 25 * 1024 * 1024))
    throw new Error("Cada imagen admite hasta 25 MiB.");
  const payload = new FormData();
  payload.set("datos", JSON.stringify(data));
  files.forEach((f) => payload.append("fotos", f));
  await request("guardar", payload, true);
  $("#editor").close();
  await load();
  notify("Publicación guardada en tu catálogo.");
});
handleForm("batch-form", async (form) => {
  const data = Object.fromEntries(new FormData(form));
  data.cantidad = Number(data.cantidad);
  data.dias = Number(data.dias);
  data.horas = data.horas
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
  const result = await request("preparar", data);
  $("#batch").close();
  await load();
  openPreview(result.plan_id);
});
handleForm("individual-form", async (form) => {
  const result = await request(
    "individual",
    Object.fromEntries(new FormData(form)),
  );
  $("#individual").close();
  await load();
  openPreview(result.plan_id);
});
handleForm("category-form", async (form) => {
  const data = {
    nombre: form.elements.nombre.value,
    padre: form.elements.padre.value || null,
    automatica: form.elements.automatica.checked,
  };
  await request("categoria", data);
  $("#category-dialog").close();
  form.reset();
  await load();
  notify("Categoría creada.");
});
$("#confirm-plan").addEventListener("click", async () => {
  const el = $("#confirm-plan");
  el.disabled = true;
  try {
    await request("confirmar", { plan_id: currentPlan });
    $("#preview").close();
    await load();
    switchView("agenda");
    notify(
      state.simulado
        ? "Plan confirmado en modo de prueba. Los envíos serán simulados."
        : "Plan confirmado. La cola enviará tus publicaciones a Meta.",
    );
  } catch (error) {
    $("#preview-error").textContent = error.message;
  } finally {
    el.disabled = false;
  }
});
$("#discard-plan").addEventListener("click", () => cancelPlan(currentPlan));
$("#new-open").addEventListener("click", () => openEditor());
$("#empty-create").addEventListener("click", () => openEditor());
$("#batch-open").addEventListener("click", openBatch);
$("#editor-form").elements.categoria.addEventListener("change", setAutomatic);
$("#add-category").addEventListener("click", () => {
  categoryOptions(
    $("#category-form").elements.padre,
    false,
    "Sin categoría superior",
  );
  openDialog("category-dialog");
});
$("#nav-catalogo").addEventListener("click", () => {
  selectedCategory = "";
  switchView("catalogo");
});
$("#nav-agenda").addEventListener("click", () => switchView("agenda"));
$("#upload-link").href = `/subir/${secret}`;
$("#search").addEventListener("input", renderCards);
$("#filter-page").addEventListener("change", renderCards);
$("#filter-category").addEventListener("change", (event) => {
  selectedCategory = event.target.value;
  renderCategories();
  renderCards();
});
$("#filter-status").addEventListener("change", renderCards);
for (const id of ["refresh", "refresh-agenda"])
  $("#" + id).addEventListener("click", () =>
    load().catch((e) => notify(e.message, true)),
  );
for (const el of document.querySelectorAll("[data-close]"))
  el.addEventListener("click", () => $("#" + el.dataset.close).close());
load().catch((error) =>
  notify("No se pudo cargar el catálogo: " + error.message, true),
);
setInterval(() => {
  if (
    currentView === "agenda" &&
    !document.querySelector("dialog[open]") &&
    document.visibilityState === "visible"
  )
    load().catch(() => {});
}, 30000);
