// Photon Spectrum sidecar. Spectrum's REST API has no send endpoint, so sending goes through spectrum-ts.
// POST /send {to, body}            -> iMessage text
// POST /poll {to, question, options} -> native iMessage poll
// Inbound messages / poll votes are forwarded to the backend: POST {BACKEND_URL}/api/photon/inbound {from, text}
import http from "node:http";
import { Spectrum, poll } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

const PORT = Number(process.env.SIDECAR_PORT ?? 8787);
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const E164 = /^\+[1-9]\d{7,14}$/;

const app = await Spectrum({ providers: [imessage.config()] }); // reads SPECTRUM_PROJECT_ID / SECRET from env
const im = imessage(app);
const dms = new Map();

async function dmFor(phone) {
  if (!dms.has(phone)) dms.set(phone, await im.space.create(await im.user(phone)));
  return dms.get(phone);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => { data += c; if (data.length > 10_000) reject(new Error("body too large")); });
    req.on("end", () => { try { resolve(JSON.parse(data || "{}")); } catch (e) { reject(e); } });
  });
}

function reply(res, code, obj) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(obj));
}

http.createServer(async (req, res) => {
  try {
    if (req.method !== "POST" || !["/send", "/poll"].includes(req.url)) return reply(res, 404, { error: "not found" });
    const body = await readJson(req);
    if (!E164.test(body.to ?? "")) return reply(res, 400, { error: "to must be E.164" });
    const dm = await dmFor(body.to);
    if (req.url === "/send") await dm.send(String(body.body ?? "").slice(0, 1500));
    else await dm.send(poll(String(body.question ?? ""), ...(body.options ?? []).map(String)));
    console.log(`[sidecar] ${req.url} ok`); // never log the number
    reply(res, 200, { ok: true, status: "sent" });
  } catch (err) {
    console.error(`[sidecar] ${req.url} failed: ${err?.message ?? err}`);
    reply(res, 502, { ok: false, error: "send failed" });
  }
}).listen(PORT, "127.0.0.1", () => console.log(`[sidecar] listening on 127.0.0.1:${PORT}`));

for await (const [, message] of app.messages) {
  const c = message.content ?? {};
  const text = c.type === "text" ? c.text : c.type === "poll_option" && c.selected ? (c.option?.title ?? c.title ?? "") : null;
  if (!text) continue;
  try {
    await fetch(`${BACKEND_URL}/api/photon/inbound`, {
      method: "POST", headers: { "content-type": "application/json", "x-sidecar-key": process.env.SIDECAR_KEY ?? "" },
      body: JSON.stringify({ from: message.sender?.id ?? "", text }),
    });
  } catch (err) {
    console.error(`[sidecar] forward inbound failed: ${err?.message ?? err}`);
  }
}
