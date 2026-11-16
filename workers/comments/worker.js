// Vertapedia 의견(댓글) 서버: Cloudflare Worker + D1
// 익명 글은 닉네임과 IP 앞 두 자리로 표시한다. IP 원문은 저장하지 않고 솔트를 친 해시만 둔다(도배 막기·차단용).
// 관리자는 구글 로그인(ID 토큰)으로 확인하고, 메일이 편집진 시트 편집자 목록(admins 표, 해시)에 있으면 관리자로 표시한다.
//
// 바인딩: DB(D1) · 변수: ORIGINS(쉼표), GOOGLE_CLIENT_ID · 비밀값: IP_SALT, TURNSTILE_SECRET, SYNC_TOKEN
const KINDS = ["opinion", "error", "info"];
const STATUSES = ["open", "review", "done", "wontfix"];
const LIMIT_GAP = 20;      // 같은 IP 연속 글 간격(초)
const LIMIT_DAY = 40;      // 같은 IP 하루 글 수

const enc = new TextEncoder();
async function sha256(s) {
  const b = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}
async function pwHash(pw, salt) {
  const key = await crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(salt), iterations: 50000 }, key, 256);
  return [...new Uint8Array(bits)].map(x => x.toString(16).padStart(2, "0")).join("");
}
function ipPrefix(ip) {
  if (!ip) return "?";
  if (ip.includes(".")) return ip.split(".").slice(0, 2).join(".");
  return ip.split(":").slice(0, 2).join(":");
}
const now = () => Math.floor(Date.now() / 1000);
const clean = (s, n) => String(s == null ? "" : s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "").trim().slice(0, n);

function cors(req, env) {
  const o = req.headers.get("Origin") || "";
  const ok = (env.ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
  return {
    "Access-Control-Allow-Origin": ok.includes(o) ? o : ok[0] || "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
const json = (req, env, data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors(req, env) },
});
const fail = (req, env, msg, status = 400) => json(req, env, { error: msg }, status);

// 구글 ID 토큰 확인(관리자). 결과는 잠깐 기억해 둔다
const TOKENS = new Map();
async function adminOf(req, env) {
  const h = req.headers.get("Authorization") || "";
  if (!h.startsWith("Bearer ")) return null;
  const tok = h.slice(7);
  const c = TOKENS.get(tok);
  if (c && c.exp > now()) return c.admin ? c : null;
  const r = await fetch("https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(tok));
  if (!r.ok) return null;
  const t = await r.json();
  if (t.aud !== env.GOOGLE_CLIENT_ID || String(t.email_verified) !== "true" || !["accounts.google.com", "https://accounts.google.com"].includes(t.iss)) return null;
  const eh = await sha256(String(t.email).toLowerCase());
  const row = await env.DB.prepare("SELECT 1 FROM admins WHERE email_hash=?").bind(eh).first();
  const v = { admin: !!row, exp: Math.min(Number(t.exp) || 0, now() + 3600) };
  TOKENS.set(tok, v);
  if (TOKENS.size > 500) TOKENS.clear();
  return v.admin ? v : null;
}

const PUBLIC = "id, page, title, parent, nick, ip_pre, admin, kind, status, body, hidden, created";
function shape(r) {
  if (r.hidden) return { id: r.id, page: r.page, parent: r.parent, hidden: r.hidden, created: r.created, status: r.status };
  return { id: r.id, page: r.page, title: r.title, parent: r.parent, nick: r.nick, ip: r.admin ? null : r.ip_pre, admin: !!r.admin,
           kind: r.kind, status: r.status, body: r.body, created: r.created };
}

async function list(req, env, url) {
  const page = clean(url.searchParams.get("page"), 200);
  if (!page) return fail(req, env, "page가 없습니다");
  const { results } = await env.DB.prepare(`SELECT ${PUBLIC} FROM comments WHERE page=? ORDER BY id`).bind(page).all();
  // 지워진 글은 답글이 있을 때만 자리를 남긴다
  const hasKids = new Set(results.filter(r => r.parent && !r.hidden).map(r => r.parent));
  return json(req, env, { items: results.filter(r => !r.hidden || hasKids.has(r.id)).map(shape) });
}

async function recent(req, env, url) {
  const kind = url.searchParams.get("kind"), status = url.searchParams.get("status");
  const before = parseInt(url.searchParams.get("before") || "0", 10);
  const where = ["parent IS NULL", "hidden=0"], args = [];
  if (KINDS.includes(kind)) { where.push("kind=?"); args.push(kind); }
  if (status === "todo") where.push("status IN ('open','review')");
  else if (STATUSES.includes(status)) { where.push("status=?"); args.push(status); }
  if (before > 0) { where.push("id<?"); args.push(before); }
  const sql = `SELECT ${PUBLIC}, (SELECT COUNT(*) FROM comments k WHERE k.parent=c.id AND k.hidden=0) AS replies
               FROM comments c WHERE ${where.join(" AND ")} ORDER BY id DESC LIMIT 30`;
  const { results } = await env.DB.prepare(sql).bind(...args).all();
  return json(req, env, { items: results.map(r => ({ ...shape(r), replies: r.replies })) });
}

async function turnstileOk(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true;
  if (!token) return false;
  const f = new FormData();
  f.append("secret", env.TURNSTILE_SECRET); f.append("response", token); if (ip) f.append("remoteip", ip);
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: f });
  return r.ok && (await r.json()).success === true;
}

async function post(req, env) {
  const b = await req.json().catch(() => null);
  if (!b) return fail(req, env, "내용을 읽지 못했습니다");
  const admin = await adminOf(req, env);
  const ip = req.headers.get("CF-Connecting-IP") || "";
  const ipHash = await sha256(env.IP_SALT + "|" + ip);
  const page = clean(b.page, 200), body = clean(b.body, 3000), title = clean(b.title, 80);
  let nick = clean(b.nick, 16) || (admin ? "관리자" : "경추");
  const kind = KINDS.includes(b.kind) ? b.kind : "opinion";
  if (!/^(sp|fam):[A-Za-z_ -]+$/.test(page)) return fail(req, env, "문서를 알 수 없습니다");
  if (!body) return fail(req, env, "내용을 적어 주세요");
  if (!admin) {
    if (await env.DB.prepare("SELECT 1 FROM bans WHERE ip_hash=?").bind(ipHash).first()) return fail(req, env, "이 주소에서는 글을 쓸 수 없습니다", 403);
    const pw = String(b.pw || "");
    if (pw.length < 4) return fail(req, env, "비밀번호를 4자 이상 적어 주세요");
    if (!(await turnstileOk(env, b.turnstile, ip))) return fail(req, env, "자동 등록 방지 확인에 실패했습니다. 다시 시도해 주세요", 403);
    const t = now();
    const last = await env.DB.prepare("SELECT MAX(created) m, SUM(created>?) d FROM comments WHERE ip_hash=? AND created>?").bind(t - 86400, ipHash, t - 86400).first();
    if (last && last.m && t - last.m < LIMIT_GAP) return fail(req, env, `잠시 뒤에 다시 써 주세요 (${LIMIT_GAP}초)`, 429);
    if (last && last.d >= LIMIT_DAY) return fail(req, env, "오늘은 더 쓸 수 없습니다", 429);
    b._pw = await pwHash(pw, ipHash.slice(0, 16) + page);
  }
  let parent = null;
  if (b.parent) {
    const p = await env.DB.prepare("SELECT id, page, parent FROM comments WHERE id=?").bind(b.parent | 0).first();
    if (!p || p.page !== page) return fail(req, env, "답글을 달 글이 없습니다");
    parent = p.parent || p.id;   // 답글의 답글은 원 글 밑으로
  }
  const status = parent ? null : (kind === "opinion" ? null : "open");
  const r = await env.DB.prepare(`INSERT INTO comments (page, title, parent, nick, ip_pre, ip_hash, pw_hash, admin, kind, status, body, created)
                                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?) RETURNING ${PUBLIC}`)
    .bind(page, title || null, parent, nick, admin ? null : ipPrefix(ip), ipHash, admin ? null : b._pw, admin ? 1 : 0,
          parent ? "opinion" : kind, status, body, now()).first();
  return json(req, env, { item: shape(r) }, 201);
}

async function remove(req, env, id) {
  const b = await req.json().catch(() => ({}));
  const row = await env.DB.prepare("SELECT * FROM comments WHERE id=?").bind(id).first();
  if (!row) return fail(req, env, "글이 없습니다", 404);
  const admin = await adminOf(req, env);
  let how = 0;
  if (admin) how = 2;
  else {
    if (!row.pw_hash) return fail(req, env, "지울 수 없는 글입니다", 403);
    if ((await pwHash(String(b.pw || ""), row.ip_hash.slice(0, 16) + row.page)) !== row.pw_hash) return fail(req, env, "비밀번호가 맞지 않습니다", 403);
    how = 1;
  }
  await env.DB.prepare("UPDATE comments SET hidden=? WHERE id=?").bind(how, id).run();
  return json(req, env, { ok: true });
}

async function setStatus(req, env, id) {
  if (!(await adminOf(req, env))) return fail(req, env, "관리자만 바꿀 수 있습니다", 403);
  const b = await req.json().catch(() => ({}));
  if (!STATUSES.includes(b.status)) return fail(req, env, "상태가 맞지 않습니다");
  await env.DB.prepare("UPDATE comments SET status=? WHERE id=? AND parent IS NULL").bind(b.status, id).run();
  return json(req, env, { ok: true });
}

async function ban(req, env, id) {
  if (!(await adminOf(req, env))) return fail(req, env, "관리자만 할 수 있습니다", 403);
  const row = await env.DB.prepare("SELECT ip_hash, admin FROM comments WHERE id=?").bind(id).first();
  if (!row || row.admin) return fail(req, env, "차단할 수 없습니다");
  await env.DB.batch([
    env.DB.prepare("INSERT OR IGNORE INTO bans (ip_hash, created, note) VALUES (?,?,?)").bind(row.ip_hash, now(), "글 " + id),
    env.DB.prepare("UPDATE comments SET hidden=2 WHERE ip_hash=? AND admin=0").bind(row.ip_hash),
  ]);
  return json(req, env, { ok: true });
}

async function whoami(req, env) {
  return json(req, env, { admin: !!(await adminOf(req, env)) });
}

// 관리자 목록 바꾸기: sync_admins.py 가 편집진 시트 편집자 메일 해시를 보낸다
async function syncAdmins(req, env) {
  if (!env.SYNC_TOKEN || req.headers.get("Authorization") !== "Bearer " + env.SYNC_TOKEN) return fail(req, env, "권한이 없습니다", 403);
  const b = await req.json().catch(() => null);
  const hs = (b && Array.isArray(b.hashes) ? b.hashes : []).filter(h => /^[0-9a-f]{64}$/.test(h));
  if (!hs.length) return fail(req, env, "목록이 비었습니다");
  await env.DB.batch([env.DB.prepare("DELETE FROM admins"), ...hs.map(h => env.DB.prepare("INSERT OR IGNORE INTO admins VALUES (?)").bind(h))]);
  TOKENS.clear();
  return json(req, env, { ok: true, n: hs.length });
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req, env) });
    const url = new URL(req.url), p = url.pathname.replace(/\/+$/, "");
    try {
      if (req.method === "GET" && p === "/comments") return await list(req, env, url);
      if (req.method === "GET" && p === "/recent") return await recent(req, env, url);
      if (req.method === "GET" && p === "/whoami") return await whoami(req, env);
      if (req.method === "POST" && p === "/comments") return await post(req, env);
      if (req.method === "POST" && p === "/admins") return await syncAdmins(req, env);
      const m = p.match(/^\/comments\/(\d+)\/(delete|status|ban)$/);
      if (req.method === "POST" && m) {
        const id = parseInt(m[1], 10);
        if (m[2] === "delete") return await remove(req, env, id);
        if (m[2] === "status") return await setStatus(req, env, id);
        return await ban(req, env, id);
      }
      if (p === "" || p === "/") return json(req, env, { ok: true, service: "vertapedia-comments" });
      return fail(req, env, "없는 주소입니다", 404);
    } catch (e) {
      return fail(req, env, "서버 오류가 났습니다", 500);
    }
  },
};
