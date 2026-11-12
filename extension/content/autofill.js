/*
 * Script injetado sob demanda (clique no popup) na página de candidatura.
 * Depende de lib/fields.js, injetado antes dele.
 *
 * Nada é enviado automaticamente: o script só preenche campos e destaca
 * o que fez. Quem revisa e clica em "Enviar" é sempre o usuário.
 */
(function () {
  "use strict";
  if (window.__searchjob) return;

  const F = window.SearchJobFields;
  const FILLED_STYLE = "2px solid #1d8a4e";
  const QUESTION_STYLE = "2px dashed #b7791f";
  const SKIP_TYPES = new Set([
    "hidden", "password", "file", "checkbox", "radio", "submit", "button", "reset", "image",
    "range", "color", "search",
  ]);

  function textOf(node) {
    return node ? (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  function isVisible(el) {
    if (el.disabled || el.readOnly) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none";
  }

  /** Texto "humano" do rótulo do campo (label, aria, legenda ou texto próximo). */
  function humanLabel(el) {
    const parts = [];
    if (el.labels) for (const l of el.labels) parts.push(textOf(l));
    const aria = el.getAttribute("aria-label");
    if (aria) parts.push(aria);
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      for (const id of labelledBy.split(/\s+/)) parts.push(textOf(document.getElementById(id)));
    }
    if (!parts.some(Boolean)) {
      // Formulários sem <label>: procura um texto curto no contêiner mais próximo.
      let node = el.parentElement;
      for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
        const clone = node.cloneNode(true);
        clone.querySelectorAll("input, textarea, select, option, button").forEach((n) => n.remove());
        const text = textOf(clone);
        if (text && text.length <= 300) {
          parts.push(text);
          break;
        }
      }
    }
    return parts.filter(Boolean).join(" ").slice(0, 300);
  }

  function describe(el) {
    return [
      humanLabel(el),
      el.getAttribute("placeholder"),
      el.getAttribute("title"),
      el.getAttribute("name"),
      el.id,
    ].filter(Boolean).join(" | ");
  }

  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    // Frameworks (React, Vue, Angular) escutam esses eventos para atualizar o estado.
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function fillSelect(el, value) {
    const idx = F.bestOptionIndex(Array.from(el.options), value);
    if (idx < 0) return false;
    el.selectedIndex = idx;
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function fill(profile, options) {
    const opts = Object.assign({ overwrite: false }, options);
    const result = { filled: [], questions: [], skipped: 0 };
    const elements = document.querySelectorAll("input, textarea, select");
    let questionSeq = 0;

    for (const el of elements) {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (el.tagName === "INPUT" && SKIP_TYPES.has(type)) continue;
      if (!isVisible(el)) continue;

      const key = F.matchField(describe(el), el.getAttribute("autocomplete"));
      const hasValue = el.tagName === "SELECT" ? el.selectedIndex > 0 : Boolean(el.value);

      if (!key) {
        const label = humanLabel(el);
        if (el.tagName !== "SELECT" && !hasValue && F.isLikelyQuestion(label, el.tagName)) {
          const id = `q${++questionSeq}`;
          el.dataset.searchjobQuestion = id;
          el.style.outline = QUESTION_STYLE;
          const maxLength = Number(el.getAttribute("maxlength")) || null;
          result.questions.push({ id, label, maxLength });
        }
        continue;
      }

      if (hasValue && !opts.overwrite) {
        result.skipped++;
        continue;
      }
      const value = F.profileValue(profile, key);
      if (!value) continue;

      const ok = el.tagName === "SELECT" ? fillSelect(el, value) : (setNativeValue(el, value), true);
      if (ok) {
        el.style.outline = FILLED_STYLE;
        result.filled.push(key);
      }
    }
    return result;
  }

  function setAnswer(questionId, text) {
    const el = document.querySelector(`[data-searchjob-question="${CSS.escape(questionId)}"]`);
    if (!el) return false;
    setNativeValue(el, text);
    el.style.outline = FILLED_STYLE;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }

  /** Texto da página, usado como contexto quando a vaga não está no banco. */
  function pageText(maxChars) {
    const main = document.querySelector("main, article, [role=main]") || document.body;
    return `${document.title}\n${textOf(main)}`.slice(0, maxChars || 6000);
  }

  window.__searchjob = { fill, setAnswer, pageText };
})();
