// static/js/tooltips.js
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
    // Only init non-sidebar ones on load — sidebar.js will manage sidebar ones
    // We check if the element is part of the sidebar. If so, skip.
    if (el.closest('#sidebar')) return;
    if (!bootstrap.Tooltip.getInstance(el)) {
      new bootstrap.Tooltip(el, {
        container: 'body',
        html: true,
        placement: el.dataset.bsPlacement || 'top'
      });
    }
  });
});
