/**
 * FB Auto Post - Distributed Worker Node Options Controller
 * extension-auth-helper/options.js
 */

const DEFAULT_TARGET = "19823";
const inputTarget = document.getElementById("syncTarget");
const inputProjectKey = document.getElementById("projectKey");
const inputToken = document.getElementById("syncToken");
const workerIdDisplay = document.getElementById("workerIdDisplay");
const warmupEnabledCheckbox = document.getElementById("warmupEnabled");
const warmupMaxReactionsInput = document.getElementById("warmupMaxReactions");
const btnSave = document.getElementById("btnSave");
const statusMsg = document.getElementById("statusMsg");

// Load settings
document.addEventListener("DOMContentLoaded", () => {
    try {
        chrome.storage.local.get([
            "syncPort", "syncTarget", "syncToken", "projectKey",
            "instanceId", "warmupEnabled", "warmupMaxReactions"
        ], (data) => {
            if (chrome.runtime.lastError) {
                console.error("Error loading settings:", chrome.runtime.lastError);
                return;
            }

            if (workerIdDisplay) {
                workerIdDisplay.value = data.instanceId || "Đang khởi tạo...";
            }

            if (data.syncTarget) {
                inputTarget.value = data.syncTarget;
            } else {
                inputTarget.value = data.syncPort || DEFAULT_TARGET;
            }

            if (data.projectKey) {
                inputProjectKey.value = data.projectKey;
            } else {
                inputProjectKey.value = "taikhoan1";
            }

            if (data.syncToken) {
                inputToken.value = data.syncToken;
            }

            if (warmupEnabledCheckbox) {
                warmupEnabledCheckbox.checked = !!data.warmupEnabled;
            }

            if (warmupMaxReactionsInput && data.warmupMaxReactions) {
                warmupMaxReactionsInput.value = data.warmupMaxReactions;
            }
        });
    } catch (e) {
        console.error("Storage API error:", e);
    }
});

// Save settings & test connection
btnSave.addEventListener("click", () => {
    const targetVal = (inputTarget.value || "").trim();
    const projectVal = (inputProjectKey.value || "taikhoan1").trim().toLowerCase();
    const tokenVal = (inputToken.value || "").trim();
    const warmupVal = warmupEnabledCheckbox ? warmupEnabledCheckbox.checked : false;
    const maxReactionsVal = warmupMaxReactionsInput ? parseInt(warmupMaxReactionsInput.value, 10) || 5 : 5;

    if (!targetVal) {
        showStatus("Vui lòng nhập số Port hoặc URL Server VPS.", "error");
        return;
    }

    const isUrl = targetVal.startsWith("http://") || targetVal.startsWith("https://");
    const portNum = parseInt(targetVal, 10);
    const isPort = !isNaN(portNum) && portNum >= 1 && portNum <= 65535 && String(portNum) === targetVal;

    if (!isUrl && !isPort) {
        showStatus("Số port phải từ 1-65535 hoặc nhập đầy đủ URL (http:// hoặc https://).", "error");
        return;
    }

    try {
        const saveData = {
            syncTarget: targetVal,
            projectKey: projectVal,
            syncToken: tokenVal,
            warmupEnabled: warmupVal,
            warmupMaxReactions: maxReactionsVal
        };
        if (isPort) {
            saveData.syncPort = portNum;
        }

        chrome.storage.local.set(saveData, async () => {
            if (chrome.runtime.lastError) {
                showStatus(`Lỗi lưu cài đặt: ${chrome.runtime.lastError.message}`, "error");
                return;
            }

            // Notify background of warmup toggle
            try {
                chrome.runtime.sendMessage({ type: "TOGGLE_WARMUP", enabled: warmupVal }).catch(() => {});
            } catch (e) {}

            const targetUrl = isUrl ? targetVal.replace(/\/+$/, "") : `http://127.0.0.1:${portNum}`;
            showStatus(`Đã lưu! Đang thử kết nối tới ${targetUrl}...`, "info", 0);

            try {
                const headers = {};
                if (tokenVal) {
                    headers["X-Sync-Token"] = tokenVal;
                    headers["Authorization"] = `Bearer ${tokenVal}`;
                }
                if (projectVal) headers["X-Project-Key"] = projectVal;

                const resp = await fetch(`${targetUrl}/api/accounts`, {
                    headers,
                    signal: AbortSignal.timeout(6000)
                });

                if (resp.ok) {
                    showStatus(`✅ Kết nối thành công tới Backend ${targetUrl}!`, "success", 5000);
                } else if (resp.status === 401) {
                    showStatus(`❌ Đã kết nối, nhưng nhận 401 Unauthorized! Kiểm tra lại Sync Token.`, "error", 6000);
                } else {
                    showStatus(`⚠️ Server phản hồi mã HTTP ${resp.status}.`, "error", 5000);
                }
            } catch (err) {
                showStatus(`⚠️ Đã lưu, nhưng chưa thể kết nối Server tại ${targetUrl}: ${err.message}`, "error", 6000);
            }
        });
    } catch (e) {
        showStatus(`Lỗi Storage API: ${e.message}`, "error");
    }
});

function showStatus(text, type, timeoutMs = 3500) {
    statusMsg.textContent = text;
    statusMsg.className = `status-msg show ${type}`;

    if (window.statusTimeout) {
        clearTimeout(window.statusTimeout);
    }
    if (timeoutMs > 0) {
        window.statusTimeout = setTimeout(() => {
            statusMsg.classList.remove("show");
        }, timeoutMs);
    }
}
