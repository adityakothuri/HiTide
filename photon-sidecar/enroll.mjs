// Enroll a phone on the project's shared iMessage line and print the line number that person should text.
// Usage: node --env-file=../.env enroll.mjs +1XXXXXXXXXX [FirstName]
// Prints the enrolled phone masked; never prints the project secret.
const [phone, firstName] = process.argv.slice(2);
const id = process.env.SPECTRUM_PROJECT_ID || process.env.PROJECT_ID;
const secret = process.env.SPECTRUM_PROJECT_SECRET || process.env.PROJECT_SECRET;

if (!/^\+[1-9]\d{6,14}$/.test(phone ?? "")) {
  console.error("Usage: node --env-file=../.env enroll.mjs +1XXXXXXXXXX [FirstName]");
  process.exit(1);
}
if (!id || !secret) {
  console.error("Missing PROJECT_ID / PROJECT_SECRET (or SPECTRUM_*) in the env file.");
  process.exit(1);
}

const res = await fetch(`https://spectrum.photon.codes/projects/${id}/users/`, {
  method: "POST",
  headers: {
    authorization: "Basic " + Buffer.from(`${id}:${secret}`).toString("base64"),
    "content-type": "application/json",
  },
  body: JSON.stringify({ type: "shared", phoneNumber: phone, firstName: firstName ?? null }),
});
const masked = phone.slice(0, -4).replace(/\d/g, "•") + phone.slice(-4);
const text = (await res.text()).replaceAll(secret, "[secret]").replaceAll(phone, masked);
console.log(`HTTP ${res.status}`);
console.log(text);
