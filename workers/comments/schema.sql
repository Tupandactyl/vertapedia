-- 문서별 의견(댓글) 저장소: Cloudflare D1
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page TEXT NOT NULL,          -- 'sp:Genus_species' 또는 'fam:Anatidae'
  title TEXT,                  -- 모아보기에 보일 문서 이름(국명)
  parent INTEGER,              -- 답글이면 원 글 id
  nick TEXT NOT NULL,
  ip_pre TEXT,                 -- 공개되는 IP 앞 두 자리 (관리자 글은 NULL)
  ip_hash TEXT,                -- 도배 막기·차단용. IP 원문은 저장하지 않는다
  pw_hash TEXT,                -- 익명 글 삭제 비밀번호
  admin INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL DEFAULT 'opinion',   -- opinion | error | info
  status TEXT,                 -- open | review | done | wontfix (원 글만)
  body TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,      -- 1 본인 삭제, 2 관리자 숨김
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS comments_page ON comments(page, id);
CREATE INDEX IF NOT EXISTS comments_recent ON comments(parent, id);
CREATE INDEX IF NOT EXISTS comments_ip ON comments(ip_hash, created);
CREATE TABLE IF NOT EXISTS bans (ip_hash TEXT PRIMARY KEY, created INTEGER NOT NULL, note TEXT);
-- 관리자: 편집진 시트 편집자 메일의 해시(메일 원문은 두지 않는다). sync_admins.py가 채운다
CREATE TABLE IF NOT EXISTS admins (email_hash TEXT PRIMARY KEY);
