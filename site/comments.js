// 문서 아래 의견(댓글)창 — 스레드형: 답글은 원 글 밑, 관리자가 처리 상태를 단다.
// 서버: workers/comments/worker.js (Cloudflare). 익명 글은 닉네임 + IP 앞 두 자리, 관리자는 구글 로그인.
(function () {
  // turnstile: Cloudflare Turnstile 사이트 키(공개값), google: 구글 OAuth 클라이언트 ID(공개값)
  // 내 컴퓨터에서 미리 볼 때(127.0.0.1)는 시험 서버(127.0.0.1:8787)를 쓴다
  var LOCAL = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
  var CFG = Object.assign({ api: LOCAL ? "http://127.0.0.1:8787" : "https://api.vertapedia.org", turnstile: "0x4AAAAAAGCt4FRnujHizDWS", google: "648752126074-gg5vskn6k8dbo1magp2kgddt0ls4dg36.apps.googleusercontent.com" }, window.VTALK || {});
  var API = CFG.api;
  var KIND = { opinion: "댓글", error: "검토 필요", info: "추가 정보" };
  var STATUS = { open: "처리 전", review: "검토 중", done: "반영됨", wontfix: "반영 안 함" };
  var esc = function (t) { return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]; }); };
  function bodyHtml(t) {
    return esc(t).replace(/https?:\/\/[^\s<]+[^\s<.,)\]]/g, function (u) { return '<a href="' + u + '" rel="nofollow ugc noopener" target="_blank">' + u + "</a>"; }).replace(/\n/g, "<br>");
  }
  function when(s) {
    var d = Math.floor(Date.now() / 1000) - s;
    if (d < 60) return "방금";
    if (d < 3600) return Math.floor(d / 60) + "분 전";
    if (d < 86400) return Math.floor(d / 3600) + "시간 전";
    if (d < 86400 * 7) return Math.floor(d / 86400) + "일 전";
    var x = new Date(s * 1000);
    return x.getFullYear() + "-" + String(x.getMonth() + 1).padStart(2, "0") + "-" + String(x.getDate()).padStart(2, "0");
  }
  var store = {
    get: function (k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) {} },
    lget: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    lset: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  var ADMIN = false;
  function call(path, opt) {
    opt = opt || {};
    var h = { "Content-Type": "application/json" }, tok = store.get("vtalk-id");
    if (tok) h.Authorization = "Bearer " + tok;
    return fetch(API + path, { method: opt.body ? "POST" : "GET", headers: h, body: opt.body ? JSON.stringify(opt.body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || "요청이 실패했습니다"); return j; }); });
  }
  function loadScript(src) {
    return new Promise(function (ok, no) {
      if (document.querySelector('script[src="' + src + '"]')) return ok();
      var s = document.createElement("script"); s.src = src; s.async = true; s.onload = ok; s.onerror = no; document.head.appendChild(s);
    });
  }
  // 자동 등록 방지(Cloudflare Turnstile): 글쓰기 칸을 처음 누를 때 불러온다
  function captcha(box) {
    if (!CFG.turnstile || ADMIN) return Promise.resolve(null);
    if (box._tw != null) return Promise.resolve(box._tw);
    return loadScript("https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit").then(function () {
      return new Promise(function (ok) { (function wait() { window.turnstile ? ok() : setTimeout(wait, 50); })(); });
    }).then(function () {
      box._tw = window.turnstile.render(box, { sitekey: CFG.turnstile, appearance: "interaction-only", language: "ko" });
      return box._tw;
    });
  }

  function meta(c) {
    var who = c.admin ? '<b class="vt-nick">' + esc(c.nick) + '</b><span class="vt-adm">관리자</span>'
                      : '<b class="vt-nick">' + esc(c.nick) + '</b><span class="vt-ip">(' + esc(c.ip) + ")</span>";
    var tags = "";
    if (!c.parent && c.kind && c.kind !== "opinion") tags += '<span class="vt-tag k-' + c.kind + '">' + KIND[c.kind] + "</span>";
    if (!c.parent && c.status) tags += '<span class="vt-tag s-' + c.status + '">' + STATUS[c.status] + "</span>";
    return '<div class="vt-meta">' + who + '<span class="vt-time" title="' + new Date(c.created * 1000).toLocaleString() + '">' + when(c.created) + "</span>" + tags + "</div>";
  }
  function tools(c) {
    var t = [];
    if (!c.parent) t.push('<button type="button" data-act="reply">답글</button>');
    if (ADMIN) {
      if (!c.parent) t.push('<select data-act="status" aria-label="처리 상태"><option value="">상태</option>' +
        Object.keys(STATUS).map(function (k) { return '<option value="' + k + '"' + (c.status === k ? " selected" : "") + ">" + STATUS[k] + "</option>"; }).join("") + "</select>");
      t.push('<button type="button" data-act="hide">숨기기</button>');
      if (!c.admin) t.push('<button type="button" data-act="ban">이 IP 차단</button>');
    } else if (!c.admin) t.push('<button type="button" data-act="delete">삭제</button>');
    return '<div class="vt-tools">' + t.join("") + "</div>";
  }
  function item(c) {
    if (c.hidden) return '<div class="vt-item vt-gone" data-id="' + c.id + '">' + (c.hidden === 2 ? "관리자가 숨긴 의견입니다." : "작성자가 지운 의견입니다.") + "</div>";
    return '<div class="vt-item" data-id="' + c.id + '">' + meta(c) + '<div class="vt-body">' + bodyHtml(c.body) + "</div>" + tools(c) + "</div>";
  }
  // 닉네임을 비워 두면 국명 가운데 하나를 무작위로 쓴다(폼을 그릴 때마다 새로 고름)
  var NICKS = null;
  function loadNicks() {
    if (NICKS) return Promise.resolve(NICKS);
    return fetch("/data/nicks.json").then(function (r) { return r.json(); })
      .then(function (a) { NICKS = a && a.length ? a : ["경추"]; return NICKS; }).catch(function () { return (NICKS = ["경추"]); });
  }
  function rollNick(f) {
    var x = f.elements.nick;
    if (x && !ADMIN) loadNicks().then(function (a) { x.placeholder = a[Math.floor(Math.random() * a.length)]; });
  }
  function form(isReply) {
    var nick = esc(store.lget("vtalk-nick") || "");
    return '<form class="vt-form' + (isReply ? " vt-replyform" : "") + '">' +
      (isReply ? "" : '<select name="kind" aria-label="종류"><option value="opinion">댓글</option><option value="error">검토 필요</option><option value="info">추가 정보</option></select>') +
      (ADMIN ? '<input name="nick" maxlength="16" placeholder="표시 이름" value="' + nick + '" aria-label="표시 이름">'
             : '<input name="nick" maxlength="16" placeholder="경추" value="' + nick + '" aria-label="닉네임"><input name="pw" type="password" minlength="4" maxlength="40" placeholder="비밀번호" aria-label="삭제용 비밀번호" autocomplete="new-password">') +
      '<textarea name="body" maxlength="3000" required placeholder="' + "제안 및 의견을 공유해 주세요. 출처가 있으면 함께 적어 주시면 좋습니다" + '"></textarea>' +
      '<div class="vt-cap"></div><div class="vt-row"><span class="vt-err" role="alert"></span><button type="submit">' + (isReply ? "답글 등록" : "등록") + "</button></div></form>";
  }

  function mount(el, page, title) {
    if (!el) return;
    el.classList.add("vt");
    var items = [];
    function draw() {
      var tops = items.filter(function (c) { return !c.parent; });
      var n = items.filter(function (c) { return !c.hidden; }).length;
      el.innerHTML = '<h2>의견 <span class="vt-n">' + n + "</span></h2>" +
        '<div class="vt-list">' + (tops.length ? tops.map(function (t) {
          var kids = items.filter(function (c) { return c.parent === t.id; });
          return '<div class="vt-thread">' + item(t) + (kids.length ? '<div class="vt-kids">' + kids.map(item).join("") + "</div>" : "") + "</div>";
        }).join("") : "") + "</div>" +
        form(false) +
        '<p class="vt-admin">' + (ADMIN ? '관리자 · <a href="talk.html">모든 의견</a> · <a href="#" data-act="logout">로그아웃</a>' : '<a href="#" data-act="login">관리자 로그인</a>') + '</p><div class="vt-gsi"></div>';
      Array.prototype.forEach.call(el.querySelectorAll(".vt-form"), rollNick);
    }
    function refresh() {
      return call("/comments?page=" + encodeURIComponent(page)).then(function (j) {
        items = j.items || []; draw();
        if (location.hash === "#talk" && el.id === "talk" && !el._jumped) { el._jumped = 1; el.scrollIntoView(); }
      })
        .catch(function () { el.innerHTML = '<h2>의견</h2><p class="vt-note">의견을 불러오지 못했습니다.</p>'; });
    }
    function submit(f, parent) {
      var err = f.querySelector(".vt-err"), btn = f.querySelector("button[type=submit]");
      var v = function (n) { var x = f.elements[n]; return x ? x.value : ""; };
      err.textContent = "";
      if (!v("body").trim()) { err.textContent = "내용을 적어 주세요"; return; }
      if (!ADMIN && v("pw").length < 4) { err.textContent = "삭제용 비밀번호를 4자 이상 적어 주세요"; return; }
      var cap = f.querySelector(".vt-cap"), tok = cap._tw != null && window.turnstile ? window.turnstile.getResponse(cap._tw) : null;
      if (CFG.turnstile && !ADMIN && !tok) { err.textContent = "자동 등록 방지 확인이 끝나지 않았습니다. 잠시 뒤 다시 눌러 주세요"; captcha(cap); return; }
      btn.disabled = true;
      if (v("nick")) store.lset("vtalk-nick", v("nick"));
      var nx = f.elements.nick;
      call("/comments", { body: { page: page, title: title, parent: parent || null, kind: v("kind") || "opinion", nick: v("nick") || (!ADMIN && nx ? nx.placeholder : ""), pw: v("pw"), body: v("body"), turnstile: tok } })
        .then(refresh).catch(function (e) { err.textContent = e.message; btn.disabled = false; if (cap._tw != null) window.turnstile.reset(cap._tw); });
    }
    el.addEventListener("focusin", function (e) { var f = e.target.closest(".vt-form"); if (f) captcha(f.querySelector(".vt-cap")); });
    el.addEventListener("submit", function (e) {
      e.preventDefault();
      var f = e.target, th = f.closest(".vt-thread");
      submit(f, f.classList.contains("vt-replyform") && th ? +th.querySelector(".vt-item").dataset.id : null);
    });
    el.addEventListener("change", function (e) {
      if (e.target.dataset.act !== "status" || !e.target.value) return;
      var id = e.target.closest(".vt-item").dataset.id;
      call("/comments/" + id + "/status", { body: { status: e.target.value } }).then(refresh).catch(function (x) { alert(x.message); });
    });
    el.addEventListener("click", function (e) {
      var b = e.target.closest("[data-act]");
      if (!b || b.tagName === "SELECT") return;
      var act = b.dataset.act, it = b.closest(".vt-item"), id = it && it.dataset.id;
      if (act === "login") { e.preventDefault(); login(el.querySelector(".vt-gsi"), refresh); return; }
      if (act === "logout") { e.preventDefault(); store.set("vtalk-id", null); ADMIN = false; draw(); return; }
      if (act === "reply") {
        var th = b.closest(".vt-thread"), old = th.querySelector(".vt-replyform");
        if (old) { old.remove(); return; }
        th.insertAdjacentHTML("beforeend", form(true)); rollNick(th.querySelector(".vt-replyform")); th.querySelector(".vt-replyform textarea").focus(); return;
      }
      if (act === "delete") {
        var pw = prompt("글을 쓸 때 정한 비밀번호");
        if (pw) call("/comments/" + id + "/delete", { body: { pw: pw } }).then(refresh).catch(function (x) { alert(x.message); });
        return;
      }
      if (act === "hide" && confirm("이 의견을 숨길까요?")) call("/comments/" + id + "/delete", { body: {} }).then(refresh).catch(function (x) { alert(x.message); });
      if (act === "ban" && confirm("이 의견을 쓴 IP를 차단하고 그 IP의 글을 모두 숨길까요?")) call("/comments/" + id + "/ban", { body: {} }).then(refresh).catch(function (x) { alert(x.message); });
    });
    // 댓글 서버는 해외 거점을 거쳐 느릴 수 있어, 의견창이 화면에 가까워질 때 불러온다
    draw();
    var started = false, go = function () { if (!started) { started = true; whoami().then(refresh); } };
    if (location.hash === "#talk" || !("IntersectionObserver" in window)) go();
    else {
      var io = new IntersectionObserver(function (es) { if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); go(); } }, { rootMargin: "800px 0px" });
      io.observe(el);
      setTimeout(go, 3000);  // 화면 감지가 멈춘 경우(백그라운드 탭 등)에도 첫 화면을 다 그린 뒤 불러온다
    }
  }

  function whoami() {
    if (!store.get("vtalk-id")) return Promise.resolve();
    return call("/whoami").then(function (j) { ADMIN = !!j.admin; if (!ADMIN) store.set("vtalk-id", null); }).catch(function () {});
  }
  // 관리자 로그인: 구글 계정. 편집진 시트 편집자 메일이면 관리자
  function login(box, done) {
    if (!CFG.google) { alert("관리자 로그인이 아직 설정되지 않았습니다."); return; }
    loadScript("https://accounts.google.com/gsi/client").then(function () {
      (function wait() {
        if (!window.google || !google.accounts) return setTimeout(wait, 50);
        google.accounts.id.initialize({ client_id: CFG.google, callback: function (r) {
          store.set("vtalk-id", r.credential);
          whoami().then(function () { if (!ADMIN) alert("이 계정은 관리자로 등록되어 있지 않습니다."); box.innerHTML = ""; done(); });
        } });
        google.accounts.id.renderButton(box, { theme: "outline", size: "medium", text: "signin_with", locale: "ko" });
      })();
    });
  }

  window.VTalk = { mount: mount, call: call, when: when, esc: esc, bodyHtml: bodyHtml, KIND: KIND, STATUS: STATUS, whoami: whoami, login: login, isAdmin: function () { return ADMIN; } };
})();
