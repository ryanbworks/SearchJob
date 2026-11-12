"use strict";

const $ = (id) => document.getElementById(id);
const { PROFILE_FIELDS } = window.SearchJobFields;

function setStatus(el, text, kind) {
  el.textContent = text;
  el.className = `status ${kind || ""}`.trim();
}

/** Monta o formulário do perfil a partir da definição de campos (lib/fields.js). */
function buildProfileForm() {
  const container = $("profile-fields");
  const groups = new Map();
  for (const field of PROFILE_FIELDS) {
    if (!groups.has(field.group)) {
      const fieldset = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = field.group;
      const grid = document.createElement("div");
      grid.className = "grid";
      fieldset.append(legend, grid);
      container.appendChild(fieldset);
      groups.set(field.group, grid);
    }
    const wrapper = document.createElement("div");
    const label = document.createElement("label");
    label.htmlFor = `p-${field.key}`;
    label.textContent = field.label;
    const input = document.createElement(field.type === "textarea" ? "textarea" : "input");
    if (field.type !== "textarea") input.type = field.type;
    if (field.type === "textarea") wrapper.className = "full";
    input.id = `p-${field.key}`;
    input.dataset.key = field.key;
    if (field.placeholder) input.placeholder = field.placeholder;
    wrapper.append(label, input);
    groups.get(field.group).appendChild(wrapper);
  }
}

async function load() {
  const [profile, settings] = await Promise.all([SJ.getProfile(), SJ.getSettings()]);
  document.querySelectorAll("[data-key]").forEach((input) => {
    input.value = profile[input.dataset.key] || "";
  });
  $("serverUrl").value = settings.serverUrl;
  $("apiKey").value = settings.apiKey;
  $("overwrite").checked = Boolean(settings.overwrite);
}

/** Padrão de permissão para o host do servidor (portas não entram no padrão). */
function hostPattern(rawUrl) {
  const url = new URL(rawUrl);
  if (!/^https?:$/.test(url.protocol)) throw new Error("Use http:// ou https://");
  return `${url.protocol}//${url.hostname}/*`;
}

async function save(event) {
  event.preventDefault();
  const serverUrl = $("serverUrl").value.trim().replace(/\/+$/, "");
  let permission = Promise.resolve(true);
  if (serverUrl) {
    try {
      // Precisa ser chamado direto no clique (gesto do usuário), antes de qualquer await.
      permission = browser.permissions.request({ origins: [hostPattern(serverUrl)] });
    } catch (err) {
      setStatus($("save-status"), `Endereço inválido: ${err.message}`, "err");
      return;
    }
  }

  const profile = {};
  document.querySelectorAll("[data-key]").forEach((input) => {
    const value = input.value.trim();
    if (value) profile[input.dataset.key] = value;
  });
  const settings = {
    serverUrl,
    apiKey: $("apiKey").value.trim(),
    overwrite: $("overwrite").checked,
  };

  const granted = await permission;
  await browser.storage.local.set({ profile, settings });
  setStatus(
    $("save-status"),
    granted ? "Salvo!" : "Perfil salvo, mas sem permissão para acessar o servidor.",
    granted ? "ok" : "warn",
  );
}

async function testConnection() {
  setStatus($("test-status"), "Testando…");
  try {
    const health = await SJ.api("/health");
    await SJ.api("/api/jobs?limit=1");
    const llm = await SJ.api("/api/llm/status");
    const ia = llm.available ? `IA online (${llm.model})` : "IA offline: análises ficam pendentes";
    setStatus($("test-status"), `Conectado, v${health.version}. ${ia}.`, llm.available ? "ok" : "warn");
  } catch (err) {
    setStatus($("test-status"), `${err.message} (salve antes de testar)`, "err");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  buildProfileForm();
  load();
  $("form").addEventListener("submit", save);
  $("test-btn").addEventListener("click", testConnection);
});
