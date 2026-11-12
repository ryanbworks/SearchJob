/* Página do currículo adaptado por vaga. Depende de common.js (window.SJ). */
(function () {
  "use strict";

  const { el, api, jobIdFromUrl, fillJobPicker } = window.SJ;
  const $ = (id) => document.getElementById(id);
  const state = { jobId: null };

  function show(id, visible) {
    $(id).classList.toggle("hidden", !visible);
  }

  function notice(message) {
    $("notice").replaceChildren(
      el("strong", {}, "Não foi possível continuar. "), message, " ",
      el("a", { href: "/painel" }, "Voltar ao painel"),
    );
    show("notice", true);
  }

  function chips(container, items, empty) {
    container.replaceChildren(...(items.length
      ? items.map((t) => el("span", { class: "chip" }, t))
      : [el("span", { class: "empty" }, empty)]));
  }

  function listItems(container, sectionId, items) {
    container.replaceChildren(...items.map((t) => el("li", {}, t)));
    $(sectionId).classList.toggle("hidden", !items.length);
  }

  function render(data) {
    const c = data.contact || {};
    $("r-name").textContent = c.nome || c.name || "Seu nome (edite aqui ou no profile.md)";
    $("r-headline").textContent = data.headline || "";
    $("r-contact").textContent = [c.email, c.telefone || c.phone, c.cidade || c.city,
      c.linkedin, c.github, c.portfolio].filter(Boolean).join("  ·  ");
    $("r-summary").textContent = data.summary;
    $("r-skills").textContent = data.skills.join("  ·  ");

    $("r-highlights").replaceChildren(...data.highlights.map((h) => el(
      "div", { class: "hl", contenteditable: "true" },
      el("strong", {}, h.title),
      h.description ? el("div", {}, h.description) : null,
    )));
    $("r-highlights-section").classList.toggle("hidden", !data.highlights.length);
    listItems($("r-education"), "r-education-section", data.education || []);
    listItems($("r-languages"), "r-languages-section", data.languages || []);

    chips($("kw-used"), data.keywords_used, "Nenhuma informada.");
    chips($("kw-missing"), data.missing_keywords, "Nenhuma: ótimo sinal!");
    chips($("removed"), data.removed_skills || [], "");
    show("removed-card", (data.removed_skills || []).length > 0);

    const job = data.job || {};
    $("job-meta").textContent = `${job.title || ""} · ${job.company || "Empresa não informada"}`;
    document.title = `Currículo: ${job.title || "vaga"}`;
    show("resume", true);
    show("regen-btn", true);
    show("print-btn", true);
  }

  async function load(regenerate) {
    show("loading", true);
    show("notice", false);
    $("regen-btn").disabled = true;
    try {
      const data = await api(
        `/api/jobs/${state.jobId}/resume${regenerate ? "?regenerate=true" : ""}`,
        { method: "POST" },
      );
      render(data);
    } catch (e) {
      notice(e.message);
    } finally {
      show("loading", false);
      $("regen-btn").disabled = false;
    }
  }

  function open(jobId) {
    state.jobId = jobId;
    $("interview-link").href = `/entrevista?job=${jobId}`;
    show("interview-link", true);
    show("picker", false);
    load(false);
  }

  async function init() {
    $("regen-btn").addEventListener("click", () => load(true));
    $("print-btn").addEventListener("click", () => window.print());

    const jobId = jobIdFromUrl();
    if (jobId) {
      open(jobId);
      return;
    }
    show("picker", true);
    try {
      await fillJobPicker($("job-picker"));
    } catch (e) {
      notice(e.message);
      return;
    }
    if (!$("job-picker").options.length) {
      notice("Ainda não há vagas. Rode uma coleta pelo painel.");
      return;
    }
    $("pick-btn").addEventListener("click", () => {
      const id = Number($("job-picker").value);
      history.replaceState(null, "", `/curriculo?job=${id}`);
      open(id);
    });
  }

  init();
})();
