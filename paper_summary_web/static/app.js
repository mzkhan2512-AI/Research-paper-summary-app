const $ = (id) => document.getElementById(id);
const input = $('fileInput');
const zone = $('dropzone');
const form = $('uploadForm');
const submit = $('submitBtn');
const MAX_BYTES = 12 * 1024 * 1024;
let chosen = null;
function error(message) { $('error').textContent = message; $('error').classList.remove('hidden'); }
function resetError() { $('error').textContent = ''; $('error').classList.add('hidden'); }
function chooseFile(file) {
  resetError(); $('result').classList.add('hidden'); chosen = null; submit.disabled = true;
  $('selected').classList.add('hidden');
  if (!file) return;
  if (!/\.(pdf|docx)$/i.test(file.name)) return error('Unsupported file type. Please choose a PDF (.pdf) or Word (.docx) file. PPT, TXT and DOC are not supported.');
  if (!file.size) return error('This file is empty. Please choose another document.');
  if (file.size > MAX_BYTES) return error('This file exceeds the 12 MB size limit.');
  chosen = file; $('selectedName').textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  $('selected').classList.remove('hidden'); submit.disabled = false;
}
zone.addEventListener('click', () => input.click());
zone.addEventListener('keydown', (event) => {if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); }});
input.addEventListener('change', () => chooseFile(input.files[0]));
$('clearFile').addEventListener('click', () => {input.value = ''; chooseFile(null);});
zone.addEventListener('dragover', (event) => { event.preventDefault(); zone.classList.add('dragging'); });
zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
zone.addEventListener('drop', (event) => { event.preventDefault(); zone.classList.remove('dragging'); chooseFile(event.dataTransfer.files[0]); });
form.addEventListener('submit', async (event) => {
  event.preventDefault(); if (!chosen) return error('Please select a PDF or DOCX document.');
  resetError(); submit.disabled = true; $('buttonText').textContent = 'Working…';
  $('progress').classList.remove('hidden'); $('result').classList.add('hidden');
  const body = new FormData(); body.append('file', chosen);
  try {
    const response = await fetch('/api/summarize', {method: 'POST', body});
    let data;
    try {data = await response.json();} catch {throw new Error('Unexpected server response. Please retry.');}
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Summarization failed. Please try again.');
    $('overview').textContent = data.summary;
    $('resultMeta').textContent = `${data.filename} · ${data.chunks} text chunk${data.chunks === 1 ? '' : 's'}`;
    $('sectionCount').textContent = `(${data.sections.length})`;
    const list = $('sectionsList'); list.replaceChildren();
    data.sections.forEach((text, i) => {const item = document.createElement('div');item.className = 'section-item';const heading = document.createElement('strong');heading.textContent = `Section ${i + 1}`;const p = document.createElement('p');p.textContent = text;item.append(heading,p);list.appendChild(item);});
    $('download').href = data.download_url; $('result').classList.remove('hidden');
    $('result').scrollIntoView({behavior: 'smooth', block: 'start'});
  } catch (err) { error(err.message || 'Could not complete the request.'); }
  finally {submit.disabled = !chosen; $('buttonText').textContent = 'Generate summary'; $('progress').classList.add('hidden');}
});
