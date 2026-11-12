/* Painel SearchJob: busca /api/dashboard e /api/jobs e desenha tudo com HTML/SVG puro. */
(function () {
  "use strict";

  const KEY_STORAGE = "searchjob.apiKey";
  const DAYS_STORAGE = "searchjob.days";
  const STATUS_LABELS = {
    new: "Novas", applied: "Candidatado", interview: "Entrevista",
    offer: "Proposta", rejected: "Recusado", ignored: "Ignorada",
  };
  const $ = (id) => document.getElementById(id);
  const fmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const brl = new Intl.NumberFormat("pt-BR", {
    style: "currency", currency: "BRL", maximumFractionDigits: 0,
  });

  function salaryText(job) {
    if (!job.salary_min) return "";
    if (job.salary_max && job.salary_max !== job.salary_min) {
      return `${brl.format(job.salary_min)} – ${brl.format(job.salary_max)}`;
    }
    return brl.format(job.salary_min);
  }
  const state = { days: 30, data: null, searchTimer: null };

  // ------------------------------------------------------------ utilidades
  const storage = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* modo privado */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* modo privado */ } },
  };

  /** Cria um elemento: el("div", {class: "x"}, "texto", outroEl). Texto nunca vira HTML. */
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "style") node.style.cssText = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  function toast(text) {
    const t = $("toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 3500);
  }

  function formatDate(iso, opts) {
    if (!iso) return "";
    const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
    return d.toLocaleDateString("pt-BR", opts || { day: "2-digit", month: "2-digit" });
  }

  // ------------------------------------------------------------ tooltip
  const tip = $("tooltip");
  function showTip(event, title, body) {
    tip.replaceChildren(el("strong", {}, title), body ? el("span", {}, body) : null);
    tip.hidden = false;
    const pad = 14;
    const { innerWidth: w, innerHeight: h } = window;
    const rect = tip.getBoundingClientRect();
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    if (x + rect.width > w - 8) x = event.clientX - rect.width - pad;
    if (y + rect.height > h - 8) y = event.clientY - rect.height - pad;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
  }
  function hideTip() { tip.hidden = true; }
  function withTip(node, title, body) {
    node.addEventListener("mousemove", (e) => showTip(e, title, body));
    node.addEventListener("mouseleave", hideTip);
    return node;
  }

  // ------------------------------------------------------------ API
  function apiKey() { return storage.get(KEY_STORAGE) || ""; }

  async function api(path, options) {
    const opts = options || {};
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey() },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (res.status === 401) {
      showLogin("Chave inválida ou ausente.");
      throw new Error("unauthorized");
    }
    if (!res.ok) throw new Error(`Erro ${res.status}`);
    return res.json();
  }

  // ------------------------------------------------------------ componentes de gráfico
  /**
   * Barras horizontais de série única.
   * items: [{label, value, text, badge?, tipTitle?, tipBody?}]
   */
  function hbars(container, items, options) {
    const opts = options || {};
    container.replaceChildren();
    if (!items.length) {
      container.append(el("div", { class: "empty" }, opts.empty || "Sem dados no período."));
      return;
    }
    const max = opts.max || Math.max(...items.map((i) => i.value), 1);
    for (const item of items) {
      const width = Math.max(0, Math.min(100, (item.value / max) * 100));
      const row = el(
        "div", { class: "hbar" },
        el("span", { class: "name", title: item.label }, item.label),
        el("span", { class: "track" }, el("span", { class: "fill", style: `width:${width}%` })),
        el("span", { class: "val" }, item.badge || null, item.text),
      );
      withTip(row, item.tipTitle || item.label, item.tipBody || item.text);
      container.append(row);
    }
  }

  /**
   * Colunas verticais em SVG (uma série), com grade recessiva e tooltip por coluna.
   * points: [{label, value, tick?, tipTitle, tipBody}]
   */
  function columns(container, points, options) {
    const opts = options || {};
    container.replaceChildren();
    const width = Math.max(container.clientWidth, 280);
    const height = container.clientHeight || 200;
    const m = { top: 8, right: 4, bottom: 22, left: 30 };
    const innerW = width - m.left - m.right;
    const innerH = height - m.top - m.bottom;
    const maxVal = Math.max(...points.map((p) => p.value), 0);
    const niceMax = maxVal <= 4 ? Math.max(maxVal, 1) : Math.ceil(maxVal / 4) * 4;
    const y = (v) => m.top + innerH - (v / niceMax) * innerH;
    const slot = innerW / points.length;
    const gap = Math.min(Math.max(slot * 0.25, 2), 12);
    const barW = Math.max(slot - gap, 1);

    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none" });
    const ticks = niceMax <= 4 ? [0, niceMax] : [0, niceMax / 2, niceMax];
    for (const t of ticks) {
      root.append(svg("line", {
        class: t === 0 ? "baseline" : "gridline",
        x1: m.left, x2: width - m.right, y1: y(t), y2: y(t),
      }));
      const label = svg("text", { class: "tick", x: m.left - 6, y: y(t) + 4, "text-anchor": "end" });
      label.textContent = fmt.format(t);
      root.append(label);
    }

    points.forEach((p, i) => {
      const x = m.left + i * slot + gap / 2;
      if (p.value > 0) {
        const top = y(p.value);
        const h = m.top + innerH - top;
        const r = Math.min(4, barW / 2, h);
        // Topo arredondado de 4px, base reta apoiada no eixo.
        root.append(svg("path", {
          class: "bar",
          d: `M${x},${m.top + innerH} V${top + r} Q${x},${top} ${x + r},${top} ` +
             `H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${m.top + innerH} Z`,
        }));
      }
      if (p.tick) {
        const t = svg("text", {
          class: "tick", x: x + barW / 2, y: height - 6, "text-anchor": "middle",
        });
        t.textContent = p.tick;
        root.append(t);
      }
      const hit = svg("rect", {
        class: "hit", x: m.left + i * slot, y: m.top, width: slot, height: innerH,
      });
      withTip(hit, p.tipTitle, p.tipBody);
      root.append(hit);
    });
    container.append(root);
    if (opts.ariaLabel) container.setAttribute("aria-label", opts.ariaLabel);
  }

  function badge(have) {
    return have
      ? el("span", { class: "badge good" }, "✓ tem")
      : el("span", { class: "badge bad" }, "✗ falta");
  }

  // ------------------------------------------------------------ seções
  function renderKpis(k) {
    const items = [
      ["Vagas no período", fmt.format(k.total_jobs), `últimos ${state.days} dias`],
      ["Novas nas últimas 24h", fmt.format(k.new_last_24h), null],
      ["Nota média da IA", k.avg_score === null ? "–" : fmt.format(k.avg_score),
        `${fmt.format(k.analyzed)} analisadas`],
      ["Vagas boas (nota ≥ 7)", fmt.format(k.good_matches), "para priorizar"],
      ["Candidaturas enviadas", fmt.format(k.applications), "desde o início"],
      ["Taxa de resposta", `${fmt.format(k.response_rate)}%`, "entrevista ou proposta"],
      ["Salário mediano", k.salary_median ? brl.format(k.salary_median) : "–",
        k.salary_count ? `em ${k.salary_count} vaga(s) que informam` : "nenhuma vaga informou"],
      ["Descartadas na coleta", fmt.format(k.excluded || 0), "sênior, termos bloqueados…"],
    ];
    $("kpis").replaceChildren(...items.map(([label, value, hint]) => el(
      "div", { class: "kpi" },
      el("div", { class: "label" }, label),
      el("div", { class: "value" }, value),
      hint ? el("div", { class: "hint" }, hint) : null,
    )));
  }

  function chip(text, count) {
    return el("span", { class: "chip" }, text, count === undefined ? null : el("small", {}, count));
  }

  function renderCoverage(d) {
    $("coverage-value").textContent = d.skills.length ? fmt.format(d.coverage) : "–";
    const s = $("strength-chips");
    const g = $("gap-chips");
    s.replaceChildren(...(d.strengths.length
      ? d.strengths.map((x) => chip(x.skill, `${fmt.format(x.percent)}%`))
      : [el("span", { class: "empty" }, "Nenhum requisito do mercado encontrado no seu perfil.")]));
    g.replaceChildren(...(d.gaps.length
      ? d.gaps.map((x) => chip(x.skill, `${fmt.format(x.percent)}%`))
      : [el("span", { class: "empty" }, "Nenhuma lacuna. Seu perfil cobre o que foi pedido!")]));
  }

  function renderSkills(d) {
    hbars($("skills-chart"), d.skills.slice(0, 15).map((s) => ({
      label: s.skill,
      value: s.percent,
      text: `${fmt.format(s.percent)}%`,
      badge: badge(s.have),
      tipTitle: s.skill,
      tipBody: `${s.count} vaga(s), ${fmt.format(s.percent)}% do período · ` +
        (s.have ? "está no seu perfil" : "não aparece no seu perfil"),
    })), { max: 100, empty: "Ainda não há vagas coletadas no período." });
  }

  function renderRecommendations(d) {
    const list = $("recommendations");
    if (!d.recommendations.length) {
      list.replaceChildren(el("li", { class: "empty" }, "Sem lacunas relevantes no período."));
      return;
    }
    list.replaceChildren(...d.recommendations.map((r) => el(
      "li", {},
      el("strong", {}, r.skill),
      el("span", { class: "meta" }, `Pedido em ${fmt.format(r.percent)}% das vagas`),
      el("div", { class: "tip" }, r.tip),
    )));
  }

  function renderResume(d) {
    const box = $("resume-keywords");
    box.replaceChildren(...(d.resume_keywords.length
      ? d.resume_keywords.map((k) => chip(k))
      : [el("span", { class: "empty" }, "Complete o data/profile.md para ver sugestões.")]));
    hbars($("ai-missing"), d.ai_missing.slice(0, 8).map((m) => ({
      label: m.label,
      value: m.percent,
      text: `${fmt.format(m.percent)}%`,
      tipBody: `Apontado em ${m.count} vaga(s) analisada(s)`,
    })), { max: 100, empty: "A IA ainda não analisou vagas neste período." });
  }

  function renderRepetition(d) {
    const list = $("reposts");
    list.replaceChildren(...(d.reposts.length
      ? d.reposts.slice(0, 8).map((r) => el(
        "li", {},
        el("span", { class: "times" }, `${r.count}×`),
        el("div", {},
          el("div", {}, r.title),
          el("div", { class: "sub" }, `${r.company} · ${formatDate(r.first_seen)} a ${formatDate(r.last_seen)}`)),
      ))
      : [el("li", { class: "empty" }, "Nenhuma vaga repetida no período.")]));

    hbars($("companies"), d.companies.map((c) => ({
      label: c.label, value: c.count, text: fmt.format(c.count),
      tipBody: `${c.count} vaga(s), ${fmt.format(c.percent)}% do período`,
    })));
    hbars($("titles"), d.titles.map((t) => ({
      label: t.label, value: t.count, text: fmt.format(t.count),
      tipBody: `${t.count} vaga(s) com cargo equivalente`,
    })));
  }

  function renderTimeline(d) {
    const every = d.timeline.length > 45 ? 14 : d.timeline.length > 14 ? 7 : 1;
    const lastIdx = d.timeline.length - 1;
    columns($("timeline"), d.timeline.map((p, i) => ({
      value: p.count,
      tick: (lastIdx - i) % every === 0 ? formatDate(p.date) : "",
      tipTitle: formatDate(p.date, { weekday: "short", day: "2-digit", month: "short" }),
      tipBody: `${p.count} vaga(s) publicada(s)`,
    })), { ariaLabel: `Vagas publicadas por dia nos últimos ${state.days} dias` });
  }

  function renderScores(d) {
    columns($("scores"), d.score_histogram.map((s) => ({
      value: s.count,
      tick: String(s.score),
      tipTitle: `Nota ${s.score}`,
      tipBody: `${s.count} vaga(s)`,
    })), { ariaLabel: "Quantidade de vagas por nota da IA" });
  }

  function renderFunnel(d) {
    hbars($("funnel"), d.funnel.map((f) => ({
      label: f.label, value: f.count, text: fmt.format(f.count),
    })));
    const k = d.kpis;
    $("funnel-note").textContent = k.applications
      ? `${fmt.format(k.response_rate)}% das candidaturas viraram entrevista ou proposta.`
      : "Marque vagas como 'Candidatado' (pela extensão ou na tabela) para acompanhar o funil.";
  }

  function renderWorkplace(d) {
    const box = $("workplace");
    if (!d.workplace.length) {
      box.replaceChildren(el("div", { class: "empty" }, "Sem dados no período."));
      return;
    }
    const colors = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
    const colorFor = (i) => colors[i] || "var(--other)";
    const stack = el("div", { class: "stack" }, ...d.workplace.map((w, i) => withTip(
      el("span", { style: `flex:${w.count};background:${colorFor(i)}` }),
      w.label, `${w.count} vaga(s), ${fmt.format(w.percent)}%`,
    )));
    const legend = el("div", { class: "legend" }, ...d.workplace.map((w, i) => el(
      "div", { class: "item" },
      el("span", { class: "sw", style: `background:${colorFor(i)}` }),
      el("span", {}, w.label),
      el("span", { class: "v" }, `${fmt.format(w.percent)}% · ${w.count}`),
    )));
    box.replaceChildren(stack, legend);
  }

  function renderFilters(d) {
    hbars($("excluded"), (d.excluded_reasons || []).map((r) => ({
      label: r.label, value: r.count, text: fmt.format(r.count),
      tipBody: `${r.count} vaga(s) descartada(s) no período`,
    })), { empty: "Nenhuma vaga descartada no período." });
    hbars($("flags"), (d.flags || []).map((f) => ({
      label: f.label, value: f.count, text: fmt.format(f.count),
      tipBody: `${f.count} vaga(s), ${fmt.format(f.percent)}% do período`,
    })), { empty: "Nenhum aviso nas vagas do período." });
  }

  function renderStates(d) {
    hbars($("states"), d.states.map((s) => ({
      label: s.label, value: s.count, text: `${fmt.format(s.percent)}%`,
      tipBody: `${s.count} vaga(s)`,
    })));
  }

  // ------------------------------------------------------------ tabela de vagas
  async function loadJobs() {
    const params = new URLSearchParams({ limit: "200" });
    const status = $("f-status").value;
    const score = $("f-score").value;
    const q = $("f-query").value.trim();
    if (status) params.set("status", status);
    if (score) params.set("min_score", score);
    if (q) params.set("q", q);
    let jobs;
    try {
      jobs = await api(`/api/jobs?${params}`);
    } catch (e) {
      return;
    }
    const body = $("jobs-body");
    body.replaceChildren(...jobs.map(jobRow));
    $("jobs-empty").classList.toggle("hidden", jobs.length > 0);
  }

  function jobRow(job) {
    const location = job.workplace_type === "remote"
      ? "Remoto"
      : [job.city, job.state].filter(Boolean).join("/") || "–";
    const select = el("select", { "aria-label": `Status de ${job.title}` },
      ...Object.entries(STATUS_LABELS).map(([value, label]) =>
        el("option", { value, selected: value === job.status ? "selected" : null }, label)));
    select.addEventListener("change", async () => {
      try {
        await api(`/api/jobs/${job.id}`, { method: "PATCH", body: { status: select.value } });
        toast(`"${job.title}" agora está como ${STATUS_LABELS[select.value]}.`);
      } catch (e) {
        toast("Não foi possível atualizar o status.");
      }
    });
    return el(
      "tr", {},
      el("td", { class: "num" }, el("span", { class: "score-pill" }, job.score ?? "–")),
      el("td", {},
        el("a", { href: job.url, target: "_blank", rel: "noopener" }, job.title),
        el("div", { class: "company" }, job.company || "Empresa não informada"),
        salaryText(job) ? el("div", { class: "salary" }, salaryText(job)) : null,
        ...(job.flags || []).map((f) => el("div", { class: "flag" }, `⚠ ${f}`))),
      el("td", {}, location),
      el("td", {}, el("div", { class: "missing" }, (job.missing || []).join(", ") || "–")),
      el("td", {}, select),
    );
  }

  // ------------------------------------------------------------ fluxo principal
  function renderAll() {
    const d = state.data;
    if (!d) return;
    $("updated").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR",
      { hour: "2-digit", minute: "2-digit" })}`;
    renderKpis(d.kpis);
    renderCoverage(d);
    renderSkills(d);
    renderRecommendations(d);
    renderResume(d);
    renderRepetition(d);
    renderTimeline(d);
    renderScores(d);
    renderFunnel(d);
    renderWorkplace(d);
    renderStates(d);
    renderFilters(d);
  }

  async function load() {
    try {
      state.data = await api(`/api/dashboard?days=${state.days}`);
    } catch (e) {
      if (e.message !== "unauthorized") toast(`Falha ao carregar o painel: ${e.message}`);
      return;
    }
    $("login").classList.add("hidden");
    $("content").classList.remove("hidden");
    renderAll();
    loadJobs();
  }

  function showLogin(message) {
    $("content").classList.add("hidden");
    $("login").classList.remove("hidden");
    $("login-error").textContent = message || "";
    $("key-input").focus();
  }

  function init() {
    // Aceita ?key= uma vez, guarda localmente e limpa a URL.
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("key");
    if (fromUrl) {
      storage.set(KEY_STORAGE, fromUrl);
      url.searchParams.delete("key");
      history.replaceState(null, "", url.pathname + url.search);
    }
    const savedDays = Number(storage.get(DAYS_STORAGE));
    if ([7, 30, 90].includes(savedDays)) state.days = savedDays;
    document.querySelectorAll(".segmented button").forEach((b) => {
      b.setAttribute("aria-pressed", String(Number(b.dataset.days) === state.days));
      b.addEventListener("click", () => {
        state.days = Number(b.dataset.days);
        storage.set(DAYS_STORAGE, String(state.days));
        document.querySelectorAll(".segmented button").forEach((x) =>
          x.setAttribute("aria-pressed", String(x === b)));
        load();
      });
    });

    $("login-form").addEventListener("submit", (e) => {
      e.preventDefault();
      storage.set(KEY_STORAGE, $("key-input").value.trim());
      load();
    });
    $("collect-btn").addEventListener("click", async () => {
      $("collect-btn").disabled = true;
      try {
        await api("/api/collect", { method: "POST" });
        toast("Coleta iniciada. Atualize o painel em alguns minutos.");
      } catch (e) {
        toast("Não foi possível iniciar a coleta.");
      } finally {
        setTimeout(() => { $("collect-btn").disabled = false; }, 5000);
      }
    });
    $("report-link").addEventListener("click", (e) => {
      e.preventDefault();
      const key = apiKey();
      window.open(`/report${key ? `?key=${encodeURIComponent(key)}` : ""}`, "_blank", "noopener");
    });
    ["f-status", "f-score"].forEach((id) => $(id).addEventListener("change", loadJobs));
    $("f-query").addEventListener("input", () => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(loadJobs, 300);
    });

    let resizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (!state.data) return;
        renderTimeline(state.data);
        renderScores(state.data);
      }, 150);
    });

    // Sem chave salva tenta mesmo assim (servidor pode estar sem SJ_API_KEY); 401 mostra o login.
    load();
  }

  init();
})();
