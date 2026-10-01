const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {test} = require('node:test');
const publish = require('../../action/publish.cjs');

function fixture(t, overrides = {}) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'promptdrift-publication-'));
  t.after(() => fs.rmSync(temp, {recursive: true, force: true}));
  const env = {
    PROMPTDRIFT_CREATE_ISSUE: 'true',
    PROMPTDRIFT_COMMENT: 'false',
    PROMPTDRIFT_MODE: 'monitor',
    PROMPTDRIFT_EXIT_CODE: '1',
    PROMPTDRIFT_SCOPE: 'a'.repeat(64),
    PROMPTDRIFT_REPORT: path.join(temp, 'report.json'),
    PROMPTDRIFT_SUMMARY: path.join(temp, 'summary.md'),
    GITHUB_SERVER_URL: 'https://github.com',
    GITHUB_RUN_ID: '123',
    ...overrides,
  };
  fs.writeFileSync(env.PROMPTDRIFT_REPORT, JSON.stringify({
    counts: {PASS: 0, WARN: 0, FAIL: 1, ERROR: 0},
    // Arbitrary CLI fields are never interpolated into publication text.
    provider: '@everyone', model: '<script>',
    tests: [{summary: 'SECRET raw response', evidence: ['SECRET']}],
  }));
  fs.writeFileSync(env.PROMPTDRIFT_SUMMARY, '## PromptDrift monitor\n\n| FAIL | 1 |\n');
  const calls = [];
  const warnings = [];
  const issuePages = [[]];
  const commentPages = [[]];
  const rest = {issues: {}};
  for (const method of ['listForRepo', 'listComments', 'create', 'update', 'createComment', 'updateComment']) {
    rest.issues[method] = async args => {
      calls.push({method, args});
      if (method === 'create') issuePages.at(-1).push({...args, number: 500, user: {type: 'Bot'}});
      if (method === 'createComment') commentPages.at(-1).push({...args, id: 501, user: {type: 'Bot'}});
      return {data: {}};
    };
  }
  const github = {
    rest,
    paginate: async (method, args) => {
      assert.equal(args.per_page, 100);
      if (method === rest.issues.listForRepo) {
        calls.push({method: 'paginateIssues', args});
        assert.equal(args.state, 'open');
        return issuePages.flat();
      }
      assert.equal(method, rest.issues.listComments);
      calls.push({method: 'paginateComments', args});
      return commentPages.flat();
    },
  };
  const context = {
    repo: {owner: 'owner', repo: 'repository'},
    eventName: 'schedule', payload: {},
  };
  const core = {warning: message => warnings.push(message)};
  return {env, github, context, core, calls, warnings, issuePages, commentPages};
}

test('opt-in failure creates one issue and later failures update it', async t => {
  const f = fixture(t);
  await publish(f);
  const created = f.calls.find(call => call.method === 'create');
  assert.ok(created);
  assert.match(created.args.body, /<!-- promptdrift-monitor:a{64} -->/);
  assert.match(created.args.body, /https:\/\/github.com\/owner\/repository\/actions\/runs\/123/);
  assert.doesNotMatch(created.args.body, /SECRET|@everyone|<script>/);
  await publish(f);
  assert.equal(f.calls.filter(call => call.method === 'create').length, 1);
  assert.equal(f.calls.filter(call => call.method === 'update').length, 1);
});

test('paginated issue lookup reuses a matching bot issue on the second page, not a PR or user forgery', async t => {
  const f = fixture(t);
  const body = `<!-- promptdrift-monitor:${f.env.PROMPTDRIFT_SCOPE} -->\nold`;
  f.issuePages[0] = [
    {number: 1, user: {type: 'User'}, body},
    {number: 2, user: {type: 'Bot'}, body, pull_request: {url: 'some-pr'}},
    ...Array.from({length: 98}, (_, i) => ({number: i + 10, user: {type: 'Bot'}, body: 'unrelated'})),
  ];
  f.issuePages.push([{number: 600, user: {type: 'Bot'}, body}]);
  await publish(f);
  assert.equal(f.calls.find(call => call.method === 'update').args.issue_number, 600);
  assert.equal(f.calls.filter(call => call.method === 'create').length, 0);
});

test('scopes cannot overwrite a different configuration issue', async t => {
  const f = fixture(t);
  f.issuePages[0].push({number: 1, user: {type: 'Bot'}, body: `<!-- promptdrift-monitor:${'b'.repeat(64)} -->`});
  await publish(f);
  assert.ok(f.calls.some(call => call.method === 'create'));
  f.env.PROMPTDRIFT_SCOPE = '<!-- injected --> @everyone';
  f.calls.length = 0;
  await publish(f);
  assert.deepEqual(f.calls, []);
});

for (const [name, changes, event] of [
  ['disabled', {PROMPTDRIFT_CREATE_ISSUE: 'false'}, 'schedule'],
  ['check mode', {PROMPTDRIFT_MODE: 'check'}, 'schedule'],
  ['healthy or changed valid', {PROMPTDRIFT_EXIT_CODE: '0'}, 'schedule'],
  ['configuration error', {PROMPTDRIFT_EXIT_CODE: '2'}, 'schedule'],
  ['privileged PR', {}, 'pull_request_target'],
  ['ordinary PR', {}, 'pull_request'],
  ['push', {}, 'push'],
]) {
  test(`issues skipped for ${name}`, async t => {
    const f = fixture(t, changes);
    f.context.eventName = event;
    await publish(f);
    assert.deepEqual(f.calls, []);
  });
}

test('manual provider failure envelope is alertable, invalid report is not', async t => {
  const f = fixture(t, {PROMPTDRIFT_EXIT_CODE: '3'});
  f.context.eventName = 'workflow_dispatch';
  fs.writeFileSync(f.env.PROMPTDRIFT_REPORT, JSON.stringify({error: {message: 'PRIVATE'}, exit_code: 3}));
  await publish(f);
  assert.ok(f.calls.some(call => call.method === 'create'));
  assert.doesNotMatch(f.calls.find(call => call.method === 'create').args.body, /PRIVATE/);
  f.calls.length = 0;
  fs.writeFileSync(f.env.PROMPTDRIFT_REPORT, JSON.stringify({error: {}, exit_code: 2}));
  await publish(f);
  assert.deepEqual(f.calls, []);
});

test('same-repository PR comment keeps legacy marker and deduplicates through pagination', async t => {
  const f = fixture(t, {PROMPTDRIFT_COMMENT: 'true'});
  f.context.eventName = 'pull_request';
  f.context.payload.pull_request = {number: 8, head: {repo: {fork: false, full_name: 'owner/repository'}}};
  await publish(f);
  assert.equal(f.calls.find(call => call.method === 'createComment').args.issue_number, 8);
  assert.match(f.calls.find(call => call.method === 'createComment').args.body, /^<!-- promptdrift-report -->/);
  f.commentPages.push(f.commentPages[0].splice(0));
  await publish(f);
  assert.equal(f.calls.filter(call => call.method === 'createComment').length, 1);
  assert.equal(f.calls.find(call => call.method === 'updateComment').args.comment_id, 501);
  assert.ok(!f.calls.some(call => call.method === 'create'));
});

test('fork and mismatched head repo never receive PR comments', async t => {
  const f = fixture(t, {PROMPTDRIFT_COMMENT: 'true'});
  f.context.eventName = 'pull_request';
  for (const repo of [{fork: true, full_name: 'outsider/repository'}, {fork: false, full_name: 'outsider/repository'}]) {
    f.context.payload.pull_request = {number: 8, head: {repo}};
    await publish(f);
  }
  assert.deepEqual(f.calls, []);
});

test('permission failures are best-effort and do not leak API response or token', async t => {
  const f = fixture(t);
  f.github.paginate = async () => { throw new Error('Authorization: token PRIVATE'); };
  await publish(f);
  assert.equal(f.warnings.length, 1);
  assert.doesNotMatch(f.warnings[0], /PRIVATE|Authorization/);
});

test('malformed JSON and unsafe workflow URLs do not publish', async t => {
  const f = fixture(t, {GITHUB_SERVER_URL: 'https://user:PRIVATE@github.com'});
  await publish(f);
  assert.deepEqual(f.calls, []);
  assert.equal(f.warnings.length, 1);
  fs.writeFileSync(f.env.PROMPTDRIFT_REPORT, 'PRIVATE non-JSON');
  await publish(f);
  assert.deepEqual(f.calls, []);
  assert.equal(f.warnings.length, 2);
  assert.doesNotMatch(f.warnings.join(''), /PRIVATE/);
});
