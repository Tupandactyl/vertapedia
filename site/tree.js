// 분류군: 목 > (아목) > 과 > 속 > 종. Wegener's Dream 의 환경 목록처럼 ▸/▾ 로 접고 편다.
// 자료는 data/tree.json — { A: [...], R: [...] }
//   마디 = [계급(o 목·u 아목·f 과·g 속), 학명, 국명, 자식들]
//   종   = [학명, 국명, 영명, 사진있음]
// 아래 단계는 펼칠 때 그린다(종이 2만 개가 넘는다). 과 이름은 과 문서로 가는 링크다.
(function () {
  var esc = function (t) {
    return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c];
    });
  };
  var RANK = { o: "목", u: "아목", f: "과", g: "속" };
  var GROUP = { A: "조류", R: "파충류" };
  var isLeaf = function (n) { return !Array.isArray(n[3]); };
  var href = function (page, sci) { return page + ".html#" + encodeURIComponent(sci.replace(/ /g, "_")); };

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
    var italic = rank === "g", isCur = rank === "f" && sci === current;
    var label = '<span class="tname">' + esc(ko || sci) + "</span> " +
      (ko ? '<span class="torig">' + (italic ? "<i>" + esc(sci) + "</i>" : esc(sci)) + "</span>" : "");
    var linked = rank === "f" && sci.charAt(0) !== "(";
    el.innerHTML = '<div class="trow' + (isCur ? " current" : "") + '">' +
      '<button type="button" class="ttog" aria-expanded="false" aria-label="펼치기">▸</button>' +
      '<span class="trank">' + RANK[rank] + "</span>" +
      (linked ? '<a href="' + href("fam", sci) + '"' + (isCur ? ' aria-current="page"' : "") + ">" + label + "</a>" : label) +
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

  // box 에 나무를 그린다. opts.groups: ["A","R"], opts.current: 지금 종 또는 과의 학명(그 경로를 펴 둔다)
  window.VTree = function (box, data, opts) {
    opts = opts || {};
    box.innerHTML = "";
    var opened = null;
    (opts.groups || ["A", "R"]).forEach(function (g) {
      if (!data[g]) return;
      var head = document.createElement("div");
      head.className = "tgroup";
      var total = data[g].reduce(function (s, o) { return s + count(o); }, 0);
      head.innerHTML = "<b>" + GROUP[g] + '</b> <small class="tn">' + total.toLocaleString() + "종</small>";
      box.appendChild(head);
      var tops = data[g].map(function (o) { var el = branch(o, opts.current); box.appendChild(el); return el; });
      var path = opts.current && !opened ? findPath(data[g], opts.current) : null;
      if (!path) return;
      var el = tops[path[0]];
      for (var k = 1; k <= path.length; k++) {
        if (el._open && (k < path.length || el.classList.contains("r-f"))) el._open(true);
        if (k < path.length) el = el.querySelector(".tkids").children[path[k]];
      }
      opened = el;
    });
    var cur = box.querySelector(".current");
    if (cur && opts.scroll !== false) box.scrollTop = Math.max(0, cur.offsetTop - box.offsetTop - box.clientHeight / 3);
  };
})();
