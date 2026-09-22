
const DEFAULT_TARGET = "19823";
const inputTarget = document.getElementById("syncTarget");
const inputToken = document.getElementById("syncToken");
const btnSave = document.getElementById("btnSave");
const statusMsg = document.getElementById("statusMsg");

// Load settings
document.addEventListener("DOMContentLoaded", () => {
    try {
        chrome.storage.local.get(["syncPort", "syncTarget", "syncToken"], (data) => {
            if (chrome.runtime.lastError) {
                console.error("Error loading settings:", chrome.runtime.lastError);
                return;
            }
            if (data.syncTarget) {
                inputTarget.value = data.syncTarget;
            } else {
                inputTarget.value = data.syncPort || DEFAULT_TARGET;
            }
            if (data.syncToken) {
                inputToken.value = data.syncToken;
            }
        });
    } catch (e) {
        console.error("Storage API error:", e);
    }
});

// Save settings & test connection
btnSave.addEventListener("click", () => {
    const targetVal = (inputTarget.value || "").trim();
    const tokenVal = (inputToken.value || "").trim();

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
            syncToken: tokenVal
        };
        if (isPort) {
            saveData.syncPort = portNum;
        }

        chrome.storage.local.set(saveData, async () => {
            if (chrome.runtime.lastError) {
                showStatus(`Lỗi lưu cài đặt: ${chrome.runtime.lastError.message}`, "error");
                return;
            }

            const targetUrl = isUrl ? targetVal.replace(/\/+$/, "") : `http://127.0.0.1:${portNum}`;
            showStatus(`Đã lưu! Đang thử kết nối tới ${targetUrl}...`, "info", 0);

            try {
                const headers = {};
                if (tokenVal) headers["X-Sync-Token"] = tokenVal;

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

