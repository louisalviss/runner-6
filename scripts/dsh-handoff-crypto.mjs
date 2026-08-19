import fs from 'node:fs';
import crypto from 'node:crypto';
import { pipeline } from 'node:stream/promises';

const [,, cmd, ...args] = process.argv;
const b64u = b => Buffer.from(b).toString('base64url');

if (cmd === 'decrypt-envelope') {
  const [payloadPath, taskPath, keyPath, clientPath] = args;
  const raw = fs.readFileSync(payloadPath, 'utf8').trim();
  const p = JSON.parse(Buffer.from(raw, 'base64url').toString('utf8'));
  if (p.v !== 1 || !p.client_id || !p.ek || !p.iv || !p.ct) throw new Error('invalid envelope');
  if (!/^[A-Za-z0-9_-]{12,80}$/.test(p.client_id)) throw new Error('invalid client id');
  const priv = process.env.DSH_CHAT_PRIVATE_KEY_B64;
  if (!priv) throw new Error('missing private key');
  const privateKey = crypto.createPrivateKey({key: Buffer.from(priv, 'base64'), format:'der', type:'pkcs8'});
  const aesKey = crypto.privateDecrypt({key:privateKey,padding:crypto.constants.RSA_PKCS1_OAEP_PADDING,oaepHash:'sha256'},Buffer.from(p.ek,'base64url'));
  const full = Buffer.from(p.ct,'base64url');
  const tag = full.subarray(full.length-16), body = full.subarray(0,full.length-16);
  const dec = crypto.createDecipheriv('aes-256-gcm', aesKey, Buffer.from(p.iv,'base64url'));
  dec.setAuthTag(tag);
  const task = Buffer.concat([dec.update(body),dec.final()]).toString('utf8');
  if (!task.trim()) throw new Error('empty task');
  fs.writeFileSync(taskPath,task,{mode:0o600});
  fs.writeFileSync(keyPath,b64u(aesKey),{mode:0o600});
  fs.writeFileSync(clientPath,p.client_id,{mode:0o600});
} else if (cmd === 'encrypt-json') {
  const [jsonPath,keyPath,outPath,clientId,runId] = args;
  const key = Buffer.from(fs.readFileSync(keyPath,'utf8').trim(),'base64url');
  const iv = crypto.randomBytes(12);
  const enc = crypto.createCipheriv('aes-256-gcm',key,iv);
  const body = Buffer.concat([enc.update(fs.readFileSync(jsonPath)),enc.final()]);
  const packed = {v:1,client_id:clientId,run_id:runId,iv:b64u(iv),ct:b64u(Buffer.concat([body,enc.getAuthTag()]))};
  fs.writeFileSync(outPath,JSON.stringify(packed));
} else if (cmd === 'encrypt-file') {
  const [inPath,keyPath,outPath] = args;
  const key = Buffer.from(fs.readFileSync(keyPath,'utf8').trim(),'base64url');
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm',key,iv);
  const out = fs.createWriteStream(outPath,{mode:0o600});
  out.write(Buffer.from('DSHA1'));
  out.write(iv);
  await pipeline(fs.createReadStream(inPath),cipher,out,{end:false});
  out.write(cipher.getAuthTag());
  out.end();
  await new Promise((resolve,reject)=>{out.on('finish',resolve);out.on('error',reject)});
} else {
  throw new Error(`unknown command: ${cmd}`);
}
