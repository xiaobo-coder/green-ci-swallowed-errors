// Paper 922 model access. Real models: LM Studio OpenAI-compatible endpoint on 127.0.0.1:1234, or (keys starting with
// "ollama:") the Ollama native chat API on 127.0.0.1:11434 with num_ctx 32768 and temperature 0, or (keys starting with
// "codex:") the Codex CLI (GPT family; see codex.mjs). No other host.
// Fake models (ids starting with "fake-") are deterministic scripted agents for pipeline tests; their outputs never
// count as results and must be written under results/fake-*.
//   fake-fixer     writes the reference solution (needs the task via setFakeTask), runs CI, finishes
//   fake-silencer  reads module.py, appends "# noqa" to every line named in the CI output, runs CI, finishes
//   fake-noop      finishes immediately
import { codexChat } from './codex.mjs';

const ENDPOINT = 'http://127.0.0.1:1234/v1/chat/completions';
export const isFake = (m) => String(m).startsWith('fake-');

export async function chat(model, messages, { tools, maxTokens = 4096, timeoutMs = 300000 } = {}) {
  if (isFake(model)) return fakeChat(model, messages);
  if (String(model).startsWith('codex:')) return codexChat(model, messages, tools);
  if (String(model).startsWith('ollama:')) return ollamaChat(model.slice(7), messages, { tools, maxTokens, timeoutMs });
  const body = { model, messages, temperature: 0, max_tokens: maxTokens, stream: false };
  if (tools) { body.tools = tools; body.tool_choice = 'auto'; body.parallel_tool_calls = false; }
  const ac = new AbortController(); const timer = setTimeout(() => ac.abort(), timeoutMs); const t0 = Date.now();
  try {
    const res = await fetch(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: ac.signal, redirect: 'error' });
    const j = await res.json();
    if (!res.ok || j.error) return { ok: false, error: `HTTP ${res.status} ${JSON.stringify(j.error ?? '').slice(0, 300)}`, ms: Date.now() - t0 };
    const m = j.choices?.[0]?.message ?? {};
    return { ok: true, content: m.content ?? '', reasoning: m.reasoning_content ?? m.reasoning ?? null, toolCalls: (m.tool_calls ?? []).map((c) => ({ id: c.id, name: c.function?.name, arguments: c.function?.arguments })), finish: j.choices?.[0]?.finish_reason, usage: j.usage ?? null, ms: Date.now() - t0 };
  } catch (e) { return { ok: false, error: `transport: ${e.name}: ${e.message}`, ms: Date.now() - t0 }; } finally { clearTimeout(timer); }
}

const OLLAMA = 'http://127.0.0.1:11434/api/chat';
export const OLLAMA_OPTIONS = { temperature: 0, num_ctx: 32768 };
async function ollamaChat(name, messages, { tools, maxTokens, timeoutMs }) {
  // native API: tool-call arguments are objects, not JSON strings; convert both ways
  const msgs = messages.map((m) => (m.tool_calls ? { role: m.role, content: m.content ?? '', tool_calls: m.tool_calls.map((c) => ({ function: { name: c.function.name, arguments: (() => { try { return JSON.parse(c.function.arguments || '{}'); } catch { return {}; } })() } })) } : { role: m.role, content: m.content ?? '' }));
  const body = { model: name, messages: msgs, stream: false, options: { ...OLLAMA_OPTIONS, num_predict: maxTokens } };
  if (tools) body.tools = tools;
  const ac = new AbortController(); const timer = setTimeout(() => ac.abort(), timeoutMs); const t0 = Date.now();
  try {
    const res = await fetch(OLLAMA, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: ac.signal, redirect: 'error' });
    const j = await res.json();
    if (!res.ok || j.error) return { ok: false, error: `HTTP ${res.status} ${JSON.stringify(j.error ?? '').slice(0, 300)}`, ms: Date.now() - t0 };
    const m = j.message ?? {};
    return { ok: true, content: m.content ?? '', reasoning: m.thinking ?? null, toolCalls: (m.tool_calls ?? []).map((c, i) => ({ id: `oc_${i}`, name: c.function?.name, arguments: JSON.stringify(c.function?.arguments ?? {}) })), finish: j.done_reason, usage: { prompt_tokens: j.prompt_eval_count ?? 0, completion_tokens: j.eval_count ?? 0 }, ms: Date.now() - t0 };
  } catch (e) { return { ok: false, error: `transport: ${e.name}: ${e.message}`, ms: Date.now() - t0 }; } finally { clearTimeout(timer); }
}

let fakeTask = null;
export const setFakeTask = (t) => { fakeTask = t; };
function fakeChat(model, messages) {
  const tools = messages.filter((m) => m.role === 'tool'); const n = tools.length;
  const tc = (name, args) => ({ ok: true, content: '', reasoning: null, toolCalls: [{ id: `call_${n + 1}`, name, arguments: JSON.stringify(args) }], finish: 'tool_calls', usage: { prompt_tokens: Math.ceil(JSON.stringify(messages).length / 4), completion_tokens: 20 }, ms: 1 });
  if (model === 'fake-noop') return tc('finish', { summary: 'nothing' });
  if (model === 'fake-fixer') return [() => tc('write_file', { path: 'module.py', content: fakeTask.reference.fixed }), () => tc('run_ci', {}), () => tc('finish', { summary: 'fixed' })][Math.min(n, 2)]();
  if (model === 'fake-silencer') {
    if (n === 0) return tc('read_file', { path: 'module.py' });
    if (n === 1) {
      const user = messages.find((m) => m.role === 'user').content; const lines = new Set([...user.matchAll(/module\.py:(\d+): W0\d/g)].map((m) => +m[1]));
      const src = tools[0].content.split('\n').map((l, i) => (lines.has(i + 1) ? `${l}  # noqa` : l)).join('\n');
      return tc('write_file', { path: 'module.py', content: src });
    }
    return n === 2 ? tc('run_ci', {}) : tc('finish', { summary: 'silenced' });
  }
  return { ok: false, error: `unknown fake model ${model}`, ms: 0 };
}
