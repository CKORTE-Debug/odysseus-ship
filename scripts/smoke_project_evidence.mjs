// DOM integration only: no claims about browser layout or accessibility.
import fs from 'node:fs/promises';
const { Window } = await import(process.env.HAPPY_DOM_MODULE || 'happy-dom');
const origin = process.argv[2];
const window = new Window({ url: origin, settings: { disableJavaScriptFileLoading: true, disableCSSFileLoading: true } });
window.TextDecoder = TextDecoder;
window.document.write(await (await fetch(origin)).text());
for (const script of ['verified-memory.js', 'project-companion.js']) {
  window.eval(await fs.readFile(new URL('../static/js/' + script, import.meta.url), 'utf8'));
}
window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
const doc = window.document, id = name => doc.getElementById(name), passed = [];
const check = (condition, label) => { if (!condition) throw new Error(label); passed.push(label); };
async function wait(test, label) {
  for (let i = 0; i < 600; i++) { if (test()) return; await new Promise(resolve => setTimeout(resolve, 10)); }
  throw new Error('Timeout: ' + label + '; ' + id('evidence-status').textContent + '; ' + id('project-step-status').textContent);
}
async function upload(name, text, role) {
  const transfer = new window.DataTransfer();
  transfer.items.add(new window.File([text], name, { type: 'text/plain' }));
  id('evidence-file').files = transfer.files;
  id('evidence-approved').checked = Boolean(role); id('evidence-role').value = role || '';
  id('evidence-import').click(); await wait(() => !id('evidence-import').disabled, 'import');
  check(id('evidence-status').textContent.startsWith('Source imported'), 'import ' + name);
}
try {
  id('evidence-project').value = 'ui-smoke'; id('evidence-open').click();
  await wait(() => id('evidence-status').textContent.startsWith('Project opened'), 'create');
  check(true, 'create project');
  const original = '# Plan\nEvidence explorer is the first milestone.\n<img src=x onerror="window.sourceExecuted=true">';
  await upload('plan.md', original);
  id('evidence-question').value = 'evidence explorer';
  id('evidence-query-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await wait(() => id('evidence-results').querySelector('pre'), 'query');
  check(id('evidence-results').textContent.includes('first milestone'), 'query source passage');
  check(!id('evidence-results').querySelector('img') && !window.sourceExecuted, 'source markup stays literal');
  id('evidence-sources').querySelector('button').click();
  await wait(() => id('evidence-original').textContent === original, 'original');
  check(true, 'inspect exact original');
  await upload('procedure.md', 'Approved procedure: use evidence.', 'procedure');
  await upload('state.md', 'Current state: evidence explorer.', 'current_state');
  id('evidence-preflight').click();
  await wait(() => id('evidence-status').textContent.startsWith('Project context ready'), 'preflight');
  check(true, 'approved context preflight');
  id('project-step-enable').click();
  await wait(() => !id('project-step-run').disabled, 'enable local step');
  id('project-step-run').click();
  await wait(() => !id('project-step-review').disabled, 'local output');
  check(id('project-step-answer').textContent.includes('evidence explorer'), 'local output waits for review');
  check(!id('project-step-answer').querySelector('img') && !window.modelExecuted, 'model markup stays literal');
  id('project-step-sources').querySelector('button').click();
  await wait(() => id('evidence-original').textContent.startsWith('Approved'), 'output provenance');
  check(true, 'inspect output source');
  id('project-step-review').click();
  await wait(() => id('project-step-status').textContent.startsWith('Reviewed') && !id('project-step-refresh').disabled, 'review');
  check(id('project-step-review').disabled, 'record review decision');
  id('evidence-question').value = 'cancel me'; id('project-step-run').click();
  await wait(() => !id('project-step-cancel').disabled && id('project-step-status').textContent.includes('attempt 1/2'), 'running');
  id('project-step-cancel').click();
  await wait(() => !id('project-step-resume').disabled, 'pause');
  check(id('project-step-status').textContent.startsWith('Paused'), 'cancel persists pause');
  id('project-step-resume').click();
  await wait(() => !id('project-step-review').disabled, 'resume');
  check(id('project-step-status').textContent.includes('attempt 2/2'), 'explicit bounded resume');
  id('project-step-reject').click();
  await wait(() => id('project-step-status').textContent.startsWith('Output rejected'), 'reject');
  check(true, 'record rejection');
  const originalFetch = window.fetch.bind(window);
  let delayed = false, release;
  window.fetch = async (url, options) => {
    const result = await originalFetch(url, options);
    if (String(url).endsWith('/ui-smoke/query')) {
      delayed = true; await new Promise(resolve => { release = resolve; });
    }
    return result;
  };
  id('evidence-query-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await wait(() => delayed, 'delayed query');
  id('evidence-project').value = 'ui-second';
  id('evidence-project').dispatchEvent(new window.Event('input', { bubbles: true }));
  id('evidence-open').click();
  await wait(() => id('evidence-status').textContent.startsWith('Project opened'), 'second project');
  release(); await wait(() => !id('evidence-search').disabled, 'stale query ignored');
  check(!id('evidence-results').textContent && !id('evidence-original').textContent, 'ignore delayed prior-project query');
  check(!id('project-step-answer').textContent && !id('project-step-tasks').options.length, 'clear task output on project switch');
  console.log(JSON.stringify({ passed, count: passed.length, verification: 'DOM with real FastAPI/SQLite and fixture model; no rendered browser' }, null, 2));
} finally {
  await window.happyDOM.close();
}
