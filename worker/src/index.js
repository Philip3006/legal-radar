// Cloudflare Worker: nimmt Watchlist-Klicks vom Dashboard entgegen
// und legt via GitHub-API ein Issue mit Label 'watchlist' an.
//
// POST https://legal-radar-watch.<subdomain>.workers.dev/watch?token=SECRET
// Body: {"id":"dip:333001", "titel":"..."}
//
// Antwort: {"ok":true,"issue":123} oder {"error":"..."}
//
// Sicherheit:
// - WATCH_TOKEN muss im Query stimmen (verhindert Casual-Spam)
// - Origin muss philip3006.github.io oder localhost sein (CORS-Preflight)
// - Duplikate abgefangen: wenn schon ein offenes Issue mit gleicher vorgang_id existiert,
//   antworten wir 200 mit dem existierenden Issue.

const REPO = "Philip3006/legal-radar";
const ALLOWED_ORIGINS = [
  "https://philip3006.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

function corsHeaders(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function json(status, body, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(origin),
    },
  });
}

async function ghGet(path, token) {
  const r = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "legal-radar-watch",
    },
  });
  return r;
}

async function ghPost(path, token, body) {
  return fetch(`https://api.github.com${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "legal-radar-watch",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

async function ghPatch(path, token, body) {
  return fetch(`https://api.github.com${path}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "legal-radar-watch",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

async function findeExistierendes(vorgangId, token) {
  // Alle offenen watchlist-Issues holen (bis 100 - wir haben nie mehr)
  const r = await ghGet(
    `/repos/${REPO}/issues?labels=watchlist&state=open&per_page=100`,
    token,
  );
  if (!r.ok) return null;
  const issues = await r.json();
  for (const issue of issues) {
    const body = issue.body || "";
    const m = body.match(/^\s*vorgang_id\s*:\s*(\S+)\s*$/m);
    if (m && m[1] === vorgangId) return issue.number;
  }
  return null;
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);

    // Health-Endpoint
    if (request.method === "GET" && url.pathname === "/") {
      return json(200, { ok: true, service: "legal-radar-watch" }, origin);
    }

    if (request.method !== "POST" || !["/watch", "/unwatch"].includes(url.pathname)) {
      return json(404, { error: "not found" }, origin);
    }

    // Token check
    const token = url.searchParams.get("token");
    if (!token || token !== env.WATCH_TOKEN) {
      return json(401, { error: "invalid token" }, origin);
    }

    // Body parse
    let payload;
    try {
      payload = await request.json();
    } catch {
      return json(400, { error: "invalid json" }, origin);
    }

    const vid = String(payload?.id || "").trim();
    if (!vid || !vid.startsWith("dip:")) {
      return json(400, { error: "id fehlt oder ungültig" }, origin);
    }

    // --- UNWATCH: Issue schliessen ---
    if (url.pathname === "/unwatch") {
      const existing = await findeExistierendes(vid, env.GITHUB_TOKEN);
      if (!existing) {
        return json(200, { ok: true, removed: false, reason: "not on watchlist" }, origin);
      }
      const r = await ghPatch(
        `/repos/${REPO}/issues/${existing}`,
        env.GITHUB_TOKEN,
        { state: "closed" },
      );
      if (!r.ok) {
        const errText = await r.text();
        return json(502, { error: "github close failed", detail: errText.slice(0, 200) }, origin);
      }
      return json(200, { ok: true, removed: true, issue: existing }, origin);
    }

    // --- WATCH: Issue anlegen ---
    const titel = String(payload?.titel || "").trim();
    if (!titel) {
      return json(400, { error: "titel fehlt" }, origin);
    }

    const existing = await findeExistierendes(vid, env.GITHUB_TOKEN);
    if (existing) {
      return json(200, { ok: true, issue: existing, existed: true }, origin);
    }

    const issueTitle = `Watchlist: ${titel.slice(0, 80)}`;
    const issueBody =
      `vorgang_id: ${vid}\n\n` +
      `Bitte die erste Zeile nicht ändern - der Watchlist-Cron liest sie.`;

    const r = await ghPost(`/repos/${REPO}/issues`, env.GITHUB_TOKEN, {
      title: issueTitle,
      body: issueBody,
      labels: ["watchlist"],
    });

    if (!r.ok) {
      const errText = await r.text();
      return json(502, { error: "github failed", detail: errText.slice(0, 200) }, origin);
    }

    const created = await r.json();
    return json(201, { ok: true, issue: created.number }, origin);
  },
};
