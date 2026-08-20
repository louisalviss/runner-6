import fs from 'node:fs';
import crypto from 'node:crypto';

const [,, inputPath, publicKeyPath, outputPath, runId=''] = process.argv;
if (!inputPath || !publicKeyPath || !outputPath) {
  throw new Error('usage: node dsh-mirror-encrypt.mjs INPUT PUBLIC_KEY OUTPUT [RUN_ID]');
}

const plaintext = fs.readFileSync(inputPath);
const publicKey = crypto.createPublicKey(fs.readFileSync(publicKeyPath, 'utf8'));
const aesKey = crypto.randomBytes(32);
const iv = crypto.randomBytes(12);
const cipher = crypto.createCipheriv('aes-256-gcm', aesKey, iv);
const body = Buffer.concat([cipher.update(plaintext), cipher.final()]);
const tag = cipher.getAuthTag();
const wrappedKey = crypto.publicEncrypt({
  key: publicKey,
  padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
  oaepHash: 'sha256'
}, aesKey);

const out = {
  v: 1,
  alg: 'RSA-OAEP-256+A256GCM',
  kid: 'runner6-chatgpt-mirror-v1',
  run_id: String(runId || ''),
  ek: wrappedKey.toString('base64url'),
  iv: iv.toString('base64url'),
  ct: Buffer.concat([body, tag]).toString('base64url')
};
fs.writeFileSync(outputPath, JSON.stringify(out));
aesKey.fill(0);
