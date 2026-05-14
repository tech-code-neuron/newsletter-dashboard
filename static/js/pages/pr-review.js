/**
 * Press Release Review Page JavaScript
 * Extracted from inline <script> tag (SOLID compliance)
 *
 * Handles:
 * - Relevance decision buttons (Relevant/Not Relevant)
 * - Company autocomplete filtering
 * - Sortable column headers
 * - Tab count updates
 */

document.addEventListener('DOMContentLoaded', function() {
    const currentFilter = document.querySelector('[data-current-filter]')?.dataset.currentFilter || 'all';

    // Make rows clickable to open press release
    document.querySelectorAll('.pr-row').forEach(row => {
        row.addEventListener('click', (e) => {
            // Don't open if clicking on buttons
            if (!e.target.closest('.relevance-buttons')) {
                const url = row.dataset.url;
                if (url) {
                    window.open(url, '_blank');
                }
            }
        });
    });

    // AJAX Relevance Decision Handler
    document.addEventListener('click', async (e) => {
        const target = e.target;

        // Handle Relevant button
        if (target.classList.contains('btn-relevant') || target.classList.contains('decision-button')) {
            if (target.classList.contains('btn-relevant')) {
                e.stopPropagation();
                await setRelevance(target.dataset.prId, 'relevant', target);
            }
        }

        // Handle Not Relevant button
        if (target.classList.contains('btn-not-relevant') || target.classList.contains('decision-button')) {
            if (target.classList.contains('btn-not-relevant')) {
                e.stopPropagation();
                await setRelevance(target.dataset.prId, 'not_relevant', target);
            }
        }
    });

    async function setRelevance(prId, decision, buttonElement) {
        const row = document.getElementById(`pr-${prId}`);
        const relevantBtn = row.querySelector('.btn-relevant');
        const notRelevantBtn = row.querySelector('.btn-not-relevant');

        try {
            const response = await fetch(`/api/press-release/${prId}/relevance`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ decision })
            });

            if (response.ok) {
                // Update button states immediately
                relevantBtn.classList.remove('active-relevant');
                notRelevantBtn.classList.remove('active-not-relevant');

                if (decision === 'relevant') {
                    relevantBtn.classList.add('active-relevant');
                } else if (decision === 'not_relevant') {
                    notRelevantBtn.classList.add('active-not-relevant');
                }

                row.dataset.relevance = decision;

                // If on uncategorized tab, fade out and remove the row
                if (currentFilter === 'uncategorized') {
                    row.style.transition = 'opacity 0.3s';
                    row.style.opacity = '0';
                    setTimeout(() => {
                        row.style.display = 'none';
                    }, 300);
                }

                // Update counts in tabs
                updateTabCounts();

            } else {
                alert('Error updating relevance. Please try again.');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error updating relevance. Please try again.');
        }
    }

    function updateTabCounts() {
        // Fetch updated counts without full page reload
        fetch(window.location.href, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            // Update tab counts
            document.querySelectorAll('.filter-tabs .tab').forEach((tab, index) => {
                const newTab = doc.querySelectorAll('.filter-tabs .tab')[index];
                if (newTab) {
                    tab.innerHTML = newTab.innerHTML;
                }
            });
        })
        .catch(err => console.error('Error updating counts:', err));
    }
});

// Sortable Column Headers
document.querySelectorAll('.sortable').forEach(th => {
    th.addEventListener('click', () => {
        const sortBy = th.dataset.sort;
        const currentSort = new URLSearchParams(window.location.search).get('sort');
        const currentOrder = new URLSearchParams(window.location.search).get('order') || 'desc';

        // Toggle order if clicking same column
        const newOrder = (currentSort === sortBy && currentOrder === 'desc') ? 'asc' : 'desc';

        // Build new URL
        const url = new URL(window.location);
        url.searchParams.set('sort', sortBy);
        url.searchParams.set('order', newOrder);

        window.location = url;
    });
});

// Company Autocomplete Filter
const companiesData = document.getElementById('companies-data');
const companies = companiesData ? JSON.parse(companiesData.textContent) : [];
const searchInput = document.getElementById('search-input');
const searchClear = document.getElementById('search-clear');
const acDropdown = document.getElementById('ac-dropdown');
const companiesInput = document.getElementById('companies-input');
const selectedCompaniesDiv = document.getElementById('selected-companies');

let selectedCompanies = companiesInput ? companiesInput.value.split(',').filter(Boolean) : [];

function renderSelectedCompanies() {
    if (!selectedCompaniesDiv) return;

    selectedCompaniesDiv.innerHTML = '';
    selectedCompanies.forEach(ticker => {
        const company = companies.find(c => c.ticker === ticker);
        if (company) {
            const badge = document.createElement('div');
            badge.className = 'company-badge';
            badge.innerHTML = `
                ${ticker}
                <button type="button" class="remove-company" data-ticker="${ticker}">✕</button>
            `;
            selectedCompaniesDiv.appendChild(badge);
        }
    });
    if (companiesInput) {
        companiesInput.value = selectedCompanies.join(',');
    }
}

function addCompany(ticker) {
    if (!selectedCompanies.includes(ticker)) {
        selectedCompanies.push(ticker);
        renderSelectedCompanies();
        document.getElementById('filter-form')?.submit();
    }
}

function removeCompany(ticker) {
    selectedCompanies = selectedCompanies.filter(t => t !== ticker);
    renderSelectedCompanies();
    document.getElementById('filter-form')?.submit();
}

if (searchInput) {
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();

        if (!query) {
            acDropdown.classList.remove('visible');
            return;
        }

        const matches = companies.filter(c =>
            c.ticker.toLowerCase().includes(query) ||
            c.name.toLowerCase().includes(query)
        ).slice(0, 10);

        if (matches.length === 0) {
            acDropdown.classList.remove('visible');
            return;
        }

        acDropdown.innerHTML = matches.map(c => `
            <div class="ac-item" data-ticker="${c.ticker}">
                <strong>${c.ticker}</strong> - ${c.name}
            </div>
        `).join('');

        acDropdown.classList.add('visible');
    });
}

if (acDropdown) {
    acDropdown.addEventListener('click', (e) => {
        const item = e.target.closest('.ac-item');
        if (item) {
            addCompany(item.dataset.ticker);
            searchInput.value = '';
            acDropdown.classList.remove('visible');
        }
    });
}

if (selectedCompaniesDiv) {
    selectedCompaniesDiv.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-company')) {
            removeCompany(e.target.dataset.ticker);
        }
    });
}

if (searchClear) {
    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        acDropdown.classList.remove('visible');
    });
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('#search-wrap')) {
        acDropdown?.classList.remove('visible');
    }
});

if (companiesInput) {
    renderSelectedCompanies();
}
