function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToB64(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

async function deriveKey(passphrase) {
  const material = new TextEncoder().encode(passphrase);
  const hash = await crypto.subtle.digest("SHA-256", material);
  return crypto.subtle.importKey("raw", hash, { name: "AES-GCM" }, false, [
    "encrypt",
    "decrypt",
  ]);
}

export async function decryptCloudBlob(blob, passphrase) {
  if (!blob || blob.v !== 1) throw new Error("云端数据格式不正确");
  const key = await deriveKey(passphrase);
  const nonce = b64ToBytes(blob.nonce);
  const data = b64ToBytes(blob.ciphertext);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, data);
  return JSON.parse(new TextDecoder().decode(plain));
}

export async function encryptCloudPayload(payload, passphrase) {
  const key = await deriveKey(passphrase);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const plain = new TextEncoder().encode(JSON.stringify(payload));
  const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, plain);
  return {
    v: 1,
    alg: "AES-GCM",
    kdf: "SHA-256",
    nonce: bytesToB64(nonce),
    ciphertext: bytesToB64(new Uint8Array(cipher)),
  };
}
