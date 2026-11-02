// Supervised local steps. No source/model output is inserted as HTML.
(() => {
  const node = id => document.getElementById(id);
  let selected = null;
  let timer = null;
  let generation = 0;
  let ready = false;
  let busy = false;
  const statuses = {
    queued: 'Waiting for the local model', running: 'Running locally', paused: 'Paused',
    failed: 'Step failed', review_required: 'Ready for review', reviewed: 'Reviewed', rejected: 'Output rejected',
  };
  function projectId() {
    const value = node('evidence-project').value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(value)) throw new Error('Open a valid project first.');
    return value;
  }
  function message(text, error = false) {
    node('project-step-status').textContent = text;
    node('project-step-status').classList.toggle('evidence-error', error);
  }
  async function request(project, path, body) {
    const response = await fetch('/api/project-companion/projects/' + encodeURIComponent(project) + path, {
      credentials: 'same-origin', method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message || 'The project step request could not be completed. Refresh and try again.');
    return result.payload;
  }
  function controls() {
    node('project-step-run').disabled = busy || !ready || !node('project-step-model').value;
    node('project-step-enable').disabled = busy || ready;
    node('project-step-cancel').disabled = busy || !selected || !(selected.live || ['running', 'queued'].includes(selected.status));
    node('project-step-resume').disabled = busy || !selected || selected.live || !['failed', 'paused', 'running', 'queued'].includes(selected.status) || selected.attempt >= 2;
    const reviewable = selected?.status === 'review_required' && !selected.live;
    node('project-step-review').disabled = busy || !reviewable;
    node('project-step-reject').disabled = busy || !reviewable;
  }
  function clear() {
    generation += 1;
    clearTimeout(timer);
    selected = null;
    ready = false;
    node('project-step-answer').textContent = '';
    node('project-step-sources').replaceChildren();
    node('project-step-tasks').replaceChildren();
    node('project-step-model').replaceChildren();
    controls();
  }
  function render(task, project) {
    selected = task;
    const interrupted = !task.live && ['running', 'queued'].includes(task.status);
    message((interrupted ? 'Interrupted — resume explicitly' : (statuses[task.status] || task.status)) +
      ' · attempt ' + (task.attempt || 0) + '/2' + (task.error_type ? ' · ' + task.error_type : ''));
    node('project-step-answer').textContent = task.answer || '';
    const sources = node('project-step-sources');
    sources.replaceChildren();
    for (const source of task.context_sources || []) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'memory-toolbar-btn';
      button.textContent = 'Inspect ' + source.filename;
      button.addEventListener('click', async () => {
        try {
          const response = await fetch('/api/verified-memory/projects/' + encodeURIComponent(project) + '/sources/' + source.revision_id, { credentials: 'same-origin' });
          const result = await response.json();
          if (!response.ok) throw new Error('The original source could not be opened.');
          if (project !== projectId()) return;
          node('evidence-original').textContent = result.payload.text;
          node('evidence-original-label').textContent = result.payload.filename + ' · revision ' + source.revision_id.slice(0, 12);
          node('evidence-original-details').open = true;
        } catch (error) { message(error.message, true); }
      });
      sources.append(button);
    }
    controls();
  }
  async function detail(id) {
    clearTimeout(timer);
    const project = projectId(), current = ++generation;
    const task = await request(project, '/tasks/' + encodeURIComponent(id));
    if (current !== generation || project !== projectId()) return;
    render(task, project);
    const panel = document.querySelector('[data-memory-panel="evidence"]');
    if (task.live && !panel.classList.contains('hidden')) {
      timer = setTimeout(() => detail(id).catch(error => message(error.message, true)), 750);
    }
  }
  async function refresh(preferred = selected?.task_id) {
    clearTimeout(timer);
    const project = projectId(), current = ++generation;
    const [state, available] = await Promise.all([request(project, '/tasks'), request(project, '/models')]);
    if (current !== generation || project !== projectId()) return;
    ready = state.ready;
    const models = node('project-step-model'), previous = models.value;
    models.replaceChildren();
    for (const model of available.models) {
      const option = document.createElement('option');
      option.value = JSON.stringify({ endpoint_id: model.endpoint_id, model: model.model });
      option.textContent = model.label; models.append(option);
    }
    if ([...models.options].some(option => option.value === previous)) models.value = previous;
    const tasks = node('project-step-tasks');
    tasks.replaceChildren();
    for (const task of state.tasks) {
      const option = document.createElement('option');
      option.value = task.task_id;
      option.textContent = (task.question || task.task_id).slice(0, 70) + ' · ' + (statuses[task.status] || task.status);
      tasks.append(option);
    }
    if ([...tasks.options].some(option => option.value === preferred)) tasks.value = preferred;
    if (tasks.value) await detail(tasks.value);
    else { selected = null; node('project-step-answer').textContent = ''; message('No project steps yet.'); }
    if (!available.models.length) message('Configure an enabled local chat model in Odysseus first.');
    else if (!ready) message('Enable local project steps, then run the question above.');
    controls();
  }
  async function act(operation) {
    busy = true; controls();
    try { await operation(); }
    catch (error) { message(error.message, true); }
    finally { busy = false; controls(); }
  }
  document.addEventListener('DOMContentLoaded', () => {
    if (!node('project-step-run')) return;
    node('evidence-project').addEventListener('input', () => { clear(); message('Open the selected project to see its steps.'); });
    document.addEventListener('evidence-project-opened', () => { clear(); refresh().catch(error => message(error.message, true)); });
    document.querySelector('[data-memory-tab="evidence"]')?.addEventListener('click', () => refresh().catch(error => message(error.message, true)));
    node('project-step-model').addEventListener('change', controls);
    node('project-step-tasks').addEventListener('change', event => detail(event.target.value).catch(error => message(error.message, true)));
    node('project-step-refresh').addEventListener('click', () => act(() => refresh()));
    node('project-step-enable').addEventListener('click', () => act(async () => { await request(projectId(), '/initialize', {}); await refresh(); }));
    node('project-step-run').addEventListener('click', () => act(async () => {
      const question = node('evidence-question').value.trim();
      if (!question) throw new Error('Enter a project question above first.');
      const model = JSON.parse(node('project-step-model').value);
      const task = await request(projectId(), '/tasks', { task_id: crypto.randomUUID(), question, ...model });
      await refresh(task.task_id);
    }));
    for (const [id, action, decision] of [
      ['project-step-cancel', 'cancel'], ['project-step-resume', 'resume'],
      ['project-step-review', 'review', 'acknowledged'], ['project-step-reject', 'review', 'rejected'],
    ]) {
      node(id).addEventListener('click', () => act(async () => {
        if (!selected) return;
        const task = await request(projectId(), '/tasks/' + encodeURIComponent(selected.task_id) + '/' + action,
          { expected_version: selected.checkpoint_version, ...(decision ? { decision } : {}) });
        await refresh(task.task_id);
      }));
    }
  });
})();
