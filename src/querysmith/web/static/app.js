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
        queryInput.value = `SELECT * FROM ${view.qualified_name}`;
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

wizardForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError(wizardError);
  const formData = new FormData(wizardForm);
  const body = {
    server: formData.get("server"),
    database: formData.get("database"),
    user: formData.get("user"),
    password: formData.get("password"),
    driver: formData.get("driver"),
    trust_server_certificate: formData.get("trust_server_certificate") === "on",
    timeout_s: Number(formData.get("timeout_s")),
  };
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
  queryInput.value = "";
  renderConnected(false, null);
});

function severityClass(severity) {
  return `severity-${(severity || "info").toLowerCase()}`;
}

function renderSuggestedFix(label, text) {
  if (!text) return "";
  return `
    <div class="suggested-fix">
      <div class="suggested-fix-label">${label} (script for review &mdash; not applied automatically)</div>
      <pre>${escapeHtml(text)}</pre>
    </div>
  `;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderReport(data) {
  const s = data.summary;
  const narration = data.narration;

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
          const fixText = f.suggested_fix || f.model_suggested_fix;
          const fixLabel = f.suggested_fix ? "Suggested fix" : "Suggested fix (model)";
          const explanation = f.explanation || f.detail;
          return `
            <div class="finding-card ${severityClass(f.severity)}">
              <div class="finding-header">
                <span class="finding-severity">${escapeHtml(f.severity)}</span>
                <span>${escapeHtml(f.rule_id)}</span>
              </div>
              <div>${escapeHtml(f.summary)}</div>
              <p class="finding-explanation">${escapeHtml(explanation)}</p>
              ${renderSuggestedFix(fixLabel, fixText)}
            </div>
          `;
        })
        .join("")
    : "<p>No issues found by the Tier 0 rules engine.</p>";

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
    <div>${narrationHtml}</div>
  `;
  report.classList.remove("hidden");
}

runBtn.addEventListener("click", async () => {
  hideError(queryError);
  const query = queryInput.value.trim();
  if (!query) {
    showError(queryError, "Enter a query first.");
    return;
  }
  runBtn.disabled = true;
  runBtn.textContent = "Running…";
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
  }
});

init();
