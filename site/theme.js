// 화면 모드: 자동(기기 설정) · 밝게 · 어둡게. 고른 값은 이 브라우저에 기억한다(localStorage 'vp-theme').
// <head> 맨 앞에서 불러야 깜빡임 없이 적용된다. 머리 메뉴(header nav)에 작은 단추를 붙인다.
(function () {
  var KEY = "vp-theme", MODES = ["auto", "light", "dark"];
  var LABEL = { auto: "◐ 자동", light: "☀ 밝게", dark: "☾ 어둡게" };
  var get = function () { try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; } };
  var apply = function (m) {
    if (m === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", m);
  };
  apply(get());
  document.addEventListener("DOMContentLoaded", function () {
    var nav = document.querySelector("header nav");
    if (!nav) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "themetog";
    var show = function () {
      var m = get();
      b.textContent = LABEL[m];
      b.title = "화면 모드: " + LABEL[m].slice(2) + " (누르면 바뀜)";
      b.setAttribute("aria-label", b.title);
    };
    b.onclick = function () {
      var m = MODES[(MODES.indexOf(get()) + 1) % MODES.length];
      try { localStorage.setItem(KEY, m); } catch (e) {}
      apply(m);
      show();
    };
    show();
    nav.appendChild(b);
    var st = document.createElement("style");
    st.textContent = ".themetog{font:inherit;font-size:12px;color:var(--muted);background:none;border:1px solid var(--line);" +
      "border-radius:999px;padding:1px 9px;cursor:pointer;white-space:nowrap}.themetog:hover{color:var(--ink);border-color:var(--moss)}";
    document.head.appendChild(st);
  });
})();
