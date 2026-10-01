// Loaded by actions/github-script, and exercised with an in-memory GitHub API in tests.
const fs = require('node:fs');

function runLink(context, env) {
  const server = new URL(env.GITHUB_SERVER_URL || 'https://github.com');
  if (server.protocol !== 'https:' || server.username || server.password || !/^\d+$/.test(env.GITHUB_RUN_ID || '')) {
    throw new Error('Invalid workflow run URL');
  }
  return `${server.origin}/${encodeURIComponent(context.repo.owner)}/${encodeURIComponent(context.repo.repo)}/actions/runs/${env.GITHUB_RUN_ID}`;
}

async function publish({github, context, core, env = process.env}) {
  const event = context.eventName;
  // Never use privileged PR events, or a token from a fork PR, for either publication path.
  if (event === 'pull_request_target') return;
  const pr = context.payload.pull_request;
  const commentAllowed = env.PROMPTDRIFT_COMMENT === 'true'
    && event === 'pull_request'
    && pr?.head?.repo?.fork === false
    && pr.head.repo.full_name === `${context.repo.owner}/${context.repo.repo}`;
  const issueAllowed = env.PROMPTDRIFT_CREATE_ISSUE === 'true'
    && env.PROMPTDRIFT_MODE === 'monitor'
    && ['schedule', 'workflow_dispatch'].includes(event)
    && ['1', '3'].includes(env.PROMPTDRIFT_EXIT_CODE);
  if (!commentAllowed && !issueAllowed) return;

  try {
    const data = JSON.parse(fs.readFileSync(env.PROMPTDRIFT_REPORT, 'utf8'));
    const summary = fs.readFileSync(env.PROMPTDRIFT_SUMMARY, 'utf8');
    const {owner, repo} = context.repo;
    const link = `[Workflow run](${runLink(context, env)})`;
    if (commentAllowed) {
      const marker = '<!-- promptdrift-report -->';
      const body = `${marker}\n${summary}\n${link}\n`;
      const issue_number = pr.number;
      const comments = await github.paginate(github.rest.issues.listComments, {
        owner, repo, issue_number, per_page: 100,
      });
      const existing = comments.find(comment => comment.user?.type === 'Bot'
        && typeof comment.body === 'string' && comment.body.startsWith(marker));
      if (existing) {
        await github.rest.issues.updateComment({owner, repo, comment_id: existing.id, body});
      } else {
        await github.rest.issues.createComment({owner, repo, issue_number, body});
      }
    }
    if (issueAllowed) {
      const code = Number(env.PROMPTDRIFT_EXIT_CODE);
      // Config/report errors are not claims of model drift. A provider error envelope is alertable.
      if (data.error
        ? data.error.type !== 'cli_error' || data.exit_code !== 3
        : !(data.counts?.FAIL > 0 || data.counts?.ERROR > 0)) return;
      if (![1, 3].includes(code) || !/^[a-f0-9]{64}$/.test(env.PROMPTDRIFT_SCOPE || '')) return;
      const scope = env.PROMPTDRIFT_SCOPE;
      const marker = `<!-- promptdrift-monitor:${scope} -->`;
      const body = `${marker}\n${summary}\n${link}\n\nThis issue tracks contract/provider failures, not proof of model drift. Repeated failures update this issue. Close it after investigation; healthy runs do not auto-close issues.\n`;
      const issues = await github.paginate(github.rest.issues.listForRepo, {
        owner, repo, state: 'open', per_page: 100,
      });
      const existing = issues.find(issue => !issue.pull_request && issue.user?.type === 'Bot'
        && typeof issue.body === 'string' && issue.body.startsWith(marker));
      if (existing) {
        await github.rest.issues.update({owner, repo, issue_number: existing.number, body});
      } else {
        await github.rest.issues.create({
          owner, repo, title: `PromptDrift monitor failure (${scope.slice(0, 12)})`, body,
        });
      }
    }
  } catch {
    // API/parse errors must not leak response bodies or hide the original CLI result.
    core.warning('PromptDrift GitHub publication failed. Check token permissions and report availability.');
  }
}

module.exports = publish;
