/**
 * tests/test_challenger_m4_admin_stress.js
 * Empirical Challenge Suite for Milestone 4 Admin Console (admin.html)
 * Focus: JavaScript Logic, Countdown Tickers, Heartbeat Formatting, and Edge Cases
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const adminHtmlPath = path.resolve(__dirname, '../fbauto-backend-python/admin.html');
assert(fs.existsSync(adminHtmlPath), `admin.html not found at ${adminHtmlPath}`);

const htmlContent = fs.readFileSync(adminHtmlPath, 'utf8');

// Extract all script contents from admin.html
const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let fullJsCode = '';
while ((match = scriptRegex.exec(htmlContent)) !== null) {
  fullJsCode += '\n' + match[1];
}

console.log(`[CHALLENGER-M4-2] Loaded admin.html (${htmlContent.length} bytes), extracted ${fullJsCode.length} bytes of JS code.`);

// Set up a sandbox with realistic DOM environment
class MockElement {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.attributes = {};
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.style = {};
    this.classList = new Set();
    this.children = [];
  }
  getAttribute(name) {
    return this.attributes[name] !== undefined ? this.attributes[name] : null;
  }
  setAttribute(name, val) {
    this.attributes[name] = String(val);
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
}

class MockDocument {
  constructor() {
    this.elements = new Map();
  }
  getElementById(id) {
    return this.elements.get(id) || null;
  }
  registerElement(el) {
    if (el.id) this.elements.set(el.id, el);
    return el;
  }
  querySelectorAll(selector) {
    const results = [];
    if (selector === '.lease-cell') {
      for (const el of this.elements.values()) {
        if (el.attributes['class'] && el.attributes['class'].includes('lease-cell')) {
          results.push(el);
        }
      }
    } else if (selector === '.worker-last-seen-text') {
      for (const el of this.elements.values()) {
        if (el.attributes['class'] && el.attributes['class'].includes('worker-last-seen-text')) {
          results.push(el);
        }
      }
    }
    return results;
  }
  createElement(tag) {
    return new MockElement(tag);
  }
  addEventListener(event, handler) {}
  removeEventListener(event, handler) {}
}

const doc = new MockDocument();

// Register mock elements required by admin scripts
const mockIds = [
  'postAccountSelect', 'postTargetType', 'postTargetId', 'postAccessToken',
  'postSeedingComments', 'postAutoReplyText', 'workerFilterProject',
  'statWorkerTotal', 'statWorkerOnline', 'statWorkerBusy', 'statWorkerOffline',
  'statWorkerAssignedAccs', 'navWorkersBadge', 'workerRefreshCountdown',
  'assignModalWorkerName', 'assignModalWorkerId', 'assignModalProjectKey',
  'toast', 'toastIcon', 'toastMsg'
];
for (const id of mockIds) {
  const el = new MockElement('div', id);
  el.classList = {
    add: () => {},
    remove: () => {}
  };
  doc.registerElement(el);
}

const sandbox = {
  document: doc,
  window: {
    location: {
      protocol: 'http:',
      host: '127.0.0.1:19823',
      origin: 'http://127.0.0.1:19823',
      pathname: '/admin.html'
    },
    localStorage: {
      getItem: () => null,
      setItem: () => {}
    },
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  localStorage: {
    getItem: () => null,
    setItem: () => {}
  },
  navigator: {
    clipboard: {
      writeText: () => Promise.resolve()
    }
  },
  console: {
    log: () => {},
    warn: () => {},
    error: () => {},
    info: () => {}
  },
  Date: Date,
  Math: Math,
  parseInt: parseInt,
  parseFloat: parseFloat,
  isNaN: isNaN,
  isFinite: isFinite,
  setInterval: () => 1,
  clearInterval: () => {},
  setTimeout: () => 1,
  clearTimeout: () => {},
  showToast: (msg, type) => {},
  escapeHtml: (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
  API_BASE: 'http://127.0.0.1:19823',
  _allWorkersCache: [],
  _allAccountsCache: [],
  _allProjectsCache: [],
  _allTasksCache: [],
  _accountsFarmCache: []
};

// Execute script in sandbox to extract defined functions
try {
  vm.createContext(sandbox);
  vm.runInContext(fullJsCode, sandbox);
  console.log('[CHALLENGER-M4-2] Successfully parsed and executed admin.html scripts in VM sandbox.');
} catch (e) {
  console.error('[CHALLENGER-M4-2] VM Execution warning:', e.message);
}

const {
  formatRelativeTime,
  computeLeaseBadgeHtml,
  updateLeaseCountdownsInDom,
  resolveWorkerStatus,
  populatePostAccountDropdown,
  onSelectPostAccount
} = sandbox;

assert(typeof formatRelativeTime === 'function', 'formatRelativeTime must be a function');
assert(typeof computeLeaseBadgeHtml === 'function', 'computeLeaseBadgeHtml must be a function');
assert(typeof updateLeaseCountdownsInDom === 'function', 'updateLeaseCountdownsInDom must be a function');
assert(typeof resolveWorkerStatus === 'function', 'resolveWorkerStatus must be a function');

console.log('[CHALLENGER-M4-2] Core functions extracted successfully.');

let passedTests = 0;
let totalTests = 0;

function runTest(name, fn) {
  totalTests++;
  try {
    fn();
    passedTests++;
    console.log(`  ✓ [PASS] ${name}`);
  } catch (err) {
    console.error(`  ✗ [FAIL] ${name}: ${err.message}`);
    throw err;
  }
}

console.log('\n======================================================================');
console.log('TEST SUITE 1: Heartbeat Relative Time Formatting (formatRelativeTime)');
console.log('======================================================================');

runTest('Relative time with null / undefined timestamp', () => {
  const res1 = formatRelativeTime(null);
  assert.strictEqual(res1.text, 'Chưa có dữ liệu');
  assert.strictEqual(res1.tier, 'red');
  assert.strictEqual(res1.sec, 999999);

  const res2 = formatRelativeTime(undefined);
  assert.strictEqual(res2.text, 'Chưa có dữ liệu');
  assert.strictEqual(res2.tier, 'red');

  const res3 = formatRelativeTime(0);
  assert.strictEqual(res3.text, 'Chưa có dữ liệu');
  assert.strictEqual(res3.tier, 'red');
});

runTest('Relative time with negative timestamp', () => {
  const res = formatRelativeTime(-5000);
  assert(!isNaN(res.sec), 'sec must not be NaN');
  assert(res.tier === 'red', 'Negative timestamp must be stale/red');
  assert(typeof res.text === 'string' && res.text.length > 0);
});

runTest('Relative time at 0s / future timestamp (clock skew)', () => {
  const now = Date.now();
  // Exact current time
  const resExact = formatRelativeTime(now);
  assert.strictEqual(resExact.sec, 0);
  assert(resExact.text.includes('Vừa xong') || resExact.text.includes('Just now'));
  assert.strictEqual(resExact.tier, 'green');

  // Future timestamp (clock skew of 10s ahead)
  const resFuture = formatRelativeTime(now + 10000);
  assert.strictEqual(resFuture.sec, 0, 'Math.max(0, ...) should clamp future diff to 0');
  assert(resFuture.text.includes('Vừa xong'));
  assert.strictEqual(resFuture.tier, 'green');
});

runTest('Relative time at 5s (threshold boundary)', () => {
  const now = Date.now();
  const res5s = formatRelativeTime(now - 5000);
  assert(res5s.sec >= 4 && res5s.sec <= 6);
  assert(res5s.text.includes('s trước') || res5s.text.includes('s ago'));
  assert.strictEqual(res5s.tier, 'green');
});

runTest('Relative time at 20s (green to amber boundary)', () => {
  const now = Date.now();
  const res20s = formatRelativeTime(now - 20000);
  assert.strictEqual(res20s.tier, 'green');

  const res25s = formatRelativeTime(now - 25000);
  assert.strictEqual(res25s.tier, 'amber');
});

runTest('Relative time at 45s (amber to red boundary / offline threshold)', () => {
  const now = Date.now();
  const res45s = formatRelativeTime(now - 45000);
  assert.strictEqual(res45s.tier, 'amber');

  const res46s = formatRelativeTime(now - 46000);
  assert.strictEqual(res46s.tier, 'red');
});

runTest('Relative time at 60s (seconds to minutes boundary)', () => {
  const now = Date.now();
  const res60s = formatRelativeTime(now - 60000);
  assert(res60s.text.includes('phút trước'));
  assert.strictEqual(res60s.tier, 'red');
});

runTest('Relative time at 3600s (minutes to hours boundary)', () => {
  const now = Date.now();
  const res3600s = formatRelativeTime(now - 3600000);
  assert(res3600s.text.includes('giờ trước'));
  assert.strictEqual(res3600s.tier, 'red');
});

runTest('Relative time at 86400s (hours to days boundary)', () => {
  const now = Date.now();
  const res86400s = formatRelativeTime(now - 86400000);
  assert(res86400s.text.includes('ngày trước'));
  assert.strictEqual(res86400s.tier, 'red');
});

console.log('\n======================================================================');
console.log('TEST SUITE 2: Task Queue Lease Tickers (computeLeaseBadgeHtml & updateLeaseCountdownsInDom)');
console.log('======================================================================');

runTest('computeLeaseBadgeHtml with null / missing leaseExpiresAt', () => {
  const taskNull = { leaseExpiresAt: null };
  const badgeNull = computeLeaseBadgeHtml(taskNull);
  assert(badgeNull.includes('N/A'));

  const taskUndef = {};
  const badgeUndef = computeLeaseBadgeHtml(taskUndef);
  assert(badgeUndef.includes('N/A'));
});

runTest('computeLeaseBadgeHtml with expired lease (in past)', () => {
  const now = Date.now();
  const taskPast = { leaseExpiresAt: now - 15000 };
  const badgePast = computeLeaseBadgeHtml(taskPast);
  assert(badgePast.includes('lease-expired'));
  assert(badgePast.includes('Hết hạn (0s)'));
});

runTest('computeLeaseBadgeHtml with urgent lease (<= 15s remaining)', () => {
  const now = Date.now();
  const taskUrgent = { leaseExpiresAt: now + 12000 };
  const badgeUrgent = computeLeaseBadgeHtml(taskUrgent);
  assert(badgeUrgent.includes('lease-amber'));
  assert(badgeUrgent.includes('Còn 12s') || badgeUrgent.includes('Còn 11s') || badgeUrgent.includes('Còn 13s'));
});

runTest('computeLeaseBadgeHtml with healthy lease (> 15s remaining)', () => {
  const now = Date.now();
  const taskHealthy = { leaseExpiresAt: now + 50000 };
  const badgeHealthy = computeLeaseBadgeHtml(taskHealthy);
  assert(badgeHealthy.includes('lease-green'));
  assert(badgeHealthy.includes('Còn 50s') || badgeHealthy.includes('Còn 49s') || badgeHealthy.includes('Còn 51s'));
});

runTest('updateLeaseCountdownsInDom DOM mutation across diverse cell statuses and timestamps', () => {
  const now = Date.now();

  // Create mock DOM cells
  const cellExpired = new MockElement('td', 'cell1');
  cellExpired.setAttribute('class', 'lease-cell');
  cellExpired.setAttribute('data-status', 'running');
  cellExpired.setAttribute('data-lease-expires', String(now - 5000));
  doc.registerElement(cellExpired);

  const cellAmber = new MockElement('td', 'cell2');
  cellAmber.setAttribute('class', 'lease-cell');
  cellAmber.setAttribute('data-status', 'assigned');
  cellAmber.setAttribute('data-lease-expires', String(now + 10000));
  doc.registerElement(cellAmber);

  const cellGreen = new MockElement('td', 'cell3');
  cellGreen.setAttribute('class', 'lease-cell');
  cellGreen.setAttribute('data-status', 'running');
  cellGreen.setAttribute('data-lease-expires', String(now + 45000));
  doc.registerElement(cellGreen);

  const cellCompleted = new MockElement('td', 'cell4');
  cellCompleted.setAttribute('class', 'lease-cell');
  cellCompleted.setAttribute('data-status', 'completed');
  cellCompleted.setAttribute('data-lease-expires', String(now + 45000));
  cellCompleted.innerHTML = '<span class="keep-completed">Done</span>';
  doc.registerElement(cellCompleted);

  const cellNoLease = new MockElement('td', 'cell5');
  cellNoLease.setAttribute('class', 'lease-cell');
  cellNoLease.setAttribute('data-status', 'running');
  cellNoLease.setAttribute('data-lease-expires', '0');
  cellNoLease.innerHTML = '<span class="keep-none">No Lease</span>';
  doc.registerElement(cellNoLease);

  // Invoke updateLeaseCountdownsInDom
  updateLeaseCountdownsInDom();

  assert(cellExpired.innerHTML.includes('lease-expired'), 'Expired cell must receive expired badge');
  assert(cellAmber.innerHTML.includes('lease-amber'), 'Urgent cell must receive amber badge');
  assert(cellGreen.innerHTML.includes('lease-green'), 'Healthy cell must receive green badge');
  assert.strictEqual(cellCompleted.innerHTML, '<span class="keep-completed">Done</span>', 'Completed cell must not be updated');
  assert.strictEqual(cellNoLease.innerHTML, '<span class="keep-none">No Lease</span>', 'Zero lease cell must not be updated');
});

console.log('\n======================================================================');
console.log('TEST SUITE 3: Worker Node Status Resolution (resolveWorkerStatus)');
console.log('======================================================================');

runTest('resolveWorkerStatus with active worker node (heartbeat < 45s, status idle)', () => {
  const now = Date.now();
  const worker = { id: 'w1', status: 'idle', lastSeen: now - 10000, currentTaskId: null };
  const res = resolveWorkerStatus(worker, now);
  assert.strictEqual(res.key, 'online');
  assert.strictEqual(res.badgeClass, 'badge-status-online');
});

runTest('resolveWorkerStatus with busy worker node (status busy or currentTaskId present)', () => {
  const now = Date.now();
  const worker1 = { id: 'w2', status: 'busy', lastSeen: now - 5000, currentTaskId: null };
  const res1 = resolveWorkerStatus(worker1, now);
  assert.strictEqual(res1.key, 'busy');

  const worker2 = { id: 'w3', status: 'idle', lastSeen: now - 5000, currentTaskId: 'task_123' };
  const res2 = resolveWorkerStatus(worker2, now);
  assert.strictEqual(res2.key, 'busy');
});

runTest('resolveWorkerStatus with stale worker node (heartbeat > 45s -> offline)', () => {
  const now = Date.now();
  const workerStale = { id: 'w4', status: 'idle', lastSeen: now - 50000, currentTaskId: null };
  const resStale = resolveWorkerStatus(workerStale, now);
  assert.strictEqual(resStale.key, 'offline');
  assert.strictEqual(resStale.badgeClass, 'badge-status-offline');
});

console.log('\n======================================================================');
console.log('TEST SUITE 4: Legacy Post Creation Form Functions & Non-Regression');
console.log('======================================================================');

runTest('populatePostAccountDropdown updates select options without exception', () => {
  const select = doc.getElementById('postAccountSelect');
  const mockAccounts = [
    { id: 'acc_1', name: 'Page Bán Hàng 1', type: 'page', targetId: '1000123' },
    { id: 'acc_2', name: 'Group Thảo Luận', type: 'group', targetId: '2000456' },
    { id: 'acc_3', name: 'Profile Nguyễn Văn A', type: 'profile', targetId: '3000789' }
  ];

  populatePostAccountDropdown(mockAccounts);
  assert(select.innerHTML.includes('acc_1'));
  assert(select.innerHTML.includes('Page Bán Hàng 1'));
  assert(select.innerHTML.includes('Group Thảo Luận'));
});

runTest('onSelectPostAccount autofills target type, target id, and token', () => {
  const targetType = doc.getElementById('postTargetType');
  const targetId = doc.getElementById('postTargetId');
  const accessToken = doc.getElementById('postAccessToken');

  // Select account 1
  onSelectPostAccount('acc_1');
  assert.strictEqual(targetType.value, 'page');
  assert.strictEqual(targetId.value, '1000123');

  // Deselect (null / empty)
  onSelectPostAccount('');
  assert.strictEqual(targetType.value, 'profile');
  assert.strictEqual(targetId.value, '');
  assert.strictEqual(accessToken.value, '');
});

console.log('\n======================================================================');
console.log(`[CHALLENGER-M4-2] ALL ${passedTests}/${totalTests} TESTS PASSED CLEANLY WITH ZERO EXCEPTIONS!`);
console.log('======================================================================\n');
