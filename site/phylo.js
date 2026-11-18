// 분기도: 분류군 창의 '분기도' 보기. tree.js 가 처음 쓸 때 불러온다.
// 자료 data/phylo_A.json(조류: Birds of the World Phylogeny Explorer 와 같은 나무, clootl)
//      data/phylo_R.json(파충류: 논문 나무 여럿을 이어 붙인 것). 둘 다 scripts/build_phylo.py 가 만든다.
// 보는 법은 Birds of the World 를 따른다.
//  - 가로축은 시간(백만 년 전). 기본은 제곱근 눈금이라 최근 갈래에 자리를 더 준다.
//  - 끝을 목·과·속·종 가운데 하나로 접는다. 접힌 끝이나 이름 붙은 마디를 누르면 그 무리를 뿌리로 다시 그린다.
//  - 목·과·속 이름은 그 무리 모든 종의 가장 가까운 공통 조상 마디에 붙인다.
//    그 마디 아래에 다른 무리의 종이 섞여 있으면 단계통이 아니므로 주황색으로 표시한다.
//  - 유전자 자료 없이 둔 종은 점선으로 그린다: 파충류 유린목은 Title et al. 2024 imputed 나무의 속별 빈자리,
//    그 밖에는 같은 속(없으면 아과·과) 곁. 어느 쪽이든 위치는 추정이다.
//  - 형제 가지의 위아래 순서는 시트(분류 목록) 순서에 맞춘다.
(function () {
  var esc = function (t) {
    return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c];
    });
  };
  var RANKS = ["o", "u", "p", "f", "s", "g"], RK = { o: "목", u: "아목", p: "상과", f: "과", s: "아과", g: "속", sp: "종" };
  var GROUP = { A: "조류", R: "파충류" };
  var NEXT = { o: "f", u: "f", p: "f", f: "sp", s: "sp", g: "sp", sp: "sp" };
  var ROW = 19, TOP = 26, KEY = "vp-phylo";
  var store = function (k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(KEY) || "{}")[k]; var o = JSON.parse(localStorage.getItem(KEY) || "{}"); o[k] = v; localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} };

  // ---- 자료 준비(한 번) ----
  var PS = {}, P = null;
  function prepare(raw, tree, G) {
    // 사이트 분류: 종 → 목·과·속, 분류군 → 국명
    var sp = {}, tx = { o: {}, u: {}, p: {}, f: {}, s: {}, g: {} };
    (function walk(list, path) {
      list.forEach(function (n) {
        if (!Array.isArray(n[3])) { var q = { ko: n[1], en: n[2], pic: n[3] }; RANKS.forEach(function (r) { q[r] = path[r]; }); sp[n[0]] = q; return; }
        var p = {}; RANKS.forEach(function (r) { p[r] = path[r]; });
        if (tx[n[0]]) { p[n[0]] = n[1]; tx[n[0]][n[1]] = { ko: n[2], sci: n[1], rank: n[0] }; }
        walk(n[3], p);
      });
    })(tree[G] || [], {});

    // Newick 읽기
    var s = raw.nwk, i = 0, root = { k: [] }, cur = root, stack = [], nodes = [];
    var tok = function () { var j = i; while (j < s.length && "(),;".indexOf(s[j]) < 0) j++; var t = s.slice(i, j); i = j; return t; };
    var setTok = function (n, t) {
      var c = t.lastIndexOf(":"), name = c >= 0 ? t.slice(0, c) : t;
      n.bl = c >= 0 ? +t.slice(c + 1) : 0;
      if (name) { n.star = name.slice(-1) === "*"; n.name = name.replace(/\*$/, "").replace(/_/g, " "); }
    };
    while (i < s.length) {
      var ch = s[i];
      if (ch === "(") { var k = { k: [], up: cur }; cur.k.push(k); stack.push(cur); cur = k; i++; }
      else if (ch === ",") { var par = stack[stack.length - 1], k2 = { k: [], up: par }; par.k.push(k2); cur = k2; i++; }
      else if (ch === ")") { cur = stack.pop(); i++; }
      else if (ch === ";") break;
      else setTok(cur, tok());
    }
    if (root.k.length === 1 && !root.name) { root = root.k[0]; root.up = null; }

    // 나이, 끝 순번, 단일 분류군 여부(pure), 끝 수
    var tips = [];
    (function down(n, depth) {
      n.d = depth + (n.up ? n.bl : 0);
      nodes.push(n);
      if (!n.k.length) { n.lo = n.hi = tips.length; n.n = 1; n.info = sp[n.name] || {}; tips.push(n); n.pure = {}; RANKS.forEach(function (r) { n.pure[r] = n.info[r] || null; }); return; }
      n.k.forEach(function (c) { down(c, n.d); });
      n.lo = n.k[0].lo; n.hi = n.k[n.k.length - 1].hi; n.n = n.hi - n.lo + 1;
      n.pure = {};
      RANKS.forEach(function (r) {
        var v = n.k[0].pure[r];
        for (var j = 1; j < n.k.length && v; j++) if (n.k[j].pure[r] !== v) v = null;
        n.pure[r] = v || null;
      });
    })(root, 0);
    var H = 0; tips.forEach(function (t) { if (t.d > H) H = t.d; });
    nodes.forEach(function (n) { n.age = Math.max(0, H - n.d); });

    // 분류군마다 공통 조상 마디와 단계통 여부
    var span = {}, byTip = {};
    tips.forEach(function (t, k) {
      byTip[t.name] = t;
      RANKS.forEach(function (r) {
        var v = t.info[r]; if (!v) return;
        var key = r + ":" + v, sp2 = span[key] || (span[key] = { r: r, sci: v, lo: k, hi: k, n: 0 });
        sp2.hi = k; sp2.n++;
      });
    });
    var taxa = {};
    Object.keys(span).forEach(function (key) {
      var t = span[key], a = tips[t.lo];
      while (a.up && a.hi < t.hi) a = a.up;
      t.node = a; t.mono = a.n === t.n;
      var m = tx[t.r][t.sci]; t.ko = m ? m.ko : "";
      (a.labels || (a.labels = [])).push(t);
      taxa[key] = t;
    });
    nodes.forEach(function (n) { if (n.labels) n.labels.sort(function (x, y) { return RANKS.indexOf(x.r) - RANKS.indexOf(y.r); }); });
    return { G: G, root: root, tips: tips, taxa: taxa, byTip: byTip, src: raw.src, cite: raw.cite || "", add: raw.add, imp: raw.imp || 0 };
  }

  // ---- 그리기 ----
  function shown(n, level, top) {
    // 지금 보이는 나무: 끝 단계(level)로 접는다. 뿌리 자체는 접지 않는다.
    if (!top && level !== "sp" && n.pure[level]) return { tip: true, node: n, taxon: P.taxa[level + ":" + n.pure[level]] };
    if (!n.k.length) return { tip: true, node: n };
    return { node: n, k: n.k.map(function (c) { return shown(c, level); }) };
  }

  function nameOf(t) { return t ? (t.ko || t.sci) : GROUP[P.G]; }

  function draw(box, st, opts) {
    P = st.P;
    var root = st.root, level = st.level;
    var cur = opts.current;
    var vis = shown(root, level, true), rows = [];
    (function lay(v) {
      if (v.tip) { v.y = TOP + rows.length * ROW + ROW / 2; rows.push(v); return; }
      v.k.forEach(lay);
      v.y = (v.k[0].y + v.k[v.k.length - 1].y) / 2;
    })(vis);

    var W = Math.max(220, box.clientWidth || 260);
    // 이름 칸은 가장 긴 이름만큼만 두고 나머지 폭은 모두 나무에 준다(넓은 화면에서 오른쪽이 비지 않게)
    var tw = function (str, fs) { var w = 0; for (var c = 0; c < str.length; c++) w += str.charCodeAt(c) > 0x1100 ? fs : fs * 0.58; return w; };
    var labW = 0;
    rows.forEach(function (v) {
      var w;
      if (v.taxon) w = tw(nameOf(v.taxon), 12.5) + tw(" " + v.node.n.toLocaleString(), 10.5);
      else { var inf = v.node.info || {}; w = tw(inf.ko || inf.en || v.node.name, 12.5); }
      if (w > labW) labW = w;
    });
    labW = Math.min(Math.max(labW + 16, 80), W * 0.6);
    var treeW = Math.round(Math.max(70, W - 6 - labW));
    var X0 = 6, X1 = X0 + treeW, rootAge = root.age || 1;
    var f = st.linear ? function (a) { return a; } : Math.sqrt;
    var x = function (age) { return X0 + (X1 - X0) * (1 - f(age) / f(rootAge)); };

    var solid = [], dashed = [], dots = [], labs = [];
    (function edges(v, px) {
      var n = v.node, nx = x(n.age);
      var seg = "M" + px.toFixed(1) + " " + v.y.toFixed(1) + "H" + (v.tip ? X1 : nx).toFixed(1);
      (n.star ? dashed : solid).push(seg);
      if (v.tip) return;
      solid.push("M" + nx.toFixed(1) + " " + v.k[0].y.toFixed(1) + "V" + v.k[v.k.length - 1].y.toFixed(1));
      var lab = (n.labels || []).filter(function (t) { return n !== root && RANKS.indexOf(t.r) < (level === "sp" ? 9 : RANKS.indexOf(level)); });
      if (lab.length) {
        dots.push('<circle class="pdot" cx="' + nx.toFixed(1) + '" cy="' + v.y.toFixed(1) + '" r="3.2" data-t="' + esc(lab[0].r + ":" + lab[0].sci) + '"><title>' +
          esc(lab.map(function (t) { return RK[t.r] + " " + nameOf(t) + " (" + t.sci + ")" + (t.mono ? "" : " · 단계통 아님"); }).join("\n")) + "</title></circle>");
        var t0 = lab[lab.length - 1];
        labs.push('<text class="plab' + (t0.mono ? "" : " poly") + '" x="' + (nx + 3).toFixed(1) + '" y="' + (v.y - 4).toFixed(1) + '" data-t="' + esc(t0.r + ":" + t0.sci) + '">' + esc(nameOf(t0)) + "</text>");
      }
      v.k.forEach(function (c) { edges(c, nx); });
    })(vis, X0);

    var ticks = [200, 100, 50, 20, 10, 5, 2, 1].filter(function (a) { return a < rootAge * 0.95; });
    var axis = ticks.map(function (a) { var ax = x(a).toFixed(1); return '<line class="pgrid" x1="' + ax + '" x2="' + ax + '" y1="' + (TOP - 6) + '" y2="' + (TOP + rows.length * ROW) + '"/><text class="ptick" x="' + ax + '" y="' + (TOP - 9) + '">' + a + "</text>"; }).join("");

    var curRow = -1;
    var tipsHtml = rows.map(function (v, k) {
      var y = v.y + 4, tx0 = X1 + 6, n = v.node;
      if (v.taxon) {
        var t = v.taxon, isCur = cur && t.sci === cur;
        if (isCur) curRow = k;
        return '<g class="ptip grp' + (isCur ? " current" : "") + '" data-t="' + esc(t.r + ":" + t.sci) + '" data-n="' + nodeId(n) + '">' +
          '<rect x="' + X1 + '" y="' + (v.y - ROW / 2) + '" width="' + (W - X1) + '" height="' + ROW + '"/>' +
          '<text x="' + tx0 + '" y="' + y + '"><tspan class="' + (t.mono ? "" : "poly") + '">' + esc(nameOf(t)) + '</tspan> <tspan class="pn">' + n.n.toLocaleString() + "</tspan></text>" +
          "<title>" + esc(RK[t.r] + " " + t.sci + (t.mono ? "" : " · 이 무리는 단계통이 아님(다른 곳에도 나뉘어 있음)")) + "</title></g>";
      }
      var inf = n.info || {}, isC = cur && n.name === cur;
      if (isC) curRow = k;
      var nm = inf.ko || inf.en || n.name;
      return '<a class="ptip' + (isC ? " current" : "") + '" href="sp/' + encodeURIComponent(n.name.replace(/ /g, "_")) + '.html">' +
        '<rect x="' + X1 + '" y="' + (v.y - ROW / 2) + '" width="' + (W - X1) + '" height="' + ROW + '"/>' +
        '<text x="' + tx0 + '" y="' + y + '"' + (inf.ko ? "" : ' class="en"') + ">" + esc(nm) + "</text>" +
        "<title>" + esc(n.name + (n.star ? " · 유전자 자료가 없어 위치를 추정해 둔 종" : "")) + "</title></a>";
    }).join("");

    var Hh = TOP + rows.length * ROW + 8;
    var svg = '<svg class="phylo" width="' + W + '" height="' + Hh + '" viewBox="0 0 ' + W + " " + Hh + '" role="img" aria-label="분기도">' +
      axis + '<text class="ptick unit" x="' + X0 + '" y="' + (TOP - 19) + '">백만 년 전</text>' +
      '<path class="pbr" d="' + solid.join("") + '"/>' + (dashed.length ? '<path class="pbr dash" d="' + dashed.join("") + '"/>' : "") +
      labs.join("") + dots.join("") + tipsHtml + "</svg>";

    // 뿌리 경로(조류 › 목 › 과 ...)
    var crumbs = [], a = root;
    while (a) {  // 단계통인 무리만 경로에 넣는다(뿌리 마디에 단계통 이름이 없으면 그 마디의 가장 높은 단계 하나)
      var ls = (a.labels || []), mono = ls.filter(function (t) { return t.mono; });
      if (!mono.length && a === root && ls.length) mono = [ls[0]];
      mono.slice().reverse().forEach(function (t) { crumbs.unshift(t); });
      a = a.up;
    }
    var seen = {};
    crumbs = crumbs.filter(function (t) { var k = t.r + t.sci; if (seen[k]) return false; seen[k] = 1; return true; });
    var bc = '<button type="button" class="pcrumb" data-root="">' + GROUP[P.G] + '</button>' + crumbs.map(function (t) {
      return ' › <button type="button" class="pcrumb" data-t="' + esc(t.r + ":" + t.sci) + '">' + esc(nameOf(t)) + "</button>";
    }).join("");

    box.innerHTML = '<div class="pbar"><div class="pcrumbs">' + bc + '</div>' +
      '<div class="plev" role="group" aria-label="끝 단계">' + ["o", "f", "g", "sp"].map(function (l) {
        return '<button type="button" data-l="' + l + '" aria-pressed="' + (l === level) + '">' + RK[l] + "</button>";
      }).join("") + '</div><label class="plin"><input type="checkbox"' + (st.linear ? " checked" : "") + "> 선형 시간</label></div>" +
      svg +
      '<p class="pkey"><span class="poly">주황</span> 단계통이 아닌 무리 · <span class="pdash"></span> 유전자 자료 없이 위치를 추정해 둔 종(' + (P.add + P.imp).toLocaleString() +
        (P.imp ? ': 그중 ' + P.imp.toLocaleString() + '종은 imputed 나무의 자리' : '') + ')</p>' +
      '<p class="psrc">' + P.cite + '</p>';

    var redraw = function () { draw(box, st, opts); };
    var reroot = function (t, lvl) { if (!t) return; st.root = t.node; st.level = lvl || NEXT[t.r]; redraw(); scrollTo(box, null); };
    box.querySelectorAll(".plev button").forEach(function (b) { b.onclick = function () { st.level = b.dataset.l; store("level", st.level); redraw(); }; });
    box.querySelector(".plin input").onchange = function (e) { st.linear = e.target.checked; store("linear", st.linear); redraw(); };
    box.querySelectorAll(".pcrumb").forEach(function (b) {
      b.onclick = function () { if (!b.dataset.t) { st.root = P.root; st.level = "o"; redraw(); return; } reroot(P.taxa[b.dataset.t], st.level === "o" ? "f" : st.level); };
    });
    box.querySelectorAll(".pdot,.plab,.ptip.grp").forEach(function (el) {
      el.addEventListener("click", function () { reroot(P.taxa[el.getAttribute("data-t")]); });
    });
    if (curRow >= 0 && st.scroll) { st.scroll = false; scrollTo(box, TOP + curRow * ROW); }
  }

  var ids = 0;
  function nodeId(n) { return n._id || (n._id = ++ids); }
  function scrollTo(box, y) {
    var sc = box; while (sc && sc !== document.body && !(sc.scrollHeight > sc.clientHeight && /auto|scroll/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
    var svg = box.querySelector("svg.phylo");
    if (!sc || sc === document.body || !svg) return;
    var off = svg.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop;
    sc.scrollTop = y == null ? Math.max(0, off - 60) : Math.max(0, off + y - sc.clientHeight / 3);
  }

  var loading = {};
  window.VPhylo = function (box, tree, opts) {
    opts = opts || {};
    var G = opts.group || "A";
    if (!PS[G]) {
      box.innerHTML = '<p class="pnote">분기도를 불러오는 중…</p>';
      loading[G] = loading[G] || fetch("data/phylo_" + G + ".json").then(function (r) { if (!r.ok) throw r; return r.json(); });
      loading[G].then(function (raw) { if (!PS[G]) PS[G] = prepare(raw, tree, G); window.VPhylo(box, tree, opts); })
        .catch(function () { box.innerHTML = '<p class="pnote">분기도 자료를 불러오지 못했습니다.</p>'; });
      return;
    }
    P = PS[G];
    var st = { P: P, root: P.root, level: store("level") || "o", linear: !!store("linear"), scroll: true };
    var cur = opts.current;
    if (cur && P.byTip[cur]) {                    // 종 문서: 그 종의 과(단계통이 아니면 목)를 뿌리로, 끝은 종
      var inf = P.byTip[cur].info, t = P.taxa["f:" + inf.f];
      if (!t || !t.mono) t = P.taxa["o:" + inf.o];
      if (t) { st.root = t.node; st.level = "sp"; }
    } else if (cur && P.taxa["f:" + cur]) {       // 과 문서: 그 과가 든 목을 뿌리로, 끝은 과
      var ft = P.taxa["f:" + cur], o = P.tips[ft.node.lo].info.o, ot = P.taxa["o:" + o];
      if (ot) st.root = ot.node;
      st.level = "f";
    }
    draw(box, st, opts);
  };
})();
