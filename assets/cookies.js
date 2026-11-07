/* Netflux L3 cookie banner: big "Accept all", small "Settings".
   Choice persists in sessionStorage; overlays the bottom of the page. */
(function () {
  "use strict";

  var KEY = "nf_cookies_l3";

  function decided() {
    return !!sessionStorage.getItem(KEY);
  }

  function bannerHtml() {
    return '<div id="nf-cookie">' +
      '<div class="ck-text"><b>We use cookies.</b> Netflux uses cookies to personalise recommendations, measure audiences and support advertising partners.</div>' +
      '<a class="ck-settings" href="#" id="ck-settings">Settings</a>' +
      '<button class="ck-accept" id="ck-accept">Accept all</button>' +
      '</div>' +
      '<div id="nf-cookie-panel">' +
      '<h4>Cookie settings</h4>' +
      '<div class="ck-cat"><div>Strictly necessary<span class="desc">Required for the service to work.</span></div><input type="checkbox" checked disabled></div>' +
      '<div class="ck-cat"><div>Personalisation<span class="desc">Remember your watchlist and language.</span></div><input type="checkbox" id="ck-pers" checked></div>' +
      '<div class="ck-cat"><div>Analytics<span class="desc">Anonymous usage statistics.</span></div><input type="checkbox" id="ck-ana" checked></div>' +
      '<div class="ck-cat"><div>Advertising<span class="desc">Used to measure and personalise ads.</span></div><input type="checkbox" id="ck-ads" checked></div>' +
      '<div class="ck-actions">' +
      '<button class="btn btn-secondary btn-sm" id="ck-reject">Reject all optional</button>' +
      '<button class="btn btn-sm" id="ck-save" style="background:#3a3a3a;color:#fff">Save choices</button>' +
      '</div></div>';
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (decided()) return;
    document.body.insertAdjacentHTML("beforeend", bannerHtml());
    document.body.classList.add("has-cookie");

    function close(choice) {
      sessionStorage.setItem(KEY, choice);
      document.getElementById("nf-cookie").remove();
      document.getElementById("nf-cookie-panel").remove();
      document.body.classList.remove("has-cookie");
    }

    document.getElementById("ck-accept").addEventListener("click", function () { close("all"); });
    document.getElementById("ck-settings").addEventListener("click", function (e) {
      e.preventDefault();
      document.getElementById("nf-cookie-panel").classList.add("open");
    });
    document.getElementById("ck-reject").addEventListener("click", function () {
      ["ck-pers", "ck-ana", "ck-ads"].forEach(function (id) { document.getElementById(id).checked = false; });
    });
    document.getElementById("ck-save").addEventListener("click", function () { close("custom"); });
  });
})();
