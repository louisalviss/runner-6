import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';

const [,, planPath, resultPath, manifestPath] = process.argv;
if (!planPath || !resultPath || !manifestPath) throw new Error('usage: dsh-media-exec.mjs <plan.json> <result.json> <manifest.json>');

const root = path.resolve(process.cwd());
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
const MAX_STEPS = 8;
const MAX_TIMEOUT = 600;

function safeRel(p) {
  if (typeof p !== 'string' || !p || p.length > 240) throw new Error('invalid path');
  if (path.isAbsolute(p) || p.includes('\0')) throw new Error('absolute/NUL path denied');
  const resolved = path.resolve(root, p);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) throw new Error('path escapes workspace');
  return { rel: path.relative(root, resolved), abs: resolved };
}

function validateArgs(args) {
  if (!Array.isArray(args) || args.length > 80) throw new Error('invalid args');
  for (const a of args) {
    if (typeof a !== 'string' || a.length > 2048 || a.includes('\0')) throw new Error('invalid arg');
    if (/^https?:\/\//i.test(a)) throw new Error('network URL must use download op');
    if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(a) && !/^color=|^testsrc=|^anullsrc=|^sine=/.test(a)) throw new Error('protocol-style arg denied');
    if (path.isAbsolute(a)) throw new Error('absolute path arg denied');
  }
}

async function runProc(bin, args, timeoutSeconds) {
  validateArgs(args);
  return await new Promise((resolve, reject) => {
    const out = [], err = [];
    const child = spawn(bin, args, {
      cwd: root,
      env: { PATH: process.env.PATH || '/usr/bin:/bin', HOME: root, TMPDIR: process.env.RUNNER_TEMP || '/tmp' },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let killed = false;
    const timer = setTimeout(() => { killed = true; child.kill('SIGKILL'); }, timeoutSeconds * 1000);
    child.stdout.on('data', d => { if (Buffer.concat(out).length < 200000) out.push(d); });
    child.stderr.on('data', d => { if (Buffer.concat(err).length < 200000) err.push(d); });
    child.on('error', reject);
    child.on('close', code => {
      clearTimeout(timer);
      resolve({ code: code ?? 1, timed_out: killed, stdout: Buffer.concat(out).toString('utf8').slice(0, 200000), stderr: Buffer.concat(err).toString('utf8').slice(0, 200000) });
    });
  });
}

async function download(step, timeoutSeconds) {
  if (typeof step.url !== 'string') throw new Error('download url missing');
  const u = new URL(step.url);
  if (u.protocol !== 'https:') throw new Error('download requires https');
  const dst = safeRel(step.output);
  fs.mkdirSync(path.dirname(dst.abs), { recursive: true });
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutSeconds * 1000);
  try {
    const r = await fetch(u, { redirect: 'follow', signal: ctrl.signal, headers: { 'user-agent': 'Runner6-DSH-Media/1.0' } });
    if (!r.ok || !r.body) throw new Error(`download HTTP ${r.status}`);
    const len = Number(r.headers.get('content-length') || 0);
    if (len > 1024 * 1024 * 1024) throw new Error('download exceeds 1 GiB');
    await pipeline(Readable.fromWeb(r.body), fs.createWriteStream(dst.abs, { mode: 0o600 }));
    const size = fs.statSync(dst.abs).size;
    if (size > 1024 * 1024 * 1024) throw new Error('download exceeds 1 GiB');
    return { code: 0, timed_out: false, stdout: `downloaded ${size} bytes`, stderr: '' };
  } finally { clearTimeout(timer); }
}

if (plan?.version !== 1) throw new Error('plan version must be 1');
if (plan?.status !== 'ready') {
  const result = { status: 'cannot_execute', reason: String(plan?.reason || 'planner declined'), steps: [] };
  fs.writeFileSync(resultPath, JSON.stringify(result));
  fs.writeFileSync(manifestPath, JSON.stringify({ count: 0, files: [] }));
  process.exit(4);
}
if (!Array.isArray(plan.steps) || plan.steps.length < 1 || plan.steps.length > MAX_STEPS) throw new Error('invalid step count');
const timeoutSeconds = Math.max(5, Math.min(MAX_TIMEOUT, Number(plan.timeout_seconds || 180)));
const stepResults = [];
let failed = false;
for (let i = 0; i < plan.steps.length; i++) {
  const step = plan.steps[i] || {};
  let r;
  try {
    if (step.op === 'download') r = await download(step, Math.min(timeoutSeconds, 180));
    else if (step.op === 'ffmpeg') r = await runProc('ffmpeg', ['-nostdin','-hide_banner','-y', ...(step.args || [])], timeoutSeconds);
    else if (step.op === 'ffprobe') r = await runProc('ffprobe', ['-v','error', ...(step.args || [])], Math.min(timeoutSeconds, 120));
    else throw new Error(`unsupported op: ${step.op}`);
  } catch (e) {
    r = { code: 1, timed_out: false, stdout: '', stderr: String(e?.message || e) };
  }
  stepResults.push({ index: i, op: step.op, ...r });
  if (r.code !== 0 || r.timed_out) { failed = true; break; }
}

const outputs = Array.isArray(plan.outputs) ? plan.outputs : [];
const files = [];
for (const p of outputs) {
  try {
    const x = safeRel(p);
    if (fs.existsSync(x.abs) && fs.statSync(x.abs).isFile()) files.push({ path: x.rel, size: fs.statSync(x.abs).size });
  } catch {}
}
const result = { status: failed ? 'exec_error' : 'success', step_results: stepResults, outputs: files };
fs.writeFileSync(resultPath, JSON.stringify(result));
fs.writeFileSync(manifestPath, JSON.stringify({ count: files.length, files }));
process.exit(failed ? 5 : 0);
