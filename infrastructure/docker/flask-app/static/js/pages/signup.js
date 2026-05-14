/**
 * Newsletter Signup Page JavaScript
 *
 * Handles:
 * - Opening/closing signup popup
 * - Form submission via fetch
 * - Loading/success/error states
 */

document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const overlay = document.getElementById('signup-overlay');
    const openBtn = document.getElementById('open-signup-btn');
    const closeBtn = document.getElementById('close-signup-btn');
    const form = document.getElementById('signup-form');
    const submitBtn = document.getElementById('signup-submit-btn');
    const formContainer = document.getElementById('signup-form-container');
    const successContainer = document.getElementById('signup-success-container');
    const errorMessage = document.getElementById('signup-error-message');
    const errorText = document.getElementById('signup-error-text');
    const emailInput = document.getElementById('signup-email');

    // State
    let isSubmitting = false;

    /**
     * Open the signup popup
     */
    function openPopup() {
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent background scroll

        // Focus email input after animation
        setTimeout(() => {
            emailInput.focus();
        }, 200);
    }

    /**
     * Close the signup popup
     */
    function closePopup() {
        overlay.classList.remove('active');
        document.body.style.overflow = ''; // Restore scroll

        // Reset form state after closing
        setTimeout(() => {
            resetForm();
        }, 200);
    }

    /**
     * Reset form to initial state
     */
    function resetForm() {
        form.reset();
        formContainer.style.display = 'block';
        successContainer.style.display = 'none';
        errorMessage.style.display = 'none';
        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
        isSubmitting = false;
    }

    /**
     * Show success state
     */
    function showSuccess() {
        formContainer.style.display = 'none';
        successContainer.style.display = 'block';
        errorMessage.style.display = 'none';
    }

    /**
     * Show error state
     * @param {string} message - Error message to display
     */
    function showError(message) {
        errorText.textContent = message;
        errorMessage.style.display = 'block';
        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
        isSubmitting = false;
    }

    /**
     * Handle form submission
     * @param {Event} e - Submit event
     */
    async function handleSubmit(e) {
        e.preventDefault();

        if (isSubmitting) return;

        // Get form data
        const email = emailInput.value.trim();

        // Basic validation
        if (!email) {
            showError('Please enter your email address.');
            return;
        }

        // Email format validation
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            showError('Please enter a valid email address.');
            return;
        }

        // Set loading state
        isSubmitting = true;
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        errorMessage.style.display = 'none';

        try {
            const response = await fetch('https://fqlxgkv638.execute-api.us-east-1.amazonaws.com/prod/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email: email })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                showSuccess();
            } else {
                showError(data.error || 'Something went wrong. Please try again.');
            }
        } catch (error) {
            console.error('Signup error:', error);
            showError('Unable to connect. Please check your connection and try again.');
        }
    }

    // Event Listeners

    // Open popup
    if (openBtn) {
        openBtn.addEventListener('click', openPopup);
    }

    // Close popup - X button
    if (closeBtn) {
        closeBtn.addEventListener('click', closePopup);
    }

    // Close popup - Click on backdrop
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                closePopup();
            }
        });
    }

    // Close popup - Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            closePopup();
        }
    });

    // Form submission
    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
});
