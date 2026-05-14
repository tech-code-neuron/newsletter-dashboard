/**
 * Companies Page JavaScript
 * Extracted from inline <script> tag (SOLID compliance)
 *
 * Handles:
 * - Highlighting last edited company from URL parameter
 * - Email toggle checkboxes with AJAX
 */

// Scroll to last edited company if URL has highlight parameter
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const highlightTicker = urlParams.get('highlight');

    if (highlightTicker) {
        setTimeout(() => {
            const rows = document.querySelectorAll('tbody tr');
            rows.forEach(row => {
                if (row.textContent.includes(highlightTicker)) {
                    row.classList.add('highlight-row');
                    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        }, 100);
    }

    // Handle email toggle checkboxes
    document.querySelectorAll('.email-toggle').forEach(checkbox => {
        checkbox.addEventListener('change', async function(e) {
            const ticker = this.dataset.ticker;
            const originalState = !this.checked;

            try {
                const response = await fetch(`/api/company/${ticker}/toggle-emails`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const data = await response.json();

                if (!data.success) {
                    // Revert checkbox on error
                    this.checked = originalState;
                    alert('Error updating email status: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                // Revert checkbox on error
                this.checked = originalState;
                alert('Error updating email status: ' + error.message);
            }
        });
    });

    // Context menu for active/inactive toggle
    const contextMenu = document.getElementById('company-context-menu');
    if (contextMenu) {
        let currentContextTicker = null;

        // Show context menu on right-click (table rows and mobile cards)
        document.querySelectorAll('.clickable-row, .mobile-card').forEach(el => {
            el.addEventListener('contextmenu', function(e) {
                e.preventDefault();
                currentContextTicker = this.dataset.ticker ||
                    this.querySelector('.ticker, .mobile-card-ticker')?.textContent.trim();

                // Update menu text based on current state
                const isInactive = this.classList.contains('inactive-row') ||
                                  this.classList.contains('inactive-card');
                document.getElementById('context-menu-active-text').textContent =
                    isInactive ? 'Set Active' : 'Set Inactive';

                // Position menu (keep on screen) - use clientX/Y for fixed positioning
                const x = Math.min(e.clientX, window.innerWidth - 150);
                const y = Math.min(e.clientY, window.innerHeight - 50);
                contextMenu.style.left = x + 'px';
                contextMenu.style.top = y + 'px';
                contextMenu.style.display = 'block';
            });
        });

        // Handle menu item click
        contextMenu.addEventListener('click', async function(e) {
            const item = e.target.closest('.context-menu-item');
            if (!item || !currentContextTicker) return;

            contextMenu.style.display = 'none';

            try {
                const response = await fetch(`/api/company/${currentContextTicker}/toggle-active`, {
                    method: 'POST'
                });
                const data = await response.json();
                if (data.success) {
                    // Reload page to move row between sections
                    window.location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        });

        // Hide menu on click outside or Escape
        document.addEventListener('click', (e) => {
            if (!contextMenu.contains(e.target)) {
                contextMenu.style.display = 'none';
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') contextMenu.style.display = 'none';
        });
    }
});
