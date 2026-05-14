/**
 * Publisher Page JavaScript
 *
 * Features:
 * - SortableJS for drag-drop reordering
 * - Inline title editing
 * - Live preview updates
 * - HTML generation with clipboard copy
 */

let selectedDate = null;
let sortableInstance = null;

/**
 * Initialize the publisher page
 * @param {string} date - ISO date string (YYYY-MM-DD)
 */
function initPublisher(date) {
    selectedDate = date;

    // Initialize SortableJS
    initSortable();

    // Initialize event listeners
    initEventListeners();

    // Load initial preview
    refreshPreview();
}

/**
 * Initialize SortableJS on the release list
 */
function initSortable() {
    const list = document.getElementById('sortable-list');
    if (!list) return;

    sortableInstance = Sortable.create(list, {
        handle: '.drag-handle:not(.drag-disabled)',
        filter: '.section-select, .status-select, .edit-title-btn',
        preventOnFilter: false,
        animation: 150,
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
        onEnd: function(evt) {
            // Save new order to session
            saveOrder();
            // Update preview
            refreshPreview();
        }
    });
}

/**
 * Initialize event listeners
 */
function initEventListeners() {
    // Generate button (desktop)
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateHTML);
    }

    // Generate button (mobile)
    const generateBtnMobile = document.getElementById('generate-btn-mobile');
    if (generateBtnMobile) {
        generateBtnMobile.addEventListener('click', generateHTMLMobile);
    }

    // Refresh preview button
    const refreshBtn = document.getElementById('refresh-preview-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshPreview);
    }

    // Mobile preview toggle - load preview when opened
    const previewDetails = document.querySelector('.preview-section-mobile');
    if (previewDetails) {
        previewDetails.addEventListener('toggle', function() {
            if (this.open) {
                refreshPreviewMobile();
            }
        });
    }

    // Fullscreen preview button (mobile)
    const fullscreenBtn = document.getElementById('fullscreen-preview-btn');
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', openFullscreenPreview);
    }

    // Close fullscreen preview
    const fullscreenCloseBtn = document.getElementById('fullscreen-close-btn');
    if (fullscreenCloseBtn) {
        fullscreenCloseBtn.addEventListener('click', closeFullscreenPreview);
    }

    // New window preview button (mobile)
    const newWindowBtn = document.getElementById('new-window-preview-btn');
    if (newWindowBtn) {
        newWindowBtn.addEventListener('click', openPreviewInNewWindow);
    }

    // Section select dropdowns
    document.querySelectorAll('.section-select').forEach(select => {
        select.addEventListener('change', function() {
            // Check if this is an SEC filing
            if (this.dataset.secFiling === 'true') {
                updateDisclosureSection(this.dataset.url, this.value);
            } else {
                updateSection(this.dataset.url, this.value);
            }
        });
    });

    // Status select dropdowns
    document.querySelectorAll('.status-select').forEach(select => {
        select.addEventListener('change', function() {
            // Check if this is an SEC filing
            if (this.dataset.secFiling === 'true') {
                updateDisclosureStatus(this.dataset.url, this.value);
            } else {
                updateStatus(this.dataset.url, this.value);
            }
        });
    });

    // Mobile section select dropdowns
    document.querySelectorAll('.section-select-mobile').forEach(select => {
        select.addEventListener('change', function() {
            updateSection(this.dataset.url, this.value);
        });
    });

    // Mobile status select dropdowns
    document.querySelectorAll('.status-select-mobile').forEach(select => {
        select.addEventListener('change', function() {
            // Check if this is an SEC filing (same logic as desktop handler)
            if (this.dataset.secFiling === 'true') {
                updateDisclosureStatus(this.dataset.url, this.value);
            } else {
                updateStatus(this.dataset.url, this.value);
            }
        });
    });

    // Edit title buttons
    document.querySelectorAll('.edit-title-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            openTitleModal(this.dataset.url);
        });
    });

    // Title modal
    const saveTitleBtn = document.getElementById('save-title-btn');
    if (saveTitleBtn) {
        saveTitleBtn.addEventListener('click', saveTitle);
    }

    const cancelTitleBtn = document.getElementById('cancel-title-btn');
    if (cancelTitleBtn) {
        cancelTitleBtn.addEventListener('click', closeTitleModal);
    }

    const titleModalClose = document.getElementById('title-modal-close');
    if (titleModalClose) {
        titleModalClose.addEventListener('click', closeTitleModal);
    }

    const titleModalOverlay = document.getElementById('title-modal-overlay');
    if (titleModalOverlay) {
        titleModalOverlay.addEventListener('click', closeTitleModal);
    }

    // HTML modal
    const copyHtmlBtn = document.getElementById('copy-html-btn');
    if (copyHtmlBtn) {
        copyHtmlBtn.addEventListener('click', copyToClipboard);
    }

    const closeModalBtn = document.getElementById('close-modal-btn');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeHtmlModal);
    }

    const htmlModalClose = document.getElementById('html-modal-close');
    if (htmlModalClose) {
        htmlModalClose.addEventListener('click', closeHtmlModal);
    }

    const htmlModalOverlay = document.getElementById('html-modal-overlay');
    if (htmlModalOverlay) {
        htmlModalOverlay.addEventListener('click', closeHtmlModal);
    }
}

/**
 * Get current URL order from the visible list (desktop or mobile)
 *
 * WARNING: DO NOT create separate mobile/desktop URL functions.
 * This unified function handles both views automatically.
 * Mobile/desktop sync has broken 4+ times. Keep ONE function.
 *
 * Desktop: #sortable-list .release-item[data-url]
 * Mobile: .mobile-card-list .publisher-card[data-url]
 *
 * @returns {string[]} Array of URLs in display order
 */
function getUrlOrder() {
    const mobileList = document.querySelector('.mobile-card-list');
    const desktopList = document.getElementById('sortable-list');

    // Check which view is visible (offsetParent is null if hidden via CSS)
    if (mobileList && mobileList.offsetParent !== null) {
        const cards = mobileList.querySelectorAll('.publisher-card');
        return Array.from(cards).map(card => card.dataset.url).filter(Boolean);
    } else if (desktopList) {
        const items = desktopList.querySelectorAll('.release-item');
        return Array.from(items).map(item => item.dataset.url).filter(Boolean);
    }
    return [];
}

/**
 * Get URLs of only "ready" items for publishing (desktop or mobile)
 *
 * WARNING: DO NOT create separate mobile/desktop URL functions.
 * This unified function handles both views automatically.
 * Mobile/desktop sync has broken 4+ times. Keep ONE function.
 *
 * Excludes: excluded, needs_review, published items
 * @returns {string[]} Array of URLs that will actually be published
 */
function getReadyUrls() {
    const mobileList = document.querySelector('.mobile-card-list');
    const desktopList = document.getElementById('sortable-list');

    if (mobileList && mobileList.offsetParent !== null) {
        const cards = mobileList.querySelectorAll('.publisher-card');
        return Array.from(cards)
            .filter(card => (card.dataset.status || 'ready') === 'ready')
            .map(card => card.dataset.url)
            .filter(Boolean);
    } else if (desktopList) {
        const items = desktopList.querySelectorAll('.release-item');
        return Array.from(items)
            .filter(item => (item.dataset.status || 'ready') === 'ready')
            .map(item => item.dataset.url)
            .filter(Boolean);
    }
    return [];
}

/**
 * Save current order to session via API
 */
function saveOrder() {
    const urls = getUrlOrder();

    fetch('/publisher/update-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            date: selectedDate,
            urls: urls
        })
    }).catch(err => console.error('Error saving order:', err));
}

/**
 * Refresh the preview iframe
 */
function refreshPreview() {
    const frame = document.getElementById('preview-frame');
    if (!frame) return;

    // Don't pass URLs in query string (exceeds header size limit for many releases)
    // Backend will use session order saved by saveOrder()
    frame.src = `/publisher/preview-web?date=${selectedDate}&t=${Date.now()}`;
}

/**
 * Open fullscreen preview modal (mobile)
 */
function openFullscreenPreview() {
    const modal = document.getElementById('fullscreen-preview-modal');
    const frame = document.getElementById('fullscreen-preview-frame');

    if (modal && frame) {
        frame.src = `/publisher/preview-web?date=${selectedDate}&t=${Date.now()}`;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close fullscreen preview modal
 */
function closeFullscreenPreview() {
    const modal = document.getElementById('fullscreen-preview-modal');

    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

/**
 * Open preview in new window
 */
function openPreviewInNewWindow() {
    const previewUrl = `/publisher/preview-web?date=${selectedDate}&t=${Date.now()}`;
    window.open(previewUrl, '_blank', 'width=800,height=600,menubar=yes,toolbar=yes,location=yes');
}

/**
 * Update press release section classification
 * @param {string} url - Press release URL
 * @param {string} section - New section ('headline', 'other', 'auto')
 */
function updateSection(url, section) {
    const select = document.querySelector(`.section-select[data-url="${url}"]`);

    fetch('/publisher/update-section', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            url: url,
            section: section
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update visual indicator for override (desktop and mobile)
            const selectMobile = document.querySelector(`.section-select-mobile[data-url="${url}"]`);
            [select, selectMobile].forEach(s => {
                if (s) {
                    if (section === 'auto') {
                        s.classList.remove('overridden');
                    } else {
                        s.classList.add('overridden');
                    }
                }
            });
            // Refresh preview to show new section placement
            refreshPreview();
            refreshPreviewMobile();
        } else {
            alert('Error updating section: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error updating section:', err);
        alert('Error updating section');
    });
}

/**
 * Update SEC disclosure section classification
 * @param {string} filingUrl - SEC filing URL
 * @param {string} section - New section ('headline', 'financing', 'property', 'earnings', 'other', 'auto')
 */
function updateDisclosureSection(filingUrl, section) {
    const select = document.querySelector(`.section-select[data-url="${filingUrl}"]`);

    fetch('/publisher/update-disclosure-section', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            filing_url: filingUrl,
            section: section
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update visual indicator for override
            if (select) {
                if (section === 'auto') {
                    select.classList.remove('overridden');
                } else {
                    select.classList.add('overridden');
                }
            }
            // Refresh preview to show new section placement
            refreshPreview();
        } else {
            alert('Error updating section: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error updating disclosure section:', err);
        alert('Error updating section');
    });
}

/**
 * Update press release status
 * @param {string} url - Press release URL
 * @param {string} status - New status
 */
function updateStatus(url, status) {
    fetch('/publisher/update-status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            url: url,
            status: status,
            date: selectedDate  // Include date for published_for_date tracking
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const item = document.querySelector(`.release-item[data-url="${url}"]`);
            if (item) {
                // Remove old status classes
                item.classList.remove('release-item-excluded', 'release-item-needs_review', 'release-item-published');
                item.dataset.status = status;

                // Add new status class if not ready
                if (status !== 'ready') {
                    item.classList.add(`release-item-${status}`);
                }

                // Update drag handle
                const dragHandle = item.querySelector('.drag-handle');
                if (dragHandle) {
                    if (status === 'ready') {
                        dragHandle.classList.remove('drag-disabled');
                    } else {
                        dragHandle.classList.add('drag-disabled');
                    }
                }
            }
            // Also update mobile card styling
            const mobileCard = document.querySelector(`.publisher-card[data-url="${url}"]`);
            if (mobileCard) {
                mobileCard.classList.remove('publisher-card-excluded', 'publisher-card-needs_review', 'publisher-card-published');
                mobileCard.dataset.status = status;
                if (status !== 'ready') {
                    mobileCard.classList.add(`publisher-card-${status}`);
                }
            }
            // Refresh preview (only shows ready items)
            refreshPreview();
            refreshPreviewMobile();
            // Update status counts
            updateStatusCounts();
        } else {
            alert('Error updating status: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error updating status:', err);
        alert('Error updating status');
    });
}

/**
 * Update SEC disclosure status
 * @param {string} filingUrl - SEC filing URL
 * @param {string} status - New status
 */
function updateDisclosureStatus(filingUrl, status) {
    fetch('/publisher/update-disclosure-status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            filing_url: filingUrl,
            status: status,
            date: selectedDate
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Find by iterating (avoids CSS selector escaping issues with SEC URLs)
            const items = document.querySelectorAll('.release-item[data-sec-filing="true"]');
            const item = Array.from(items).find(el => el.dataset.url === filingUrl);
            if (item) {
                // Remove old status classes
                item.classList.remove('release-item-excluded', 'release-item-needs_review', 'release-item-published');
                item.dataset.status = status;

                // Add new status class if not ready
                if (status !== 'ready') {
                    item.classList.add(`release-item-${status}`);
                }

                // Update drag handle
                const dragHandle = item.querySelector('.drag-handle');
                if (dragHandle) {
                    if (status === 'ready') {
                        dragHandle.classList.remove('drag-disabled');
                    } else {
                        dragHandle.classList.add('drag-disabled');
                    }
                }
            }
            // Refresh preview
            refreshPreview();
            // Update status counts
            updateStatusCounts();
        } else {
            alert('Error updating SEC filing status: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error updating SEC filing status:', err);
        alert('Error updating SEC filing status');
    });
}

/**
 * Permanently delete an SEC disclosure
 * @param {string} filingUrl - SEC filing URL
 */
function deleteDisclosure(filingUrl) {
    if (!confirm('Permanently delete this SEC filing? This cannot be undone.')) return;

    fetch('/publisher/delete-disclosure', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({ filing_url: filingUrl })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove item from DOM (find by iterating to avoid CSS selector issues)
            const items = document.querySelectorAll('.release-item[data-sec-filing="true"]');
            const item = Array.from(items).find(el => el.dataset.url === filingUrl);
            if (item) item.remove();
            // Also remove from mobile view
            const mobileItems = document.querySelectorAll('.publisher-card[data-sec-filing="true"]');
            const mobileItem = Array.from(mobileItems).find(el => el.dataset.url === filingUrl);
            if (mobileItem) mobileItem.remove();
            refreshPreview();
            updateStatusCounts();
        } else {
            alert('Error deleting: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error deleting SEC filing:', err);
        alert('Error deleting SEC filing');
    });
}

/**
 * Update status count badges
 */
function updateStatusCounts() {
    const items = document.querySelectorAll('.release-item');
    const counts = { ready: 0, needs_review: 0, published: 0, excluded: 0 };

    items.forEach(item => {
        const status = item.dataset.status || 'ready';
        if (counts.hasOwnProperty(status)) {
            counts[status]++;
        }
    });

    // Update the count displays
    document.querySelectorAll('.status-item').forEach(el => {
        if (el.classList.contains('status-ready')) {
            el.querySelector('.status-count').textContent = counts.ready;
        } else if (el.classList.contains('status-needs-review')) {
            el.querySelector('.status-count').textContent = counts.needs_review;
        } else if (el.classList.contains('status-published')) {
            el.querySelector('.status-count').textContent = counts.published;
        } else if (el.classList.contains('status-excluded')) {
            el.querySelector('.status-count').textContent = counts.excluded;
        }
    });
}

/**
 * Open the title edit modal
 * @param {string} url - Press release URL
 */
function openTitleModal(url) {
    const item = document.querySelector(`.release-item[data-url="${url}"]`);
    if (!item) return;

    const titleSpan = item.querySelector('.release-title');
    const currentTitle = titleSpan ? titleSpan.textContent.trim() : '';

    document.getElementById('title-input').value = currentTitle;
    document.getElementById('title-edit-url').value = url;

    document.getElementById('title-modal-overlay').classList.add('open');
    document.getElementById('title-modal').classList.add('open');

    // Focus input
    document.getElementById('title-input').focus();
}

/**
 * Close the title edit modal
 */
function closeTitleModal() {
    document.getElementById('title-modal-overlay').classList.remove('open');
    document.getElementById('title-modal').classList.remove('open');
}

/**
 * Save the edited title
 */
function saveTitle() {
    const url = document.getElementById('title-edit-url').value;
    const title = document.getElementById('title-input').value.trim();

    fetch('/publisher/update-title', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            url: url,
            title: title
        })
    })
    .then(response => {
        // Check if response is OK and is JSON
        const contentType = response.headers.get('content-type');
        if (!response.ok) {
            // If not OK, try to get error message
            if (contentType && contentType.includes('application/json')) {
                return response.json().then(data => {
                    throw new Error(data.error || `Server error: ${response.status}`);
                });
            } else {
                throw new Error(`Server error: ${response.status}. Check CSRF token.`);
            }
        }
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        }
        throw new Error('Server returned non-JSON response');
    })
    .then(data => {
        if (data.success) {
            // Update the title in the UI
            const titleSpan = document.querySelector(`.release-title[data-url="${url}"]`);
            if (titleSpan) {
                titleSpan.textContent = title;
            }
            closeTitleModal();
            refreshPreview();
        } else {
            alert('Error saving title: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error saving title:', err);
        alert('Error saving title: ' + err.message);
    });
}

/**
 * Generate final HTML and show modal
 */
function generateHTML() {
    const urls = getUrlOrder();

    const generateBtn = document.getElementById('generate-btn');
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating...';

    fetch('/publisher/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            date: selectedDate,
            urls: urls
        })
    })
    .then(response => response.json())
    .then(data => {
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate HTML';

        if (data.success) {
            // Show HTML in modal
            document.getElementById('html-output').value = data.html;

            let successMsg = `Generated newsletter with ${data.count} press releases.`;
            if (data.published_count > 0) {
                successMsg += ` Marked ${data.published_count} as published.`;
            }
            document.getElementById('success-message').textContent = successMsg;

            document.getElementById('html-modal-overlay').classList.add('open');
            document.getElementById('html-modal').classList.add('open');
        } else {
            alert('Error generating HTML: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate HTML';
        console.error('Error generating HTML:', err);
        alert('Error generating HTML');
    });
}

/**
 * Close the HTML modal
 */
function closeHtmlModal() {
    document.getElementById('html-modal-overlay').classList.remove('open');
    document.getElementById('html-modal').classList.remove('open');
}

/**
 * Copy HTML to clipboard
 */
function copyToClipboard() {
    const textarea = document.getElementById('html-output');
    textarea.select();
    textarea.setSelectionRange(0, 99999); // For mobile

    navigator.clipboard.writeText(textarea.value)
        .then(() => {
            const copyBtn = document.getElementById('copy-html-btn');
            const originalText = copyBtn.textContent;
            copyBtn.textContent = 'Copied!';
            setTimeout(() => {
                copyBtn.textContent = originalText;
            }, 2000);
        })
        .catch(err => {
            console.error('Failed to copy:', err);
            // Fallback for older browsers
            document.execCommand('copy');
            alert('HTML copied to clipboard');
        });
}

/**
 * Get CSRF token from the page
 * @returns {string} CSRF token
 */
function getCSRFToken() {
    // Try meta tag first
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    // Try hidden input
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;

    return '';
}

/**
 * Refresh preview iframe for mobile
 */
function refreshPreviewMobile() {
    const frame = document.getElementById('preview-frame-mobile');
    if (!frame) return;

    // Don't pass URLs in query string (exceeds header size limit for many releases)
    // Backend will use session order saved by saveOrder()
    frame.src = `/publisher/preview-web?date=${selectedDate}&t=${Date.now()}`;
}

/**
 * Generate HTML for mobile
 */
function generateHTMLMobile() {
    const urls = getUrlOrder();  // Uses unified function for both desktop/mobile

    const generateBtn = document.getElementById('generate-btn-mobile');
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating...';

    fetch('/publisher/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            date: selectedDate,
            urls: urls
        })
    })
    .then(response => response.json())
    .then(data => {
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate HTML';

        if (data.success) {
            // Show HTML in modal
            document.getElementById('html-output').value = data.html;

            let successMsg = `Generated newsletter with ${data.count} press releases.`;
            if (data.published_count > 0) {
                successMsg += ` Marked ${data.published_count} as published.`;
            }
            document.getElementById('success-message').textContent = successMsg;

            document.getElementById('html-modal-overlay').classList.add('open');
            document.getElementById('html-modal').classList.add('open');
        } else {
            alert('Error generating HTML: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate HTML';
        console.error('Error generating HTML:', err);
        alert('Error generating HTML');
    });
}

// =============================================================================
// STYLE EDITOR
// =============================================================================

let currentStyles = null;

const FONT_FAMILIES = [
    { value: 'Georgia, serif', label: 'Georgia (Serif)' },
    { value: 'Arial, sans-serif', label: 'Arial (Sans-serif)' },
    { value: '"Times New Roman", Times, serif', label: 'Times New Roman' },
    { value: '"Helvetica Neue", Helvetica, sans-serif', label: 'Helvetica' },
    { value: 'Verdana, sans-serif', label: 'Verdana' },
    { value: '"Courier New", monospace', label: 'Courier New' },
];

const STYLE_ELEMENTS = [
    { key: 'logo', label: 'Newsletter Title (THE REIT SHEET)' },
    { key: 'date', label: 'Date' },
    { key: 'company', label: 'Company Name' },
    { key: 'title', label: 'Press Release Title' },
    { key: 'source', label: 'Source Link' },
    { key: 'footer', label: 'Footer' },
];

/**
 * Open style editor modal
 */
async function openStyleEditor() {
    // Fetch current styles
    try {
        const response = await fetch('/publisher/styles/');
        if (!response.ok) throw new Error('Failed to load styles');
        currentStyles = await response.json();
    } catch (err) {
        console.error('Error loading styles:', err);
        alert('Error loading styles');
        return;
    }

    // Render style editor
    renderStyleEditor();

    // Open modal
    document.getElementById('style-modal-overlay').classList.add('open');
    document.getElementById('style-modal').classList.add('open');
}

/**
 * Render style editor controls
 */
function renderStyleEditor() {
    const container = document.getElementById('style-editor');
    container.innerHTML = '';

    STYLE_ELEMENTS.forEach(element => {
        const styles = currentStyles[element.key] || {};

        const elementDiv = document.createElement('div');
        elementDiv.className = 'style-element';
        elementDiv.innerHTML = `
            <div class="style-element-header">${element.label}</div>
            <div class="style-controls">
                <div class="style-control">
                    <label>Font Family</label>
                    <select data-element="${element.key}" data-prop="fontFamily">
                        ${FONT_FAMILIES.map(font => `
                            <option value="${font.value}" ${styles.fontFamily === font.value ? 'selected' : ''}>
                                ${font.label}
                            </option>
                        `).join('')}
                    </select>
                </div>
                <div class="style-control">
                    <label>Font Size</label>
                    <input type="text" 
                           data-element="${element.key}" 
                           data-prop="fontSize" 
                           value="${styles.fontSize || '16px'}" 
                           placeholder="e.g., 16px">
                </div>
                <div class="style-control">
                    <label>Color</label>
                    <input type="color" 
                           data-element="${element.key}" 
                           data-prop="color" 
                           value="${styles.color || '#000000'}">
                </div>
                <div class="style-control style-control-checkbox">
                    <input type="checkbox" 
                           id="bold-${element.key}" 
                           data-element="${element.key}" 
                           data-prop="fontWeight" 
                           ${styles.fontWeight === 'bold' || styles.fontWeight === '700' ? 'checked' : ''}>
                    <label for="bold-${element.key}">Bold</label>
                </div>
                <div class="style-control style-control-checkbox">
                    <input type="checkbox" 
                           id="italic-${element.key}" 
                           data-element="${element.key}" 
                           data-prop="fontStyle" 
                           ${styles.fontStyle === 'italic' ? 'checked' : ''}>
                    <label for="italic-${element.key}">Italic</label>
                </div>
                <div class="style-control style-control-checkbox">
                    <input type="checkbox" 
                           id="underline-${element.key}" 
                           data-element="${element.key}" 
                           data-prop="textDecoration" 
                           ${styles.textDecoration === 'underline' ? 'checked' : ''}>
                    <label for="underline-${element.key}">Underline</label>
                </div>
            </div>
        `;
        container.appendChild(elementDiv);
    });

    // Setup font size auto-formatting
    setupFontSizeFormatting();
    setupStyleEditorKeyboard();
}

/**
 * Save style changes
 */
async function saveStyles() {
    // Collect all style values from form
    const updatedStyles = {};

    STYLE_ELEMENTS.forEach(element => {
        const styles = {};

        // Get all inputs for this element
        const inputs = document.querySelectorAll(`[data-element="${element.key}"]`);
        inputs.forEach(input => {
            const prop = input.dataset.prop;

            if (input.type === 'checkbox') {
                if (prop === 'fontWeight') {
                    styles[prop] = input.checked ? 'bold' : 'normal';
                } else if (prop === 'fontStyle') {
                    styles[prop] = input.checked ? 'italic' : 'normal';
                } else if (prop === 'textDecoration') {
                    styles[prop] = input.checked ? 'underline' : 'none';
                }
            } else {
                let value = input.value;
                // Strip "px" from fontSize before saving
                if (prop === 'fontSize') {
                    value = value.replace(/px$/i, '');
                }
                styles[prop] = value;
            }
        });

        updatedStyles[element.key] = styles;
    });

    // Save to server
    try {
        const response = await fetch('/publisher/styles/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify(updatedStyles),
        });

        if (!response.ok) throw new Error('Failed to save styles');

        const data = await response.json();
        if (data.success) {
            closeStyleEditor();
            // Refresh preview to show new styles
            refreshPreview();
        } else {
            alert('Error saving styles: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('Error saving styles:', err);
        alert('Error saving styles');
    }
}

/**
 * Close style editor modal
 */
function closeStyleEditor() {
    document.getElementById('style-modal-overlay').classList.remove('open');
    document.getElementById('style-modal').classList.remove('open');
}

// Add event listeners for style editor
document.addEventListener('DOMContentLoaded', function() {
    // Style editor button
    const styleEditorBtn = document.getElementById('style-editor-btn');
    if (styleEditorBtn) {
        styleEditorBtn.addEventListener('click', openStyleEditor);
    }

    // Save styles button
    const saveStylesBtn = document.getElementById('save-styles-btn');
    if (saveStylesBtn) {
        saveStylesBtn.addEventListener('click', saveStyles);
    }

    // Cancel/Close buttons
    const cancelStylesBtn = document.getElementById('cancel-styles-btn');
    const closeStyleModalBtn = document.getElementById('style-modal-close');
    const styleModalOverlay = document.getElementById('style-modal-overlay');

    if (cancelStylesBtn) {
        cancelStylesBtn.addEventListener('click', closeStyleEditor);
    }
    if (closeStyleModalBtn) {
        closeStyleModalBtn.addEventListener('click', closeStyleEditor);
    }
    if (styleModalOverlay) {
        styleModalOverlay.addEventListener('click', closeStyleEditor);
    }
});

/**
 * Format font size input with automatic "px" suffix
 */
function formatFontSizeInput(input) {
    // Get current value
    let value = input.value;
    
    // Strip "px" if present (and any whitespace)
    value = value.replace(/px/gi, '').trim();
    
    // Keep only numbers
    value = value.replace(/[^0-9]/g, '');
    
    // Set value with "px" suffix
    if (value) {
        input.value = value + 'px';
    } else {
        input.value = '';
    }
}

/**
 * Setup font size input auto-formatting
 */
function setupFontSizeFormatting() {
    const fontSizeInputs = document.querySelectorAll('input[data-prop="fontSize"]');
    
    fontSizeInputs.forEach(input => {
        // On input: just strip "px" if user types it, keep numbers only
        input.addEventListener('input', function(e) {
            let value = this.value;
            
            // If they typed "px", remove it
            if (value.toLowerCase().includes('px')) {
                value = value.replace(/px/gi, '');
            }
            
            // Keep only numbers (don't add "px" yet - let them type)
            value = value.replace(/[^0-9]/g, '');
            
            this.value = value;
        });
        
        // On blur: add "px" suffix
        input.addEventListener('blur', function() {
            if (this.value && !this.value.toLowerCase().includes('px')) {
                this.value = this.value + 'px';
            }
        });
        
        // On focus: remove "px" so they can edit the number
        input.addEventListener('focus', function() {
            this.value = this.value.replace(/px/gi, '');
        });
        
        // Initial format
        formatFontSizeInput(input);
    });
}


/**
 * Setup keyboard shortcuts for style editor
 */
function setupStyleEditorKeyboard() {
    const styleEditor = document.getElementById('style-editor');
    if (!styleEditor) return;
    
    // Listen for Enter key on all inputs/selects in style editor
    styleEditor.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault(); // Prevent form submission
            saveStyles(); // Auto-save
        }
    });
}


// =============================================================================
// SEND TO EMAIL
// =============================================================================

/**
 * Send newsletter to email via AWS SES
 */
function sendToEmail(event) {
    // Get the button that was clicked (works for both desktop and mobile)
    const sendBtn = event ? event.target :
                    document.getElementById('send-email-btn') ||
                    document.getElementById('send-email-btn-mobile');
    if (!sendBtn) return;

    // Confirm before sending to all subscribers
    if (!confirm('Send this newsletter to ALL verified subscribers?\n\nThis action cannot be undone.')) {
        return;
    }

    // Get current order
    const urls = getUrlOrder();

    // Disable button and show loading
    sendBtn.disabled = true;
    const originalText = sendBtn.textContent;
    sendBtn.textContent = 'Sending...';

    // Send request
    fetch('/publisher/email/send', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            date: selectedDate,
            urls: urls,
            mode: 'subscribers'
        })
    })
    .then(response => {
        console.log('Response status:', response.status);
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        sendBtn.disabled = false;

        if (data.success) {
            // Success - show green button with checkmark
            sendBtn.textContent = '✅ Sent!';
            sendBtn.style.background = '#28a745';

            // Alert with confirmation (show subscriber count from response)
            const count = data.successful || data.total || 0;
            alert(`✅ NEWSLETTER SENT!\n\nSent to ${count} subscriber(s).\n\nEmails will arrive within 1-2 minutes.`);

            // Reset button after 3 seconds
            setTimeout(() => {
                sendBtn.textContent = originalText;
                sendBtn.style.background = '';
            }, 3000);
        } else {
            sendBtn.textContent = originalText;
            alert('❌ ERROR SENDING EMAIL\n\n' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        sendBtn.disabled = false;
        sendBtn.textContent = originalText;
        console.error('Error sending email:', err);
        alert('❌ ERROR SENDING EMAIL\n\n' + err.message + '\n\nCheck browser console (F12) for details.');
    });
}

// Add event listener for send email button
document.addEventListener('DOMContentLoaded', function() {
    const sendEmailBtn = document.getElementById('send-email-btn');
    if (sendEmailBtn) {
        sendEmailBtn.addEventListener('click', sendToEmail);
    }

    const publishHomepageBtn = document.getElementById('publish-homepage-btn');
    if (publishHomepageBtn) {
        publishHomepageBtn.addEventListener('click', publishToHomepage);
    }

    // Mobile buttons
    const sendEmailBtnMobile = document.getElementById('send-email-btn-mobile');
    if (sendEmailBtnMobile) {
        sendEmailBtnMobile.addEventListener('click', sendToEmail);
    }

    const publishHomepageBtnMobile = document.getElementById('publish-homepage-btn-mobile');
    if (publishHomepageBtnMobile) {
        publishHomepageBtnMobile.addEventListener('click', publishToHomepage);
    }
});

// =============================================================================
// PUBLISH TO HOMEPAGE
// =============================================================================

/**
 * Check for duplicate articles in recent archives
 * @returns {Promise<{hasDuplicates: boolean, duplicates: Array}>}
 */
async function checkForDuplicates() {
    const urls = getReadyUrls();

    try {
        const response = await fetch('/publisher/email/check-duplicates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                date: selectedDate,
                urls: urls
            })
        });

        const data = await response.json();
        return {
            hasDuplicates: data.has_duplicates || false,
            duplicates: data.duplicates || []
        };
    } catch (err) {
        console.error('Error checking duplicates:', err);
        // Warn but don't block publish - duplicate check is not critical
        console.warn('Could not check for duplicates, proceeding anyway');
        return { hasDuplicates: false, duplicates: [], error: err.message };
    }
}

/**
 * Format duplicate warning message for user
 * @param {Array} duplicates - Array of duplicate info objects
 * @returns {string} Formatted warning message
 */
function formatDuplicateWarning(duplicates) {
    let message = '⚠️ DUPLICATE ARTICLES DETECTED!\n\n';
    message += 'The following articles already appear in recent archives:\n\n';

    for (const dup of duplicates) {
        message += `📅 Archive from ${dup.archive_date}:\n`;
        for (const article of dup.overlapping_articles) {
            message += `   • ${article.title}\n`;
        }
        message += '\n';
    }

    message += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';
    message += 'These articles will appear in BOTH places.\n\n';
    message += 'Would you like to publish anyway?';

    return message;
}

/**
 * Publish newsletter to homepage (your-domain.com)
 * Checks for duplicate articles before publishing
 */
async function publishToHomepage(event) {
    // Get the button that was clicked (works for both desktop and mobile)
    const publishBtn = event ? event.target :
                       document.getElementById('publish-homepage-btn') ||
                       document.getElementById('publish-homepage-btn-mobile');
    if (!publishBtn) return;

    // Confirm before publishing
    if (!confirm('Are you sure you want to publish to the homepage?\n\nThis will make the selected items visible on the website.')) {
        return;
    }

    // Get ready URLs only (consistent with backend filter)
    const urls = getReadyUrls();

    // Disable button and show checking state
    publishBtn.disabled = true;
    const originalText = publishBtn.textContent;
    publishBtn.textContent = 'Checking...';

    // Check for duplicates first
    const { hasDuplicates, duplicates } = await checkForDuplicates();

    if (hasDuplicates) {
        const warningMessage = formatDuplicateWarning(duplicates);
        if (!confirm(warningMessage)) {
            // User cancelled - restore button
            publishBtn.disabled = false;
            publishBtn.textContent = originalText;
            return;
        }
    }

    // Proceed with publish
    publishBtn.textContent = 'Publishing...';

    try {
        const response = await fetch('/publisher/email/publish-v2', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                date: selectedDate,
                urls: urls
            })
        });

        // Check response status before parsing JSON
        if (!response.ok) {
            let errorMessage = `Server error: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.error || errorMessage;
            } catch (parseError) {
                errorMessage = `Server error: ${response.status} ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }

        const data = await response.json();
        publishBtn.disabled = false;

        if (data.success) {
            // Success - show green button with checkmark
            publishBtn.textContent = '✅ Published!';
            publishBtn.style.background = '#28a745';

            // Alert with confirmation
            alert('✅ PUBLISHED TO HOMEPAGE!\n\nNewsletter is now live at your-domain.com');

            // Reset button after 3 seconds
            setTimeout(() => {
                publishBtn.textContent = originalText;
                publishBtn.style.background = '';
            }, 3000);
        } else {
            publishBtn.textContent = originalText;
            alert('❌ ERROR PUBLISHING\n\n' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        publishBtn.disabled = false;
        publishBtn.textContent = originalText;
        console.error('Error publishing to homepage:', err);
        alert('❌ ERROR PUBLISHING\n\n' + err.message);
    }
}

// =============================================================================
// UNPUBLISH (Previously Published Articles)
// =============================================================================

/**
 * Unpublish a previously published article to make it includable again
 * @param {string} url - Press release URL or SEC filing URL
 * @param {boolean} isSecFiling - Whether this is an SEC filing (uses different endpoint)
 */
function unpublishArticle(url, isSecFiling = false) {
    if (!confirm('Unpublish this article and make it available for inclusion in today\'s newsletter?')) {
        return;
    }

    const endpoint = isSecFiling ? '/publisher/update-disclosure-status' : '/publisher/unpublish';
    const body = isSecFiling
        ? { filing_url: url, status: 'ready' }
        : { url: url };

    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(body)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to refresh the list
            location.reload();
        } else {
            alert('Error unpublishing: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error unpublishing:', err);
        alert('Error unpublishing article');
    });
}

/**
 * Initialize click handlers for previously published items
 */
function initPreviouslyPublishedHandlers() {
    // Desktop: Click on previously published badge or item
    document.querySelectorAll('.previously-published-badge').forEach(badge => {
        badge.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const item = this.closest('.release-item');
            if (item && item.dataset.url) {
                const isSecFiling = item.dataset.secFiling === 'true';
                unpublishArticle(item.dataset.url, isSecFiling);
            }
        });
    });

    // Desktop: Click anywhere on the previously published item row
    document.querySelectorAll('.release-item-previously-published').forEach(item => {
        item.addEventListener('click', function(e) {
            // Don't trigger if clicking on dropdowns or edit button
            if (e.target.closest('.release-actions') || e.target.closest('.edit-title-btn') || e.target.closest('.release-title')) {
                return;
            }
            if (this.dataset.url) {
                const isSecFiling = this.dataset.secFiling === 'true';
                unpublishArticle(this.dataset.url, isSecFiling);
            }
        });
    });

    // Mobile: Click on previously published badge
    document.querySelectorAll('.status-badge-previously-published').forEach(badge => {
        badge.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const card = this.closest('.publisher-card');
            if (card && card.dataset.url) {
                const isSecFiling = card.dataset.secFiling === 'true';
                unpublishArticle(card.dataset.url, isSecFiling);
            }
        });
    });

    // Mobile: Click anywhere on the previously published card
    document.querySelectorAll('.publisher-card-previously-published').forEach(card => {
        card.addEventListener('click', function(e) {
            // Don't trigger if clicking on forms or links
            if (e.target.closest('form') || e.target.closest('a') || e.target.closest('select')) {
                return;
            }
            if (this.dataset.url) {
                const isSecFiling = this.dataset.secFiling === 'true';
                unpublishArticle(this.dataset.url, isSecFiling);
            }
        });
    });
}

// Initialize previously published handlers on page load
document.addEventListener('DOMContentLoaded', function() {
    initPreviouslyPublishedHandlers();
});

