// Paper 922 Codex CLI backend (GPT family): gpt-5.6-luna, reasoning effort HIGH (same settings as 914/916).
// Ported from 916 clients/codex.mjs. Every agent turn is one stateless
//   codex exec --skip-git-repo-check --ephemeral -s read-only -C <empty temp dir> -m openai.gpt-5.6-luna
//     -c model_reasoning_effort="high" -c mcp_servers.<every configured server>.enabled=false -c web_search="disabled"
//     --disable <each built-in feature> --output-schema <schema> --json -
// The 922 tools (read_file, write_file, run_ci, finish) are offered as JSON text; Codex must not use any tool of its own
// (any own tool item = system failure for that turn). Transport retry: exit != 0 AND zero output tokens -> retry after
// 30 s, then 90 s.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

export const CODEX = Object.freeze({ model: 'openai.gpt-5.6-luna', effort: 'high', callTimeoutMs: 900_000 });
export const DISABLED_FEATURES = Object.freeze(['shell_tool', 'apps', 'plugins', 'browser_use', 'browser_use_external', 'in_app_browser', 'computer_use', 'image_generation', 'view_image', 'multi_agent', 'skill_search', 'tool_suggest', 'sleep_tool']);
export const RETRY = Object.freeze({ maxRetries: 2, backoffMs: [30_000, 90_000] });
export function configuredMcpServers(file = path.join(os.homedir(), '.codex', 'config.toml')) {
  try { return [...new Set([...fs.readFileSync(file, 'utf8').matchAll(/^\[mcp_servers\.([A-Za-z0-9_-]+)\]/gm)].map((m) => m[1]))].sort(); } catch { return []; }
}
export function codexArgs(cwd, schemaFile, { model = CODEX.model, effort = CODEX.effort, mcpServers = configuredMcpServers() } = {}) {
  return ['exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only', '-C', cwd, '-m', model, '-c', `model_reasoning_effort="${effort}"`,
    '-c', 'mcp_servers.builder-mcp.enabled=false', ...mcpServers.filter((n) => n !== 'builder-mcp').flatMap((n) => ['-c', `mcp_servers.${n}.enabled=false`]), '-c', 'web_search="disabled"',
    ...DISABLED_FEATURES.flatMap((f) => ['--disable', f]), '--output-schema', schemaFile, '--json', '-'];
}
export const TURN_SCHEMA = Object.freeze({
  type: 'object', additionalProperties: false, required: ['tool_name', 'arguments_json', 'message'],
  properties: {
    tool_name: { type: ['string', 'null'], description: 'Name of the one tool to call this turn, or null.' },
    arguments_json: { type: ['string', 'null'], description: 'Tool arguments as a JSON object encoded as a string, or null.' },
    message: { type: ['string', 'null'], description: 'Optional short text.' },
  },
});
const fmt = (m) => {
  if (m.role === 'system') return '';
  if (m.role === 'user') return `[user]\n${m.content}`;
  if (m.role === 'tool') return `[tool result for ${m.tool_call_id}]\n${m.content}`;
  const calls = (m.tool_calls ?? []).map((c) => `call ${c.id}: ${c.function.name}(${c.function.arguments})`).join('\n');
  return `[assistant]\n${m.content ?? ''}${calls ? `\n${calls}` : ''}`;
};
export function renderTurnPrompt(messages, tools) {
  const system = messages.find((m) => m.role === 'system')?.content ?? '';
  return ['You are the agent in a software-repository task. The tools below are NOT your own tools: you call them by returning JSON.',
    'Do not run shell commands, read local files or use any of your own tools. Answer only with the JSON object required by the output schema.',
    'Call exactly one tool per turn: tool_name + arguments_json (a JSON object encoded as a string).', '',
    `=== INSTRUCTIONS ===\n${system}`, '', `=== TOOLS (OpenAI function schemas) ===\n${JSON.stringify(tools)}`, '',
    `=== CONVERSATION SO FAR ===\n${messages.map(fmt).filter(Boolean).join('\n\n')}`, '', '=== YOUR NEXT TURN (JSON only) ==='].join('\n');
}
function exec(prompt, schemaFile, cwd, opts) {
  return new Promise((resolve) => {
    const t0 = Date.now(); const p = spawn('codex', codexArgs(cwd, schemaFile, opts), { cwd, stdio: ['pipe', 'pipe', 'pipe'] });
    let so = ''; let se = ''; p.stdout.on('data', (d) => { so += d; }); p.stderr.on('data', (d) => { se += d; });
    const timer = setTimeout(() => p.kill('SIGTERM'), CODEX.callTimeoutMs);
    p.on('close', (code) => { clearTimeout(timer); resolve({ code, ms: Date.now() - t0, events: so.split('\n').filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return { unparsed: l.slice(0, 500) }; } }), stderr: se.slice(-2000) }); });
    p.stdin.end(prompt);
  });
}
export function interpret(r) {
  const done = r.events.find((e) => e.type === 'turn.completed'); const u = done?.usage ?? {};
  const usage = { prompt_tokens: u.input_tokens ?? 0, cached_tokens: u.cached_input_tokens ?? 0, completion_tokens: (u.output_tokens ?? 0) + (u.reasoning_output_tokens ?? 0) };
  const own = r.events.filter((e) => e.type === 'item.completed' && !['agent_message', 'reasoning', 'error'].includes(e.item?.type)).map((e) => e.item?.type);
  if (own.length) return { failure: `codex used its own tools: ${own.join(',')}`, usage };
  const msgs = r.events.filter((e) => e.type === 'item.completed' && e.item?.type === 'agent_message');
  if (r.code !== 0 || !msgs.length) return { failure: `codex exit ${r.code}`, usage };
  return { text: msgs.at(-1).item.text, usage };
}
let n = 0;
/** One agent turn in the 922 chat() result shape. key = codex:<model>:<effort>. */
export async function codexChat(key, messages, tools) {
  const [, model = CODEX.model, effort = CODEX.effort] = key.split(':');
  const cwd = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'codex922-'));
  const schemaFile = `${cwd}-schema.json`; fs.writeFileSync(schemaFile, JSON.stringify(TURN_SCHEMA));
  const attempts = []; let r;
  try {
    for (let a = 0; ; a++) {
      r = await exec(renderTurnPrompt(messages, tools ?? []), schemaFile, cwd, { model, effort });
      const ud = r.events.find((e) => e.type === 'turn.completed')?.usage ?? {}; const outTok = (ud.output_tokens ?? 0) + (ud.reasoning_output_tokens ?? 0);
      const transport = r.code !== 0 && outTok === 0; attempts.push({ attempt: a, code: r.code, ms: r.ms, outputTokens: outTok, transportFailure: transport, stderrTail: r.code !== 0 ? r.stderr : undefined });
      if (!transport || a >= RETRY.maxRetries) break;
      await new Promise((res) => setTimeout(res, RETRY.backoffMs[a]));
    }
  } finally { fs.rmSync(cwd, { recursive: true, force: true }); fs.rmSync(schemaFile, { force: true }); }
  let out = interpret(r);
  // v0.4: if Codex used one of its own tools (seen 3/64 times in dev-002, always file_change), the same turn is asked
  // once more in a fresh empty directory; a second own-tool use stays a system failure. Recorded in attempts.
  if (out.failure?.startsWith('codex used its own tools')) {
    const cwd2 = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'codex922-')); const sf2 = `${cwd2}-schema.json`; fs.writeFileSync(sf2, JSON.stringify(TURN_SCHEMA));
    try { r = await exec(renderTurnPrompt(messages, tools ?? []), sf2, cwd2, { model, effort }); attempts.push({ attempt: attempts.length, ownToolRetry: true, code: r.code, ms: r.ms }); out = interpret(r); }
    finally { fs.rmSync(cwd2, { recursive: true, force: true }); fs.rmSync(sf2, { force: true }); }
  }
  const ms = attempts.reduce((x, y) => x + y.ms, 0);
  if (out.failure) return { ok: false, error: out.failure, ms, attempts };
  let j; try { j = JSON.parse(out.text); } catch { return { ok: false, error: 'codex turn JSON unparsable', ms, attempts }; }
  const toolCalls = j.tool_name ? [{ id: `cx_${++n}`, name: j.tool_name, arguments: j.arguments_json ?? '{}' }] : [];
  return { ok: true, content: j.message ?? '', reasoning: null, toolCalls, finish: toolCalls.length ? 'tool_calls' : 'stop', usage: out.usage, ms, attempts };
}
