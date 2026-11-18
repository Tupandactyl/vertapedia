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
    box.innerHTML = '<div class="tmode" role="group" aria-label="분류군 보기">' +
      '<button type="button" data-m="drawer" aria-pressed="' + (mode === "drawer") + '">서랍</button>' +
      '<button type="button" data-m="phylo" aria-pressed="' + (mode === "phylo") + '">분기도</button></div>';
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
        window.VPhylo(pbox, data, { group: pg, current: pg === groups[0] ? opts.current : null });
      }, function () { pbox.innerHTML = '<p class="pnote">분기도를 불러오지 못했습니다.</p>'; });
      return;
    }
    drawer(inner, data, opts);
    var curEl = inner.querySelector(".current");
    if (curEl && opts.scroll !== false) box.scrollTop = Math.max(0, curEl.offsetTop - box.offsetTop - box.clientHeight / 3);
  };

  function drawer(box, data, opts) {
    var opened = null;
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
  }
})();
