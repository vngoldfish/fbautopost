/**
 * FB Auto Post — Milestone 3 Iteration 2 Adversarial Stress Test Harness
 * tests/test_challenger_m3_checkpoint_stress.js
 *
 * Authored by: challenger_m3_gate2_2 (Empirical Challenger)
 * Verification Scope:
 * 1. Vanity handle boundary matching (zero false positives)
 * 2. Valid checkpoint URL patterns (zero false negatives)
 * 3. Multi-error GraphQL payloads (security error codes precedence over soft errors)
 * 4. Raw cookie string parsing (RFC 6265 compliant formatting, corrupted strings, missing c_user)
 * 5. CheckpointWatchdog controller behavior (alerts, quarantine, health reporting)
 */

const assert = require('assert');
const checkpoint = require('../extension-auth-helper/checkpoint.js');

let total = 0;
let passed = 0;
let failed = 0;
const failures = [];

function test(description, fn) {
    total++;
    try {
        fn();
        passed++;
        console.log(`  [PASS] ${description}`);
    } catch (err) {
        failed++;
        console.error(`  [FAIL] ${description} -> ${err.message}`);
        failures.push({ description, error: err.message });
    }
}

console.log("======================================================================");
console.log("🔥 FB AUTO POST — M3 ITERATION 2 CHECKPOINT STRESS HARNESS");
console.log("======================================================================\n");

// ======================================================================
// SECTION 1: VANITY HANDLES (ZERO FALSE POSITIVES)
// ======================================================================
console.log("--- SECTION 1: Vanity Handles & Benign URL Boundary Stress ---");

const vanityHandles = [
    // Authoritative requirements from prompt
    "https://facebook.com/checkpoint.clothing",
    "https://facebook.com/login_hub",
    "https://facebook.com/disabledveterans",
    // Subdomain variations
    "https://www.facebook.com/checkpoint.clothing",
    "https://m.facebook.com/checkpoint.clothing",
    "https://web.facebook.com/checkpoint.clothing",
    "https://www.facebook.com/login_hub",
    "https://m.facebook.com/login_hub",
    "https://www.facebook.com/disabledveterans",
    "https://m.facebook.com/disabledveterans",
    // Additional adversarial vanity handles
    "https://facebook.com/checkpoint123",
    "https://facebook.com/checkpoint-app",
    "https://facebook.com/checkpoint_security_services",
    "https://facebook.com/login-page-design",
    "https://facebook.com/login_support_center",
    "https://facebook.com/disabled_athletes_foundation",
    "https://facebook.com/recover-fitness-club",
    "https://facebook.com/checkpoint.clothing/posts/1015829182",
    "https://facebook.com/checkpoint.clothing?ref=bookmarks",
    "https://facebook.com/login_hub?id=987654",
    "https://facebook.com/disabledveterans/photos",
    // Standard benign paths
    "https://www.facebook.com/",
    "https://www.facebook.com/marketplace",
    "https://www.facebook.com/watch",
    "https://www.facebook.com/groups/feed/",
    "https://www.facebook.com/pages/manage/"
];

for (const url of vanityHandles) {
    test(`Vanity / benign handle is NOT a checkpoint: ${url}`, () => {
        const res = checkpoint.checkUrlForCheckpoint(url);
        assert.strictEqual(res.isCheckpoint, false, `Expected isCheckpoint: false for ${url}, got: ${JSON.stringify(res)}`);
        assert.strictEqual(res.type, null);
    });
}

console.log("");

// ======================================================================
// SECTION 2: VALID CHECKPOINTS (ZERO FALSE NEGATIVES)
// ======================================================================
console.log("--- SECTION 2: Valid Checkpoint URLs & Suspensions ---");

const validCheckpoints = [
    // Authoritative requirements from prompt
    { url: "https://facebook.com/checkpoint/123/", expectedType: "checkpoint" },
    { url: "https://facebook.com/checkpoint?next=https%3A%2F%2Fwww.facebook.com", expectedType: "checkpoint" },
    { url: "https://facebook.com/login.php?login_attempt=1", expectedType: "logged_out" },
    { url: "https://facebook.com/disabled/", expectedType: "disabled" },
    // Trailing slash / boundary edge cases
    { url: "https://www.facebook.com/checkpoint", expectedType: "checkpoint" },
    { url: "https://www.facebook.com/checkpoint/", expectedType: "checkpoint" },
    { url: "https://www.facebook.com/checkpoint#security_wizard", expectedType: "checkpoint" },
    { url: "https://m.facebook.com/checkpoint/?next=home", expectedType: "checkpoint" },
    { url: "https://www.facebook.com/login", expectedType: "logged_out" },
    { url: "https://www.facebook.com/login/", expectedType: "logged_out" },
    { url: "https://www.facebook.com/login?id=456", expectedType: "logged_out" },
    { url: "https://www.facebook.com/login.php", expectedType: "logged_out" },
    { url: "https://www.facebook.com/recover", expectedType: "recovery" },
    { url: "https://www.facebook.com/recover/", expectedType: "recovery" },
    { url: "https://www.facebook.com/recover?account_id=789", expectedType: "recovery" },
    { url: "https://www.facebook.com/disabled", expectedType: "disabled" },
    { url: "https://www.facebook.com/disabled?code=suspension", expectedType: "disabled" },
    { url: "https://facebook.com/help/contact/123456789", expectedType: "checkpoint" }
];

for (const tc of validCheckpoints) {
    test(`Valid checkpoint URL detected: ${tc.url} (type: ${tc.expectedType})`, () => {
        const res = checkpoint.checkUrlForCheckpoint(tc.url);
        assert.strictEqual(res.isCheckpoint, true, `Expected isCheckpoint: true for ${tc.url}`);
        assert.strictEqual(res.type, tc.expectedType, `Expected type ${tc.expectedType}, got ${res.type}`);
    });
}

console.log("");

// ======================================================================
// SECTION 3: MULTI-ERROR GRAPHQL PAYLOADS
// ======================================================================
console.log("--- SECTION 3: Multi-Error GraphQL Payload Inspection ---");

const multiErrorCases = [
    // Authoritative requirements from prompt
    {
        desc: "Soft error 100 precedes checkpoint code 1357004",
        payload: { errors: [{ code: 100, message: "Invalid field" }, { code: 1357004, message: "Account checkpoint" }] },
        expectedCode: 1357004,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    },
    {
        desc: "Soft error 200 precedes session code 190",
        payload: { errors: [{ code: 200, message: "Permissions warning" }, { code: 190, message: "Token expired" }] },
        expectedCode: 190,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    // More complex sequences
    {
        desc: "Multiple soft warnings (100, 500) before action block 368",
        payload: {
            errors: [
                { code: 100, message: "Soft warn 1" },
                { code: 500, message: "Internal server error" },
                { code: 368, message: "Temporarily blocked from posting" }
            ]
        },
        expectedCode: 368,
        expectedStatus: "restricted",
        expectedHealth: "restricted"
    },
    {
        desc: "Checkpoint variation 1357001 preceded by code 100",
        payload: { errors: [{ code: 100 }, { code: 1357001 }] },
        expectedCode: 1357001,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    },
    {
        desc: "Nested error objects within GraphQL errors array",
        payload: {
            errors: [
                { error: { code: 100, message: "Soft warn" } },
                { error: { code: 1357004, message: "Locked checkpoint" } }
            ]
        },
        expectedCode: 1357004,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    },
    {
        desc: "String codes in multi-error array",
        payload: {
            errors: [
                { code: "100" },
                { code: "190" }
            ]
        },
        expectedCode: 190,
        expectedStatus: "logged_out",
        expectedHealth: "expired"
    },
    {
        desc: "Array with corrupted or empty error slots before checkpoint code",
        payload: {
            errors: [
                null,
                undefined,
                {},
                { code: 1357004, message: "Recovered from corrupted array slots" }
            ]
        },
        expectedCode: 1357004,
        expectedStatus: "checkpoint",
        expectedHealth: "checkpoint"
    }
];

for (const tc of multiErrorCases) {
    test(`Multi-error payload: ${tc.desc}`, () => {
        const res = checkpoint.inspectGraphQLError(tc.payload);
        assert.strictEqual(res.isError, true, `Expected isError: true`);
        assert.strictEqual(res.code, tc.expectedCode, `Expected code ${tc.expectedCode}, got ${res.code}`);
        assert.strictEqual(res.mappedStatus, tc.expectedStatus, `Expected mappedStatus ${tc.expectedStatus}, got ${res.mappedStatus}`);
        assert.strictEqual(res.healthStatus, tc.expectedHealth, `Expected healthStatus ${tc.expectedHealth}, got ${res.healthStatus}`);
    });
}

// Benign-only multi-error arrays
const benignMultiErrorCases = [
    {
        desc: "Multi-error array containing only soft warnings (100, 200, 404)",
        payload: { errors: [{ code: 100 }, { code: 200 }, { code: 404 }] }
    },
    {
        desc: "Empty errors array",
        payload: { errors: [] }
    },
    {
        desc: "Errors array with null elements only",
        payload: { errors: [null, undefined, {}] }
    }
];

for (const tc of benignMultiErrorCases) {
    test(`Benign multi-error payload: ${tc.desc}`, () => {
        const res = checkpoint.inspectGraphQLError(tc.payload);
        assert.strictEqual(res.isError, false, `Expected isError: false`);
        assert.strictEqual(res.healthStatus, "live", `Expected healthStatus: live`);
    });
}

console.log("");

// ======================================================================
// SECTION 4: RAW COOKIE STRINGS
// ======================================================================
console.log("--- SECTION 4: Raw Cookie String Parsing & Health Inspection ---");

// 4.1 Valid cookie strings
const validCookieStrings = [
    {
        desc: "Standard cookie header string with c_user and xs",
        raw: "c_user=100084247794160; xs=32%3Abc92817; datr=abc_token",
        expectedUser: "100084247794160"
    },
    {
        desc: "Cookie string with excessive spaces around '=' and ';'",
        raw: "   c_user  =   100084247794160  ;   xs = token_123   ;   fr = 0xyz   ",
        expectedUser: "100084247794160"
    },
    {
        desc: "Single c_user cookie string without trailing semicolon",
        raw: "c_user=100099887766554",
        expectedUser: "100099887766554"
    },
    {
        desc: "Cookie string where other cookies contain '=' in their values",
        raw: "datr=abc=def==; c_user=100011223344; xs=base64==token; wd=1920x1080",
        expectedUser: "100011223344"
    },
    {
        desc: "c_user at the very end of a long cookie header",
        raw: "sb=1; fr=2; presence=3; locale=en_US; c_user=100077889900",
        expectedUser: "100077889900"
    }
];

for (const tc of validCookieStrings) {
    test(`Valid cookie string: ${tc.desc}`, () => {
        const parsed = checkpoint.parseCookieString(tc.raw);
        assert(Array.isArray(parsed), "parseCookieString should return an array");
        const found = parsed.find(c => c.name === "c_user");
        assert(found, "c_user cookie must be present in parsed list");
        assert.strictEqual(found.value, tc.expectedUser);

        const health = checkpoint.inspectCookieHealth(tc.raw);
        assert.strictEqual(health.isHealthy, true, `Expected isHealthy: true`);
        assert.strictEqual(health.status, "live", `Expected status: live`);
        assert.strictEqual(health.c_user, tc.expectedUser, `Expected c_user: ${tc.expectedUser}`);
    });
}

// 4.2 Corrupted or missing c_user cookie strings
const invalidCookieStrings = [
    {
        desc: "Missing c_user entirely (only xs and datr)",
        raw: "xs=32%3Abc92817; datr=abc_token; sb=xyz"
    },
    {
        desc: "c_user with empty value: c_user=",
        raw: "c_user=; xs=32%3Abc92817; datr=abc_token"
    },
    {
        desc: "c_user with whitespace value: c_user=   ",
        raw: "c_user=   ; xs=32%3Abc92817"
    },
    {
        desc: "c_user with zero value: c_user=0",
        raw: "c_user=0; xs=32%3Abc92817"
    },
    {
        desc: "Malformed delimiter string: ;;;===;;;",
        raw: ";;;===;;;"
    },
    {
        desc: "Empty cookie string: ''",
        raw: ""
    },
    {
        desc: "Whitespace-only cookie string: '   '",
        raw: "   "
    },
    {
        desc: "Arbitrary text without key-value formatting",
        raw: "ThisIsNotACookieHeaderAtAll"
    },
    {
        desc: "null cookie input",
        raw: null
    },
    {
        desc: "undefined cookie input",
        raw: undefined
    },
    {
        desc: "numeric cookie input",
        raw: 987654321
    },
    {
        desc: "boolean cookie input",
        raw: false
    }
];

for (const tc of invalidCookieStrings) {
    test(`Corrupted / missing c_user string: ${tc.desc}`, () => {
        const health = checkpoint.inspectCookieHealth(tc.raw);
        assert.strictEqual(health.isHealthy, false, `Expected isHealthy: false for ${tc.desc}`);
        assert.strictEqual(health.status, "logged_out", `Expected status: logged_out`);
        assert(!health.c_user, `Expected c_user to be falsy`);
    });
}

console.log("");

// ======================================================================
// SECTION 5: CONTROLLER INTEGRATION (CheckpointWatchdog)
// ======================================================================
console.log("--- SECTION 5: CheckpointWatchdog Controller Integration ---");

test("CheckpointWatchdog tab health evaluation: benign vs checkpoint URLs", async () => {
    const watchdog = new checkpoint.CheckpointWatchdog({
        syncUrl: "http://127.0.0.1:19823",
        getHeaders: () => ({ "X-Sync-Token": "test-token" })
    });
    watchdog.setAccount({ targetId: "100084247794160", name: "Test Account" });

    // 1. Benign tab URL
    const benignRes = await watchdog.evaluateTabHealth(1, "https://facebook.com/checkpoint.clothing");
    assert.strictEqual(benignRes.healthy, true, "Benign vanity URL should report healthy: true");
    assert.strictEqual(watchdog.isQuarantined, false, "Watchdog should not be quarantined");

    // 2. Checkpoint tab URL
    let alerted = false;
    watchdog.setOnCheckpoint((info) => {
        alerted = true;
        assert.strictEqual(info.accountId, "100084247794160");
        assert.strictEqual(info.source, "url_redirect");
    });

    const cpRes = await watchdog.evaluateTabHealth(2, "https://facebook.com/checkpoint/123/");
    assert.strictEqual(cpRes.healthy, false, "Checkpoint URL should report healthy: false");
    assert.strictEqual(watchdog.isQuarantined, true, "Watchdog should enter quarantine state");
    assert.strictEqual(alerted, true, "Checkpoint callback must have fired");
});

test("CheckpointWatchdog GraphQL multi-error evaluation", async () => {
    const watchdog = new checkpoint.CheckpointWatchdog({
        syncUrl: "http://127.0.0.1:19823"
    });
    watchdog.setAccount({ targetId: "100084247794160" });

    let callbackTriggered = false;
    watchdog.setOnCheckpoint((info) => {
        callbackTriggered = true;
        assert.strictEqual(info.healthStatus, "checkpoint");
    });

    const multiError = {
        errors: [
            { code: 100, message: "Benign param warning" },
            { code: 1357004, message: "Security checkpoint required" }
        ]
    };

    const res = await watchdog.evaluateGraphQLErrors(multiError);
    assert.strictEqual(res.healthy, false);
    assert.strictEqual(res.check.code, 1357004);
    assert.strictEqual(watchdog.isQuarantined, true);
    assert.strictEqual(callbackTriggered, true);
});

console.log("\n======================================================================");
console.log(`[*] SUMMARY: Total Tests: ${total} | Passed: ${passed} | Failed: ${failed}`);
console.log("======================================================================\n");

if (failed > 0) {
    console.error(`❌ STRESS HARNESS FAILED with ${failed} failure(s):`);
    for (const f of failures) {
        console.error(`  - ${f.description}: ${f.error}`);
    }
    process.exit(1);
} else {
    console.log("🏆 ALL EMPIRICAL STRESS TESTS PASSED WITH 100% SUCCESS!");
    process.exit(0);
}
