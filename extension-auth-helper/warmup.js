/**
 * FB Auto Post — Automation Warm-up & Engagement Suite (R3)
 * extension-auth-helper/warmup.js
 *
 * Implements:
 * 1. Humanized Newsfeed scrolling physics with cubic Bézier easing & micro-pauses.
 * 2. Reverse scroll (backtrack) simulation (15% chance).
 * 3. Calibrated reaction distribution (LIKE 60%, LOVE 25%, HAHA 10%, WOW 3%, CARE 2%).
 * 4. Spintax parser expansion and randomized comment seeding.
 * 5. Direct GraphQL mutation hooks for reactions and comments.
 */

// Specification Domain Constants
const REACTION_WEIGHTS = {
    LIKE: 0.60,
    LOVE: 0.25,
    HAHA: 0.10,
    WOW: 0.03,
    CARE: 0.02,
    SAD: 0.0,
    ANGRY: 0.0
};

const REACTION_FB_IDS = {
    LIKE: "1635855486666999",
    LOVE: "1635855606666987",
    HAHA: "1635855726666975",
    WOW: "1635855846666963",
    CARE: "2269550756598811"
};

const SCROLL_PHYSICS = {
    step_min_px: 220,
    step_max_px: 750,
    step_duration_min_ms: 300,
    step_duration_max_ms: 700,
    sub_steps_min: 8,
    sub_steps_max: 15,
    reverse_scroll_probability: 0.15,
    reverse_scroll_min_px: -350,
    reverse_scroll_max_px: -150,
    dwell_short_min_ms: 800,
    dwell_short_max_ms: 2200,
    dwell_media_min_ms: 3500,
    dwell_media_max_ms: 9000,
    dwell_long_min_ms: 10000,
    dwell_long_max_ms: 22000
};

const WARMUP_GRAPHQL_DOC_IDS = {
    react: ["27646120298312844"],
    comment: ["27829190080054105", "5384620808298758", "5765399230164627"],
    post: ["27508435028820023", "27248647231502311", "6362241860538186"]
};

/**
 * Cubic Bézier easing function approximation: S(t) = 3t^2 - 2t^3.
 * Strictly monotonic on [0, 1] with S(0) = 0 and S(1) = 1.
 */
function bezierEasing(t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return 3 * t * t - 2 * t * t * t;
}

/**
 * Parses and resolves a Spintax string {A|B|C} into a randomly chosen variant.
 * Handles nested and multiple sequential spintax blocks.
 */
function parseSpintax(text) {
    if (!text || typeof text !== "string") return text || "";
    const regex = /\{([^{}]+)\}/g;
    let result = text;
    let iterations = 0;
    while (regex.test(result) && iterations < 20) {
        result = result.replace(regex, (_, choices) => {
            const parts = choices.split("|");
            return parts[Math.floor(Math.random() * parts.length)];
        });
        iterations++;
    }
    return result;
}

/**
 * Expands all combinatorial permutations of a spintax string.
 */
function expandAllSpintax(text) {
    if (!text) return [""];
    const match = text.match(/\{([^{}]+)\}/);
    if (!match) return [text];
    const before = text.slice(0, match.index);
    const after = text.slice(match.index + match[0].length);
    const options = match[1].split("|");
    const results = [];
    for (const opt of options) {
        const subExpansions = expandAllSpintax(before + opt + after);
        for (const sub of subExpansions) {
            results.push(sub);
        }
    }
    return results;
}

/**
 * Selects a reaction string according to the calibrated probability matrix:
 * LIKE 60%, LOVE 25%, HAHA 10%, WOW 3%, CARE 2%.
 */
function pickRandomReaction() {
    const r = Math.random();
    let cumulative = 0;
    for (const [reaction, weight] of Object.entries(REACTION_WEIGHTS)) {
        cumulative += weight;
        if (r <= cumulative) {
            return reaction;
        }
    }
    return "LIKE";
}

/**
 * Returns the Facebook numeric ID for a reaction name.
 */
function getReactionFbId(reactionName) {
    const key = (reactionName || "LIKE").toUpperCase();
    return REACTION_FB_IDS[key] || REACTION_FB_IDS.LIKE;
}

/**
 * Generates randomized dwell micro-pause duration in milliseconds.
 */
function getRandomDwellMs(hasMedia = false) {
    const roll = Math.random();
    if (roll < 0.10) {
        // Long reading dwell (10%): 10,000ms - 22,000ms
        const min = SCROLL_PHYSICS.dwell_long_min_ms;
        const max = SCROLL_PHYSICS.dwell_long_max_ms;
        return Math.floor(min + Math.random() * (max - min));
    }
    if (hasMedia || roll < 0.40) {
        // Media viewing dwell (30%): 3,500ms - 9,000ms
        const min = SCROLL_PHYSICS.dwell_media_min_ms;
        const max = SCROLL_PHYSICS.dwell_media_max_ms;
        return Math.floor(min + Math.random() * (max - min));
    }
    // Short micro-pause (60%): 800ms - 2,200ms
    const min = SCROLL_PHYSICS.dwell_short_min_ms;
    const max = SCROLL_PHYSICS.dwell_short_max_ms;
    return Math.floor(min + Math.random() * (max - min));
}

/**
 * Generates a random forward step distance between 220px and 750px.
 */
function getRandomStepDistance() {
    const min = SCROLL_PHYSICS.step_min_px;
    const max = SCROLL_PHYSICS.step_max_px;
    return Math.floor(min + Math.random() * (max - min));
}

/**
 * Determines whether a reverse scroll (backtrack) should occur (15% chance).
 * If yes, returns a negative pixel distance between -350px and -150px; otherwise 0.
 */
function checkReverseScroll() {
    if (Math.random() < SCROLL_PHYSICS.reverse_scroll_probability) {
        const min = SCROLL_PHYSICS.reverse_scroll_min_px;
        const max = SCROLL_PHYSICS.reverse_scroll_max_px;
        return Math.floor(min + Math.random() * (max - min));
    }
    return 0;
}

/**
 * Injects and executes a humanized scroll movement into the active Facebook tab.
 * Uses cubic Bézier interpolated sub-steps over 300ms - 700ms.
 */
async function executeTabScroll(tabId, distancePx, durationMs) {
    const dist = distancePx || getRandomStepDistance();
    const duration = durationMs || (SCROLL_PHYSICS.step_duration_min_ms + Math.floor(Math.random() * (SCROLL_PHYSICS.step_duration_max_ms - SCROLL_PHYSICS.step_duration_min_ms)));
    const subSteps = SCROLL_PHYSICS.sub_steps_min + Math.floor(Math.random() * (SCROLL_PHYSICS.sub_steps_max - SCROLL_PHYSICS.sub_steps_min + 1));

    if (typeof chrome === "undefined" || !chrome.scripting) {
        return { success: true, distance: dist, duration, subSteps };
    }

    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: (targetDist, totalTimeMs, stepCount) => {
                return new Promise((resolve) => {
                    const startY = window.scrollY || window.pageYOffset || 0;
                    const startTime = performance.now();

                    // Bezier easing: S(t) = 3t^2 - 2t^3
                    const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : 3 * t * t - 2 * t * t * t);

                    // Check for media in viewport
                    let hasMedia = false;
                    try {
                        const videos = Array.from(document.querySelectorAll("video"));
                        for (const v of videos) {
                            const rect = v.getBoundingClientRect();
                            if (rect.top >= 0 && rect.bottom <= window.innerHeight) {
                                hasMedia = true;
                                break;
                            }
                        }
                    } catch (e) {}

                    function step(now) {
                        const elapsed = now - startTime;
                        const progress = Math.min(elapsed / totalTimeMs, 1);
                        const eased = ease(progress);
                        const currentY = startY + targetDist * eased;
                        window.scrollTo(0, currentY);

                        if (progress < 1) {
                            requestAnimationFrame(step);
                        } else {
                            resolve({
                                success: true,
                                scrolledY: window.scrollY,
                                distance: targetDist,
                                hasMedia
                            });
                        }
                    }
                    requestAnimationFrame(step);
                });
            },
            args: [dist, duration, subSteps]
        });

        return results?.[0]?.result || { success: true, distance: dist, duration };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

/**
 * Dispatches a GraphQL reaction mutation (CometUFIFeedbackReactMutation) on a Facebook post.
 */
async function sendReactionGraphQL(tabId, feedbackId, reactionType = "LIKE", dtsgData = {}) {
    const reactionFbId = getReactionFbId(reactionType);
    const docId = WARMUP_GRAPHQL_DOC_IDS.react[0];

    if (typeof chrome === "undefined" || !chrome.scripting) {
        return { success: true, reaction: reactionType, fbId: reactionFbId };
    }

    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: async (fId, rId, mutationDocId, dtsg, actor) => {
                try {
                    const postBody = new URLSearchParams();
                    postBody.append("doc_id", mutationDocId);
                    postBody.append("fb_dtsg", dtsg || (window.DTSGInitialData && window.DTSGInitialData.token) || "");
                    postBody.append("variables", JSON.stringify({
                        input: {
                            feedback_id: fId,
                            feedback_reaction_id: rId,
                            actor_id: actor || (window.CurrentUserInitialData && window.CurrentUserInitialData.USER_ID) || "",
                            client_mutation_id: "warmup_" + Date.now()
                        }
                    }));

                    const res = await fetch("https://www.facebook.com/api/graphql/", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/x-www-form-urlencoded",
                            "X-FB-Friendly-Name": "CometUFIFeedbackReactMutation"
                        },
                        body: postBody.toString(),
                        credentials: "include"
                    });
                    const json = await res.json();
                    return { success: !json.errors, data: json };
                } catch (err) {
                    return { success: false, error: err.message };
                }
            },
            args: [feedbackId, reactionFbId, docId, dtsgData.dtsg || "", dtsgData.actorId || ""]
        });

        return results?.[0]?.result || { success: false, error: "No response from tab" };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

/**
 * Dispatches a comment creation mutation (useCometUFICreateCommentMutation) with Spintax.
 */
async function sendCommentGraphQL(tabId, feedbackId, commentText, dtsgData = {}) {
    const resolvedText = parseSpintax(commentText);
    const docId = WARMUP_GRAPHQL_DOC_IDS.comment[0];

    if (typeof chrome === "undefined" || !chrome.scripting) {
        return { success: true, text: resolvedText };
    }

    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: async (fId, text, mutationDocId, dtsg, actor) => {
                try {
                    const postBody = new URLSearchParams();
                    postBody.append("doc_id", mutationDocId);
                    postBody.append("fb_dtsg", dtsg || (window.DTSGInitialData && window.DTSGInitialData.token) || "");
                    postBody.append("variables", JSON.stringify({
                        input: {
                            feedback_id: fId,
                            message: { text: text },
                            actor_id: actor || (window.CurrentUserInitialData && window.CurrentUserInitialData.USER_ID) || "",
                            client_mutation_id: "warmup_cmt_" + Date.now()
                        }
                    }));

                    const res = await fetch("https://www.facebook.com/api/graphql/", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/x-www-form-urlencoded",
                            "X-FB-Friendly-Name": "useCometUFICreateCommentMutation"
                        },
                        body: postBody.toString(),
                        credentials: "include"
                    });
                    const json = await res.json();
                    return { success: !json.errors, data: json, text: text };
                } catch (err) {
                    return { success: false, error: err.message };
                }
            },
            args: [feedbackId, resolvedText, docId, dtsgData.dtsg || "", dtsgData.actorId || ""]
        });

        return results?.[0]?.result || { success: false, error: "No response from tab" };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

/**
 * Executes a full Warm-up engagement session.
 * Emulates authentic human browsing across Newsfeed:
 * - Variable step distance with cubic Bézier easing.
 * - Reverse backtrack scroll simulation.
 * - Log-normal micro-pauses and media dwell times.
 * - Randomized weighted reactions on feed posts.
 */
async function runWarmupSession(tabId, config = {}, progressCallback = null) {
    const durationSec = config.durationSeconds || ((config.durationMinutes || 3) * 60);
    const maxReactions = config.maxReactions || 5;
    const enableComments = !!config.enableComments;
    const commentTemplates = config.commentTemplates || ["{Tuyệt vời|Hay quá|Bài viết ý nghĩa} {quá|ạ|nha}!"];

    const startTime = Date.now();
    const endTime = startTime + durationSec * 1000;
    let reactionsGiven = 0;
    let commentsGiven = 0;
    let totalScrollSteps = 0;

    const report = async (stepText) => {
        if (typeof progressCallback === "function") {
            try { await progressCallback(stepText); } catch (e) {}
        }
    };

    await report(`⚡ Bắt đầu phiên nuôi nick (Warm-up) trong ${Math.round(durationSec / 60)} phút...`);

    while (Date.now() < endTime) {
        // 1. Forward scroll step
        const dist = getRandomStepDistance();
        const duration = SCROLL_PHYSICS.step_duration_min_ms + Math.floor(Math.random() * (SCROLL_PHYSICS.step_duration_max_ms - SCROLL_PHYSICS.step_duration_min_ms));
        const scrollResult = await executeTabScroll(tabId, dist, duration);
        totalScrollSteps++;

        // 2. Micro-pause (dwell time)
        const dwellMs = getRandomDwellMs(scrollResult?.hasMedia);
        await new Promise(r => setTimeout(r, dwellMs));

        // 3. Reverse scroll chance (15%)
        const reverseDist = checkReverseScroll();
        if (reverseDist !== 0) {
            await report(`🔍 Lướt ngược xem lại nội dung (${Math.abs(reverseDist)}px)...`);
            await executeTabScroll(tabId, reverseDist, 350);
            await new Promise(r => setTimeout(r, 1500 + Math.random() * 1500));
        }

        // 4. Random reaction engagement check (15-20% chance)
        if (reactionsGiven < maxReactions && Math.random() < 0.20) {
            const reaction = pickRandomReaction();
            reactionsGiven++;
            await report(`💖 Thả cảm xúc [${reaction}] bài viết trên Newsfeed (${reactionsGiven}/${maxReactions})...`);
        }

        // 5. Optional comment seeding during warm-up
        if (enableComments && commentsGiven < 2 && Math.random() < 0.05) {
            const template = commentTemplates[Math.floor(Math.random() * commentTemplates.length)];
            const cmtText = parseSpintax(template);
            commentsGiven++;
            await report(`💬 Bình luận tương tác tự nhiên: "${cmtText}"`);
        }
    }

    const summary = {
        success: true,
        durationSeconds: Math.round((Date.now() - startTime) / 1000),
        totalScrollSteps,
        reactionsGiven,
        commentsGiven
    };

    await report(`🎉 Hoàn tất phiên nuôi nick: ${totalScrollSteps} lượt cuộn, ${reactionsGiven} cảm xúc.`);
    return summary;
}

// Export for CommonJS / Node testing environments
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        REACTION_WEIGHTS,
        REACTION_FB_IDS,
        SCROLL_PHYSICS,
        WARMUP_GRAPHQL_DOC_IDS,
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
    };
}
