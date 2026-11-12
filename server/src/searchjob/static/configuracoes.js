/* Aba Configurações: verificação, preferências editáveis, perfil em Markdown e coletas. */
(function () {
  "use strict";

  const { el, api, toast } = window.SJ;
  const $ = (id) => document.getElementById(id);
  const TAG_FIELDS = ["search_terms", "preferred_states", "exclude_title_terms", "blocked_terms"];
  const NUMBER_FIELDS = ["max_pages_per_term", "max_experience_years", "collect_every_hours", "report_hour"];
  const TEXT_FIELDS = ["llm_base_url", "llm_model"];
  const state = { config: null, tags: {}, prefsDirty: false, profileSaved: "", profileDirty: false };

  function show(id, visible) {
    $(id).classList.toggle("hidden", !visible);
  }

  function notice(message) {
    $("notice").replaceChildren(el("strong", {}, "Não foi possível carregar. "), message, " ",
      el("a", { href: "/painel" }, "Voltar ao painel"));
    show("notice", true);
  }

  // ------------------------------------------------------------ campo de etiquetas
  function tagInput(container, onChange) {
    let values = [];
    const list = el("span", { class: "tags" });
    const input = el("input", {
      type: "text", id: `${container.id}-input`, placeholder: "Adicionar…", autocomplete: "off",
    });
    container.replaceChildren(list, input);
    container.addEventListener("click", () => input.focus());

    function render() {
      list.replaceChildren(...values.map((v, i) => el(
        "span", { class: "tag" }, v,
        el("button", {
          type: "button", class: "tag-x", "aria-label": `Remover ${v}`,
          onclick: (e) => { e.stopPropagation(); values.splice(i, 1); render(); onChange(); },
        }, "×"),
      )));
    }
    function add(raw) {
      const parts = raw.split(",").map((p) => p.trim()).filter((p) => p.length >= 2);
      let changed = false;
      for (const p of parts) {
        if (!values.some((v) => v.toLowerCase() === p.toLowerCase())) {
          values.push(p.slice(0, 80));
          changed = true;
        }
      }
      input.value = "";
      if (changed) { render(); onChange(); }
    }
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        add(input.value);
      } else if (e.key === "Backspace" && !input.value && values.length) {
        values.pop();
        render();
        onChange();
      }
    });
    input.addEventListener("blur", () => { if (input.value.trim()) add(input.value); });

    return {
      get: () => [...values],
      set: (v) => { values = [...(v || [])]; render(); },
    };
  }

  // ------------------------------------------------------------ Markdown (seguro, sem HTML)
  function inline(text) {
    const frag = document.createDocumentFragment();
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    for (const m of text.matchAll(re)) {
      if (m.index > last) frag.append(text.slice(last, m.index));
      const token = m[0];
      frag.append(token.startsWith("**")
        ? el("strong", {}, token.slice(2, -2))
        : el("code", {}, token.slice(1, -1)));
      last = m.index + token.length;
    }
    if (last < text.length) frag.append(text.slice(last));
    return frag;
  }

  function renderMarkdown(text) {
    const out = document.createDocumentFragment();
    let lines = text.replace(/\r\n/g, "\n").split("\n");

    // Bloco de contato (--- chave: valor ---)
    if (lines[0] && lines[0].trim() === "---") {
      const end = lines.findIndex((l, i) => i > 0 && l.trim() === "---");
      if (end > 0) {
        const items = lines.slice(1, end).map((l) => l.split(/:(.*)/s)).filter((p) => p[1]);
        out.append(el("dl", { class: "contact-card" }, ...items.flatMap(([k, v]) => [
          el("dt", {}, k.trim()), el("dd", {}, v.trim()),
        ])));
        lines = lines.slice(end + 1);
      }
    }

    let list = null;
    let para = [];
    const flushPara = () => {
      if (para.length) out.append(el("p", {}, inline(para.join(" "))));
      para = [];
    };
    const flushList = () => { if (list) out.append(list); list = null; };

    for (const raw of lines) {
      const line = raw.trimEnd();
      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      const bullet = line.match(/^\s*[-*]\s+(.*)$/);
      if (heading) {
        flushPara(); flushList();
        const level = Math.min(heading[1].length + 2, 6);
        out.append(el(`h${level}`, {}, inline(heading[2])));
      } else if (bullet) {
        flushPara();
        if (!list) list = el("ul", {});
        list.append(el("li", {}, inline(bullet[1])));
      } else if (!line.trim()) {
        flushPara(); flushList();
      } else {
        flushList();
        para.push(line.trim());
      }
    }
    flushPara(); flushList();
    return out;
  }

  // ------------------------------------------------------------ verificação
  const ICONS = { ok: "✓", warn: "!", off: "–" };

  function renderChecks(cfg) {
    const { ok, warn } = cfg.summary;
    const total = cfg.checks.length;
    $("ok-count").textContent = ok;
    $("total-count").textContent = total;
    $("status-ring").className = `hero-ring ${warn ? "warn" : "ok"}`;
    $("status-title").textContent = warn
      ? `${warn} ${warn === 1 ? "item precisa" : "itens precisam"} de atenção`
      : "Tudo certo!";
    $("status-sub").textContent =
      `${ok} de ${total} itens em ordem · itens opcionais desligados não contam como problema · v${cfg.version}`;
    $("checks").replaceChildren(...cfg.checks.map((c) => el(
      "li", { class: `check ${c.level}` },
      el("span", { class: "check-icon", "aria-hidden": "true" }, ICONS[c.level]),
      el("div", {},
        el("strong", {}, c.label),
        el("span", { class: "sr-only" }, ` (${c.level === "ok" ? "ok" : c.level === "warn" ? "atenção" : "desligado"})`),
        el("div", { class: "small" }, c.detail),
        c.level !== "ok" && c.fix ? el("div", { class: "small muted" }, `Como resolver: ${c.fix}`) : null),
    )));
    show("status", true);
  }

  function renderSecrets(cfg) {
    const byId = Object.fromEntries(cfg.checks.map((c) => [c.id, c]));
    const rows = [
      ["api_key", "Chave de acesso", "SJ_API_KEY"],
      ["imap", "Alertas por e-mail", "SJ_IMAP_HOST · SJ_IMAP_USER · SJ_IMAP_PASSWORD"],
      ["telegram", "Aviso no Telegram", "SJ_TELEGRAM_BOT_TOKEN · SJ_TELEGRAM_CHAT_ID"],
    ];
    $("secrets").replaceChildren(...rows.map(([id, label, vars]) => {
      const c = byId[id] || { level: "off", detail: "" };
      const text = { ok: "✓ configurado", warn: "! atenção", off: "– desligado" }[c.level];
      return el("li", {},
        el("div", {}, el("strong", {}, label), el("div", { class: "small muted" }, el("code", {}, vars))),
        el("span", { class: `badge ${c.level === "ok" ? "good" : c.level === "warn" ? "bad" : ""}` }, text));
    }));
  }

  // ------------------------------------------------------------ preferências
  function setDirty(dirty) {
    state.prefsDirty = dirty;
    $("dirty").textContent = dirty ? "● Alterações não salvas" : "";
  }

  function fillPrefs(cfg) {
    const values = {
      search_terms: cfg.search.terms,
      preferred_states: cfg.search.preferred_states,
      max_pages_per_term: cfg.search.max_pages_per_term,
      exclude_title_terms: cfg.filters.exclude_title_terms,
      blocked_terms: cfg.filters.blocked_terms,
      max_experience_years: cfg.filters.max_experience_years,
      llm_base_url: cfg.llm.base_url,
      llm_model: cfg.llm.model,
      collect_every_hours: cfg.schedule.collect_every_hours,
      report_hour: cfg.schedule.report_hour,
    };
    TAG_FIELDS.forEach((f) => state.tags[f].set(values[f]));
    [...NUMBER_FIELDS, ...TEXT_FIELDS].forEach((f) => { $(`f-${f}`).value = values[f]; });
    $("timezone").textContent = cfg.schedule.timezone;
    const llm = $("llm-status");
    llm.textContent = cfg.llm.online ? "✓ online" : "! offline";
    llm.className = `badge ${cfg.llm.online ? "good" : "bad"}`;
    setDirty(false);
  }

  function collectPrefs() {
    const body = {};
    TAG_FIELDS.forEach((f) => { body[f] = state.tags[f].get(); });
    NUMBER_FIELDS.forEach((f) => { body[f] = Number($(`f-${f}`).value); });
    TEXT_FIELDS.forEach((f) => { body[f] = $(`f-${f}`).value.trim(); });
    return body;
  }

  async function savePrefs(event) {
    event.preventDefault();
    const body = collectPrefs();
    if (!body.search_terms.length) {
      toast("Adicione pelo menos um termo de busca.");
      return;
    }
    $("save-prefs").disabled = true;
    try {
      applyConfig(await api("/api/preferences", { method: "PUT", body }));
      toast("Preferências salvas e aplicadas.");
    } catch (e) {
      toast(`Não salvou: ${e.message}`);
    } finally {
      $("save-prefs").disabled = false;
    }
  }

  async function resetPrefs() {
    if (!window.confirm("Descartar as preferências feitas aqui e voltar aos valores do .env?")) return;
    try {
      applyConfig(await api("/api/preferences", { method: "DELETE" }));
      toast("Voltou para os valores do .env.");
    } catch (e) {
      toast(e.message);
    }
  }

  // ------------------------------------------------------------ perfil
  function renderProfilePreview() {
    const text = $("profile-editor").value;
    $("profile-preview").replaceChildren(renderMarkdown(text));
    $("profile-count").textContent = `${text.length.toLocaleString("pt-BR")} caracteres`;
    state.profileDirty = text !== state.profileSaved;
    $("profile-save").textContent = state.profileDirty ? "Salvar perfil ●" : "Salvar perfil";
  }

  function renderProfileMeta(cfg) {
    const labels = { nome: "Nome", email: "E-mail", telefone: "Telefone", cidade: "Cidade",
      linkedin: "LinkedIn", github: "GitHub" };
    $("contact-chips").replaceChildren(...Object.entries(cfg.profile.contact_fields).map(([k, ok]) =>
      el("span", { class: `chip ${ok ? "" : "chip-missing"}` }, `${ok ? "✓" : "✗"} ${labels[k] || k}`)));
    $("profile-skills").replaceChildren(...(cfg.profile.skills.length
      ? cfg.profile.skills.map((s) => el("span", { class: "chip" }, s))
      : [el("span", { class: "empty" }, "Nenhum requisito reconhecido ainda.")]));
    show("profile-example", cfg.profile.using_example);
  }

  async function loadProfile() {
    const data = await api("/api/profile");
    state.profileSaved = data.markdown;
    $("profile-editor").value = data.markdown;
    renderProfilePreview();
  }

  async function saveProfile() {
    const markdown = $("profile-editor").value;
    $("profile-save").disabled = true;
    try {
      applyConfig(await api("/api/profile", { method: "PUT", body: { markdown } }));
      state.profileSaved = markdown;
      renderProfilePreview();
      toast("Perfil salvo. As próximas análises já usam a versão nova.");
    } catch (e) {
      toast(`Não salvou: ${e.message}`);
    } finally {
      $("profile-save").disabled = false;
    }
  }

  // ------------------------------------------------------------ coletas
  function renderRuns(cfg) {
    const fmtDate = (iso) => new Date(iso).toLocaleString("pt-BR",
      { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    $("runs-body").replaceChildren(...cfg.runs.map((r) => el(
      "tr", {},
      el("td", {}, fmtDate(r.ran_at)),
      el("td", { class: "num" }, r.found), el("td", { class: "num" }, r.new),
      el("td", { class: "num" }, r.excluded), el("td", { class: "num" }, r.analyzed ?? "–"),
      el("td", { class: "num" }, r.errors ? el("span", { class: "flag" }, `⚠ ${r.errors}`) : "0"),
    )));
    show("runs-empty", !cfg.runs.length);
  }

  // ------------------------------------------------------------ abas
  function selectTab(name) {
    ["prefs", "profile", "runs"].forEach((t) => {
      const active = t === name;
      $(`tab-btn-${t}`).setAttribute("aria-selected", String(active));
      $(`tab-${t}`).hidden = !active;
    });
    const hash = { prefs: "", profile: "#perfil", runs: "#coletas" }[name];
    history.replaceState(null, "", location.pathname + hash);
  }

  function applyConfig(cfg) {
    state.config = cfg;
    renderChecks(cfg);
    renderSecrets(cfg);
    fillPrefs(cfg);
    renderProfileMeta(cfg);
    renderRuns(cfg);
  }

  async function init() {
    TAG_FIELDS.forEach((f) => { state.tags[f] = tagInput($(`f-${f}`), () => setDirty(true)); });
    $("prefs-form").addEventListener("input", () => setDirty(true));
    $("prefs-form").addEventListener("submit", savePrefs);
    $("reset-prefs").addEventListener("click", resetPrefs);

    let previewTimer;
    $("profile-editor").addEventListener("input", () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(renderProfilePreview, 150);
    });
    $("profile-save").addEventListener("click", saveProfile);
    $("profile-revert").addEventListener("click", () => {
      $("profile-editor").value = state.profileSaved;
      renderProfilePreview();
    });

    const tabs = { "tab-btn-prefs": "prefs", "tab-btn-profile": "profile", "tab-btn-runs": "runs" };
    Object.entries(tabs).forEach(([id, name]) => $(id).addEventListener("click", () => selectTab(name)));
    selectTab({ "#perfil": "profile", "#coletas": "runs" }[location.hash] || "prefs");

    window.addEventListener("beforeunload", (e) => {
      if (state.prefsDirty || state.profileDirty) e.preventDefault();
    });

    try {
      applyConfig(await api("/api/config"));
      await loadProfile();
    } catch (e) {
      notice(e.message);
      return;
    }
    show("content", true);
  }

  init();
})();
