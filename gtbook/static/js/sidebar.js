// static/js/sidebar.js
(function () {
  // guard
  if (!window.bootstrap) return;

  document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.getElementById("sidebar");
    if (!sidebar) return;

    // selector for sidebar elements we want tooltips for
    const SIDEBAR_TOOLTIP_SELECTOR = "#sidebar .nav-link[title], #sidebar .chevron-btn[title]";

    // Dispose any bootstrap tooltip instance for an element
    function disposeTooltip(el) {
      const inst = bootstrap.Tooltip.getInstance(el);
      if (inst) inst.dispose();
      // leave title attribute intact (we remove data-bs-toggle only when expanded)
    }

    // Create tooltip if not already created
    function createTooltip(el, opts = {}) {
      if (!bootstrap.Tooltip.getInstance(el)) {
        // ensure attribute is present so other code can see it
        el.setAttribute("data-bs-toggle", "tooltip");
        new bootstrap.Tooltip(el, Object.assign({ placement: "right", container: "body" }, opts));
      }
    }

    // Return true if sidebar should be considered "collapsed" (narrow)
    function isSidebarCollapsed() {
      // Prefer class toggle if you have it
      if (sidebar.classList.contains("collapsed")) return true;
      // fallback to measuring width (animated widths can be tricky; we'll use a tolerant cutoff)
      const w = parseInt(getComputedStyle(sidebar).width || 0, 10) || 0;
      return (w <= 80) || window.innerWidth < 768;
    }

    // Enable tooltips for sidebar when collapsed, otherwise remove the data-bs-toggle attr and dispose
    function updateSidebarTooltips() {
      const collapsed = isSidebarCollapsed();

      document.querySelectorAll(SIDEBAR_TOOLTIP_SELECTOR).forEach(el => {
        // always dispose first to ensure fresh state
        disposeTooltip(el);
        if (collapsed) {
          // only create sidebar tooltips when collapsed
          createTooltip(el, { placement: "right", html: false });
        } else {
          // expanded -> remove tooltip attribute so global initializer won't re-create it
          el.removeAttribute("data-bs-toggle");
        }
      });
    }

    // Initial run: wait a frame + tiny timeout to avoid race with CSS/initial layout
    requestAnimationFrame(() => setTimeout(updateSidebarTooltips, 60));

    // Observe class changes on the sidebar (collapsed toggles are usually class-based)
    const mo = new MutationObserver(() => {
    clearTimeout(window._sidebarTooltipTimer);
    window._sidebarTooltipTimer = setTimeout(updateSidebarTooltips, 40);
    });

    mo.observe(sidebar, {
    attributes: true,
    attributeFilter: ["class", "style"]
    });

    // Also listen for explicit collapse events (if you toggle a class from code)
    // and for resize fallback
    window.addEventListener("resize", () => {
      clearTimeout(window._sidebarTooltipTimer);
      window._sidebarTooltipTimer = setTimeout(updateSidebarTooltips, 120);
    });

    // If some other code toggles sidebar by manipulating inline styles or other attributes,
    // we still run a periodic sanity check for the first few seconds (defensive)
    let sanityRuns = 0;
    const sanityInterval = setInterval(() => {
      updateSidebarTooltips();
      sanityRuns += 1;
      if (sanityRuns > 6) clearInterval(sanityInterval);
    }, 300);
  });
})();
