/**
 * Disclosure Detail Page JavaScript
 * Handles title editing with modal (desktop) and AJAX submission
 */

document.addEventListener('DOMContentLoaded', function() {
    initTitleEdit();
});

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
 * Initialize title editing functionality
 */
function initTitleEdit() {
    const editBtn = document.getElementById('edit-title-btn');
    const saveBtn = document.getElementById('save-title-btn');
    const cancelBtn = document.getElementById('cancel-title-btn');
    const closeBtn = document.getElementById('title-modal-close');
    const overlay = document.getElementById('title-modal-overlay');

    if (editBtn) {
        editBtn.addEventListener('click', openTitleModal);
    }
    if (saveBtn) {
        saveBtn.addEventListener('click', saveTitle);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeTitleModal);
    }
    if (closeBtn) {
        closeBtn.addEventListener('click', closeTitleModal);
    }
    if (overlay) {
        overlay.addEventListener('click', closeTitleModal);
    }

    // Handle Enter key in title input
    const titleInput = document.getElementById('title-input');
    if (titleInput) {
        titleInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveTitle();
            }
            if (e.key === 'Escape') {
                closeTitleModal();
            }
        });
    }
}

/**
 * Open the title edit modal
 */
function openTitleModal() {
    const modal = document.getElementById('title-modal');
    const overlay = document.getElementById('title-modal-overlay');
    const titleInput = document.getElementById('title-input');

    if (modal && overlay) {
        overlay.classList.add('open');
        modal.classList.add('open');
        if (titleInput) {
            titleInput.focus();
            titleInput.select();
        }
    }
}

/**
 * Close the title edit modal
 */
function closeTitleModal() {
    const modal = document.getElementById('title-modal');
    const overlay = document.getElementById('title-modal-overlay');

    if (modal && overlay) {
        overlay.classList.remove('open');
        modal.classList.remove('open');
    }
}

/**
 * Save the edited title via AJAX
 */
function saveTitle() {
    const filingUrl = document.getElementById('title-edit-filing-url').value;
    const titleInput = document.getElementById('title-input');
    const title = titleInput.value.trim();
    const saveBtn = document.getElementById('save-title-btn');

    // Disable button during save
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';

    fetch('/disclosures/update-title', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            filing_url: filingUrl,
            title: title
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update the displayed title
            const displayTitle = document.getElementById('disclosure-title');
            if (displayTitle) {
                displayTitle.textContent = title || 'Untitled Filing';
            }
            // Also update the mobile input
            const mobileInput = document.querySelector('.mobile-title-input');
            if (mobileInput) {
                mobileInput.value = title;
            }
            closeTitleModal();
        } else {
            alert('Error saving title: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error saving title:', err);
        alert('Error saving title: ' + err.message);
    })
    .finally(() => {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    });
}
