// Set the demo teammates' numbers in ../.env and enroll each on the Photon shared line.
// Usage: node --env-file=../.env team.mjs A=+1XXXXXXXXXX B=+1XXXXXXXXXX C=+1XXXXXXXXXX
//   A = pre-trip driver + teen's parent, B = en-route driver (in-app alert only), C = Margaret's relative
// Numbers are masked in the output; the project secret is never printed.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENV_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".env");
const E164 = /^\+[1-9]\d{6,14}$/;
const id = process.env.SPECTRUM_PROJECT_ID || process.env.PROJECT_ID;
const secret = process.env.SPECTRUM_PROJECT_SECRET || process.env.PROJECT_SECRET;
const mask = (p) => p.slice(0, -4).replace(/\d/g, "•") + p.slice(-4);

function parseArgs(argv) {
  const out = {};
  for (const arg of argv) {
    const m = /^([ABC])=(.+)$/i.exec(arg);
    if (!m || !E164.test(m[2])) throw new Error(`Bad argument "${arg}". Use A=+1XXXXXXXXXX (E.164).`);
    out[m[1].toUpperCase()] = m[2];
  }
  if (!Object.keys(out).length) throw new Error("Usage: node --env-file=../.env team.mjs A=+1... B=+1... C=+1...");
  return out;
}

function updateEnv(numbers) {
  let text = fs.readFileSync(ENV_PATH, "utf8");
  for (const [slot, phone] of Object.entries(numbers)) {
    const key = `DEMO_PHONE_${slot}`;
    const line = `${key}=${phone}`;
    text = new RegExp(`^${key}=.*$`, "m").test(text) ? text.replace(new RegExp(`^${key}=.*$`, "m"), line) : `${text.trimEnd()}\n${line}\n`;
  }
  fs.writeFileSync(ENV_PATH, text, { mode: 0o600 });
}

async function enroll(phone, firstName) {
  const res = await fetch(`https://spectrum.photon.codes/projects/${id}/users/`, {
    method: "POST",
    headers: { authorization: "Basic " + Buffer.from(`${id}:${secret}`).toString("base64"), "content-type": "application/json" },
    body: JSON.stringify({ type: "shared", phoneNumber: phone, firstName }),
  });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, line: body?.data?.assignedPhoneNumber, error: body?.message };
}

try {
  if (!id || !secret) throw new Error("Missing Photon credentials in .env");
  const numbers = parseArgs(process.argv.slice(2));
  updateEnv(numbers);
  console.log(`Updated ${Object.keys(numbers).map((s) => `DEMO_PHONE_${s}`).join(", ")} in .env`);
  for (const [slot, phone] of Object.entries(numbers)) {
    const r = await enroll(phone, `Teammate ${slot}`);
    console.log(r.ok ? `  ${slot} ${mask(phone)} enrolled -> text ${r.line} once to open the chat`
                     : `  ${slot} ${mask(phone)} FAILED: ${r.error ?? "unknown error"}`);
  }
  console.log("Restart the backend so it picks up the new numbers.");
} catch (err) {
  console.error(err.message);
  process.exit(1);
}
