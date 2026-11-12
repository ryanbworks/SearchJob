/* Funções compartilhadas pelas páginas de entrevista e currículo. */
(function (root) {
  "use strict";

  const KEY_STORAGE = "searchjob.apiKey";

  const storage = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* modo privado */ } },
  };

  // Aceita ?key= uma vez (vindo da extensão), guarda localmente e limpa a URL.
  (function captureKeyFromUrl() {
    const url = new URL(window.location.href);
    const key = url.searchParams.get("key");
    if (!key) return;
    storage.set(KEY_STORAGE, key);
    url.searchParams.delete("key");
    history.replaceState(null, "", url.pathname + url.search);
  })();

  /** Cria um elemento. Texto nunca é interpretado como HTML. */
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function api(path, options) {
    const opts = options || {};
    let res;
    try {
      res = await fetch(path, {
        method: opts.method || "GET",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": storage.get(KEY_STORAGE) || "",
        },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch (e) {
      throw new ApiError("Servidor inacessível.", 0);
    }
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail; } catch (e) { detail = ""; }
      const messages = {
        401: "Chave de acesso ausente ou inválida. Entre pelo painel primeiro.",
        404: "Vaga não encontrada.",
        503: "A IA local está offline. Ligue o Ollama/LM Studio e tente de novo.",
      };
      throw new ApiError(messages[res.status] || detail || `Erro ${res.status}`, res.status);
    }
    return res.json();
  }

  function toast(text) {
    const t = document.getElementById("toast");
    if (!t) return;
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 3500);
  }

  function jobIdFromUrl() {
    const id = Number(new URL(window.location.href).searchParams.get("job"));
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  /** Lista para escolher uma vaga quando a página abre sem ?job=. */
  async function fillJobPicker(select) {
    const groups = [
      ["Em entrevista", "/api/jobs?status=interview&limit=50"],
      ["Candidatado", "/api/jobs?status=applied&limit=50"],
      ["Novas (nota ≥ 6)", "/api/jobs?status=new&min_score=6&limit=50"],
    ];
    for (const [label, path] of groups) {
      const jobs = await api(path);
      if (!jobs.length) continue;
      select.append(el("optgroup", { label },
        ...jobs.map((j) => el("option", { value: j.id },
          `${j.score ?? "–"} | ${j.title} — ${j.company || "?"}`))));
    }
  }

  function scoreLabel(score) {
    if (score >= 8) return ["good", "Boa resposta"];
    if (score >= 5) return ["warn", "Dá para melhorar"];
    return ["bad", "Precisa treinar"];
  }

  root.SJ = { storage, el, api, ApiError, toast, jobIdFromUrl, fillJobPicker, scoreLabel };
})(window);
