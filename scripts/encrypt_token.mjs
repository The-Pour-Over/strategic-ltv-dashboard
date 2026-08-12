// Encrypt the Meta access token with Nicole's dashboard password so the
// public dashboard can ship it safely: PBKDF2-SHA256 (1M iterations) →
// AES-256-GCM. Output goes to client/public/data/meta_token.enc.json; the
// page decrypts it in-browser (WebCrypto) when she enters the password.
//
// Rerun whenever the token rotates (META_ADS_ACCESS_TOKEN in
// ~/.secrets/meta-ads.env; password in ~/.secrets/dashboard-pass.txt),
// then rebuild + republish both dashboard surfaces.
//
// Usage: node scripts/encrypt_token.mjs
import { webcrypto as crypto } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const env = readFileSync(join(homedir(), ".secrets/meta-ads.env"), "utf8");
const token = env.match(/^META_ADS_ACCESS_TOKEN=(.+)$/m)[1].trim().replace(/^"|"$/g, "");
const password = readFileSync(join(homedir(), ".secrets/dashboard-pass.txt"), "utf8").trim();

const iter = 1_000_000;
const salt = crypto.getRandomValues(new Uint8Array(16));
const iv = crypto.getRandomValues(new Uint8Array(12));
const enc = new TextEncoder();

const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
const key = await crypto.subtle.deriveKey(
  { name: "PBKDF2", salt, iterations: iter, hash: "SHA-256" },
  keyMaterial,
  { name: "AES-GCM", length: 256 },
  false,
  ["encrypt"],
);
const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, enc.encode(token)));

const b64 = (u) => Buffer.from(u).toString("base64");
const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "client/public/data");
const out = join(DATA, "meta_token.enc.json");
writeFileSync(out, JSON.stringify({ v: 1, iter, salt: b64(salt), iv: b64(iv), ct: b64(ct) }));
console.log(`wrote ${out} (${ct.length} byte ciphertext, ${iter} PBKDF2 iterations)`);

// Decision-sync GitHub token (fine-grained, contents:write on ONLY the
// strategic-ltv-dashboard repo — never a broad token). Optional: skipped
// when the secret file doesn't exist yet.
try {
  const gh = readFileSync(join(homedir(), ".secrets/dashboard-gh-token.txt"), "utf8").trim();
  const salt2 = crypto.getRandomValues(new Uint8Array(16));
  const iv2 = crypto.getRandomValues(new Uint8Array(12));
  const key2 = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt2, iterations: iter, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"],
  );
  const ct2 = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv2 }, key2, enc.encode(gh)));
  const out2 = join(DATA, "gh_sync.enc.json");
  writeFileSync(out2, JSON.stringify({ v: 1, iter, salt: b64(salt2), iv: b64(iv2), ct: b64(ct2) }));
  console.log(`wrote ${out2} (decision sync enabled)`);
} catch {
  console.log("no ~/.secrets/dashboard-gh-token.txt — decision sync blob skipped");
}
