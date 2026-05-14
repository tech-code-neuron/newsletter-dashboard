/**
 * Company Detail Page JavaScript
 * Handles RSS status toggle buttons
 */

document.addEventListener('DOMContentLoaded', function() {
    const statusButtons = document.querySelectorAll('.rss-status-btn');

    statusButtons.forEach(button => {
        button.addEventListener('click', async function() {
            // Don't do anything if button is disabled
            if (this.disabled) return;

            const ticker = this.dataset.ticker;
            const desiredStatus = this.dataset.status; // 'active' or 'ignored'
            const buttons = document.querySelectorAll(`.rss-status-btn[data-ticker="${ticker}"]`);

            try {
                const response = await fetch(`/api/company/${ticker}/toggle-ignore-rss`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const data = await response.json();

                if (data.success) {
                    // Update button states
                    buttons.forEach(btn => {
                        btn.classList.remove('btn-primary');

                        if (data.ignore_company_rss && btn.dataset.status === 'ignored') {
                            btn.classList.add('btn-primary');
                        } else if (!data.ignore_company_rss && btn.dataset.status === 'active') {
                            btn.classList.add('btn-primary');
                        }
                    });
                } else {
                    alert('Error updating RSS status: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                alert('Error updating RSS status: ' + error.message);
            }
        });
    });
});
