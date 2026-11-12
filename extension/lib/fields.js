/*
 * Definição dos campos do perfil e regras para reconhecer cada campo em
 * formulários de candidatura (Gupy, Kenoby, Greenhouse, Lever, sites próprios…).
 *
 * Arquivo sem dependências de DOM: é usado pela página de opções, pelo script
 * injetado nas páginas e pelos testes em Node.
 */
(function (root) {
  "use strict";

  /**
   * key: chave no perfil salvo
   * label: rótulo exibido nas opções
   * type: tipo do input nas opções
   * autocomplete: valores do atributo HTML autocomplete que identificam o campo
   * match: padrões (texto já normalizado: minúsculo, sem acento)
   * exclude: padrões que impedem o casamento
   *
   * A ordem importa: campos mais específicos vêm antes dos genéricos.
   * Por segurança, documentos (CPF, RG) NÃO são armazenados nem preenchidos.
   */
  const PROFILE_FIELDS = [
    { key: "firstName", label: "Primeiro nome", type: "text", group: "Dados pessoais",
      autocomplete: ["given-name"],
      match: [/primeiro nome/, /\bfirst ?name\b/, /\bgiven name\b/] },
    { key: "lastName", label: "Sobrenome", type: "text", group: "Dados pessoais",
      autocomplete: ["family-name"],
      match: [/sobrenome/, /\blast ?name\b/, /\bfamily name\b/, /\bsurname\b/] },
    { key: "fullName", label: "Nome completo", type: "text", group: "Dados pessoais",
      autocomplete: ["name"],
      match: [/nome completo/, /\bfull ?name\b/, /\bnome\b/, /\bname\b/, /\bseu nome\b/],
      exclude: [/empresa/, /company/, /\bmae\b/, /\bpai\b/, /social/, /usuario/, /user ?name/,
        /institui/, /curso/, /cartao/, /referen/, /contato de emergencia/, /recrutador/] },
    { key: "email", label: "E-mail", type: "email", group: "Dados pessoais",
      autocomplete: ["email"],
      match: [/\be ?mail\b/] },
    { key: "phone", label: "Celular / WhatsApp", type: "tel", group: "Dados pessoais",
      autocomplete: ["tel", "tel-national", "mobile"],
      match: [/telefone/, /celular/, /whats/, /\bphone\b/, /\bmobile\b/, /\bfone\b/],
      exclude: [/\bddd\b/, /emergencia/, /recado/] },
    { key: "cep", label: "CEP", type: "text", group: "Endereço",
      autocomplete: ["postal-code"],
      match: [/\bcep\b/, /postal/, /\bzip\b/] },
    { key: "city", label: "Cidade", type: "text", group: "Endereço",
      autocomplete: ["address-level2"],
      match: [/cidade/, /\bcity\b/, /municipio/] },
    { key: "state", label: "Estado (UF)", type: "text", group: "Endereço",
      autocomplete: ["address-level1"],
      match: [/\bestado\b/, /\buf\b/, /\bstate\b/],
      exclude: [/civil/, /marital/] },
    { key: "linkedin", label: "LinkedIn (URL)", type: "url", group: "Links",
      match: [/linkedin/] },
    { key: "github", label: "GitHub (URL)", type: "url", group: "Links",
      match: [/github/] },
    { key: "portfolio", label: "Portfólio / site", type: "url", group: "Links",
      autocomplete: ["url"],
      match: [/portfolio/, /site pessoal/, /\bwebsite\b/, /personal site/, /\bsite\b/],
      exclude: [/linkedin/, /github/] },
    { key: "education", label: "Escolaridade", type: "text", group: "Formação",
      placeholder: "Ex.: Superior incompleto (cursando)",
      match: [/escolaridade/, /grau de (instrucao|escolaridade)/, /nivel de (ensino|formacao)/,
        /education level/, /formacao academica/] },
    { key: "course", label: "Curso", type: "text", group: "Formação",
      match: [/\bcurso\b/, /\bcourse\b/, /area de formacao/, /\bmajor\b/],
      exclude: [/nivel/, /institui/, /conclus/] },
    { key: "institution", label: "Instituição de ensino", type: "text", group: "Formação",
      match: [/institui/, /faculdade/, /universidade/, /university/, /\bschool\b/, /\bescola\b/] },
    { key: "graduation", label: "Previsão de conclusão", type: "text", group: "Formação",
      placeholder: "Ex.: 12/2029",
      match: [/conclusao/, /formatura/, /graduation/] },
    { key: "english", label: "Nível de inglês", type: "text", group: "Formação",
      placeholder: "Ex.: Intermediário",
      match: [/ingles/, /\benglish\b/] },
    { key: "salary", label: "Pretensão salarial", type: "text", group: "Preferências",
      placeholder: "Ex.: 2200",
      match: [/pretens/, /salari/, /salary/, /remunera/] },
    { key: "availability", label: "Disponibilidade", type: "text", group: "Preferências",
      placeholder: "Ex.: Imediata",
      match: [/disponibilidade/, /availability/, /inicio imediato/, /quando (pode|poderia) comecar/] },
    { key: "summary", label: "Resumo profissional (sobre você)", type: "textarea",
      group: "Preferências",
      match: [/sobre voce/, /resumo profissional/, /apresente-se/, /fale (um pouco )?sobre (voce|si)/,
        /about (you|yourself)/, /cover letter/, /carta de apresentacao/] },
  ];

  function normalize(text) {
    return String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[_\-.[\]:*()]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  /**
   * Descobre qual campo do perfil corresponde a um input.
   * @param {string} description texto agregado (label, placeholder, name, id…)
   * @param {string} [autocomplete] atributo autocomplete do input
   * @returns {string|null} chave do perfil
   */
  function matchField(description, autocomplete) {
    const ac = String(autocomplete || "").toLowerCase().trim().split(/\s+/).pop();
    if (ac && ac !== "on" && ac !== "off") {
      const byAc = PROFILE_FIELDS.find((f) => (f.autocomplete || []).includes(ac));
      if (byAc) return byAc.key;
    }
    // Considera também a versão com camelCase separado (firstName -> first name),
    // sem perder a original (LinkedIn continua "linkedin").
    const raw = String(description || "");
    const split = raw.replace(/([a-z])([A-Z])/g, "$1 $2");
    const text = normalize(split === raw ? raw : `${raw} ${split}`);
    if (!text) return null;
    for (const field of PROFILE_FIELDS) {
      if ((field.exclude || []).some((re) => re.test(text))) continue;
      if (field.match.some((re) => re.test(text))) return field.key;
    }
    return null;
  }

  /** Um campo não reconhecido parece uma pergunta aberta para a IA responder? */
  function isLikelyQuestion(label, tagName) {
    const text = String(label || "").trim();
    if (text.length < 12) return false;
    if (String(tagName).toUpperCase() === "TEXTAREA") return true;
    return text.includes("?") || /^(descreva|conte|explique|por que|porque|qual|como)\b/i.test(text);
  }

  /** Valor a preencher para uma chave, com derivação de nome/sobrenome. */
  function profileValue(profile, key) {
    const p = profile || {};
    const direct = String(p[key] || "").trim();
    if (direct) return direct;
    const parts = String(p.fullName || "").trim().split(/\s+/).filter(Boolean);
    if (key === "firstName") return parts[0] || "";
    if (key === "lastName") return parts.slice(1).join(" ");
    if (key === "fullName") {
      return [p.firstName, p.lastName].filter(Boolean).join(" ").trim();
    }
    return "";
  }

  /** Escolhe a melhor opção de um <select> para um valor do perfil. */
  function bestOptionIndex(options, value) {
    const wanted = normalize(value);
    if (!wanted) return -1;
    let best = -1;
    let bestScore = 0;
    options.forEach((opt, i) => {
      const text = normalize(opt.text || opt.value);
      if (!text) return;
      let score = 0;
      if (text === wanted) score = 3;
      else if (text.startsWith(wanted) || wanted.startsWith(text)) score = 2;
      else if (text.length >= 3 && (text.includes(wanted) || wanted.includes(text))) score = 1;
      if (score > bestScore) {
        best = i;
        bestScore = score;
      }
    });
    return best;
  }

  const api = { PROFILE_FIELDS, normalize, matchField, isLikelyQuestion, profileValue, bestOptionIndex };
  root.SearchJobFields = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
