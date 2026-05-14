/**
 * Index/Dashboard Page JavaScript
 *
 * SOLID Principle: Page-specific logic separated from global utils.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize select all functionality for press releases
    initializeSelectAll('select-all-releases', 'release-checkbox', 'delete-selected');

    // Handle delete form submission
    const form = document.getElementById('delete-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const checkboxes = document.querySelectorAll('.release-checkbox');
            const selected = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => cb.value);

            if (selected.length === 0) {
                e.preventDefault();
                return;
            }

            if (!confirm(`Archive ${selected.length} press release(s)?`)) {
                e.preventDefault();
                return;
            }

            // Add selected IDs as hidden inputs
            selected.forEach(id => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'release_ids';
                input.value = id;
                form.appendChild(input);
            });
        });
    }
});
