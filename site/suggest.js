// 머리 검색창 자동완성: 글자를 칠 때마다 후보 다섯 개. 이름 찾기 페이지(find.html)와 같은 순위 규칙
// (정확히 같음 > 별칭 같음 > 앞부분 > 단어 앞부분 > 포함 > 초성 > 한 글자 오타).
// 자료는 data/names.min.json — 검색창을 처음 누를 때 받는다(이름 찾기 페이지와 같은 파일이라 캐시를 같이 쓴다).
(function () {
  var esc = function (t) { return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]; }); };
  var key = function (t) { return (t || "").toLowerCase().replace(/[\s\-‐-―'’.,()]+/g, ""); };
  var CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
  var cho = function (t) { return Array.from(t || "").map(function (c) { var n = c.charCodeAt(0) - 0xAC00; return n >= 0 && n < 11172 ? CHO[Math.floor(n / 588)] : c; }).join(""); };
  var isCho = function (t) { return /^[ㄱ-ㅎ]+$/.test(t); };
  function near1(a, b) {
    if (Math.abs(a.length - b.length) > 1 || a === b) return a === b;
    var i = 0, j = 0, d = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) { i++; j++; continue; }
      if (++d > 1) return false;
      if (a.length > b.length) i++; else if (a.length < b.length) j++; else { i++; j++; }
    }
    return d + (a.length - i) + (b.length - j) <= 1;
  }
  var RK = { o: "목", u: "아목", f: "과", g: "속", s: "종" };
  var rows = null, loading = null;
  function load() {
    if (rows || loading) return loading;
    loading = fetch("data/names.min.json").then(function (r) { return r.json(); }).then(function (d) {
      rows = d.filter(function (r) { return r[1] === "s" || r[1] === "f"; }).map(function (r) {
        var al = function (label) { return (r[10] || []).filter(function (x) { return x[0] === label; }).map(function (x) { return key(x[1]); }); };
        var tr = al("국내 유통명"), mo = al("환경부 지정명"), ss = (r[7] || []).map(function (x) { return key(x[1]); }).filter(Boolean);
        var a = tr.concat(mo, ss).filter(Boolean);
        return { r: r, n: key(r[3]), sc: key(r[2]), en: key(r[4]), a: a, tr: tr, mo: mo, ss: ss, c: cho(key(r[3])),
                 w: [r[2], r[4]].join(" ").toLowerCase().split(/[\s\-']+/).filter(Boolean),
                 k: key([r[3], r[2], r[4]].join(" ")) + a.join("|") };
      });
    });
    return loading;
  }
  // 같은 단계 안에서는 편집진 합의 국명 > 국내 유통명 > 환경부 지정명 > 아종 국명
  var eq = function (list, k) { return list.indexOf(k) >= 0; };
  var pre = function (list, k) { return list.some(function (a) { return a.indexOf(k) === 0; }); };
  function score(x, k) {
    if (x.n === k || x.sc === k || x.en === k) return 0;
    if (eq(x.tr, k)) return 0.2;
    if (eq(x.mo, k)) return 0.4;
    if (eq(x.ss, k)) return 0.6;
    if (x.n && x.n.indexOf(k) === 0) return 1;
    if (pre(x.tr, k)) return 1.2;
    if (pre(x.mo, k)) return 1.4;
    if (pre(x.ss, k)) return 1.6;
    if (x.sc.indexOf(k) === 0 || x.en.indexOf(k) === 0) return 2;
    if (x.w.some(function (w) { return w.indexOf(k) === 0; })) return 3;
    if (x.k.indexOf(k) >= 0) return 4;
    if (isCho(k) && x.c.indexOf(k) >= 0) return 5;
    if (k.length >= 3 && x.n && near1(x.n, k)) return 6;
    return -1;
  }
  function top5(q) {
    var k = key(q);
    if (!k || !rows) return [];
    var hits = [];
    for (var i = 0; i < rows.length; i++) { var s = score(rows[i], k); if (s >= 0) hits.push([s, rows[i]]); }
    hits.sort(function (a, b) {
      return a[0] - b[0] || (a[1].r[1] === "s" ? 0 : 1) - (b[1].r[1] === "s" ? 0 : 1) ||
        (a[1].r[3] ? 0 : 1) - (b[1].r[3] ? 0 : 1) || (a[1].n || "").length - (b[1].n || "").length;
    });
    return hits.slice(0, 5).map(function (h) { return h[1].r; });
  }
  var href = function (r) { return (r[1] === "f" ? "fam.html#" : "sp.html#") + encodeURIComponent(r[2].replace(/ /g, "_")); };

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("form.hs"), input = form && form.querySelector("input");
    if (!input) return;
    form.style.position = "relative";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", "hs-list");
    var box = document.createElement("ul");
    box.id = "hs-list";
    box.className = "hs-list";
    box.setAttribute("role", "listbox");
    box.hidden = true;
    form.appendChild(box);
    var st = document.createElement("style");
    st.textContent = ".hs-list{position:absolute;left:0;right:0;top:calc(100% + 4px);z-index:50;list-style:none;margin:0;padding:4px;" +
      "background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.18)}" +
      ".hs-list li a{display:flex;align-items:baseline;gap:8px;padding:7px 10px;border-radius:6px;color:var(--ink);text-decoration:none;font-size:14px}" +
      ".hs-list li a:hover,.hs-list li a.on{background:var(--moss-soft)}" +
      ".hs-list .rk{font-size:11px;color:var(--muted);min-width:18px}.hs-list .s{color:var(--muted);font-size:12.5px;font-style:italic;" +
      "overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hs-list .al{color:var(--muted);font-size:12px}";
    document.head.appendChild(st);
    var items = [], cur = -1, tmr;
    function draw() {
      var q = input.value, k = key(q);
      items = top5(q);
      cur = -1;
      if (!items.length) { box.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
      box.innerHTML = items.map(function (r, i) {
        var byLabel = function (l) { return (r[10] || []).filter(function (x) { return x[0] === l; }); };
        var alias = byLabel("국내 유통명").concat(byLabel("환경부 지정명"), (r[7] || []).map(function (x) { return ["아종", x[1]]; }))
          .filter(function (x) { return x[1] && key(x[1]).indexOf(k) >= 0 && key(r[3]).indexOf(k) < 0; })[0];
        return '<li role="option"><a href="' + href(r) + '" data-i="' + i + '"><span class="rk">' + RK[r[1]] + "</span><b>" +
          esc(r[3] || r[4] || r[2]) + "</b>" + (alias ? '<span class="al">' + esc(alias[1]) + "</span>" : "") +
          '<span class="s">' + esc(r[2]) + "</span></a></li>";
      }).join("");
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function mark() {
      Array.prototype.forEach.call(box.querySelectorAll("a"), function (a, i) { a.classList.toggle("on", i === cur); });
    }
    input.addEventListener("focus", function () { load(); });
    input.addEventListener("input", function () {
      clearTimeout(tmr);
      tmr = setTimeout(function () { (rows ? Promise.resolve() : load()).then(draw); }, 100);
    });
    input.addEventListener("keydown", function (e) {
      if (box.hidden) return;
      if (e.key === "ArrowDown") { cur = Math.min(items.length - 1, cur + 1); mark(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { cur = Math.max(-1, cur - 1); mark(); e.preventDefault(); }
      else if (e.key === "Enter" && cur >= 0) { location.href = href(items[cur]); box.hidden = true; e.preventDefault(); }
      else if (e.key === "Escape") { box.hidden = true; }
    });
    box.addEventListener("click", function () { box.hidden = true; input.blur(); });
    document.addEventListener("click", function (e) { if (!form.contains(e.target)) box.hidden = true; });
  });
})();
