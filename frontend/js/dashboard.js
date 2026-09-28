/**
 * ABB Robot Web Services (RWS) Dashboard — Frontend Client Application
 * Clean Light Industrial Theme & Progressive Disclosure Controller
 */

class RWSDashboardApp {
  constructor() {
    this.apiBase = "";
    this.autoPoll = true;
    this.fastPollTimer = null;
    this.slowPollTimer = null;
    this.selectedFile = null;
    this.currentIOFilter = "all";
    this.currentEventFilter = "ALL";
    this.pendingAction = null;

    this.initElements();
    this.bindEvents();
    this.initApp();
  }

  initElements() {
    // Topbar
    this.elConnBadge = document.getElementById("topbar-conn-badge");
    this.elConnText = document.getElementById("topbar-conn-text");
    this.elTaskText = document.getElementById("topbar-task-text");
    this.elExecChip = document.getElementById("topbar-exec-chip");
    this.elExecText = document.getElementById("topbar-exec-text");
    this.elAutoPoll = document.getElementById("auto-refresh-toggle");
    this.btnRefreshNow = document.getElementById("btn-refresh-now");

    // Progressive Disclosure Elements
    this.btnMoreTools = document.getElementById("btn-more-tools");
    this.btnMoreToolsText = document.getElementById("btn-more-tools-text");
    this.moreToolsContainer = document.getElementById("more-tools-container");

    // Modal & Toasts
    this.modal = document.getElementById("safety-modal");
    this.modalTitle = document.getElementById("modal-title");
    this.modalBody = document.getElementById("modal-body");
    this.modalConfirmBtn = document.getElementById("modal-confirm-btn");
    this.modalCancelBtn = document.getElementById("modal-cancel-btn");
    this.modalCloseBtn = document.getElementById("modal-close-btn");
    this.toastContainer = document.getElementById("toast-container");
  }

  bindEvents() {
    // Sidebar View Navigation
    document.querySelectorAll(".sidebar .nav-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        if (view) this.switchView(view);
      });
    });

    // Progressive Disclosure "More Tools" Toggle
    if (this.btnMoreTools && this.moreToolsContainer) {
      this.btnMoreTools.addEventListener("click", () => {
        const isExpanded = this.moreToolsContainer.classList.toggle("expanded");
        this.btnMoreTools.classList.toggle("open", isExpanded);
        if (this.btnMoreToolsText) {
          this.btnMoreToolsText.textContent = isExpanded ? "Hide tools" : "More tools";
        }
        if (isExpanded) {
          this.fetchModules();
          this.fetchSignals();
          this.fetchSystemInfo();
        }
      });
    }

    // Sidebar Quick Set Widget (Speed Ratio)
    const btnQuickSpeed = document.getElementById("btn-quickset-speed");
    const inputQuickSpeed = document.getElementById("quickset-speed-input");

    const applySpeedRatio = async () => {
      if (!inputQuickSpeed) return;
      const val = parseInt(inputQuickSpeed.value, 10);
      if (isNaN(val) || val < 1 || val > 100) {
        this.showToast("Speed ratio must be between 1% and 100%", "warning");
        return;
      }
      try {
        const res = await fetch(`${this.apiBase}/api/rapid/speed-ratio`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ speedratio: val }),
        });
        if (res.ok) {
          this.showToast(`RAPID speed override set to ${val}%`, "success");
          this.pollFast();
        } else {
          const err = await res.json();
          this.showToast(`Failed setting speed: ${err.detail || "Error"}`, "error");
        }
      } catch (e) {
        this.showToast(`Failed: ${e.message}`, "error");
      }
    };

    btnQuickSpeed?.addEventListener("click", applySpeedRatio);
    inputQuickSpeed?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        applySpeedRatio();
      }
    });

    // Auto Refresh Toggle
    if (this.elAutoPoll) {
      this.elAutoPoll.addEventListener("change", (e) => {
        this.autoPoll = e.target.checked;
        if (this.autoPoll) {
          this.startPolling();
          this.showToast("Auto-polling enabled", "info");
        } else {
          this.stopPolling();
          this.showToast("Auto-polling paused", "info");
        }
      });
    }

    // Manual Refresh Button
    if (this.btnRefreshNow) {
      this.btnRefreshNow.addEventListener("click", () => {
        this.pollFast();
        this.pollSlow();
        this.showToast("Telemetry refreshed", "info");
      });
    }

    // Quick Execution Controls on Dashboard
    document.getElementById("quick-btn-start")?.addEventListener("click", () => this.promptStartExecution("once"));
    document.getElementById("quick-btn-stop")?.addEventListener("click", () => this.stopExecution());
    document.getElementById("quick-btn-reset")?.addEventListener("click", () => this.resetExecutionPointer());
    document.getElementById("quick-btn-step-prev")?.addEventListener("click", () => this.stepPointer("prev"));
    document.getElementById("quick-btn-step-next")?.addEventListener("click", () => this.stepPointer("next"));

    // Execution Hero Controls
    document.getElementById("exec-hero-start")?.addEventListener("click", () => {
      const cycle = document.querySelector('input[name="exec-cycle-option"]:checked')?.value || "once";
      this.promptStartExecution(cycle);
    });
    document.getElementById("exec-hero-stop")?.addEventListener("click", () => this.stopExecution());
    document.getElementById("exec-hero-reset")?.addEventListener("click", () => this.resetExecutionPointer());
    document.getElementById("exec-hero-abort")?.addEventListener("click", () => this.promptAbortExecution());

    // Program Pointer Stepping Buttons
    document.getElementById("pp-btn-prev")?.addEventListener("click", () => this.stepPointer("prev"));
    document.getElementById("pp-btn-next")?.addEventListener("click", () => this.stepPointer("next"));
    document.getElementById("pp-btn-reset-main")?.addEventListener("click", () => this.resetExecutionPointer());

    // Program Pointer Forms
    document.getElementById("form-set-pp-routine")?.addEventListener("submit", (e) => this.handleSetPPRoutine(e));
    document.getElementById("form-set-pp-cursor")?.addEventListener("submit", (e) => this.handleSetPPCursor(e));

    // Module Management Forms & Dropzone
    this.initModuleDropzone();
    document.getElementById("form-upload-module")?.addEventListener("submit", (e) => this.handleModuleUpload(e));
    document.getElementById("form-load-module")?.addEventListener("submit", (e) => this.handleModuleLoad(e));
    document.getElementById("btn-refresh-modules")?.addEventListener("click", () => this.fetchModules());

    // I/O Filter & Search
    document.querySelectorAll(".io-filter-tabs .filter-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".io-filter-tabs .filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        this.currentIOFilter = tab.dataset.cat || "all";
        this.fetchSignals();
      });
    });

    document.getElementById("io-search-input")?.addEventListener("input", (e) => {
      this.filterIOTable(e.target.value);
    });

    // Events Filter & Actions
    document.querySelectorAll(".events-filter-group .filter-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".events-filter-group .filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        this.currentEventFilter = tab.dataset.level || "ALL";
        this.fetchEvents();
      });
    });

    document.getElementById("btn-clear-events")?.addEventListener("click", () => this.clearEvents());
    document.getElementById("btn-export-events")?.addEventListener("click", () => this.exportEvents());

    // Settings Form
    document.getElementById("form-settings")?.addEventListener("submit", (e) => this.handleSaveSettings(e));

    // Modal Buttons
    this.modalCloseBtn?.addEventListener("click", () => this.closeModal());
    this.modalCancelBtn?.addEventListener("click", () => this.closeModal());
    this.modalConfirmBtn?.addEventListener("click", () => {
      if (this.pendingAction) {
        const action = this.pendingAction;
        this.pendingAction = null;
        this.closeModal();
        action();
      }
    });
  }

  async initApp() {
    await this.loadInitialConfig();
    this.pollFast();
    this.pollSlow();
    this.fetchSystemInfo();
    this.startPolling();
  }

  switchView(viewName) {
    document.querySelectorAll(".sidebar .nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewName);
    });

    document.querySelectorAll(".content-area .view-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `view-${viewName}`);
    });

    // Dynamic 3D canvas viewport switching between overview and full twin
    if (window.digitalTwinViewer) {
      if (viewName === "dashboard") {
        window.digitalTwinViewer.attachToContainer("digital-twin-canvas-container");
      } else if (viewName === "twin") {
        window.digitalTwinViewer.attachToContainer("digital-twin-full-canvas-container");
      }
      setTimeout(() => {
        window.digitalTwinViewer.onResize();
      }, 50);
    }

    if (viewName === "events") this.fetchEvents();
    if (viewName === "modules") this.fetchModules();
    if (viewName === "io") this.fetchSignals();
    if (viewName === "system") this.fetchSystemInfo();
  }

  startPolling() {
    this.stopPolling();
    // Fast telemetry poll (1000ms): Controller, Execution, Program Pointer
    this.fastPollTimer = setInterval(() => {
      if (this.autoPoll) this.pollFast();
    }, 1000);

    // Normal telemetry poll (4000ms): Modules, Signals, Events
    this.slowPollTimer = setInterval(() => {
      if (this.autoPoll) this.pollSlow();
    }, 4000);
  }

  stopPolling() {
    if (this.fastPollTimer) clearInterval(this.fastPollTimer);
    if (this.slowPollTimer) clearInterval(this.slowPollTimer);
  }

  // --------------------------------------------------------------------------
  // Telemetry Polling
  // --------------------------------------------------------------------------

  async pollFast() {
    await Promise.all([
      this.fetchControllerStatus(),
      this.fetchExecutionState(),
      this.fetchProgramPointer(),
    ]);
  }

  async pollSlow() {
    await Promise.all([
      this.fetchModules(),
      this.fetchSignals(),
      this.fetchEvents(),
    ]);
  }

  async fetchControllerStatus() {
    try {
      const res = await fetch(`${this.apiBase}/api/controller/status`);
      const data = await res.json();
      this.updateControllerUI(data);
    } catch (err) {
      this.updateControllerUI({ connected: false, simulation: false, message: err.message });
    }
  }

  updateControllerUI(status) {
    if (!this.elConnBadge) return;
    this.elConnBadge.className = "status-badge";

    if (status.simulation) {
      this.elConnBadge.classList.add("simulation");
      this.elConnText.textContent = "SIMULATION";
    } else if (status.connected) {
      this.elConnBadge.classList.add("connected");
      this.elConnText.textContent = "CONNECTED";
    } else {
      this.elConnBadge.classList.add("disconnected");
      this.elConnText.textContent = "OFFLINE";
    }

    // Topbar task
    if (status.task_name && this.elTaskText) {
      this.elTaskText.textContent = status.task_name;
    }

    // Dashboard Overview Card
    const dashIp = document.getElementById("dash-ctrl-ip");
    const dashState = document.getElementById("dash-ctrl-state");
    const dashMode = document.getElementById("dash-ctrl-mode");
    const dashBadge = document.getElementById("dash-ctrl-badge");

    if (dashIp) dashIp.textContent = status.ip || "192.168.125.1";
    if (dashState) dashState.textContent = status.ctrlstate || "unknown";
    if (dashMode) dashMode.textContent = status.opmode || "AUTO";
    if (dashBadge) {
      dashBadge.textContent = status.simulation ? "SIMULATION" : (status.connected ? "ONLINE" : "OFFLINE");
      dashBadge.className = `badge ${status.connected || status.simulation ? 'badge-success' : 'badge-danger'}`;
    }
  }

  async fetchExecutionState() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/execution`);
      const data = await res.json();
      this.updateExecutionUI(data);
    } catch (err) {
      console.warn("Failed fetching execution state:", err);
    }
  }

  updateExecutionUI(exec) {
    const isRunning = exec.is_running || exec.state === "RUNNING";
    const stateText = exec.state || "STOPPED";
    const cycleText = exec.cycle || "ONCE";
    const speedRatio = exec.speedratio || 100;
    const speedText = `${speedRatio}%`;

    // Topbar badge
    if (this.elExecText) {
      this.elExecText.textContent = stateText;
      this.elExecText.className = `chip-value pill ${isRunning ? 'running' : ''}`;
    }

    // Dashboard overview card
    const dashBadge = document.getElementById("dash-exec-badge");
    const dashCycle = document.getElementById("dash-exec-cycle");
    const dashSpeed = document.getElementById("dash-exec-speed");
    const dashTask = document.getElementById("dash-exec-task");

    if (dashBadge) {
      dashBadge.textContent = stateText;
      dashBadge.className = `badge ${isRunning ? 'badge-success' : 'badge-warning'}`;
    }
    if (dashCycle) dashCycle.textContent = cycleText;
    if (dashSpeed) dashSpeed.textContent = speedText;
    if (dashTask) dashTask.textContent = exec.task || "T_ROB1";

    // Keep Quick Set input synced if not focused
    const quickSpeedInput = document.getElementById("quickset-speed-input");
    if (quickSpeedInput && document.activeElement !== quickSpeedInput) {
      quickSpeedInput.value = speedRatio;
    }

    // Update Weld Card
    this.updateWeldCard(exec);
  }

  updateWeldCard(exec) {
    const badge = document.getElementById("dash-weld-badge");
    const ready = document.getElementById("dash-weld-ready");
    const arc = document.getElementById("dash-weld-arc");
    const feed = document.getElementById("dash-weld-feed");

    const isRunning = exec && (exec.is_running || exec.state === "RUNNING");
    if (badge) {
      badge.textContent = isRunning ? "WELDING" : "STANDBY";
      badge.className = `badge ${isRunning ? 'badge-warning' : 'badge-success'}`;
    }
    if (ready) ready.textContent = "24V Power Bus / Standby OK";
    if (arc) arc.textContent = isRunning ? "Arc Active (Simulated)" : "Extinguished";
    if (feed) feed.textContent = isRunning ? "Wire Feed Engaged" : "Purged / Idle";
  }

  async fetchProgramPointer() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/program-pointer`);
      const data = await res.json();
      this.updateProgramPointerUI(data);
    } catch (err) {
      console.warn("Failed fetching program pointer:", err);
    }
  }

  updateProgramPointerUI(pp) {
    const mod = pp.module || "MainModule";
    const routine = pp.routine || "main";
    const line = pp.line || 1;
    const col = pp.col || 1;
    const posFormatted = `${line},${col}`;

    // Dashboard card
    const dashMod = document.getElementById("dash-pp-mod");
    const dashRoutine = document.getElementById("dash-pp-routine");
    const dashPos = document.getElementById("dash-pp-pos");

    if (dashMod) dashMod.textContent = mod;
    if (dashRoutine) dashRoutine.textContent = routine;
    if (dashPos) dashPos.textContent = posFormatted;
  }

  async fetchModules() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/modules`);
      const modules = await res.json();
      this.updateModulesUI(modules);
    } catch (err) {
      console.warn("Failed fetching modules:", err);
    }
  }

  updateModulesUI(modules) {
    if (!Array.isArray(modules)) return;

    // Overview table
    const dashTbody = document.getElementById("dash-modules-tbody");
    if (dashTbody) {
      if (modules.length === 0) {
        dashTbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No modules found</td></tr>';
      } else {
        dashTbody.innerHTML = modules.map((m) => `
          <tr style="cursor: pointer;" onclick="dashboardApp.inspectModule('${m.name}')">
            <td class="font-mono"><strong>${m.name}</strong></td>
            <td><span class="badge ${m.type === 'SysMod' ? 'badge-info' : 'badge-neutral'}">${m.type}</span></td>
            <td class="font-mono text-muted">T_ROB1</td>
          </tr>
        `).join("");
      }
    }

    const modCount = document.getElementById("dash-mod-count");
    if (modCount) modCount.textContent = modules.length;

    const progMods = modules.filter(m => m.type !== "SysMod").length;
    const sysMods = modules.filter(m => m.type === "SysMod").length;
    const progEl = document.getElementById("dash-prog-mods");
    const sysEl = document.getElementById("dash-sys-mods");
    if (progEl) progEl.textContent = progMods;
    if (sysEl) sysEl.textContent = sysMods;
  }

  async inspectModule(moduleName) {
    const badge = document.getElementById("rapid-inspect-mod-name");
    const codeView = document.getElementById("rapid-source-code");
    if (badge) badge.textContent = `Module: ${moduleName}`;
    if (codeView) codeView.textContent = `Loading source for ${moduleName}...`;

    try {
      const res = await fetch(`${this.apiBase}/api/rapid/module-source/${encodeURIComponent(moduleName)}`);
      const data = await res.json();
      if (codeView) {
        codeView.textContent = data.source || "! Empty module source";
      }
      this.showToast(`Inspecting module ${moduleName}`, "info");
    } catch (err) {
      if (codeView) codeView.textContent = `! Could not fetch module source: ${err.message}`;
      this.showToast(`Error reading module: ${err.message}`, "error");
    }
  }

  async fetchSignals() {
    try {
      const url = this.currentIOFilter === "all" ? `${this.apiBase}/api/io/signals` : `${this.apiBase}/api/io/signals?category=${this.currentIOFilter}`;
      const res = await fetch(url);
      const signals = await res.json();
      this.updateSignalsUI(signals);
    } catch (err) {
      console.warn("Failed fetching signals:", err);
    }
  }

  updateSignalsUI(signals) {
    const tbody = document.getElementById("io-signals-tbody");
    if (!tbody || !Array.isArray(signals)) return;

    const totalEl = document.getElementById("io-total-signals");
    const activeEl = document.getElementById("io-active-signals");
    if (totalEl) totalEl.textContent = signals.length;
    if (activeEl) {
      const highCount = signals.filter(s => Number(s.value) === 1).length;
      activeEl.textContent = highCount;
    }

    if (signals.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No signals found matching criteria</td></tr>';
      return;
    }

    tbody.innerHTML = signals.map((s) => {
      const isDigital = s.type === "DI" || s.type === "DO";
      const isDO = s.type === "DO";
      const isHigh = Number(s.value) === 1;

      let valBadge = "";
      if (isDigital) {
        valBadge = `<span class="badge ${isHigh ? 'badge-success' : 'badge-neutral'}">${isHigh ? '1 (HIGH)' : '0 (LOW)'}</span>`;
      } else {
        valBadge = `<span class="font-mono"><strong>${s.value}</strong></span>`;
      }

      const actionBtn = isDO
        ? `<button class="btn btn-secondary btn-sm" onclick="dashboardApp.promptToggleSignal('${s.name}', ${isHigh ? 0 : 1})">
             Set to ${isHigh ? '0' : '1'}
           </button>`
        : '<span class="text-muted">Read Only</span>';

      return `
        <tr data-sig-name="${s.name.toLowerCase()}">
          <td class="font-mono"><strong>${s.name}</strong></td>
          <td><span class="badge badge-info">${s.type}</span></td>
          <td class="text-muted">${s.category || s.type}</td>
          <td>${valBadge}</td>
          <td>${actionBtn}</td>
        </tr>
      `;
    }).join("");
  }

  filterIOTable(searchTerm) {
    const term = (searchTerm || "").toLowerCase().trim();
    document.querySelectorAll("#io-signals-tbody tr").forEach((row) => {
      const name = row.dataset.sigName || "";
      row.style.display = name.includes(term) ? "" : "none";
    });
  }

  async fetchEvents() {
    try {
      const url = this.currentEventFilter === "ALL" ? `${this.apiBase}/api/events?limit=50` : `${this.apiBase}/api/events?limit=50&level=${this.currentEventFilter}`;
      const res = await fetch(url);
      const events = await res.json();
      this.updateEventsUI(events);
    } catch (err) {
      console.warn("Failed fetching events:", err);
    }
  }

  updateEventsUI(events) {
    if (!Array.isArray(events)) return;

    // Update Overview "Last Event" card
    if (events.length > 0) {
      const last = events[0];
      const levelEl = document.getElementById("last-event-level");
      const timeEl = document.getElementById("last-event-time");
      const msgEl = document.getElementById("last-event-msg");
      if (levelEl) {
        levelEl.textContent = last.level;
        levelEl.className = `badge ${last.level === 'ERROR' ? 'badge-danger' : (last.level === 'WARNING' ? 'badge-warning' : 'badge-info')}`;
      }
      if (timeEl) timeEl.textContent = last.timestamp || "";
      if (msgEl) msgEl.textContent = last.message || "";
    }

    // Events full table
    const tbody = document.getElementById("events-tbody");
    if (tbody) {
      if (events.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No events recorded</td></tr>';
      } else {
        tbody.innerHTML = events.map((e) => `
          <tr>
            <td class="font-mono text-muted">${e.timestamp}</td>
            <td><span class="event-level ${e.level.toLowerCase()}">${e.level}</span></td>
            <td><strong>${e.source || 'Controller'}</strong></td>
            <td class="event-msg">${e.message}</td>
          </tr>
        `).join("");
      }
    }
  }

  async fetchSystemInfo() {
    try {
      const res = await fetch(`${this.apiBase}/api/system/info`);
      const data = await res.json();

      const ctrlName = document.getElementById("sys-ctrl-name");
      const rwVer = document.getElementById("sys-rw-version");
      const mechUnit = document.getElementById("sys-mech-unit");
      const robotType = document.getElementById("sys-robot-type");
      const payload = document.getElementById("sys-payload");
      const reach = document.getElementById("sys-reach");

      if (ctrlName && data.controller) ctrlName.textContent = data.controller.name || "IRC5_Compact";
      if (rwVer && data.controller) rwVer.textContent = data.controller.version || "RobotWare 6.06.03";
      if (mechUnit && data.robot) mechUnit.textContent = data.robot.mechanical_unit || "ROB_1";
      if (robotType && data.robot) robotType.textContent = data.robot.model || "ABB IRB 1660ID-6/1.55";
      if (payload && data.robot) payload.textContent = `${data.robot.payload_kg || 6} kg`;
      if (reach && data.robot) reach.textContent = `${data.robot.reach_m || 1.55} m`;
    } catch (e) {
      console.warn("Failed fetching system info:", e);
    }
  }

  // --------------------------------------------------------------------------
  // Execution Control Handlers
  // --------------------------------------------------------------------------

  promptStartExecution(cycle = "once") {
    this.openSafetyModal(
      "Confirm Program Execution Start",
      `Are you sure you want to <strong>START RAPID EXECUTION</strong>?<br><br>
       Cycle mode: <strong>${cycle.toUpperCase()}</strong>.<br>
       <span style="color: var(--warn-strong);">Ensure all personnel and obstacles are outside the physical robot cell!</span>`,
      () => this.startExecution(cycle)
    );
  }

  async startExecution(cycle = "once") {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/execution/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cycle }),
      });
      const data = await res.json();
      this.showToast(data.message || "Execution started", "success");
      this.pollFast();
    } catch (err) {
      this.showToast(`Error starting execution: ${err.message}`, "error");
    }
  }

  async stopExecution() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/execution/stop`, {
        method: "POST",
      });
      const data = await res.json();
      this.showToast(data.message || "Execution stopped", "warning");
      this.pollFast();
    } catch (err) {
      this.showToast(`Error stopping execution: ${err.message}`, "error");
    }
  }

  promptAbortExecution() {
    this.openSafetyModal(
      "Confirm RAPID Execution Abort",
      `<span style="color: var(--crit); font-weight: bold;">EMERGENCY ABORT:</span><br><br>
       This will immediately halt RAPID execution and abort all active motion instructions.<br>
       Do you wish to proceed?`,
      () => this.abortExecution()
    );
  }

  async abortExecution() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/execution/abort`, {
        method: "POST",
      });
      const data = await res.json();
      this.showToast(data.message || "Execution aborted", "error");
      this.pollFast();
    } catch (err) {
      this.showToast(`Error aborting execution: ${err.message}`, "error");
    }
  }

  async resetExecutionPointer() {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/execution/reset`, {
        method: "POST",
      });
      const data = await res.json();
      this.showToast(data.message || "PP reset to Main", "info");
      this.pollFast();
    } catch (err) {
      this.showToast(`Error resetting PP: ${err.message}`, "error");
    }
  }

  async stepPointer(direction) {
    try {
      const endpoint = direction === "next" ? "/api/rapid/next-instruction" : "/api/rapid/previous-instruction";
      const res = await fetch(`${this.apiBase}${endpoint}`, { method: "POST" });
      const data = await res.json();
      this.showToast(`Stepped ${direction}`, "info");
      this.pollFast();
    } catch (err) {
      this.showToast(`Step failed: ${err.message}`, "error");
    }
  }

  async handleSetPPRoutine(e) {
    e.preventDefault();
    const module = document.getElementById("pp-routine-module").value.trim();
    const routine = document.getElementById("pp-routine-name").value.trim();
    const userlevel = parseInt(document.getElementById("pp-routine-userlevel")?.value, 10) || 1;

    try {
      const res = await fetch(`${this.apiBase}/api/rapid/set-pointer-routine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module, routine, userlevel }),
      });
      const data = await res.json();
      this.showToast(data.message || `PP set to ${module}.${routine}`, "success");
      this.pollFast();
    } catch (err) {
      this.showToast(`Failed setting PP to routine: ${err.message}`, "error");
    }
  }

  async handleSetPPCursor(e) {
    e.preventDefault();
    const module = document.getElementById("pp-cursor-module").value.trim();
    const routine = document.getElementById("pp-cursor-routine").value.trim();
    const line = parseInt(document.getElementById("pp-cursor-line").value, 10);
    const col = parseInt(document.getElementById("pp-cursor-col").value, 10);

    try {
      const res = await fetch(`${this.apiBase}/api/rapid/set-pointer-cursor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module, routine, line, col }),
      });
      const data = await res.json();
      this.showToast(data.message || `PP set to line ${line}`, "success");
      this.pollFast();
    } catch (err) {
      this.showToast(`Failed setting PP to cursor: ${err.message}`, "error");
    }
  }

  initModuleDropzone() {
    const dropzone = document.getElementById("upload-dropzone");
    const fileInput = document.getElementById("file-module-input");
    const fileInfo = document.getElementById("selected-file-info");
    const fileName = document.getElementById("selected-file-name");
    const fileSize = document.getElementById("selected-file-size");

    if (!dropzone || !fileInput) return;

    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        this.handleFileSelected(fileInput.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files.length) {
        this.handleFileSelected(e.target.files[0]);
      }
    });
  }

  handleFileSelected(file) {
    this.selectedFile = file;
    const fileInfo = document.getElementById("selected-file-info");
    const fileName = document.getElementById("selected-file-name");
    const fileSize = document.getElementById("selected-file-size");

    if (file) {
      if (fileName) fileName.textContent = file.name;
      if (fileSize) fileSize.textContent = `(${(file.size / 1024).toFixed(1)} KB)`;
      if (fileInfo) fileInfo.style.display = "flex";
      const loadInput = document.getElementById("load-module-path");
      if (loadInput) loadInput.value = `$HOME/${file.name}`;
    }
  }

  async handleModuleUpload(e) {
    e.preventDefault();
    if (!this.selectedFile) return;

    const formData = new FormData();
    formData.append("file", this.selectedFile);

    try {
      this.showToast(`Uploading ${this.selectedFile.name} to $HOME/...`, "info");
      const res = await fetch(`${this.apiBase}/api/rapid/upload-module`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "success");
      } else {
        this.showToast(data.message || "Upload failed", "error");
      }
      this.fetchEvents();
      this.fetchModules();
    } catch (err) {
      this.showToast(`Upload error: ${err.message}`, "error");
    }
  }

  async handleModuleLoad(e) {
    e.preventDefault();
    const modulepath = document.getElementById("load-module-path")?.value.trim() || "$HOME/MainModule.mod";
    const replace = document.getElementById("load-module-replace")?.checked ?? true;
    const task = document.getElementById("load-module-task")?.value || "T_ROB1";

    try {
      const res = await fetch(`${this.apiBase}/api/rapid/load-module`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modulepath, replace, task }),
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "success");
        this.fetchModules();
      } else {
        this.showToast(data.message || "Load failed", "error");
      }
      this.fetchEvents();
    } catch (err) {
      this.showToast(`Load error: ${err.message}`, "error");
    }
  }

  promptUnloadModule(moduleName) {
    this.openSafetyModal(
      "Confirm Module Unload",
      `Are you sure you want to unload module <strong>${moduleName}</strong> from task T_ROB1?<br><br>
       <span style="color: var(--warn-strong);">Any active routines within this module will be terminated.</span>`,
      () => this.unloadModule(moduleName)
    );
  }

  async unloadModule(moduleName) {
    try {
      const res = await fetch(`${this.apiBase}/api/rapid/unload-module`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module_name: moduleName }),
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "warning");
        this.fetchModules();
      } else {
        this.showToast(data.message || "Unload failed", "error");
      }
      this.fetchEvents();
    } catch (err) {
      this.showToast(`Unload error: ${err.message}`, "error");
    }
  }

  promptToggleSignal(sigName, newVal) {
    this.openSafetyModal(
      "Confirm Signal State Change",
      `Set digital output <strong>${sigName}</strong> to <strong>${newVal}</strong>?`,
      () => this.setSignalValue(sigName, newVal)
    );
  }

  async setSignalValue(signalName, value) {
    try {
      const res = await fetch(`${this.apiBase}/api/io/set-signal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_name: signalName, value }),
      });
      const data = await res.json();
      this.showToast(data.message || `Signal ${signalName} set to ${value}`, "info");
      this.fetchSignals();
    } catch (err) {
      this.showToast(`Failed setting signal: ${err.message}`, "error");
    }
  }

  async clearEvents() {
    try {
      await fetch(`${this.apiBase}/api/events/clear`, { method: "POST" });
      this.showToast("Event buffer cleared", "info");
      this.fetchEvents();
    } catch (err) {
      this.showToast(`Error clearing events: ${err.message}`, "error");
    }
  }

  async exportEvents() {
    try {
      const res = await fetch(`${this.apiBase}/api/events?limit=500`);
      const events = await res.json();
      const blob = new Blob([JSON.stringify(events, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `abb_rws_events_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.showToast("Events exported to JSON", "success");
    } catch (err) {
      this.showToast(`Export failed: ${err.message}`, "error");
    }
  }

  async loadInitialConfig() {
    try {
      const res = await fetch(`${this.apiBase}/api/controller/config`);
      const cfg = await res.json();
      const ipEl = document.getElementById("setting-ip") || document.getElementById("set-ip");
      const portEl = document.getElementById("setting-port") || document.getElementById("set-port");
      const userEl = document.getElementById("setting-user") || document.getElementById("set-user");
      const taskEl = document.getElementById("setting-task") || document.getElementById("set-task");
      const timeoutEl = document.getElementById("setting-timeout") || document.getElementById("set-timeout");
      const simEl = document.getElementById("setting-sim-mode") || document.getElementById("set-sim-mode");

      if (ipEl) ipEl.value = cfg.robot_ip || "192.168.125.1";
      if (portEl) portEl.value = cfg.robot_port || 80;
      if (userEl) userEl.value = cfg.username || "Default User";
      if (taskEl) taskEl.value = cfg.task_name || "T_ROB1";
      if (timeoutEl) timeoutEl.value = cfg.timeout || 3.0;
      if (simEl) simEl.checked = !!cfg.simulation_mode;
    } catch (e) {
      console.warn("Could not load initial config:", e);
    }
  }

  async handleSaveSettings(e) {
    e.preventDefault();
    const ip = (document.getElementById("setting-ip") || document.getElementById("set-ip"))?.value.trim() || "192.168.125.1";
    const port = parseInt((document.getElementById("setting-port") || document.getElementById("set-port"))?.value, 10) || 80;
    const username = (document.getElementById("setting-user") || document.getElementById("set-user"))?.value.trim() || "Default User";
    const password = (document.getElementById("setting-pass") || document.getElementById("set-pass"))?.value || "";
    const task_name = (document.getElementById("setting-task") || document.getElementById("set-task"))?.value.trim() || "T_ROB1";
    const timeout = parseFloat((document.getElementById("setting-timeout") || document.getElementById("set-timeout"))?.value) || 3.0;
    const simulation_mode = (document.getElementById("setting-sim-mode") || document.getElementById("set-sim-mode"))?.checked ?? true;

    const payload = { robot_ip: ip, robot_port: port, username, task_name, timeout, simulation_mode };
    if (password) payload.password = password;

    try {
      const res = await fetch(`${this.apiBase}/api/controller/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      this.showToast("Settings updated. Connecting...", "info");
      this.pollFast();
      this.fetchSystemInfo();
    } catch (err) {
      this.showToast(`Error saving settings: ${err.message}`, "error");
    }
  }

  // --------------------------------------------------------------------------
  // Modals & Notifications
  // --------------------------------------------------------------------------

  openSafetyModal(title, bodyHtml, confirmCallback) {
    if (!this.modal) return;
    this.modalTitle.textContent = title;
    this.modalBody.innerHTML = bodyHtml;
    this.pendingAction = confirmCallback;
    this.modal.style.display = "flex";
  }

  closeModal() {
    if (!this.modal) return;
    this.modal.style.display = "none";
    this.pendingAction = null;
  }

  showToast(message, type = "info") {
    if (!this.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    this.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(40px)";
      setTimeout(() => toast.remove(), 200);
    }, 3500);
  }
}

// Instantiate dashboard application on page load
let dashboardApp;
window.addEventListener("DOMContentLoaded", () => {
  dashboardApp = new RWSDashboardApp();
});
