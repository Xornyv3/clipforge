/* ── ClipForge Web UI — Frontend Logic ─────────────────────────── */

// API base: empty = same origin (Render all-in-one), or set to backend URL
const API = window.__CLIPFORGE_API || '';
let pollTimer = null;

// ── Section navigation ──────────────────────────────────────────
function showSection(name) {
    for (const id of ['hero', 'create', 'jobs', 'detail']) {
        const show = (id === name) || (id === 'hero' && name === 'create');
        document.getElementById(id).classList.toggle('hidden', !show);
    }
    if (name === 'jobs') loadJobs();
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ── Submit new job ──────────────────────────────────────────────
async function submitJob(e) {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');

    // Validate: need URL or file
    const urlVal = document.getElementById('source_url').value.trim();
    const fileInput = document.getElementById('source_file');
    if (!urlVal && !fileInput.files.length) {
        alert('Please provide a YouTube URL or upload a video file.');
        return;
    }

    btn.disabled = true;
    btn.querySelector('.btn-text').classList.add('hidden');
    btn.querySelector('.btn-loading').classList.remove('hidden');

    const form = document.getElementById('jobForm');
    const fd = new FormData(form);

    // Handle checkboxes (FormData only includes checked ones)
    for (const cb of ['color_grade', 'subtitles', 'sub_bold', 'strip_commas']) {
        fd.set(cb, document.getElementById(cb).checked ? 'true' : 'false');
    }

    // If no file, remove the file field so the server gets source_url
    if (!fileInput.files.length) {
        fd.delete('source_file');
    } else {
        // If file uploaded, source_url becomes optional
        fd.set('source_url', '');
    }

    try {
        const res = await fetch(`${API}/api/jobs`, { method: 'POST', body: fd });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Job creation failed');
        }
        const job = await res.json();
        showJobDetail(job.job_id);
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.querySelector('.btn-text').classList.remove('hidden');
        btn.querySelector('.btn-loading').classList.add('hidden');
    }
}

// ── Load job list ───────────────────────────────────────────────
async function loadJobs() {
    const el = document.getElementById('jobList');
    el.innerHTML = '<p class="muted">Loading...</p>';

    try {
        const res = await fetch(`${API}/api/jobs`);
        const jobs = await res.json();

        if (!jobs.length) {
            el.innerHTML = '<p class="muted">No jobs yet. Create one above!</p>';
            return;
        }

        el.innerHTML = jobs.map(j => `
            <div class="job-item" onclick="showJobDetail('${j.job_id}')">
                <div class="job-item-left">
                    <span class="job-id">${j.job_id}</span>
                    <span class="job-meta">${j.num_clips} clips &bull; ${formatDate(j.created_at)}</span>
                </div>
                <span class="badge badge-${j.status}">${statusIcon(j.status)} ${j.status}</span>
            </div>
        `).join('');
    } catch (err) {
        el.innerHTML = `<p class="muted">Failed to load jobs: ${err.message}</p>`;
    }
}

// ── Show job detail ─────────────────────────────────────────────
async function showJobDetail(jobId) {
    showSection('detail');
    const el = document.getElementById('jobDetail');
    el.innerHTML = '<p class="muted"><span class="spinner"></span> Loading...</p>';

    try {
        const job = await fetchJob(jobId);
        renderJobDetail(job);

        // Poll if still processing
        if (!['completed', 'failed'].includes(job.status)) {
            pollTimer = setInterval(async () => {
                const updated = await fetchJob(jobId);
                renderJobDetail(updated);
                if (['completed', 'failed'].includes(updated.status)) {
                    clearInterval(pollTimer);
                    pollTimer = null;
                }
            }, 3000);
        }
    } catch (err) {
        el.innerHTML = `<div class="error-msg">Failed to load job: ${err.message}</div>`;
    }
}

async function fetchJob(jobId) {
    const res = await fetch(`${API}/api/jobs/${jobId}`);
    if (!res.ok) throw new Error('Job not found');
    return await res.json();
}

function renderJobDetail(job) {
    const el = document.getElementById('jobDetail');
    const progress = getProgressPercent(job.status);

    let clipsHtml = '';
    if (job.clips && job.clips.length) {
        clipsHtml = `
            <h3 style="margin-bottom:1rem">Generated Clips</h3>
            <div class="clip-grid">
                ${job.clips.map(c => `
                    <div class="clip-card">
                        <div class="clip-card-top">
                            <div>
                                <span class="clip-label">${c.label}</span>
                                <span class="clip-time">${c.start}s — ${c.end}s (${c.duration}s)</span>
                            </div>
                            <a href="${c.download_url}" class="btn-download" download>↓ Download</a>
                        </div>
                        <div class="clip-score">Score: ${c.score}</div>
                        <div class="clip-text">${c.text_preview}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    let errorHtml = '';
    if (job.status === 'failed' && job.message) {
        errorHtml = `<div class="error-msg">${job.message}</div>`;
    }

    el.innerHTML = `
        <div class="detail-header">
            <h2>Job ${job.job_id}</h2>
            <span class="badge badge-${job.status}">${statusIcon(job.status)} ${job.status}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
        <div class="detail-progress">${job.progress || ''}</div>
        ${errorHtml}
        ${clipsHtml}
        <div class="detail-actions">
            <span class="muted">Created: ${formatDate(job.created_at)}</span>
            ${job.completed_at ? `<span class="muted">Completed: ${formatDate(job.completed_at)}</span>` : ''}
            <button class="btn btn-danger" onclick="deleteJob('${job.job_id}')" style="margin-left:auto">Delete Job</button>
        </div>
    `;
}

// ── Delete job ──────────────────────────────────────────────────
async function deleteJob(jobId) {
    if (!confirm('Delete this job and all its clips?')) return;
    try {
        await fetch(`${API}/api/jobs/${jobId}`, { method: 'DELETE' });
        showSection('jobs');
    } catch (err) {
        alert('Delete failed: ' + err.message);
    }
}

// ── Helpers ─────────────────────────────────────────────────────
function statusIcon(status) {
    const icons = {
        pending: '⏳',
        downloading: '⬇️',
        transcribing: '🎙️',
        selecting: '🎯',
        rendering: '🎬',
        mixing_music: '🎵',
        completed: '✅',
        failed: '❌',
    };
    return icons[status] || '';
}

function getProgressPercent(status) {
    const map = {
        pending: 5,
        downloading: 15,
        transcribing: 35,
        selecting: 50,
        rendering: 75,
        mixing_music: 90,
        completed: 100,
        failed: 100,
    };
    return map[status] || 0;
}

function formatDate(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        return d.toLocaleString();
    } catch {
        return iso;
    }
}
