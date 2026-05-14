/**
 * REIT Email Viewer - Client-side interactions
 * Financial Editorial Design
 *
 * Features:
 * - Three-column Gmail-style layout
 * - Keyboard navigation (↑/↓/Enter/Esc/j/k)
 * - Persistent viewer pane (no modal)
 * - Smooth transitions
 * - AJAX email loading
 */

// ==============================================================================
// STATE
// ==============================================================================

let selectedEmailIndex = -1;
let emails = [];
let currentEmailId = null;

// ==============================================================================
// DOM READY
// ==============================================================================

document.addEventListener('DOMContentLoaded', function() {
    initializeEmails();
    initializeFilters();
    initializeKeyboardShortcuts();
    initializeViewerTabs();
    initializeButtons();
});

// ==============================================================================
// EMAIL LIST INITIALIZATION
// ==============================================================================

function initializeEmails() {
    const emailCards = document.querySelectorAll('.email-card');
    emails = Array.from(emailCards);

    console.log(`[Emails] Found ${emails.length} email cards`);
    console.log(`[Emails] First card:`, emails[0]);

    emails.forEach((card, index) => {
        console.log(`[Emails] Attaching click handler to card ${index}`);

        // Click to select
        card.addEventListener('click', function(e) {
            console.log(`[Emails] Clicked email ${index}`, e);
            selectEmail(index);
        });

        // Test if card is clickable
        card.style.cursor = 'pointer';
    });

    // Auto-select first email if any exist
    if (emails.length > 0 && window.innerWidth > 768) {
        console.log(`[Emails] Auto-selecting first email`);
        selectEmail(0);
    }
}

// ==============================================================================
// EMAIL SELECTION
// ==============================================================================

function selectEmail(index) {
    if (index < 0 || index >= emails.length) {
        return;
    }

    selectedEmailIndex = index;

    // Update visual state
    emails.forEach((card, i) => {
        if (i === index) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });

    // Scroll selected card into view
    emails[index].scrollIntoView({
        behavior: 'smooth',
        block: 'nearest'
    });

    // Load email in viewer pane
    const emailId = emails[index].getAttribute('data-email-id');
    loadEmailInViewer(emailId);
}

function deselectEmail() {
    selectedEmailIndex = -1;
    emails.forEach(card => card.classList.remove('selected'));

    // Show empty state
    document.getElementById('viewer-empty').style.display = 'flex';
    document.getElementById('viewer-content').style.display = 'none';
}

// ==============================================================================
// EMAIL VIEWER PANE
// ==============================================================================

function loadEmailInViewer(emailId) {
    if (currentEmailId === emailId) {
        return; // Already loaded
    }

    currentEmailId = emailId;

    // Show viewer content, hide empty state
    const viewerEmpty = document.getElementById('viewer-empty');
    const viewerContent = document.getElementById('viewer-content');
    const viewerLoading = document.getElementById('viewer-loading');
    const viewerEmail = document.getElementById('viewer-email');
    const viewerError = document.getElementById('viewer-error');

    viewerEmpty.style.display = 'none';
    viewerContent.style.display = 'flex';
    viewerLoading.style.display = 'flex';
    viewerEmail.style.display = 'none';
    viewerError.style.display = 'none';

    // Open mobile viewer on mobile devices
    openMobileViewer();

    // Fetch email detail via AJAX
    fetch(`/emails/${encodeURIComponent(emailId)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Email not found');
            }
            return response.json();
        })
        .then(data => {
            populateViewer(data);
            viewerLoading.style.display = 'none';
            viewerEmail.style.display = 'flex';
        })
        .catch(error => {
            console.error('Error loading email:', error);
            viewerLoading.style.display = 'none';
            viewerError.style.display = 'flex';
        });
}

function populateViewer(data) {
    // Subject
    document.getElementById('viewer-subject').textContent = data.metadata.subject || 'No subject';

    // Metadata
    document.getElementById('viewer-from').textContent = data.metadata.from || 'Unknown';
    document.getElementById('viewer-to').textContent = data.metadata.to || 'Unknown';
    document.getElementById('viewer-date').textContent = data.metadata.date_display || 'Unknown';

    // Ticker (optional)
    const tickerRow = document.getElementById('viewer-ticker-row');
    const tickerValue = document.getElementById('viewer-ticker');
    if (data.metadata.ticker) {
        tickerValue.textContent = data.metadata.ticker;
        tickerRow.style.display = 'flex';
    } else {
        tickerRow.style.display = 'none';
    }

    // Download button
    const downloadBtn = document.getElementById('download-btn');
    if (data.raw_url) {
        downloadBtn.href = data.raw_url;
    }

    // Body content
    const htmlFrame = document.getElementById('html-frame');
    const textContent = document.getElementById('text-content');
    const headersContent = document.getElementById('headers-content');
    const htmlTab = document.getElementById('html-tab');
    const textTab = document.getElementById('text-tab');

    // HTML body (use URL-based loading like publisher pattern)
    if (data.has_html) {
        htmlFrame.src = `/emails/${encodeURIComponent(currentEmailId)}/preview?t=${Date.now()}`;
        htmlTab.style.display = 'block';
        switchViewerTab('html');
    } else {
        htmlTab.style.display = 'none';
    }

    // Text body
    if (data.body_text) {
        textContent.textContent = data.body_text;
        textTab.style.display = 'block';
        if (!data.has_html) {
            switchViewerTab('text');
        }
    } else {
        textTab.style.display = 'none';
    }

    // Headers
    if (data.headers) {
        let headersText = '';
        for (const [key, value] of Object.entries(data.headers)) {
            headersText += `${key}: ${value}\n`;
        }
        headersContent.textContent = headersText;
    }
}

// ==============================================================================
// VIEWER TABS
// ==============================================================================

function initializeViewerTabs() {
    const tabs = document.querySelectorAll('.viewer-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const tabType = this.getAttribute('data-tab');
            switchViewerTab(tabType);
        });
    });
}

function switchViewerTab(tabType) {
    const tabs = document.querySelectorAll('.viewer-tab');
    const panes = document.querySelectorAll('.viewer-pane');

    tabs.forEach(tab => {
        if (tab.getAttribute('data-tab') === tabType) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    panes.forEach(pane => {
        if (pane.id === `${tabType}-pane`) {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });
}

// ==============================================================================
// KEYBOARD SHORTCUTS
// ==============================================================================

function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Don't trigger if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            // Exception: '/' to focus search
            if (e.key === '/') {
                e.preventDefault();
                document.getElementById('search-input').focus();
            }
            return;
        }

        switch(e.key) {
            case 'ArrowUp':
            case 'k':
                e.preventDefault();
                navigatePrevious();
                break;

            case 'ArrowDown':
            case 'j':
                e.preventDefault();
                navigateNext();
                break;

            case 'Enter':
                e.preventDefault();
                if (selectedEmailIndex >= 0) {
                    // Already selected, do nothing (viewer pane already showing)
                }
                break;

            case 'Escape':
                e.preventDefault();
                deselectEmail();
                break;

            case 'r':
                e.preventDefault();
                refreshEmailList();
                break;

            case '?':
                e.preventDefault();
                toggleShortcutsHelp();
                break;
        }
    });
}

function navigatePrevious() {
    if (emails.length === 0) return;

    if (selectedEmailIndex <= 0) {
        selectEmail(emails.length - 1); // Wrap to last
    } else {
        selectEmail(selectedEmailIndex - 1);
    }
}

function navigateNext() {
    if (emails.length === 0) return;

    if (selectedEmailIndex < 0 || selectedEmailIndex >= emails.length - 1) {
        selectEmail(0); // Wrap to first
    } else {
        selectEmail(selectedEmailIndex + 1);
    }
}

function refreshEmailList() {
    window.location.reload();
}

function toggleShortcutsHelp() {
    const help = document.getElementById('shortcuts-help');
    help.classList.toggle('open');
}

// ==============================================================================
// MOBILE VIEWER
// ==============================================================================

function openMobileViewer() {
    const viewerColumn = document.querySelector('.email-viewer-column');
    if (viewerColumn && window.innerWidth <= 768) {
        viewerColumn.classList.add('mobile-active');
        document.body.style.overflow = 'hidden'; // Prevent background scroll
    }
}

function closeMobileViewer() {
    const viewerColumn = document.querySelector('.email-viewer-column');
    if (viewerColumn) {
        viewerColumn.classList.remove('mobile-active');
        document.body.style.overflow = ''; // Restore scroll
    }
}

// ==============================================================================
// BUTTONS
// ==============================================================================

function initializeButtons() {
    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshEmailList);
    }

    // Shortcuts button
    const shortcutsBtn = document.getElementById('shortcuts-btn');
    if (shortcutsBtn) {
        shortcutsBtn.addEventListener('click', toggleShortcutsHelp);
    }

    // Close shortcuts
    const shortcutsClose = document.getElementById('shortcuts-close');
    if (shortcutsClose) {
        shortcutsClose.addEventListener('click', toggleShortcutsHelp);
    }

    // Mobile close button
    const mobileCloseBtn = document.getElementById('mobile-close-btn');
    if (mobileCloseBtn) {
        mobileCloseBtn.addEventListener('click', closeMobileViewer);
    }

    // Click outside shortcuts overlay
    const shortcutsOverlay = document.querySelector('.shortcuts-overlay');
    if (shortcutsOverlay) {
        shortcutsOverlay.addEventListener('click', toggleShortcutsHelp);
    }
}

// ==============================================================================
// FILTERS
// ==============================================================================

function initializeFilters() {
    // Initialize flatpickr for date inputs
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    if (startDateInput && endDateInput && typeof flatpickr !== 'undefined') {
        flatpickr(startDateInput, {
            dateFormat: 'Y-m-d',
            maxDate: 'today'
        });

        flatpickr(endDateInput, {
            dateFormat: 'Y-m-d',
            maxDate: 'today'
        });
    }

    // Date preset buttons
    const presetButtons = document.querySelectorAll('.preset-btn');
    presetButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const preset = this.getAttribute('data-preset');
            applyDatePreset(preset);
        });
    });

    // Search input - submit on Enter
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                document.getElementById('filter-form').submit();
            }
        });
    }
}

function applyDatePreset(preset) {
    const today = new Date();
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    let startDate;

    switch(preset) {
        case 'today':
            startDate = today;
            break;
        case '7':
            startDate = new Date(today);
            startDate.setDate(today.getDate() - 7);
            break;
        case '30':
            startDate = new Date(today);
            startDate.setDate(today.getDate() - 30);
            break;
        case 'all':
            startDate = new Date(today);
            startDate.setFullYear(today.getFullYear() - 1);
            break;
        default:
            return;
    }

    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    startDateInput.value = formatDate(startDate);
    endDateInput.value = formatDate(today);

    document.getElementById('filter-form').submit();
}

// ==============================================================================
// RELATIVE TIMESTAMPS
// ==============================================================================

function updateRelativeTimestamps() {
    const timeElements = document.querySelectorAll('.email-time[data-timestamp]');

    timeElements.forEach(element => {
        const timestamp = element.getAttribute('data-timestamp');
        if (!timestamp) return;

        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        let relativeTime;

        if (diffMins < 1) {
            relativeTime = 'Just now';
        } else if (diffMins < 60) {
            relativeTime = `${diffMins}m ago`;
        } else if (diffHours < 24) {
            relativeTime = `${diffHours}h ago`;
        } else if (diffDays === 1) {
            relativeTime = 'Yesterday';
        } else if (diffDays < 7) {
            relativeTime = `${diffDays}d ago`;
        } else {
            // Show formatted date
            const options = { month: 'short', day: 'numeric' };
            relativeTime = date.toLocaleDateString('en-US', options);
        }

        // Keep original format in title for tooltip
        element.setAttribute('title', element.textContent);
        element.textContent = relativeTime;
    });
}

// Update relative timestamps every minute
setInterval(updateRelativeTimestamps, 60000);

// Initial update
if (document.readyState === 'complete') {
    updateRelativeTimestamps();
} else {
    window.addEventListener('load', updateRelativeTimestamps);
}
