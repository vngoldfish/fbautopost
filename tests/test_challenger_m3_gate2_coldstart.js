/**
 * tests/test_challenger_m3_gate2_coldstart.js
 * Adversarial Empirical Stress Tests for Cold-Start Worker Header Behavior
 * Milestone 3 Iteration 2 (Gate 2)
 * Author: challenger_m3_gate2_1
 *
 * Verifies:
 * 1. Synchronous Tick 0 evaluation of _getSyncHeaders() in background.js
 * 2. Guaranteed non-empty X-Worker-Id on Tick 0 (via _ephemeralBootId)
 * 3. InstanceId transition once storage resolves
 * 4. Fallback resilience when instanceId in storage is empty, null, undefined, or non-string
 * 5. Deterministic repeatability across multiple Tick 0 calls
 * 6. Multi-boot collision resistance (1,000 cold boots produce 1,000 distinct IDs)
 * 7. Token presence & RFC 6750 Authorization: Bearer pairing across lifecycle states
 * 8. Fallback generation when crypto.randomUUID is absent
 * 9. Preservation of custom extra headers
 * 10. Dynamic updates on chrome.storage.onChanged
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
const failures = [];

function assert(condition, testName, details = "") {
    totalTests++;
    if (condition) {
        passedTests++;
        console.log(`  ✅ [PASS] ${testName}`);
    } else {
        failedTests++;
        console.error(`  ❌ [FAIL] ${testName}${details ? ` -> ${details}` : ""}`);
        failures.push({ testName, details });
    }
}

console.log("======================================================================");
console.log("🔥 CHALLENGER 1 (GATE 2): COLD-START HEADER & LIFECYCLE EMPIRICAL HARNESS");
console.log("======================================================================\n");

const bgSourcePath = path.join(__dirname, '../extension-auth-helper/background.js');
const bgCode = fs.readFileSync(bgSourcePath, 'utf8');

/**
 * Creates a sandbox simulating Chrome Extension Service Worker environment.
 */
function createExtensionSandbox(options = {}) {
    const storageData = options.storageData || {};
    const storageDelayMs = options.storageDelayMs !== undefined ? options.storageDelayMs : 50;
    const includeRandomUUID = options.includeRandomUUID !== false;

    let storageChangeListeners = [];

    const mockStorage = {
        local: {
            get: (keys, callback) => {
                const result = {};
                const keyList = Array.isArray(keys) ? keys : [keys];
                keyList.forEach(k => {
                    if (storageData[k] !== undefined) {
                        result[k] = storageData[k];
                    }
                });

                if (storageDelayMs === 0) {
                    if (typeof callback === 'function') callback(result);
                    return Promise.resolve(result);
                }

                return new Promise((resolve) => {
                    setTimeout(() => {
                        if (typeof callback === 'function') callback(result);
                        resolve(result);
                    }, storageDelayMs);
                });
            },
            set: (items, callback) => {
                Object.assign(storageData, items);
                if (typeof callback === 'function') callback();
                return Promise.resolve();
            }
        },
        onChanged: {
            addListener: (fn) => storageChangeListeners.push(fn)
        }
    };

    function triggerStorageChange(changes, area = 'local') {
        storageChangeListeners.forEach(fn => {
            try { fn(changes, area); } catch (e) {}
        });
    }

    function createRecursiveProxy(targetObj = {}) {
        return new Proxy(targetObj, {
            get: (target, prop) => {
                if (prop in target) return target[prop];
                if (prop === 'then' || prop === 'catch') return undefined;
                target[prop] = createRecursiveProxy(function() {});
                return target[prop];
            },
            apply: (target, thisArg, args) => {
                return createRecursiveProxy(function() {});
            }
        });
    }

    const mockChrome = createRecursiveProxy({
        storage: mockStorage
    });

    const mockCrypto = includeRandomUUID
        ? crypto
        : {
            // Simulate older browser without randomUUID
            randomUUID: undefined
        };

    const timers = [];
    const safeSetTimeout = (fn, ms, ...args) => {
        const id = setTimeout(fn, ms, ...args);
        timers.push({ type: 'timeout', id });
        return id;
    };
    const safeSetInterval = (fn, ms, ...args) => {
        // Intercept long intervals to prevent process hang
        const id = setInterval(fn, Math.max(ms, 60000), ...args);
        timers.push({ type: 'interval', id });
        return id;
    };

    const sandbox = {
        chrome: mockChrome,
        console: {
            log: () => {},
            warn: () => {},
            error: () => {},
            info: () => {}
        },
        crypto: mockCrypto,
        setTimeout: safeSetTimeout,
        clearTimeout: clearTimeout,
        setInterval: safeSetInterval,
        clearInterval: clearInterval,
        fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
        importScripts: () => {},
        _triggerStorageChange: triggerStorageChange,
        _cleanupTimers: () => {
            timers.forEach(t => {
                if (t.type === 'timeout') clearTimeout(t.id);
                if (t.type === 'interval') clearInterval(t.id);
            });
        }
    };

    vm.createContext(sandbox);
    return sandbox;
}

// ======================================================================
// TEST GROUP 1: TICK 0 IMMEDIATE COLD-START INVOCATION
// ======================================================================
console.log("[>] Test Group 1: Tick 0 Immediate Cold-Start Invocation");

{
    // Storage has artificial 500ms delay to simulate disk LevelDB I/O
    const sandbox = createExtensionSandbox({
        storageData: { instanceId: "worker-stored-persisted-123", syncToken: "tok_stored_abc" },
        storageDelayMs: 500
    });

    // Execute background.js synchronously
    vm.runInContext(bgCode, sandbox);

    // INVOCATION AT TICK 0 (Synchronous immediately after evaluation)
    const tick0Headers = sandbox._getSyncHeaders();
    console.log("    Tick 0 Headers:", tick0Headers);

    assert(tick0Headers !== null && typeof tick0Headers === 'object', "Tick 0 _getSyncHeaders() returns an object");
    assert("X-Worker-Id" in tick0Headers, "X-Worker-Id is present in Tick 0 headers");
    assert(typeof tick0Headers["X-Worker-Id"] === "string", "X-Worker-Id is a string");
    assert(tick0Headers["X-Worker-Id"].length > 0, "X-Worker-Id is non-empty");
    assert(tick0Headers["X-Worker-Id"].startsWith("node-boot-"), "X-Worker-Id uses _ephemeralBootId format ('node-boot-')");

    // Check repeatability: calling multiple times on Tick 0 returns the exact same ID
    const tick0HeadersAgain = sandbox._getSyncHeaders();
    assert(tick0HeadersAgain["X-Worker-Id"] === tick0Headers["X-Worker-Id"], "Multiple Tick 0 calls return deterministic ephemeral boot ID");

    sandbox._cleanupTimers();
}

// ======================================================================
// TEST GROUP 2: LIFECYCLE TRANSITION FROM TICK 0 TO RESOLVED INSTANCE ID
// ======================================================================
console.log("\n[>] Test Group 2: Lifecycle Transition After Storage Resolution");

async function testStorageResolutionLifecycle() {
    const sandbox = createExtensionSandbox({
        storageData: {
            instanceId: "worker-real-node-prod-789",
            syncToken: "prod_token_xyz_456",
            projectKey: "tenant_alpha"
        },
        storageDelayMs: 15
    });

    vm.runInContext(bgCode, sandbox);

    // Tick 0 check: before storage resolves
    const tick0Headers = sandbox._getSyncHeaders();
    assert(tick0Headers["X-Worker-Id"].startsWith("node-boot-"), "Tick 0 uses ephemeral boot id before storage resolves");

    // Wait for storage init to complete
    await new Promise(r => setTimeout(r, 60));

    // Post-resolution check: after storage resolves
    const resolvedHeaders = sandbox._getSyncHeaders();
    console.log("    Resolved Headers:", resolvedHeaders);

    assert(resolvedHeaders["X-Worker-Id"] === "worker-real-node-prod-789", "Post-resolution X-Worker-Id resolves to stored instanceId");
    assert(resolvedHeaders["X-Sync-Token"] === "prod_token_xyz_456", "Post-resolution X-Sync-Token is populated");
    assert(resolvedHeaders["Authorization"] === "Bearer prod_token_xyz_456", "Post-resolution Authorization is 'Bearer <token>'");
    assert(resolvedHeaders["X-Project-Key"] === "tenant_alpha", "Post-resolution X-Project-Key is populated");

    sandbox._cleanupTimers();
}

// ======================================================================
// TEST GROUP 3: DEFENSIVE RESILIENCE AGAINST CORRUPTED / EMPTY STORAGE
// ======================================================================
console.log("\n[>] Test Group 3: Defensive Fallback on Empty or Invalid Stored instanceId");

async function testDefensiveStorageCases() {
    const testCases = [
        { label: "Empty string instanceId", data: { instanceId: "" } },
        { label: "Whitespace only instanceId", data: { instanceId: "   " } },
        { label: "Null instanceId", data: { instanceId: null } },
        { label: "Undefined instanceId", data: { instanceId: undefined } },
        { label: "Numeric instanceId", data: { instanceId: 98765 } },
        { label: "Object instanceId", data: { instanceId: { id: "nested" } } },
        { label: "Completely missing key in storage", data: {} }
    ];

    for (const tc of testCases) {
        const sandbox = createExtensionSandbox({
            storageData: tc.data,
            storageDelayMs: 20
        });

        vm.runInContext(bgCode, sandbox);

        // Phase 1: Verify Tick 0 behavior before storage resolves
        const tick0Headers = sandbox._getSyncHeaders();
        const tick0WorkerId = tick0Headers["X-Worker-Id"];
        assert(
            typeof tick0WorkerId === 'string' && tick0WorkerId.length > 0 && tick0WorkerId.startsWith("node-boot-"),
            `Tick 0 ephemeral boot ID present for ${tc.label}`,
            `Expected non-empty node-boot-* string, got: ${JSON.stringify(tick0WorkerId)}`
        );

        // Phase 2: Wait for storage resolution and eager getInstanceId() completion
        await new Promise(r => setTimeout(r, 50));

        const postHeaders = sandbox._getSyncHeaders();
        const postWorkerId = postHeaders["X-Worker-Id"];

        assert(
            typeof postWorkerId === 'string' && postWorkerId.length > 0,
            `Post-resolution persistent worker ID present and non-empty for ${tc.label}`,
            `Expected non-empty string, got: ${JSON.stringify(postWorkerId)}`
        );

        sandbox._cleanupTimers();
    }
}

// ======================================================================
// TEST GROUP 4: MULTI-BOOT COLLISION RESISTANCE & ENTROPY
// ======================================================================
console.log("\n[>] Test Group 4: Multi-Boot Collision Resistance (1,000 Cold Boots)");

{
    const ITERATIONS = 1000;
    const generatedBootIds = new Set();

    for (let i = 0; i < ITERATIONS; i++) {
        const sandbox = createExtensionSandbox({ storageDelayMs: 500 });
        vm.runInContext(bgCode, sandbox);
        const headers = sandbox._getSyncHeaders();
        const bootId = headers["X-Worker-Id"];

        if (bootId && typeof bootId === 'string') {
            generatedBootIds.add(bootId);
        }
        sandbox._cleanupTimers();
    }

    assert(
        generatedBootIds.size === ITERATIONS,
        `1,000 independent cold boots generated ${generatedBootIds.size} unique IDs (0 collisions)`
    );
}

// ======================================================================
// TEST GROUP 5: ENTROPY FALLBACK WHEN crypto.randomUUID IS UNAVAILABLE
// ======================================================================
console.log("\n[>] Test Group 5: Fallback When crypto.randomUUID is Unavailable");

{
    const sandbox = createExtensionSandbox({
        includeRandomUUID: false, // Forces fallback to Date.now() + Math.random()
        storageDelayMs: 500
    });

    vm.runInContext(bgCode, sandbox);
    const headers = sandbox._getSyncHeaders();
    const fallbackId = headers["X-Worker-Id"];

    console.log("    crypto.randomUUID fallback ID:", fallbackId);
    assert(
        typeof fallbackId === 'string' && fallbackId.length > 0 && fallbackId.startsWith("node-boot-"),
        "Fallback worker ID generated cleanly without crypto.randomUUID"
    );

    sandbox._cleanupTimers();
}

// ======================================================================
// TEST GROUP 6: EXTRA HEADERS PRESERVATION & IMMUTABILITY
// ======================================================================
console.log("\n[>] Test Group 6: Extra Headers Merging & Immutability");

{
    const sandbox = createExtensionSandbox({ storageDelayMs: 500 });
    vm.runInContext(bgCode, sandbox);

    const extra = {
        "Content-Type": "application/json",
        "X-Correlation-Id": "corr-uuid-9999",
        "Accept": "application/json"
    };

    const headers = sandbox._getSyncHeaders(extra);

    assert(headers["Content-Type"] === "application/json", "Extra header Content-Type preserved");
    assert(headers["X-Correlation-Id"] === "corr-uuid-9999", "Extra header X-Correlation-Id preserved");
    assert(headers["Accept"] === "application/json", "Extra header Accept preserved");
    assert(headers["X-Worker-Id"].startsWith("node-boot-"), "X-Worker-Id present alongside extra headers");

    // Immutability: original extra object was not mutated
    assert(!("X-Worker-Id" in extra), "Original extra argument was not mutated");

    sandbox._cleanupTimers();
}

// ======================================================================
// TEST GROUP 7: DYNAMIC STORAGE CHANGE EVENTS (chrome.storage.onChanged)
// ======================================================================
console.log("\n[>] Test Group 7: Dynamic Storage Change Event Handling");

{
    const sandbox = createExtensionSandbox({ storageDelayMs: 500 });
    vm.runInContext(bgCode, sandbox);

    // Initial state: default projectKey, empty syncToken
    let h1 = sandbox._getSyncHeaders();
    assert(h1["X-Project-Key"] === "taikhoan1", "Initial projectKey is 'taikhoan1'");
    assert(!("X-Sync-Token" in h1), "Initial X-Sync-Token is absent");
    assert(!("Authorization" in h1), "Initial Authorization is absent");

    // Fire storage update event with new token and projectKey
    sandbox._triggerStorageChange({
        syncToken: { newValue: "updated_token_998877" },
        projectKey: { newValue: "tenant_beta" }
    });

    let h2 = sandbox._getSyncHeaders();
    assert(h2["X-Sync-Token"] === "updated_token_998877", "X-Sync-Token updated after onChanged event");
    assert(h2["Authorization"] === "Bearer updated_token_998877", "Authorization updated after onChanged event");
    assert(h2["X-Project-Key"] === "tenant_beta", "X-Project-Key updated after onChanged event");

    // Clear token
    sandbox._triggerStorageChange({
        syncToken: { newValue: "" }
    });

    let h3 = sandbox._getSyncHeaders();
    assert(!("X-Sync-Token" in h3), "X-Sync-Token cleanly omitted when cleared to empty");
    assert(!("Authorization" in h3), "Authorization cleanly omitted when cleared to empty");

    sandbox._cleanupTimers();
}

// ======================================================================
// RUN ASYNC TEST RUNNER & PRODUCE FINAL SUMMARY
// ======================================================================
async function runAll() {
    await testStorageResolutionLifecycle();
    await testDefensiveStorageCases();

    console.log("\n======================================================================");
    console.log(`[*] COLD-START SUMMARY: Total Tests: ${totalTests} | Passed: ${passedTests} | Failed: ${failedTests}`);
    console.log("======================================================================\n");

    if (failedTests > 0) {
        console.error(`❌ ${failedTests} test(s) failed in cold-start harness!`);
        process.exit(1);
    } else {
        console.log("🎉 ALL COLD-START & HEADER RESILIENCE TESTS PASSED EMPIRICALLY!");
        process.exit(0);
    }
}

runAll().catch(err => {
    console.error("FATAL HARNESS ERROR:", err);
    process.exit(1);
});
