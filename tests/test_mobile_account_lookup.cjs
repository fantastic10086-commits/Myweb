// Exercise the shipped lookup code, including silent password-manager autofill.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/mobile/mobile.js', 'utf8');
const events = {}, intervals = [], requests = [];
const elements = {
  account: {value: '', addEventListener(name, fn) { events[name] = fn; }},
  'resolved-username': {value: ''},
  'account-name': {textContent: ''},
};
const context = {
  $: id => elements[id], state: {user: null, csrf: 'test-csrf'},
  document: {hidden: false}, window: {addEventListener() {}},
  setTimeout, clearTimeout, AbortController,
  setInterval: fn => intervals.push(fn),
  fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve})),
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('// Reuse the normal login'), source.indexOf('function dateText')), context);
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
(async () => {
  // No input/change event: browser fills after initialization.
  elements.account.value = 'admin'; intervals[0](); await tick();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].options.headers['X-CSRFToken'], 'test-csrf');
  requests[0].resolve({ok: true, json: async () => ({ok: true, username: '管理员'})});
  await tick(); assert.equal(elements['resolved-username'].value, '管理员');
  for (let i=0; i<5; i++) intervals[0]();
  await tick(); assert.equal(requests.length, 1, 'unchanged account must not trigger network polling');
  elements.account.value = 'old-account'; intervals[0](); await tick();
  assert.equal(elements['resolved-username'].value, '');
  elements.account.value = ''; intervals[0]();
  requests[1].resolve({ok: true, json: async () => ({ok: true, username: '过期姓名'})});
  await tick(); assert.equal(elements['resolved-username'].value, '');
  elements.account.value = 'unknown'; intervals[0](); await tick();
  requests[2].resolve({ok: true, json: async () => ({ok: false})});
  await tick(); assert.equal(elements['resolved-username'].value, '');
  assert.match(elements['account-name'].textContent, /未识别/);
  context.state.user = {name: 'signed-in'};
  elements.account.value = 'another'; intervals[0](); await tick();
  assert.equal(requests.length, 3, 'signed-in page must not perform account lookups');
  console.log('PASS: silent autofill, CSRF, no repeated queries, stale results, clear, unknown and signed-in cases');
})().catch(error => { console.error(error); process.exitCode = 1; });
