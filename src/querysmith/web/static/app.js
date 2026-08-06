const wizardSection = document.getElementById("wizard");
const workspaceSection = document.getElementById("workspace");
const connectionPill = document.getElementById("connection-pill");
const disconnectBtn = document.getElementById("disconnect-btn");
const wizardForm = document.getElementById("wizard-form");
const wizardError = document.getElementById("wizard-error");
const viewsList = document.getElementById("views-list");
const viewsError = document.getElementById("views-error");
const queryInput = document.getElementById("query-input");
const runBtn = document.getElementById("run-btn");
const narrateCheckbox = document.getElementById("narrate-checkbox");
const redactCheckbox = document.getElementById("redact-checkbox");
const queryError = document.getElementById("query-error");
const report = document.getElementById("report");
const runOverlay = document.getElementById("run-overlay");
const runOverlayText = document.getElementById("run-overlay-text");

// The findings from the most recently rendered report -- kept around so a
// later Propose Fix response (which only carries finding_index) can be
// labeled with the rule_id/summary it belongs to.
let lastFindings = [];

function showError(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function hideError(el) {
  el.classList.add("hidden");
  el.textContent = "";
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  let body = null;
  if (response.status !== 204) {
    body = await response.json().catch(() => null);
  }
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function renderConnected(connected, status) {
  if (connected) {
    connectionPill.textContent = `Connected to ${status.database} as ${status.user}`;
    connectionPill.classList.remove("pill-disconnected");
    connectionPill.classList.add("pill-connected");
    disconnectBtn.classList.remove("hidden");
    wizardSection.classList.add("hidden");
    workspaceSection.classList.remove("hidden");
  } else {
    connectionPill.textContent = "Not connected";
    connectionPill.classList.remove("pill-connected");
    connectionPill.classList.add("pill-disconnected");
    disconnectBtn.classList.add("hidden");
    workspaceSection.classList.add("hidden");
    wizardSection.classList.remove("hidden");
  }
}

async function loadViews() {
  hideError(viewsError);
  viewsList.innerHTML = "";
  try {
    const data = await requestJson("/api/views");
    for (const view of data.views) {
      const li = document.createElement("li");
      li.textContent = view.qualified_name;
      li.addEventListener("click", () => {
        queryInput.value = view.select_body || `SELECT * FROM ${view.qualified_name}`;
      });
      viewsList.appendChild(li);
    }
  } catch (err) {
    showError(viewsError, `Couldn't load views: ${err.message}`);
  }
}

async function init() {
  try {
    const status = await requestJson("/api/connection");
    renderConnected(status.connected, status);
    if (status.connected) {
      await loadViews();
    }
  } catch (err) {
    renderConnected(false, null);
  }
}

const connectBtn = wizardForm.querySelector('button[type="submit"]');

wizardForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError(wizardError);
  const formData = new FormData(wizardForm);
  const serverHost = formData.get("server");
  const port = formData.get("port");
  const body = {
    server: port ? `${serverHost},${port}` : serverHost,
    database: formData.get("database"),
    user: formData.get("user"),
    password: formData.get("password"),
    driver: formData.get("driver"),
    trust_server_certificate: formData.get("trust_server_certificate") === "on",
    timeout_s: Number(formData.get("timeout_s")),
  };

  let remaining = body.timeout_s > 0 ? body.timeout_s : null;
  connectBtn.disabled = true;
  const renderCountdown = () => {
    connectBtn.textContent =
      remaining === null
        ? "Connecting…"
        : remaining > 0
        ? `Connecting… (${remaining}s)`
        : "Connecting… (waiting on server)";
  };
  renderCountdown();
  const countdownId =
    remaining === null
      ? null
      : setInterval(() => {
          remaining -= 1;
          renderCountdown();
        }, 1000);

  try {
    const status = await requestJson("/api/connection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    wizardForm.reset();
    renderConnected(true, status);
    await loadViews();
  } catch (err) {
    showError(wizardError, err.message);
  } finally {
    if (countdownId !== null) clearInterval(countdownId);
    connectBtn.disabled = false;
    connectBtn.textContent = "Test & Connect";
  }
});

disconnectBtn.addEventListener("click", async () => {
  try {
    await requestJson("/api/connection", { method: "DELETE" });
  } catch (err) {
    // Ignore -- disconnect should always leave the client in a
    // disconnected-looking state even if the request itself failed.
  }
  report.classList.add("hidden");
  report.innerHTML = "";
  lastFindings = [];
  queryInput.value = "";
  renderConnected(false, null);
});

function severityClass(severity) {
  return `severity-${(severity || "info").toLowerCase()}`;
}

// Populated fresh by renderReport(); copy buttons reference an entry by
// index via data-fix-idx rather than round-tripping text through an HTML
// attribute, so nothing about the SQL/text itself needs re-escaping.
let currentFixTexts = [];

function fixCard({ badge, label, text, code }) {
  const idx = currentFixTexts.length;
  currentFixTexts.push(text);
  const body = code ? `<pre>${escapeHtml(text)}</pre>` : `<p>${escapeHtml(text)}</p>`;
  return `
    <div class="fix-card">
      <div class="fix-card-header">
        <span class="fix-card-badge">${escapeHtml(badge)}</span>
        <span class="fix-card-label">${escapeHtml(label)}</span>
        <button type="button" class="btn btn-secondary copy-btn" data-fix-idx="${idx}">Copy</button>
      </div>
      ${body}
    </div>
  `;
}

report.addEventListener("click", async (event) => {
  const copyBtn = event.target.closest(".copy-btn");
  if (copyBtn) {
    const text = currentFixTexts[Number(copyBtn.dataset.fixIdx)];
    if (text === undefined) return;
    try {
      await navigator.clipboard.writeText(text);
      const original = copyBtn.textContent;
      copyBtn.textContent = "Copied!";
      setTimeout(() => {
        copyBtn.textContent = original;
      }, 1500);
    } catch (err) {
      copyBtn.textContent = "Copy failed";
    }
    return;
  }

  const proposeBtn = event.target.closest("#propose-fix-btn");
  if (proposeBtn) {
    await handleProposeFix(proposeBtn);
  }
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderReport(data) {
  const s = data.summary;
  const narration = data.narration;
  currentFixTexts = [];
  lastFindings = data.findings;

  let narrationHtml = "";
  if (narration) {
    let badge = "";
    if (narration.degraded) {
      badge = `<span class="badge">Tier 1 narration unavailable &mdash; showing Tier 0 findings only (${escapeHtml(
        narration.degraded_reason || "unknown reason"
      )})</span>`;
    }
    narrationHtml = `<h3>Overview</h3><p>${escapeHtml(narration.overview)}</p>${badge}`;
  } else {
    narrationHtml = `<h3>Overview</h3><span class="badge">Tier 1 narration disabled for this run.</span>`;
  }

  const findingsHtml = data.findings.length
    ? data.findings
        .map((f) => {
          const explanation = f.explanation || f.detail;
          return `
            <div class="finding-card ${severityClass(f.severity)}">
              <div class="finding-header">
                <span class="finding-severity">${escapeHtml(f.severity)}</span>
                <span>${escapeHtml(f.rule_id)}</span>
              </div>
              <div>${escapeHtml(f.summary)}</div>
              <p class="finding-explanation">${escapeHtml(explanation)}</p>
            </div>
          `;
        })
        .join("")
    : "<p>No issues found by the Tier 0 rules engine.</p>";

  const fixCards = [];
  for (const f of data.findings) {
    const context = `${f.rule_id} — ${f.summary}`;
    if (f.suggested_fix) {
      fixCards.push(
        fixCard({
          badge: "Tier 0 · verified",
          label: `${context}: script (review before running)`,
          text: f.suggested_fix,
          code: true,
        })
      );
    } else if (f.model_suggested_fix) {
      fixCards.push(
        fixCard({
          badge: "Model suggestion",
          label: `${context}: suggested fix`,
          text: f.model_suggested_fix,
          code: false,
        })
      );
    }
  }
  const fixesHtml = fixCards.length
    ? fixCards.join("")
    : '<p class="fix-cards-empty">No fix suggestions yet.</p>';

  report.innerHTML = `
    <div>
      <h3>Plan summary</h3>
      <dl class="summary-grid">
        <div><dt>Engine</dt><dd>${escapeHtml(s.engine)}${s.engine_version ? " (" + escapeHtml(s.engine_version) + ")" : ""}</dd></div>
        <div><dt>Database</dt><dd>${escapeHtml(s.database_name || "unknown")}</dd></div>
        <div><dt>Statement type</dt><dd>${escapeHtml(s.statement_type)}</dd></div>
        <div><dt>Estimated cost</dt><dd>${s.total_estimated_cost ?? "n/a"}</dd></div>
        <div><dt>Actual duration (ms)</dt><dd>${s.total_actual_duration_ms ?? "n/a"}</dd></div>
        <div><dt>Actual rows</dt><dd>${s.total_actual_rows ?? "n/a"}</dd></div>
        <div><dt>Operator count</dt><dd>${s.operator_count}</dd></div>
      </dl>
      <div class="statement-text">${escapeHtml(s.statement_text)}</div>
    </div>
    <div>
      <h3>Findings (${data.findings.length})</h3>
      ${findingsHtml}
    </div>
    <div>
      <div class="fixes-header">
        <h3>Suggested fixes</h3>
        ${
          data.findings.length
            ? '<button type="button" id="propose-fix-btn" class="btn btn-secondary">Propose Fix</button>'
            : ""
        }
      </div>
      <div id="propose-fix-note" class="error-banner hidden"></div>
      <div id="fix-cards-container">${fixesHtml}</div>
    </div>
    <div>${narrationHtml}</div>
  `;
  report.classList.remove("hidden");
}

function renderProposedFixes(result, container, note) {
  if (result.degraded) {
    showError(note, `Tier 1 unavailable for fix proposals (${result.degraded_reason || "unknown reason"}).`);
    return;
  }
  if (!result.fixes.length) {
    showError(note, "The model didn't have anything new to propose.");
    return;
  }
  hideError(note);
  const placeholder = container.querySelector(".fix-cards-empty");
  if (placeholder) placeholder.remove();

  let html = "";
  for (const fix of result.fixes) {
    const finding = lastFindings[fix.finding_index];
    const context = finding ? `${finding.rule_id} — ${finding.summary}` : `Finding #${fix.finding_index}`;
    if (fix.rewritten_query) {
      html += fixCard({
        badge: "Model suggestion · review before running",
        label: `${context}: rewritten query`,
        text: fix.rewritten_query,
        code: true,
      });
    }
    if (fix.index_script) {
      html += fixCard({
        badge: "Model suggestion · review before running",
        label: `${context}: index script`,
        text: fix.index_script,
        code: true,
      });
    }
  }
  container.insertAdjacentHTML("beforeend", html);
}

async function handleProposeFix(btn) {
  const container = report.querySelector("#fix-cards-container");
  const note = report.querySelector("#propose-fix-note");
  hideError(note);
  btn.disabled = true;
  btn.textContent = "Proposing…";
  runOverlayText.textContent = "Asking the local model for fix proposals…";
  runOverlay.classList.remove("hidden");
  try {
    const result = await requestJson("/api/propose-fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    renderProposedFixes(result, container, note);
  } catch (err) {
    showError(note, `Couldn't propose fixes: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Propose Fix";
    runOverlay.classList.add("hidden");
  }
}

runBtn.addEventListener("click", async () => {
  hideError(queryError);
  const query = queryInput.value.trim();
  if (!query) {
    showError(queryError, "Enter a query first.");
    return;
  }
  report.classList.add("hidden");
  report.innerHTML = "";
  runBtn.disabled = true;
  runBtn.textContent = "Running…";
  runOverlayText.textContent = "Running query…";
  runOverlay.classList.remove("hidden");
  try {
    const data = await requestJson("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        narrate: narrateCheckbox.checked,
        redact: redactCheckbox.checked,
      }),
    });
    renderReport(data);
  } catch (err) {
    showError(queryError, err.message);
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run";
    runOverlay.classList.add("hidden");
  }
});

init();
