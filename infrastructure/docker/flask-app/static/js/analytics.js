/**
 * CTA Click Analytics
 * Tracks clicks on elements with data-cta attribute
 */

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-cta]').forEach(function(el) {
        el.addEventListener('click', function() {
            var data = {
                cta_id: el.dataset.cta,
                text: el.textContent.trim().substring(0, 100),
                viewport_width: window.innerWidth,
                timestamp: new Date().toISOString(),
                page: window.location.pathname,
                referrer: document.referrer || ''
            };

            // Use sendBeacon for reliable tracking even on navigation
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/track-click', JSON.stringify(data));
            } else {
                fetch('/api/track-click', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                    keepalive: true
                });
            }
        });
    });
});
