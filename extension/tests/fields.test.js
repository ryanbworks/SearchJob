"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const F = require("../lib/fields.js");

test("reconhece campos comuns em português e inglês", () => {
  const cases = [
    ["Nome completo *", "fullName"],
    ["Nome", "fullName"],
    ["candidate[first_name]", "firstName"],
    ["lastName", "lastName"],
    ["Sobrenome", "lastName"],
    ["E-mail", "email"],
    ["Celular (WhatsApp)", "phone"],
    ["Seu perfil do LinkedIn", "linkedin"],
    ["GitHub", "github"],
    ["Portfólio ou site pessoal", "portfolio"],
    ["CEP", "cep"],
    ["Cidade onde mora", "city"],
    ["UF", "state"],
    ["Pretensão salarial (R$)", "salary"],
    ["Instituição de ensino", "institution"],
    ["Nível de inglês", "english"],
    ["Fale um pouco sobre você", "summary"],
  ];
  for (const [label, expected] of cases) {
    assert.equal(F.matchField(label), expected, `"${label}" deveria ser ${expected}`);
  }
});

test("não confunde campos parecidos", () => {
  assert.equal(F.matchField("Nome da empresa atual"), null);
  assert.equal(F.matchField("Nome da mãe"), null);
  assert.equal(F.matchField("Estado civil"), null);
  assert.equal(F.matchField("Nome da instituição"), "institution");
});

test("atributo autocomplete tem prioridade", () => {
  assert.equal(F.matchField("campo1", "email"), "email");
  assert.equal(F.matchField("x", "section-a given-name"), "firstName");
  assert.equal(F.matchField("Nome", "off"), "fullName");
});

test("deriva nome e sobrenome do nome completo", () => {
  const profile = { fullName: "Maria Souza Lima" };
  assert.equal(F.profileValue(profile, "firstName"), "Maria");
  assert.equal(F.profileValue(profile, "lastName"), "Souza Lima");
  assert.equal(F.profileValue({ firstName: "Ana", lastName: "Reis" }, "fullName"), "Ana Reis");
  assert.equal(F.profileValue(profile, "salary"), "");
});

test("detecta perguntas abertas", () => {
  assert.ok(F.isLikelyQuestion("Por que você quer trabalhar conosco?", "INPUT"));
  assert.ok(F.isLikelyQuestion("Descreva uma experiência de atendimento", "TEXTAREA"));
  assert.ok(!F.isLikelyQuestion("Observações", "INPUT"));
});

test("escolhe a melhor opção de um select", () => {
  const options = [
    { text: "Selecione", value: "" },
    { text: "Ensino Médio Completo", value: "1" },
    { text: "Superior Incompleto", value: "2" },
    { text: "Superior Completo", value: "3" },
  ];
  assert.equal(F.bestOptionIndex(options, "superior incompleto"), 2);
  assert.equal(F.bestOptionIndex(options, "Doutorado"), -1);
});
