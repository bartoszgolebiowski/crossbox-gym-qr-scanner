let autoScanActive = false;

document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    fetchHistory();
    // Poll status & history every 2 seconds
    setInterval(fetchStatus, 2000);
    setInterval(fetchHistory, 2000);
});

async function fetchStatus() {
    try {
        const res = await fetch("/api/v1/status");
        if (!res.ok) return;
        const data = await res.json();

        // Update Pills
        const statusPill = document.getElementById("aws-status-pill");
        if (data.aws_connected) {
            statusPill.textContent = "mTLS AWS IoT Connected";
            statusPill.className = "pill pill-success";
        } else {
            statusPill.textContent = "AWS Disconnected";
            statusPill.className = "pill pill-warning";
        }

        document.getElementById("topic-pill").textContent = `Topic: ${data.aws_iot_topic || '--'}`;

        // Update Info Banner
        document.getElementById("info-endpoint").textContent = data.aws_iot_endpoint || '--';
        document.getElementById("info-clientid").textContent = data.aws_iot_client_id || '--';
        document.getElementById("info-secret").textContent = data.aws_secret_name || '--';
        document.getElementById("info-totalscans").textContent = data.total_scans_count || 0;

        // Auto Scan state
        autoScanActive = data.auto_scan_active;
        const autoBtn = document.getElementById("btn-toggle-auto");
        if (autoScanActive) {
            autoBtn.textContent = "⏹ Stop Auto-Scan Simulation";
            autoBtn.className = "btn btn-secondary btn-active-auto";
        } else {
            autoBtn.textContent = "▶ Start Auto-Scan Simulation";
            autoBtn.className = "btn btn-secondary";
        }
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

async function fetchHistory() {
    try {
        const res = await fetch("/api/v1/history");
        if (!res.ok) return;
        const history = await res.json();
        renderEventsList(history);
    } catch (err) {
        console.error("Error fetching history:", err);
    }
}

function renderEventsList(events) {
    const listEl = document.getElementById("events-list");
    if (!events || events.length === 0) {
        listEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📥</div>
                <p>No QR scans published yet.</p>
                <p class="subtext">Use the controls on the left to trigger a simulated scan.</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = events.map(evt => {
        const dateStr = new Date(evt.timestamp * 1000).toLocaleTimeString();
        const rawData = evt.payload ? evt.payload.raw_data : '';
        return `
            <div class="event-card">
                <div class="event-header">
                    <span class="event-id">ID: ${evt.event_id || 'N/A'}</span>
                    <span class="event-time">${dateStr}</span>
                </div>
                <div class="event-data">${escapeHtml(rawData)}</div>
            </div>
        `;
    }).join("");
}

function usePreset(val) {
    document.getElementById("qr-data-input").value = val;
}

function updateIntervalLabel(val) {
    document.getElementById("interval-val").textContent = val;
}

async function handleManualScan(e) {
    e.preventDefault();
    const input = document.getElementById("qr-data-input");
    const data = input.value.trim();
    if (!data) return;

    const btn = document.getElementById("btn-trigger");
    btn.disabled = true;
    btn.textContent = "Publishing to AWS IoT...";

    try {
        const res = await fetch("/api/v1/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ qr_data: data })
        });
        if (res.ok) {
            input.value = "";
            fetchStatus();
            fetchHistory();
        } else {
            alert("Failed to trigger scan event.");
        }
    } catch (err) {
        alert("Error triggering scan event: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = "<span>📷 Trigger QR Scan Event</span>";
    }
}

async function toggleAutoScan() {
    const interval = parseFloat(document.getElementById("interval-slider").value);
    if (autoScanActive) {
        await fetch("/api/v1/auto-scan/stop", { method: "POST" });
    } else {
        await fetch("/api/v1/auto-scan/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ interval_seconds: interval })
        });
    }
    fetchStatus();
}

function refreshHistory() {
    fetchHistory();
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
