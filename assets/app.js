/* Netflux shared chrome: nav, hero, poster grid, footer. No dependencies. */
(function () {
  "use strict";

  var TITLES = [
    ["Midnight Protocol", "2024 · Thriller · 1h 58m", "linear-gradient(135deg,#3a0ca3,#7209b7)"],
    ["The Last Ray", "2023 · Sci-Fi · 2h 11m", "linear-gradient(135deg,#0d3b66,#f4a261)"],
    ["Neon Divide", "2025 · Crime · 1h 47m", "linear-gradient(135deg,#ff006e,#3a0ca3)"],
    ["Paper Empires", "2022 · Drama · 2h 03m", "linear-gradient(135deg,#264653,#e9c46a)"],
    ["Slow Fire", "2024 · Romance · 1h 39m", "linear-gradient(135deg,#6a040f,#f48c06)"],
    ["Chrome Valley", "2023 · Documentary · 1h 26m", "linear-gradient(135deg,#2b2d42,#8d99ae)"],
    ["The Understudy", "2025 · Comedy · 1h 44m", "linear-gradient(135deg,#bc6c25,#dda15e)"],
    ["Night Market", "2024 · Horror · 1h 52m", "linear-gradient(135deg,#10002b,#e07a5f)"],
    ["Static Bloom", "2022 · Indie · 1h 33m", "linear-gradient(135deg,#5f0f40,#fb8b24)"],
    ["Iron Lullaby", "2025 · Action · 2h 07m", "linear-gradient(135deg,#14213d,#fca311)"],
    ["Glass Harbor", "2023 · Drama · 1h 49m", "linear-gradient(135deg,#1b4332,#95d5b2)"],
    ["Zero Hour Paris", "2024 · Thriller · 1h 56m", "linear-gradient(135deg,#370617,#ffba08)"]
  ];

  var BADGES = ["Top 10", "New", "", "", "", "", "", "", "", "", "", ""];

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function navHtml(active) {
    var links = [
      ["Home", "index.html", "home"],
      ["Series", "#", "series"],
      ["Films", "#", "films"],
      ["New & Popular", "#", "new"],
      ["My List", "#", "list"]
    ];
    var html = '<div class="nf-nav">' +
      '<a class="nf-logo" href="index.html">NETFLUX</a>';
    links.forEach(function (l) {
      var cls = l[2] === active ? ' class="nav-link active"' : ' class="nav-link"';
      html += '<a' + cls + ' href="' + l[1] + '">' + l[0] + '</a>';
    });
    html += '<span class="spacer"></span><span class="nf-avatar" title="Demo User">DU</span></div>';
    return html;
  }

  function gridHtml() {
    var html = '<div class="nf-grid">';
    TITLES.forEach(function (t, i) {
      html += '<div class="poster" style="background:' + t[2] + '">' +
        (BADGES[i] ? '<span class="pmeta">' + esc(BADGES[i]) + '</span>' : '') +
        '<span class="ptitle">' + esc(t[0]) + '</span></div>';
    });
    return html + '</div>';
  }

  function footerHtml() {
    return '<footer class="nf-footer">' +
      '<div>Questions? Contact demo@netflux.test — this is a fictional service.</div>' +
      '<div style="margin-top:6px">Netflux is a fictional demo service for Escape Hatch.</div>' +
      '</footer>';
  }

  function heroHtml(title, sub) {
    return '<section class="nf-hero"><h1>' + esc(title) + '</h1><p>' + esc(sub) + '</p></section>';
  }

  window.Netflux = {
    nav: navHtml,
    grid: gridHtml,
    footer: footerHtml,
    hero: heroHtml,
    TITLES: TITLES
  };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-nf-nav]").forEach(function (el) {
      el.outerHTML = navHtml(el.getAttribute("data-active") || "home");
    });
    document.querySelectorAll("[data-nf-grid]").forEach(function (el) {
      el.outerHTML = gridHtml();
    });
    document.querySelectorAll("[data-nf-footer]").forEach(function (el) {
      el.outerHTML = footerHtml();
    });
    document.querySelectorAll("[data-nf-hero]").forEach(function (el) {
      el.outerHTML = heroHtml(el.getAttribute("data-title") || "", el.getAttribute("data-sub") || "");
    });
  });
})();
