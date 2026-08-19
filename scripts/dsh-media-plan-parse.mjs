import fs from 'node:fs';
const [,, inPath, outPath] = process.argv;
if (!inPath || !outPath) throw new Error('usage: dsh-media-plan-parse.mjs <raw> <out>');
let s = fs.readFileSync(inPath,'utf8').trim();
if (s.startsWith('```')) {
  s = s.replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'').trim();
}
let obj;
try { obj = JSON.parse(s); }
catch {
  const a=s.indexOf('{'), b=s.lastIndexOf('}');
  if (a<0 || b<=a) throw new Error('planner did not return JSON');
  obj=JSON.parse(s.slice(a,b+1));
}
if (!obj || obj.version!==1 || !['ready','cannot_execute'].includes(obj.status)) throw new Error('invalid plan envelope');
if (obj.status==='ready') {
  if (!Array.isArray(obj.steps) || obj.steps.length<1 || obj.steps.length>8) throw new Error('invalid plan steps');
  for (const step of obj.steps) {
    if (!step || !['download','ffmpeg','ffprobe'].includes(step.op)) throw new Error('unsupported plan op');
  }
  if (!Array.isArray(obj.outputs)) obj.outputs=[];
}
fs.writeFileSync(outPath, JSON.stringify(obj));
