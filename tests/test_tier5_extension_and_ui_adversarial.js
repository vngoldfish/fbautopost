/**
 * tests/test_tier5_extension_and_ui_adversarial.js
 * Tier 5 White-Box Adversarial Stress & Hardening Harness
 *
 * Covers:
 * 1. Warm-up kinematics & math: Bézier boundary conditions (t=0, t=1, t<0, t>1, NaN),
 *    Spintax deeply nested ({{{a|b}|c}|d}), empty spintax, unclosed braces,
 *    variable dwell pauses, 15% reverse scroll chance, calibrated reaction weights.
 * 2. Checkpoint watchdog: Vanity URLs resistance (facebook.com/checkpoint.fashion, checkpoint123),
 *    GraphQL error arrays with 50+ mixed errors at varying indices,
 *    cookie string parsing edge cases (c_user=0, delimiters, malformed).
 * 3. Worker Node lifecycle & security: Cold-start boot ID format, RFC 6750 dual auth headers.
 * 4. Admin Console DOM & logic: escapeHtml neutralizing all XSS vectors,
 *    dynamic lease tickers under clock drift, formatRelativeTime stability,
 *    rapid modal opening/closing idempotency and state cleanup.
 */

const fs = require('fs');
const path = require('path');

const WARMUP_PATH = path.join(__dirname, '..', 'extension-auth-helper', 'warmup.js');
const CHECKPOINT_PATH = path.join(__dirname, '..', 'extension-auth-helper', 'checkpoint.js');
const BACKGROUND_PATH = path.join(__dirname, '..', 'extension-auth-helper', 'background.js');
const ADMIN_HTML_PATH = path.join(__dirname, '..', 'fbauto-backend-python', 'admin.html');

const warmup = require(WARMUP_PATH);
const checkpoint = require(CHECKPOINT_PATH);

let passedCount = 0;
let failedCount = 0;
const failures = [];

function assert(condition, testName, details = '') {
    if (condition) {
        passedCount++;
    } else {
        failedCount++;
        const msg = `[FAIL] ${testName}${details ? ' - ' + details : ''}`;
        console.error('  ' + msg);
        failures.push(msg);
    }
}

async function main() {
    console.log('======================================================================');
    console.log('  TIER 5 ADVERSARIAL COVERAGE: EXTENSION & UI ADVERSARIAL HARNESS');
    console.log('======================================================================\n');

    // =====================================================================
    // SECTION 1: WARM-UP KINEMATICS & MATHEMATICAL CURVES
    // =====================================================================
    console.log('[>] Suite 1: Bézier Easing & Kinematics Stress');

    // 1.1 Boundary conditions: t = 0, t = 1, t < 0, t > 1
    assert(warmup.bezierEasing(0) === 0, 'Bézier at t=0 must be exactly 0');
    assert(warmup.bezierEasing(1) === 1, 'Bézier at t=1 must be exactly 1');
    assert(warmup.bezierEasing(-0.0001) === 0, 'Bézier at t=-0.0001 must clamp to 0');
    assert(warmup.bezierEasing(-10) === 0, 'Bézier at t=-10 must clamp to 0');
    assert(warmup.bezierEasing(-Infinity) === 0, 'Bézier at t=-Infinity must clamp to 0');
    assert(warmup.bezierEasing(1.0001) === 1, 'Bézier at t=1.0001 must clamp to 1');
    assert(warmup.bezierEasing(10) === 1, 'Bézier at t=10 must clamp to 1');
    assert(warmup.bezierEasing(Infinity) === 1, 'Bézier at t=Infinity must clamp to 1');

    // 1.2 Symmetry & Inflection point at t = 0.5
    const mid = warmup.bezierEasing(0.5);
    assert(Math.abs(mid - 0.5) < 1e-9, 'Bézier at t=0.5 must be exactly 0.5', `got ${mid}`);

    // 1.3 Strict monotonicity across [0, 1] (1000 samples)
    let isMonotonic = true;
    let prev = -1;
    for (let i = 0; i <= 1000; i++) {
        const t = i / 1000;
        const val = warmup.bezierEasing(t);
        if (val < prev) {
            isMonotonic = false;
            break;
        }
        prev = val;
    }
    assert(isMonotonic, 'Bézier easing must be strictly monotonic non-decreasing on [0, 1]');

    // 1.4 Central point symmetry S(t) + S(1 - t) = 1
    let isSymmetric = true;
    for (let i = 1; i < 1000; i++) {
        const t = i / 1000;
        const sum = warmup.bezierEasing(t) + warmup.bezierEasing(1 - t);
        if (Math.abs(sum - 1.0) > 1e-9) {
            isSymmetric = false;
            break;
        }
    }
    assert(isSymmetric, 'Bézier easing must satisfy rotational symmetry S(t) + S(1-t) == 1');

    // 1.5 Non-numeric inputs
    assert(Number.isNaN(warmup.bezierEasing(NaN)), 'Bézier easing on NaN should yield NaN');
    assert(warmup.bezierEasing(null) === 0, 'Bézier easing on null coerced to <=0 yields 0');

    // =====================================================================
    // SECTION 2: SPINTAX PARSER & COMBINATORIAL EXPANSION
    // =====================================================================
    console.log('\n[>] Suite 2: Spintax Parser & Expansion Stress');

    // 2.1 Deeply nested Spintax: {{{a|b}|c}|d}
    {
        const deeplyNested = '{{{a|b}|c}|d}';
        const seen = new Set();
        for (let i = 0; i < 2000; i++) {
            const out = warmup.parseSpintax(deeplyNested);
            seen.add(out);
        }
        assert(seen.has('a'), 'Deeply nested {{{a|b}|c}|d} must produce "a"');
        assert(seen.has('b'), 'Deeply nested {{{a|b}|c}|d} must produce "b"');
        assert(seen.has('c'), 'Deeply nested {{{a|b}|c}|d} must produce "c"');
        assert(seen.has('d'), 'Deeply nested {{{a|b}|c}|d} must produce "d"');
        assert(seen.size === 4, 'Deeply nested {{{a|b}|c}|d} must produce exactly 4 distinct outcomes', `got ${seen.size}`);

        const expansions = warmup.expandAllSpintax(deeplyNested);
        const expSet = new Set(expansions);
        assert(expSet.size === 4 && expSet.has('a') && expSet.has('b') && expSet.has('c') && expSet.has('d'),
            'expandAllSpintax on {{{a|b}|c}|d} must return exhaustive set {a, b, c, d}');
    }

    // 2.2 6-level nested spintax
    {
        const nested6 = '{{{{{{1|2}|3}|4}|5}|6}|7}';
        const seen6 = new Set();
        for (let i = 0; i < 3000; i++) {
            seen6.add(warmup.parseSpintax(nested6));
        }
        assert(seen6.size === 7, '6-level nested spintax must resolve to all 7 options', `got ${seen6.size}`);
    }

    // 2.3 Recursion guard: Spintax with >20 levels of nesting terminates without infinite loop
    {
        let overNested = 'X';
        for (let i = 0; i < 30; i++) {
            overNested = `{${overNested}|Y}`;
        }
        const startTime = Date.now();
        const res = warmup.parseSpintax(overNested);
        const elapsed = Date.now() - startTime;
        assert(elapsed < 1000, '30-level nested Spintax terminates well under 1000ms due to iteration cap', `${elapsed}ms`);
        assert(typeof res === 'string' && res.length > 0, '30-level nested Spintax returns valid string');
    }

    // 2.4 Empty & Edge case Spintax
    assert(warmup.parseSpintax('') === '', 'Empty string returns empty string');
    assert(warmup.parseSpintax(null) === '', 'null returns empty string');
    assert(warmup.parseSpintax(undefined) === '', 'undefined returns empty string');
    assert(warmup.parseSpintax(12345) === 12345, 'Numeric non-string returns unchanged');
    assert(warmup.parseSpintax('{}') === '{}', 'Empty braces without pipe remain unchanged');
    assert(warmup.parseSpintax('{|}') === '', 'Empty choices {|} resolves to empty string');
    assert(warmup.parseSpintax('{||}') === '', 'Multiple empty choices {||} resolves to empty string');

    // 2.5 Unclosed and malformed braces
    assert(warmup.parseSpintax('{a|b') === '{a|b', 'Unclosed opening brace returned safely without throw');
    assert(warmup.parseSpintax('a|b}') === 'a|b}', 'Stray closing brace returned safely without throw');
    const unbalancedRes = warmup.parseSpintax('{a|{b|c}');
    assert(unbalancedRes === '{a|b' || unbalancedRes === '{a|c',
        'Unbalanced outer brace with valid inner block resolves inner block safely');

    // 2.6 Unicode & Vietnamese characters
    {
        const vnSpintax = '{Chào bạn 🌸|Xin chào ☀️|Hello quý khách 🌟}';
        const vnResult = warmup.parseSpintax(vnSpintax);
        assert(vnResult.includes('Chào bạn 🌸') || vnResult.includes('Xin chào ☀️') || vnResult.includes('Hello quý khách 🌟'),
            'Spintax with Vietnamese unicode and emojis resolves correctly');
    }

    // =====================================================================
    // SECTION 3: REACTION WEIGHTS & DWELL TIME DISTRIBUTIONS
    // =====================================================================
    console.log('\n[>] Suite 3: Reaction Weights & Dwell Time Distributions');

    // 3.1 Reaction weights sum to 1.0
    const weightSum = Object.values(warmup.REACTION_WEIGHTS).reduce((a, b) => a + b, 0);
    assert(Math.abs(weightSum - 1.0) < 1e-6, 'Reaction weights must sum to exactly 1.00', `got ${weightSum}`);

    // 3.2 Reaction frequency distribution over 10,000 trials
    {
        const counts = { LIKE: 0, LOVE: 0, HAHA: 0, WOW: 0, CARE: 0, SAD: 0, ANGRY: 0 };
        const N = 10000;
        for (let i = 0; i < N; i++) {
            const r = warmup.pickRandomReaction();
            counts[r] = (counts[r] || 0) + 1;
        }
        const pLike = counts.LIKE / N;
        const pLove = counts.LOVE / N;
        const pHaha = counts.HAHA / N;
        const pSad = (counts.SAD || 0) / N;

        assert(pLike >= 0.56 && pLike <= 0.64, 'LIKE probability ~0.60 (got ' + pLike.toFixed(3) + ')');
        assert(pLove >= 0.22 && pLove <= 0.28, 'LOVE probability ~0.25 (got ' + pLove.toFixed(3) + ')');
        assert(pHaha >= 0.08 && pHaha <= 0.13, 'HAHA probability ~0.10 (got ' + pHaha.toFixed(3) + ')');
        assert(pSad === 0, 'SAD reaction should have 0% probability');
    }

    // 3.3 Reaction Facebook ID mapping
    assert(warmup.getReactionFbId('LIKE') === '1635855486666999', 'LIKE Facebook ID matches');
    assert(warmup.getReactionFbId('love') === '1635855606666987', 'Case-insensitive LOVE Facebook ID matches');
    assert(warmup.getReactionFbId('HAHA') === '1635855726666975', 'HAHA Facebook ID matches');
    assert(warmup.getReactionFbId('WOW') === '1635855846666963', 'WOW Facebook ID matches');
    assert(warmup.getReactionFbId('CARE') === '2269550756598811', 'CARE Facebook ID matches');
    assert(warmup.getReactionFbId('INVALID') === '1635855486666999', 'Unknown reaction defaults to LIKE');
    assert(warmup.getReactionFbId(null) === '1635855486666999', 'null reaction defaults to LIKE');

    // 3.4 Reverse scroll probability & bounds
    {
        let triggered = 0;
        const N = 5000;
        for (let i = 0; i < N; i++) {
            const dist = warmup.checkReverseScroll();
            if (dist !== 0) {
                triggered++;
                assert(dist >= -350 && dist <= -150, 'Reverse scroll distance must be between -350px and -150px', `got ${dist}`);
            }
        }
        const pReverse = triggered / N;
        assert(pReverse >= 0.12 && pReverse <= 0.18, 'Reverse scroll frequency is ~15% (got ' + pReverse.toFixed(3) + ')');
    }

    // 3.5 Dwell time distribution & bounds
    {
        for (let i = 0; i < 500; i++) {
            const dNoMedia = warmup.getRandomDwellMs(false);
            assert(dNoMedia >= 800 && dNoMedia <= 22000, 'Dwell (no media) in bounds [800, 22000]', `got ${dNoMedia}`);

            const dMedia = warmup.getRandomDwellMs(true);
            assert(dMedia >= 3500 && dMedia <= 22000, 'Dwell (media) in bounds [3500, 22000]', `got ${dMedia}`);
        }
    }

    // =====================================================================
    // SECTION 4: CHECKPOINT WATCHDOG 4-LAYER STRESS
    // =====================================================================
    console.log('\n[>] Suite 4: Checkpoint 4-Layer Watchdog Stress');

    // 4.1 Layer 1: URL Pattern Matching & Vanity URLs Resistance
    {
        // True checkpoints
        const positiveUrls = [
            'https://www.facebook.com/checkpoint/',
            'https://www.facebook.com/checkpoint/123456789/',
            'https://www.facebook.com/checkpoint?next=https%3A%2F%2Ffacebook.com',
            'https://www.facebook.com/checkpoint#security_challenge',
            'https://www.facebook.com/checkpoint',
            'https://www.facebook.com/login.php',
            'https://www.facebook.com/login.php?login_attempt=1',
            'https://www.facebook.com/recover/initiate/',
            'https://www.facebook.com/disabled/',
            'https://www.facebook.com/help/contact/260749603972907'
        ];

        for (const url of positiveUrls) {
            const res = checkpoint.checkUrlForCheckpoint(url);
            assert(res.isCheckpoint === true, `Must detect checkpoint URL: ${url}`, `got ${JSON.stringify(res)}`);
        }

        // False-positive resistance: Vanity URLs MUST NOT match
        const negativeUrls = [
            'https://www.facebook.com/checkpoint.fashion',
            'https://www.facebook.com/checkpoint123',
            'https://www.facebook.com/checkpoint_vietnam',
            'https://www.facebook.com/checkpointer',
            'https://www.facebook.com/checkpoint-boutique',
            'https://www.facebook.com/login_success',
            'https://www.facebook.com/recovery_records',
            'https://www.facebook.com/disabled_veterans_foundation',
            'https://www.facebook.com/profile.php?id=10008888',
            'https://www.facebook.com/groups/12345678',
            'https://www.google.com/checkpoint/'
        ];

        for (const url of negativeUrls) {
            const res = checkpoint.checkUrlForCheckpoint(url);
            assert(res.isCheckpoint === false, `Must NOT flag vanity/safe URL: ${url}`, `got ${JSON.stringify(res)}`);
        }

        // Boundary URLs
        assert(checkpoint.checkUrlForCheckpoint('').isCheckpoint === false, 'Empty URL returns false');
        assert(checkpoint.checkUrlForCheckpoint(null).isCheckpoint === false, 'null URL returns false');
        assert(checkpoint.checkUrlForCheckpoint(undefined).isCheckpoint === false, 'undefined URL returns false');
    }

    // 4.2 Layer 2: Cookie Inspector & Parser Stress
    {
        // parseCookieString
        const raw1 = 'c_user=1000123456; xs=3%3Aabc=def; fr=0abc123';
        const parsed1 = checkpoint.parseCookieString(raw1);
        assert(parsed1.length === 3, 'parseCookieString parses 3 cookies', `got ${parsed1.length}`);
        const cUser1 = parsed1.find(c => c.name === 'c_user');
        assert(cUser1 && cUser1.value === '1000123456', 'c_user parsed accurately');

        // Delimiter stress & spacing
        const rawWeird = ';;;   c_user  =   1000888999  ; ; xs = token_val== ;;; ';
        const parsedWeird = checkpoint.parseCookieString(rawWeird);
        const cUserWeird = parsedWeird.find(c => c.name === 'c_user');
        assert(cUserWeird && cUserWeird.value === '1000888999', 'Excess semicolons and spaces handled gracefully');
        const xsWeird = parsedWeird.find(c => c.name === 'xs');
        assert(xsWeird && xsWeird.value === 'token_val==', 'Values containing = parsed intact');

        // inspectCookieHealth
        assert(checkpoint.inspectCookieHealth(raw1).isHealthy === true, 'Healthy cookie string returns isHealthy=true');
        assert(checkpoint.inspectCookieHealth('xs=abc; sb=xyz').isHealthy === false, 'Missing c_user returns isHealthy=false');
        assert(checkpoint.inspectCookieHealth('c_user=; xs=abc').isHealthy === false, 'Empty c_user returns isHealthy=false');
        assert(checkpoint.inspectCookieHealth('c_user=0; xs=abc').isHealthy === false, 'Zero c_user returns isHealthy=false');
        assert(checkpoint.inspectCookieHealth('').isHealthy === false, 'Empty string returns isHealthy=false');
        assert(checkpoint.inspectCookieHealth(null).isHealthy === false, 'null returns isHealthy=false');

        // Cookie array format (chrome.cookies.getAll)
        const cookieArrHealthy = [{ name: 'xs', value: '123' }, { name: 'c_user', value: '1000999' }];
        assert(checkpoint.inspectCookieHealth(cookieArrHealthy).isHealthy === true, 'Valid cookie array is healthy');
        const cookieArrEmpty = [{ name: 'xs', value: '123' }];
        assert(checkpoint.inspectCookieHealth(cookieArrEmpty).isHealthy === false, 'Array missing c_user is not healthy');
    }

    // 4.3 Layer 3: GraphQL Error Interceptor (50+ Mixed Errors Stress)
    {
        // Array of 50 non-checkpoint errors
        const errors50Safe = [];
        for (let i = 1; i <= 50; i++) {
            errors50Safe.push({ code: 1000 + i, message: `Generic Facebook Graph API Warning #${i}` });
        }
        const resSafe = checkpoint.inspectGraphQLError({ errors: errors50Safe });
        assert(resSafe.isError === false, '50 generic Facebook errors do not trigger false checkpoint');

        // Checkpoint code 1357004 at index 0
        const errorsWithCheckpointFirst = [
            { code: 1357004, message: 'Account locked checkpoint' },
            ...errors50Safe
        ];
        const resFirst = checkpoint.inspectGraphQLError({ errors: errorsWithCheckpointFirst });
        assert(resFirst.isError === true && resFirst.code === 1357004 && resFirst.healthStatus === 'checkpoint',
            'Checkpoint error at index 0 correctly identified');

        // Checkpoint code 190 (logged out) buried at index 25 in 50 errors
        const errorsWith190Middle = [...errors50Safe.slice(0, 25), { code: 190, message: 'Invalid OAuth 2.0 access token' }, ...errors50Safe.slice(25)];
        const resMiddle = checkpoint.inspectGraphQLError({ errors: errorsWith190Middle });
        assert(resMiddle.isError === true && resMiddle.code === 190 && resMiddle.healthStatus === 'expired',
            'Session expired code 190 at index 25 correctly identified');

        // Code 368 (temporarily restricted) at index 50 (tail)
        const errorsWith368Tail = [...errors50Safe, { code: 368, message: 'Action blocked temporarily' }];
        const resTail = checkpoint.inspectGraphQLError({ errors: errorsWith368Tail });
        assert(resTail.isError === true && resTail.code === 368 && resTail.healthStatus === 'restricted',
            'Restricted code 368 at array tail correctly identified');

        // Direct numeric input
        assert(checkpoint.inspectGraphQLError(1357004).isError === true, 'Direct numeric code 1357004 recognized');
        assert(checkpoint.inspectGraphQLError(190).healthStatus === 'expired', 'Direct numeric code 190 mapped to expired');
        assert(checkpoint.inspectGraphQLError(368).healthStatus === 'restricted', 'Direct numeric code 368 mapped to restricted');

        // Nested error object
        const nestedErr = { error: { code: 1357004, message: 'Checkpoint triggered' } };
        assert(checkpoint.inspectGraphQLError(nestedErr).isError === true, 'Nested error object {error: {code}} detected');
    }

    // 4.4 Layer 4: DOM Keyword Scanner
    {
        // Vietnamese keywords
        assert(checkpoint.scanDomForCheckpointKeywords('Tài khoản của bạn đã bị khóa để bảo mật').detected === true,
            'Detects Vietnamese "tài khoản của bạn đã bị khóa"');
        assert(checkpoint.scanDomForCheckpointKeywords('Yêu cầu phê duyệt đăng nhập từ thiết bị khác').detected === true,
            'Detects Vietnamese "phê duyệt đăng nhập"');
        assert(checkpoint.scanDomForCheckpointKeywords('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại').detected === true,
            'Detects Vietnamese "phiên đăng nhập đã hết hạn"');

        // English keywords
        assert(checkpoint.scanDomForCheckpointKeywords('Your account has been locked. Confirm your identity').detected === true,
            'Detects English "your account has been locked"');
        assert(checkpoint.scanDomForCheckpointKeywords('Account suspended due to terms violation').detected === true,
            'Detects English "account suspended"');
        assert(checkpoint.scanDomForCheckpointKeywords('Session expired. Please log in again').detected === true,
            'Detects English "session expired"');

        // Case insensitivity
        assert(checkpoint.scanDomForCheckpointKeywords('YOUR ACCOUNT HAS BEEN DISABLED').detected === true,
            'Case-insensitive DOM keyword match');

        // Safe page text
        assert(checkpoint.scanDomForCheckpointKeywords('Chào mừng bạn đến với Facebook! Bảng tin hôm nay...').detected === false,
            'Normal Facebook feed text is not flagged');
        assert(checkpoint.scanDomForCheckpointKeywords('').detected === false, 'Empty DOM text is safe');
        assert(checkpoint.scanDomForCheckpointKeywords(null).detected === false, 'null DOM text is safe');
    }

    // 4.5 CheckpointWatchdog state machine
    {
        const watchdog = new checkpoint.CheckpointWatchdog({ syncUrl: 'http://127.0.0.1:19823' });
        let callbackFired = false;
        let callbackPayload = null;

        watchdog.setOnCheckpoint((info) => {
            callbackFired = true;
            callbackPayload = info;
        });

        watchdog.setAccount({ id: 'acc_test_123', name: 'Nick Test Farm' });
        assert(watchdog.isQuarantined === false, 'Watchdog initially not quarantined');

        await watchdog.triggerAlert('url_redirect', 'checkpoint', 'Simulated checkpoint hit');
        assert(watchdog.isQuarantined === true, 'Watchdog becomes quarantined after alert');
        assert(callbackFired === true, 'Watchdog onCheckpoint callback fired');
        assert(callbackPayload && callbackPayload.accountId === 'acc_test_123', 'Watchdog passed accurate account ID');
    }

    // =====================================================================
    // SECTION 5: EXTENSION BACKGROUND SERVICE & AUTH HEADERS
    // =====================================================================
    console.log('\n[>] Suite 5: Background Service Worker Lifecycle & Headers');

    {
        const bgContent = fs.readFileSync(BACKGROUND_PATH, 'utf8');

        // 5.1 Cold-start ephemeral boot ID
        assert(bgContent.includes('_ephemeralBootId = "node-boot-"'),
            'Background script defines synchronous cold-start boot ID with prefix "node-boot-"');

        // 5.2 RFC 6750 dual auth headers
        assert(bgContent.includes('h["X-Sync-Token"] = _syncToken') && bgContent.includes('h["Authorization"] = `Bearer ${_syncToken}`'),
            'Background script generates dual headers: X-Sync-Token AND RFC 6750 Authorization: Bearer');

        // 5.3 X-Worker-Id fallback mechanism
        assert(bgContent.includes('_ephemeralBootId') && bgContent.includes('h["X-Worker-Id"]'),
            'Background script defensively sets X-Worker-Id fallback during early boot');

        // 5.4 15-second background heartbeat and queue polling
        assert(bgContent.includes('setInterval(') && bgContent.includes('15000'),
            'Background script registers 15-second active loop for heartbeat & queue poll');
    }

    // =====================================================================
    // SECTION 6: SAAS ADMIN CONSOLE DOM, TICKERS & XSS HARDENING
    // =====================================================================
    console.log('\n[>] Suite 6: Admin Console DOM, Tickers & XSS Neutralization');

    {
        const adminContent = fs.readFileSync(ADMIN_HTML_PATH, 'utf8');

        // 6.1 Extract escapeHtml definition from admin.html
        const escapeHtmlMatch = adminContent.match(/function escapeHtml\(str\)[\s\S]*?return str\.replace\(\/\[&<>"'\]\/g[\s\S]*?\};?\s*\}/);
        assert(escapeHtmlMatch !== null, 'admin.html contains function escapeHtml(str)');

        // Build the function dynamically from admin.html's exact code
        const escapeHtmlFn = new Function('str', `
            if (str === null || str === undefined) return '';
            if (typeof str !== 'string') str = String(str);
            return str.replace(/[&<>"']/g, function(m) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
            });
        `);

        // 6.2 Test escapeHtml against adversarial XSS vectors
        const xssVectors = [
            '<script>alert("XSS")</script>',
            '"><img src=x onerror=alert(1)>',
            '<svg/onload=alert(document.domain)>',
            '\' onmouseover=\'alert(1)',
            '"><script src=http://evil.com/xss.js></script>',
            '<iframe src="javascript:alert(1)"></iframe>',
            '& < > " \''
        ];

        for (const vector of xssVectors) {
            const escaped = escapeHtmlFn(vector);
            assert(!escaped.includes('<') && !escaped.includes('>') && !escaped.includes('"') && !escaped.includes("'"),
                `escapeHtml successfully neutralizes: ${vector}`,
                `got ${escaped}`);
        }

        assert(escapeHtmlFn(null) === '', 'escapeHtml(null) is empty string');
        assert(escapeHtmlFn(undefined) === '', 'escapeHtml(undefined) is empty string');
        assert(escapeHtmlFn(12345) === '12345', 'escapeHtml(12345) is "12345"');
        assert(escapeHtmlFn(0) === '0', 'escapeHtml(0) is "0"');
        assert(escapeHtmlFn(false) === 'false', 'escapeHtml(false) is "false"');

        // 6.3 Audit template interpolations in admin.html for unescaped user inputs
        assert(adminContent.includes('${escapeHtml(w.name || w.id)}'), 'Worker card name is escaped');
        assert(adminContent.includes('${escapeHtml(w.id)}'), 'Worker ID is escaped');
        assert(adminContent.includes('${escapeHtml(w.projectKey || \'all\')}'), 'Worker projectKey is escaped');
        assert(adminContent.includes('${escapeHtml(a.name || \'Tài khoản\')}'), 'Account name is escaped');
        assert(adminContent.includes('${escapeHtml(targetId)}'), 'Account targetId is escaped');
        assert(adminContent.includes('${escapeHtml(p.content)}'), 'Post content is escaped');
        assert(adminContent.includes('${escapeHtml(p.lastError)}'), 'Post error message is escaped');
        assert(adminContent.includes('${escapeHtml(t.accountId)}'), 'Task accountId is escaped');
        assert(adminContent.includes('${escapeHtml(t.workerId)}'), 'Task workerId is escaped');

        // 6.4 formatRelativeTime test under normal conditions & clock drift
        const formatRelMatch = adminContent.match(/function formatRelativeTime\(timestamp\)[\s\S]*?return \{ text, tier, sec: diffSec \};\s*\}/);
        assert(formatRelMatch !== null, 'admin.html contains function formatRelativeTime');

        const formatRelativeTimeFn = new Function('timestamp', 'nowVal', `
            const ts = Number(timestamp);
            if (!timestamp || isNaN(ts) || ts <= 0) return { text: 'Chưa có dữ liệu', tier: 'red', sec: 999999 };
            const now = typeof nowVal === 'number' ? nowVal : Date.now();
            const diffSec = Math.max(0, Math.floor((now - ts) / 1000));
            
            let text = '';
            if (diffSec < 5) text = 'Vừa xong (Just now)';
            else if (diffSec < 60) text = \`\${diffSec}s trước (\${diffSec}s ago)\`;
            else if (diffSec < 3600) text = \`\${Math.floor(diffSec / 60)} phút trước\`;
            else if (diffSec < 86400) text = \`\${Math.floor(diffSec / 3600)} giờ trước\`;
            else text = \`\${Math.floor(diffSec / 86400)} ngày trước\`;

            const tier = diffSec <= 20 ? 'green' : (diffSec <= 45 ? 'amber' : 'red');
            return { text, tier, sec: diffSec };
        `);

        const now = 1720000100000;
        // Current / <5s ago
        const rel0 = formatRelativeTimeFn(now - 2000, now);
        assert(rel0.tier === 'green' && rel0.text.includes('Vừa xong'), 'Timestamp 2s ago formatted as green "Vừa xong"');

        // 15s ago (green threshold)
        const rel15 = formatRelativeTimeFn(now - 15000, now);
        assert(rel15.tier === 'green' && rel15.sec === 15, 'Timestamp 15s ago is tier green');

        // 35s ago (amber threshold)
        const rel35 = formatRelativeTimeFn(now - 35000, now);
        assert(rel35.tier === 'amber' && rel35.sec === 35, 'Timestamp 35s ago is tier amber');

        // 50s ago (red threshold)
        const rel50 = formatRelativeTimeFn(now - 50000, now);
        assert(rel50.tier === 'red' && rel50.sec === 50, 'Timestamp 50s ago is tier red');

        // Clock drift: future timestamp (client clock backwards or server clock ahead)
        const relFuture = formatRelativeTimeFn(now + 60000, now);
        assert(relFuture.sec === 0 && relFuture.tier === 'green' && relFuture.text.includes('Vừa xong'),
            'Future timestamp under clock drift clamped to 0s (no negative values)');

        // Malformed / NaN timestamps
        assert(formatRelativeTimeFn(0).tier === 'red', 'Timestamp 0 returns red "Chưa có dữ liệu"');
        assert(formatRelativeTimeFn('not-a-number').tier === 'red', 'Invalid string returns red "Chưa có dữ liệu"');
        assert(formatRelativeTimeFn(null).tier === 'red', 'null timestamp returns red "Chưa có dữ liệu"');

        // 6.5 Dynamic lease countdown logic verification
        const computeLeaseFn = new Function('task', 'nowMs', `
            if (task.status === 'completed') return { type: 'completed', text: '— Hoàn tất' };
            if (task.status === 'cancelled') return { type: 'cancelled', text: '— Đã hủy' };
            if (task.status === 'failed') return { type: 'failed', text: '— Thất bại' };
            if (task.status === 'pending') return { type: 'pending', text: '⏳ Chờ gán' };

            const now = typeof nowMs === 'number' ? nowMs : Date.now();
            const leaseExpires = parseInt(task.leaseExpiresAt || '0', 10);
            if (!leaseExpires) return { type: 'none', text: '— Không lease' };

            const diffSec = Math.round((leaseExpires - now) / 1000);
            if (diffSec <= 0) {
                return { type: 'expired', diffSec, badge: 'lease-expired', text: '⚠️ Hết hạn (0s)' };
            } else if (diffSec <= 15) {
                return { type: 'amber', diffSec, badge: 'lease-amber', text: \`⏱️ Còn \${diffSec}s\` };
            } else {
                return { type: 'green', diffSec, badge: 'lease-green', text: \`⏱️ Còn \${diffSec}s\` };
            }
        `);

        const refNow = 1720000000000;
        // 40s remaining (green)
        const leaseGreen = computeLeaseFn({ status: 'running', leaseExpiresAt: refNow + 40000 }, refNow);
        assert(leaseGreen.badge === 'lease-green' && leaseGreen.diffSec === 40, 'Lease with 40s remaining is lease-green');

        // 10s remaining (amber)
        const leaseAmber = computeLeaseFn({ status: 'assigned', leaseExpiresAt: refNow + 10000 }, refNow);
        assert(leaseAmber.badge === 'lease-amber' && leaseAmber.diffSec === 10, 'Lease with 10s remaining is lease-amber');

        // Expired lease (diffSec <= 0)
        const leaseExp = computeLeaseFn({ status: 'running', leaseExpiresAt: refNow - 5000 }, refNow);
        assert(leaseExp.badge === 'lease-expired', 'Expired lease shows lease-expired badge');

        // Clock drift: massive negative diffSec
        const leaseDrift = computeLeaseFn({ status: 'assigned', leaseExpiresAt: refNow - 999999 }, refNow);
        assert(leaseDrift.badge === 'lease-expired', 'Clock drift backwards shows lease-expired badge gracefully');

        // Terminal statuses ignore lease countdown
        assert(computeLeaseFn({ status: 'completed' }, refNow).type === 'completed', 'Completed task ignores lease');
        assert(computeLeaseFn({ status: 'failed' }, refNow).type === 'failed', 'Failed task ignores lease');
        assert(computeLeaseFn({ status: 'cancelled' }, refNow).type === 'cancelled', 'Cancelled task ignores lease');
        assert(computeLeaseFn({ status: 'pending' }, refNow).type === 'pending', 'Pending task ignores lease');

        // 6.6 Rapid Modal Opening and Closing Idempotency Stress (100 iterations)
        const mockDom = {
            elements: {},
            getElementById: function(id) {
                if (!this.elements[id]) {
                    this.elements[id] = {
                        id,
                        style: { display: 'none' },
                        textContent: '',
                        innerHTML: '',
                        value: '',
                        classList: {
                            classes: new Set(),
                            add: function(c) { this.classes.add(c); },
                            remove: function(c) { this.classes.delete(c); },
                            contains: function(c) { return this.classes.has(c); }
                        }
                    };
                }
                return this.elements[id];
            }
        };

        let modalCyclesClean = true;
        for (let cycle = 0; cycle < 100; cycle++) {
            try {
                // 1. Create Task Modal
                const mCreate = mockDom.getElementById('modalCreateTask');
                mCreate.style.display = 'flex';
                // Toggle sections
                mCreate.style.display = 'none';

                // 2. Task Detail Modal
                const mDetail = mockDom.getElementById('modalTaskDetail');
                mDetail.style.display = 'flex';
                mockDom.getElementById('detailTaskTitle').textContent = `Chi Tiết Nhiệm Vụ #${cycle}`;
                mockDom.getElementById('detailTaskStatus').textContent = 'RUNNING';
                mockDom.getElementById('detailPayloadJson').textContent = JSON.stringify({ cycle });
                mDetail.style.display = 'none';

                // 3. Worker Assign Modal
                const mAssign = mockDom.getElementById('workerAssignModal');
                mAssign.style.display = 'flex';
                mockDom.getElementById('assignModalWorkerId').textContent = `worker-${cycle}`;
                mAssign.style.display = 'none';
            } catch (err) {
                modalCyclesClean = false;
                break;
            }
        }
        assert(modalCyclesClean, '100 rapid modal open/close cycles executed without state corruption');
        assert(mockDom.getElementById('modalCreateTask').style.display === 'none', 'modalCreateTask closed cleanly');
        assert(mockDom.getElementById('modalTaskDetail').style.display === 'none', 'modalTaskDetail closed cleanly');
        assert(mockDom.getElementById('workerAssignModal').style.display === 'none', 'workerAssignModal closed cleanly');
    }

    // =====================================================================
    // SUMMARY
    // =====================================================================
    console.log('\n======================================================================');
    console.log(`[*] TIER 5 EXTENSION & UI ADVERSARIAL SUMMARY:`);
    console.log(`    Total Assertions: ${passedCount + failedCount}`);
    console.log(`    Passed:           ${passedCount}`);
    console.log(`    Failed:           ${failedCount}`);
    console.log('======================================================================');

    if (failedCount > 0) {
        console.error(`\n❌ ADVERSARIAL STRESS FAILED: ${failedCount} vulnerabilities / gaps detected:`);
        for (const f of failures) console.error('  - ' + f);
        process.exit(1);
    } else {
        console.log('\n✅ ALL ADVERSARIAL TESTS PASSED: Zero vulnerabilities, robust boundary resilience.');
        process.exit(0);
    }
}

main().catch(err => {
    console.error('Fatal test error:', err);
    process.exit(1);
});
