// Evidence explorer. Source text is rendered with textContent, never innerHTML.
const api = '/api/verified-memory';
const maxBytes = 2 * 1024 * 1024;
const byId = id => document.getElementById(id);
let viewVersion = 0;

function view() { return { path: project(), version: viewVersion }; }
function isCurrent(captured) {
  try { return captured.version === viewVersion && captured.path === project(); }
  catch { return false; }
}
function clearView() {
  viewVersion += 1;
  byId('evidence-sources').replaceChildren();
  byId('evidence-results').replaceChildren();
  byId('evidence-original').textContent = '';
  byId('evidence-original-label').textContent = 'Original source';
  byId('evidence-original-details').open = false;
}

async function request(path, options = {}) {
  const response = await fetch(api + path, {
    credentials: 'same-origin', ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.detail?.error?.message || body.detail?.message || 'The request could not be completed.');
    error.status = response.status;
    throw error;
  }
  return body.payload;
}

function project() {
  const value = byId('evidence-project').value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(value)) throw new Error('Use a project ID with letters, numbers, dots, dashes or underscores.');
  return '/projects/' + encodeURIComponent(value);
}

function status(message, error = false) {
  byId('evidence-status').textContent = message;
  byId('evidence-status').classList.toggle('evidence-error', error);
}

async function action(button, run) {
  button.disabled = true;
  try { await run(); } catch (error) { status(error.message, true); }
  finally { button.disabled = false; }
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function loadSources() {
  const captured = view();
  const list = byId('evidence-sources');
  list.replaceChildren();
  const history = byId('evidence-history').checked ? '?include_history=true' : '';
  const result = await request(captured.path + '/sources' + history);
  if (!isCurrent(captured)) return;
  for (const source of result.sources) {
    const card = element('div', undefined, 'evidence-source');
    const button = element('button', source.filename, 'memory-toolbar-btn');
    button.type = 'button';
    button.addEventListener('click', () => action(button, async () => {
      const full = await request(captured.path + '/sources/' + source.revision_id);
      if (!isCurrent(captured)) return;
      byId('evidence-original').textContent = full.text;
      byId('evidence-original-label').textContent = full.filename + ' · revision ' + full.revision_id.slice(0, 12);
      byId('evidence-original-details').open = true;
    }));
    card.append(button, element('span',
      (source.owner_approved ? 'Approved record' : 'Reference') +
      (source.canonical_role ? ' · ' + source.canonical_role.replace('_', ' ') : '') +
      ' · effective ' + new Date(source.effective_from).toLocaleString(), 'evidence-meta'));
    list.append(card);
  }
  if (!result.sources.length) list.append(element('p', 'No sources yet. Import a Markdown or text file.'));
}

document.addEventListener('DOMContentLoaded', () => {
  const panel = document.querySelector('[data-memory-panel="evidence"]');
  if (!panel) return;
  byId('evidence-project').addEventListener('input', () => { clearView(); status('Open the selected project to see its sources.'); });
  byId('evidence-open').addEventListener('click', event => action(event.currentTarget, async () => {
    const projectId = byId('evidence-project').value.trim();
    clearView();
    const captured = view();
    await request('/projects', { method: 'POST', body: JSON.stringify({ project_id: projectId }) });
    if (!isCurrent(captured)) return;
    await loadSources();
    if (!isCurrent(captured)) return;
    status('Project opened. Sources stay separate for each account and project.');
    document.dispatchEvent(new CustomEvent('evidence-project-opened', { detail: { projectId } }));
  }));
  document.querySelector('[data-memory-tab="evidence"]')?.addEventListener('click', async () => {
    try { await loadSources(); }
    catch (error) { status(error.status === 404 ? 'Open or create this project to start importing sources.' : error.message, error.status !== 404); }
  });
  byId('evidence-history').addEventListener('change', () => loadSources().catch(error => status(error.message, true)));
  byId('evidence-approved').addEventListener('change', event => {
    byId('evidence-role').disabled = !event.target.checked;
  });
  byId('evidence-import').addEventListener('click', event => action(event.currentTarget, async () => {
    const captured = view();
    const file = byId('evidence-file').files[0];
    if (!file) throw new Error('Choose a .md or .txt file first.');
    if (!/\.(md|txt)$/i.test(file.name) || file.size > maxBytes) throw new Error('Choose a Markdown or UTF-8 text file smaller than 2 MiB.');
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer()); }
    catch { throw new Error('The file must contain UTF-8 text.'); }
    const approved = byId('evidence-approved').checked;
    const body = {
      filename: file.name, text,
      authority: approved ? 'canonical' : 'reference', owner_approved: approved,
      canonical_role: approved ? (byId('evidence-role').value || null) : null,
    };
    if (!isCurrent(captured)) return;
    await request(captured.path + '/sources', { method: 'POST', body: JSON.stringify(body) });
    if (!isCurrent(captured)) return;
    await loadSources();
    if (!isCurrent(captured)) return;
    status('Source imported. Previous revisions remain available in history.');
  }));
  byId('evidence-query-form').addEventListener('submit', event => {
    event.preventDefault();
    action(byId('evidence-search'), async () => {
      const captured = view();
      const body = { question: byId('evidence-question').value };
      const date = byId('evidence-as-of').value;
      if (date) body.as_of = new Date(date).toISOString();
      const result = await request(captured.path + '/query', { method: 'POST', body: JSON.stringify(body) });
      if (!isCurrent(captured)) return;
      const output = byId('evidence-results');
      output.replaceChildren();
      for (const passage of result.passages) {
        const card = element('article', undefined, 'evidence-passage');
        card.append(element('h3', passage.source.filename + ' · lines ' + passage.line_start + '–' + passage.line_end));
        card.append(element('p', 'Source reference checked · claim support not evaluated', 'evidence-meta'));
        card.append(element('pre', passage.text));
        card.append(element('code', '[' + passage.citation_ref + ']'));
        output.append(card);
      }
      status(result.passages.length
        ? 'Showing source passages. Live upstream revisions have not been checked.'
        : 'No matching evidence within the current search and context budget. Try different wording or import the relevant source.');
    });
  });
  byId('evidence-preflight').addEventListener('click', event => action(event.currentTarget, async () => {
    const captured = view();
    const result = await request(captured.path + '/prepare-context', {
      method: 'POST', body: JSON.stringify({ question: byId('evidence-question').value || 'Current project context', context_budget_chars: 64000 }),
    });
    if (!isCurrent(captured)) return;
    status('Project context ready: ' + result.required_sources.length + ' approved records checked. Freshness refers to imported snapshots; live Drive revisions have not been checked.');
  }));
});
