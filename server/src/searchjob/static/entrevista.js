/* Página de preparação para entrevista. Depende de common.js (window.SJ). */
(function () {
  "use strict";

  const { el, api, toast, storage, jobIdFromUrl, fillJobPicker, scoreLabel } = window.SJ;
  const $ = (id) => document.getElementById(id);
  const state = { jobId: null, job: null };

  function show(id, visible) {
    $(id).classList.toggle("hidden", !visible);
  }

  function notice(message) {
    $("notice").replaceChildren(
      el("strong", {}, "Não foi possível continuar. "),
      message,
      " ",
      el("a", { href: "/painel" }, "Voltar ao painel"),
    );
    show("notice", true);
  }

  // ------------------------------------------------------------ feedback da IA
  function renderFeedback(box, fb) {
    const [kind, label] = scoreLabel(fb.score);
    box.replaceChildren(
      el("div", { class: "fb-head" },
        el("span", { class: "score-big" }, `${fb.score}/10`),
        el("span", { class: `badge ${kind}` }, label)),
      fb.strengths.length ? el("div", {},
        el("h4", {}, "O que foi bom"),
        el("ul", { class: "plain-list good-list" }, ...fb.strengths.map((s) => el("li", {}, s)))) : null,
      fb.improve.length ? el("div", {},
        el("h4", {}, "O que melhorar"),
        el("ul", { class: "plain-list improve-list" }, ...fb.improve.map((s) => el("li", {}, s)))) : null,
      fb.model_answer ? el("details", { open: true },
        el("summary", {}, "Exemplo de resposta"),
        el("p", { class: "model" }, fb.model_answer)) : null,
    );
  }

  /** Bloco de resposta com textarea salvo localmente e botão de avaliação. */
  function answerBlock(question, storageKey) {
    const textarea = el("textarea", {
      rows: 4, placeholder: "Escreva sua resposta como falaria na entrevista…",
      "aria-label": `Sua resposta: ${question}`,
    });
    textarea.value = storage.get(storageKey) || "";
    textarea.addEventListener("input", () => storage.set(storageKey, textarea.value));
    const feedback = el("div", { class: "feedback", "aria-live": "polite" });
    const button = el("button", { type: "button" }, "Avaliar minha resposta");
    button.addEventListener("click", async () => {
      const answer = textarea.value.trim();
      if (answer.length < 3) {
        toast("Escreva sua resposta primeiro.");
        textarea.focus();
        return;
      }
      button.disabled = true;
      button.textContent = "Avaliando…";
      try {
        const fb = await api("/api/interview/feedback", {
          method: "POST", body: { question, answer, job_id: state.jobId },
        });
        renderFeedback(feedback, fb);
      } catch (e) {
        feedback.replaceChildren(el("p", { class: "error small" }, e.message));
      } finally {
        button.disabled = false;
        button.textContent = "Avaliar de novo";
      }
    });
    return el("div", { class: "answer" }, textarea, button, feedback);
  }

  // ------------------------------------------------------------ preparação
  function renderPrep(prep) {
    $("pitch").textContent = prep.pitch || "A IA não gerou um roteiro. Tente gerar de novo.";

    $("questions").replaceChildren(...prep.questions.map((q, i) => el(
      "li", { class: "qitem" },
      el("p", { class: "question" }, q.question),
      (q.why || q.tip) ? el("details", {},
        el("summary", {}, "Por que perguntam e como responder"),
        q.why ? el("p", { class: "small" }, el("strong", {}, "Avaliam: "), q.why) : null,
        q.tip ? el("p", { class: "small" }, el("strong", {}, "Dica: "), q.tip) : null) : null,
      answerBlock(q.question, `searchjob.interview.${state.jobId}.q${i}`),
    )));

    $("scenarios").replaceChildren(...(prep.scenarios.length ? prep.scenarios.map((s, i) => el(
      "article", { class: "scenario" },
      el("h3", {}, `Caso ${i + 1}`),
      el("p", {}, s.situation),
      answerBlock(`Caso prático: ${s.situation} Como você resolveria?`,
        `searchjob.interview.${state.jobId}.s${i}`),
      s.steps.length ? el("details", {},
        el("summary", {}, "Ver um caminho de resolução"),
        el("ol", { class: "steps" }, ...s.steps.map((step) => el("li", {}, step)))) : null,
    )) : [el("p", { class: "muted small" }, "Nenhum caso prático gerado.")]));

    $("ask-them").replaceChildren(...(prep.ask_them.length
      ? prep.ask_them.map((q) => el("li", {}, q))
      : [el("li", { class: "muted" }, "Pergunte sobre o dia a dia do time e as ferramentas usadas.")]));

    if (prep.created_at) {
      $("generated").textContent =
        `Gerado em ${new Date(prep.created_at).toLocaleString("pt-BR")} pela IA local.`;
    }
    show("prep", true);
    show("regen-btn", true);
  }

  async function loadPrep(regenerate) {
    show("loading", true);
    show("notice", false);
    $("regen-btn").disabled = true;
    try {
      const prep = await api(
        `/api/jobs/${state.jobId}/interview${regenerate ? "?regenerate=true" : ""}`,
        { method: "POST" },
      );
      renderPrep(prep);
    } catch (e) {
      notice(e.message);
    } finally {
      show("loading", false);
      $("regen-btn").disabled = false;
    }
  }

  async function openJob(jobId) {
    state.jobId = jobId;
    try {
      state.job = await api(`/api/jobs/${jobId}`);
    } catch (e) {
      notice(e.message);
      return;
    }
    const job = state.job;
    $("job-meta").replaceChildren(
      el("a", { href: job.url, target: "_blank", rel: "noopener" }, job.title),
      ` · ${job.company || "Empresa não informada"}`,
    );
    document.title = `Entrevista: ${job.title}`;
    $("resume-link").href = `/curriculo?job=${jobId}`;
    show("resume-link", true);
    show("picker", false);
    loadPrep(false);
  }

  async function init() {
    $("regen-btn").addEventListener("click", () => loadPrep(true));
    $("copy-pitch").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("pitch").textContent);
        toast("Roteiro copiado.");
      } catch (e) {
        toast("Não foi possível copiar. Selecione o texto manualmente.");
      }
    });

    const jobId = jobIdFromUrl();
    if (jobId) {
      openJob(jobId);
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
      notice("Ainda não há vagas para preparar. Rode uma coleta pelo painel.");
      return;
    }
    $("pick-btn").addEventListener("click", () => {
      const id = Number($("job-picker").value);
      history.replaceState(null, "", `/entrevista?job=${id}`);
      openJob(id);
    });
  }

  init();
})();
