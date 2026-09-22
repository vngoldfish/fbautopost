

// ===================================================================
// 🚀 FB AUTO POST — PRODUCTION DISTRIBUTED WORKER NODE (V7.1.0)
// ===================================================================

try {
    importScripts("warmup.js", "checkpoint.js");
} catch (e) {
    // Graceful fallback for non-worker environments (e.g. Node syntax check)
}

let _syncPort = 19823;
let _syncUrl = `http://127.0.0.1:${_syncPort}`;
let _syncToken = "";
let _projectKey = "taikhoan1";

// Synchronous ephemeral fallback worker identifier for ultra-early cold boot micro-races
const _ephemeralBootId = "node-boot-" + (
    (typeof crypto !== "undefined" && crypto.randomUUID)
        ? crypto.randomUUID().slice(0, 12)
        : (Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8))
);

let instanceId = null;
let instanceIdPromise = null;
let _storageInitPromise = null;

// ===================================================================
// 📡 AUTOMATIC GRAPHQL DOC_ID SNIFFER & DYNAMIC AUTO-CAPTURE
// ===================================================================
const _capturedDocIds = {
    ComposerStoryCreateMutation: "28329575890036120",
    useCometUFICreateCommentMutation: "27829190080054105",
    CometSinglePostDialogContentQuery: "25494545246909173",
    CometUFIFeedbackReactMutation: "27646120298312844"
};

try {
    chrome.storage.local.get(["capturedDocIds"], (res) => {
        if (res && res.capturedDocIds) {
            Object.assign(_capturedDocIds, res.capturedDocIds);
            console.log("📌 [Auto-Sniffer] Loaded cached live doc_ids:", _capturedDocIds);
        }
    });
} catch(e) {}

if (chrome.webRequest && chrome.webRequest.onBeforeRequest) {
    chrome.webRequest.onBeforeRequest.addListener(
        (details) => {
            if (details.method === "POST" && details.requestBody && details.requestBody.formData) {
                try {
                    const formData = details.requestBody.formData;
                    const fname = formData.fb_api_req_friendly_name ? formData.fb_api_req_friendly_name[0] : null;
                    const docId = formData.doc_id ? formData.doc_id[0] : null;
                    if (fname && docId) {
                        if (_capturedDocIds[fname] !== docId) {
                            _capturedDocIds[fname] = docId;
                            console.log(`✨ [Auto-Sniffer] Captured LIVE Facebook doc_id for '${fname}': ${docId}`);
                            chrome.storage.local.set({ capturedDocIds: _capturedDocIds });
                        }
                    }
                } catch(e) {}
            }
        },
        { urls: ["https://*.facebook.com/api/graphql/*", "https://*.facebook.com/graphql/*"] },
        ["requestBody"]
    );
}

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
    if (_syncToken) h["X-Sync-Token"] = _syncToken;
    if (_syncToken) h["Authorization"] = `Bearer ${_syncToken}`;
    if (_projectKey) h["X-Project-Key"] = _projectKey;

    // Defensive fallback: ensure X-Worker-Id is never omitted during early cold-start boot
    const effectiveWorkerId = (typeof instanceId === "string" && instanceId) ? instanceId : _ephemeralBootId;
    if (typeof effectiveWorkerId === "string" && effectiveWorkerId) h["X-Worker-Id"] = effectiveWorkerId;
    if (typeof instanceId === "string" && instanceId) h["X-Worker-Id"] = instanceId;

    return h;
}

async function initStorageConfig() {
    if (_storageInitPromise) return _storageInitPromise;
    _storageInitPromise = (async () => {
        try {
            if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                const data = await chrome.storage.local.get([
                    "syncPort",
                    "syncTarget",
                    "syncToken",
                    "projectKey",
                    "warmupEnabled",
                    "instanceId"
                ]);
                if (data) {
                    if (data.syncTarget) {
                        _updateSyncTarget(data.syncTarget);
                    } else if (data.syncPort) {
                        _updateSyncTarget(data.syncPort);
                    }
                    if (data.syncToken) {
                        _syncToken = String(data.syncToken).trim();
                    }
                    if (data.projectKey) {
                        _projectKey = String(data.projectKey).trim();
                    }
                    if (typeof data.warmupEnabled !== "undefined") {
                        _warmupEnabled = !!data.warmupEnabled;
                    }
                    if (data.instanceId && typeof data.instanceId === "string") {
                        instanceId = data.instanceId;
                    }
                }
            }
        } catch (e) {
            // Graceful fallback for non-extension environments (e.g. Node syntax check)
        }
    })();
    return _storageInitPromise;
}

// Immediately trigger eager configuration load
initStorageConfig().catch(() => {});

if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName !== "local") return;
        if (changes.syncTarget) {
            _updateSyncTarget(changes.syncTarget.newValue);
        } else if (changes.syncPort) {
            _updateSyncTarget(changes.syncPort.newValue);
        }
        if (changes.syncToken) {
            _syncToken = changes.syncToken.newValue ? String(changes.syncToken.newValue).trim() : "";
        }
        if (changes.projectKey) {
            _projectKey = changes.projectKey.newValue ? String(changes.projectKey.newValue).trim() : "taikhoan1";
        }
        if (changes.warmupEnabled) {
            _warmupEnabled = !!changes.warmupEnabled.newValue;
        }
        if (changes.instanceId && changes.instanceId.newValue) {
            instanceId = String(changes.instanceId.newValue).trim();
        }
    });
}
// ===================================================================
// 🖥️ DISTRIBUTED WORKER NODE ENGINE & STATE MACHINE (R1 & R2)
// ===================================================================

let _isProcessingPosts = false;
let _isExecutingTask = false;
let _activeExecutingTaskId = null;
let _isPaused = false;
let _warmupEnabled = false;
let _lastExtractedAccount = null;
let _checkpointDetected = false;
let _checkpointWatchdog = null;

async function getInstanceId() {
    if (instanceId) return instanceId;

    if (_storageInitPromise) {
        await _storageInitPromise;
        if (instanceId) return instanceId;
    }

    if (!instanceIdPromise) {
        instanceIdPromise = (async () => {
            try {
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                    const data = await chrome.storage.local.get(["instanceId"]);
                    if (data && data.instanceId && typeof data.instanceId === "string") {
                        instanceId = data.instanceId;
                        return instanceId;
                    }
                }
            } catch (e) { }
            const fresh = (typeof crypto !== "undefined" && crypto.randomUUID && crypto.randomUUID()) ||
                (Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
            try {
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                    await chrome.storage.local.set({ instanceId: fresh });
                }
            } catch (e) { }
            instanceId = fresh;
            return fresh;
        })();
    }
    instanceId = await instanceIdPromise;
    return instanceId;
}

// Eagerly resolve worker instanceId at top-level execution scope
getInstanceId().catch(() => {});

// Asynchronous storage ready gatekeeper for background network routines
async function _ensureStorageReady() {
    if (_storageInitPromise) await _storageInitPromise;
    if (!instanceId) await getInstanceId();
}

async function _uploadImageToBackend() {
    await _ensureStorageReady();
}

// Initialize CheckpointWatchdog if available
try {
    if (typeof CheckpointWatchdog !== "undefined") {
        _checkpointWatchdog = new CheckpointWatchdog({
            syncUrl: _syncUrl,
            getHeaders: () => _getSyncHeaders()
        });
        _checkpointWatchdog.setOnCheckpoint((info) => {
            _checkpointDetected = true;
            console.warn("?? [Watchdog] Account checkpoint event:", info);
        });
    }
} catch (e) {}

// Alarms setup (compliant with MV3 service worker lifecycle)
chrome.alarms.create("workerHeartbeat", { periodInMinutes: 0.25 });
chrome.alarms.create("taskQueuePoll", { periodInMinutes: 0.25 });
chrome.alarms.create("autoPostCheck", { periodInMinutes: 0.25 });
chrome.alarms.create("autoReplyCheck", { periodInMinutes: 1.0 });

// Active foreground loop (every 15s)
setInterval(() => {
    sendWorkerHeartbeat().catch(() => {});
    pollAndExecuteDistributedTask().catch(() => {});
    _processScheduledPosts().catch(() => {});
    _processAutoReplyMonitor().catch(() => {});
}, 15000);

// Alarms listener
chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name === "workerHeartbeat") sendWorkerHeartbeat();
    if (alarm.name === "taskQueuePoll") pollAndExecuteDistributedTask();
    if (alarm.name === "autoPostCheck") _processScheduledPosts();
    if (alarm.name === "autoReplyCheck") _processAutoReplyMonitor();
});

// Port keep-alive listener from content.js
chrome.runtime.onConnect.addListener((port) => {
    if (port.name === "worker_heartbeat_port") {
        port.onMessage.addListener(() => {
            // Keep service worker awake
        });
    }
});

// Listen for tab URL changes to detect checkpoints
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.url && tab.url.includes("facebook.com")) {
        _extractFacebookAccessToken().catch(() => {});
        if (typeof checkUrlForCheckpoint === "function") {
            const check = checkUrlForCheckpoint(tab.url);
            if (check.isCheckpoint) {
                _checkpointDetected = true;
                if (_checkpointWatchdog) {
                    await _checkpointWatchdog.triggerAlert("url_redirect", check.type, "Redirected to " + tab.url);
                }
            }
        }
    }
});

// Listen for cookie changes (detect session logouts)
try {
    if (chrome.cookies && chrome.cookies.onChanged) {
        chrome.cookies.onChanged.addListener((changeInfo) => {
            if (changeInfo.cookie && changeInfo.cookie.domain && changeInfo.cookie.domain.includes("facebook.com")) {
                if (changeInfo.cookie.name === "c_user" && changeInfo.removed) {
                    console.warn("?? [Watchdog] c_user cookie removed -> Session Expired");
                    _checkpointDetected = true;
                    if (_checkpointWatchdog) {
                        _checkpointWatchdog.triggerAlert("cookie_missing", "expired", "c_user cookie removed by browser/Facebook");
                    }
                }
            }
        });
    }
} catch (e) {}

/**
 * Registers this Chrome Extension instance as a Worker Node with the backend server.
 * POST /api/workers/register
 */
async function registerWorkerNode() {
    try {
        const workerId = await getInstanceId();
        let assignedAccs = [];
        if (_lastExtractedAccount && _lastExtractedAccount.targetId) {
            assignedAccs.push(_lastExtractedAccount.targetId);
        }

        const payload = {
            workerId: workerId,
            name: "Node-" + workerId.slice(-6),
            projectKey: _projectKey || "taikhoan1",
            version: "7.1.0",
            assignedAccounts: assignedAccs
        };

        const res = await fetch(_syncUrl + "/api/workers/register", {
            method: "POST",
            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(6000)
        });

        if (res.ok) {
            const data = await res.json();
            console.log("? [WorkerNode] Registered with backend:", data.workerId);
        }
    } catch (err) {
        console.warn("?? [WorkerNode] Registration failed (will retry):", err.message);
    }
}

/**
 * Transmits 15-second heartbeat to backend server.
 * POST /api/workers/heartbeat
 */
async function sendWorkerHeartbeat() {
    try {
        const workerId = await getInstanceId();
        let statusVal = _activeExecutingTaskId ? "busy" : (_isPaused ? "paused" : "idle");

        let accList = [];
        if (_lastExtractedAccount && _lastExtractedAccount.targetId) {
            accList.push({
                targetId: _lastExtractedAccount.targetId,
                name: _lastExtractedAccount.name || "",
                status: _checkpointDetected ? "checkpoint" : "live"
            });
        }

        const payload = {
            workerId: workerId,
            projectKey: _projectKey || "taikhoan1",
            status: statusVal,
            currentTaskId: _activeExecutingTaskId || null,
            accounts: accList
        };

        const res = await fetch(_syncUrl + "/api/workers/heartbeat", {
            method: "POST",
            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(5000)
        });

        if (res.ok) {
            const data = await res.json();
            if (data.hasPendingTasks && !_activeExecutingTaskId && !_isExecutingTask) {
                pollAndExecuteDistributedTask().catch(() => {});
            }
        }
    } catch (e) {
        // Server might be temporarily unreachable
    }
}

/**
 * Finds or creates a Facebook tab for automation.
 */
async function _findOrCreateFacebookTab(targetUrl = "https://www.facebook.com") {
    try {
        const tabs = await chrome.tabs.query({ url: "*://*.facebook.com/*" });
        let fbTab = tabs.find(t => t.active && t.url && t.url.includes("facebook.com")) || tabs.find(t => t.url && t.url.includes("facebook.com"));
        if (!fbTab) {
            fbTab = await chrome.tabs.create({ url: targetUrl, active: false });
            await ensureTabLoaded(fbTab.id, 10000);
        }
        return fbTab;
    } catch (e) {
        return null;
    }
}

/**
 * Distributed Task Queue Consumer:
 * Atomically claims task from POST /api/tasks/poll, executes it via Direct GraphQL or DOM fallback,
 * and reports status via POST /api/tasks/{id}/status.
 */
async function pollAndExecuteDistributedTask() {
    if (_isExecutingTask || _isPaused) return;

    try {
        const workerId = await getInstanceId();
        const pollRes = await fetch(_syncUrl + "/api/tasks/poll", {
            method: "POST",
            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                workerId: workerId,
                projectKey: _projectKey || "taikhoan1",
                supportedTypes: ["post", "seed", "warmup", "reply_comment"]
            }),
            signal: AbortSignal.timeout(8000)
        });

        if (!pollRes.ok) return;
        const pollData = await pollRes.json();
        const task = pollData.task;
        if (!task) return;

        _isExecutingTask = true;
        _activeExecutingTaskId = task.id;
        console.log("?? [WorkerNode] Claimed distributed task " + task.id + " (type: " + task.type + ")");

        // Checkpoint guard: If account is currently in checkpoint, fail task immediately
        if (_checkpointDetected) {
            console.warn("? [WorkerNode] Aborting task " + task.id + " due to detected account checkpoint.");
            await fetch(_syncUrl + "/api/tasks/" + task.id + "/status", {
                method: "POST",
                headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({
                    workerId: workerId,
                    status: "failed",
                    error: "Account is in checkpoint/restricted status"
                }),
                signal: AbortSignal.timeout(5000)
            }).catch(() => {});
            _activeExecutingTaskId = null;
            _isExecutingTask = false;
            return;
        }

        // Acknowledge task running
        await fetch(_syncUrl + "/api/tasks/" + task.id + "/status", {
            method: "POST",
            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                workerId: workerId,
                status: "running"
            }),
            signal: AbortSignal.timeout(5000)
        }).catch(() => {});

        // Periodic lease extension (every 25s for long tasks)
        const leaseWatchdog = setInterval(async () => {
            try {
                await fetch(_syncUrl + "/api/tasks/" + task.id + "/heartbeat", {
                    method: "POST",
                    headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                    body: JSON.stringify({ extendSec: 60 }),
                    signal: AbortSignal.timeout(4000)
                });
            } catch (e) {}
        }, 25000);

        let taskResult = { success: false, error: "Task execution unhandled" };

        try {
            if (task.type === "post") {
                const p = task.payload || {};
                const parsedContent = typeof parseSpintax === "function" ? parseSpintax(p.content || p.caption || p.text || "") : (p.content || p.caption || p.text || "");
                const postItem = {
                    id: task.id,
                    postType: p.postType || "post",
                    content: parsedContent,
                    mediaUrl: p.mediaUrl || (Array.isArray(p.mediaUrls) ? p.mediaUrls[0] : ""),
                    mediaData: p.mediaData || null,
                    targetType: p.targetType || "profile",
                    targetId: p.targetId || "",
                    actorId: p.actorId || "",
                    seedingComments: p.seedingComments || [],
                    autoReactType: p.autoReactType || "NONE"
                };
                taskResult = await _executePostItem(postItem);
            } else if (task.type === "seed") {
                const p = task.payload || {};
                const postId = p.postId || "";
                const comments = p.comments || p.seedingComments || [];
                const minDelay = (p.minDelaySec || 3) * 1000;
                const maxDelay = (p.maxDelaySec || 10) * 1000;
                let count = 0;
                const fbTab = await _findOrCreateFacebookTab(p.postUrl || "https://www.facebook.com");
                if (fbTab && typeof sendCommentGraphQL === "function") {
                    for (const cmt of comments) {
                        const text = typeof parseSpintax === "function" ? parseSpintax(cmt) : cmt;
                        const cRes = await sendCommentGraphQL(fbTab.id, postId, text);
                        if (cRes?.success) count++;
                        const delay = minDelay + Math.random() * (maxDelay - minDelay);
                        await new Promise(r => setTimeout(r, delay));
                    }
                    if (p.autoReactType && p.autoReactType !== "NONE" && typeof sendReactionGraphQL === "function") {
                        await sendReactionGraphQL(fbTab.id, postId, p.autoReactType);
                    }
                    taskResult = { success: true, commentsPosted: count, postId };
                } else {
                    taskResult = { success: false, error: "Facebook tab unavailable for seeding" };
                }
            } else if (task.type === "warmup") {
                const p = task.payload || {};
                const fbTab = await _findOrCreateFacebookTab("https://www.facebook.com");
                if (fbTab && typeof runWarmupSession === "function") {
                    taskResult = await runWarmupSession(fbTab.id, p.warmupConfig || p, (step) => {
                        chrome.tabs.sendMessage(fbTab.id, { type: "POST_STATUS_UPDATE", message: step }).catch(() => {});
                    });
                } else {
                    taskResult = { success: false, error: "Facebook tab unavailable for warm-up" };
                }
            } else if (task.type === "reply_comment") {
                const p = task.payload || {};
                const fbTab = await _findOrCreateFacebookTab(p.postUrl || "https://www.facebook.com");
                if (fbTab && typeof sendCommentGraphQL === "function") {
                    const replyText = typeof parseSpintax === "function" ? parseSpintax(p.replyText || "") : (p.replyText || "");
                    const targetId = p.targetCommentId || p.postId;
                    const rRes = await sendCommentGraphQL(fbTab.id, targetId, replyText);
                    if (p.autoReactType && p.autoReactType !== "NONE" && typeof sendReactionGraphQL === "function") {
                        await sendReactionGraphQL(fbTab.id, targetId, p.autoReactType);
                    }
                    taskResult = { success: rRes?.success || false, error: rRes?.error, result: rRes };
                } else {
                    taskResult = { success: false, error: "Facebook tab unavailable for reply" };
                }
            }
        } finally {
            clearInterval(leaseWatchdog);
        }

        const isSuccess = !!(taskResult && taskResult.success);
        const errorDetail = isSuccess ? null : (taskResult?.error || "Task execution failed");
        console.log("?? [WorkerNode] Task " + task.id + " finished: success=" + isSuccess + ", error=" + errorDetail);

        await fetch(_syncUrl + "/api/tasks/" + task.id + "/status", {
            method: "POST",
            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                workerId: workerId,
                status: isSuccess ? "completed" : "failed",
                result: taskResult || {},
                error: errorDetail
            }),
            signal: AbortSignal.timeout(5000)
        }).catch(() => {});

    } catch (err) {
        console.warn("?? [WorkerNode] Task queue polling error:", err.message);
    } finally {
        _activeExecutingTaskId = null;
        _isExecutingTask = false;
    }
}

// Initial worker startup registration
chrome.runtime.onInstalled.addListener(() => { registerWorkerNode(); });
chrome.runtime.onStartup.addListener(() => { registerWorkerNode(); });
setTimeout(() => { registerWorkerNode(); }, 1500);



async function ensureTabLoaded(tabId, maxWaitMs = 12000) {
    const startTime = Date.now();
    while (Date.now() - startTime < maxWaitMs) {
        try {
            const tab = await chrome.tabs.get(tabId);
            if (tab && tab.status === "complete") {
                await new Promise(r => setTimeout(r, 300));
                return true;
            }
        } catch (e) {}
        await new Promise(r => setTimeout(r, 300));
    }
    return false;
}

const _activeExecutingPostIds = new Set();

async function _processScheduledPosts() {
    await _ensureStorageReady();
    if (_isProcessingPosts) return;
    _isProcessingPosts = true;
    try {
        const now = Date.now();

        // 1. Process local extension scheduled posts
        const data = await chrome.storage.local.get(["scheduled_posts"]);
        let posts = data.scheduled_posts || [];
        let changed = false;

        for (let i = 0; i < posts.length; i++) {
            const post = posts[i];
            if (post.status === "pending" && post.scheduledTime <= now && !_activeExecutingPostIds.has(post.id)) {
                _activeExecutingPostIds.add(post.id);
                post.status = "in_progress";
                changed = true;
                await chrome.storage.local.set({ scheduled_posts: posts });

                _executePostItem(post).then((res) => {
                    _activeExecutingPostIds.delete(post.id);
                    chrome.storage.local.get(["scheduled_posts"], (latestData) => {
                        let currentPosts = latestData.scheduled_posts || [];
                        const targetIdx = currentPosts.findIndex(p => p.id === post.id);
                        if (targetIdx !== -1) {
                            if (res.success) {
                                currentPosts[targetIdx].status = "completed";
                                currentPosts[targetIdx].lastError = null;
                                if (currentPosts[targetIdx].repeatIntervalMinutes > 0) {
                                    currentPosts[targetIdx].status = "pending";
                                    currentPosts[targetIdx].scheduledTime = Date.now() + (currentPosts[targetIdx].repeatIntervalMinutes * 60000);
                                }
                            } else {
                                currentPosts[targetIdx].retryCount = (currentPosts[targetIdx].retryCount || 0) + 1;
                                currentPosts[targetIdx].lastError = res.error || "Unknown error";
                                if (currentPosts[targetIdx].retryCount >= (currentPosts[targetIdx].maxRetries || 3)) {
                                    currentPosts[targetIdx].status = "failed";
                                } else {
                                    currentPosts[targetIdx].status = "pending";
                                    currentPosts[targetIdx].scheduledTime = Date.now() + 60000;
                                }
                            }
                            chrome.storage.local.set({ scheduled_posts: currentPosts });
                        }
                    });
                });
            }
        }

        if (changed) {
            await chrome.storage.local.set({ scheduled_posts: posts });
        }

        // 2. Process Python Backend scheduled posts
        try {
            const backendRes = await fetch(`${_syncUrl}/api/posts?status=pending`, { headers: _getSyncHeaders(), signal: AbortSignal.timeout(30000) });
            if (backendRes.ok) {
                const backendData = await backendRes.json();
                const backendPending = backendData.posts || [];
                        for (const p of backendPending) {
                    if (p.scheduledTime <= now && !_activeExecutingPostIds.has(p.id)) {
                        _activeExecutingPostIds.add(p.id);

                        // Safety Watchdog Timer (60s): Release post ID lock if stuck
                        const lockWatchdog = setTimeout(() => {
                            _activeExecutingPostIds.delete(p.id);
                        }, 60000);

                        console.log("📌 [Extension] Processing backend pending post:", p.id, "hasMedia:", !!p.mediaData);
                        _executePostItem(p).then(async (res) => {
                            try {
                                const newStatus = (res && res.success) ? "completed" : "failed";
                                const errDetail = (res && res.success) ? null : (res?.error || "Execution failed");
                                const method = res?.method || "auto";
                                const finalStep = (res && res.success)
                                    ? `🎉 Đã đăng thành công qua [${method.toUpperCase()}]!`
                                    : `❌ Đăng thất bại: ${errDetail}`;

                                console.log(`📌 [Extension] Post ${p.id} finished: status=${newStatus}, step=${finalStep}`);
                                await fetch(`${_syncUrl}/api/posts/${p.id}`, {
                                    method: "PATCH",
                                    headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                                    body: JSON.stringify({
                                        status: newStatus,
                                        progressStep: finalStep,
                                        executedAt: Date.now(),
                                        lastError: errDetail,
                                        executionMethod: method,
                                        fbPostId: res?.fbPostId || null,
                                        fbPostUrl: res?.fbPostUrl || null
                                    }),
                                    signal: AbortSignal.timeout(5000)
                                });
                            } catch (sErr) { console.warn("⚠️ Status update error:", sErr.message); }
                        }).finally(() => {
                            clearTimeout(lockWatchdog);
                            _activeExecutingPostIds.delete(p.id);
                        });
                    }
                }
            }
        } catch (backendErr) { console.warn("⚠️ [Extension] Backend fetch error:", backendErr.message); }
    } catch (e) {
        console.error("Error processing scheduled posts:", e);
    } finally {
        _isProcessingPosts = false;
    }
}

async function _uploadMediaToFacebook(tabId, fileBase64, fileName, mimeType) {
    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: "MAIN",
            func: async (base64Data, fName, fMime) => {
                try {
                    // ===== Extract ALL security tokens =====
                    let fb_dtsg = "";
                    let lsd = "";
                    let jazoest = "";
                    let spinR = "";
                    let spinB = "";
                    let spinT = "";
                    let hsi = "";

                    const html = document.documentElement.innerHTML;

                    // fb_dtsg
                    const dtsgPatterns = [
                        /\["DTSGInitialData",\[\],\{"token":"([^"]+)"/,
                        /\["DTSGInitData",\[\],\{"token":"([^"]+)"/,
                        /"DTSGInitialData"[^}]*"token":"([^"]+)"/,
                        /"dtsg":\{"token":"([^"]+)"/,
                    ];
                    for (const p of dtsgPatterns) {
                        const m = html.match(p);
                        if (m && m[1]) { fb_dtsg = m[1]; break; }
                    }
                    if (!fb_dtsg && typeof require !== "undefined") {
                        try {
                            const mod = require("DTSGInitData") || require("DTSGInitialData");
                            if (mod && mod.token) fb_dtsg = mod.token;
                        } catch(e) {}
                    }

                    // lsd
                    const lsdM = html.match(/\["LSD",\[\],\{"token":"([^"]+)"/) || html.match(/"lsd":"([^"]+)"/);
                    if (lsdM) lsd = lsdM[1];

                    // jazoest
                    const jazoM = html.match(/jazoest=(\d+)/);
                    if (jazoM) jazoest = jazoM[1];

                    // spin tokens + hsi
                    const spinM = html.match(/"__spin_t":(\d+),"__spin_r":(\d+),"__spin_b":"([^"]+)","__hsi":"([^"]+)"/);
                    if (spinM) { spinT = spinM[1]; spinR = spinM[2]; spinB = spinM[3]; hsi = spinM[4]; }

                    let userId = "";
                    const cUserMatch = document.cookie.match(/c_user=(\d+)/) ||
                                      html.match(/"USER_ID":"(\d+)"/) ||
                                      html.match(/"ACCOUNT_ID":"(\d+)"/) ||
                                      html.match(/\["CurrentUserInitialData",\[\],\{"ACCOUNT_ID":"(\d+)"/);
                    if (cUserMatch && cUserMatch[1]) userId = cUserMatch[1];

                    if (!fb_dtsg || !userId) {
                        return { success: false, error: "Missing fb_dtsg or userId" };
                    }

                    // ===== Convert base64 to Blob =====
                    const byteStr = atob(base64Data);
                    const ab = new ArrayBuffer(byteStr.length);
                    const ia = new Uint8Array(ab);
                    for (let i = 0; i < byteStr.length; i++) ia[i] = byteStr.charCodeAt(i);
                    const blob = new Blob([ab], { type: fMime });

                    // ===== Build URL params (matching real Facebook request) =====
                    const urlParams = new URLSearchParams();
                    urlParams.append("av", userId);
                    urlParams.append("__aaid", "0");
                    urlParams.append("__user", userId);
                    urlParams.append("__a", "1");
                    urlParams.append("__req", Math.floor(Math.random()*100).toString(36));
                    urlParams.append("__hs", hsi || "");
                    urlParams.append("dpr", "2");
                    urlParams.append("__ccg", "EXCELLENT");
                    urlParams.append("__rev", spinR);
                    urlParams.append("__s", [1,2,3].map(()=>Math.random().toString(36).substr(2,6)).join(":"));
                    urlParams.append("__hsi", hsi);
                    urlParams.append("__comet_req", "15");
                    urlParams.append("fb_dtsg", fb_dtsg);
                    urlParams.append("jazoest", jazoest);
                    urlParams.append("lsd", lsd);
                    urlParams.append("__spin_r", spinR);
                    urlParams.append("__spin_b", spinB);
                    urlParams.append("__spin_t", spinT);

                    // ===== Upload via FormData to REAL endpoint =====
                    const formData = new FormData();
                    formData.append("farr", blob, fName);
                    formData.append("file", blob, fName);
                    formData.append("photo", blob, fName);
                    formData.append("source", "8");
                    formData.append("profile_id", userId);
                    formData.append("waterfallxapp", "comet");
                    formData.append("upload_speed", "0");

                    const isVideo = fMime.startsWith("video/") || (fName && fName.match(/\.(mp4|mov|avi|mkv|webm)$/i));
                    if (isVideo) {
                        // ===== NATIVE VUPLOAD PROTOCOL (matches production flow from facebook.com.har) =====
                        // Step 1: vupload-edge/start → get video_id + upload_session_id
                        // Step 2: rupload POST binary → get hash h
                        // Step 3: vupload-edge/receive → confirm upload complete
                        console.log("🎬 [Background] Video file detected — Using native vupload-edge protocol");

                        const waterfallId = crypto.randomUUID ? crypto.randomUUID() : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16));
                        const fileSize = byteStr.length;

                        // Build common FB params
                        const fbParams = new URLSearchParams();
                        fbParams.append("__aaid", "0");
                        fbParams.append("__user", userId);
                        fbParams.append("__a", "1");
                        fbParams.append("__comet_req", "15");
                        fbParams.append("fb_dtsg", fb_dtsg);
                        fbParams.append("jazoest", jazoest);
                        fbParams.append("lsd", lsd);
                        fbParams.append("__spin_r", spinR);
                        fbParams.append("__spin_b", spinB);
                        fbParams.append("__spin_t", spinT);
                        fbParams.append("__hsi", hsi);
                        fbParams.append("dpr", "2");
                        fbParams.append("__ccg", "EXCELLENT");
                        fbParams.append("__rev", spinR);

                        // --- STEP 1: START ---
                        const startParams = new URLSearchParams(fbParams);
                        startParams.append("waterfall_id", waterfallId);
                        startParams.append("target_id", userId);
                        startParams.append("source", "composer");
                        startParams.append("composer_entry_point_ref", "timeline");
                        startParams.append("supports_chunking", "true");
                        startParams.append("supports_file_api", "true");
                        startParams.append("file_size", fileSize.toString());
                        startParams.append("file_extension", fName.split(".").pop() || "mp4");
                        startParams.append("partition_start_offset", "0");
                        startParams.append("partition_end_offset", fileSize.toString());
                        startParams.append("has_file_been_replaced", "false");

                        const startResp = await fetch(`https://vupload-edge.facebook.com/ajax/video/upload/requests/start/?av=${userId}&__a=1`, {
                            method: "POST",
                            body: startParams.toString(),
                            headers: {
                                "Content-Type": "application/x-www-form-urlencoded",
                                "X_FB_VIDEO_WATERFALL_ID": waterfallId,
                            },
                            credentials: "include",
                        });
                        const startText = await startResp.text();
                        const startClean = startText.replace(/^for\s*\(;+\)\s*;?\s*/, "");
                        const startData = JSON.parse(startClean);
                        const videoId = startData?.payload?.video_id;
                        const uploadSessionId = startData?.payload?.upload_session_id;
                        const chunkEnd = startData?.payload?.end_offset || fileSize;

                        if (!videoId || !uploadSessionId) {
                            console.error("❌ vupload start failed:", startData);
                            return { success: false, error: "vupload start failed: no video_id", details: startClean.substring(0, 300) };
                        }
                        console.log(`✅ [vupload] START OK → video_id=${videoId}, session=${uploadSessionId}, chunk_end=${chunkEnd}`);

                        // --- STEP 2: RUPLOAD binary ---
                        const sessionHash = Array.from(crypto.getRandomValues(new Uint8Array(16))).map(b => b.toString(16).padStart(2,"0")).join("");
                        const ruploadUrl = `https://rupload.facebook.com/fb_video/${sessionHash}-0-${chunkEnd}?` + fbParams.toString();

                        const ruploadResp = await fetch(ruploadUrl, {
                            method: "POST",
                            body: ab,  // raw ArrayBuffer with video binary
                            headers: {
                                "X-Entity-Name": fName,
                                "X-Entity-Length": fileSize.toString(),
                                "X-Entity-Type": fMime,
                                "X-Total-Asset-Size": fileSize.toString(),
                                "Composer_Session_Id": waterfallId,
                                "Id": uploadSessionId,
                                "Product_Media_Id": videoId,
                                "Offset": "0",
                                "Start_Offset": "0",
                                "End_Offset": chunkEnd.toString(),
                            },
                            credentials: "include",
                        });
                        const ruploadText = await ruploadResp.text();
                        let ruploadHash = "";
                        try {
                            const ruploadData = JSON.parse(ruploadText);
                            ruploadHash = ruploadData?.h || "";
                        } catch(e) {}
                        console.log(`✅ [vupload] RUPLOAD OK → hash=${ruploadHash.substring(0,40)}...`);

                        // --- STEP 3: RECEIVE (confirm upload complete) ---
                        const receiveParams = new URLSearchParams(fbParams);
                        receiveParams.append("waterfall_id", waterfallId);
                        receiveParams.append("target_id", userId);
                        receiveParams.append("video_id", videoId);
                        receiveParams.append("source", "composer");
                        receiveParams.append("composer_entry_point_ref", "timeline");
                        receiveParams.append("supports_chunking", "true");
                        receiveParams.append("supports_upload_service", "true");
                        receiveParams.append("partition_start_offset", "0");
                        receiveParams.append("partition_end_offset", fileSize.toString());
                        receiveParams.append("start_offset", "0");
                        receiveParams.append("end_offset", fileSize.toString());
                        receiveParams.append("upload_speed", Math.round(fileSize / 1.5).toString());
                        if (ruploadHash) {
                            receiveParams.append("fbuploader_video_file_chunk", ruploadHash);
                        }
                        receiveParams.append("has_file_been_replaced", "false");

                        const receiveResp = await fetch(`https://vupload-edge.facebook.com/ajax/video/upload/requests/receive/?av=${userId}&__a=1`, {
                            method: "POST",
                            body: receiveParams.toString(),
                            headers: {
                                "Content-Type": "application/x-www-form-urlencoded",
                                "X_FB_VIDEO_WATERFALL_ID": waterfallId,
                            },
                            credentials: "include",
                        });
                        const receiveText = await receiveResp.text();
                        const receiveClean = receiveText.replace(/^for\s*\(;+\)\s*;?\s*/, "");
                        const receiveData = JSON.parse(receiveClean);
                        const confirmedEnd = receiveData?.payload?.end_offset;

                        console.log(`✅ [vupload] RECEIVE OK → confirmed end_offset=${confirmedEnd}`);

                        if (confirmedEnd >= fileSize) {
                            console.log(`🎬 [vupload] Video upload COMPLETE! video_id=${videoId}`);
                            return { success: true, mediaId: videoId, isVideo: true };
                        } else {
                            console.warn(`⚠️ [vupload] Partial upload: confirmed=${confirmedEnd}, total=${fileSize}`);
                            return { success: true, mediaId: videoId, isVideo: true, partial: true };
                        }
                    }

                    const endpointPath = isVideo ? "/ajax/react_composer/attachments/video/upload?" : "/ajax/react_composer/attachments/photo/upload?";
                    const uploadUrl = "https://upload.facebook.com" + endpointPath + urlParams.toString();

                    let resp = await fetch(uploadUrl, {
                        method: "POST",
                        body: formData,
                        credentials: "include",
                    });

                    const text = await resp.text();
                    const clean = text.replace(/^for\s*\(;+\)\s*;?\s*/, "");

                    // Extract photo / video ID from response
                    const idPatterns = [
                        /"video_id"\s*:\s*"?(\d+)"?/,
                        /"videoId"\s*:\s*"?(\d+)"?/,
                        /"photoID"\s*:\s*"?(\d+)"?/,
                        /"photo_id"\s*:\s*"?(\d+)"?/,
                        /"media_id"\s*:\s*"?(\d+)"?/,
                        /"fbid"\s*:\s*"?(\d+)"?/,
                        /"id"\s*:\s*"?(\d+)"?/,
                    ];

                    for (const p of idPatterns) {
                        const m = clean.match(p);
                        if (m && m[1]) {
                            return { success: true, mediaId: m[1] };
                        }
                    }

                    return { success: false, error: "No photo ID in response", status: resp.status, preview: clean.substring(0, 500) };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            },
            args: [fileBase64, fileName, mimeType]
        });

        return results && results[0] && results[0].result;
    } catch (e) {
        return { success: false, error: e.message };
    }
}

// Store pending post results from content.js
// const _pendingPostResults = new Map();

async function _executePostItem(post) {
    try {
        const extId = await getInstanceId();
        const postType = post.postType || post.type || "post";
        const payload = {
            id: post.id,
            postType: postType,
            content: post.content || "",
            mediaUrl: post.mediaUrl || "",
            mediaData: post.mediaData || null,
            targetUrl: post.targetUrl || "",
            targetType: post.targetType || "profile",
            targetId: post.targetId || "",
            actorId: post.actorId || "",
            seedingComments: post.seedingComments || [],
            autoReplyComments: post.autoReplyComments || [],
            autoReactType: post.autoReactType || "NONE",
            onlyAction: post.onlyAction || null,
            targetCommentId: post.targetCommentId || null,
            timestamp: Date.now()
        };

        // Helper to update progress step to backend AND active Facebook tab screen
        let targetTab = null;
        const updateStep = async (stepText) => {
            try {
                console.log(`📌 [Step Progress] ${post.id}: ${stepText}`);
                // 1. Update Python backend
                await fetch(`${_syncUrl}/api/posts/${post.id}`, {
                    method: "PATCH",
                    headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                    body: JSON.stringify({ progressStep: stepText, status: "in_progress" }),
                    signal: AbortSignal.timeout(4000)
                });

                // 2. Broadcast live HUD status banner to active Facebook tab
                if (targetTab && targetTab.id) {
                    try {
                        await chrome.tabs.sendMessage(targetTab.id, { type: "POST_STATUS_UPDATE", message: stepText });
                    } catch(e) {}
                }
            } catch(e) {}
        };

        await updateStep("🚀 1/4: Đã nhận lệnh, đang khởi động tab Facebook...");

        // 2. Find or create Facebook tab
        let targetFbUrl = post.targetUrl;
        if (!targetFbUrl || !targetFbUrl.includes("facebook.com")) {
            if (postType === "reel") {
                targetFbUrl = "https://www.facebook.com/reels/create";
            } else if (postType === "story") {
                targetFbUrl = "https://www.facebook.com/stories/create";
            } else {
                targetFbUrl = "https://www.facebook.com";
            }
        }

        const tabs = await chrome.tabs.query({});
        targetTab = tabs.find(t => t.active && t.url && t.url.includes("facebook.com")) || tabs.find(t => t.url && t.url.includes("facebook.com"));
        if (!targetTab) {
            targetTab = await chrome.tabs.create({ url: targetFbUrl, active: false });
        }

        if (!targetTab || !targetTab.id) {
            return { success: false, error: "No Facebook tab available" };
        }

        // Ensure tab is fully loaded
        await ensureTabLoaded(targetTab.id);
        await new Promise(r => setTimeout(r, 300));

        // Fetch mediaUrl if mediaData is missing
        if (!payload.mediaData && payload.mediaUrl) {
            try {
                console.log(`[Background] Fetching mediaUrl: ${payload.mediaUrl}`);
                const res = await fetch(payload.mediaUrl);
                if (res.ok) {
                    const blob = await res.blob();
                    const arrayBuffer = await blob.arrayBuffer();
                    const bytes = new Uint8Array(arrayBuffer);
                    const chunks = [];
                    for (let i = 0; i < bytes.byteLength; i += 8192) {
                        chunks.push(String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + 8192, bytes.byteLength))));
                    }
                    const binary = chunks.join('');
                    payload.mediaData = {
                        base64: btoa(binary),
                        fileName: "downloaded_media",
                        mimeType: blob.type || (payload.mediaUrl.match(/\\.(mp4|mov|avi)/i) ? "video/mp4" : "image/jpeg")
                    };
                } else {
                    console.warn(`⚠️ [Background] mediaUrl fetch failed with status ${res.status}`);
                }
            } catch (err) {
                console.warn(`⚠️ [Background] Failed to fetch mediaUrl:`, err);
            }
        }

        // ===== MEDIA UPLOAD (if post has media data) =====
        let uploadedMediaId = null;
        if (payload.mediaData && payload.mediaData.base64) {
            await updateStep(`📸 2/4: Đang upload File lên Facebook (${payload.mediaData.fileName})...`);
            console.log(`📸 [Background] Uploading media: ${payload.mediaData.fileName}`);
            const uploadResult = await _uploadMediaToFacebook(
                targetTab.id,
                payload.mediaData.base64,
                payload.mediaData.fileName,
                payload.mediaData.mimeType
            );
            console.log(`[Background] Upload result:`, uploadResult);
            if (uploadResult && uploadResult.success) {
                uploadedMediaId = uploadResult.mediaId;
                console.log(`✅ [Background] Media uploaded: ID=${uploadedMediaId}`);
                await updateStep(`✅ 2/4: Upload File thành công! ID=${uploadedMediaId}`);
            } else {
                console.warn(`⚠️ [Background] Media upload failed:`, uploadResult?.error);
                await updateStep(`⚠️ 2/4: Upload File thất bại (${uploadResult?.error || 'Unknown'}), chuyển sang quét giao diện...`);
            }
        }

        // Get c_user cookie directly from Chrome Extension API as fallback
        let fallbackActorId = "";
        try {
            const cCookie = await chrome.cookies.get({ url: "https://www.facebook.com", name: "c_user" });
            if (cCookie && cCookie.value) fallbackActorId = cCookie.value;
        } catch(e) {}

        const isVideo = (payload.mediaData && ((payload.mediaData.mimeType && payload.mediaData.mimeType.startsWith("video/")) || (payload.mediaData.fileName && payload.mediaData.fileName.match(/\.(mp4|mov|avi|mkv|webm)$/i)))) || postType === "video" || postType === "reel";
        const hasMedia = !!(payload.mediaData && payload.mediaData.base64);

        // ===================================================================
        // TIER 1: Direct GraphQL API — LUÔN CHẠY (DOM đã tắt hoàn toàn)
        // ===================================================================
        let graphqlResult = null;
        if (post.fbPostId || (payload.onlyAction && payload.onlyAction !== "post")) {
            console.log(`ℹ️ [Background] Post ${post.id} running targeted action '${payload.onlyAction || 'post_exists'}'. Skipping main post creation...`);
            graphqlResult = {
                success: true,
                fbPostId: post.fbPostId || null,
                fbPostUrl: post.fbPostUrl || null
            };
        } else {
            const tier1Mode = (hasMedia && !uploadedMediaId) 
                ? "text-only (media upload thất bại)" 
                : (uploadedMediaId ? `with media ID=${uploadedMediaId}` : "text-only");
            await updateStep(`⚡ 3/4: Đang tạo bài viết qua Facebook GraphQL API [${tier1Mode}]...`);
            console.log(`⚡ [Background] Running TIER 1 GraphQL API (mode=${tier1Mode}, hasMedia=${hasMedia}, mediaId=${uploadedMediaId})`);

            const effectiveMediaId = uploadedMediaId || null;
            try {
                const graphqlResults = await chrome.scripting.executeScript({
                    target: { tabId: targetTab.id },
                    func: async (postContent, postType, mediaId, isVideo, fallbackActorId, targetType, targetId, customActorId) => {
                        try {
                            let fb_dtsg = "";
                            let lsd = "";
                            let jazoest = "";
                            let hsi = "";
                            let spinR = "";
                            let spinB = "";
                            let spinT = "";

                            for (let attempt = 0; attempt < 10; attempt++) {
                                const html = document.documentElement.innerHTML || "";

                                try {
                                    if (window.DTSGInitialData && window.DTSGInitialData.token) fb_dtsg = window.DTSGInitialData.token;
                                    else if (window.DTSGInitData && window.DTSGInitData.token) fb_dtsg = window.DTSGInitData.token;
                                    else if (window.__DTSGInitialData && window.__DTSGInitialData.token) fb_dtsg = window.__DTSGInitialData.token;
                                } catch (e) {}

                                if (!fb_dtsg && typeof require !== "undefined") {
                                    try {
                                        const mod = require("DTSGInitData") || require("DTSGInitialData");
                                        if (mod && mod.token) fb_dtsg = mod.token;
                                        else if (mod && typeof mod.getAsyncParams === "function") {
                                            const params = mod.getAsyncParams();
                                            if (params && params.fb_dtsg) fb_dtsg = params.fb_dtsg;
                                        }
                                    } catch (e) {}
                                }

                                if (!fb_dtsg) {
                                    try {
                                        const inputEl = document.querySelector('input[name="fb_dtsg"]') || document.querySelector('[name="fb_dtsg"]');
                                        if (inputEl && inputEl.value) fb_dtsg = inputEl.value;
                                    } catch (e) {}
                                }

                                if (!fb_dtsg) {
                                    const dtsgPatterns = [
                                        /\["DTSGInitialData",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                        /\["DTSGInitData",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                        /\["DTSGInitialData",\s*\{[^}]*\}\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                        /\["DTSGInitData",\s*\{[^}]*\}\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                        /"DTSGInitialData"[^}]*"token"\s*:\s*"([^"]+)"/,
                                        /"DTSGInitData"[^}]*"token"\s*:\s*"([^"]+)"/,
                                        /"dtsg"\s*:\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                        /"dtsg_token"\s*:\s*"([^"]+)"/,
                                        /"dtsg"\s*:\s*"([^"]+)"/,
                                        /name="fb_dtsg"[^>]*value="([^"]+)"/,
                                        /"token"\s*:\s*"([^"]{20,})"\s*,\s*"async_get_token"/,
                                        /DTSGInitialData.*?token["']\s*:\s*["']([^"']+)["']/,
                                        /DTSGInitData.*?token["']\s*:\s*["']([^"']+)["']/
                                    ];
                                    for (const p of dtsgPatterns) {
                                        const m = html.match(p);
                                        if (m && m[1]) { fb_dtsg = m[1]; break; }
                                    }
                                }

                                if (!lsd) {
                                    try {
                                        if (window.LSD && window.LSD.token) lsd = window.LSD.token;
                                    } catch(e) {}
                                    if (!lsd && typeof require !== "undefined") {
                                        try {
                                            const mod = require("LSD");
                                            if (mod && mod.token) lsd = mod.token;
                                        } catch(e) {}
                                    }
                                    if (!lsd) {
                                        const lsdPatterns = [
                                            /\["LSD",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                            /name="lsd"[^>]*value="([^"]+)"/,
                                            /"lsd"\s*:\s*"([^"]+)"/
                                        ];
                                        for (const p of lsdPatterns) {
                                            const m = html.match(p);
                                            if (m && m[1]) { lsd = m[1]; break; }
                                        }
                                    }
                                }

                                if (fb_dtsg) break;
                                await new Promise(r => setTimeout(r, 500));
                            }

                            const finalHtml = document.documentElement.innerHTML || "";
                            const jazoM = finalHtml.match(/jazoest=(\d+)/);
                            if (jazoM) jazoest = jazoM[1];

                            const spinM = finalHtml.match(/"__spin_t":(\d+),"__spin_r":(\d+),"__spin_b":"([^"]+)","__hsi":"([^"]+)"/);
                            if (spinM) {
                                spinT = spinM[1]; spinR = spinM[2]; spinB = spinM[3]; hsi = spinM[4];
                            }

                            let activeTabActorId = "";
                            try {
                                if (typeof require !== "undefined") {
                                    const ca = require("CometCurrentActor");
                                    if (ca) activeTabActorId = ca.actorId || ca.id || (typeof ca.get === "function" ? ca.get() : null) || "";
                                }
                            } catch(e) {}
                            if (!activeTabActorId) {
                                try {
                                    if (window.CurrentUserInitialData) activeTabActorId = window.CurrentUserInitialData.ACCOUNT_ID || window.CurrentUserInitialData.USER_ID || "";
                                } catch(e) {}
                            }
                            if (!activeTabActorId) {
                                const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                if (cUserMatch && cUserMatch[1]) activeTabActorId = cUserMatch[1];
                            }
                            let actorId = activeTabActorId || ((customActorId && customActorId !== "0" && customActorId !== "null") ? customActorId : "") || fallbackActorId || "";

                            // 1. Try CometCurrentActor (Facebook Comet active profile/page module)
                            if (!actorId && typeof require !== "undefined") {
                                try {
                                    const ca = require("CometCurrentActor");
                                    if (ca) {
                                        actorId = ca.actorId || ca.id || (typeof ca.get === "function" ? ca.get() : null) || "";
                                    }
                                } catch(e) {}
                            }

                            // 2. Try CurrentUserInitialData (Window or Require)
                            if (!actorId) {
                                try {
                                    if (window.CurrentUserInitialData) {
                                        actorId = window.CurrentUserInitialData.ACCOUNT_ID || 
                                                  window.CurrentUserInitialData.USER_ID || 
                                                  window.CurrentUserInitialData.actor_id || "";
                                    }
                                } catch(e) {}
                            }
                            if (!actorId && typeof require !== "undefined") {
                                try {
                                    const mod = require("CurrentUserInitialData");
                                    if (mod) actorId = mod.ACCOUNT_ID || mod.USER_ID || mod.actor_id || "";
                                } catch(e) {}
                            }

                            // 3. Try Env / __user globals
                            if (!actorId) {
                                try {
                                    if (window.Env && (window.Env.user || window.Env.ACCOUNT_ID)) {
                                        actorId = String(window.Env.user || window.Env.ACCOUNT_ID);
                                    } else if (window.__user) {
                                        actorId = String(window.__user);
                                    }
                                } catch(e) {}
                            }

                            // 4. Try HTML Regex Patterns
                            if (!actorId) {
                                const m = finalHtml.match(/"actorID"\s*:\s*"(\d+)"/) ||
                                          finalHtml.match(/"actor_id"\s*:\s*"(\d+)"/) ||
                                          finalHtml.match(/"USER_ID"\s*:\s*"(\d+)"/) ||
                                          finalHtml.match(/"ACCOUNT_ID"\s*:\s*"(\d+)"/) ||
                                          finalHtml.match(/\["CurrentUserInitialData"\s*,\s*\[\]\s*,\s*\{\s*"ACCOUNT_ID"\s*:\s*"(\d+)"/) ||
                                          finalHtml.match(/\["CurrentUserInitialData"\s*,\s*\[\]\s*,\s*\{\s*"USER_ID"\s*:\s*"(\d+)"/);
                                if (m && m[1]) actorId = m[1];
                            }

                            // 5. Fallback to Cookie c_user or passed fallbackActorId
                            if (!actorId) {
                                const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                            }
                            if (!actorId) actorId = fallbackActorId || "";

                            if (!fb_dtsg || !actorId) {
                                return { success: false, error: "Missing dtsg or actorId (dtsg:" + !!fb_dtsg + ", actorId:" + !!actorId + ")", tier: "graphql" };
                            }

                            // Force NEWSFEED default surface for profile posts so it appears on main Newsfeed (Bảng tin)
                            let surface = "newsfeed";
                            let feedLoc = "NEWSFEED";
                            let renderLoc = "homepage_stream";

                            if (targetType === "group" && targetId) {
                                surface = "group";
                                feedLoc = "GROUP";
                                renderLoc = "group";
                            } else if (targetType === "page") {
                                surface = "page_timeline";
                                feedLoc = "TIMELINE";
                                renderLoc = "page_timeline";
                            }

                            // Dynamically scan for active ComposerStoryCreateMutation doc_id from Facebook page scripts
                            let liveDocIds = [];
                            try {
                                if (typeof _capturedDocIds !== "undefined" && _capturedDocIds.ComposerStoryCreateMutation) {
                                    liveDocIds.push(String(_capturedDocIds.ComposerStoryCreateMutation));
                                }
                            } catch(e) {}
                            try {
                                if (typeof require !== "undefined") {
                                    const mod = require("ComposerStoryCreateMutation.graphql") || require("ComposerStoryCreateMutation");
                                    if (mod) {
                                        const id = mod.params?.id || mod.id || mod.default?.params?.id;
                                        if (id && !liveDocIds.includes(String(id))) liveDocIds.push(String(id));
                                    }
                                }
                            } catch(e) {}

                            try {
                                const scripts = Array.from(document.scripts || []);
                                for (const s of scripts) {
                                    const content = s.textContent || s.innerHTML || "";
                                    if (content.includes("ComposerStoryCreateMutation")) {
                                        const matches = content.matchAll(/"doc_id"\s*:\s*"(\d{14,})"/g);
                                        for (const m of matches) {
                                            if (m && m[1] && !liveDocIds.includes(m[1])) liveDocIds.push(m[1]);
                                        }
                                        const matches2 = content.matchAll(/ComposerStoryCreateMutation.*?["'](\d{14,})["']/g);
                                        for (const m of matches2) {
                                            if (m && m[1] && !liveDocIds.includes(m[1])) liveDocIds.push(m[1]);
                                        }
                                    }
                                }
                            } catch(e) {}

                            const defaultFallbackDocIds = ["28329575890036120", "27508435028820023", "27248647231502311", "6362241860538186", "6815340158580277", "6143924765664426"];
                            const fallbackDocIds = [...liveDocIds];
                            for (const id of defaultFallbackDocIds) {
                                if (!fallbackDocIds.includes(id)) fallbackDocIds.push(id);
                            }

                            const composerSessionId = actorId + "_" + Date.now();
                            const variables = {
                                input: {
                                    composer_entry_point: "inline_composer",
                                    composer_source_surface: surface,
                                    composer_type: targetType === "group" ? "group" : "feed",
                                    idempotence_token: composerSessionId + "_FEED",
                                    source: "WWW",
                                    ai_generated_self_disclosure_metadata: {
                                        was_self_disclosed_as_ai_generated: false
                                    },
                                    ...(targetType === "profile" ? {
                                        audience: {
                                            privacy: {
                                                allow: [],
                                                base_state: "EVERYONE",
                                                deny: [],
                                                tag_expansion_state: "UNSPECIFIED"
                                            }
                                        }
                                    } : {}),
                                    message: { text: postContent || "", ranges: [] },
                                    inline_activities: [],
                                    text_format_preset_id: "0",
                                    publishing_flow: {
                                        supported_flows: ["ASYNC_SILENT", "ASYNC_NOTIF", "FALLBACK"]
                                    },
                                    reels_remix: {
                                        is_original_audio_reusable: true,
                                        remix_status: "ENABLED"
                                    },
                                    post_publish_story_data: {
                                        reshare_post_as_sticker: "DISABLED"
                                    },
                                    logging: {
                                        composer_session_id: composerSessionId
                                    },
                                    navigation_data: {
                                        attribution_id_v2: "CometHomeRoot.react,comet.home,via_cold_start," + Date.now() + ",166542,4748854339,,"
                                    },
                                    tracking: [null],
                                    event_share_metadata: {
                                        surface: surface
                                    },
                                    ...(mediaId ? {
                                        attachments: [
                                            isVideo ? {
                                                video: {
                                                    id: String(mediaId)
                                                }
                                            } : {
                                                photo: {
                                                    id: String(mediaId)
                                                }
                                            }
                                        ]
                                    } : {}),
                                    actor_id: actorId,
                                    client_mutation_id: String(Math.floor(Math.random() * 10) + 1)
                                },
                                feedLocation: feedLoc,
                                feedbackSource: 1,
                                focusCommentID: null,
                                gridMediaWidth: null,
                                groupID: targetType === "group" ? String(targetId) : null,
                                scale: 1,
                                privacySelectorRenderLocation: "COMET_STREAM",
                                checkPhotosToReelsUpsellEligibility: true,
                                referringStoryRenderLocation: null,
                                renderLocation: renderLoc,
                                useDefaultActor: false,
                                inviteShortLinkKey: null,
                                isFeed: true,
                                isFundraiser: false,
                                isFunFactPost: false,
                                isGroup: targetType === "group",
                                isEvent: false,
                                isTimeline: targetType === "profile",
                                isSocialLearning: false,
                                isPageNewsFeed: targetType === "page",
                                isProfileReviews: false,
                                isWorkSharedDraft: false
                            };

                            if (targetType === "group" && targetId) {
                                variables.input.group_id = String(targetId);
                                delete variables.input.audience;
                            } else if (targetType === "page") {
                                delete variables.input.audience;
                            }

                            console.log(`📡 [GraphQL Post] Actor=${actorId}, DTSG=${fb_dtsg.substring(0,10)}..., Target=${targetType}, Surface=${surface}, FeedLoc=${feedLoc}`);

                            let lastErr = "";
                            for (const targetDocId of fallbackDocIds) {
                                console.log(`🚀 [GraphQL Request] Trying ComposerStoryCreateMutation doc_id=${targetDocId}...`);
                                const params = new URLSearchParams();
                                params.append("av", actorId);
                                params.append("__user", actorId);
                                params.append("__a", "1");
                                params.append("__req", Math.floor(Math.random()*100).toString(36));
                                params.append("__hs", hsi || "");
                                params.append("dpr", "1");
                                params.append("__ccg", "EXCELLENT");
                                params.append("__rev", spinR || "1043647106");
                                params.append("__s", [1,2,3].map(()=>Math.random().toString(36).substr(2,6)).join(":"));
                                params.append("__hsi", hsi);
                                params.append("__comet_req", "15");
                                params.append("fb_dtsg", fb_dtsg);
                                params.append("jazoest", jazoest);
                                params.append("lsd", lsd);
                                params.append("__spin_r", spinR || "1043647106");
                                params.append("__spin_b", spinB || "trunk");
                                params.append("__spin_t", spinT || String(Math.floor(Date.now()/1000)));
                                params.append("fb_api_caller_class", "RelayModern");
                                params.append("fb_api_req_friendly_name", "ComposerStoryCreateMutation");
                                params.append("variables", JSON.stringify(variables));
                                params.append("server_timestamps", "true");
                                params.append("doc_id", targetDocId);

                                const resp = await fetch("/api/graphql/", {
                                    method: "POST",
                                    headers: {
                                        "Content-Type": "application/x-www-form-urlencoded",
                                        "X-FB-Friendly-Name": "ComposerStoryCreateMutation",
                                        "X-FB-LSD": lsd,
                                        "X-ASBD-ID": "129477",
                                    },
                                    body: params.toString(),
                                    credentials: "include",
                                });

                                const text = await resp.text();
                                const clean = text.replace(/^for\s*\(;+\)\s*;?\s*/, "");

                                if (resp.ok) {
                                    let pid = null;
                                    let realFbUrl = null;
                                    try {
                                        const jsonResp = JSON.parse(clean);
                                        const sc = jsonResp?.data?.story_create || jsonResp?.data?.composer_story_create || jsonResp?.data;
                                        if (sc) {
                                            const storyObj = sc.story || sc;
                                            pid = storyObj?.legacy_story_hideable?.legacy_story_id ||
                                                  storyObj?.story_fbid ||
                                                  storyObj?.story_id ||
                                                  (storyObj?.id && String(storyObj.id) !== String(mediaId) ? storyObj.id : null);
                                            
                                            const rawUrl = storyObj?.url || storyObj?.permalink_url || storyObj?.legacy_story_hideable?.url;
                                            if (rawUrl) {
                                                realFbUrl = String(rawUrl).replace(/\\/g, "");
                                                if (realFbUrl.endsWith("facebook.com/") || realFbUrl.endsWith("facebook.com")) realFbUrl = null;
                                            }
                                        }
                                    } catch(e) {}

                                    // Fallback Regex for Published Story/Reel ID
                                    const legacyMatch = clean ? (
                                        clean.match(/"legacy_story_id"\s*:\s*"(\d+)"/) ||
                                        clean.match(/"story_fbid"\s*:\s*"(\d+)"/) ||
                                        clean.match(/"post_id"\s*:\s*"(\d+)"/) ||
                                        clean.match(/"story_id"\s*:\s*"(\d+)"/)
                                    ) : null;
                                    if (legacyMatch && legacyMatch[1]) {
                                        pid = legacyMatch[1];
                                    }

                                    if (pid && typeof pid === "string" && !/^\d+$/.test(pid)) {
                                        try {
                                            const decoded = atob(pid);
                                            const m = decoded.match(/(\d{8,})/);
                                            if (m) pid = m[1];
                                        } catch(e) {}
                                    }

                                    let pfbidM = clean ? clean.match(/"(pfbid[a-zA-Z0-9]+)"/) : null;
                                    const effectiveId = pfbidM ? pfbidM[1] : (pid || mediaId);

                                    let purl = realFbUrl;
                                    if (purl && postType === "post" && purl.includes("/reel/")) {
                                        purl = null; // Ignore reel url for regular feed posts
                                    }

                                    if (!purl && effectiveId) {
                                        if (String(effectiveId).startsWith("pfbid")) {
                                            purl = actorId ? `https://www.facebook.com/${actorId}/posts/${effectiveId}` : `https://www.facebook.com/posts/${effectiveId}`;
                                        } else if (postType === "reel") {
                                            purl = `https://www.facebook.com/reel/${effectiveId}`;
                                        } else if (postType === "video") {
                                            purl = `https://www.facebook.com/watch/?v=${effectiveId}`;
                                        } else if (pid) {
                                            purl = actorId ? `https://www.facebook.com/permalink.php?story_fbid=${pid}&id=${actorId}` : `https://www.facebook.com/permalink.php?story_fbid=${pid}`;
                                        } else if (mediaId) {
                                            purl = `https://www.facebook.com/photo/?fbid=${effectiveId}`;
                                        } else {
                                            purl = actorId ? `https://www.facebook.com/permalink.php?story_fbid=${effectiveId}&id=${actorId}` : `https://www.facebook.com/permalink.php?story_fbid=${effectiveId}`;
                                        }
                                    }

                                    let extractedFeedbackId = null;
                                    if (clean) {
                                        const fM = clean.match(/"feedback"\s*:\s*\{[^}]*?"id"\s*:\s*"([^"]+)"/) ||
                                                   clean.match(/"subscription_target_id"\s*:\s*"(\d+)"/);
                                        if (fM && fM[1]) {
                                            extractedFeedbackId = fM[1].startsWith("ZmVl") ? fM[1] : btoa("feedback:" + fM[1]);
                                        }
                                    }

                                    // Robust Error & Success parsing for Facebook GraphQL responses
                                     let hasGqlError = false;
                                     let gqlErrorMessage = "";
                                     
                                     if (clean) {
                                         const rawPreview = clean.slice(0, 250).replace(/[\r\n\t]+/g, ' ');
                                         const lines = clean.split("\n");
                                         for (const line of lines) {
                                             const trimmed = line.trim();
                                             if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                                                 try {
                                                     const p = JSON.parse(trimmed);
                                                     if (p.errors && Array.isArray(p.errors) && p.errors.length > 0) {
                                                         const errObj = p.errors[0];
                                                         const msg = errObj.message || errObj.summary || errObj.description || JSON.stringify(errObj);
                                                         if (!msg.toLowerCase().includes("warning")) {
                                                             hasGqlError = true;
                                                             gqlErrorMessage = `[FB GQL Err ${errObj.code || ''}] ${msg}`;
                                                         }
                                                     } else if (p.error) {
                                                         const errObj = p.error;
                                                         const msg = errObj.message || errObj.error_user_msg || errObj.error_user_title || JSON.stringify(errObj);
                                                         hasGqlError = true;
                                                         gqlErrorMessage = `[FB Err ${errObj.code || ''}] ${msg}`;
                                                     }
                                                 } catch(e) {}
                                             }
                                         }
                                         if (!hasGqlError && (clean.includes('"errors"') || clean.includes('"error"'))) {
                                             const errM = clean.match(/"errors"\s*:\s*\[\s*\{\s*"message"\s*:\s*"([^"]+)"/) || 
                                                          clean.match(/"error"\s*:\s*\{\s*"message"\s*:\s*"([^"]+)"/);
                                             if (errM && errM[1] && !errM[1].toLowerCase().includes("warning")) {
                                                 hasGqlError = true;
                                                 gqlErrorMessage = `[FB Msg] ${errM[1]}`;
                                             }
                                         }
                                         if (!hasGqlError && !gqlErrorMessage) {
                                             gqlErrorMessage = `[FB Raw] ${rawPreview}`;
                                         }
                                     }

                                     const isJsonResponse = clean && (clean.trim().startsWith("{") || clean.trim().startsWith("[") || clean.includes('"data"') || clean.includes('"composer_story_create"'));
                                     const postCreatedId = pfbidM ? pfbidM[1] : pid;
                                     const effectivePostId = postCreatedId || (realFbUrl ? null : mediaId);

                                     // Check if Facebook returned valid story creation payload or post IDs
                                     const hasStoryData = clean && (
                                         clean.includes('"composer_story_create"') || 
                                         clean.includes('"story_create"') || 
                                         clean.includes('"legacy_story_id"') || 
                                         clean.includes('"story_fbid"') || 
                                         clean.includes('"pfbid') ||
                                         !!postCreatedId || 
                                         !!realFbUrl
                                     );

                                     // If Facebook returned story creation data OR HTTP 200 with data and no fatal blocking error, return SUCCESS immediately
                                     const isSuccess = resp.ok && (hasStoryData || (isJsonResponse && !hasGqlError));

                                     if (isSuccess) {
                                         console.log(`✅ [GraphQL Post Success] Post created via doc_id=${targetDocId}, ID=${effectivePostId}, URL=${purl || realFbUrl}`);
                                         return {
                                             success: true,
                                             tier: "graphql",
                                             fbPostId: effectivePostId ? String(effectivePostId) : null,
                                             fbPostUrl: purl || realFbUrl,
                                             fbFeedbackId: extractedFeedbackId,
                                             response: "Story created via doc_id " + targetDocId
                                         };
                                     } else {
                                         lastErr = gqlErrorMessage || "Facebook returned an invalid or error response (not a post creation response)";
                                     }
                                 } else {
                                     lastErr = `HTTP ${resp.status}: Facebook tab blocked or unreachable`;
                                 }
                                 }

                            return { success: false, error: lastErr || "GraphQL failed", tier: "graphql" };
                        } catch (e) {
                            return { success: false, error: e.message, tier: "graphql" };
                        }
                    },
                    args: [payload.content, postType, effectiveMediaId, isVideo, fallbackActorId, payload.targetType || "profile", payload.targetId || "", payload.actorId || ""]
                });

                graphqlResult = graphqlResults && graphqlResults[0] && graphqlResults[0].result;
                console.log(`[Background] HAR GraphQL result:`, graphqlResult);
            } catch (graphqlErr) {
                console.warn(`❌ [Background] Direct GraphQL API ERROR:`, graphqlErr.message);
            }
        }

        if (graphqlResult && graphqlResult.success) {
                    const pid = graphqlResult.fbPostId || uploadedMediaId;
                    let purl = graphqlResult.fbPostUrl;
                    if (purl && postType !== "reel" && purl.includes("/reel/")) {
                        purl = purl.replace("/reel/", "/watch/?v=");
                    }
                    if (!purl && pid) {
                        if (String(pid).startsWith("pfbid")) {
                            purl = `https://www.facebook.com/posts/${pid}`;
                        } else if (postType === "reel") {
                            purl = `https://www.facebook.com/reel/${pid}`;
                        } else if (isVideo) {
                            purl = `https://www.facebook.com/watch/?v=${pid}`;
                        } else if (uploadedMediaId) {
                            purl = `https://www.facebook.com/photo/?fbid=${pid}`;
                        } else {
                            purl = `https://www.facebook.com/permalink.php?story_fbid=${pid}`;
                        }
                    }
                    console.log(`✅ [Background] TIER 1 HAR SUCCESS — Post ${post.id} created via GraphQL API (FB ID: ${pid})`);
                    
                    // Navigate tab to the post URL if seeding or reactions are configured
                    const hasSeeding = payload.seedingComments && Array.isArray(payload.seedingComments) && payload.seedingComments.length > 0;
                    const hasReact = payload.autoReactType && payload.autoReactType !== "NONE";
                    if ((hasSeeding || hasReact) && purl) {
                        try {
                            const currentTab = await chrome.tabs.get(targetTab.id);
                            const currentUrl = currentTab.url || "";
                            const isAlreadyOnPostPage = pid && currentUrl.includes(pid);
                            if (!isAlreadyOnPostPage && currentUrl !== purl) {
                                await updateStep(`🔄 Đang chuyển hướng tab Facebook sang link bài viết...`);
                                await chrome.tabs.update(targetTab.id, { url: purl });
                                await ensureTabLoaded(targetTab.id);
                                await new Promise(r => setTimeout(r, 2000));
                            }
                        } catch (navErr) {
                            console.warn("⚠️ [Background] Navigating to post URL failed:", navErr.message);
                        }
                    }

                    const onlyAction = payload.onlyAction || null;

                    // Exec Auto-Seeding Comments if configured
                    if ((!onlyAction || onlyAction === "seeding") && payload.seedingComments && Array.isArray(payload.seedingComments) && payload.seedingComments.length > 0) {
                        await updateStep(`💬 Đang gửi ${payload.seedingComments.length} bình luận seeding trực tiếp qua Direct GraphQL API...`);
                        
                        try {
                            const knownFeedbackId = graphqlResult?.fbFeedbackId || null;
                            const seedingResults = await chrome.scripting.executeScript({
                                target: { tabId: targetTab.id },
                                func: async (postId, knownFeedbackId, comments, fallbackActorId) => {
                                    let fb_dtsg = "";
                                    let lsd = "";

                                    for (let attempt = 0; attempt < 10; attempt++) {
                                        const html = document.documentElement.innerHTML || "";

                                        try {
                                            if (window.DTSGInitialData && window.DTSGInitialData.token) fb_dtsg = window.DTSGInitialData.token;
                                            else if (window.DTSGInitData && window.DTSGInitData.token) fb_dtsg = window.DTSGInitData.token;
                                            else if (window.__DTSGInitialData && window.__DTSGInitialData.token) fb_dtsg = window.__DTSGInitialData.token;
                                        } catch (e) {}

                                        if (!fb_dtsg && typeof require !== "undefined") {
                                            try {
                                                const mod = require("DTSGInitData") || require("DTSGInitialData");
                                                if (mod && mod.token) fb_dtsg = mod.token;
                                                else if (mod && typeof mod.getAsyncParams === "function") {
                                                    const params = mod.getAsyncParams();
                                                    if (params && params.fb_dtsg) fb_dtsg = params.fb_dtsg;
                                                }
                                            } catch(e) {}
                                        }

                                        if (!fb_dtsg) {
                                            try {
                                                const inputEl = document.querySelector('input[name="fb_dtsg"]') || document.querySelector('[name="fb_dtsg"]');
                                                if (inputEl && inputEl.value) fb_dtsg = inputEl.value;
                                            } catch(e) {}
                                        }

                                        if (!fb_dtsg) {
                                            const dtsgPatterns = [
                                                /\["DTSGInitialData",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                /\["DTSGInitData",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                /\["DTSGInitialData",\s*\{[^}]*\}\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                /\["DTSGInitData",\s*\{[^}]*\}\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                /"DTSGInitialData"[^}]*"token"\s*:\s*"([^"]+)"/,
                                                /"DTSGInitData"[^}]*"token"\s*:\s*"([^"]+)"/,
                                                /"dtsg"\s*:\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                /"dtsg_token"\s*:\s*"([^"]+)"/,
                                                /"dtsg"\s*:\s*"([^"]+)"/,
                                                /name="fb_dtsg"[^>]*value="([^"]+)"/,
                                                /"token"\s*:\s*"([^"]{20,})"\s*,\s*"async_get_token"/,
                                                /DTSGInitialData.*?token["']\s*:\s*["']([^"']+)["']/,
                                                /DTSGInitData.*?token["']\s*:\s*["']([^"']+)["']/
                                            ];
                                            for (const p of dtsgPatterns) {
                                                const m = html.match(p);
                                                if (m && m[1]) { fb_dtsg = m[1]; break; }
                                            }
                                        }

                                        if (!lsd) {
                                            try {
                                                if (window.LSD && window.LSD.token) lsd = window.LSD.token;
                                            } catch(e) {}
                                            if (!lsd && typeof require !== "undefined") {
                                                try {
                                                    const mod = require("LSD");
                                                    if (mod && mod.token) lsd = mod.token;
                                                } catch(e) {}
                                            }
                                            if (!lsd) {
                                                const lsdPatterns = [
                                                    /\["LSD",\s*\[\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"/,
                                                    /name="lsd"[^>]*value="([^"]+)"/,
                                                    /"lsd"\s*:\s*"([^"]+)"/
                                                ];
                                                for (const p of lsdPatterns) {
                                                    const m = html.match(p);
                                                    if (m && m[1]) { lsd = m[1]; break; }
                                                }
                                            }
                                        }

                                        if (fb_dtsg) break;
                                        await new Promise(r => setTimeout(r, 500));
                                    }

                                    const finalHtml = document.documentElement.innerHTML || "";
                                    let actorId = "";

                                    // 1. Try CometCurrentActor (Facebook Comet active profile/page module)
                                    if (!actorId && typeof require !== "undefined") {
                                        try {
                                            const ca = require("CometCurrentActor");
                                            if (ca) {
                                                actorId = ca.actorId || ca.id || (typeof ca.get === "function" ? ca.get() : null) || "";
                                            }
                                        } catch(e) {}
                                    }

                                    // 2. Try CurrentUserInitialData (Window or Require)
                                    if (!actorId) {
                                        try {
                                            if (window.CurrentUserInitialData) {
                                                actorId = window.CurrentUserInitialData.ACCOUNT_ID || 
                                                          window.CurrentUserInitialData.USER_ID || 
                                                          window.CurrentUserInitialData.actor_id || "";
                                            }
                                        } catch(e) {}
                                    }
                                    if (!actorId && typeof require !== "undefined") {
                                        try {
                                            const mod = require("CurrentUserInitialData");
                                            if (mod) actorId = mod.ACCOUNT_ID || mod.USER_ID || mod.actor_id || "";
                                        } catch(e) {}
                                    }

                                    // 3. Try Env / __user globals
                                    if (!actorId) {
                                        try {
                                            if (window.Env && (window.Env.user || window.Env.ACCOUNT_ID)) {
                                                actorId = String(window.Env.user || window.Env.ACCOUNT_ID);
                                            } else if (window.__user) {
                                                actorId = String(window.__user);
                                            }
                                        } catch(e) {}
                                    }

                                    // 4. Try HTML Regex Patterns
                                    if (!actorId) {
                                        const m = finalHtml.match(/"actorID"\s*:\s*"(\d+)"/) ||
                                                  finalHtml.match(/"actor_id"\s*:\s*"(\d+)"/) ||
                                                  finalHtml.match(/"USER_ID"\s*:\s*"(\d+)"/) ||
                                                  finalHtml.match(/"ACCOUNT_ID"\s*:\s*"(\d+)"/) ||
                                                  finalHtml.match(/\["CurrentUserInitialData"\s*,\s*\[\]\s*,\s*\{\s*"ACCOUNT_ID"\s*:\s*"(\d+)"/) ||
                                                  finalHtml.match(/\["CurrentUserInitialData"\s*,\s*\[\]\s*,\s*\{\s*"USER_ID"\s*:\s*"(\d+)"/);
                                        if (m && m[1]) actorId = m[1];
                                    }

                                    // 5. Fallback to Cookie c_user or passed fallbackActorId
                                    if (!actorId) {
                                        const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                        if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                                    }
                                    if (!actorId) actorId = fallbackActorId || "";

                                    if (!fb_dtsg || !actorId || !postId) {
                                        return { success: false, error: "Missing tokens (dtsg:" + !!fb_dtsg + ", actorId:" + !!actorId + ", postId:" + !!postId + ")" };
                                    }

                                    // Calculate mandatory jazoest parameter for Facebook CSRF validation
                                    let jazoest = "2";
                                    for (let i = 0; i < fb_dtsg.length; i++) {
                                        jazoest += fb_dtsg.charCodeAt(i);
                                    }

                                    const feedbackCandidates = [];
                                    if (knownFeedbackId) {
                                        if (knownFeedbackId.startsWith("ZmVl")) {
                                            feedbackCandidates.push(knownFeedbackId);
                                        } else {
                                            feedbackCandidates.push(btoa("feedback:" + knownFeedbackId));
                                            feedbackCandidates.push(btoa("Feedback:" + knownFeedbackId));
                                        }
                                    }

                                    if (postId && /^\d+$/.test(String(postId))) {
                                        feedbackCandidates.push(btoa("feedback:" + postId));
                                        feedbackCandidates.push(btoa("Feedback:" + postId));
                                    } else if (postId && String(postId).startsWith("pfbid")) {
                                        feedbackCandidates.push(btoa("feedback:" + postId));
                                        feedbackCandidates.push(btoa("Feedback:" + postId));
                                    }

                                    // Extract all numeric story/feedback target IDs from HTML DOM
                                    const numMatches = finalHtml.matchAll(/"(?:legacy_story_id|story_fbid|post_id|story_id|subscription_target_id|feedback_target_id|target_id)"\s*:\s*"(\d+)"/g);
                                    for (const m of numMatches) {
                                        if (m[1] && m[1].length >= 8) {
                                            const b1 = btoa("feedback:" + m[1]);
                                            const b2 = btoa("Feedback:" + m[1]);
                                            if (!feedbackCandidates.includes(b1)) feedbackCandidates.push(b1);
                                            if (!feedbackCandidates.includes(b2)) feedbackCandidates.push(b2);
                                        }
                                    }

                                    let liveCommentDocIds = [];
                                    try {
                                        if (typeof require !== "undefined") {
                                            const mod = require("useCometUFICreateCommentMutation.graphql") || require("useCometUFICreateCommentMutation") || require("CometCommentCreateMutation.graphql");
                                            if (mod) {
                                                const id = mod.params?.id || mod.id || mod.default?.params?.id;
                                                if (id && !liveCommentDocIds.includes(String(id))) liveCommentDocIds.push(String(id));
                                            }
                                        }
                                    } catch(e) {}

                                    try {
                                        const scripts = Array.from(document.scripts || []);
                                        for (const s of scripts) {
                                            const content = s.textContent || s.innerHTML || "";
                                            if (content.includes("CometUFICreateCommentMutation") || content.includes("CometCommentCreateMutation")) {
                                                const matches = content.matchAll(/"doc_id"\s*:\s*"(\d{14,})"/g);
                                                for (const m of matches) {
                                                    if (m && m[1] && !liveCommentDocIds.includes(m[1])) liveCommentDocIds.push(m[1]);
                                                }
                                            }
                                        }
                                    } catch(e) {}

                                    const defaultCommentDocIds = ["27829190080054105", "5384620808298758", "5765399230165702", "5515286528574762", "7181675201948512"];
                                    const docIds = [...liveCommentDocIds];
                                    for (const id of defaultCommentDocIds) {
                                        if (!docIds.includes(id)) docIds.push(id);
                                    }

                                    let successCount = 0;
                                    const errors = [];

                                    for (const commentText of comments) {
                                        if (!commentText || !commentText.trim()) continue;
                                        let commentSuccess = false;

                                        for (const fbIdCandidate of feedbackCandidates) {
                                            if (commentSuccess) break;
                                            for (const docId of docIds) {
                                                try {
                                                    const isNewMutation = (docId === "27829190080054105");
                                                    const vars = isNewMutation ? {
                                                        feedLocation: "POST_PERMALINK_DIALOG",
                                                        feedbackSource: 2,
                                                        groupID: null,
                                                        input: {
                                                            client_mutation_id: String(Date.now()),
                                                            attachments: null,
                                                            feedback_id: fbIdCandidate,
                                                            formatting_style: null,
                                                            is_inline_vote_enabled_for_qna: false,
                                                            message: {
                                                                ranges: [],
                                                                text: commentText.trim()
                                                            },
                                                            attribution_id_v2: "CometSinglePostDialogRoot.react,comet.post.single_dialog,unexpected," + Date.now() + ",881640,,,",
                                                            feedback_source: "OBJECT",
                                                            idempotence_token: "client:" + String(Date.now()),
                                                            session_id: String(Date.now())
                                                        },
                                                        scale: 2,
                                                        useDefaultActor: false,
                                                        translationType: "AUTO_TRANSLATE",
                                                        canUseNicknameOnComet: false,
                                                        __relay_internal__pv__groups_comet_use_glvrelayprovider: false,
                                                        __relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider: true,
                                                        __relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider: false,
                                                        __relay_internal__pv__IsWorkUserrelayprovider: false,
                                                        __relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider: "AUTO_TRANSLATE"
                                                    } : {
                                                        input: {
                                                            feedback_id: fbIdCandidate,
                                                            message: { text: commentText.trim() },
                                                            actor_id: actorId,
                                                            client_mutation_id: String(Date.now())
                                                        }
                                                    };

                                                    const params = new URLSearchParams();
                                                    params.append("av", actorId);
                                                    params.append("__user", actorId);
                                                    params.append("__a", "1");
                                                    params.append("fb_dtsg", fb_dtsg);
                                                    params.append("jazoest", jazoest);
                                                    params.append("lsd", lsd);
                                                    params.append("fb_api_caller_class", "RelayModern");
                                                    params.append("fb_api_req_friendly_name", isNewMutation ? "useCometUFICreateCommentMutation" : "CometCommentCreateMutation");
                                                    params.append("server_timestamps", "true");
                                                    params.append("variables", JSON.stringify(vars));
                                                    params.append("doc_id", docId);

                                                    const res = await fetch("https://www.facebook.com/api/graphql/", {
                                                        method: "POST",
                                                        headers: {
                                                            "Content-Type": "application/x-www-form-urlencoded",
                                                            "X-FB-Friendly-Name": isNewMutation ? "useCometUFICreateCommentMutation" : "CometCommentCreateMutation",
                                                            "X-FB-LSD": lsd,
                                                            "X-ASBD-ID": "129477"
                                                        },
                                                        body: params.toString(),
                                                        credentials: "include"
                                                    });
                                                    const text = await res.text();
                                                    let json = null;
                                                    try { json = JSON.parse(text.replace(/^for\s*\([^)]*\);?/, "")); } catch(e) {}

                                                    const hasCommentData = json && json.data && (
                                                        json.data.comment_create || 
                                                        json.data.useCometUFICreateCommentMutation || 
                                                        json.data.comment || 
                                                        json.data.feedback || 
                                                        json.data.id ||
                                                        text.includes('"comment"') ||
                                                        text.includes('"feedback"')
                                                    );

                                                    if (res.ok && (hasCommentData || (json && json.data && !json.errors))) {
                                                        commentSuccess = true;
                                                        break;
                                                    } else if (json && json.errors && json.errors.length) {
                                                        errors.push(`doc ${docId}: ${json.errors[0].message}`);
                                                    }
                                                } catch(e) {
                                                    errors.push(e.message);
                                                }
                                            }
                                        }

                                        // DOM Automation Fallback if GraphQL did not succeed
                                        if (!commentSuccess) {
                                            try {
                                                const commentBox = document.querySelector(
                                                    'div[role="textbox"][aria-label*="bình luận"], ' +
                                                    'div[role="textbox"][aria-label*="Comment"], ' +
                                                    'div[role="textbox"][aria-label*="Viết"], ' +
                                                    'div[role="textbox"][contenteditable="true"], ' +
                                                    'form div[role="textbox"]'
                                                );
                                                if (commentBox) {
                                                    commentBox.focus();
                                                    document.execCommand("insertText", false, commentText.trim());
                                                    commentBox.dispatchEvent(new Event("input", { bubbles: true }));
                                                    await new Promise(r => setTimeout(r, 400));
                                                    
                                                    const enterEvt = new KeyboardEvent("keydown", {
                                                        key: "Enter", code: "Enter", keyCode: 13, which: 13,
                                                        bubbles: true, cancelable: true
                                                    });
                                                    commentBox.dispatchEvent(enterEvt);
                                                    commentSuccess = true;
                                                }
                                            } catch(domErr) {
                                                errors.push("DOM error: " + domErr.message);
                                            }
                                        }

                                        if (commentSuccess) successCount++;
                                        await new Promise(r => setTimeout(r, 1200));
                                    }

                                    return { success: successCount > 0, successCount, total: comments.length, errors };
                                },
                                args: [pid, knownFeedbackId, payload.seedingComments, fallbackActorId]
                            });

                            const seedResult = seedingResults?.[0]?.result;
                            console.log("💬 [Seeding Comments Result]:", seedResult);
                            if (seedResult && seedResult.success) {
                                await updateStep(`✅ 💬 Đã gửi thành công ${seedResult.successCount}/${seedResult.total} bình luận seeding!`);
                            } else {
                                const seedErrMsg = seedResult?.error || (seedResult?.errors && seedResult.errors.join("; ")) || "Không tìm thấy token/post ID";
                                await updateStep(`⚠️ 💬 Kết quả Seeding: ${seedErrMsg}`);
                            }
                        } catch(e) {
                        }
                    }

                    // Exec Auto-React to Post & Comments if configured
                    if ((!onlyAction || onlyAction === "react") && payload.autoReactType && payload.autoReactType !== "NONE") {
                        await updateStep(`❤️ Đang tự động thả cảm xúc ${payload.autoReactType} cho bài viết...`);
                        try {
                            const knownFeedbackId = graphqlResult?.fbFeedbackId || null;
                            const reactResults = await chrome.scripting.executeScript({
                                target: { tabId: targetTab.id },
                                func: async (postId, knownFeedbackId, reactType, fallbackActorId) => {
                                    let fb_dtsg = "";
                                    let lsd = "";

                                    for (let attempt = 0; attempt < 10; attempt++) {
                                        const html = document.documentElement.innerHTML || "";

                                        try {
                                            if (window.DTSGInitialData && window.DTSGInitialData.token) fb_dtsg = window.DTSGInitialData.token;
                                            else if (window.DTSGInitData && window.DTSGInitData.token) fb_dtsg = window.DTSGInitData.token;
                                        } catch (e) {}

                                        if (!lsd) {
                                            const m = html.match(/"lsd"\s*:\s*"([^"]+)"/);
                                            if (m && m[1]) lsd = m[1];
                                        }

                                        if (fb_dtsg) break;
                                        await new Promise(r => setTimeout(r, 400));
                                    }

                                    const finalHtml = document.documentElement.innerHTML || "";
                                    let actorId = "";
                                    try {
                                        const ca = typeof require !== "undefined" ? require("CometCurrentActor") : null;
                                        if (ca) actorId = ca.actorId || ca.id || "";
                                    } catch(e) {}
                                    if (!actorId) {
                                        const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                        if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                                    }
                                    if (!actorId) actorId = fallbackActorId || "";

                                    if (!fb_dtsg || !actorId) return { success: false, error: "Missing tokens for react" };

                                    let jazoest = "2";
                                    for (let i = 0; i < fb_dtsg.length; i++) jazoest += fb_dtsg.charCodeAt(i);

                                    const reactionMap = {
                                        "LIKE": "1635855486666999",
                                        "LOVE": "1635855606666987",
                                        "HAHA": "1635855726666975",
                                        "WOW": "1635855846666963",
                                        "SAD": "1635855966666951",
                                        "ANGRY": "1635856086666939"
                                    };
                                    const reactionId = reactionMap[reactType] || "1635855486666999";

                                    const reactCandidates = [];
                                    if (knownFeedbackId) {
                                        reactCandidates.push(knownFeedbackId.startsWith("ZmVl") ? knownFeedbackId : btoa("feedback:" + knownFeedbackId));
                                    }
                                    if (postId && /^\d+$/.test(String(postId))) {
                                        reactCandidates.push(btoa("feedback:" + postId));
                                        reactCandidates.push(btoa("Feedback:" + postId));
                                    }

                                    const numMatches = finalHtml.matchAll(/"(?:legacy_story_id|story_fbid|post_id|story_id|subscription_target_id|feedback_target_id|target_id)"\s*:\s*"(\d+)"/g);
                                    for (const m of numMatches) {
                                        if (m[1] && m[1].length >= 8) {
                                            const b1 = btoa("feedback:" + m[1]);
                                            if (!reactCandidates.includes(b1)) reactCandidates.push(b1);
                                        }
                                    }

                                    if (reactCandidates.length === 0) return { success: false, error: "Missing feedbackId candidate for react" };

                                    let lastReactErr = "";
                                    for (const targetFeedbackId of reactCandidates) {
                                        try {
                                            const vars = {
                                                input: {
                                                    attribution_id_v2: "CometSinglePostDialogRoot.react,comet.post.single_dialog,unexpected," + Date.now() + ",881640,,,",
                                                    feedback_id: targetFeedbackId,
                                                    feedback_reaction_id: reactionId,
                                                    feedback_source: "OBJECT",
                                                    is_tracking_encrypted: true,
                                                    session_id: String(Date.now()),
                                                    actor_id: actorId,
                                                    client_mutation_id: String(Math.floor(Math.random() * 10) + 1)
                                                },
                                                scale: 2,
                                                canUseNicknameOnComet: false,
                                                useDefaultActor: false,
                                                __relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider: false
                                            };
                                            const params = new URLSearchParams();
                                            params.append("av", actorId);
                                            params.append("__user", actorId);
                                            params.append("__a", "1");
                                            params.append("fb_dtsg", fb_dtsg);
                                            params.append("jazoest", jazoest);
                                            params.append("lsd", lsd);
                                            params.append("fb_api_caller_class", "RelayModern");
                                            params.append("fb_api_req_friendly_name", "CometUFIFeedbackReactMutation");
                                            params.append("server_timestamps", "true");
                                            params.append("variables", JSON.stringify(vars));
                                            params.append("doc_id", "27646120298312844");

                                            const res = await fetch("https://www.facebook.com/api/graphql/", {
                                                method: "POST",
                                                headers: {
                                                    "Content-Type": "application/x-www-form-urlencoded",
                                                    "X-FB-Friendly-Name": "CometUFIFeedbackReactMutation",
                                                    "X-FB-LSD": lsd,
                                                    "X-ASBD-ID": "129477"
                                                },
                                                body: params.toString(),
                                                credentials: "include"
                                            });
                                            const text = await res.text();
                                            let json = null;
                                            try { json = JSON.parse(text.replace(/^for\s*\([^)]*\);?/, "")); } catch(e) {}
                                            
                                            const hasReactData = json && json.data && (
                                                json.data.feedback_react || 
                                                json.data.feedback_react_mode || 
                                                json.data.feedback ||
                                                text.includes('"feedback_react"') ||
                                                text.includes('"feedback"')
                                            );

                                            if (res.ok && (hasReactData || (json && json.data && !json.errors))) {
                                                return { success: true, reactType, feedbackId: targetFeedbackId };
                                            } else if (json && json.errors && json.errors.length) {
                                                lastReactErr = json.errors[0].message;
                                            }
                                        } catch(e) {
                                            lastReactErr = e.message;
                                        }
                                    }
                                    return { success: false, error: lastReactErr || "React failed" };
                                },
                                args: [pid, knownFeedbackId, payload.autoReactType, fallbackActorId]
                            });
                            console.log("❤️ [Auto-React Result]:", reactResults?.[0]?.result);
                            if (reactResults?.[0]?.result?.success) {
                                await updateStep(`✅ ❤️ Đã tự động thả cảm xúc ${payload.autoReactType} cho bài viết thành công!`);
                            } else {
                                await updateStep(`⚠️ ❤️ Kết quả Thả Cảm Xúc: ${reactResults?.[0]?.result?.error || 'Chưa hoàn tất'}`);
                            }
                        } catch(e) {
                            console.warn("⚠️ [Auto-React Error]:", e.message);
                        }
                    }

                    // Exec Auto-Reply to Comments if configured
                    if ((!onlyAction || onlyAction === "reply") && payload.autoReplyComments && Array.isArray(payload.autoReplyComments) && payload.autoReplyComments.length > 0) {
                        await updateStep(`🤖 Đang thực hiện Auto-Reply với ${payload.autoReplyComments.length} câu trả lời tư vấn...`);
                        try {
                            const knownFeedbackId = graphqlResult?.fbFeedbackId || null;
                            const replyResults = await chrome.scripting.executeScript({
                                target: { tabId: targetTab.id },
                                func: async (postId, knownFeedbackId, replyTemplates, fallbackActorId, targetCommentId) => {
                                    let fb_dtsg = "";
                                    let lsd = "";
                                    for (let attempt = 0; attempt < 10; attempt++) {
                                        const html = document.documentElement.innerHTML || "";
                                        try {
                                            if (window.DTSGInitialData?.token) fb_dtsg = window.DTSGInitialData.token;
                                            else if (window.DTSGInitData?.token) fb_dtsg = window.DTSGInitData.token;
                                        } catch(e) {}
                                        if (!lsd) {
                                            const m = html.match(/"lsd"\s*:\s*"([^"]+)"/);
                                            if (m && m[1]) lsd = m[1];
                                        }
                                        if (fb_dtsg) break;
                                        await new Promise(r => setTimeout(r, 400));
                                    }
                                    const finalHtml = document.documentElement.innerHTML || "";
                                    let actorId = "";
                                    try {
                                        const ca = typeof require !== "undefined" ? require("CometCurrentActor") : null;
                                        if (ca) actorId = ca.actorId || ca.id || "";
                                    } catch(e) {}
                                    if (!actorId) {
                                        const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                        if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                                    }
                                    if (!actorId) actorId = fallbackActorId || "";
                                    if (!fb_dtsg || !actorId) return { success: false, error: "Missing tokens for reply" };

                                    let jazoest = "2";
                                    for (let i = 0; i < fb_dtsg.length; i++) jazoest += fb_dtsg.charCodeAt(i);

                                    let resolvedCmtId = targetCommentId ? String(targetCommentId) : "";
                                    let rawStoryId = "";
                                    if (knownFeedbackId && /^\d+$/.test(String(knownFeedbackId))) {
                                        rawStoryId = String(knownFeedbackId);
                                    } else if (postId && /^\d+$/.test(String(postId))) {
                                        rawStoryId = String(postId);
                                    } else if (postId && String(postId).startsWith("pfbid")) {
                                        rawStoryId = String(postId);
                                    }

                                    if (!rawStoryId) {
                                        const curUrl = window.location.href || "";
                                        const mUrl = curUrl.match(/(?:story_fbid=|posts\/|videos\/|watch\/\?v=|reel\/)(\d+|pfbid[a-zA-Z0-9]+)/);
                                        if (mUrl && mUrl[1]) {
                                            rawStoryId = mUrl[1];
                                        } else {
                                            const storyMatch = finalHtml.match(/"(?:legacy_story_id|story_fbid|post_id|story_id|subscription_target_id|feedback_target_id)"\s*:\s*"(\d{8,})"/);
                                            if (storyMatch && storyMatch[1]) rawStoryId = storyMatch[1];
                                        }
                                    }

                                    // Resolve local non-numeric IDs (like cmt_...) to real Facebook comment IDs
                                    if (resolvedCmtId && !/^\d+$/.test(resolvedCmtId) && !resolvedCmtId.includes("_")) {
                                        if (rawStoryId) {
                                            try {
                                                const targetFeedbackId = btoa("feedback:" + rawStoryId);
                                                const queryVars = {
                                                    feedbackSource: 2, feedLocation: "POST_PERMALINK_DIALOG", focusCommentID: null,
                                                    privacySelectorRenderLocation: "COMET_STREAM", renderLocation: "permalink", scale: 2, useDefaultActor: false, id: targetFeedbackId
                                                };
                                                const queryParams = new URLSearchParams();
                                                queryParams.append("av", actorId); queryParams.append("__user", actorId); queryParams.append("__a", "1");
                                                queryParams.append("fb_dtsg", fb_dtsg); queryParams.append("jazoest", jazoest); queryParams.append("lsd", lsd);
                                                queryParams.append("fb_api_caller_class", "RelayModern");
                                                queryParams.append("fb_api_req_friendly_name", "CometSinglePostDialogContentQuery");
                                                queryParams.append("variables", JSON.stringify(queryVars));
                                                queryParams.append("doc_id", "25494545246909173");

                                                const qRes = await fetch("https://www.facebook.com/api/graphql/", {
                                                    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: queryParams.toString(), credentials: "include"
                                                });
                                                const qText = await qRes.text();
                                                const legacyMatch = qText.match(/"legacy_fbid"\s*:\s*"(\d+)"/);
                                                if (legacyMatch && legacyMatch[1]) {
                                                    resolvedCmtId = legacyMatch[1];
                                                }
                                            } catch(e) {}
                                        }
                                    }

                                    // Fallback: If no resolved comment ID exists at all, find any existing comment on post
                                    if (!resolvedCmtId && rawStoryId) {
                                        try {
                                            const targetFeedbackId = btoa("feedback:" + rawStoryId);
                                            const queryVars = {
                                                feedbackSource: 2, feedLocation: "POST_PERMALINK_DIALOG", focusCommentID: null,
                                                privacySelectorRenderLocation: "COMET_STREAM", renderLocation: "permalink", scale: 2, useDefaultActor: false, id: targetFeedbackId
                                            };
                                            const queryParams = new URLSearchParams();
                                            queryParams.append("av", actorId); queryParams.append("__user", actorId); queryParams.append("__a", "1");
                                            queryParams.append("fb_dtsg", fb_dtsg); queryParams.append("jazoest", jazoest); queryParams.append("lsd", lsd);
                                            queryParams.append("fb_api_caller_class", "RelayModern");
                                            queryParams.append("fb_api_req_friendly_name", "CometSinglePostDialogContentQuery");
                                            queryParams.append("variables", JSON.stringify(queryVars));
                                            queryParams.append("doc_id", "25494545246909173");

                                            const qRes = await fetch("https://www.facebook.com/api/graphql/", {
                                                method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: queryParams.toString(), credentials: "include"
                                            });
                                            const qText = await qRes.text();
                                            const legacyMatch = qText.match(/"legacy_fbid"\s*:\s*"(\d+)"/);
                                            if (legacyMatch && legacyMatch[1]) {
                                                resolvedCmtId = legacyMatch[1];
                                            }
                                        } catch(e) {}
                                    }

                                    let fullCmtId = resolvedCmtId;
                                    if (fullCmtId && !fullCmtId.includes("_") && rawStoryId) {
                                        fullCmtId = rawStoryId + "_" + resolvedCmtId;
                                    }

                                    const parentFbid = fullCmtId ? (fullCmtId.startsWith("Y29t") ? fullCmtId : btoa("comment:" + fullCmtId)) : null;

                                    const replyCandidates = [];
                                    if (fullCmtId) {
                                        replyCandidates.push(btoa("feedback:" + fullCmtId));
                                    } else {
                                        if (knownFeedbackId) {
                                            if (knownFeedbackId.startsWith("ZmVl")) {
                                                replyCandidates.push(knownFeedbackId);
                                            } else {
                                                replyCandidates.push(btoa("feedback:" + knownFeedbackId));
                                                replyCandidates.push(btoa("Feedback:" + knownFeedbackId));
                                            }
                                        }
                                        if (postId && /^\d+$/.test(String(postId))) {
                                            replyCandidates.push(btoa("feedback:" + postId));
                                            replyCandidates.push(btoa("Feedback:" + postId));
                                        } else if (postId && String(postId).startsWith("pfbid")) {
                                            replyCandidates.push(btoa("feedback:" + postId));
                                            replyCandidates.push(btoa("Feedback:" + postId));
                                        }

                                        const numMatches = finalHtml.matchAll(/"(?:legacy_story_id|story_fbid|post_id|story_id|subscription_target_id|feedback_target_id|target_id)"\s*:\s*"(\d+)"/g);
                                        for (const m of numMatches) {
                                            if (m[1] && m[1].length >= 8) {
                                                const b1 = btoa("feedback:" + m[1]);
                                                const b2 = btoa("Feedback:" + m[1]);
                                                if (!replyCandidates.includes(b1)) replyCandidates.push(b1);
                                                if (!replyCandidates.includes(b2)) replyCandidates.push(b2);
                                            }
                                        }
                                    }
                                    if (replyCandidates.length === 0) return { success: false, error: "Không tìm thấy ID bài viết để trả lời" };

                                    let replySuccessCount = 0;
                                    let lastReplyErr = "";
                                    for (const replyText of replyTemplates) {
                                        if (!replyText || !replyText.trim()) continue;
                                        for (const targetFbId of replyCandidates) {
                                            try {
                                                const vars = {
                                                    feedLocation: "POST_PERMALINK_DIALOG",
                                                    feedbackSource: 2,
                                                    groupID: null,
                                                    input: {
                                                        client_mutation_id: String(Date.now()),
                                                        attachments: null,
                                                        feedback_id: targetFbId,
                                                        formatting_style: null,
                                                        is_inline_vote_enabled_for_qna: false,
                                                        message: { ranges: [], text: replyText.trim() },
                                                        reply_comment_parent_fbid: parentFbid,
                                                        reply_target_clicked: !!parentFbid,
                                                        attribution_id_v2: "CometSinglePostDialogRoot.react,comet.post.single_dialog,unexpected," + Date.now() + ",881640,,,",
                                                        feedback_source: "OBJECT",
                                                        idempotence_token: "client:" + String(Date.now()),
                                                        session_id: String(Date.now())
                                                    },
                                                    scale: 2,
                                                    useDefaultActor: false,
                                                    translationType: "AUTO_TRANSLATE"
                                                };
                                                const params = new URLSearchParams();
                                                params.append("av", actorId);
                                                params.append("__user", actorId);
                                                params.append("__a", "1");
                                                params.append("fb_dtsg", fb_dtsg);
                                                params.append("jazoest", jazoest);
                                                params.append("lsd", lsd);
                                                params.append("fb_api_caller_class", "RelayModern");
                                                params.append("fb_api_req_friendly_name", "useCometUFICreateCommentMutation");
                                                params.append("server_timestamps", "true");
                                                params.append("variables", JSON.stringify(vars));
                                                params.append("doc_id", "27829190080054105");

                                                const res = await fetch("https://www.facebook.com/api/graphql/", {
                                                    method: "POST",
                                                    headers: {
                                                        "Content-Type": "application/x-www-form-urlencoded",
                                                        "X-FB-Friendly-Name": "useCometUFICreateCommentMutation",
                                                        "X-FB-LSD": lsd,
                                                        "X-ASBD-ID": "129477"
                                                    },
                                                    body: params.toString(),
                                                    credentials: "include"
                                                });
                                                const text = await res.text();
                                                let json = null;
                                                try { json = JSON.parse(text.replace(/^for\s*\([^)]*\);?/, "")); } catch(e) {}
                                                if (res.ok && (text.includes('"comment_create"') || text.includes('"feedback"') || (json && json.data && !json.errors))) {
                                                    replySuccessCount++;
                                                    break;
                                                } else if (json && json.errors && json.errors.length) {
                                                    const errObj = json.errors[0];
                                                    lastReplyErr = `[FB GraphQL Error ${errObj.code || ''}] ${errObj.message || errObj.summary || 'Mutation failed'}`;
                                                } else {
                                                    lastReplyErr = `[FB HTTP ${res.status}] ${text.slice(0, 150)}`;
                                                }
                                            } catch(e) {
                                                lastReplyErr = `[Network Exception] ${e.message}`;
                                            }
                                        }
                                    }
                                    return { success: replySuccessCount > 0, replySuccessCount, total: replyTemplates.length, error: lastReplyErr };
                                },
                                args: [pid, knownFeedbackId, payload.autoReplyComments, fallbackActorId, payload.targetCommentId || null]
                            });
                            const replyRes = replyResults?.[0]?.result;
                            console.log("🤖 [Auto-Reply Result]:", replyRes);
                            if (replyRes && replyRes.success) {
                                await updateStep(`🎉 [THÀNH CÔNG 100%] Đã trả lời trực tiếp bên dưới comment Facebook!`);
                            } else {
                                const detailedErr = replyRes?.error || "Không nhận được phản hồi từ Facebook";
                                await updateStep(`❌ [LỖI TRẢ LỜI FACEBOOK] ${detailedErr}`);
                            }
                        } catch(e) {
                            console.warn("⚠️ [Auto-Reply Error]:", e.message);
                            await updateStep(`❌ [LỖI EXTENSION EXEC] ${e.message}`);
                        }
                    }

                    if (payload.onlyAction === "fetch_comments") {
                        await updateStep("⚡ Đang kết nối Facebook quét bình luận thực tế...");
                        try {
                            let realPostId = post.fbFeedbackId || post.fbPostId || "";
                            if (!realPostId || (!/^\d+$/.test(String(realPostId)) && !String(realPostId).startsWith("pfbid"))) {
                                if (post.fbPostUrl) {
                                    const m = post.fbPostUrl.match(/(?:story_fbid=|posts\/|videos\/|watch\/\?v=|reel\/)(\d+)/);
                                    if (m && m[1]) realPostId = m[1];
                                }
                            }
                            if (!realPostId) realPostId = post.fbPostId || post.id;

                            const results = await chrome.scripting.executeScript({
                                target: { tabId: targetTab.id },
                                func: async (postId, fallbackActorId) => {
                                    let fb_dtsg = ""; let lsd = "";
                                    for (let attempt = 0; attempt < 5; attempt++) {
                                        const html = document.documentElement.innerHTML || "";
                                        if (window.DTSGInitialData?.token) fb_dtsg = window.DTSGInitialData.token;
                                        else if (window.DTSGInitData?.token) fb_dtsg = window.DTSGInitData.token;
                                        if (!lsd) {
                                            const m = html.match(/"lsd"\s*:\s*"([^"]+)"/);
                                            if (m && m[1]) lsd = m[1];
                                        }
                                        if (fb_dtsg) break;
                                        await new Promise(r => setTimeout(r, 300));
                                    }
                                    let actorId = "";
                                    try {
                                        const ca = typeof require !== "undefined" ? require("CometCurrentActor") : null;
                                        if (ca) actorId = ca.actorId || ca.id || "";
                                    } catch(e) {}
                                    if (!actorId) {
                                        const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                                        if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                                    }
                                    if (!actorId) actorId = fallbackActorId || "";
                                    if (!fb_dtsg || !actorId) return { scannedComments: [] };

                                    let jazoest = "2";
                                    for (let i = 0; i < fb_dtsg.length; i++) jazoest += fb_dtsg.charCodeAt(i);

                                    const scannedComments = [];
                                    let storyId = "";
                                    const storyMatch = String(postId).match(/\d{8,}/);
                                    if (storyMatch) {
                                        storyId = storyMatch[0];
                                    } else if (String(postId).startsWith("pfbid")) {
                                        storyId = String(postId);
                                    }

                                    // Fallback: If storyId is local or missing, extract story ID from current FB tab URL/HTML
                                    if (!storyId || (!/^\d+$/.test(storyId) && !storyId.startsWith("pfbid"))) {
                                        const curUrl = window.location.href || "";
                                        const mUrl = curUrl.match(/(?:story_fbid=|posts\/|videos\/|watch\/\?v=|reel\/)(\d+)/);
                                        if (mUrl && mUrl[1]) {
                                            storyId = mUrl[1];
                                        } else {
                                            const html = document.documentElement.innerHTML || "";
                                            const mHtml = html.match(/"(?:legacy_story_id|story_fbid|post_id|story_id|subscription_target_id|feedback_target_id)"\s*:\s*"(\d{8,})"/);
                                            if (mHtml && mHtml[1]) storyId = mHtml[1];
                                        }
                                    }

                                    if (storyId) {
                                        try {
                                            const targetFeedbackId = btoa("feedback:" + storyId);
                                            const queryVars = {
                                                feedbackSource: 2, feedLocation: "POST_PERMALINK_DIALOG", focusCommentID: null,
                                                privacySelectorRenderLocation: "COMET_STREAM", renderLocation: "permalink", scale: 2, useDefaultActor: false, id: targetFeedbackId
                                            };
                                            const queryParams = new URLSearchParams();
                                            queryParams.append("av", actorId); queryParams.append("__user", actorId); queryParams.append("__a", "1");
                                            queryParams.append("fb_dtsg", fb_dtsg); queryParams.append("jazoest", jazoest); queryParams.append("lsd", lsd);
                                            queryParams.append("fb_api_caller_class", "RelayModern");
                                            queryParams.append("fb_api_req_friendly_name", "CometSinglePostDialogContentQuery");
                                            queryParams.append("variables", JSON.stringify(queryVars));
                                            queryParams.append("doc_id", "25494545246909173");

                                            const res = await fetch("https://www.facebook.com/api/graphql/", {
                                                method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: queryParams.toString(), credentials: "include"
                                            });
                                            const text = await res.text();

                                            // Method A: Recursive JSON Parser
                                            const cleanedText = text.replace(/^for\s*\([^)]*\);?/, "").trim();
                                            const linesArr = cleanedText.split("\n");
                                            for (const line of linesArr) {
                                                if (!line.trim()) continue;
                                                try {
                                                    const parsed = JSON.parse(line.trim());
                                                    async function processGqlObj(obj) {
                                                        if (!obj || typeof obj !== "object") return;
                                                        if (obj.legacy_fbid || (obj.__typename === "Comment" && (obj.id || obj.legacy_fbid))) {
                                                            const cmtId = String(obj.legacy_fbid || obj.id || "");
                                                            const authObj = obj.author || obj.comment_author || {};
                                                            const authName = typeof authObj === "object" ? (authObj.name || authObj.short_name || "Khách hàng") : String(authObj || "Khách hàng");
                                                            const authId = typeof authObj === "object" ? String(authObj.id || "") : "";

                                                            let cmtText = "";
                                                            if (obj.body && typeof obj.body === "object" && obj.body.text) cmtText = String(obj.body.text);
                                                            else if (obj.preferred_body && typeof obj.preferred_body === "object" && obj.preferred_body.text) cmtText = String(obj.preferred_body.text);
                                                            else if (obj.message && typeof obj.message === "object" && obj.message.text) cmtText = String(obj.message.text);
                                                            else if (typeof obj.body === "string") cmtText = obj.body;
                                                            else if (typeof obj.text === "string") cmtText = obj.text;

                                                            const cmtTime = obj.created_time ? (obj.created_time * 1000) : Date.now();
                                                            const isSelf = (authId && String(authId) === String(actorId));

                                                            const parentObj = obj.comment_parent || obj.comment_direct_parent || null;
                                                            let parentCommentId = parentObj ? String(parentObj.legacy_fbid || parentObj.id || "") : null;
                                                            if (parentCommentId === cmtId || parentCommentId === storyId) parentCommentId = null;

                                                            if (cmtId && cmtId !== storyId && cmtText && !scannedComments.some(c => c.id === cmtId)) {
                                                                scannedComments.push({
                                                                    id: cmtId,
                                                                    authorName: authName,
                                                                    authorId: authId,
                                                                    text: cmtText,
                                                                    time: cmtTime,
                                                                    isSelf: isSelf,
                                                                    parentCommentId: parentCommentId
                                                                });
                                                                if (parentCommentId) {
                                                                    const parentItem = scannedComments.find(c => c.id === parentCommentId);
                                                                    if (parentItem) parentItem.isReplied = true;
                                                                }
                                                            }
                                                        }
                                                        for (const k of Object.keys(obj)) await processGqlObj(obj[k]);
                                                    }
                                                    await processGqlObj(parsed);
                                                } catch(e) {}
                                            }

                                            // Method B: High-Precision Regex Parser Fallback
                                            if (scannedComments.length === 0) {
                                                const fbidMatches = text.matchAll(/"legacy_fbid"\s*:\s*"(\d+)"/g);
                                                for (const m of fbidMatches) {
                                                    const cmtId = m[1];
                                                    if (cmtId && cmtId !== storyId && !scannedComments.some(c => c.id === cmtId)) {
                                                        const pos = m.index;
                                                        const snippet = text.slice(Math.max(0, pos - 300), Math.min(text.length, pos + 600));
                                                        const bodyMatch = snippet.match(/"body"\s*:\s*\{\s*"text"\s*:\s*"([^"]+)"/);
                                                        const nameMatch = snippet.match(/"author"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"/);
                                                        
                                                        let rawText = bodyMatch ? bodyMatch[1] : "";
                                                        try { rawText = JSON.parse(`"${rawText}"`); } catch(e) {}
                                                        let rawName = nameMatch ? nameMatch[1] : "Khách hàng";
                                                        try { rawName = JSON.parse(`"${rawName}"`); } catch(e) {}

                                                        if (rawText) {
                                                            scannedComments.push({
                                                                id: cmtId,
                                                                authorName: rawName,
                                                                authorId: "",
                                                                text: rawText,
                                                                time: Date.now(),
                                                                isSelf: false
                                                            });
                                                        }
                                                    }
                                                }
                                            }
                                        } catch(e) {}
                                    }

                                    // Method C: Direct DOM Scraper Fallback on active tab
                                    if (scannedComments.length === 0) {
                                        try {
                                            const articles = document.querySelectorAll('[role="article"]');
                                            for (const art of articles) {
                                                const txt = art.innerText || "";
                                                const lines = txt.split("\n").map(l => l.trim()).filter(Boolean);
                                                if (lines.length >= 2 && !txt.includes("Viết bình luận")) {
                                                    const name = lines[0];
                                                    const content = lines.slice(1).join(" ");
                                                    if (content && !scannedComments.some(c => c.text === content)) {
                                                        scannedComments.push({
                                                            id: "dom_" + Math.random().toString(36).slice(2, 9),
                                                            authorName: name,
                                                            text: content,
                                                            time: Date.now(),
                                                            isSelf: false
                                                        });
                                                    }
                                                }
                                            }
                                        } catch(e) {}
                                    }

                                    return { scannedComments, detectedStoryId: storyId };
                                },
                                args: [realPostId, post.actorId || ""]
                            });

                            const execRes = results?.[0]?.result || {};
                            const scanned = execRes.scannedComments || [];
                            const detectedId = execRes.detectedStoryId || null;

                            if (detectedId && (!post.fbPostId || post.fbPostId === post.id)) {
                                await fetch(`${_syncUrl}/api/posts/${post.id}`, {
                                    method: "PATCH", headers: _getSyncHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ fbPostId: detectedId, fbFeedbackId: detectedId })
                                });
                            }

                            if (scanned.length > 0) {
                                await fetch(`${_syncUrl}/api/posts/${post.id}/comments`, {
                                    method: "POST", headers: _getSyncHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ comments: scanned })
                                });
                                await updateStep(`🎉 [THÀNH CÔNG QUÉT BÌNH LUẬN] Đã tải ${scanned.length} bình luận thực tế từ Facebook!`);
                            } else {
                                await updateStep(`✨ [QUÉT BÌNH LUẬN XONG] Bài viết hiện chưa có bình luận nào trên Facebook.`);
                            }
                            return { success: true, count: scanned.length };
                        } catch(e) {
                            await updateStep(`❌ [LỖI QUÉT BÌNH LUẬN] ${e.message}`);
                            return { success: false, error: e.message };
                        }
                    }

                    await updateStep(`🎉 4/4: Đã đăng bài viết thành công qua Direct GraphQL API!${pid ? ' ID: ' + pid : ''}`);
                    return { success: true, method: "graphql", fbPostId: pid, fbPostUrl: purl };
                }

                const graphqlErrMsg = graphqlResult?.error || "Direct GraphQL API failed to publish story";
                console.warn(`❌ [Background] Direct GraphQL API FAILED (${graphqlErrMsg}), starting TIER 2 DOM Fallback...`);
                await updateStep(`🤖 Direct GraphQL bị Facebook chặn (${graphqlErrMsg}). Đang tự động chuyển sang đăng bài qua Giao diện Facebook (DOM Fallback)...`);

                try {
                    const domResults = await chrome.scripting.executeScript({
                        target: { tabId: targetTab.id },
                        func: async (postContent) => {
                            try {
                                // 1. Find & click Facebook Composer opener button
                                let composerBtn = null;
                                const buttons = Array.from(document.querySelectorAll('[role="button"], [role="link"], span'));
                                composerBtn = buttons.find(b => {
                                    const txt = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
                                    return txt.includes('bạn đang nghĩ gì') || txt.includes("what's on your mind") || txt.includes('tạo bài viết') || txt.includes('create post');
                                });

                                if (composerBtn) {
                                    composerBtn.click();
                                    await new Promise(r => setTimeout(r, 1500));
                                }

                                // 2. Poll for modal dialog & text input box (up to 6 seconds)
                                let dialog = null;
                                let inputEl = null;
                                for (let attempt = 0; attempt < 15; attempt++) {
                                    dialog = document.querySelector('[role="dialog"]');
                                    if (dialog) {
                                        inputEl = dialog.querySelector('[contenteditable="true"], [role="textbox"], [data-lexical-editor="true"], div[aria-label*="Bạn đang nghĩ gì"], div[aria-label*="What\'s on your mind"]');
                                    }
                                    if (!inputEl) {
                                        inputEl = document.querySelector('[role="dialog"] [contenteditable="true"], [contenteditable="true"], [role="textbox"]');
                                    }
                                    if (inputEl) break;
                                    await new Promise(r => setTimeout(r, 400));
                                }

                                if (!inputEl) {
                                    return { success: false, error: "Không tìm thấy ô nhập nội dung bài viết trên Facebook Web" };
                                }

                                // 3. Focus & insert text into Lexical / Draft.js editor
                                inputEl.focus();
                                const inserted = document.execCommand("insertText", false, postContent);
                                if (!inserted || !inputEl.textContent.trim()) {
                                    inputEl.innerText = postContent;
                                    inputEl.dispatchEvent(new InputEvent("input", { inputType: "insertText", data: postContent, bubbles: true }));
                                }
                                inputEl.dispatchEvent(new Event("input", { bubbles: true }));
                                await new Promise(r => setTimeout(r, 1500));

                                // 4. Poll for active 'Đăng' / 'Post' submit button (up to 4 seconds)
                                let submitBtn = null;
                                for (let attempt = 0; attempt < 10; attempt++) {
                                    const container = dialog || document;
                                    const allBtns = Array.from(container.querySelectorAll('[role="button"]'));
                                    submitBtn = allBtns.find(b => {
                                        const txt = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
                                        const isMatch = txt === 'đăng' || txt === 'post' || txt === 'chia sẻ' || txt === 'share';
                                        const isDisabled = b.getAttribute('aria-disabled') === 'true' || b.hasAttribute('disabled');
                                        return isMatch && !isDisabled;
                                    });
                                    if (submitBtn) break;
                                    await new Promise(r => setTimeout(r, 400));
                                }

                                if (!submitBtn) {
                                    return { success: false, error: "Không tìm thấy nút 'Đăng' đang kích hoạt trên Facebook Web" };
                                }

                                submitBtn.click();
                                await new Promise(r => setTimeout(r, 4000));
                                return { success: true, method: "dom_fallback" };
                            } catch(err) {
                                return { success: false, error: err.message };
                            }
                        },
                        args: [payload.content || ""]
                    });

                    const domRes = domResults && domResults[0] && domResults[0].result;
                    if (domRes && domRes.success) {
                        await updateStep(`🎉 4/4: Đã tự động đăng bài thành công qua Giao diện Facebook (DOM Fallback)!`);
                        return { success: true, method: "dom_fallback" };
                    } else {
                        const domErrMsg = domRes?.error || "Giao diện Facebook không phản hồi nút Đăng";
                        await updateStep(`❌ 4/4: ${domErrMsg} (GQL: ${graphqlErrMsg})`);
                        return { success: false, error: `${domErrMsg} (GQL: ${graphqlErrMsg})`, method: "dom_fallback" };
                    }
                } catch(domErr) {
                    await updateStep(`❌ 4/4: Lỗi Giao diện FB: ${domErr.message} (GQL: ${graphqlErrMsg})`);
                    return { success: false, error: domErr.message, method: "dom_fallback" };
                }
    } catch (e) {
        return { success: false, error: e.message };
    }
}

async function _extractFacebookAccessToken() {
    await _ensureStorageReady();
    try {
        const tabs = await chrome.tabs.query({ url: "*://*.facebook.com/*" });
        if (!tabs || tabs.length === 0) {
            return { success: false, error: "Vui lòng mở một tab Facebook (https://www.facebook.com) và bấm lại!" };
        }

        const targetTab = tabs.find(t => t.active) || tabs[0];
        const results = await chrome.scripting.executeScript({
            target: { tabId: targetTab.id },
            world: "MAIN",
            func: () => {
                try {
                    let token = window.__accessToken || "";

                    if (!token) {
                        const scripts = Array.from(document.querySelectorAll("script"));
                        for (const s of scripts) {
                            const txt = s.textContent || "";
                            const match = txt.match(/["'](EAAG[A-Za-z0-9]+)["']/) || txt.match(/["'](EAAU[A-Za-z0-9]+)["']/);
                            if (match && match[1]) { token = match[1]; break; }
                        }
                    }

                    if (!token && window.require) {
                        try {
                            const asyncUtils = window.require("CometAsyncRequestUtils");
                            if (asyncUtils && asyncUtils.getAsyncParams) {
                                const params = asyncUtils.getAsyncParams();
                                if (params && params.av) token = params.av;
                            }
                        } catch (e) {}
                    }

                    // Extract Active Account / Nick Details
                    let actorId = "";
                    let name = "";
                    let isPage = false;

                    try {
                        if (typeof require !== "undefined") {
                            const ca = require("CometCurrentActor");
                            if (ca) {
                                actorId = ca.actorId || ca.id || (typeof ca.get === "function" ? ca.get() : null) || "";
                                name = ca.name || ca.shortName || "";
                                if (ca.isPage || ca.is_page) isPage = true;
                            }
                        }
                    } catch(e) {}

                    if (!actorId || !name) {
                        try {
                            const cu = window.CurrentUserInitialData || (typeof require !== "undefined" ? require("CurrentUserInitialData") : null);
                            if (cu) {
                                if (!actorId) actorId = cu.ACCOUNT_ID || cu.USER_ID || cu.actor_id || "";
                                if (!name) name = cu.NAME || cu.USER_NAME || cu.name || "";
                            }
                        } catch(e) {}
                    }

                    if (!actorId) {
                        try {
                            if (window.Env && (window.Env.user || window.Env.ACCOUNT_ID)) {
                                actorId = String(window.Env.user || window.Env.ACCOUNT_ID);
                            } else if (window.__user) {
                                actorId = String(window.__user);
                            }
                        } catch(e) {}
                    }

                    if (!actorId) {
                        const html = document.documentElement.innerHTML || "";
                        const m = html.match(/"actorID"\s*:\s*"(\d+)"/) ||
                                  html.match(/"actor_id"\s*:\s*"(\d+)"/) ||
                                  html.match(/"USER_ID"\s*:\s*"(\d+)"/) ||
                                  html.match(/"ACCOUNT_ID"\s*:\s*"(\d+)"/);
                        if (m && m[1]) actorId = m[1];
                    }

                    if (!actorId) {
                        const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                        if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                    }

                    if (name) name = name.replace(/^Tài khoản\s*/i, "").trim();

                    return { 
                        token: token || null, 
                        actorId: actorId || "", 
                        name: name || (actorId ? `FB User (${actorId})` : "Tài Khoản Facebook"),
                        isPage: isPage || (actorId && !actorId.startsWith("1000"))
                    };
                } catch (e) {
                    return { token: null, error: e.message };
                }
            }
        });

        if (results && results[0] && results[0].result) {
            const data = results[0].result;
            let actorId = data.actorId;
            
            if (!actorId || actorId === "0") {
                try {
                    const cCookie = await chrome.cookies.get({ url: "https://www.facebook.com", name: "c_user" });
                    if (cCookie && cCookie.value) actorId = cCookie.value;
                } catch(e) {}
            }

            if (!actorId || actorId === "0") {
                return { success: false, error: "Chưa nhận diện được ID tài khoản Facebook (c_user). Vui lòng kiểm tra tab Facebook đã đăng nhập thành công." };
            }

            const nickName = data.name || `Tài Khoản Facebook (${actorId})`;
            const accountTypeLabel = data.isPage ? "[Fanpage]" : "[Cá nhân]";
            const fullName = `${accountTypeLabel} ${nickName} (${actorId})`;

            // Save to Python Backend with auth headers
            _lastExtractedAccount = { targetId: actorId, name: nickName, status: "live" };
            await fetch(`${_syncUrl}/api/accounts`, {
                method: "POST",
                headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({
                    id: `acc_${actorId}`,
                    name: fullName,
                    targetId: actorId,
                    projectKey: _projectKey || "taikhoan1",
                    accessToken: data.token || "session_cookie",
                    updatedAt: Date.now()
                })
            }).catch(() => {});

            return { success: true, token: data.token, userId: actorId, name: nickName, fullName: fullName };
        }

        return { success: false, error: "Chưa tìm thấy Access Token. Hãy bấm F5 làm mới lại trang Facebook rồi thử lại!" };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

// Automatically extract Facebook Access Token silently whenever Facebook is open/loaded
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.url && tab.url.includes("facebook.com")) {
        _extractFacebookAccessToken().catch(() => {});
    }
});
setTimeout(() => { _extractFacebookAccessToken().catch(() => {}); }, 3000);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "FETCH_FB_TOKEN") {
        _extractFacebookAccessToken()
            .then(r => sendResponse(r))
            .catch(e => sendResponse({ success: false, error: e.message }));
        return true;
    }

    // Handle post execution result from content.js
    if (message.type === "POST_RESULT") {
        const postId = message.postId;
        console.log(`📬 [Background] Received POST_RESULT for ${postId}:`, message.success ? "✅ Success" : "❌ Failed");
        
        // Resolve the pending promise in _executePostItem
        // if (postId && _pendingPostResults.has(postId)) {
        //     const resolve = _pendingPostResults.get(postId);
        //     _pendingPostResults.delete(postId);
        //     resolve({ success: message.success, error: message.error || null });
        // }
        
        // Also update Python backend with the result
        if (postId) {
            const extId = instanceId || "";
            fetch(`${_syncUrl}/sync/auto-post`, {
                method: "POST",
                headers: _getSyncHeaders({ "Content-Type": "application/json", "X-Ext-Id": extId }),
                body: JSON.stringify({
                    id: postId,
                    status: message.success ? "completed" : "failed",
                    error: message.error || null,
                    executedAt: Date.now()
                }),
                signal: AbortSignal.timeout(5000)
            }).catch(() => {});
        }
        
        sendResponse({ ok: true });
        return true;
    }

    // Handle progress updates from content.js (for dashboard display)
    if (message.type === "POST_PROGRESS") {
        console.log(`📊 [Background] Post ${message.postId} progress: [${message.step}] ${message.detail}`);
        // Store progress for dashboard polling
        chrome.storage.local.get(["post_progress"], (data) => {
            const progress = data.post_progress || {};
            progress[message.postId] = {
                step: message.step,
                detail: message.detail,
                timestamp: message.timestamp || Date.now()
            };
            chrome.storage.local.set({ post_progress: progress });
        });
        sendResponse({ ok: true });
        return true;
    }


    if (message.type === "SCHEDULE_UPDATE" || message.type === "CHECK_SCHEDULED_POSTS") {
        _processScheduledPosts().then(() => sendResponse({ ok: true }));
        return true;
    }

    if (message.type === "TRIGGER_POST_NOW" && message.postId) {
        (async () => {
            let targetPost = null;

            // Try fetching from Python backend first
            try {
                const res = await fetch(`${_syncUrl}/api/posts`, { headers: _getSyncHeaders() });
                if (res.ok) {
                    const data = await res.json();
                    targetPost = (data.posts || []).find(p => p.id === message.postId);
                }
            } catch (e) {}

            // Fallback to local extension storage
            if (!targetPost) {
                const res = await chrome.storage.local.get(["scheduled_posts"]);
                const posts = res.scheduled_posts || [];
                targetPost = posts.find(p => p.id === message.postId);
            }

            if (targetPost) {
                targetPost.status = "pending";
                targetPost.scheduledTime = Date.now();
                const execRes = await _executePostItem(targetPost);
                sendResponse({ ok: true, result: execRes });
            } else {
                sendResponse({ ok: false, error: "Post not found" });
            }
        })();
        return true;
    }

    if (message.type === "GET_METRICS" || message.type === "GET_WORKER_STATUS") {
        sendResponse({
            workerId: instanceId,
            status: _activeExecutingTaskId ? "busy" : (_isPaused ? "paused" : "online"),
            projectKey: _projectKey,
            currentTaskId: _activeExecutingTaskId,
            warmupEnabled: _warmupEnabled
        });
        return true;
    }

    if (message.type === "TOGGLE_WARMUP") {
        _warmupEnabled = !!message.enabled;
        chrome.storage.local.set({ warmupEnabled: _warmupEnabled });
        sendResponse({ ok: true, warmupEnabled: _warmupEnabled });
        return true;
    }

    if (message.type === "CHECKPOINT_DETECTED") {
        _checkpointDetected = true;
        if (_checkpointWatchdog) {
            _checkpointWatchdog.triggerAlert("dom_scanner", "checkpoint", message.keyword || "Detected via content DOM scanner");
        }
        sendResponse({ ok: true });
        return true;
    }

    return false;
});

let _autoReplyRunning = false;
async function _processAutoReplyMonitor() {
    if (_autoReplyRunning) return;
    _autoReplyRunning = true;
    try {
        const res = await fetch(`${_syncUrl}/api/posts`, { headers: _getSyncHeaders() });
        if (!res.ok) { _autoReplyRunning = false; return; }
        const data = await res.json();
        const posts = data.posts || [];

        const monitorPosts = posts.filter(p => (p.fbPostId || (p.fbPostUrl && p.fbPostUrl.includes("facebook.com"))) && p.autoReplyComments && Array.isArray(p.autoReplyComments) && p.autoReplyComments.length > 0);

        if (monitorPosts.length === 0) { _autoReplyRunning = false; return; }

        const tabs = await chrome.tabs.query({});
        let fbTab = tabs.find(t => t.url && t.url.includes("facebook.com"));
        if (!fbTab) { _autoReplyRunning = false; return; }

        const repliedCommentIds = await _getRepliedCommentIds();

        for (const post of monitorPosts) {
            let realPostId = post.fbFeedbackId || post.fbPostId || "";
            if (!realPostId || (!/^\d+$/.test(String(realPostId)) && !String(realPostId).startsWith("pfbid"))) {
                if (post.fbPostUrl) {
                    const m = post.fbPostUrl.match(/(?:story_fbid=|posts\/|videos\/|watch\/\?v=|reel\/)(\d+)/);
                    if (m && m[1]) realPostId = m[1];
                }
            }
            if (!realPostId) realPostId = post.fbPostId || post.id;

            const autoReplyTexts = post.autoReplyComments || [];
            const autoReactType = post.autoReactType || "NONE";

            try {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: fbTab.id },
                    world: "MAIN",
                    func: async (postId, autoReplyTexts, autoReactType, repliedIdsArray, fallbackActorId) => {
                        let fb_dtsg = "";
                        let lsd = "";

                        for (let attempt = 0; attempt < 5; attempt++) {
                            const html = document.documentElement.innerHTML || "";
                            try {
                                if (window.DTSGInitialData?.token) fb_dtsg = window.DTSGInitialData.token;
                                else if (window.DTSGInitData?.token) fb_dtsg = window.DTSGInitData.token;
                            } catch (e) {}

                            if (!lsd) {
                                const m = html.match(/"lsd"\s*:\s*"([^"]+)"/);
                                if (m && m[1]) lsd = m[1];
                            }
                            if (fb_dtsg) break;
                            await new Promise(r => setTimeout(r, 300));
                        }

                        const finalHtml = document.documentElement.innerHTML || "";
                        let actorId = "";
                        try {
                            const ca = typeof require !== "undefined" ? require("CometCurrentActor") : null;
                            if (ca) actorId = ca.actorId || ca.id || "";
                        } catch(e) {}
                        if (!actorId) {
                            const cUserMatch = document.cookie.match(/c_user=(\d+)/);
                            if (cUserMatch && cUserMatch[1]) actorId = cUserMatch[1];
                        }
                        if (!actorId) actorId = fallbackActorId || "";

                        if (!fb_dtsg || !actorId) return { newlyReplied: [], scannedComments: [] };

                        let jazoest = "2";
                        for (let i = 0; i < fb_dtsg.length; i++) jazoest += fb_dtsg.charCodeAt(i);

                        const newlyReplied = [];
                        const repliedSet = new Set(repliedIdsArray || []);
                        const scannedComments = [];
                        const storyMatch = String(postId).match(/\d{8,}/);
                        const storyId = storyMatch ? storyMatch[0] : String(postId);

                        // 1. Fetch live comments via CometSinglePostDialogContentQuery
                        if (storyId) {
                            try {
                                const targetFeedbackId = btoa("feedback:" + storyId);
                                const queryVars = {
                                    feedbackSource: 2, feedLocation: "POST_PERMALINK_DIALOG", focusCommentID: null,
                                    privacySelectorRenderLocation: "COMET_STREAM", renderLocation: "permalink", scale: 2, useDefaultActor: false, id: targetFeedbackId
                                };

                                const queryParams = new URLSearchParams();
                                queryParams.append("av", actorId); queryParams.append("__user", actorId); queryParams.append("__a", "1");
                                queryParams.append("fb_dtsg", fb_dtsg); queryParams.append("jazoest", jazoest); queryParams.append("lsd", lsd);
                                queryParams.append("fb_api_caller_class", "RelayModern");
                                queryParams.append("fb_api_req_friendly_name", "CometSinglePostDialogContentQuery");
                                queryParams.append("variables", JSON.stringify(queryVars));
                                queryParams.append("doc_id", "25494545246909173");

                                const res = await fetch("https://www.facebook.com/api/graphql/", {
                                    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: queryParams.toString(), credentials: "include"
                                });
                                const text = await res.text();
                                const linesArr = text.split("\n");

                                for (const line of linesArr) {
                                    if (!line.includes('"legacy_fbid"') && !line.includes('"Comment"')) continue;
                                    try {
                                        const parsed = JSON.parse(line.replace(/^for\s*\([^)]*\);?/, ""));
                                        async function processGqlObj(obj) {
                                            if (!obj || typeof obj !== "object") return;
                                            if (obj.legacy_fbid || (obj.__typename === "Comment" && obj.id)) {
                                                const cmtId = String(obj.legacy_fbid || obj.id || "");
                                                const authObj = obj.author || obj.comment_author || {};
                                                const authName = typeof authObj === "object" ? (authObj.name || authObj.short_name || "Khách hàng") : String(authObj || "Khách hàng");
                                                const authId = typeof authObj === "object" ? String(authObj.id || "") : "";
                                                let cmtText = "";
                                                if (obj.body && typeof obj.body === "object" && obj.body.text) cmtText = String(obj.body.text);
                                                else if (obj.message && typeof obj.message === "object" && obj.message.text) cmtText = String(obj.message.text);
                                                else if (typeof obj.body === "string") cmtText = obj.body;

                                                const cmtTime = obj.created_time ? (obj.created_time * 1000) : Date.now();
                                                const isSelf = (authId && String(authId) === String(actorId));

                                                if (cmtId && cmtId !== storyId) {
                                                    if (!scannedComments.some(c => c.id === cmtId)) {
                                                        scannedComments.push({
                                                            id: cmtId, authorName: authName, authorId: authId, text: cmtText, time: cmtTime, isSelf
                                                        });
                                                    }

                                                    // If customer comment and not yet replied -> Auto Reply via GraphQL!
                                                    if (!isSelf && !repliedSet.has(cmtId) && autoReplyTexts.length > 0) {
                                                        try {
                                                            const replyMsg = autoReplyTexts[Math.floor(Math.random() * autoReplyTexts.length)];
                                                            let fullAutoCmtId = cmtId;
                                                            if (!fullAutoCmtId.includes("_") && storyId) fullAutoCmtId = storyId + "_" + cmtId;
                                                            const parentCommentFbid = btoa("comment:" + fullAutoCmtId);
                                                            const replyCmtFeedbackId = btoa("feedback:" + fullAutoCmtId);

                                                            const replyVars = {
                                                                feedLocation: "POST_PERMALINK_DIALOG",
                                                                feedbackSource: 2,
                                                                groupID: null,
                                                                input: {
                                                                    client_mutation_id: String(Date.now()),
                                                                    attachments: null,
                                                                    feedback_id: replyCmtFeedbackId,
                                                                    formatting_style: null,
                                                                    is_inline_vote_enabled_for_qna: false,
                                                                    message: { ranges: [], text: replyMsg.trim() },
                                                                    reply_comment_parent_fbid: parentCommentFbid,
                                                                    reply_target_clicked: true,
                                                                    attribution_id_v2: "CometSinglePostDialogRoot.react,comet.post.single_dialog,unexpected," + Date.now() + ",881640,,,",
                                                                    feedback_source: "OBJECT",
                                                                    idempotence_token: "client:" + String(Date.now()),
                                                                    session_id: String(Date.now())
                                                                },
                                                                scale: 2,
                                                                useDefaultActor: false,
                                                                translationType: "AUTO_TRANSLATE"
                                                            };
                                                            const replyParams = new URLSearchParams();
                                                            replyParams.append("av", actorId);
                                                            replyParams.append("__user", actorId);
                                                            replyParams.append("__a", "1");
                                                            replyParams.append("fb_dtsg", fb_dtsg);
                                                            replyParams.append("jazoest", jazoest);
                                                            replyParams.append("lsd", lsd);
                                                            replyParams.append("fb_api_caller_class", "RelayModern");
                                                            replyParams.append("fb_api_req_friendly_name", "useCometUFICreateCommentMutation");
                                                            replyParams.append("server_timestamps", "true");
                                                            replyParams.append("variables", JSON.stringify(replyVars));
                                                            replyParams.append("doc_id", "27829190080054105");

                                                            const replyRes = await fetch("https://www.facebook.com/api/graphql/", {
                                                                method: "POST",
                                                                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                                                                body: replyParams.toString(),
                                                                credentials: "include"
                                                            });
                                                            const replyResText = await replyRes.text();
                                                            if (replyRes.ok && (replyResText.includes('"comment_create"') || replyResText.includes('"feedback"'))) {
                                                                newlyReplied.push(cmtId);
                                                                repliedSet.add(cmtId);
                                                            }
                                                        } catch(e) {}
                                                    }
                                                }
                                            }
                                            for (const k of Object.keys(obj)) await processGqlObj(obj[k]);
                                        }
                                        await processGqlObj(parsed);
                                    } catch(e) {}
                                }
                            } catch(e) {}
                        }

                        return { newlyReplied, scannedComments };
                    },
                    args: [realPostId, autoReplyTexts, autoReactType, Array.from(repliedCommentIds), post.actorId || ""]
                });

                const newReplied = results?.[0]?.result?.newlyReplied || [];
                const scannedComments = results?.[0]?.result?.scannedComments || [];

                if (scannedComments.length > 0) {
                    try {
                        await fetch(`${_syncUrl}/api/posts/${post.id}/comments`, {
                            method: "POST",
                            headers: _getSyncHeaders({ "Content-Type": "application/json" }),
                            body: JSON.stringify({ comments: scannedComments })
                        });
                    } catch(e) {}
                }

                if (newReplied.length > 0) {
                    for (const id of newReplied) repliedCommentIds.add(id);
                    await chrome.storage.local.set({ repliedCommentIds: Array.from(repliedCommentIds) });
                    console.log(`🤖 [Auto-Reply Monitor] Replied to ${newReplied.length} new comments for post ${post.id}`);
                }
            } catch(postErr) {
                console.warn(`⚠️ [Auto-Reply Monitor] Error for post ${post.id}:`, postErr.message);
            }
        }
    } catch(e) {
        console.warn("⚠️ [Auto-Reply Monitor Error]:", e.message);
    } finally {
        _autoReplyRunning = false;
    }
}


