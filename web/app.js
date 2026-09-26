/* pose-mirror frontend: polls /api/matches, renders the match grid. */
(function () {
  "use strict";

  var streamImg = document.getElementById("stream");
  var noCam = document.getElementById("no-camera");
  var statusEl = document.getElementById("status");
  var grid = document.getElementById("grid");
  var countEl = document.getElementById("count");
  var topk = document.getElementById("topk");
  var topkVal = document.getElementById("topk-val");
  var mirror = document.getElementById("mirror");
  var pauseBtn = document.getElementById("pause");
  var lightbox = document.getElementById("lightbox");
  var lightboxImg = document.getElementById("lightbox-img");
  var lightboxCap = document.getElementById("lightbox-cap");

  var paused = false;
  var lastKey = "";

  streamImg.addEventListener("error", function () {
    streamImg.classList.add("hidden");
    noCam.classList.remove("hidden");
  });

  topk.addEventListener("input", function () {
    topkVal.textContent = topk.value;
  });
  pauseBtn.addEventListener("click", function () {
    paused = !paused;
    pauseBtn.textContent = paused ? "Resume" : "Pause";
  });
  lightbox.addEventListener("click", function () {
    lightbox.classList.add("hidden");
  });

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderMatches(items) {
    var key = items.map(function (m) { return m.id + ":" + m.score; }).join("|");
    if (key === lastKey) return; // avoid DOM churn when nothing changed
    lastKey = key;
    grid.innerHTML = "";
    countEl.textContent = items.length ? "(" + items.length + ")" : "";
    if (!items.length) {
      var d = document.createElement("div");
      d.className = "empty";
      d.textContent = "No matches yet — strike a pose in front of the camera.";
      grid.appendChild(d);
      return;
    }
    items.forEach(function (m) {
      var card = document.createElement("div");
      card.className = "card";
      card.innerHTML =
        '<img loading="lazy" src="' + esc(m.thumb) + '" alt="' + esc(m.title) + '">' +
        '<div class="meta"><span class="score">' + esc(m.score) + "%</span>" +
        '<span class="lic" title="' + esc(m.author) + '">' + esc(m.license || m.author || "") + "</span></div>";
      card.addEventListener("click", function () {
        lightboxImg.src = m.thumb;
        lightboxCap.textContent = (m.title || "") +
          (m.author ? " — " + m.author : "") +
          (m.license ? " (" + m.license + ")" : "");
        lightbox.classList.remove("hidden");
      });
      grid.appendChild(card);
    });
  }

  function pollStatus() {
    fetch("/api/status")
      .then(function (r) { return r.json(); })
      .then(function (s) {
        var parts = [];
        if (s.camera_ok) {
          statusEl.className = "status ok";
          parts.push("camera: on");
        } else {
          statusEl.className = "status warn";
          parts.push("camera: off");
        }
        parts.push("index: " + s.index_size + " poses");
        if (s.pose_detected) parts.push("pose: detected");
        statusEl.textContent = parts.join(" · ");
      })
      .catch(function () {
        statusEl.className = "status";
        statusEl.textContent = "server unreachable";
      });
  }

  function pollMatches() {
    if (paused) return;
    var url = "/api/matches?k=" + encodeURIComponent(topk.value) +
      "&mirror=" + (mirror.checked ? "1" : "0");
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(renderMatches)
      .catch(function () { /* keep last grid on transient errors */ });
  }

  pollStatus();
  pollMatches();
  setInterval(pollStatus, 3000);
  setInterval(pollMatches, 700);
})();
