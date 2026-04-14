/* =====================================================================
   Job Hunt — SPA controller
   ===================================================================== */

// ── State ─────────────────────────────────────────────────────────────
const state = {
  roles: [],
  resumeId: null,
  currentSearchId: null,
  currentPage: 1,
  totalPages: 1,
  sortBy: "fit_score",
  filterPortal: "",
  filterExperience: "",
  allJobs: [],          // flat cache for client-side filter
  scorePollers: {},     // jobId → intervalId
};

// ── Helpers ───────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const scoreClass = s => s >= 75 ? "badge-score-high" : s >= 50 ? "badge-score-mid" : "badge-score-low";
const scoreBadge = s => s == null
  ? `<span class="score-loading"></span>`
  : `<span class="badge ${scoreClass(s)} rounded-pill">${s}%</span>`;
const portalBadge = p => `<span class="portal-badge">${p}</span>`;

function showToast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3 shadow`;
  el.style.zIndex = 9999;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Tabs ──────────────────────────────────────────────────────────────
document.querySelectorAll("[data-tab]").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    switchTab(link.dataset.tab);
  });
});

function switchTab(name) {
  document.querySelectorAll(".tab-content").forEach(t => t.classList.add("d-none"));
  document.querySelectorAll("[data-tab]").forEach(l => l.classList.remove("active"));
  $(`tab-${name}`).classList.remove("d-none");
  document.querySelector(`[data-tab="${name}"]`).classList.add("active");

  if (name === "saved") loadSaved();
  if (name === "history") loadHistory();
  if (name === "autohunt") ahLoadProfile();
}

// ── Roles tag input ───────────────────────────────────────────────────
function renderRoles() {
  const c = $("rolesContainer");
  c.innerHTML = state.roles.map((r, i) =>
    `<span class="badge bg-primary d-flex align-items-center gap-1">
      ${r}
      <button class="btn-close btn-close-white btn-sm ms-1" data-idx="${i}" style="font-size:.6rem"></button>
    </span>`
  ).join("");
  c.querySelectorAll(".btn-close").forEach(b =>
    b.addEventListener("click", () => {
      state.roles.splice(+b.dataset.idx, 1);
      renderRoles();
      updateFindBtn();
    })
  );
}

$("addRoleBtn").addEventListener("click", addRole);
$("roleInput").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addRole(); } });

function addRole() {
  const val = $("roleInput").value.trim();
  if (val && !state.roles.includes(val)) {
    state.roles.push(val);
    $("roleInput").value = "";
    renderRoles();
    updateFindBtn();
  }
}

// ── Max results slider ────────────────────────────────────────────────
$("maxResults").addEventListener("input", () => {
  $("maxResultsLabel").textContent = $("maxResults").value;
});

// ── Resume upload ─────────────────────────────────────────────────────
const dropZone = $("dropZone");
const fileInput = $("resumeFile");

dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) uploadResume(fileInput.files[0]);
});

["dragover", "dragenter"].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add("drag-over"); })
);
["dragleave", "drop"].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove("drag-over"); })
);
dropZone.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (file) uploadResume(file);
});

$("replaceResumeBtn").addEventListener("click", () => fileInput.click());
$("downloadResumeBtn").addEventListener("click", () => {
  window.location.href = "/api/resume/download";
});

async function uploadResume(file) {
  $("uploadProgress").classList.remove("d-none");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/resume", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed");
    state.resumeId = data.id;
    $("resumeStatus").innerHTML =
      `<i class="bi bi-check-circle-fill text-success me-1"></i><strong>${data.filename}</strong>`;
    $("downloadResumeBtn").disabled = false;
    updateFindBtn();
    showToast("Resume uploaded successfully", "success");
  } catch (err) {
    showToast(err.message, "danger");
  } finally {
    $("uploadProgress").classList.add("d-none");
  }
}

// ── Portals ───────────────────────────────────────────────────────────
async function loadPortals() {
  const res = await fetch("/api/portals");
  const portals = await res.json();
  const container = $("portalCheckboxes");
  container.innerHTML = portals.map(p =>
    `<div class="form-check">
      <input class="form-check-input portal-check" type="checkbox" value="${p.key}" id="p_${p.key}" ${p.enabled ? "checked" : ""} />
      <label class="form-check-label small" for="p_${p.key}">${p.label}</label>
    </div>`
  ).join("");

  // Populate results filter
  const sel = $("filterPortal");
  portals.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.key;
    opt.textContent = p.label;
    sel.appendChild(opt);
  });
}

$("selectAllPortals").addEventListener("click", e => {
  e.preventDefault();
  document.querySelectorAll(".portal-check").forEach(c => c.checked = true);
});
$("deselectAllPortals").addEventListener("click", e => {
  e.preventDefault();
  document.querySelectorAll(".portal-check").forEach(c => c.checked = false);
});

// ── Find button ───────────────────────────────────────────────────────
function updateFindBtn() {
  $("findBtn").disabled = !(state.roles.length > 0 && state.resumeId);
}

$("findBtn").addEventListener("click", startSearch);

async function startSearch() {
  const portals = [...document.querySelectorAll(".portal-check:checked")].map(c => c.value);
  if (!portals.length) { showToast("Select at least one portal", "warning"); return; }

  const empTypes = [...document.querySelectorAll(".emp-type:checked")].map(c => c.value);

  const payload = {
    roles: state.roles,
    location: $("location").value.trim(),
    country: $("country").value,
    remote_only: $("remoteOnly").checked,
    experience: $("experience").value,
    employment_type: empTypes,
    date_posted: $("datePosted").value,
    salary_min: $("salaryMin").value ? +$("salaryMin").value : null,
    salary_currency: $("salaryCurrency").value,
    max_results: +$("maxResults").value,
    portals,
  };

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Search failed");

    state.currentSearchId = data.search_id;
    state.allJobs = [];
    state.currentPage = 1;

    showProgressSection(portals);
    switchTab("results");
    openSSEStream(data.search_id, portals);
    $("findBtn").disabled = true;
  } catch (err) {
    showToast(err.message, "danger");
  }
}

// ── Progress bars ─────────────────────────────────────────────────────
function showProgressSection(portals) {
  const section = $("progressSection");
  section.classList.remove("d-none");

  const container = $("portalProgressBars");
  container.innerHTML = portals.map(p =>
    `<div class="portal-progress-item d-flex align-items-center gap-2" id="pp_${p}">
      <span class="label text-truncate">${p}</span>
      <div class="progress flex-grow-1" style="height:10px">
        <div class="progress-bar progress-bar-striped progress-bar-animated bg-info"
             id="ppbar_${p}" style="width:100%"></div>
      </div>
      <span class="small text-muted" id="ppcnt_${p}"></span>
    </div>`
  ).join("");
}

function markPortalDone(portal, status, count) {
  const bar = $(`ppbar_${portal}`);
  const cnt = $(`ppcnt_${portal}`);
  if (!bar) return;
  bar.classList.remove("progress-bar-striped", "progress-bar-animated", "bg-info");
  if (status === "done") {
    bar.classList.add("bg-success");
    if (cnt) cnt.textContent = `${count} jobs`;
  } else {
    bar.classList.add("bg-danger");
    if (cnt) cnt.textContent = "error";
  }
  bar.style.width = "100%";
}

// ── SSE stream ────────────────────────────────────────────────────────
function openSSEStream(searchId, portals) {
  const evtSource = new EventSource(`/api/search/${searchId}/stream`);

  evtSource.addEventListener("portal_done", e => {
    const d = JSON.parse(e.data);
    markPortalDone(d.portal, d.status, d.count);
  });

  evtSource.addEventListener("job_added", e => {
    const d = JSON.parse(e.data);
    // Fetch and display the job row immediately
    appendJobRow(d);
    $("resultsCount").textContent = ++state.allJobs.length;
  });

  evtSource.addEventListener("status", e => {
    const d = JSON.parse(e.data);
    if (d.status === "done") {
      showToast(`Search complete — ${d.total} jobs found`, "success");
      $("findBtn").disabled = false;
      loadResultsPage();   // full refresh with pagination
    }
  });

  evtSource.addEventListener("error", e => {
    const d = JSON.parse(e.data);
    showToast(`Search error: ${d.message}`, "danger");
    evtSource.close();
    $("findBtn").disabled = false;
  });

  evtSource.addEventListener("__done__", () => evtSource.close());
}

// ── Quick-append a row during streaming ──────────────────────────────
function appendJobRow(d) {
  // d = { job_id, title, company, fit_score }
  const tbody = $("resultsBody");
  const idx = state.allJobs.length + 1;
  state.allJobs.push(d);

  const tr = document.createElement("tr");
  tr.id = `row_${d.job_id}`;
  tr.innerHTML = `
    <td>${idx}</td>
    <td>${escHtml(d.company)}</td>
    <td>${escHtml(d.title)}</td>
    <td>—</td>
    <td id="score_${d.job_id}">${scoreBadge(d.fit_score)}</td>
    <td><span class="text-muted small">Loading…</span></td>
    <td>—</td>
    <td><button class="btn btn-sm btn-outline-warning star-btn" data-id="${d.job_id}"><i class="bi bi-star"></i></button></td>
  `;
  tbody.appendChild(tr);
  bindStarBtn(tr.querySelector(".star-btn"));
  startScorePoller(d.job_id);
}

// Poll for Claude score update
function startScorePoller(jobId) {
  if (state.scorePollers[jobId]) return;
  const interval = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}/score`);
    const data = await res.json();
    if (data.fit_rationale) {
      clearInterval(interval);
      delete state.scorePollers[jobId];
      const cell = $(`score_${jobId}`);
      if (cell) cell.innerHTML = scoreBadge(data.fit_score);
    }
  }, 3000);
  state.scorePollers[jobId] = interval;
}

// ── Full paginated results load ───────────────────────────────────────
async function loadResultsPage() {
  if (!state.currentSearchId) return;

  const params = new URLSearchParams({
    page: state.currentPage,
    per_page: 25,
    sort: state.sortBy,
  });

  const res = await fetch(`/api/search/${state.currentSearchId}/results?${params}`);
  const data = await res.json();

  state.totalPages = data.pages;
  renderResultsTable(data.jobs, data.total);
}

function renderResultsTable(jobs, total) {
  const tbody = $("resultsBody");
  tbody.innerHTML = "";

  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No results yet.</td></tr>`;
    $("resultsSummary").textContent = "";
    return;
  }

  const offset = (state.currentPage - 1) * 25;
  jobs.forEach((job, i) => {
    const tr = document.createElement("tr");
    tr.id = `row_${job.id}`;
    const excerpt = (job.description || "").replace(/<[^>]+>/g, "").slice(0, 180);

    tr.innerHTML = `
      <td>${offset + i + 1}</td>
      <td>
        <div class="fw-semibold">${escHtml(job.company)}</div>
        ${portalBadge(job.portal)}
      </td>
      <td>${escHtml(job.title)}</td>
      <td><span class="badge bg-secondary">${job.experience || "—"}</span></td>
      <td id="score_${job.id}">
        ${scoreBadge(job.fit_score)}
        ${job.fit_rationale ? `<div class="small text-muted mt-1" style="max-width:160px">${escHtml(job.fit_rationale)}</div>` : ""}
      </td>
      <td>
        <div class="desc-excerpt">${escHtml(excerpt)}</div>
        <a href="#" class="small read-more-link" data-id="${job.id}">Read more</a>
      </td>
      <td><a href="${escHtml(job.url)}" target="_blank" class="btn btn-sm btn-outline-primary">Apply <i class="bi bi-box-arrow-up-right"></i></a></td>
      <td><button class="btn btn-sm ${job.saved ? "btn-warning" : "btn-outline-warning"} star-btn" data-id="${job.id}"><i class="bi bi-star${job.saved ? "-fill" : ""}"></i></button></td>
    `;
    tbody.appendChild(tr);

    tr.querySelector(".read-more-link").addEventListener("click", e => {
      e.preventDefault();
      openJdModal(job);
    });
    bindStarBtn(tr.querySelector(".star-btn"));
    if (!job.fit_rationale) startScorePoller(job.id);
  });

  $("resultsSummary").textContent = `${total} results`;
  $("resultsCount").textContent = total;
  $("pageInfo").textContent = `Page ${state.currentPage} of ${state.totalPages}`;
  $("prevPage").disabled = state.currentPage <= 1;
  $("nextPage").disabled = state.currentPage >= state.totalPages;
}

$("prevPage").addEventListener("click", () => { state.currentPage--; loadResultsPage(); });
$("nextPage").addEventListener("click", () => { state.currentPage++; loadResultsPage(); });

$("sortBy").addEventListener("change", () => {
  state.sortBy = $("sortBy").value;
  state.currentPage = 1;
  loadResultsPage();
});

// ── JD Modal ──────────────────────────────────────────────────────────
function openJdModal(job) {
  $("jdModalTitle").textContent = `${job.title} — ${job.company}`;
  $("jdModalBody").innerHTML = `
    <p class="text-muted small mb-3">${portalBadge(job.portal)} ${job.location || ""} ${job.salary_text ? "· " + job.salary_text : ""}</p>
    <div>${job.description ? job.description.replace(/\n/g, "<br>") : "<em>No description available</em>"}</div>
    ${job.fit_rationale ? `<div class="alert alert-info mt-3 small"><strong>AI fit note:</strong> ${escHtml(job.fit_rationale)}</div>` : ""}
  `;
  $("jdModalApply").href = job.url;
  bootstrap.Modal.getOrCreateInstance($("jdModal")).show();
}

// ── Star / save ───────────────────────────────────────────────────────
function bindStarBtn(btn) {
  btn.addEventListener("click", async () => {
    const jobId = btn.dataset.id;
    const res = await fetch(`/api/jobs/${jobId}/save`, { method: "POST" });
    const data = await res.json();
    btn.className = `btn btn-sm ${data.saved ? "btn-warning" : "btn-outline-warning"} star-btn`;
    btn.innerHTML = `<i class="bi bi-star${data.saved ? "-fill" : ""}"></i>`;
    const cnt = parseInt($("savedCount").textContent, 10) || 0;
    $("savedCount").textContent = data.saved ? cnt + 1 : Math.max(0, cnt - 1);
  });
}

// ── Saved jobs tab ────────────────────────────────────────────────────
async function loadSaved() {
  const res = await fetch("/api/saved");
  const jobs = await res.json();
  const tbody = $("savedBody");
  $("savedEmpty").classList.toggle("d-none", jobs.length > 0);

  if (!jobs.length) { tbody.innerHTML = ""; return; }

  tbody.innerHTML = jobs.map(j => `
    <tr>
      <td>${escHtml(j.company)}</td>
      <td>${escHtml(j.title)}</td>
      <td>${portalBadge(j.portal)}</td>
      <td>${scoreBadge(j.fit_score)}</td>
      <td><a href="${escHtml(j.url)}" target="_blank" class="btn btn-sm btn-outline-primary">Apply</a></td>
      <td><button class="btn btn-sm btn-warning star-btn" data-id="${j.id}"><i class="bi bi-star-fill"></i></button></td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".star-btn").forEach(bindStarBtn);
  $("savedCount").textContent = jobs.length;
}

// ── History tab ───────────────────────────────────────────────────────
async function loadHistory() {
  const res = await fetch("/api/history");
  const searches = await res.json();
  const list = $("historyList");
  $("historyEmpty").classList.toggle("d-none", searches.length > 0);

  if (!searches.length) { list.innerHTML = ""; return; }

  list.innerHTML = searches.map(s => `
    <div class="card history-card mb-3">
      <div class="card-body d-flex justify-content-between align-items-start">
        <div>
          <h6 class="mb-1">${s.roles.join(", ")}</h6>
          <div class="text-muted small">
            ${s.location || "Any location"} · ${s.experience || "Any experience"} · ${s.job_count} jobs found
          </div>
          <div class="text-muted small">${new Date(s.created_at).toLocaleString()}</div>
        </div>
        <button class="btn btn-sm btn-outline-primary re-run-btn" data-search='${escAttr(JSON.stringify(s))}'>
          <i class="bi bi-arrow-clockwise me-1"></i>Re-run
        </button>
      </div>
    </div>
  `).join("");

  list.querySelectorAll(".re-run-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const s = JSON.parse(btn.dataset.search);
      prefillSearch(s);
      switchTab("search");
    });
  });
}

function prefillSearch(s) {
  state.roles = s.roles || [];
  renderRoles();
  $("location").value = s.location || "";
  $("country").value = s.country || "US";
  $("remoteOnly").checked = s.remote_only;
  $("experience").value = s.experience || "";
  $("datePosted").value = s.date_posted || "any";
  $("salaryMin").value = s.salary_min || "";
  $("salaryCurrency").value = s.salary_currency || "USD";
  $("maxResults").value = s.max_results || 50;
  $("maxResultsLabel").textContent = s.max_results || 50;

  const empSet = new Set(s.employment_type || []);
  document.querySelectorAll(".emp-type").forEach(c => c.checked = empSet.has(c.value));

  const portalSet = new Set(s.portals || []);
  document.querySelectorAll(".portal-check").forEach(c => c.checked = portalSet.has(c.value));

  updateFindBtn();
}

// ── AutoHunt module ───────────────────────────────────────────────────────────
const ahState = { skills: [], searchId: null, currentPage: 1, totalPages: 1 };

function ahRenderSkills() {
  const c = $("ahSkillsContainer");
  c.innerHTML = ahState.skills.map((s, i) =>
    `<span class="badge bg-primary d-flex align-items-center gap-1">
      ${escHtml(s)}
      <button class="btn-close btn-close-white btn-sm ms-1" data-idx="${i}" style="font-size:.6rem"></button>
    </span>`
  ).join("");
  c.querySelectorAll(".btn-close").forEach(b =>
    b.addEventListener("click", () => {
      ahState.skills.splice(+b.dataset.idx, 1);
      ahRenderSkills();
      ahSaveProfile();
    })
  );
}

async function ahLoadProfile() {
  try {
    const res = await fetch("/api/autohunt/profile");
    const data = await res.json();
    ahState.skills = data.skills || [];
    ahRenderSkills();
  } catch (_) {}
}

async function ahSaveProfile() {
  try {
    await fetch("/api/autohunt/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skills: ahState.skills }),
    });
  } catch (_) {}
}

function ahAddSkill() {
  const val = $("ahSkillInput").value.trim();
  if (val && !ahState.skills.includes(val)) {
    ahState.skills.push(val);
    $("ahSkillInput").value = "";
    ahRenderSkills();
    ahSaveProfile();
  }
}

function ahSetupPortalProgress(portals) {
  const container = $("ahPortalProgressBars");
  container.innerHTML = portals.map(p =>
    `<div class="portal-progress-item d-flex align-items-center gap-2" id="ahpp_${p}">
      <span class="label text-truncate">${p}</span>
      <div class="progress flex-grow-1" style="height:10px">
        <div class="progress-bar progress-bar-striped progress-bar-animated bg-info"
             id="ahppbar_${p}" style="width:100%"></div>
      </div>
      <span class="small text-muted" id="ahppcnt_${p}"></span>
    </div>`
  ).join("");
}

function ahMarkPortalDone(portal, status, count) {
  const bar = $(`ahppbar_${portal}`);
  const cnt = $(`ahppcnt_${portal}`);
  if (!bar) return;
  bar.classList.remove("progress-bar-striped", "progress-bar-animated", "bg-info");
  if (status === "done") {
    bar.classList.add("bg-success");
    if (cnt) cnt.textContent = `${count} jobs`;
  } else {
    bar.classList.add("bg-danger");
    if (cnt) cnt.textContent = "error";
  }
}

function ahOpenSSE(searchId) {
  const evtSource = new EventSource(`/api/search/${searchId}/stream`);

  evtSource.addEventListener("portal_done", e => {
    const d = JSON.parse(e.data);
    ahMarkPortalDone(d.portal, d.status, d.count);
  });

  evtSource.addEventListener("status", e => {
    const d = JSON.parse(e.data);
    if (d.status === "done") {
      showToast(`AutoHunt complete — ${d.total} jobs found`, "success");
      $("ahHuntBtn").disabled = false;
      $("ahResultsSection").classList.remove("d-none");
      ahLoadPage(1);
    }
  });

  evtSource.addEventListener("error", e => {
    const d = JSON.parse(e.data);
    showToast(`AutoHunt error: ${d.message}`, "danger");
    evtSource.close();
    $("ahHuntBtn").disabled = false;
  });

  evtSource.addEventListener("__done__", () => evtSource.close());
}

async function ahLoadPage(page) {
  if (!ahState.searchId) return;
  ahState.currentPage = page;

  const params = new URLSearchParams({
    page,
    per_page: 25,
    sort: "fit_score",
    exclude_filtered: "1",
  });

  const res = await fetch(`/api/search/${ahState.searchId}/results?${params}`);
  const data = await res.json();

  ahState.totalPages = data.pages;

  const tbody = $("ahResultsBody");
  tbody.innerHTML = "";

  if (!data.jobs.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No results found.</td></tr>`;
    $("ahResultsSummary").textContent = "";
    return;
  }

  data.jobs.forEach(job => {
    const tr = document.createElement("tr");
    tr.id = `ahrow_${job.id}`;
    const excerpt = (job.description || "").replace(/<[^>]+>/g, "").slice(0, 200);

    tr.innerHTML = `
      <td>
        <div class="fw-semibold">${escHtml(job.company)}</div>
        ${portalBadge(job.portal)}
      </td>
      <td>${escHtml(job.title)}</td>
      <td><span class="badge bg-secondary">${job.experience || "—"}</span></td>
      <td>
        <div class="desc-excerpt">${escHtml(excerpt)}</div>
        <a href="#" class="small read-more-link" data-id="${job.id}">Read more</a>
      </td>
      <td><a href="${escHtml(job.url)}" target="_blank" class="btn btn-sm btn-outline-primary">Apply <i class="bi bi-box-arrow-up-right"></i></a></td>
    `;
    tbody.appendChild(tr);

    tr.querySelector(".read-more-link").addEventListener("click", e => {
      e.preventDefault();
      openJdModal(job);
    });
  });

  $("ahResultsSummary").textContent = `${data.total} results`;
  $("ahPageInfo").textContent = `Page ${page} of ${ahState.totalPages}`;
  $("ahPrevBtn").disabled = page <= 1;
  $("ahNextBtn").disabled = page >= ahState.totalPages;
}

async function ahStartHunt() {
  if (!ahState.skills.length) {
    showToast("Add at least one skill before hunting", "warning");
    return;
  }

  $("ahHuntBtn").disabled = true;
  $("ahResultsSection").classList.add("d-none");
  $("ahResultsBody").innerHTML = "";

  try {
    const res = await fetch("/api/autohunt/hunt", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Hunt failed");

    ahState.searchId = data.search_id;
    ahState.currentPage = 1;

    // Fetch portal list for progress bars
    const portalsRes = await fetch("/api/portals");
    const portals = await portalsRes.json();
    const portalKeys = portals.filter(p => p.enabled).map(p => p.key);

    $("ahProgress").classList.remove("d-none");
    ahSetupPortalProgress(portalKeys);
    ahOpenSSE(data.search_id);
  } catch (err) {
    showToast(err.message, "danger");
    $("ahHuntBtn").disabled = false;
  }
}

$("ahAddSkillBtn").addEventListener("click", ahAddSkill);
$("ahSkillInput").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); ahAddSkill(); } });
$("ahHuntBtn").addEventListener("click", ahStartHunt);
$("ahPrevBtn").addEventListener("click", () => ahLoadPage(ahState.currentPage - 1));
$("ahNextBtn").addEventListener("click", () => ahLoadPage(ahState.currentPage + 1));

// ── XSS helpers ───────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(str) {
  return escHtml(str).replace(/'/g, "&#39;");
}

// ── Init ──────────────────────────────────────────────────────────────
(async function init() {
  await loadPortals();

  // Check if a resume already exists
  try {
    const res = await fetch("/api/resume");
    if (res.ok) {
      const data = await res.json();
      state.resumeId = data.id;
      $("resumeStatus").innerHTML =
        `<i class="bi bi-check-circle-fill text-success me-1"></i><strong>${data.filename}</strong>`;
      $("downloadResumeBtn").disabled = false;
      updateFindBtn();
    }
  } catch (_) {}
})();
