// node cloudflare/scheduler.test.mjs  – checks the Cloudflare scheduler against the real workflow files
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseCrons, due, tick } from "./scheduler.js";

const WF = ["daily-adhkar", "daily-post", "daily-reel", "daily-short", "serenity-adhkar", "serenity-post", "serenity-reels"];
const files = Object.fromEntries(WF.map((w) => [`${w}.yml`, readFileSync(`.github/workflows/${w}.yml`, "utf8")]));

// every cron line of the repo is found
const all = Object.entries(files).flatMap(([wf, t]) => parseCrons(t).map(([h, m]) => ["obelixagency/quran-reels", wf, h, m]));
assert.equal(all.length, 12, "12 publishing slots a day");

// due(): exact minute, 9 minutes late, 10 minutes late (not due), midnight wrap
const at = (s) => new Date(s + "Z");
assert.deepEqual(due(all, at("2026-11-28T16:47")).map((d) => d.wf), ["daily-reel.yml"]);
assert.deepEqual(due(all, at("2026-11-28T16:56")).map((d) => d.wf), ["daily-reel.yml"]);
assert.deepEqual(due(all, at("2026-11-28T16:57")), []);
assert.deepEqual(due([["r", "x.yml", 23, 58]], at("2026-11-29T00:03")).map((d) => d.slot), ["2026-11-28T23:58"]);

// tick(): dispatches once with the right inputs, never twice for the same slot
const kv = new Map();
const env = { GH_TOKEN: "T", STATE: {
  get: async (k, t) => (kv.has(k) ? (t === "json" ? JSON.parse(kv.get(k)) : kv.get(k)) : null),
  put: async (k, v) => void kv.set(k, v),
} };
const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push([url, init]);
  if (url.includes("/contents/")) return new Response(files[url.split("/").pop()]);
  return new Response(null, { status: 204 });
};
await tick(env, at("2026-11-28T22:08"));
await tick(env, at("2026-11-28T22:09"));
const disp = calls.filter(([u]) => u.endsWith("/dispatches"));
assert.equal(disp.length, 1, "dispatched once");
assert.match(disp[0][0], /serenity-reels\.yml\/dispatches$/);
assert.deepEqual(JSON.parse(disp[0][1].body), { ref: "main", inputs: { kind: "sunnah", publish: "true" } });
assert.equal(disp[0][1].headers.Authorization, "Bearer T");
await tick(env, at("2026-11-28T21:17"));
assert.deepEqual(JSON.parse(calls.filter(([u]) => u.endsWith("/dispatches"))[1][1].body).inputs, { publish: "true", platforms: "tiktok,youtube" });
await tick(env, at("2026-11-28T01:07"));
assert.deepEqual(JSON.parse(calls.filter(([u]) => u.endsWith("/dispatches"))[2][1].body).inputs, { kind: "recited", publish: "true" });
await tick(env, at("2026-11-28T04:23"));
assert.deepEqual(JSON.parse(calls.filter(([u]) => u.endsWith("/dispatches"))[3][1].body).inputs, { session: "morning", publish: "true" });
// failed dispatch is not marked done, so the next minute retries
globalThis.fetch = async (url) => (url.includes("/contents/") ? new Response("") : new Response(null, { status: 401 }));
const log = await tick(env, at("2026-11-28T07:47"));
assert.match(log[0], /FAILED .*daily-post\.yml.*HTTP 401/);
assert.ok(![...kv.keys()].some((k) => k.includes("daily-post")));
console.log("scheduler tests passed");
