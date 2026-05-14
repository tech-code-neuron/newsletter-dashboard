/**
 * Email Viewer - Client-side interactions
 *
 * Features:
 * - Modal open/close
 * - AJAX email detail fetch
 * - Date picker initialization
 * - Date preset buttons
 * - Body tab switching (HTML/Text)
 */

// ==============================================================================
// DOM Ready
// ==============================================================================

document.addEventListener('DOMContentLoaded', function() {
    initializeFilters();
    initializeEmailList();
    initializeModal();
});

// ==============================================================================
// Filter Initialization
// ==============================================================================

function initializeFilters() {
    // Initialize flatpickr for date inputs
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    if (startDateInput && endDateInput) {
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
    const presetButtons = document.querySelectorAll('[data-preset]');
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
            // Set to 1 year ago for "all time"
            startDate = new Date(today);
            startDate.setFullYear(today.getFullYear() - 1);
            break;
        default:
            return;
    }

    // Format dates as YYYY-MM-DD
    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    startDateInput.value = formatDate(startDate);
    endDateInput.value = formatDate(today);

    // Submit form
    document.getElementById('filter-form').submit();
}

// ==============================================================================
// Email List Initialization
// ==============================================================================

function initializeEmailList() {
    // Desktop: Table row click
    const tableRows = document.querySelectorAll('.email-row');
    tableRows.forEach(row => {
        row.addEventListener('click', function(e) {
            // Don't trigger if clicking button
            if (e.target.tagName === 'BUTTON' || e.target.closest('button')) {
                return;
            }
            const emailId = this.getAttribute('data-email-id');
            openEmailModal(emailId);
        });
    });

    // Mobile: Card click
    const mobileCards = document.querySelectorAll('.email-card');
    mobileCards.forEach(card => {
        card.addEventListener('click', function(e) {
            // Don't trigger if clicking button
            if (e.target.tagName === 'BUTTON' || e.target.closest('button')) {
                return;
            }
            const emailId = this.getAttribute('data-email-id');
            openEmailModal(emailId);
        });
    });

    // View buttons
    const viewButtons = document.querySelectorAll('.view-email-btn');
    viewButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const emailId = this.getAttribute('data-email-id');
            openEmailModal(emailId);
        });
    });
}

// ==============================================================================
// Modal Initialization
// ==============================================================================

function initializeModal() {
    const modal = document.getElementById('email-modal');
    const closeBtn = document.getElementById('modal-close');

    // Close button
    if (closeBtn) {
        closeBtn.addEventListener('click', closeEmailModal);
    }

    // Click outside to close
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeEmailModal();
            }
        });
    }

    // Escape key to close
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('open')) {
            closeEmailModal();
        }
    });

    // Body tabs
    const bodyTabs = document.querySelectorAll('.body-tab');
    bodyTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const tabType = this.getAttribute('data-tab');
            switchBodyTab(tabType);
        });
    });
}

// ==============================================================================
// Email Modal Functions
// ==============================================================================

function openEmailModal(emailId) {
    console.log('Opening email modal for:', emailId);

    const modal = document.getElementById('email-modal');
    const modalWindow = modal.querySelector('.modal-window');
    const loadingState = document.getElementById('loading-state');
    const emailContent = document.getElementById('email-content');
    const errorState = document.getElementById('error-state');

    if (!modal || !modalWindow) {
        console.error('Modal elements not found');
        return;
    }

    console.log('Showing modal...');

    // Show modal with loading state
    modal.classList.add('open');
    modalWindow.classList.add('open');
    loadingState.style.display = 'block';
    emailContent.style.display = 'none';
    errorState.style.display = 'none';

    // Fetch email detail via AJAX
    fetch(`/emails/${encodeURIComponent(emailId)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Email not found');
            }
            return response.json();
        })
        .then(data => {
            populateEmailModal(data);
            loadingState.style.display = 'none';
            emailContent.style.display = 'flex';
        })
        .catch(error => {
            console.error('Error loading email:', error);
            loadingState.style.display = 'none';
            errorState.style.display = 'block';
        });
}

function closeEmailModal() {
    const modal = document.getElementById('email-modal');
    const modalWindow = modal.querySelector('.modal-window');

    modal.classList.remove('open');
    modalWindow.classList.remove('open');

    // Clear modal content after animation
    setTimeout(() => {
        clearEmailModal();
    }, 300);
}

function populateEmailModal(data) {
    // Update modal title
    document.getElementById('modal-subject').textContent = data.metadata.subject || 'Email';

    // Populate metadata
    document.getElementById('email-from').textContent = data.metadata.from || 'Unknown';
    document.getElementById('email-to').textContent = data.metadata.to || 'Unknown';
    document.getElementById('email-date').textContent = data.metadata.date_display || 'Unknown';
    document.getElementById('email-subject').textContent = data.metadata.subject || 'No subject';
    document.getElementById('email-size').textContent = `${data.metadata.size || 0} KB`;

    // Ticker (optional)
    const tickerRow = document.getElementById('ticker-row');
    const tickerValue = document.getElementById('email-ticker');
    if (data.metadata.ticker) {
        tickerValue.textContent = data.metadata.ticker;
        tickerRow.style.display = 'flex';
    } else {
        tickerRow.style.display = 'none';
    }

    // Attachments (optional)
    const attachmentsRow = document.getElementById('attachments-row');
    const attachmentsValue = document.getElementById('email-attachments');
    if (data.metadata.has_attachments) {
        attachmentsValue.textContent = `${data.metadata.attachment_count} file(s)`;
        attachmentsRow.style.display = 'flex';
    } else {
        attachmentsRow.style.display = 'none';
    }

    // Headers
    const headersContent = document.getElementById('email-headers');
    if (data.headers) {
        let headersText = '';
        for (const [key, value] of Object.entries(data.headers)) {
            headersText += `${key}: ${value}\n`;
        }
        headersContent.textContent = headersText;
    }

    // Download button
    const downloadBtn = document.getElementById('download-btn');
    if (data.raw_url) {
        downloadBtn.href = data.raw_url;
        downloadBtn.style.display = 'inline-block';
    } else {
        downloadBtn.style.display = 'none';
    }

    // Body content
    const htmlFrame = document.getElementById('html-frame');
    const textContent = document.getElementById('text-content');
    const htmlTab = document.getElementById('html-tab');
    const textTab = document.getElementById('text-tab');
    const htmlPane = document.getElementById('html-pane');
    const textPane = document.getElementById('text-pane');
    const noBodyPane = document.getElementById('no-body-pane');

    if (data.has_html && data.body_html) {
        // Show HTML in iframe
        const iframeDoc = htmlFrame.contentDocument || htmlFrame.contentWindow.document;
        iframeDoc.open();
        iframeDoc.write(data.body_html);
        iframeDoc.close();

        htmlTab.style.display = 'block';
        htmlPane.style.display = 'block';
        noBodyPane.style.display = 'none';

        // Set HTML tab as active
        switchBodyTab('html');
    } else if (data.body_text) {
        // Show text only
        textContent.textContent = data.body_text;
        htmlTab.style.display = 'none';
        textPane.style.display = 'block';
        noBodyPane.style.display = 'none';

        // Set text tab as active
        switchBodyTab('text');
    } else {
        // No body available
        htmlTab.style.display = 'none';
        textTab.style.display = 'none';
        htmlPane.style.display = 'none';
        textPane.style.display = 'none';
        noBodyPane.style.display = 'block';
    }

    // Show text tab if available
    if (data.body_text) {
        textContent.textContent = data.body_text;
        textTab.style.display = 'block';
    } else {
        textTab.style.display = 'none';
    }
}

function clearEmailModal() {
    // Clear all modal content
    document.getElementById('modal-subject').textContent = 'Email';
    document.getElementById('email-from').textContent = '';
    document.getElementById('email-to').textContent = '';
    document.getElementById('email-date').textContent = '';
    document.getElementById('email-subject').textContent = '';
    document.getElementById('email-ticker').textContent = '';
    document.getElementById('email-size').textContent = '';
    document.getElementById('email-headers').textContent = '';

    const htmlFrame = document.getElementById('html-frame');
    const iframeDoc = htmlFrame.contentDocument || htmlFrame.contentWindow.document;
    iframeDoc.open();
    iframeDoc.write('');
    iframeDoc.close();

    document.getElementById('text-content').textContent = '';
}

function switchBodyTab(tabType) {
    const htmlTab = document.getElementById('html-tab');
    const textTab = document.getElementById('text-tab');
    const htmlPane = document.getElementById('html-pane');
    const textPane = document.getElementById('text-pane');

    // Remove active class from all tabs
    htmlTab.classList.remove('active');
    textTab.classList.remove('active');
    htmlPane.classList.remove('active');
    textPane.classList.remove('active');

    // Add active class to selected tab
    if (tabType === 'html') {
        htmlTab.classList.add('active');
        htmlPane.classList.add('active');
    } else if (tabType === 'text') {
        textTab.classList.add('active');
        textPane.classList.add('active');
    }
}
