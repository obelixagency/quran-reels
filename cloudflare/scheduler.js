// Quran scheduler (Cloudflare Worker, cron "* * * * *").
// GitHub's own cron starts runs hours late, so this Worker starts every publishing workflow at its exact time
// with workflow_dispatch. The times are the `- cron:` lines of each workflow file (the same lines the watchdog
// reads), so changing a time — e.g. for summer time — is still a one-line edit in the workflow.
// Bindings: STATE = KV namespace "quran-state" (keys under sched/). Secret: GH_TOKEN (fine-grained token,
// "Actions: read & write" on the repos below). The token is never logged.

const REPOS = {
  "obelixagency/quran-reels": {
    "daily-adhkar.yml": (h) => ({ session: h < 9 ? "morning" : "evening", publish: "true" }),
    "daily-post.yml": () => ({ publish: "true" }),
    "daily-reel.yml": (h) => (h >= 20 ? { publish: "true", platforms: "tiktok,youtube" } : { publish: "true" }),
    "daily-short.yml": () => ({ publish: "true" }),
    "serenity-adhkar.yml": (h) => ({ session: h < 16 ? "morning" : "evening", publish: "true" }),
    "serenity-post.yml": () => ({ publish: "true" }),
    "serenity-reels.yml": (h) => ({ kind: h <= 3 ? "recited" : h >= 15 && h <= 20 ? "quran" : "sunnah", publish: "true" }),
  },
};
const WINDOW_MIN = 10;          // a slot is started in the first 10 minutes after its time, once
const CRON_RE = /^\s*- cron: "(\d+) (\d+) \* \* \*"(.*)$/;

function gh(env, repo, path, init = {}) {
  return fetch(`https://api.github.com/repos/${repo}/${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "quran-scheduler",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
}

export function parseCrons(text) {
  const out = [];
  for (const line of text.split("\n")) {
    const m = line.match(CRON_RE);
    if (m && !m[3].includes("backup")) out.push([+m[2], +m[1]]);
  }
  return out;
}

// [repo, workflow, hour, minute] for every slot; cached in KV for an hour
async function slots(env) {
  const cached = await env.STATE.get("sched/slots", "json");
  if (cached) return cached;
  const out = [];
  for (const [repo, wfs] of Object.entries(REPOS)) {
    for (const wf of Object.keys(wfs)) {
      const r = await gh(env, repo, `contents/.github/workflows/${wf}`, { headers: { Accept: "application/vnd.github.raw+json" } });
      if (!r.ok) throw new Error(`reading ${repo}/${wf}: HTTP ${r.status}`);
      for (const [h, m] of parseCrons(await r.text())) out.push([repo, wf, h, m]);
    }
  }
  await env.STATE.put("sched/slots", JSON.stringify(out), { expirationTtl: 3600 });
  return out;
}

// slots whose time is in (now - WINDOW, now] – today's or yesterday's (around midnight)
export function due(all, now) {
  const out = [];
  for (const [repo, wf, h, m] of all) {
    for (const back of [0, 1]) {
      const slot = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - back, h, m);
      const age = (now.getTime() - slot) / 60000;
      if (age >= 0 && age < WINDOW_MIN) out.push({ repo, wf, h, m, slot: new Date(slot).toISOString().slice(0, 16) });
    }
  }
  return out;
}

export async function tick(env, now) {
  const log = [];
  for (const s of due(await slots(env), now)) {
    const key = `sched/done/${s.repo}/${s.wf}/${s.slot}`;
    if (await env.STATE.get(key)) continue;
    const r = await gh(env, s.repo, `actions/workflows/${s.wf}/dispatches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: REPOS[s.repo][s.wf](s.h) }),
    });
    if (r.status === 204) {
      await env.STATE.put(key, now.toISOString(), { expirationTtl: 3 * 86400 });
      log.push(`started ${s.repo} ${s.wf} (${s.slot} UTC)`);
    } else {
      log.push(`FAILED ${s.repo} ${s.wf} (${s.slot} UTC): HTTP ${r.status}`);
    }
  }
  if (log.length) {
    console.log(log.join("\n"));
    await env.STATE.put("sched/last", JSON.stringify({ at: now.toISOString(), log }), { expirationTtl: 30 * 86400 });
  }
  return log;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(tick(env, new Date(event.scheduledTime)));
  },
  async fetch() {
    return new Response("quran-scheduler: runs on a cron trigger only\n");
  },
};
