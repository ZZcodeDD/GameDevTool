#!/usr/bin/env node
/**
 * 将 data/tasks.json 加密写入 data/tasks.cloud.json
 * 口令从环境变量 RICI_PASSPHRASE 或 /cursor/stores/self/planner/secrets.json 读取
 */
import { createHash, randomBytes, createCipheriv } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = __dirname; // planner/
const tasksPath = join(root, "data", "tasks.json");
const cloudPath = join(root, "data", "tasks.cloud.json");

function loadPassphrase() {
  if (process.env.RICI_PASSPHRASE) return process.env.RICI_PASSPHRASE;
  const secretsPath = "/cursor/stores/self/planner/secrets.json";
  if (existsSync(secretsPath)) {
    return JSON.parse(readFileSync(secretsPath, "utf8")).passphrase;
  }
  throw new Error("缺少口令：请设置 RICI_PASSPHRASE");
}

function encrypt(plainText, passphrase) {
  const key = createHash("sha256").update(passphrase, "utf8").digest();
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  const ciphertext = Buffer.concat([cipher.update(plainText, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    v: 1,
    alg: "AES-GCM",
    kdf: "SHA-256",
    nonce: nonce.toString("base64"),
    ciphertext: Buffer.concat([ciphertext, tag]).toString("base64"),
  };
}

const passphrase = loadPassphrase();
const tasks = JSON.parse(readFileSync(tasksPath, "utf8"));
tasks.updatedAt = new Date().toISOString();
writeFileSync(tasksPath, JSON.stringify(tasks, null, 2) + "\n", "utf8");
const blob = encrypt(JSON.stringify(tasks), passphrase);
writeFileSync(cloudPath, JSON.stringify(blob, null, 2) + "\n", "utf8");
console.log(`已同步 ${tasks.items?.length ?? 0} 条事项 → data/tasks.cloud.json`);
