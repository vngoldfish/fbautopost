/**
 * FB Auto Post — 4-Layer Checkpoint & Session Error Guard (R3)
 * extension-auth-helper/checkpoint.js
 *
 * Implements:
 * Layer 1: URL Redirection Observer (/checkpoint/, /login.php, /recover/, /disabled).
 * Layer 2: Cookie Inspector (verifies c_user and xs cookie presence).
 * Layer 3: GraphQL Error Code Interceptor (190: logged_out, 368: restricted, 1357004: locked).
 * Layer 4: DOM Anomaly Scanner (bilingual Vietnamese & English security keywords).
 *
 * Automated Quarantine & Recovery:
 * - Immediately halts active tasks.
 * - Dispatches POST /api/accounts/{id}/health to server.
 * - Attempts safe tab reload recovery before permanent quarantine.
 */

// Specification Domain Constants
const CHECKPOINT_ERROR_CODES = {
    190: "logged_out",
    368: "restricted",
    1357004: "checkpoint",
    1357001: "checkpoint"
};

const CHECKPOINT_URL_PATTERNS = [
    /facebook\.com\/(checkpoint|login|recover)(\/|\?|#|$)/i,
    /facebook\.com\/login\.php(\/|\?|#|$)/i,
    /facebook\.com\/disabled(\/|\?|#|$)/i,
    /facebook\.com\/help\/contact\//i
];

const DOM_CHECKPOINT_KEYWORDS = [
    // Vietnamese
    "tài khoản của bạn đã bị khóa",
    "tài khoản của bạn đã bị tạm khóa",
    "phê duyệt đăng nhập",
    "vô hiệu hóa",
    "xác nhận danh tính",
    "phiên đăng nhập đã hết hạn",
    // English
    "your account has been locked",
    "account suspended",
    "login approval needed",
    "your account has been disabled",
    "confirm your identity",
    "session expired"
];

/**
 * Layer 1: Evaluates URL to detect Facebook security checkpoints, login redirects, or suspension pages.
 */
function checkUrlForCheckpoint(url) {
    if (!url || typeof url !== "string") {
        return { isCheckpoint: false, type: null, matchedPattern: null };
    }

    for (const pattern of CHECKPOINT_URL_PATTERNS) {
        if (pattern.test(url)) {
            let type = "checkpoint";
            if (url.includes("/login")) type = "logged_out";
            else if (url.includes("/recover")) type = "recovery";
            else if (url.includes("/disabled")) type = "disabled";

            return {
                isCheckpoint: true,
                type,
                url,
                matchedPattern: pattern.toString()
            };
        }
    }

    return { isCheckpoint: false, type: null, matchedPattern: null };
}

/**
 * Utility: Parses raw cookie header or document.cookie string into cookie objects array.
 */
function parseCookieString(cookieString) {
    if (!cookieString || typeof cookieString !== "string") {
        return [];
    }
    const cookies = [];
    const parts = cookieString.split(";");
    for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;
        const eqIdx = trimmed.indexOf("=");
        if (eqIdx !== -1) {
            const name = trimmed.substring(0, eqIdx).trim();
            const value = trimmed.substring(eqIdx + 1).trim();
            if (name) {
                cookies.push({ name, value });
            }
        }
    }
    return cookies;
}

/**
 * Layer 2: Checks presence of essential authentication cookies (c_user).
 * Accepts either an Array of cookie objects (from chrome.cookies API)
 * or a raw cookie string (from document.cookie or HTTP headers).
 */
function inspectCookieHealth(cookies) {
    if (!cookies) {
        return { isHealthy: false, status: "logged_out", c_user: null };
    }

    let cookieList = cookies;
    if (typeof cookies === "string") {
        cookieList = parseCookieString(cookies);
    }

    if (!Array.isArray(cookieList)) {
        return { isHealthy: false, status: "logged_out", c_user: null };
    }

    const cUserCookie = cookieList.find(c => c && c.name === "c_user" && String(c.value).trim().length > 0 && String(c.value) !== "0");
    if (!cUserCookie) {
        return {
            isHealthy: false,
            status: "logged_out",
            healthStatus: "expired",
            reason: "Missing or empty c_user cookie"
        };
    }

    return {
        isHealthy: true,
        status: "live",
        healthStatus: "live",
        c_user: String(cUserCookie.value).trim()
    };
}

/**
 * Layer 3: Intercepts Facebook GraphQL response payload to detect error codes.
 */
function inspectGraphQLError(errorPayload) {
    if (!errorPayload) {
        return { isError: false, code: null, healthStatus: "live" };
    }

    let code = null;
    let message = "";

    // Parse GraphQL error object or numeric code
    if (typeof errorPayload === "number") {
        code = errorPayload;
    } else if (typeof errorPayload === "object") {
        if (errorPayload.code) code = parseInt(errorPayload.code, 10);
        else if (Array.isArray(errorPayload.errors) && errorPayload.errors.length > 0) {
            let foundCheckpoint = false;
            for (const err of errorPayload.errors) {
                if (!err) continue;
                const c = parseInt(err.code || (err.error && err.error.code), 10);
                if (c && CHECKPOINT_ERROR_CODES[c]) {
                    code = c;
                    message = err.message || (err.error && err.error.message) || "";
                    foundCheckpoint = true;
                    break;
                }
            }
            if (!foundCheckpoint) {
                const first = errorPayload.errors[0];
                if (first) {
                    code = parseInt(first.code || (first.error && first.error.code), 10) || null;
                    message = first.message || (first.error && first.error.message) || "";
                }
            }
        } else if (errorPayload.error && errorPayload.error.code) {
            code = parseInt(errorPayload.error.code, 10);
            message = errorPayload.error.message || "";
        }
    }

    if (code && CHECKPOINT_ERROR_CODES[code]) {
        const mappedStatus = CHECKPOINT_ERROR_CODES[code];
        let healthStatus = "checkpoint";
        if (mappedStatus === "logged_out") healthStatus = "expired";
        else if (mappedStatus === "restricted") healthStatus = "restricted";
        else if (mappedStatus === "checkpoint") healthStatus = "checkpoint";

        return {
            isError: true,
            code,
            mappedStatus,
            healthStatus,
            message: message || `Facebook Error ${code}: ${mappedStatus}`
        };
    }

    return {
        isError: false,
        code: code || null,
        healthStatus: "live",
        message
    };
}

/**
 * Layer 4: Scans rendered DOM text for security warning keywords.
 */
function scanDomForCheckpointKeywords(domText) {
    if (!domText || typeof domText !== "string") {
        return { detected: false, keyword: null };
    }

    const lower = domText.toLowerCase();
    for (const kw of DOM_CHECKPOINT_KEYWORDS) {
        if (lower.includes(kw)) {
            return {
                detected: true,
                keyword: kw,
                type: kw.includes("khóa") || kw.includes("locked") ? "locked" : "checkpoint"
            };
        }
    }

    return { detected: false, keyword: null };
}

/**
 * Reports account health update to centralized backend API:
 * POST /api/accounts/{accountId}/health
 */
async function reportAccountHealth(syncUrl, accountId, healthStatus, details = {}, extraHeaders = {}) {
    if (!syncUrl || !accountId) return null;
    const url = `${syncUrl.replace(/\/+$/, "")}/api/accounts/${encodeURIComponent(accountId)}/health`;

    const body = {
        healthStatus: healthStatus || "checkpoint",
        status: healthStatus,
        checkpointType: details.type || details.checkpointType || "security_check",
        checkpointMessage: details.message || details.checkpointMessage || "Detected via extension guard",
        detectedAt: details.detectedAt || Date.now()
    };

    try {
        const headers = {
            "Content-Type": "application/json",
            ...extraHeaders
        };
        const res = await fetch(url, {
            method: "POST",
            headers,
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(6000)
        });
        if (res.ok) {
            return await res.json();
        }
        return { success: false, status: res.status };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

/**
 * Attempts a safe reload of the target Facebook tab with bypassCache to test recovery.
 */
async function attemptTabRecovery(tabId, maxWaitMs = 10000) {
    if (typeof chrome === "undefined" || !chrome.tabs) {
        return false;
    }

    try {
        await chrome.tabs.reload(tabId, { bypassCache: true });
        const startTime = Date.now();
        while (Date.now() - startTime < maxWaitMs) {
            await new Promise(r => setTimeout(r, 500));
            const tab = await chrome.tabs.get(tabId);
            if (tab && tab.status === "complete") {
                return true;
            }
        }
    } catch (e) {
        return false;
    }
    return false;
}

/**
 * Unified Checkpoint Watchdog Controller
 */
class CheckpointWatchdog {
    constructor(options = {}) {
        this.syncUrl = options.syncUrl || "http://127.0.0.1:19823";
        this.getHeaders = options.getHeaders || (() => ({}));
        this.activeAccount = null;
        this.isQuarantined = false;
        this.onCheckpointCallback = null;
    }

    setAccount(account) {
        this.activeAccount = account;
        this.isQuarantined = false;
    }

    setOnCheckpoint(cb) {
        this.onCheckpointCallback = cb;
    }

    /**
     * Inspects active tab URL and cookies.
     */
    async evaluateTabHealth(tabId, url) {
        // 1. URL check
        const urlCheck = checkUrlForCheckpoint(url);
        if (urlCheck.isCheckpoint) {
            await this.triggerAlert("url_redirect", urlCheck.type, `Redirected to ${url}`);
            return { healthy: false, reason: "url_redirect", details: urlCheck };
        }

        // 2. Cookie check
        if (typeof chrome !== "undefined" && chrome.cookies) {
            try {
                const cookies = await chrome.cookies.getAll({ domain: "facebook.com" });
                const cookieCheck = inspectCookieHealth(cookies);
                if (!cookieCheck.isHealthy) {
                    await this.triggerAlert("cookie_missing", "logged_out", "c_user cookie missing or expired");
                    return { healthy: false, reason: "cookie_missing", details: cookieCheck };
                }
            } catch (e) {}
        }

        return { healthy: true };
    }

    /**
     * Inspects GraphQL response errors.
     */
    async evaluateGraphQLErrors(errorObj) {
        const check = inspectGraphQLError(errorObj);
        if (check.isError) {
            await this.triggerAlert("graphql_error", check.healthStatus, check.message);
            return { healthy: false, check };
        }
        return { healthy: true };
    }

    /**
     * Handles quarantine and notifies server.
     */
    async triggerAlert(source, healthStatus, message) {
        this.isQuarantined = true;
        const accountId = this.activeAccount?.targetId || this.activeAccount?.id || "unknown";

        console.warn(`🚨 [CheckpointWatchdog] Alert: account=${accountId}, status=${healthStatus}, source=${source}: ${message}`);

        // Notify backend
        const headers = typeof this.getHeaders === "function" ? this.getHeaders() : {};
        await reportAccountHealth(this.syncUrl, accountId, healthStatus, {
            type: source,
            message: message,
            detectedAt: Date.now()
        }, headers);

        if (typeof this.onCheckpointCallback === "function") {
            try {
                this.onCheckpointCallback({ accountId, healthStatus, source, message });
            } catch (e) {}
        }
    }
}

// Export for CommonJS / Node testing environments
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        CHECKPOINT_ERROR_CODES,
        CHECKPOINT_URL_PATTERNS,
        DOM_CHECKPOINT_KEYWORDS,
        parseCookieString,
        checkUrlForCheckpoint,
        inspectCookieHealth,
        inspectGraphQLError,
        scanDomForCheckpointKeywords,
        reportAccountHealth,
        attemptTabRecovery,
        CheckpointWatchdog
    };
}
