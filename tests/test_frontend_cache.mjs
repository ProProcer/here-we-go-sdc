import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cachedResult, clearResults, lastResult, rememberResult, resultKey, reuseResult } from '../frontend/src/resultCache.ts';

test('cache keys isolate sessions, settings and languages', () => {
  const key = resultKey('session-one', 'map', ['role', 5, 'ms']);
  assert.notEqual(key, resultKey('session-two', 'map', ['role', 5, 'ms']));
  assert.notEqual(key, resultKey('session-one', 'map', ['role', 10, 'ms']));
  assert.notEqual(key, resultKey('session-one', 'map', ['role', 5, 'zh']));
});

test('expired outlook stays visible while a fresh request loads', () => {
  clearResults();
  const original = Date.now;
  let now = original();
  Date.now = () => now;
  try {
    rememberResult('outlook', { finding: 'A completed assessment' }, 60000);
    now += 61000;
    assert.equal(cachedResult('outlook'), null);
    assert.equal(lastResult('outlook').finding, 'A completed assessment');
    now += 3600000;
    assert.equal(lastResult('outlook'), null);
  } finally { Date.now = original; }
});

test('duplicate requests share one load and profile edits discard late results', async () => {
  clearResults();
  let complete;
  let calls = 0;
  const load = () => { calls++; return new Promise(resolve => { complete = resolve; }); };
  const one = reuseResult('map', load);
  const two = reuseResult('map', load);
  assert.equal(calls, 1);
  clearResults();
  complete({ nodes: ['old-profile'] });
  assert.deepEqual(await one, await two);
  assert.equal(cachedResult('map'), null);
  await reuseResult('map', async () => ({ nodes: ['new-profile'] }));
  assert.deepEqual(cachedResult('map').nodes, ['new-profile']);
});

test('failed requests are retryable and retained entries are bounded', async () => {
  clearResults();
  await assert.rejects(reuseResult('error', async () => { throw new Error('temporary'); }));
  assert.equal(cachedResult('error'), null);
  assert.equal(await reuseResult('error', async () => 'retried'), 'retried');
  for (let index = 0; index < 81; index++) rememberResult(`key-${index}`, index);
  assert.equal(lastResult('key-0'), null);
  assert.equal(cachedResult('key-80'), 80);
});
