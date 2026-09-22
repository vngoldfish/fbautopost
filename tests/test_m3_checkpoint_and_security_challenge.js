/**
 * FB Auto Post — Milestone 3 Empirical Challenge Test Harness
 * tests/test_m3_checkpoint_and_security_challenge.js
 *
 * Adversarial and empirical stress tests for:
 * 1. Layer 1: Checkpoint URL Matcher (valid, boundary, benign, malicious, ReDoS)
 * 2. Layer 2: Cookie Health Inspector (Array objects, string formats, corrupted inputs)
 * 3. Layer 3: GraphQL Error Inspector (codes 190, 368, 1357004, 1357001, benign, malformed)
 * 4. Layer 4: DOM Anomaly Scanner (English & Vietnamese checkpoint keywords, benign DOM, noise)
 * 5. Security Headers & Fetch Audit: AST/Regex analysis of background.js for unauthenticated endpoints
 */

const fs = require('fs');
const path = require('path');

// Load checkpoint module under test
const checkpoint = require('../extension-auth-helper/checkpoint.js');

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
const findings = [];

function assert(condition, testName, details = "") {
    totalTests++;
    if (condition) {
        passedTests++;
        console.log(`  ✅ [PASS] ${testName}`);
    } else {
        failedTests++;
        console.error(`  ❌ [FAIL] ${testName}${details ? ` -> ${details}` : ""}`);
        findings.push({ testName, details });
    }
}

console.log("======================================================================");
console.log("🔥 FB AUTO POST — M3 EMPIRICAL CHALLENGE HARNESS");
console.log("======================================================================\n");

// ======================================================================
// 1. LAYER 1: URL CHECKPOINT MATCHER STRESS TESTS
// ======================================================================
console.log("[>] Section 1: Layer 1 URL Matcher (checkUrlForCheckpoint)");

const validCheckpointUrls = [
    { url: "https://www.facebook.com/checkpoint/150876538269381/", expectedType: "checkpoint" },
    { url: "https://m.facebook.com/checkpoint/?next=https%3A%2F%2Fwww.facebook.com%2F", expectedType: "checkpoint" },
    { url: "https://facebook.com/checkpoint/", expectedType: "checkpoint" },
    { url: "https://www.facebook.com/login.php?login_attempt=1", expectedType: "logged_out" },
    { url: "https://www.facebook.com/login/device-based/regular/login/?login_attempt=1", expectedType: "logged_out" },
    { url: "https://www.facebook.com/recover/initiate/", expectedType: "recovery" },
    { url: "https://www.facebook.com/disabled/", expectedType: "disabled" },
    { url: "https://www.facebook.com/help/contact/260749603972907", expectedType: "checkpoint" }
];

for (const tc of validCheckpointUrls) {
    const res = checkpoint.checkUrlForCheckpoint(tc.url);
    assert(res.isCheckpoint === true && res.type === tc.expectedType,
        `Valid checkpoint URL: ${tc.url}`,
        `Expected isCheckpoint=true, type=${tc.expectedType}, got isCheckpoint=${res.isCheckpoint}, type=${res.type}`
    );
}

const benignUrls = [
    "https://www.facebook.com/",
    "https://www.facebook.com/groups/123456789/",
    "https://www.facebook.com/profile.php?id=1000123456",
    "https://www.facebook.com/messages/t/1000123456",
    "https://www.facebook.com/watch/?v=987654321",
    "https://www.facebook.com/pages/create/",
    "https://www.facebook.com/marketplace/item/11223344/",
    "https://www.facebook.com/notifications"
];

for (const url of benignUrls) {
    const res = checkpoint.checkUrlForCheckpoint(url);
    assert(res.isCheckpoint === false && res.type === null,
        `Benign Facebook URL: ${url}`,
        `Expected isCheckpoint=false, got ${res.isCheckpoint}`
    );
}

// Boundary & Adversarial inputs for Layer 1
const boundaryUrls = [
    { input: null, desc: "null URL" },
    { input: undefined, desc: "undefined URL" },
    { input: "", desc: "empty string URL" },
    { input: 12345, desc: "numeric URL" },
    { input: {}, desc: "object URL" },
    { input: "https://facebook.com", desc: "bare domain without trailing slash" },
    { input: "https://www.google.com/checkpoint/", desc: "non-facebook domain with checkpoint path" }
];

for (const tc of boundaryUrls) {
    const res = checkpoint.checkUrlForCheckpoint(tc.input);
    assert(res.isCheckpoint === false,
        `Boundary URL handling: ${tc.desc}`,
        `Expected isCheckpoint=false, got ${res.isCheckpoint}`
    );
}

// ReDoS / Performance check with 100k characters URL
const longUrl = "https://www.facebook.com/" + "a".repeat(100000);
const startT = Date.now();
const resLong = checkpoint.checkUrlForCheckpoint(longUrl);
const elapsed = Date.now() - startT;
assert(resLong.isCheckpoint === false && elapsed < 100,
    `ReDoS protection on 100k char URL (${elapsed}ms)`,
    `Too slow: ${elapsed}ms`
);

console.log("");

// ======================================================================
// 2. LAYER 2: COOKIE HEALTH INSPECTOR STRESS TESTS
// ======================================================================
console.log("[>] Section 2: Layer 2 Cookie Inspector (inspectCookieHealth)");

// Standard Chrome Extension Cookie Objects
const validCookieArrays = [
    {
        desc: "Valid c_user + xs cookies",
        cookies: [{ name: "c_user", value: "100084247794160" }, { name: "xs", value: "32%3Abc92817" }],
        expectedHealthy: true,
        expectedUser: "100084247794160"
    },
    {
        desc: "Valid c_user among many other cookies",
        cookies: [
            { name: "fr", value: "0abc" },
            { name: "sb", value: "xyz" },
            { name: "c_user", value: "100099887766" },
            { name: "datr", value: "12345" },
            { name: "wd", value: "1920x1080" }
        ],
        expectedHealthy: true,
        expectedUser: "100099887766"
    }
];

for (const tc of validCookieArrays) {
    const res = checkpoint.inspectCookieHealth(tc.cookies);
    assert(res.isHealthy === tc.expectedHealthy && res.c_user === tc.expectedUser && res.status === "live",
        `Valid cookie array: ${tc.desc}`,
        `Got isHealthy=${res.isHealthy}, c_user=${res.c_user}`
    );
}

const invalidCookieArrays = [
    {
        desc: "Missing c_user (only xs and datr present)",
        cookies: [{ name: "xs", value: "32%3Abc92817" }, { name: "datr", value: "12345" }],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    },
    {
        desc: "Empty c_user string value",
        cookies: [{ name: "c_user", value: "" }, { name: "xs", value: "32%3Abc" }],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    },
    {
        desc: "Whitespace-only c_user string value",
        cookies: [{ name: "c_user", value: "   " }],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    },
    {
        desc: "Zero c_user value ('0')",
        cookies: [{ name: "c_user", value: "0" }],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    },
    {
        desc: "Empty array []",
        cookies: [],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    },
    {
        desc: "Corrupted items in array [null, undefined, 42, {}]",
        cookies: [null, undefined, 42, {}, { name: "unknown", value: "test" }],
        expectedHealthy: false,
        expectedStatus: "logged_out"
    }
];

for (const tc of invalidCookieArrays) {
    const res = checkpoint.inspectCookieHealth(tc.cookies);
    assert(res.isHealthy === tc.expectedHealthy && res.status === tc.expectedStatus,
        `Invalid cookie array: ${tc.desc}`,
        `Got isHealthy=${res.isHealthy}, status=${res.status}`
    );
}

// Boundary and Non-Array Types
const nonArrayCookies = [
    { input: null, desc: "null cookies" },
    { input: undefined, desc: "undefined cookies" },
    { input: 12345, desc: "numeric cookies" },
    { input: { name: "c_user", value: "1000123" }, desc: "single object instead of array" }
];

for (const tc of nonArrayCookies) {
    const res = checkpoint.inspectCookieHealth(tc.input);
    assert(res.isHealthy === false && res.status === "logged_out",
        `Boundary non-array cookie input: ${tc.desc}`,
        `Got isHealthy=${res.isHealthy}, status=${res.status}`
    );
}

// Testing String Input Behavior (Validating Hardened Fallback Parser)
console.log("  ℹ️ Testing cookie string inputs directly against inspectCookieHealth...");
const validCookieString = "c_user=100084247794160; xs=32%3Abc92817; datr=abc";
const resString = checkpoint.inspectCookieHealth(validCookieString);
console.log(`    Result for valid string '${validCookieString}': isHealthy=${resString.isHealthy}, status=${resString.status}`);
assert(resString.isHealthy === true && resString.c_user === "100084247794160",
    "String input is parsed and validates c_user successfully",
    `Cookie string parsing: isHealthy=${resString.isHealthy}, c_user=${resString.c_user}`
);

const invalidCookieString = "xs=32%3Abc92817; datr=abc";
const resInvalidString = checkpoint.inspectCookieHealth(invalidCookieString);
assert(resInvalidString.isHealthy === false && resInvalidString.status === "logged_out",
    "Cookie string missing c_user safely flags as logged_out",
    `Missing c_user string: isHealthy=${resInvalidString.isHealthy}`
);

console.log("");

// ======================================================================
// 3. LAYER 3: GRAPHQL ERROR INSPECTOR STRESS TESTS
// ======================================================================
console.log("[>] Section 3: Layer 3 GraphQL Error Inspector (inspectGraphQLError)");

const graphQLErrorCases = [
    {
        desc: "Code 190 (Token Expired / Logged Out) - numeric",
        input: 190,
        expectedError: true,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    {
        desc: "Code 190 in object { code: 190 }",
        input: { code: 190 },
        expectedError: true,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    {
        desc: "Code 190 in standard GraphQL errors array",
        input: {
            errors: [
                {
                    code: 190,
                    message: "Error validating access token: The session has been invalidated because the user changed their password or Facebook has changed the session for security reasons."
                }
            ]
        },
        expectedError: true,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    {
        desc: "Code 190 in nested error object { error: { code: 190 } }",
        input: { error: { code: 190, message: "Session expired" } },
        expectedError: true,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    {
        desc: "Code 368 (Action Blocked / Restricted) - numeric",
        input: 368,
        expectedError: true,
        expectedStatus: "restricted",
        expectedHealth: "restricted"
    },
    {
        desc: "Code 368 in GraphQL errors array",
        input: {
            errors: [
                {
                    code: 368,
                    message: "It looks like you were misusing this feature by going too fast. You've been temporarily blocked from using it."
                }
            ]
        },
        expectedError: true,
        expectedStatus: "restricted",
        expectedHealth: "restricted"
    },
    {
        desc: "Code 1357004 (Account Checkpoint / Locked) - numeric",
        input: 1357004,
        expectedError: true,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    },
    {
        desc: "Code 1357004 in GraphQL errors array",
        input: {
            errors: [
                {
                    code: 1357004,
                    message: "Your account is temporarily locked for security review."
                }
            ]
        },
        expectedError: true,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    },
    {
        desc: "Code 1357001 (Checkpoint variation)",
        input: { code: 1357001 },
        expectedError: true,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    }
];

for (const tc of graphQLErrorCases) {
    const res = checkpoint.inspectGraphQLError(tc.input);
    assert(
        res.isError === tc.expectedError &&
        res.mappedStatus === tc.expectedStatus &&
        res.healthStatus === tc.expectedHealth,
        `GraphQL error check: ${tc.desc}`,
        `Got isError=${res.isError}, mappedStatus=${res.mappedStatus}, healthStatus=${res.healthStatus}`
    );
}

// Benign errors (should NOT flag as checkpoint)
const benignGraphQLErrors = [
    {
        desc: "Code 100 (Invalid parameter)",
        input: { errors: [{ code: 100, message: "Invalid parameter: feedback_id" }] }
    },
    {
        desc: "Code 200 (Temporary warning)",
        input: { errors: [{ code: 200, message: "Permissions warning" }] }
    },
    {
        desc: "Success GraphQL payload without errors",
        input: { data: { comment_create: { id: "cmt_123" } } }
    },
    {
        desc: "Empty errors array",
        input: { errors: [] }
    },
    {
        desc: "null input",
        input: null
    },
    {
        desc: "undefined input",
        input: undefined
    },
    {
        desc: "numeric code 0",
        input: 0
    }
];

for (const tc of benignGraphQLErrors) {
    const res = checkpoint.inspectGraphQLError(tc.input);
    assert(res.isError === false && res.healthStatus === "live",
        `Benign GraphQL error: ${tc.desc}`,
        `Expected isError=false, got ${res.isError}`
    );
}

console.log("");

// ======================================================================
// 4. LAYER 4: DOM KEYWORD SCANNER STRESS TESTS
// ======================================================================
console.log("[>] Section 4: Layer 4 DOM Keyword Scanner (scanDomForCheckpointKeywords)");

const checkpointDomSnippets = [
    // English variations
    {
        desc: "English: your account has been locked",
        html: `<div class="security-box"><h2>Your account has been locked</h2><p>We saw unusual activity on your account.</p></div>`,
        expectedKeyword: "your account has been locked",
        expectedType: "locked"
    },
    {
        desc: "English: account suspended",
        html: `<div><h1>Account Suspended</h1><p>We suspended your account because your activity doesn't follow our Community Standards.</p></div>`,
        expectedKeyword: "account suspended",
        expectedType: "checkpoint"
    },
    {
        desc: "English: login approval needed",
        html: `<div role="main"><span class="title">Login approval needed</span><p>Please approve from your mobile device.</p></div>`,
        expectedKeyword: "login approval needed",
        expectedType: "checkpoint"
    },
    {
        desc: "English: your account has been disabled",
        html: `<div><p>Your account has been disabled. For more information, please visit the Help Center.</p></div>`,
        expectedKeyword: "your account has been disabled",
        expectedType: "checkpoint"
    },
    {
        desc: "English: confirm your identity",
        html: `<div><form><h3>Please Confirm Your Identity</h3></form></div>`,
        expectedKeyword: "confirm your identity",
        expectedType: "checkpoint"
    },
    {
        desc: "English: session expired",
        html: `<div><span>Session expired. Please log in again.</span></div>`,
        expectedKeyword: "session expired",
        expectedType: "checkpoint"
    },
    // Vietnamese variations
    {
        desc: "Vietnamese: tài khoản của bạn đã bị khóa",
        html: `<div class="x1jx97hy"><h2>Tài khoản của bạn đã bị khóa</h2><p>Chúng tôi nhận thấy hoạt động bất thường...</p></div>`,
        expectedKeyword: "tài khoản của bạn đã bị khóa",
        expectedType: "locked"
    },
    {
        desc: "Vietnamese: tài khoản của bạn đã bị tạm khóa",
        html: `<div><span>Tài khoản của bạn đã bị tạm khóa để bảo vệ an toàn.</span></div>`,
        expectedKeyword: "tài khoản của bạn đã bị tạm khóa",
        expectedType: "locked"
    },
    {
        desc: "Vietnamese: phê duyệt đăng nhập",
        html: `<div><h3>Yêu cầu phê duyệt đăng nhập trên thiết bị đã tin cậy</h3></div>`,
        expectedKeyword: "phê duyệt đăng nhập",
        expectedType: "checkpoint"
    },
    {
        desc: "Vietnamese: vô hiệu hóa",
        html: `<div><p>Tài khoản Facebook của bạn đã bị vô hiệu hóa do vi phạm Tiêu chuẩn cộng đồng.</p></div>`,
        expectedKeyword: "vô hiệu hóa",
        expectedType: "checkpoint"
    },
    {
        desc: "Vietnamese: xác nhận danh tính",
        html: `<div><label>Vui lòng xác nhận danh tính của bạn</label></div>`,
        expectedKeyword: "xác nhận danh tính",
        expectedType: "checkpoint"
    },
    {
        desc: "Vietnamese: phiên đăng nhập đã hết hạn",
        html: `<div><span>Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.</span></div>`,
        expectedKeyword: "phiên đăng nhập đã hết hạn",
        expectedType: "checkpoint"
    },
    // Uppercase variation
    {
        desc: "Uppercase variation: YOUR ACCOUNT HAS BEEN LOCKED",
        html: `<div><h1>YOUR ACCOUNT HAS BEEN LOCKED</h1></div>`,
        expectedKeyword: "your account has been locked",
        expectedType: "locked"
    }
];

for (const tc of checkpointDomSnippets) {
    const res = checkpoint.scanDomForCheckpointKeywords(tc.html);
    assert(
        res.detected === true &&
        res.keyword === tc.expectedKeyword &&
        res.type === tc.expectedType,
        `DOM scanner: ${tc.desc}`,
        `Got detected=${res.detected}, keyword=${res.keyword}, type=${res.type}`
    );
}

const benignDomSnippets = [
    `<div><h2>Welcome to Facebook</h2><p>Connect with friends and the world around you.</p></div>`,
    `<div><p>Trang chủ Facebook: Bảng tin, bài viết mới, nhóm và video trực tiếp.</p></div>`,
    `<div>Post published successfully! 15 likes, 3 comments, 2 shares.</div>`,
    `<div><button>Tạo bài viết mới</button></div>`,
    `<div><h3>Manage your Facebook Page</h3><p>Insights, followers, and ad campaigns.</p></div>`
];

for (let i = 0; i < benignDomSnippets.length; i++) {
    const res = checkpoint.scanDomForCheckpointKeywords(benignDomSnippets[i]);
    assert(res.detected === false && res.keyword === null,
        `Benign DOM snippet #${i + 1}`,
        `Expected detected=false, got ${res.detected}`
    );
}

// DOM Scanner Boundary cases
const boundaryDomCases = [
    { input: null, desc: "null DOM text" },
    { input: undefined, desc: "undefined DOM text" },
    { input: "", desc: "empty DOM string" },
    { input: 123456, desc: "numeric DOM input" },
    { input: {}, desc: "object DOM input" }
];

for (const tc of boundaryDomCases) {
    const res = checkpoint.scanDomForCheckpointKeywords(tc.input);
    assert(res.detected === false && res.keyword === null,
        `DOM scanner boundary: ${tc.desc}`,
        `Expected detected=false, got ${res.detected}`
    );
}

console.log("");

// ======================================================================
// 5. SECURITY HEADERS & TASK POLLER AUDIT
// ======================================================================
console.log("[>] Section 5: Security Headers & Task Poller Audit in background.js");

const bgContent = fs.readFileSync(path.join(__dirname, '../extension-auth-helper/background.js'), 'utf8');
const bgLines = bgContent.split('\n');

// 5.1 Verify _getSyncHeaders implementation
assert(bgContent.includes('function _getSyncHeaders(extra = {}) {'),
    "_getSyncHeaders() is declared in background.js"
);
assert(bgContent.includes('if (_syncToken) h["X-Sync-Token"] = _syncToken;'),
    "_getSyncHeaders() injects X-Sync-Token"
);
assert(bgContent.includes('if (_projectKey) h["X-Project-Key"] = _projectKey;'),
    "_getSyncHeaders() injects X-Project-Key"
);
assert(bgContent.includes('if (typeof instanceId === "string" && instanceId) h["X-Worker-Id"] = instanceId;'),
    "_getSyncHeaders() injects X-Worker-Id"
);

// 5.2 Forensic scan: check EVERY fetch call in background.js targeting backend (_syncUrl)
const backendFetchRegex = /fetch\s*\(\s*(_syncUrl|`\$\{_syncUrl\}[^`]*`)/g;
let match;
let backendFetchCount = 0;
let bypassCount = 0;

bgLines.forEach((line, idx) => {
    if (line.includes('_syncUrl') && (line.includes('fetch(') || line.includes('fetch ('))) {
        backendFetchCount++;
        // Check surrounding 8 lines for headers: _getSyncHeaders
        const snippet = bgLines.slice(idx, idx + 8).join('\n');
        const usesSyncHeaders = snippet.includes('_getSyncHeaders');
        if (!usesSyncHeaders) {
            bypassCount++;
            console.error(`    🚨 Fetch at line ${idx + 1} appears to bypass _getSyncHeaders():\n    ${line.trim()}`);
        }
    }
});

console.log(`    Total backend fetch calls inspected: ${backendFetchCount}`);
assert(backendFetchCount > 0, "Found backend fetch calls in background.js");
assert(bypassCount === 0, `Zero backend fetch calls bypass _getSyncHeaders() (bypasses found: ${bypassCount})`);

// 5.3 Verify Task Queue Poller Mechanics
assert(bgContent.includes('async function pollAndExecuteDistributedTask() {'),
    "pollAndExecuteDistributedTask() is implemented"
);
assert(bgContent.includes('_syncUrl + "/api/tasks/poll"'),
    "Task poller consumes POST /api/tasks/poll"
);
assert(bgContent.includes('if (_checkpointDetected) {'),
    "Task poller contains checkpoint guard checking _checkpointDetected"
);
assert(bgContent.includes('status: "failed"') && bgContent.includes('"Account is in checkpoint/restricted status"'),
    "Task poller immediately aborts task when account checkpoint detected"
);
assert(bgContent.includes('/api/tasks/" + task.id + "/heartbeat'),
    "Task poller sends periodic lease heartbeats during execution"
);
assert(bgContent.includes('clearInterval(leaseWatchdog);'),
    "Task poller cleans up lease watchdog interval in finally block"
);
assert(bgContent.includes('_isExecutingTask = false;'),
    "Task poller resets _isExecutingTask in outer finally block"
);

// ======================================================================
// 6. ADVERSARIAL EDGE-CASE MINING & HARDENING TESTS
// ======================================================================
console.log("[>] Section 6: Adversarial Edge-Case Mining & Hardening Tests");

// 6.1 URL Matcher Vanity / Boundary Challenge
const vanityUrl = "https://www.facebook.com/checkpoint.clothing";
const vanityRes = checkpoint.checkUrlForCheckpoint(vanityUrl);
console.log(`    [Adversarial Note] Vanity URL '${vanityUrl}' check result: isCheckpoint=${vanityRes.isCheckpoint} (Pattern matches substring without word boundary)`);
assert(vanityRes.isCheckpoint === false, "URL vanity handle checkpoint.clothing does not trigger false positive");

// 6.2 Multi-error GraphQL Array Challenge
const multiErrorPayload = {
    errors: [
        { code: 100, message: "Invalid parameter: feedback_id" },
        { code: 1357004, message: "Account locked for checkpoint review" }
    ]
};
const multiErrorRes = checkpoint.inspectGraphQLError(multiErrorPayload);
console.log(`    [Adversarial Note] Multi-error array with [code 100, code 1357004] result: isError=${multiErrorRes.isError}, code=${multiErrorRes.code}`);
assert(multiErrorRes.isError === true && multiErrorRes.code === 1357004, "Multi-error GraphQL payload detects security code 1357004");

// 6.3 Cookie Inspector String Input Challenge
const rawCookieString = "c_user=100084247794160; xs=32%3Abc92817";
const cookieStrRes = checkpoint.inspectCookieHealth(rawCookieString);
console.log(`    [Adversarial Note] Raw cookie string '${rawCookieString}' result: isHealthy=${cookieStrRes.isHealthy}, status=${cookieStrRes.status}`);
assert(cookieStrRes.isHealthy === true && cookieStrRes.c_user === "100084247794160", "Raw cookie string parsed and validated");

// 6.4 Watchdog Integration with Background GraphQL handlers
const bgHasGraphQLErrorHandler = bgContent.includes('evaluateGraphQLErrors(');
console.log(`    [Adversarial Note] background.js invokes _checkpointWatchdog.evaluateGraphQLErrors on GraphQL failures: ${bgHasGraphQLErrorHandler}`);
assert(bgContent.includes('new CheckpointWatchdog'), "CheckpointWatchdog is instantiated in background.js");

console.log("\n======================================================================");
console.log(`[*] SUMMARY: Total Tests: ${totalTests} | Passed: ${passedTests} | Failed: ${failedTests}`);
console.log("======================================================================\n");

if (failedTests > 0) {
    console.error(`❌ ${failedTests} test(s) failed!`);
    process.exit(1);
} else {
    console.log("🎉 ALL EMPIRICAL CHALLENGE TESTS PASSED!");
    process.exit(0);
}

