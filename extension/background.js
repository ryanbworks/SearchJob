/*
 * Background: executa as chamadas demoradas à IA. Assim a resposta é
 * preenchida mesmo que o popup feche enquanto o modelo ainda está gerando.
 */
"use strict";

async function runInFrame(tabId, frameId, func, args) {
  const [res] = await browser.scripting.executeScript({
    target: { tabId, frameIds: [frameId] },
    func,
    args,
  });
  return res ? res.result : undefined;
}

async function answerQuestion(msg) {
  const { tabId, frameId, questionId, question, jobId, maxChars } = msg;
  const body = { question, max_chars: maxChars && maxChars >= 50 ? maxChars : null };
  if (jobId) {
    body.job_id = jobId;
  } else {
    body.page_context = await runInFrame(tabId, 0, (n) => window.__searchjob.pageText(n), [6000]);
  }
  const { answer } = await SJ.api("/api/answer", { method: "POST", body });
  const ok = await runInFrame(
    tabId,
    frameId,
    (id, text) => window.__searchjob.setAnswer(id, text),
    [questionId, answer],
  );
  return { ok: Boolean(ok), answer };
}

browser.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "answer") {
    return answerQuestion(msg).catch((err) => ({ ok: false, error: err.message }));
  }
  return undefined;
});
