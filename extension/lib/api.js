/* Acesso ao armazenamento local e à API do servidor SearchJob. */
(function (root) {
  "use strict";

  const DEFAULT_SETTINGS = { serverUrl: "", apiKey: "", overwrite: false };

  async function getSettings() {
    const { settings } = await browser.storage.local.get("settings");
    return Object.assign({}, DEFAULT_SETTINGS, settings);
  }

  async function getProfile() {
    const { profile } = await browser.storage.local.get("profile");
    return profile || {};
  }

  async function api(path, { method = "GET", body } = {}) {
    const settings = await getSettings();
    if (!settings.serverUrl) {
      throw new Error("Configure o endereço do servidor nas opções da extensão.");
    }
    let res;
    try {
      res = await fetch(settings.serverUrl.replace(/\/+$/, "") + path, {
        method,
        headers: { "Content-Type": "application/json", "X-API-Key": settings.apiKey },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (err) {
      throw new Error("Servidor SearchJob inacessível. Ele está ligado e na mesma rede?");
    }
    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.json()).detail;
      } catch (err) {
        detail = "";
      }
      const error = new Error(typeof detail === "string" && detail ? detail : `Erro ${res.status}`);
      error.status = res.status;
      throw error;
    }
    return res.json();
  }

  root.SJ = { DEFAULT_SETTINGS, getSettings, getProfile, api };
})(globalThis);
