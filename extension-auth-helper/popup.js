/**
 * FB Auto Post - Distributed Worker Node Popup Controller
 * extension-auth-helper/popup.js
 */

let _syncPort = 19823;
let _syncUrl = `http://127.0.0.1:${_syncPort}`;
let _syncToken = "";
let _projectKey = "taikhoan1";
let _instanceId = "";

function _updateSyncTarget(target) {
    if (!target) return;
    const s = String(target).trim();
    if (s.startsWith("http://") || s.startsWith("https://")) {
        _syncUrl = s.replace(/\/+$/, "");
        _syncPort = 0;
        return;
    }
    const port = parseInt(s, 10);
    if (!isNaN(port) && port >= 1 && port <= 65535) {
        _syncPort = port;
        _syncUrl = `http://127.0.0.1:${_syncPort}`;
    }
}

function _updateSyncPort(port) { _updateSyncTarget(port); }

function _getSyncHeaders(extra = {}) {
    const h = { ...extra };
    if (_syncToken) {
        h["X-Sync-Token"] = _syncToken;
        h["Authorization"] = `Bearer ${_syncToken}`;
    }
    if (_projectKey) h["X-Project-Key"] = _projectKey;
    if (_instanceId) h["X-Worker-Id"] = _instanceId;
    return h;
}

// DOM Elements
const dotBridge = document.getElementById("dotBridge");
const valBridge = document.getElementById("valBridge");
const dotTab = document.getElementById("dotTab");
const valTab = document.getElementById("valTab");
const valWorkerId = document.getElementById("valWorkerId");
const valProjectKey = document.getElementById("valProjectKey");

const btnCheck = document.getElementById("btnTest");
const btnRefresh = document.getElementById("btnRefresh");
const btnOpenDashboard = document.getElementById("btnOpenDashboard");
const btnExtractToken = document.getElementById("btnExtractToken");
const warmupToggle = document.getElementById("warmupToggle");

const resultBox = document.getElementById("resultBox");
const statTokens = document.getElementById("statTokens");
const statStatus = document.getElementById("statStatus");
const statLast = document.getElementById("statLast");

function _setIndicator(dot, type) {
    if (!dot) return;
    dot.className = `status-dot dot-${type}`;
}

function init() {
    chrome.storage.local.get([
        "syncPort", "syncTarget", "syncToken", "projectKey",
        "instanceId", "warmupEnabled", "lastSyncTime"
    ], (data) => {
        if (data) {
            if (data.syncTarget) _updateSyncTarget(data.syncTarget);
            else if (data.syncPort) _updateSyncTarget(data.syncPort);
            if (data.syncToken) _syncToken = String(data.syncToken).trim();
            if (data.projectKey) _projectKey = String(data.projectKey).trim();
            if (data.instanceId) _instanceId = String(data.instanceId).trim();

            if (valWorkerId) valWorkerId.textContent = _instanceId ? `node_${_instanceId.slice(-8)}` : "—";
            if (valProjectKey) valProjectKey.textContent = _projectKey;
            if (warmupToggle) warmupToggle.checked = !!data.warmupEnabled;
        }

        _pullSnapshot();
        _pingServer().catch(() => {});
        _checkFacebookTab().catch(() => {});

        setInterval(() => {
            _pingServer().catch(() => {});
            _checkFacebookTab().catch(() => {});
            _pullSnapshot();
        }, 5000);
    });

    chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName !== "local") return;
        if (changes.syncTarget) _updateSyncTarget(changes.syncTarget.newValue);
        else if (changes.syncPort) _updateSyncTarget(changes.syncPort.newValue);
        if (changes.syncToken) _syncToken = changes.syncToken.newValue ? String(changes.syncToken.newValue).trim() : "";
        if (changes.projectKey) {
            _projectKey = changes.projectKey.newValue ? String(changes.projectKey.newValue).trim() : "taikhoan1";
            if (valProjectKey) valProjectKey.textContent = _projectKey;
        }
        if (changes.instanceId) {
            _instanceId = String(changes.instanceId.newValue).trim();
            if (valWorkerId) valWorkerId.textContent = `node_${_instanceId.slice(-8)}`;
        }
        if (changes.warmupEnabled && warmupToggle) {
            warmupToggle.checked = !!changes.warmupEnabled.newValue;
        }
        _pullSnapshot();
    });

    // Warm-up toggle listener
    if (warmupToggle) {
        warmupToggle.addEventListener("change", () => {
            const enabled = warmupToggle.checked;
            chrome.storage.local.set({ warmupEnabled: enabled });
            chrome.runtime.sendMessage({ type: "TOGGLE_WARMUP", enabled }).catch(() => {});
            _showResult(`Nuôi nick tự động (Warm-up): ${enabled ? "BẬT" : "TẮT"}`, true);
        });
    }

    if (btnCheck) btnCheck.addEventListener("click", () => {
        _pingServer();
        _checkFacebookTab();
        _pullSnapshot();
    });

    if (btnRefresh) btnRefresh.addEventListener("click", () => {
        _pingServer();
        _checkFacebookTab();
        _pullSnapshot();
        _showResult("Đã làm mới trạng thái kết nối.", true);
    });

    if (btnOpenDashboard) btnOpenDashboard.addEventListener("click", () => {
        chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
    });

    if (btnExtractToken) btnExtractToken.addEventListener("click", async () => {
        btnExtractToken.disabled = true;
        btnExtractToken.textContent = "⏳ Đang trích xuất...";
        try {
            chrome.runtime.sendMessage({ type: "FETCH_FB_TOKEN" }, (res) => {
                btnExtractToken.disabled = false;
                btnExtractToken.textContent = "🔑 Tự Động Lấy Access Token FB";
                if (res && res.success) {
                    _showResult(`✅ Đã kết nối nick: ${res.fullName || res.name}`, true);
                    _checkFacebookTab();
                } else {
                    _showResult(`❌ Lỗi: ${res?.error || "Không tìm thấy token. Hãy mở tab Facebook và thử lại!"}`, false);
                }
            });
        } catch (e) {
            btnExtractToken.disabled = false;
            btnExtractToken.textContent = "🔑 Tự Động Lấy Access Token FB";
            _showResult(`Lỗi: ${e.message}`, false);
        }
    });
}

function _pullSnapshot() {
    try {
        chrome.runtime.sendMessage({ type: "GET_WORKER_STATUS" }, (res) => {
            if (chrome.runtime.lastError || !res) return;
            if (statStatus) {
                const s = res.status || "online";
                if (s === "busy") {
                    statStatus.textContent = "BUSY 🔵";
                    statStatus.style.color = "#3b82f6";
                } else if (s === "paused") {
                    statStatus.textContent = "PAUSED 🟡";
                    statStatus.style.color = "#f59e0b";
                } else {
                    statStatus.textContent = "ONLINE 🟢";
                    statStatus.style.color = "#22c55e";
                }
            }
        });
    } catch (e) {}

    try {
        chrome.storage.local.get(["scheduled_posts"], (data) => {
            const posts = data.scheduled_posts || [];
            const completed = posts.filter(p => p.status === "completed").length;
            if (statTokens) statTokens.textContent = completed;
        });
    } catch (e) {}
}

async function _pingServer() {
    try {
        const response = await fetch(`${_syncUrl}/api/accounts`, {
            headers: _getSyncHeaders(),
            signal: AbortSignal.timeout(3500)
        });
        if (response.ok) {
            _setIndicator(dotBridge, "ok");
            valBridge.textContent = "Connected";
            if (statLast) statLast.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        } else if (response.status === 401) {
            _setIndicator(dotBridge, "warn");
            valBridge.textContent = "401 Token Invalid";
        } else {
            _setIndicator(dotBridge, "warn");
            valBridge.textContent = `HTTP ${response.status}`;
        }
    } catch (e) {
        _setIndicator(dotBridge, "err");
        valBridge.textContent = "Offline";
    }
}

async function _checkFacebookTab() {
    try {
        const tabs = await chrome.tabs.query({});
        const fbTabs = tabs.filter(t => t.url && (t.url.includes("facebook.com") || t.url.includes("fb.com")));
        if (fbTabs.length > 0) {
            // Check cookie
            if (chrome.cookies) {
                chrome.cookies.get({ url: "https://www.facebook.com", name: "c_user" }, (cookie) => {
                    if (cookie && cookie.value) {
                        _setIndicator(dotTab, "ok");
                        valTab.textContent = `UID: ${cookie.value}`;
                    } else {
                        _setIndicator(dotTab, "warn");
                        valTab.textContent = "Chưa Đăng Nhập";
                    }
                });
            } else {
                _setIndicator(dotTab, "ok");
                valTab.textContent = `Mở (${fbTabs.length} tab)`;
            }
        } else {
            _setIndicator(dotTab, "warn");
            valTab.textContent = "Chưa mở Facebook";
        }
    } catch (e) {
        _setIndicator(dotTab, "err");
        valTab.textContent = "Lỗi kiểm tra tab";
    }
}

function _showResult(text, isSuccess) {
    if (!resultBox) return;
    resultBox.textContent = text;
    resultBox.className = `result-box show ${isSuccess ? "success" : "error"}`;
    setTimeout(() => {
        if (resultBox) resultBox.classList.remove("show");
    }, 4500);
}

document.addEventListener("DOMContentLoaded", init);
