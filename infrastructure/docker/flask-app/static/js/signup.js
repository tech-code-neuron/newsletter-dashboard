/**
 * Signup Form Enhancement
 *
 * Adds client-side validation, loading states, and AJAX submission to all signup forms.
 * Works with both popup forms (.popup-form) and standalone forms (.signup-form, .signup-form-vertical).
 *
 * AJAX mode: Forms with data-ajax="true" submit via fetch() to avoid CSRF issues
 * on forms that don't have access to Flask-WTF CSRF tokens.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Select all signup form types
    const forms = document.querySelectorAll('.popup-form, .signup-form, .signup-form-vertical');

    forms.forEach(function(form) {
        const emailInput = form.querySelector('input[type="email"], input[name="email"]');
        const submitBtn = form.querySelector('button[type="submit"]');
        const honeypotInput = form.querySelector('input[name="website"]');
        const signupBox = form.closest('.signup-box') || form.closest('.signup-popup');
        const messageDiv = signupBox ? signupBox.querySelector('.signup-message') : null;

        if (!emailInput || !submitBtn) return;

        const originalBtnText = submitBtn.textContent;
        const isAjax = form.dataset.ajax === 'true';

        form.addEventListener('submit', function(e) {
            // Client-side email validation
            const email = emailInput.value.trim();
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

            if (!emailRegex.test(email)) {
                e.preventDefault();
                emailInput.setCustomValidity('Please enter a valid email address');
                emailInput.reportValidity();
                return;
            }

            // AJAX submission for homepage forms (no CSRF token needed)
            if (isAjax) {
                e.preventDefault();

                // Show loading state
                submitBtn.disabled = true;
                submitBtn.textContent = 'Subscribing...';

                // Build request body
                const body = { email: email };
                if (honeypotInput) {
                    body.website = honeypotInput.value;
                }

                fetch('/api/subscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(body)
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Show success message
                        if (messageDiv) {
                            messageDiv.textContent = data.message || 'Check your email to confirm.';
                            messageDiv.className = 'signup-message success';
                            messageDiv.style.display = 'block';
                        }
                        // Hide the form
                        form.style.display = 'none';
                    } else {
                        // Show error message
                        if (messageDiv) {
                            messageDiv.textContent = data.error || 'An error occurred. Please try again.';
                            messageDiv.className = 'signup-message error';
                            messageDiv.style.display = 'block';
                        }
                        // Reset button
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalBtnText;
                    }
                })
                .catch(error => {
                    console.error('Subscription error:', error);
                    if (messageDiv) {
                        messageDiv.textContent = 'An error occurred. Please try again.';
                        messageDiv.className = 'signup-message error';
                        messageDiv.style.display = 'block';
                    }
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalBtnText;
                });

                return;
            }

            // Non-AJAX forms (Flask-WTF with CSRF token) - just show loading state
            submitBtn.disabled = true;
            submitBtn.textContent = 'Subscribing...';
        });

        // Clear validation on input
        emailInput.addEventListener('input', function() {
            emailInput.setCustomValidity('');
            // Hide error message if showing
            if (messageDiv && messageDiv.classList.contains('error')) {
                messageDiv.style.display = 'none';
            }
        });
    });
});
