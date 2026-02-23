/**
 * AFAS-link frontend JavaScript
 * Beheert de synchronisatie-trigger en statuspolling
 */

// Controleer sync-status elke 5 seconden
let syncPollingInterval = null;

async function triggerSync(envId = null) {
    const btn = document.querySelector('button[onclick="triggerSync()"]');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Bezig...';
    }

    try {
        const url = envId
            ? `/api/sync/trigger?env_id=${envId}`
            : '/api/sync/trigger';

        const response = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
        });

        const data = await response.json();

        if (response.status === 409) {
            showToast('Er loopt al een synchronisatie. Even geduld.', 'warning');
        } else if (response.ok) {
            showToast('Synchronisatie is gestart!', 'success');
            startPolling();
        } else {
            showToast(`Fout: ${data.detail || 'Onbekende fout'}`, 'danger');
        }
    } catch (e) {
        showToast('Verbindingsfout bij starten van synchronisatie.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Nu synchroniseren';
        }
    }
}

async function checkSyncStatus() {
    try {
        const response = await fetch('/api/sync/status');
        if (!response.ok) return;

        const data = await response.json();
        const indicator = document.getElementById('sync-indicator');

        if (data.actief) {
            if (indicator) {
                indicator.className = 'badge bg-warning text-dark sync-running';
                indicator.innerHTML = '<i class="bi bi-circle-fill me-1" style="font-size:0.6rem;"></i>Synchroniseren...';
            }
        } else {
            if (indicator) {
                indicator.className = 'badge bg-success';
                indicator.innerHTML = '<i class="bi bi-circle-fill me-1" style="font-size:0.6rem;"></i>Actief';
            }
            // Stop polling als sync klaar is, herlaad de pagina voor verse data
            if (syncPollingInterval && !data.actief) {
                stopPolling();
                setTimeout(() => window.location.reload(), 1000);
            }
        }
    } catch (e) {
        // Stille fout bij statuscheck
    }
}

function startPolling() {
    if (syncPollingInterval) return;
    syncPollingInterval = setInterval(checkSyncStatus, 3000);
}

function stopPolling() {
    if (syncPollingInterval) {
        clearInterval(syncPollingInterval);
        syncPollingInterval = null;
    }
}

function showToast(message, type = 'success') {
    const toastEl = document.getElementById('syncToast');
    const toastBody = document.getElementById('syncToastBody');
    if (!toastEl || !toastBody) return;

    // Verwijder bestaande klassen en zet de juiste kleur
    toastEl.className = `toast align-items-center border-0 text-bg-${type}`;
    toastBody.textContent = message;

    const toast = new bootstrap.Toast(toastEl, {delay: 4000});
    toast.show();
}

// Start statuscheck bij laden van de pagina
document.addEventListener('DOMContentLoaded', () => {
    checkSyncStatus();
});
