"use strict";

const $ = (id) => document.getElementById(id);
let currentTab = null;
let jobsById = new Map();

function setStatus(el, text, kind) {
  el.textContent = text;
  el.className = `status ${kind || ""}`.trim();
}

function describeJob(job) {
  const parts = [job.company || "Empresa não informada"];
  if (job.score !== null && job.score !== undefined) parts.push(`nota ${job.score}/10`);
  if (job.status && job.status !== "new") parts.push(`status: ${job.status}`);
  return parts.join(" · ");
}

function addJobOption(job) {
  if (jobsById.has(job.id)) return;
  jobsById.set(job.id, job);
  const opt = document.createElement("option");
  opt.value = String(job.id);
  opt.textContent = `${job.score ?? "–"} | ${job.title} — ${job.company || "?"}`;
  $("job-select").appendChild(opt);
}

function selectedJob() {
  const id = Number($("job-select").value);
  return id ? jobsById.get(id) : null;
}

function renderJobInfo() {
  const job = selectedJob();
  $("job-info").textContent = job ? describeJob(job) : "";
  $("job-links").classList.toggle("hidden", !job);
}

/** Abre uma página do servidor (painel, entrevista, currículo) numa nova aba. */
async function openServerPage(path, params) {
  const settings = await SJ.getSettings();
  if (!settings.serverUrl) {
    browser.runtime.openOptionsPage();
    return;
  }
  const url = new URL(path, settings.serverUrl);
  for (const [k, v] of Object.entries(params || {})) url.searchParams.set(k, v);
  browser.tabs.create({ url: url.toString() });
  window.close();
}

async function loadServerState() {
  try {
    await SJ.api("/api/jobs?limit=1");
    $("server-dot").className = "dot ok";
    $("server-label").textContent = "servidor online";
  } catch (err) {
    $("server-dot").className = "dot err";
    $("server-label").textContent = "offline";
    $("server-label").title = err.message;
    return;
  }

  try {
    const match = await SJ.api(`/api/jobs/match?url=${encodeURIComponent(currentTab.url)}`);
    addJobOption(match);
    $("job-select").value = String(match.id);
  } catch (err) {
    // Página fora do banco (ex.: site da empresa). O usuário escolhe na lista.
  }
  try {
    const jobs = await SJ.api("/api/jobs?status=new&limit=40");
    jobs.forEach(addJobOption);
  } catch (err) {
    // Lista é opcional.
  }
  renderJobInfo();
}

async function fillForm() {
  const btn = $("fill-btn");
  btn.disabled = true;
  setStatus($("fill-status"), "Preenchendo…");
  $("questions").replaceChildren();
  try {
    const [profile, settings] = await Promise.all([SJ.getProfile(), SJ.getSettings()]);
    if (!profile.fullName && !profile.email) {
      setStatus($("fill-status"), "Seu perfil está vazio. Abra 'Editar perfil' primeiro.", "warn");
      return;
    }
    const target = { tabId: currentTab.id, allFrames: true };
    await browser.scripting.executeScript({
      target,
      files: ["/lib/fields.js", "/content/autofill.js"],
    });
    const results = await browser.scripting.executeScript({
      target,
      func: (p, o) => window.__searchjob.fill(p, o),
      args: [profile, { overwrite: settings.overwrite }],
    });

    let filled = 0;
    let skipped = 0;
    const questions = [];
    for (const r of results) {
      if (!r.result) continue;
      filled += r.result.filled.length;
      skipped += r.result.skipped;
      r.result.questions.forEach((q) => questions.push({ ...q, frameId: r.frameId }));
    }
    const extra = skipped ? ` (${skipped} já estavam preenchidos)` : "";
    setStatus(
      $("fill-status"),
      filled ? `${filled} campo(s) preenchido(s)${extra}. Revise antes de enviar.` :
        `Nenhum campo reconhecido nesta página${extra}.`,
      filled ? "ok" : "warn",
    );
    renderQuestions(questions);
  } catch (err) {
    setStatus($("fill-status"), `Não foi possível preencher: ${err.message}`, "err");
  } finally {
    btn.disabled = false;
  }
}

function renderQuestions(questions) {
  const box = $("questions");
  if (!questions.length) return;
  const title = document.createElement("h2");
  title.textContent = `Perguntas abertas (${questions.length})`;
  box.appendChild(title);

  for (const q of questions) {
    const card = document.createElement("div");
    card.className = "card question";
    const text = document.createElement("p");
    text.textContent = q.label;
    const btn = document.createElement("button");
    btn.textContent = "Responder com IA";
    const status = document.createElement("div");
    status.className = "status small";
    btn.addEventListener("click", () => answer(q, btn, status));
    card.append(text, btn, status);
    box.appendChild(card);
  }
}

async function answer(question, btn, statusEl) {
  btn.disabled = true;
  setStatus(statusEl, "Gerando resposta com a IA local… (pode levar alguns segundos)");
  const job = selectedJob();
  const res = await browser.runtime.sendMessage({
    type: "answer",
    tabId: currentTab.id,
    frameId: question.frameId,
    questionId: question.id,
    question: question.label,
    jobId: job ? job.id : null,
    maxChars: question.maxLength,
  });
  if (res && res.ok) {
    setStatus(statusEl, "Resposta inserida. Leia e ajuste com suas palavras.", "ok");
  } else {
    setStatus(statusEl, (res && res.error) || "Falha ao gerar resposta.", "err");
    btn.disabled = false;
  }
}

async function markApplied() {
  const job = selectedJob();
  if (!job) {
    setStatus($("applied-status"), "Selecione a vaga na lista acima.", "warn");
    return;
  }
  try {
    const updated = await SJ.api(`/api/jobs/${job.id}`, {
      method: "PATCH",
      body: { status: "applied" },
    });
    jobsById.set(updated.id, updated);
    renderJobInfo();
    setStatus($("applied-status"), "Candidatura registrada. Boa sorte!", "ok");
  } catch (err) {
    setStatus($("applied-status"), err.message, "err");
  }
}

async function openReport(event) {
  event.preventDefault();
  const settings = await SJ.getSettings();
  // O painel guarda a chave localmente; as outras páginas reaproveitam.
  openServerPage("/painel", settings.apiKey ? { key: settings.apiKey } : {});
}

document.addEventListener("DOMContentLoaded", async () => {
  [currentTab] = await browser.tabs.query({ active: true, currentWindow: true });
  $("fill-btn").addEventListener("click", fillForm);
  $("applied-btn").addEventListener("click", markApplied);
  $("job-select").addEventListener("change", renderJobInfo);
  $("options-link").addEventListener("click", (e) => {
    e.preventDefault();
    browser.runtime.openOptionsPage();
    window.close();
  });
  $("report-link").addEventListener("click", openReport);
  document.querySelectorAll("#job-links a").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const job = selectedJob();
      if (!job) return;
      SJ.getSettings().then((s) => openServerPage(link.dataset.page, {
        job: String(job.id),
        ...(s.apiKey ? { key: s.apiKey } : {}),
      }));
    });
  });
  loadServerState();
});
