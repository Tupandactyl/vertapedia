// 분류 나무: 목 > 과 > 속 > 종. Wegener's Dream 의 환경 나무처럼 ▸/▾ 로 접고 편다.
// 자료는 data/tree.json — { A: [목...], R: [목...] }
//   목 = [학명, 국명, [과...]], 과 = [학명, 국명, [속...]], 속 = [학명, 국명, [종...]]
//   종 = [학명, 국명, 영명, 사진있음]
// 아래 단계는 펼칠 때 그린다(종이 2만 개가 넘는다).
(function () {
  var esc = function (t) {
    return String(t == null ? "" : t).replace(/[<>&"]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c];
    });
  };
  var RANK = ["목", "과", "속", "종"];
  var GROUP = { A: "조류", R: "파충류" };

  function count(n, depth) {
    if (depth === 3) return 1;
    if (n._n == null) n._n = n[2].reduce(function (s, c) { return s + count(c, depth + 1); }, 0);
    return n._n;
  }

  function row(n, depth, current) {
    var el = document.createElement("div");
    el.className = "tnode d" + depth;
    if (depth === 3) {
      var sci = n[0], label = n[1] || n[2] || sci;
      var cur = sci === current ? " current" : "";
      el.innerHTML = '<div class="trow leaf' + cur + '"><span class="ttog-sp"></span>' +
        '<a href="sp.html#' + esc(sci.replace(/ /g, "_")) + '"' + (cur ? ' aria-current="page"' : "") + ">" +
        '<span class="tname' + (n[1] ? "" : " en") + '">' + esc(label) + "</span> " +
        '<span class="torig"><i>' + esc(sci) + "</i></span></a>" +
        (n[3] ? '<span class="tpic" title="사진 있음">●</span>' : "") + "</div>";
      return el;
    }
    var italic = depth === 2;
    el.innerHTML = '<div class="trow"><button type="button" class="ttog" aria-expanded="false" aria-label="펼치기">▸</button>' +
      '<span class="trank">' + RANK[depth] + "</span>" +
      '<span class="tname">' + esc(n[1] || n[0]) + "</span> " +
      (n[1] ? '<span class="torig">' + (italic ? "<i>" + esc(n[0]) + "</i>" : esc(n[0])) + "</span>" : "") +
      '<small class="tn">' + count(n, depth).toLocaleString() + "</small></div>" +
      '<div class="tkids" hidden></div>';
    var tog = el.querySelector(".ttog"), kids = el.querySelector(".tkids");
    var drawn = false;
    el._open = function (on) {
      if (on && !drawn) {
        n[2].forEach(function (c) { kids.appendChild(row(c, depth + 1, current)); });
        drawn = true;
      }
      kids.hidden = !on;
      tog.textContent = on ? "▾" : "▸";
      tog.setAttribute("aria-expanded", String(on));
      tog.setAttribute("aria-label", on ? "접기" : "펼치기");
    };
    tog.addEventListener("click", function () { el._open(kids.hidden); });
    el.querySelector(".tname").addEventListener("click", function () { el._open(kids.hidden); });
    return el;
  }

  // box 에 나무를 그린다. opts.groups: ["A","R"], opts.current: 지금 종의 학명(그 경로를 펴 둔다)
  window.VTree = function (box, data, opts) {
    opts = opts || {};
    box.innerHTML = "";
    var path = null;
    (opts.groups || ["A", "R"]).forEach(function (g) {
      if (!data[g]) return;
      var head = document.createElement("div");
      head.className = "tgroup";
      var total = data[g].reduce(function (s, o) { return s + count(o, 0); }, 0);
      head.innerHTML = "<b>" + GROUP[g] + '</b> <small class="tn">' + total.toLocaleString() + "종</small>";
      box.appendChild(head);
      data[g].forEach(function (o, oi) {
        var el = row(o, 0, opts.current);
        box.appendChild(el);
        if (!opts.current || path) return;
        o[2].forEach(function (f, fi) {
          f[2].forEach(function (ge, gi) {
            ge[2].forEach(function (s) { if (s[0] === opts.current) path = [el, fi, gi]; });
          });
        });
      });
    });
    if (path) {  // 지금 종까지 펴고 그 칸이 보이게
      var oEl = path[0];
      oEl._open(true);
      var fEl = oEl.querySelector(".tkids").children[path[1]];
      fEl._open(true);
      var gEl = fEl.querySelector(".tkids").children[path[2]];
      gEl._open(true);
      var cur = gEl.querySelector(".current");
      if (cur && opts.scroll !== false) {
        var top = cur.offsetTop - box.offsetTop - box.clientHeight / 3;
        box.scrollTop = Math.max(0, top);
      }
    }
  };
})();
