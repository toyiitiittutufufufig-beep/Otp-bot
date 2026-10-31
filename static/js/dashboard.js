/* ══════════════════════════════════════════════════════════════
   24XRAVEN SMS Bot - Dashboard JavaScript
   ══════════════════════════════════════════════════════════════ */

const API = {
    status: "/api/status",
    logs: "/api/logs",
    start: "/api/start",
    stop: "/api/stop",
    check: "/api/check",
    maintenance: "/api/maintenance",
};

let refreshTimer = null;
let isLoading = false;
let maintenanceState = false;

// ══════════════════════════════════════════════════════════════
//  Utilities
// ══════════════════════════════════════════════════════════════
function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

function formatNumber(num) {
    if (num === null || num === undefined) return "0";
    return Number(num).toLocaleString("en-US");
}

function showAlert(message, type = "info") {
    const alertArea = document.getElementById("alertArea");
    const alertClass = {
        success: "alert-success",
        error: "alert-danger",
        warning: "alert-warning",
        info: "alert-info",
    }[type] || "alert-info";

    const icons = {
        success: "fa-check-circle",
        error: "fa-exclamation-circle",
        warning: "fa-exclamation-triangle",
        info: "fa-info-circle",
    };
    const icon = icons[type] || "fa-info-circle";

    const alert = document.createElement("div");
    alert.className = `alert ${alertClass} alert-dismissible fade show fade-in`;
    alert.innerHTML = `
        <i class="fas ${icon}"></i>
        ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    alertArea.innerHTML = "";
    alertArea.appendChild(alert);

    setTimeout(() => {
        if (alert.parentNode) {
            alert.classList.remove("show");
            setTimeout(() => alert.remove(), 300);
        }
    }, 5000);
}

async function apiCall(url, method = "GET") {
    try {
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API Error (${url}):`, error);
        return { success: false, message: error.message };
    }
}

function setButtonLoading(button, loading) {
    if (!button) return;
    if (loading) {
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = '<span class="spinner"></span> جاري...';
        button.disabled = true;
    } else {
        if (button.dataset.originalText) {
            button.innerHTML = button.dataset.originalText;
        }
        button.disabled = false;
    }
}

// ══════════════════════════════════════════════════════════════
//  Status Update
// ══════════════════════════════════════════════════════════════
async function loadStatus() {
    try {
        const data = await apiCall(API.status);
        if (!data || !data.monitor) return;

        const monitor = data.monitor;
        const db = data.db || {};

        // Global status
        const globalStatus = document.getElementById("globalStatus");
        if (monitor.is_running) {
            globalStatus.innerHTML = `
                <span class="status-dot online"></span>
                <span>المراقبة شغالة</span>
            `;
        } else {
            globalStatus.innerHTML = `
                <span class="status-dot offline"></span>
                <span>المراقبة متوقفة</span>
            `;
        }

        // Monitor status card
        const monitorStatus = document.getElementById("monitorStatus");
        if (monitor.is_running) {
            monitorStatus.innerHTML = '<span class="badge bg-success">شغال</span>';
        } else {
            monitorStatus.innerHTML = '<span class="badge bg-secondary">متوقف</span>';
        }

        // Stats
        document.getElementById("uptime").textContent = monitor.uptime || "--";
        document.getElementById("otpsSent").textContent = formatNumber(monitor.total_sent_user + monitor.total_sent_group);
        document.getElementById("totalUsers").textContent = formatNumber(db.total_users);

        // Monitor stats
        document.getElementById("totalFetched").textContent = formatNumber(monitor.total_fetched);
        document.getElementById("sentUser").textContent = formatNumber(monitor.total_sent_user);
        document.getElementById("sentGroup").textContent = formatNumber(monitor.total_sent_group);
        document.getElementById("duplicates").textContent = formatNumber(monitor.total_duplicates);
        document.getElementById("errors").textContent = formatNumber(monitor.total_errors);
        document.getElementById("lastCheck").textContent = monitor.last_check || "--";

        // DB stats
        document.getElementById("dbOtps").textContent = formatNumber(db.total_otps);
        document.getElementById("dbCombos").textContent = formatNumber(db.total_combos);
        document.getElementById("dbBanned").textContent = formatNumber(db.total_banned);

        // Maintenance
        maintenanceState = db.maintenance === true;
        const maintenanceLabel = document.getElementById("maintenanceLabel");
        if (maintenanceState) {
            maintenanceLabel.textContent = "إيقاف الصيانة";
        } else {
            maintenanceLabel.textContent = "وضع الصيانة";
        }

        // Last updated
        document.getElementById("lastUpdated").textContent = new Date().toLocaleTimeString("ar-EG");
    } catch (error) {
        console.error("loadStatus error:", error);
    }
}

// ══════════════════════════════════════════════════════════════
//  Logs Update
// ══════════════════════════════════════════════════════════════
async function loadLogs() {
    try {
        const data = await apiCall(API.logs + "?limit=30");
        const tbody = document.getElementById("logsTable");

        if (!data || !data.success || !data.logs || data.logs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted py-4">
                        لا توجد OTPs مسجلة حتى الآن
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = data.logs.map((log, idx) => {
            const statusBadge = log.sent_to_telegram
                ? '<span class="badge bg-success">مرسل</span>'
                : '<span class="badge bg-warning">معلق</span>';

            const userDisplay = log.user_id
                ? `<code>${escapeHtml(log.user_id)}</code>`
                : '<span class="text-muted">—</span>';

            return `
                <tr class="fade-in">
                    <td>${idx + 1}</td>
                    <td><code>${escapeHtml(log.otp)}</code></td>
                    <td>${escapeHtml(log.service || "Unknown")}</td>
                    <td><code>+${escapeHtml(log.number || "")}</code></td>
                    <td>${userDisplay}</td>
                    <td>${statusBadge}</td>
                    <td class="text-muted small">${escapeHtml(log.created_at || "")}</td>
                </tr>
            `;
        }).join("");
    } catch (error) {
        console.error("loadLogs error:", error);
    }
}

// ══════════════════════════════════════════════════════════════
//  Actions
// ══════════════════════════════════════════════════════════════
async function startMonitor() {
    if (isLoading) return;
    isLoading = true;
    const btn = event?.target?.closest("button");
    setButtonLoading(btn, true);

    const result = await apiCall(API.start, "POST");
    if (result.success) {
        showAlert(result.message || "تم بدء المراقبة", "success");
        await loadStatus();
    } else {
        showAlert(result.message || "فشل بدء المراقبة", "error");
    }

    setButtonLoading(btn, false);
    isLoading = false;
}

async function stopMonitor() {
    if (isLoading) return;
    isLoading = true;
    const btn = event?.target?.closest("button");
    setButtonLoading(btn, true);

    const result = await apiCall(API.stop, "POST");
    if (result.success) {
        showAlert(result.message || "تم إيقاف المراقبة", "success");
        await loadStatus();
    } else {
        showAlert(result.message || "فشل إيقاف المراقبة", "error");
    }

    setButtonLoading(btn, false);
    isLoading = false;
}

async function checkNow() {
    if (isLoading) return;
    isLoading = true;
    const btn = event?.target?.closest("button");
    setButtonLoading(btn, true);

    const result = await apiCall(API.check, "POST");
    if (result.success) {
        showAlert(result.message || "تم الفحص", "info");
        await loadStatus();
        await loadLogs();
    } else {
        showAlert(result.message || "فشل الفحص", "error");
    }

    setButtonLoading(btn, false);
    isLoading = false;
}

async function toggleMaintenance() {
    if (isLoading) return;
    isLoading = true;

    const result = await apiCall(API.maintenance, "POST");
    if (result.success) {
        maintenanceState = result.maintenance;
        showAlert(result.message || "تم تغيير الحالة", "warning");
        await loadStatus();
    } else {
        showAlert(result.message || "فشل التغيير", "error");
    }

    isLoading = false;
}

async function refreshAll() {
    if (isLoading) return;
    await loadStatus();
    await loadLogs();
}

// ══════════════════════════════════════════════════════════════
//  Auto Refresh
// ══════════════════════════════════════════════════════════════
function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        loadStatus();
    }, 10000);

    setInterval(() => {
        loadLogs();
    }, 30000);
}

// ══════════════════════════════════════════════════════════════
//  Init
// ══════════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", async () => {
    console.log("🚀 Dashboard loaded");
    await refreshAll();
    startAutoRefresh();

    setInterval(() => {
        document.getElementById("lastUpdated").textContent =
            new Date().toLocaleTimeString("ar-EG");
    }, 1000);
});

window.addEventListener("error", (e) => {
    console.error("Global error:", e.error);
});
