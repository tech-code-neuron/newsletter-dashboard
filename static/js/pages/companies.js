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
});
