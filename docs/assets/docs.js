/* ============================================================================
 * ProjectCompass — Mariner & Sailboat Command Deck Controller (docs.js)
 * Provides:
 *   1. Persistent dark/light mode toggle ("🌙 Night Watch" / "⛵ Day Sail")
 *   2. Automatic multi-layer SVG ocean wave divider & sailboat emblem injection
 *   3. Interactive Mariner's Bridge Telemetry (HDG bearing, TWS knots, Sail Trim)
 *   4. Instant search & card/section filter (Ctrl+K or '/' shortcut)
 *   5. Automatic "On This Page" TOC builder & scroll-spy
 *   6. One-click copy-to-clipboard buttons on all pre:not(.mermaid) blocks
 *   7. Graceful CDN initialization for Mermaid 10.9.8 & Prism.js
 * ============================================================================ */

(function () {
  "use strict";

  const THEME_STORAGE_KEY = "pc_docs_theme";
  const COMPASS_POINTS_16 = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW"
  ];

  /* ── 1. Theme Initialization & Toggle ─────────────────────────────────── */
  function getInitialTheme() {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === "light" || saved === "dark") {
        return saved;
      }
    } catch (_) {
      /* ignore storage errors on restricted file:// contexts */
    }
    return "dark";
  }

  function renderMermaidDiagrams(theme) {
    if (!window.mermaid) return;
    const mermaidNodes = Array.from(document.querySelectorAll(".mermaid"));
    if (mermaidNodes.length === 0) return;

    mermaidNodes.forEach(function (node) {
      const strayBtn = node.querySelector(".copy-code-btn");
      if (strayBtn) {
        strayBtn.remove();
      }
      if (!node.getAttribute("data-mermaid-src")) {
        node.setAttribute("data-mermaid-src", (node.textContent || "").trim());
      } else {
        node.removeAttribute("data-processed");
        node.textContent = node.getAttribute("data-mermaid-src");
      }
    });

    try {
      window.mermaid.initialize({
        startOnLoad: false,
        theme: theme === "light" ? "default" : "dark",
        securityLevel: "loose",
        fontFamily: "Inter, system-ui, sans-serif",
      });
      if (typeof window.mermaid.run === "function") {
        window.mermaid.run({ nodes: mermaidNodes });
      } else if (typeof window.mermaid.init === "function") {
        window.mermaid.init(undefined, mermaidNodes);
      }
    } catch (err) {
      console.error("Mermaid render error:", err);
    }
  }

  function applyTheme(theme, reRenderMermaid) {
    document.documentElement.setAttribute("data-theme", theme);
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.innerHTML =
        theme === "dark"
          ? '<span aria-hidden="true">⛵</span> <span>Day Sail</span>'
          : '<span aria-hidden="true">🌙</span> <span>Night Watch</span>';
      btn.setAttribute(
        "title",
        theme === "dark"
          ? "Switch to Day Sail (Light Sailcloth Mode)"
          : "Switch to Night Watch (Dark Offshore Mode)"
      );
    }
    if (reRenderMermaid) {
      renderMermaidDiagrams(theme);
    }
  }

  function initTheme() {
    const initial = getInitialTheme();
    applyTheme(initial, false);

    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        const current =
          document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(THEME_STORAGE_KEY, next);
        } catch (_) {}
        applyTheme(next, true);
      });
    }
  }

  /* ── 2. Multi-Layer Ocean Wave Dividers & Sailboat Emblem ─────────────── */
  function initOceanWavesAndEmblems() {
    /* Upgrade top-nav brand icon to include a sailboat inside the compass ring */
    const miniIcons = document.querySelectorAll("svg.compass-mini");
    miniIcons.forEach(function (svg) {
      svg.setAttribute("viewBox", "0 0 36 36");
      svg.innerHTML =
        '<circle cx="18" cy="18" r="15.5" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 2" opacity="0.6"/>' +
        '<circle cx="18" cy="18" r="13" stroke="currentColor" stroke-width="1.5"/>' +
        '<path d="M18 7 L18 24" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
        '<path d="M18 8 L26 22 L18 22 Z" fill="currentColor" fill-opacity="0.32" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>' +
        '<path d="M16.5 10.5 L11 22 L16.5 22 Z" fill="#fbbf24" fill-opacity="0.45" stroke="#fbbf24" stroke-width="1.2" stroke-linejoin="round"/>' +
        '<path d="M10 24.5 L26 24.5 L23.5 27.5 L12.5 27.5 Z" fill="currentColor" fill-opacity="0.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>';
    });

    /* Inject animated multi-layered ocean waves at bottom of hero/page headers */
    const headers = document.querySelectorAll(".hero-deck, .page-header");
    headers.forEach(function (header) {
      if (header.querySelector(".ocean-wave-divider")) return;
      const waveWrap = document.createElement("div");
      waveWrap.className = "ocean-wave-divider";
      waveWrap.setAttribute("aria-hidden", "true");
      waveWrap.innerHTML =
        '<svg viewBox="0 0 1440 54" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">' +
        '<path class="wave-layer-1" d="M0,18 C240,48 480,-6 720,20 C960,46 1200,2 1440,24 L1440,54 L0,54 Z"></path>' +
        '<path class="wave-layer-2" d="M0,30 C300,4 600,50 900,22 C1140,2 1320,38 1440,28 L1440,54 L0,54 Z"></path>' +
        '<path class="wave-layer-3" d="M0,40 C360,56 720,24 1080,44 C1260,52 1380,38 1440,42 L1440,54 L0,54 Z"></path>' +
        "</svg>";
      header.appendChild(waveWrap);
    });
  }

  /* ── 3. Interactive Mariner's Bridge Telemetry (HDG, Knots, Sail Trim) ── */
  function initBridgeTelemetry() {
    const hdgEl = document.getElementById("bridge-hdg");
    const twsEl = document.getElementById("bridge-tws");
    const trimEl = document.getElementById("bridge-trim");
    const needleGroup = document.getElementById("compass-needle-group");
    const heroDeck = document.querySelector(".hero-deck");

    if (!hdgEl) return;

    function updateTelemetryFromBearing(deg) {
      const normalized = ((Math.round(deg) % 360) + 360) % 360;
      const padded = String(normalized).padStart(3, "0");
      const pointIdx = Math.round(normalized / 22.5) % 16;
      const cardinal = COMPASS_POINTS_16[pointIdx];
      hdgEl.textContent = padded + "° " + cardinal;

      if (needleGroup) {
        needleGroup.setAttribute(
          "transform",
          "rotate(" + (normalized - 42) * 0.25 + " 130 130)"
        );
      }

      if (twsEl) {
        const knots = (16.8 + Math.sin((normalized * Math.PI) / 180) * 3.4).toFixed(1);
        twsEl.textContent = knots + " kn • Force 5";
      }

      if (trimEl) {
        if (normalized >= 315 || normalized < 45) {
          trimEl.textContent = "Close-Hauled • Full Main & Genoa";
        } else if (normalized >= 45 && normalized < 135) {
          trimEl.textContent = "Beam Reach • Starboard Tack";
        } else if (normalized >= 135 && normalized < 225) {
          trimEl.textContent = "Broad Reach • Spinnaker Hoisted";
        } else {
          trimEl.textContent = "Beam Reach • Port Tack";
        }
      }
    }

    if (heroDeck) {
      heroDeck.addEventListener(
        "mousemove",
        function (e) {
          const rect = heroDeck.getBoundingClientRect();
          const cx = rect.left + rect.width * 0.72;
          const cy = rect.top + rect.height * 0.45;
          const rad = Math.atan2(e.clientX - cx, -(e.clientY - cy));
          const deg = (rad * 180) / Math.PI;
          updateTelemetryFromBearing(deg);
        },
        { passive: true }
      );
    }

    const waypointBtns = document.querySelectorAll("[data-bearing]");
    waypointBtns.forEach(function (btn) {
      btn.addEventListener("mouseenter", function () {
        const b = parseFloat(btn.getAttribute("data-bearing") || "42");
        if (!Number.isNaN(b)) {
          updateTelemetryFromBearing(b);
        }
      });
    });
  }

  /* ── 2. Live Filter / Search Bar (Ctrl+K or '/') ──────────────────────── */
  function initSearchFilter() {
    const searchInput = document.getElementById("docs-search");
    if (!searchInput) return;

    const cards = Array.from(document.querySelectorAll(".doc-card"));
    const pillars = Array.from(document.querySelectorAll(".pillar-section"));
    const countEl = document.getElementById("search-result-count");

    function filterItems() {
      const query = searchInput.value.trim().toLowerCase();
      let visibleCount = 0;

      if (cards.length > 0) {
        cards.forEach(function (card) {
          const text = (
            card.textContent +
            " " +
            (card.getAttribute("data-keywords") || "")
          ).toLowerCase();
          const matched = !query || text.indexOf(query) !== -1;
          card.style.display = matched ? "" : "none";
          if (matched) visibleCount += 1;
        });

        pillars.forEach(function (pillar) {
          const visibleInPillar = pillar.querySelectorAll(
            '.doc-card:not([style*="display: none"])'
          );
          pillar.style.display = visibleInPillar.length > 0 ? "" : "none";
        });

        if (countEl) {
          countEl.textContent = query
            ? visibleCount + " of " + cards.length + " guides match"
            : "Showing all " + cards.length + " guides across 4 pillars";
        }
      }
    }

    searchInput.addEventListener("input", filterItems);

    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      } else if (
        e.key === "/" &&
        document.activeElement !== searchInput &&
        !["INPUT", "TEXTAREA"].includes(
          (document.activeElement && document.activeElement.tagName) || ""
        )
      ) {
        e.preventDefault();
        searchInput.focus();
      } else if (e.key === "Escape" && document.activeElement === searchInput) {
        searchInput.value = "";
        filterItems();
        searchInput.blur();
      }
    });
  }

  /* ── 3. Copy-to-Clipboard Buttons on Code Blocks ──────────────────────── */
  function initCopyButtons() {
    const blocks = document.querySelectorAll("pre:not(.mermaid)");
    blocks.forEach(function (pre) {
      if (pre.classList.contains("mermaid")) return;
      if (pre.querySelector(".copy-code-btn")) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-code-btn";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () {
        const codeEl = pre.querySelector("code") || pre;
        const text = codeEl.innerText || codeEl.textContent || "";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            btn.textContent = "Copied!";
            setTimeout(function () {
              btn.textContent = "Copy";
            }, 1600);
          });
        }
      });
      pre.appendChild(btn);
    });
  }

  /* ── 4. Sticky Table of Contents & Scroll-Spy ─────────────────────────── */
  function initTableOfContents() {
    const tocList = document.getElementById("toc-list");
    const content = document.querySelector(".docs-content");
    if (!tocList || !content) return;

    const headings = Array.from(content.querySelectorAll("h2[id], h3[id]"));
    if (tocList.children.length === 0 && headings.length > 0) {
      headings.forEach(function (heading) {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "#" + heading.id;
        a.textContent = heading.textContent.replace(/^#\s*/, "");
        if (heading.tagName.toLowerCase() === "h3") {
          a.classList.add("toc-sub");
        }
        li.appendChild(a);
        tocList.appendChild(li);
      });
    }

    const tocLinks = Array.from(tocList.querySelectorAll("a"));
    if (tocLinks.length === 0 || headings.length === 0) return;

    function updateActiveHeading() {
      let currentId = headings[0].id;
      const offset = 120;
      for (let i = 0; i < headings.length; i++) {
        const rect = headings[i].getBoundingClientRect();
        if (rect.top <= offset) {
          currentId = headings[i].id;
        }
      }
      tocLinks.forEach(function (link) {
        if (link.getAttribute("href") === "#" + currentId) {
          link.classList.add("toc-active");
        } else {
          link.classList.remove("toc-active");
        }
      });
    }

    window.addEventListener("scroll", updateActiveHeading, { passive: true });
    updateActiveHeading();
  }

  /* ── 5. Mermaid & Syntax Highlighting Loader ──────────────────────────── */
  function initDiagramsAndSyntax() {
    const currentTheme =
      document.documentElement.getAttribute("data-theme") || "dark";
    renderMermaidDiagrams(currentTheme);

    if (window.Prism && typeof window.Prism.highlightAll === "function") {
      try {
        window.Prism.highlightAll();
      } catch (_) {}
    }
  }

  if (window.mermaid && typeof window.mermaid.initialize === "function") {
    try {
      window.mermaid.initialize({ startOnLoad: false });
    } catch (_) {}
  }

  /* ── 6. Mobile Navigation Drawer Toggle ─────────────────────────────────── */
  function initMobileNav() {
    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");
    var overlay = document.getElementById("nav-overlay");
    if (!toggle || !links) return;

    function openNav() {
      toggle.classList.add("is-open");
      links.classList.add("is-open");
      if (overlay) overlay.classList.add("is-visible");
      document.body.style.overflow = "hidden";
    }

    function closeNav() {
      toggle.classList.remove("is-open");
      links.classList.remove("is-open");
      if (overlay) overlay.classList.remove("is-visible");
      document.body.style.overflow = "";
    }

    toggle.addEventListener("click", function () {
      if (links.classList.contains("is-open")) {
        closeNav();
      } else {
        openNav();
      }
    });

    if (overlay) {
      overlay.addEventListener("click", closeNav);
    }

    links.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        if (window.innerWidth <= 960) closeNav();
      });
    });

    window.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && links.classList.contains("is-open")) {
        closeNav();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initOceanWavesAndEmblems();
    initTheme();
    initBridgeTelemetry();
    initSearchFilter();
    initCopyButtons();
    initTableOfContents();
    initDiagramsAndSyntax();
    initMobileNav();
  });
})();
