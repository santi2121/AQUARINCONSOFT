(function () {
  var STORAGE_KEY = "dash-state";
  var expiryMs = 10000;

  function isDashboard() {
    var p = window.location.pathname;
    return p.indexOf("/dashboard/") !== -1 || p.indexOf("/admin") !== -1;
  }

  function save() {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          scrollY: window.scrollY,
          hash: window.location.hash || "",
          ts: Date.now(),
        })
      );
    } catch (e) {}
  }

  function hasFlashes() {
    return !!(document.querySelector('.admin-flashes') || document.querySelector('.flash-stack'));
  }

  function restore() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      sessionStorage.removeItem(STORAGE_KEY);
      if (hasFlashes()) return;
      var state = JSON.parse(raw);
      if (Date.now() - state.ts > expiryMs) return;
      if (!isDashboard()) return;
      var doScroll = function () {
        window.scrollTo(0, state.scrollY);
      };
      if (document.readyState === "complete") {
        setTimeout(doScroll, 60);
      } else {
        window.addEventListener("load", function () {
          setTimeout(doScroll, 60);
        });
      }
    } catch (e) {}
  }

  document.addEventListener("submit", function (e) {
    if (e.target && e.target.nodeName === "FORM") save();
  });

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[href^='#']");
    if (a) save();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restore);
  } else {
    restore();
  }
})();
