/**
 * Edit Press Release Page JavaScript
 * Extracted from inline <script> tag (SOLID compliance)
 *
 * Handles:
 * - Word counter for full text field
 * - Delete button confirmation
 * - Relevance decision buttons (AJAX)
 */

document.addEventListener('DOMContentLoaded', function() {
    // Word counter for full text
    const fullText = document.getElementById('full_text');
    const wordCountEdit = document.getElementById('word-count-edit');
    const wordLimitInfoEdit = document.getElementById('word-limit-info-edit');

    function updateWordCount() {
        const text = fullText.value.trim();
        const words = text ? text.split(/\s+/).length : 0;
        wordCountEdit.textContent = words + ' word' + (words === 1 ? '' : 's');

        if (words > 2000) {
            wordLimitInfoEdit.style.display = 'inline';
        } else {
            wordLimitInfoEdit.style.display = 'none';
        }
    }

    fullText.addEventListener('input', updateWordCount);
    updateWordCount(); // Initialize on page load

    // Delete button with confirmation
    document.getElementById('delete-btn').addEventListener('click', function() {
        if (confirm('Are you sure you want to PERMANENTLY DELETE this press release?\n\nThis action cannot be undone.')) {
            document.getElementById('delete-form').submit();
        }
    });

    // AJAX Handlers for Relevance Buttons
    document.addEventListener('click', async (e) => {
        if (e.target.classList.contains('btn-relevant-detail')) {
            await setRelevanceDetail(e.target.dataset.prId, 'relevant');
        }

        if (e.target.classList.contains('btn-not-relevant-detail')) {
            await setRelevanceDetail(e.target.dataset.prId, 'not_relevant');
        }

        if (e.target.classList.contains('btn-undo-detail')) {
            await setRelevanceDetail(e.target.dataset.prId, null);
        }
    });

    async function setRelevanceDetail(prId, decision) {
        try {
            const response = await fetch(`/api/press-release/${prId}/relevance`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ decision })
            });

            if (response.ok) {
                // Reload page to show updated decision
                window.location.reload();
            } else {
                alert('Error updating relevance. Please try again.');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error updating relevance. Please try again.');
        }
    }
});
