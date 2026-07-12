const nodeKeys = ["master", "replica1", "replica2"];
const nodeNames = {
    master: "Maestro",
    replica1: "Réplica 1",
    replica2: "Réplica 2",
};

const state = { refreshing: false };

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json().catch(() => ({ ok: false, message: "Respuesta no válida." }));
    if (!response.ok || data.ok === false) {
        throw new Error(data.message || `Error HTTP ${response.status}`);
    }
    return data;
}

function showToast(message, type = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast ${type}`;
    setTimeout(() => toast.classList.add("hidden"), 4200);
}

function addLog(message, type = "info") {
    const log = document.getElementById("activityLog");
    const entry = document.createElement("p");
    const time = new Date().toLocaleTimeString();
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${time}] ${message}`;
    log.prepend(entry);
}

function humanBytes(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function setCardStatus(nodeKey, node) {
    const card = document.getElementById(`card-${nodeKey}`);
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const online = Boolean(node.db_online);

    card.classList.toggle("is-primary", online && node.role === "primary");
    card.classList.toggle("is-replica", online && node.role === "replica");
    card.classList.toggle("is-offline", !online);

    field("status-pill").textContent = online ? "En línea" : "Fuera de línea";
    field("status-pill").className = `status-pill ${online ? "status-online" : "status-offline"}`;
    field("status-dot").className = `status-dot ${online ? "online" : "offline"}`;

    const roleLabel = !online
        ? "Sin conexión"
        : node.role === "primary"
            ? "Primario / escritura"
            : "Réplica / solo lectura";

    field("role").textContent = roleLabel;
    field("docker").textContent = node.health ? `${node.docker_status} · ${node.health}` : node.docker_status;
    field("read-only").textContent = node.read_only === null ? "—" : (node.read_only ? "Sí" : "No");
    field("rows").textContent = node.row_count ?? "—";
    field("wal").textContent = node.wal_lsn || node.replayed_lsn || "—";
    field("lag").textContent = node.lag_seconds === null || node.lag_seconds === undefined
        ? "—"
        : `${node.lag_seconds} s`;
    field("error").textContent = node.error || "";
}

function renderReplication(rows) {
    const body = document.getElementById("replicationBody");
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="7" class="empty-state">No hay réplicas conectadas al primario actual.</td></tr>';
        return;
    }

    body.innerHTML = rows.map((row) => `
        <tr>
            <td>${escapeHtml(row.application_name)}</td>
            <td>${escapeHtml(row.client_addr)}</td>
            <td>${escapeHtml(row.state)}</td>
            <td>${escapeHtml(row.sync_state)}</td>
            <td>${escapeHtml(row.sent_lsn || "—")}</td>
            <td>${escapeHtml(row.replay_lsn || "—")}</td>
            <td>${humanBytes(row.pending_bytes)}</td>
        </tr>
    `).join("");
}

function renderEmployees(nodeKey, result) {
    const body = document.getElementById(`employees-${nodeKey}`);
    const status = document.querySelector(`[data-table-status="${nodeKey}"]`);

    if (!result.ok) {
        status.textContent = "Sin conexión";
        body.innerHTML = `<tr><td colspan="4" class="empty-state">${escapeHtml(result.message || "No disponible")}</td></tr>`;
        return;
    }

    const rows = result.rows || [];
    status.textContent = `${rows.length} registro(s)`;
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty-state">Sin empleados registrados.</td></tr>';
        return;
    }

    body.innerHTML = rows.map((row) => `
        <tr>
            <td>${escapeHtml(row.id)}</td>
            <td>${escapeHtml(row.nombre)}</td>
            <td>${escapeHtml(row.cargo)}</td>
            <td>${escapeHtml(row.creado_en)}</td>
        </tr>
    `).join("");
}

async function loadStatus() {
    const data = await apiFetch("/api/status");
    nodeKeys.forEach((key) => setCardStatus(key, data.nodes[key]));
    renderReplication(data.replication || []);

    const warning = document.getElementById("warningBanner");
    if (data.split_brain_warning) {
        warning.textContent = "Advertencia: se detectaron varios nodos primarios activos. Detén uno inmediatamente para evitar divergencia de datos.";
        warning.classList.remove("hidden");
    } else if (!data.primary) {
        warning.textContent = "No se detectó un único primario disponible. Las escrituras desde el formulario están deshabilitadas hasta recuperar o promover un nodo.";
        warning.classList.remove("hidden");
    } else {
        warning.classList.add("hidden");
    }
}

async function loadEmployees() {
    const data = await apiFetch("/api/employees");
    nodeKeys.forEach((key) => renderEmployees(key, data.nodes[key]));
}

async function refreshAll({ quiet = false } = {}) {
    if (state.refreshing) return;
    state.refreshing = true;
    const button = document.getElementById("refreshButton");
    button.disabled = true;
    button.textContent = "Actualizando…";

    try {
        await Promise.all([loadStatus(), loadEmployees()]);
        document.getElementById("lastUpdate").textContent = `Última actualización: ${new Date().toLocaleTimeString()}`;
        if (!quiet) addLog("Estado y datos actualizados.", "success");
    } catch (error) {
        showToast(error.message, "error");
        addLog(error.message, "error");
    } finally {
        state.refreshing = false;
        button.disabled = false;
        button.textContent = "Actualizar";
    }
}

async function submitEmployee(event) {
    event.preventDefault();
    const nombre = document.getElementById("nombre").value.trim();
    const cargo = document.getElementById("cargo").value.trim();
    const submitButton = event.submitter;
    submitButton.disabled = true;

    try {
        const data = await apiFetch("/api/employees", {
            method: "POST",
            body: JSON.stringify({ nombre, cargo }),
        });
        event.target.reset();
        showToast(data.message);
        addLog(data.message, "success");
        setTimeout(() => refreshAll({ quiet: true }), 500);
    } catch (error) {
        showToast(error.message, "error");
        addLog(error.message, "error");
    } finally {
        submitButton.disabled = false;
    }
}

async function handleNodeAction(button) {
    const node = button.dataset.node;
    const action = button.dataset.nodeAction;
    const label = nodeNames[node];

    if (["stop", "restart", "promote"].includes(action)) {
        const messages = {
            stop: `¿Detener ${label}? Si es el primario, las escrituras dejarán de funcionar hasta promover otra réplica.`,
            restart: `¿Reiniciar ${label}? Habrá una interrupción breve.`,
            promote: `¿Promover ${label}? Primero debe estar detenido el primario actual para evitar split-brain.`,
        };
        if (!window.confirm(messages[action])) return;
    }

    button.disabled = true;
    try {
        let data;
        if (action === "read" || action === "write") {
            data = await apiFetch(`/api/test/${node}/${action}`, { method: "POST", body: "{}" });
        } else if (action === "promote") {
            data = await apiFetch(`/api/nodes/${node}/promote`, { method: "POST", body: "{}" });
        } else {
            data = await apiFetch(`/api/nodes/${node}/${action}`, { method: "POST", body: "{}" });
        }

        const type = data.write_allowed === false ? "warning" : "success";
        showToast(data.message, type === "warning" ? "success" : type);
        addLog(data.message, type);
        setTimeout(() => refreshAll({ quiet: true }), 1300);
    } catch (error) {
        showToast(error.message, "error");
        addLog(error.message, "error");
    } finally {
        button.disabled = false;
    }
}

async function seedData() {
    const button = document.getElementById("seedButton");
    button.disabled = true;
    try {
        const data = await apiFetch("/api/seed", { method: "POST", body: "{}" });
        showToast(data.message);
        addLog(data.message, "success");
        setTimeout(() => refreshAll({ quiet: true }), 500);
    } catch (error) {
        showToast(error.message, "error");
        addLog(error.message, "error");
    } finally {
        button.disabled = false;
    }
}

async function reconnectReplica2() {
    if (!window.confirm("Esta acción detendrá Réplica 2, la apuntará a Réplica 1 y la volverá a iniciar. Úsala solo después de promover Réplica 1.")) {
        return;
    }
    const button = document.getElementById("reconnectReplica2Button");
    button.disabled = true;
    try {
        const data = await apiFetch("/api/reconnect-replica2", { method: "POST", body: "{}" });
        showToast(data.message);
        addLog(data.message, "success");
        setTimeout(() => refreshAll({ quiet: true }), 2500);
    } catch (error) {
        showToast(error.message, "error");
        addLog(error.message, "error");
    } finally {
        button.disabled = false;
    }
}

document.getElementById("refreshButton").addEventListener("click", () => refreshAll());
document.getElementById("employeeForm").addEventListener("submit", submitEmployee);
document.getElementById("seedButton").addEventListener("click", seedData);
document.getElementById("reconnectReplica2Button").addEventListener("click", reconnectReplica2);
document.getElementById("clearLogButton").addEventListener("click", () => {
    document.getElementById("activityLog").innerHTML = '<p class="log-entry log-info">Registro limpiado.</p>';
});

document.querySelectorAll("[data-node-action]").forEach((button) => {
    button.addEventListener("click", () => handleNodeAction(button));
});

refreshAll({ quiet: true });
setInterval(() => refreshAll({ quiet: true }), 8000);
