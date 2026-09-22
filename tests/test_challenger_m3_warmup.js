/**
 * Empirical Stress Test Harness for Milestone 3 (Warm-up & Spintax Suite)
 * tests/test_challenger_m3_warmup.js
 *
 * Challenger: challenger_m3_1
 */

const {
    REACTION_WEIGHTS,
    REACTION_FB_IDS,
    SCROLL_PHYSICS,
    bezierEasing,
    parseSpintax,
    expandAllSpintax,
    pickRandomReaction,
    getReactionFbId,
    getRandomDwellMs,
    getRandomStepDistance,
    checkReverseScroll,
    executeTabScroll,
    sendReactionGraphQL,
    sendCommentGraphQL,
    runWarmupSession
} = require('../extension-auth-helper/warmup.js');

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
const failureDetails = [];

function assert(condition, description, extra = '') {
    totalTests++;
    if (condition) {
        passedTests++;
        console.log(`  [PASS] ${description}`);
    } else {
        failedTests++;
        console.error(`  [FAIL] ${description} ${extra ? `(${extra})` : ''}`);
        failureDetails.push({ description, extra });
    }
}

console.log('================================================================');
console.log('  MILESTONE 3 EMPIRICAL STRESS TEST HARNESS (challenger_m3_1)');
console.log('================================================================\n');

// -----------------------------------------------------------------------------
// SUITE 1: SPINTAX PARSER & EXPANSION STRESS TESTING
// -----------------------------------------------------------------------------
console.log('--- SUITE 1: Spintax Parsing & Expansion Robustness ---');

// 1.1 Deeply nested Spintax
{
    const nested = '{A|{B|{C|D}}}';
    const seen = new Set();
    const N = 10000;
    for (let i = 0; i < N; i++) {
        const res = parseSpintax(nested);
        seen.add(res);
    }
    const allExpected = ['A', 'B', 'C', 'D'];
    const validOutputsOnly = Array.from(seen).every(x => allExpected.includes(x));
    const allBranchesReached = allExpected.every(x => seen.has(x));

    assert(validOutputsOnly && allBranchesReached,
        'Deeply nested {A|{B|{C|D}}} generates only and all valid outcomes {A,B,C,D}',
        `Seen: ${Array.from(seen).join(', ')}`);
}

// 1.2 10-level deep nesting
{
    const deep10 = '{L1|{L2|{L3|{L4|{L5|{L6|{L7|{L8|{L9|L10}}}}}}}}}';
    const deepSeen = new Set();
    for (let i = 0; i < 5000; i++) {
        deepSeen.add(parseSpintax(deep10));
    }
    const expected10 = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'L10'];
    const valid10 = Array.from(deepSeen).every(x => expected10.includes(x));
    assert(valid10 && deepSeen.size === 10,
        '10-level nested Spintax resolves completely across all 10 branches',
        `Discovered: ${deepSeen.size}/10 branches`);
}

// 1.3 Exceeding max iterations (safety limit behavior)
{
    let deep25 = 'L26';
    for (let i = 25; i >= 1; i--) {
        deep25 = `{L${i}|${deep25}}`;
    }
    const res25 = parseSpintax(deep25);
    assert(typeof res25 === 'string' && res25.length > 0,
        '25-level nested Spintax terminates safely without infinite loop or crash',
        `Result preview: ${res25.slice(0, 30)}...`);
}

// 1.4 Edge cases: Empty options
{
    const emptyOption1 = parseSpintax('{|B}');
    const emptyOption2 = parseSpintax('{A|}');
    const emptyBoth = parseSpintax('{|}');

    const seenEmpty1 = new Set();
    for (let i = 0; i < 200; i++) seenEmpty1.add(parseSpintax('{|B}'));

    assert(seenEmpty1.has('') && seenEmpty1.has('B') && seenEmpty1.size === 2,
        'Spintax with empty leading choice {|B} correctly resolves to empty string or "B"',
        `Seen: ${JSON.stringify(Array.from(seenEmpty1))}`);

    const seenEmpty2 = new Set();
    for (let i = 0; i < 200; i++) seenEmpty2.add(parseSpintax('{A|}'));
    assert(seenEmpty2.has('') && seenEmpty2.has('A') && seenEmpty2.size === 2,
        'Spintax with empty trailing choice {A|} correctly resolves to empty string or "A"',
        `Seen: ${JSON.stringify(Array.from(seenEmpty2))}`);

    const seenBoth = new Set();
    for (let i = 0; i < 100; i++) seenBoth.add(parseSpintax('{|}'));
    assert(seenBoth.size === 1 && seenBoth.has(''),
        'Spintax with empty both choices {|} resolves to empty string',
        `Seen: ${JSON.stringify(Array.from(seenBoth))}`);
}

// 1.5 Edge cases: Non-string, null, undefined, empty string
{
    assert(parseSpintax('') === '', 'parseSpintax handles empty string');
    assert(parseSpintax(null) === '', 'parseSpintax handles null without exception');
    assert(parseSpintax(undefined) === '', 'parseSpintax handles undefined without exception');
    assert(parseSpintax(12345) === 12345, 'parseSpintax handles number input safely');
}

// 1.6 Special Characters, Unicode, Vietnamese Diacritics, HTML/JSON
{
    const unicodeSpintax = '{Xin chào Việt Nam! 🇻🇳|Chào bạn nha ❤️|Hôm nay thật tuyệt vời 🎉}';
    const unicodeSeen = new Set();
    for (let i = 0; i < 1000; i++) unicodeSeen.add(parseSpintax(unicodeSpintax));
    assert(unicodeSeen.size === 3,
        'UTF-8 Vietnamese diacritics and emojis parsed accurately',
        `Discovered options: ${unicodeSeen.size}/3`);

    const htmlSpintax = '{<span class="fb">Hi</span>|<b id="test">Hello</b>}';
    const htmlSeen = new Set();
    for (let i = 0; i < 200; i++) htmlSeen.add(parseSpintax(htmlSpintax));
    assert(htmlSeen.size === 2 && htmlSeen.has('<span class="fb">Hi</span>') && htmlSeen.has('<b id="test">Hello</b>'),
        'HTML tags and attributes preserved in Spintax options');

    const jsonSpintax = '{"status": "{ok|ready}", "code": {200|201}}';
    const jsonRes = parseSpintax(jsonSpintax);
    assert(jsonRes.includes('"status":') && (jsonRes.includes('200') || jsonRes.includes('201')),
        'JSON structures with inner Spintax resolve correctly');

    const specialPunctuationSpintax = '{!@#$%^&*()_+-=[]:;"\'<>,.?/|#hashtag_test|user@fb.domain.vn}';
    const specialSeen = new Set();
    for (let i = 0; i < 500; i++) specialSeen.add(parseSpintax(specialPunctuationSpintax));
    assert(specialSeen.size === 3,
        'Punctuation symbols, hashtags, and email patterns parsed accurately without corrupting Spintax parser');
}

// 1.7 Unbalanced & Malformed Braces
{
    assert(parseSpintax('{A|B') === '{A|B', 'Unclosed opening brace {A|B handled without hanging');
    assert(parseSpintax('A|B}') === 'A|B}', 'Unmatched closing brace A|B} handled without error');
    assert(parseSpintax('}{') === '}{', 'Disordered braces }{ preserved');
    assert(parseSpintax('}{}{') === '}{}{', 'Multiple disordered braces preserved');
    assert(parseSpintax('{}') === '{}', 'Empty braces {} safely preserved without loop');
    assert(['A', 'B'].includes(parseSpintax('{{A|B}}')), 'Double braced {{A|B}} unwraps and resolves');

    // Single invocation check for random outcome
    const tripleRes = parseSpintax('{{{A|B}');
    assert(tripleRes === '{{A' || tripleRes === '{{B',
        'Asymmetric triple-open brace {{{A|B} unwrap behaves deterministically',
        `Returned: ${tripleRes}`);
}

// 1.8 Combinatorial expandAllSpintax tests
{
    const simpleComb = '{A|B} and {C|D}';
    const expanded = expandAllSpintax(simpleComb);
    const expectedCombinations = ['A and C', 'A and D', 'B and C', 'B and D'];
    const exactMatch = expanded.length === 4 && expectedCombinations.every(x => expanded.includes(x));
    assert(exactMatch, 'expandAllSpintax accurately produces 2x2=4 Cartesian combinations');

    const nestedComb = '{A|{B|C}}';
    const nestedExpanded = expandAllSpintax(nestedComb);
    const uniqueOptions = Array.from(new Set(nestedExpanded)).sort();
    const expectedUnique = ['A', 'B', 'C'].sort();
    const uniqueMatch = uniqueOptions.length === 3 && uniqueOptions.every((v, i) => v === expectedUnique[i]);
    assert(uniqueMatch,
        'expandAllSpintax covers all unique options [A, B, C] for nested {A|{B|C}}',
        `Unique set: ${JSON.stringify(uniqueOptions)} (raw count: ${nestedExpanded.length})`);

    assert(expandAllSpintax('')[0] === '', 'expandAllSpintax on empty string returns [""]');
    assert(expandAllSpintax(null)[0] === '', 'expandAllSpintax on null returns [""]');
}

// 1.9 Throughput Benchmark
{
    const benchStr = '{Chào|Hello|Hi} {bạn|anh|chị}! {Chúc bạn|Mong bạn} {một ngày tốt lành|vạn sự như ý|luôn vui vẻ}!';
    const tStart = performance.now();
    const benchmarkIters = 20000;
    for (let i = 0; i < benchmarkIters; i++) {
        parseSpintax(benchStr);
    }
    const tElapsed = performance.now() - tStart;
    const opsPerSec = Math.round((benchmarkIters / (tElapsed / 1000)));
    assert(tElapsed < 1000, `Spintax parsing throughput: ${opsPerSec.toLocaleString()} ops/sec (20k in ${tElapsed.toFixed(1)}ms)`);
}

console.log('');

// -----------------------------------------------------------------------------
// SUITE 2: BÉZIER CURVE EMPIRICAL VERIFICATION (10,000 Interpolation Points)
// -----------------------------------------------------------------------------
console.log('--- SUITE 2: Bézier Curve Calculations & Monotonicity ---');

{
    const N_POINTS = 10000;
    let strictlyMonotonic = true;
    let strictlyBounded = true;
    let noNanOrInf = true;
    let maxDiffFromSymmetry = 0;
    let prevVal = -1;

    for (let i = 0; i <= N_POINTS; i++) {
        const t = i / N_POINTS;
        const s = bezierEasing(t);

        // NaN / Infinity check
        if (Number.isNaN(s) || !Number.isFinite(s)) {
            noNanOrInf = false;
        }

        // Bounded check [0, 1]
        if (s < 0.0 || s > 1.0) {
            strictlyBounded = false;
        }

        // Monotonicity check
        if (i > 0 && s < prevVal) {
            strictlyMonotonic = false;
        }

        // Central point symmetry check: S(t) + S(1-t) == 1.0
        const sOpposite = bezierEasing(1 - t);
        const symmetryDiff = Math.abs((s + sOpposite) - 1.0);
        if (symmetryDiff > maxDiffFromSymmetry) {
            maxDiffFromSymmetry = symmetryDiff;
        }

        prevVal = s;
    }

    assert(noNanOrInf, '10,000 points contain 0 instances of NaN or Infinity');
    assert(strictlyBounded, '10,000 points are strictly bounded in [0.0, 1.0]');
    assert(strictlyMonotonic, '10,000 points are strictly non-decreasing (monotonic)');
    assert(maxDiffFromSymmetry < 1e-12, `Cubic Bézier curve satisfies exact point symmetry: max symmetry diff = ${maxDiffFromSymmetry.toExponential(4)}`);
    assert(bezierEasing(0) === 0, 'Exact boundary value: bezierEasing(0) === 0');
    assert(bezierEasing(1) === 1, 'Exact boundary value: bezierEasing(1) === 1');
    assert(bezierEasing(0.5) === 0.5, 'Exact inflection point: bezierEasing(0.5) === 0.5');
}

// 2.2 Boundary & Out-of-bounds stress
{
    assert(bezierEasing(-10) === 0, 'Negative input t=-10 clamps to 0');
    assert(bezierEasing(-0.0001) === 0, 'Near-zero negative input t=-0.0001 clamps to 0');
    assert(bezierEasing(1.0001) === 1, 'Near-one excess input t=1.0001 clamps to 1');
    assert(bezierEasing(999) === 1, 'Large excess input t=999 clamps to 1');
    assert(bezierEasing(Infinity) === 1, 'Input t=Infinity safely clamps to 1');
    assert(bezierEasing(-Infinity) === 0, 'Input t=-Infinity safely clamps to 0');
}

// 2.3 Derivative & Acceleration profile
{
    const dt = 0.001;
    const vStart = (bezierEasing(dt) - bezierEasing(0)) / dt;
    const vMid = (bezierEasing(0.5 + dt / 2) - bezierEasing(0.5 - dt / 2)) / dt;
    const vEnd = (bezierEasing(1) - bezierEasing(1 - dt)) / dt;

    assert(vStart < 0.05, `Velocity at start is low (ease-in): vStart = ${vStart.toFixed(4)}`);
    assert(Math.abs(vMid - 1.5) < 0.01, `Velocity at midpoint matches theoretical peak 1.5: vMid = ${vMid.toFixed(4)}`);
    assert(vEnd < 0.05, `Velocity at end is low (ease-out): vEnd = ${vEnd.toFixed(4)}`);
}

// 2.4 Bézier Throughput Benchmark
{
    const tStart = performance.now();
    const benchPoints = 1000000;
    let dummy = 0;
    for (let i = 0; i < benchPoints; i++) {
        dummy += bezierEasing(i / benchPoints);
    }
    const tElapsed = performance.now() - tStart;
    const opsSec = Math.round((benchPoints / (tElapsed / 1000)));
    assert(tElapsed < 500, `Bézier calculation throughput: ${opsSec.toLocaleString()} ops/sec (1M in ${tElapsed.toFixed(1)}ms)`);
}

console.log('');

// -----------------------------------------------------------------------------
// SUITE 3: REACTION SELECTION STATISTICAL SIMULATION
// -----------------------------------------------------------------------------
console.log('--- SUITE 3: Reaction Distribution Statistical Simulation ---');

function runReactionSimulation(sampleSize) {
    const counts = { LIKE: 0, LOVE: 0, HAHA: 0, WOW: 0, CARE: 0, SAD: 0, ANGRY: 0 };
    for (let i = 0; i < sampleSize; i++) {
        const r = pickRandomReaction();
        counts[r] = (counts[r] || 0) + 1;
    }
    return counts;
}

// 3.1 10,000 Sample Simulation & Pearson Chi-Square Test
{
    const N = 10000;
    const counts = runReactionSimulation(N);

    console.log(`  Statistical counts over N = ${N.toLocaleString()} draws:`);
    for (const [r, count] of Object.entries(counts)) {
        const expected = REACTION_WEIGHTS[r] * N;
        const pct = (count / N * 100).toFixed(2);
        const expPct = (REACTION_WEIGHTS[r] * 100).toFixed(2);
        console.log(`    - ${r.padEnd(5)}: ${count.toString().padStart(5)} (${pct}%) [Expected: ${expected} (${expPct}%)]`);
    }

    // Pearson Chi-Square calculation across non-zero weight classes (df = 4)
    let chiSquare = 0;
    const activeReactions = ['LIKE', 'LOVE', 'HAHA', 'WOW', 'CARE'];
    for (const r of activeReactions) {
        const observed = counts[r];
        const expected = REACTION_WEIGHTS[r] * N;
        chiSquare += Math.pow(observed - expected, 2) / expected;
    }

    const chiCritical01 = 13.277;
    console.log(`    -> Chi-Square statistic: ${chiSquare.toFixed(4)} (Critical threshold α=0.01: ${chiCritical01})`);

    assert(chiSquare < chiCritical01,
        `Chi-Square test passes at α=0.01 (χ² = ${chiSquare.toFixed(3)} < ${chiCritical01})`,
        `Empirical distribution conforms to calibrated weights`);

    // Individual confidence interval checks (allowing 99% binomial bounds)
    for (const r of activeReactions) {
        const p = REACTION_WEIGHTS[r];
        const se = Math.sqrt((p * (1 - p)) / N);
        const margin = 2.576 * se;
        const observedP = counts[r] / N;
        const inConfidenceInterval = Math.abs(observedP - p) <= margin * 1.5;
        assert(inConfidenceInterval,
            `Reaction ${r} empirical frequency ${(observedP * 100).toFixed(2)}% conforms to theoretical ${(p * 100).toFixed(1)}%`);
    }

    assert(counts.SAD === 0 && counts.ANGRY === 0,
        'Zero-weighted reactions (SAD, ANGRY) have exactly 0 occurrences');
}

// 3.2 100,000 Sample High-Precision Convergence Verification
{
    const N = 100000;
    const counts = runReactionSimulation(N);
    let maxDeviation = 0;
    for (const [r, expectedW] of Object.entries(REACTION_WEIGHTS)) {
        if (expectedW > 0) {
            const observedW = counts[r] / N;
            const dev = Math.abs(observedW - expectedW);
            if (dev > maxDeviation) maxDeviation = dev;
        }
    }
    assert(maxDeviation < 0.01,
        `Large sample convergence (N=100k): max deviation across all categories is ${(maxDeviation * 100).toFixed(3)}% (< 1.0%)`);
}

// 3.3 Reaction Facebook ID Mapping
{
    assert(getReactionFbId('LIKE') === '1635855486666999', 'getReactionFbId("LIKE") returns correct FB ID');
    assert(getReactionFbId('LOVE') === '1635855606666987', 'getReactionFbId("LOVE") returns correct FB ID');
    assert(getReactionFbId('HAHA') === '1635855726666975', 'getReactionFbId("HAHA") returns correct FB ID');
    assert(getReactionFbId('WOW') === '1635855846666963', 'getReactionFbId("WOW") returns correct FB ID');
    assert(getReactionFbId('CARE') === '2269550756598811', 'getReactionFbId("CARE") returns correct FB ID');
    assert(getReactionFbId('like') === '1635855486666999', 'getReactionFbId handles lowercase "like"');
    assert(getReactionFbId('INVALID_REACTION') === '1635855486666999', 'Unknown reaction type safely falls back to LIKE ID');
    assert(getReactionFbId(null) === '1635855486666999', 'Null reaction safely falls back to LIKE ID');
}

console.log('');

// -----------------------------------------------------------------------------
// SUITE 4: SECONDARY WARM-UP MECHANICS (Dwell, Scroll Physics, Reverse Jitter)
// -----------------------------------------------------------------------------
console.log('--- SUITE 4: Warm-up Behavioral Physics Verification ---');

// 4.1 Step distance distribution
{
    let allInBounds = true;
    for (let i = 0; i < 10000; i++) {
        const d = getRandomStepDistance();
        if (d < SCROLL_PHYSICS.step_min_px || d > SCROLL_PHYSICS.step_max_px) {
            allInBounds = false;
            break;
        }
    }
    assert(allInBounds, `getRandomStepDistance across 10,000 samples strictly in [${SCROLL_PHYSICS.step_min_px}px, ${SCROLL_PHYSICS.step_max_px}px]`);
}

// 4.2 Reverse scroll probability and distance
{
    let reverseCount = 0;
    let allDistValid = true;
    const N = 10000;
    for (let i = 0; i < N; i++) {
        const rev = checkReverseScroll();
        if (rev !== 0) {
            reverseCount++;
            if (rev > SCROLL_PHYSICS.reverse_scroll_max_px || rev < SCROLL_PHYSICS.reverse_scroll_min_px) {
                allDistValid = false;
            }
        }
    }
    const revRate = reverseCount / N;
    assert(allDistValid, `Reverse scroll distances strictly within [${SCROLL_PHYSICS.reverse_scroll_min_px}px, ${SCROLL_PHYSICS.reverse_scroll_max_px}px]`);
    assert(revRate >= 0.13 && revRate <= 0.17,
        `Reverse scroll frequency conforms to 15% specification: observed ${(revRate * 100).toFixed(2)}% (target: 15%)`);
}

// 4.3 Dwell micro-pause bounds
{
    let allNormalInBounds = true;
    let allMediaInBounds = true;
    for (let i = 0; i < 5000; i++) {
        const dwellNoMedia = getRandomDwellMs(false);
        if (dwellNoMedia < 800 || dwellNoMedia > 22000) allNormalInBounds = false;

        const dwellMedia = getRandomDwellMs(true);
        if (dwellMedia < 3500 || dwellMedia > 22000) allMediaInBounds = false;
    }
    assert(allNormalInBounds, 'Dwell times without media fall strictly in [800ms, 22000ms]');
    assert(allMediaInBounds, 'Dwell times with media fall strictly in [3500ms, 22000ms] (no short pauses)');
}

// 4.4 Headless safe execution
async function testHeadlessRoutines() {
    const scrollRes = await executeTabScroll(1, 400, 300);
    assert(scrollRes.success === true && scrollRes.distance === 400, 'executeTabScroll gracefully handles non-browser environment');

    const reactRes = await sendReactionGraphQL(1, 'feedback_123', 'LOVE');
    assert(reactRes.success === true && reactRes.reaction === 'LOVE', 'sendReactionGraphQL gracefully handles non-browser environment');

    const cmtRes = await sendCommentGraphQL(1, 'feedback_123', '{Tuyệt|Hay} quá!');
    assert(cmtRes.success === true && typeof cmtRes.text === 'string', 'sendCommentGraphQL gracefully handles non-browser environment');

    const reportedSteps = [];
    const sessionRes = await runWarmupSession(1, { durationSeconds: 0.1 }, async (msg) => {
        reportedSteps.push(msg);
    });
    assert(sessionRes.success === true && reportedSteps.length > 0,
        'runWarmupSession completes clean lifecycle in headless environment',
        `Steps recorded: ${reportedSteps.length}`);
}

testHeadlessRoutines().then(() => {
    console.log('\n================================================================');
    console.log(`  TEST RESULTS: ${passedTests} passed, ${failedTests} failed (Total: ${totalTests})`);
    console.log('================================================================\n');

    if (failedTests > 0) {
        console.error('FAILED TESTS SUMMARY:');
        failureDetails.forEach(f => console.error(`  - ${f.description}: ${f.extra}`));
        process.exit(1);
    } else {
        console.log('ALL EMPIRICAL TESTS PASSED SUCCESSFULLY! Verdict: APPROVE');
        process.exit(0);
    }
}).catch(err => {
    console.error('FATAL TEST RUN ERROR:', err);
    process.exit(1);
});
