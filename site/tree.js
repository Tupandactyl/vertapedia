// 분류군: 목 > (아목) > (상과) > 과 > (아과) > 속 > (아속) > 종. Wegener's Dream 의 환경 목록처럼 ▸/▾ 로 접고 편다.
// 자료는 data/tree.json — { A: [...], R: [...] }
//   마디 = [계급(o 목·u 아목·p 상과·f 과·s 아과·g 속·h 아속), 학명, 국명, 자식들, (속이면) 모식종 학명]
//   종   = [학명, 국명, 영명, 사진있음]
// 아래 단계는 펼칠 때 그린다(종이 2만 개가 넘는다). 과 이름은 과 문서, 속 이름은 모식종 문서로 가는 링크다.
(function () {
  var esc = function (t) {
    return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c];
    });
  };
  var RANK = { o: "목", u: "아목", p: "상과", f: "과", s: "아과", g: "속", h: "아속" };
  var GROUP = { A: "조류", R: "파충류" };
  var OPEN_FIRST = { Squamata: 1 };  // 처음부터 펴 두는 목(유린목)
  var isLeaf = function (n) { return !Array.isArray(n[3]); };
  var href = function (page, sci) {
    var s = encodeURIComponent(sci.replace(/ /g, "_"));
    return page === "sp" ? "sp/" + s + ".html" : page + ".html#" + s;
  };

  function count(n) {
    if (isLeaf(n)) return 1;
    if (n._n == null) n._n = n[3].reduce(function (s, c) { return s + count(c); }, 0);
    return n._n;
  }

  function leaf(n, current) {
    var el = document.createElement("div");
    var sci = n[0], cur = sci === current ? " current" : "";
    el.className = "tnode";
    el.innerHTML = '<div class="trow leaf' + cur + '"><span class="ttog-sp"></span>' +
      '<a href="' + href("sp", sci) + '"' + (cur ? ' aria-current="page"' : "") + ">" +
      '<span class="tname' + (n[1] ? "" : " en") + '">' + esc(n[1] || n[2] || sci) + "</span> " +
      '<span class="torig"><i>' + esc(sci) + "</i></span></a>" +
      (n[4 - 1] ? '<span class="tpic" title="사진 있음">●</span>' : "") + "</div>";
    return el;
  }

  function branch(n, current) {
    if (isLeaf(n)) return leaf(n, current);
    var rank = n[0], sci = n[1], ko = n[2];
    var el = document.createElement("div");
    el.className = "tnode r-" + rank;
    var italic = rank === "g" || (rank === "h" && /^[A-Z]/.test(sci)), isCur = rank === "f" && sci === current;
    var label = '<span class="tname">' + (!ko && italic ? "<i>" + esc(sci) + "</i>" : esc(ko || sci)) + "</span> " +
      (ko ? '<span class="torig">' + (italic ? "<i>" + esc(sci) + "</i>" : esc(sci)) + "</span>" : "");
    // 과 이름 → 과 문서, 속 이름 → 그 속의 모식종 문서(n[4])
    var typeSp = rank === "g" ? n[4] : null;
    var linked = (rank === "f" && /^[A-Z]/.test(sci)) || !!typeSp;
    var to = typeSp ? href("sp", typeSp) : href("fam", sci);
    el.innerHTML = '<div class="trow' + (isCur ? " current" : "") + '">' +
      '<button type="button" class="ttog" aria-expanded="false" aria-label="펼치기">▸</button>' +
      '<span class="trank">' + RANK[rank] + "</span>" +
      (linked ? '<a href="' + to + '"' + (typeSp ? ' title="모식종: ' + esc(typeSp) + '"' : "") +
        (isCur ? ' aria-current="page"' : "") + ">" + label + "</a>" : label) +
      '<small class="tn">' + count(n).toLocaleString() + "</small></div>" +
      '<div class="tkids" hidden></div>';
    var tog = el.querySelector(".ttog"), kids = el.querySelector(".tkids");
    var drawn = false;
    el._open = function (on) {
      if (on && !drawn) {
        n[3].forEach(function (c) { kids.appendChild(branch(c, current)); });
        drawn = true;
      }
      kids.hidden = !on;
      tog.textContent = on ? "▾" : "▸";
      tog.setAttribute("aria-expanded", String(on));
      tog.setAttribute("aria-label", on ? "접기" : "펼치기");
    };
    tog.addEventListener("click", function () { el._open(kids.hidden); });
    if (!linked) el.querySelector(".tname").addEventListener("click", function () { el._open(kids.hidden); });
    return el;
  }

  // 지금 문서(종 학명 또는 과 학명)까지 가는 자식 번호들
  function findPath(list, target) {
    for (var i = 0; i < list.length; i++) {
      var n = list[i];
      if (isLeaf(n)) { if (n[0] === target) return [i]; continue; }
      if (n[0] === "f" && n[1] === target) return [i];
      var sub = findPath(n[3], target);
      if (sub) return [i].concat(sub);
    }
    return null;
  }

  // 아무 분류군(종·속·과·목 …)까지 가는 자식 번호들
  function findAny(list, target) {
    for (var i = 0; i < list.length; i++) {
      var n = list[i];
      if (isLeaf(n)) { if (n[0] === target) return [i]; continue; }
      if (n[1] === target) return [i];
      var sub = findAny(n[3], target);
      if (sub) return [i].concat(sub);
    }
    return null;
  }

  // 분류군 찾기 색인: 국명·학명·영명(종)
  var IDX = null, IDX_OF = null;
  function index(data) {
    if (IDX && IDX_OF === data) return IDX;
    var out = [];
    ["A", "R"].forEach(function (g) {
      (function walk(list) {
        list.forEach(function (n) {
          if (isLeaf(n)) { out.push({ g: g, r: "sp", sci: n[0], ko: n[1] || "", en: n[2] || "" }); return; }
          if (n[0] !== "h") out.push({ g: g, r: n[0], sci: n[1], ko: n[2] || "", en: "" });
          walk(n[3]);
        });
      })(data[g] || []);
    });
    out.forEach(function (x) { x.k = (x.ko + "\u0001" + x.sci + "\u0001" + x.en).toLowerCase(); });
    IDX = out; IDX_OF = data;
    return out;
  }
  var RORD = { o: 0, u: 1, p: 2, f: 3, s: 4, g: 5, sp: 6 };
  function search(data, q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    var hits = [];
    index(data).forEach(function (x) {
      var i = x.k.indexOf(q);
      if (i < 0) return;
      var exact = x.ko.toLowerCase() === q || x.sci.toLowerCase() === q || x.en.toLowerCase() === q;
      var head = i === 0 || x.k.charAt(i - 1) === "\u0001" || x.k.charAt(i - 1) === " ";
      hits.push({ x: x, s: (exact ? 0 : head ? 1 : 2) * 10 + RORD[x.r] });
    });
    hits.sort(function (a, b) { return a.s - b.s || a.x.k.length - b.x.k.length; });
    return hits.slice(0, 10).map(function (h) { return h.x; });
  }

  // box 에 나무를 그린다. opts.groups: ["A","R"](이 순서로), opts.current: 지금 종 또는 과의 학명(그 경로를 펴 둔다),
  // opts.folded: 처음에 접어 둘 강(펼칠 때 그린다)
  // 분류군 창 너비: 창과 본문 사이의 손잡이(.navgrip)를 끌어 조절한다. 이 브라우저에 기억하고, 두 번 누르면 처음 너비(270px).
  // 키보드: 손잡이에 초점을 두고 ←/→ 로 20px씩.
  (function () {
    var page = document.querySelector(".page"), nav = page && page.querySelector(".navtree");
    if (!nav) return;
    var MIN = 180, MAX = 640, KEY = "vp-navw";
    var grip = document.createElement("div");
    grip.className = "navgrip";
    grip.tabIndex = 0;
    grip.title = "끌어서 너비 조절 · 두 번 누르면 처음 너비로";
    [["role", "separator"], ["aria-orientation", "vertical"], ["aria-label", "분류군 창 너비"],
     ["aria-valuemin", MIN], ["aria-valuemax", MAX], ["aria-valuenow", 270]].forEach(function (a) { grip.setAttribute(a[0], a[1]); });
    nav.parentNode.insertBefore(grip, nav.nextSibling);
    var set = function (w, save) {
      var max = Math.max(MIN, Math.min(MAX, page.clientWidth - 460));  // 본문이 너무 좁아지지 않게
      w = Math.round(Math.max(MIN, Math.min(max, w)));
      page.style.setProperty("--navw", w + "px");
      grip.setAttribute("aria-valuenow", w);
      if (save) try { localStorage.setItem(KEY, w); } catch (e) {}
    };
    try { var saved = +localStorage.getItem(KEY); if (saved) set(saved); } catch (e) {}
    grip.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      grip.setPointerCapture(e.pointerId);
      grip.classList.add("drag");
      document.body.classList.add("resizing");
      var left = nav.getBoundingClientRect().left;
      var noSelect = function (ev) { ev.preventDefault(); };  // 끄는 동안 글자가 선택되지 않게
      document.addEventListener("selectstart", noSelect);
      var sel = window.getSelection && window.getSelection();
      if (sel) sel.removeAllRanges();
      var move = function (ev) { set(ev.clientX - left); };
      var up = function () {
        document.removeEventListener("selectstart", noSelect);
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        grip.classList.remove("drag");
        document.body.classList.remove("resizing");
        set(nav.getBoundingClientRect().width, true);
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    });
    grip.addEventListener("mousedown", function (e) { e.preventDefault(); });
    grip.addEventListener("dblclick", function () {
      page.style.removeProperty("--navw");
      grip.setAttribute("aria-valuenow", 270);
      try { localStorage.removeItem(KEY); } catch (e) {}
    });
    grip.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowLeft" ? -20 : e.key === "ArrowRight" ? 20 : 0;
      if (!d) return;
      e.preventDefault();
      set(nav.getBoundingClientRect().width + d, true);
    });
  })();

  // 보기 전환: 서랍(린네식 분류) | 분기도(phylo.js, 조류·파충류). 고른 보기는 이 브라우저에 기억한다.
  var MODE_KEY = "vp-treemode";
  var getMode = function () { try { return localStorage.getItem(MODE_KEY) === "phylo" ? "phylo" : "drawer"; } catch (e) { return "drawer"; } };
  var BASE = (document.currentScript && document.currentScript.src || "").replace(/tree\.js(\?.*)?$/, "");
  var phyloLoading = null;
  var loadPhylo = function () {
    return phyloLoading || (phyloLoading = new Promise(function (ok, no) {
      var s = document.createElement("script"); s.src = BASE + "phylo.js"; s.onload = ok; s.onerror = no; document.head.appendChild(s);
    }));
  };

  window.VTree = function (box, data, opts) {
    opts = opts || {};
    var mode = getMode();
    box.innerHTML = '<div class="tbar"><div class="tmode" role="group" aria-label="분류군 보기">' +
      '<button type="button" data-m="drawer" aria-pressed="' + (mode === "drawer") + '">서랍</button>' +
      '<button type="button" data-m="phylo" aria-pressed="' + (mode === "phylo") + '">분기도</button></div>' +
      '<input class="tsearch" type="search" placeholder="분류군 찾기" aria-label="분류군 찾기" autocomplete="off" spellcheck="false">' +
      '<div class="tsugg" role="listbox" hidden></div></div>';
    (function () {  // 분류군 찾기: 고르면 지금 보기(서랍·분기도)에서 그 자리로 간다
      var inp = box.querySelector(".tsearch"), sug = box.querySelector(".tsugg"), list = [], sel = -1;
      var go = function (x) {
        var o2 = {}; for (var k in opts) o2[k] = opts[k];
        o2.focus = x; o2.phyloGroup = x.g;
        o2.folded = (opts.folded || []).filter(function (g) { return g !== x.g; });
        window.VTree(box, data, o2);
      };
      var paint = function () {
        sug.hidden = !list.length;
        sug.innerHTML = list.map(function (x, i) {
          var nm = x.ko || (x.r === "sp" ? x.en : "") || x.sci;
          return '<button type="button" role="option" data-i="' + i + '" aria-selected="' + (i === sel) + '">' +
            '<span class="trank">' + (x.r === "sp" ? "종" : RANK[x.r]) + "</span>" + esc(nm) +
            (nm !== x.sci ? ' <i class="torig">' + esc(x.sci) + "</i>" : "") + '<small class="tn">' + GROUP[x.g] + "</small></button>";
        }).join("");
      };
      inp.addEventListener("input", function () { list = search(data, inp.value); sel = list.length ? 0 : -1; paint(); });
      inp.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          if (!list.length) return;
          e.preventDefault();
          sel = (sel + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length; paint();
        } else if (e.key === "Enter") {
          if (sel >= 0 && list[sel]) { e.preventDefault(); go(list[sel]); }
        } else if (e.key === "Escape") { list = []; paint(); }
      });
      sug.addEventListener("mousedown", function (e) { e.preventDefault(); });
      sug.addEventListener("click", function (e) {
        var b = e.target.closest("button[data-i]"); if (b) go(list[+b.dataset.i]);
      });
      inp.addEventListener("blur", function () { setTimeout(function () { list = []; paint(); }, 150); });
    })();
    box.querySelectorAll(".tmode button").forEach(function (b) {
      b.onclick = function () {
        if (b.dataset.m === getMode()) return;
        try { localStorage.setItem(MODE_KEY, b.dataset.m); } catch (e) {}
        window.VTree(box, data, opts);
      };
    });
    var inner = document.createElement("div");
    box.appendChild(inner);
    if (mode === "phylo") {
      var groups = (opts.groups || ["A", "R"]).filter(function (g) { return data[g]; });
      var GKEY = "vp-phylo-group", pg = groups[0];
      if (!opts.current) { try { var sg = localStorage.getItem(GKEY); if (groups.indexOf(sg) >= 0) pg = sg; } catch (e) {} }
      if (opts.phyloGroup && groups.indexOf(opts.phyloGroup) >= 0) pg = opts.phyloGroup;
      if (groups.length > 1) {
        var gs = document.createElement("div");
        gs.className = "tmode tgrp"; gs.setAttribute("role", "group"); gs.setAttribute("aria-label", "분기도 무리");
        gs.innerHTML = groups.map(function (g) { return '<button type="button" data-g="' + g + '" aria-pressed="' + (g === pg) + '">' + GROUP[g] + "</button>"; }).join("");
        inner.appendChild(gs);
        gs.querySelectorAll("button").forEach(function (b) {
          b.onclick = function () {
            if (b.dataset.g === pg) return;
            try { localStorage.setItem(GKEY, b.dataset.g); } catch (e) {}
            var o2 = {}; for (var k in opts) o2[k] = opts[k];
            o2.phyloGroup = b.dataset.g;
            window.VTree(box, data, o2);
          };
        });
      }
      var pbox = document.createElement("div");
      inner.appendChild(pbox);
      pbox.innerHTML = '<p class="pnote">분기도를 불러오는 중…</p>';
      loadPhylo().then(function () {
        window.VPhylo(pbox, data, { group: pg, current: pg === groups[0] ? opts.current : null,
                                    focus: opts.focus && opts.focus.g === pg ? opts.focus : null });
      }, function () { pbox.innerHTML = '<p class="pnote">분기도를 불러오지 못했습니다.</p>'; });
      return;
    }
    drawer(inner, data, opts);
    var hitEl = inner.querySelector(".trow.hit");
    if (hitEl) { hitEl.scrollIntoView({ block: "center" }); return; }
    var curEl = inner.querySelector(".current");
    if (curEl && opts.scroll !== false) box.scrollTop = Math.max(0, curEl.offsetTop - box.offsetTop - box.clientHeight / 3);
  };

  function drawer(box, data, opts) {
    var opened = null, tops_by = {};
    (opts.groups || ["A", "R"]).forEach(function (g) {
      if (!data[g]) return;
      var head = document.createElement("div");
      head.className = "tgroup";
      var total = data[g].reduce(function (s, o) { return s + count(o); }, 0);
      var folded = (opts.folded || []).indexOf(g) >= 0;
      head.innerHTML = '<button type="button" class="ttog" aria-expanded="' + !folded + '">' + (folded ? "▸" : "▾") + "</button><b>" +
        GROUP[g] + '</b> <small class="tn">' + total.toLocaleString() + "종</small>";
      box.appendChild(head);
      var body = document.createElement("div");
      body.hidden = folded;
      box.appendChild(body);
      var tops = null;
      var draw = function () {
        if (tops) return;
        tops = data[g].map(function (o) {
          var el = branch(o, opts.current);
          body.appendChild(el);
          if (OPEN_FIRST[o[1]]) el._open(true);
          return el;
        });
        tops_by[g] = tops;
      };
      head.addEventListener("click", function () {
        draw();
        body.hidden = !body.hidden;
        var tog = head.querySelector(".ttog");
        tog.textContent = body.hidden ? "▸" : "▾";
        tog.setAttribute("aria-expanded", String(!body.hidden));
      });
      if (folded) return;
      draw();
      var path = opts.current && !opened ? findPath(data[g], opts.current) : null;
      if (!path) return;
      var el = tops[path[0]];
      for (var k = 1; k <= path.length; k++) {
        if (el._open && (k < path.length || el.classList.contains("r-f"))) el._open(true);
        if (k < path.length) el = el.querySelector(".tkids").children[path[k]];
      }
      opened = el;
    });
    // 찾은 분류군: 조상들을 펴고 그 줄을 표시한다
    var f = opts.focus;
    if (f && tops_by[f.g]) {
      var p2 = findAny(data[f.g], f.sci);
      if (p2) {
        var e2 = tops_by[f.g][p2[0]];
        for (var j = 1; j < p2.length; j++) {
          if (e2._open) e2._open(true);
          e2 = e2.querySelector(".tkids").children[p2[j]];
        }
        var row = e2 && e2.querySelector(".trow");
        if (row) row.classList.add("hit");
      }
    }
  }
})();
