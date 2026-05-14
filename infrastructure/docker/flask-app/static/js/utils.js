/**
 * JavaScript Utilities
 *
 * SOLID Principle: Reusable utility functions.
 * Single Responsibility: Each function does one thing.
 */

/**
 * CSRF Token Support for AJAX Requests
 * Automatically includes CSRF token in all POST/PUT/DELETE/PATCH requests
 */
(function() {
    // Get CSRF token from meta tag
    function getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }

    // Override fetch to include CSRF token
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        // Add CSRF token header for state-changing requests
        if (options.method && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(options.method.toUpperCase())) {
            options.headers = options.headers || {};
            if (!options.headers['X-CSRFToken']) {
                options.headers['X-CSRFToken'] = getCSRFToken();
            }
        }
        return originalFetch(url, options);
    };

    // If jQuery is loaded, add CSRF token to all AJAX requests
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof $ !== 'undefined' && $.ajaxSetup) {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                        xhr.setRequestHeader("X-CSRFToken", getCSRFToken());
                    }
                }
            });
        }
    });
})();

/**
 * Make table rows clickable
 * Looks for rows with class 'clickable-row' and data-href attribute
 */
function initializeClickableRows() {
    const clickableRows = document.querySelectorAll('.clickable-row');
    if (clickableRows && clickableRows.length > 0) {
        clickableRows.forEach(row => {
            row.addEventListener('click', function() {
                if (this.dataset.href) {
                    window.location.href = this.dataset.href;
                }
            });
        });
    }
}

/**
 * Initialize "select all" checkbox functionality
 * @param {string} selectAllId - ID of the "select all" checkbox
 * @param {string} checkboxClass - Class of individual checkboxes
 * @param {string} buttonId - ID of button to enable/disable
 */
function initializeSelectAll(selectAllId, checkboxClass, buttonId) {
    const selectAllCheckbox = document.getElementById(selectAllId);
    const checkboxes = document.querySelectorAll(`.${checkboxClass}`);
    const button = document.getElementById(buttonId);

    if (!selectAllCheckbox || !button) return;

    // Select/deselect all
    selectAllCheckbox.addEventListener('change', function() {
        checkboxes.forEach(checkbox => {
            checkbox.checked = this.checked;
        });
        updateButtonState();
    });

    // Update select all checkbox when individual checkboxes change
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            const someChecked = Array.from(checkboxes).some(cb => cb.checked);

            selectAllCheckbox.checked = allChecked;
            selectAllCheckbox.indeterminate = someChecked && !allChecked;

            updateButtonState();
        });
    });

    // Enable/disable button based on selection
    function updateButtonState() {
        const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
        button.disabled = !anyChecked;
    }
}

/**
 * Show modal by ID
 * @param {string} modalId - ID of the modal element
 */
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
    }
}

/**
 * Hide modal by ID
 * @param {string} modalId - ID of the modal element
 */
function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Close modal when clicking outside
 * @param {string} modalId - ID of the modal element
 */
function initializeModalClose(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    // Close when clicking outside modal content
    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            hideModal(modalId);
        }
    });

    // Close with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && modal.style.display === 'block') {
            hideModal(modalId);
        }
    });
}

/**
 * Prevent form submission on Enter key (useful for search forms)
 * @param {string} formId - ID of the form element
 */
function preventEnterSubmit(formId) {
    const form = document.getElementById(formId);
    if (form) {
        form.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
            }
        });
    }
}

/**
 * Debounce function to limit rate of function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Milliseconds to wait
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Format date to readable string
 * @param {Date|string} date - Date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
    if (!(date instanceof Date)) {
        date = new Date(date);
    }
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Safe JSON parse with fallback
 * @param {string} json - JSON string to parse
 * @param {*} fallback - Fallback value if parse fails
 * @returns {*} Parsed object or fallback
 */
function safeJSONParse(json, fallback = null) {
    try {
        return JSON.parse(json);
    } catch (e) {
        console.error('JSON parse error:', e);
        return fallback;
    }
}

/**
 * Enable backspace key to navigate back
 * Only works when NOT in an input/textarea/select element
 */
function initializeBackspaceNavigation() {
    document.addEventListener('keydown', function(event) {
        // Check if backspace key was pressed
        if (event.key === 'Backspace' || event.keyCode === 8) {
            // Get the active element
            const activeElement = document.activeElement;
            const tagName = activeElement.tagName.toLowerCase();

            // Check if we're NOT in an input field
            const isEditable = (
                tagName === 'input' ||
                tagName === 'textarea' ||
                tagName === 'select' ||
                activeElement.isContentEditable
            );

            // If not in an editable field, go back
            if (!isEditable) {
                event.preventDefault();
                window.history.back();
            }
        }
    });
}

// Initialize common functionality when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Make all clickable rows work
    initializeClickableRows();

    // Enable backspace to go back
    initializeBackspaceNavigation();
});
