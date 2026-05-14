/**
 * Review Page JavaScript
 *
 * Handles email review actions, scanning, and modal interactions.
 */

/* ============================================================================
   EMAIL ACTIONS
   ============================================================================ */

async function addToPressReleases(emailId) {
    const row = document.getElementById(`email-${emailId}`);
    const addBtn = row.querySelector('.add-btn');
    const deleteBtn = row.querySelector('.delete-btn');

    // Update UI immediately
    row.classList.add('processing');
    row.querySelector('.status-badge').textContent = 'processing';
    row.querySelector('.status-badge').classList.add('status-processing');
    addBtn.disabled = true;
    deleteBtn.disabled = true;
    addBtn.innerHTML = '<span class="spinner"></span>Processing...';

    try {
        const response = await fetch(`/api/review/${emailId}/add-to-press-releases`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            // Show success message
            addBtn.innerHTML = 'Processing in background...';

            // Check status every 3 seconds
            const checkStatus = setInterval(async () => {
                // In production, you'd have an endpoint to check status
                // For now, just reload after 10 seconds
                setTimeout(() => {
                    location.reload();
                }, 10000);
                clearInterval(checkStatus);
            }, 3000);
        } else {
            alert('Error: ' + data.error);
            addBtn.innerHTML = 'Add to PRs';
            addBtn.disabled = false;
            deleteBtn.disabled = false;
            row.classList.remove('processing');
        }
    } catch (error) {
        alert('Network error: ' + error.message);
        addBtn.innerHTML = 'Add to PRs';
        addBtn.disabled = false;
        deleteBtn.disabled = false;
        row.classList.remove('processing');
    }
}

async function deleteEmail(emailId) {
    if (!confirm('Delete this email from Gmail and remove from review?')) {
        return;
    }

    const row = document.getElementById(`email-${emailId}`);
    const addBtn = row.querySelector('.add-btn');
    const deleteBtn = row.querySelector('.delete-btn');

    // Update UI
    deleteBtn.disabled = true;
    addBtn.disabled = true;
    deleteBtn.innerHTML = '<span class="spinner"></span>Deleting...';

    try {
        const response = await fetch(`/api/review/${emailId}/delete`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            // Mark as deleted
            row.classList.add('deleted');
            deleteBtn.innerHTML = data.gmail_deleted ? 'Deleted from Gmail' : 'Removed';

            // Remove row after 2 seconds
            setTimeout(() => {
                row.style.display = 'none';

                // Reload if no more rows
                const visibleRows = document.querySelectorAll('.email-row:not([style*="display: none"])');
                if (visibleRows.length === 0) {
                    location.reload();
                }
            }, 2000);
        } else {
            alert('Error: ' + data.error);
            deleteBtn.innerHTML = 'Delete';
            deleteBtn.disabled = false;
            addBtn.disabled = false;
        }
    } catch (error) {
        alert('Network error: ' + error.message);
        deleteBtn.innerHTML = 'Delete';
        deleteBtn.disabled = false;
        addBtn.disabled = false;
    }
}

// Auto-refresh every 30 seconds if there are processing emails
setInterval(() => {
    const processingEmails = document.querySelectorAll('.email-row.processing');
    if (processingEmails.length > 0) {
        location.reload();
    }
}, 30000);

/* ============================================================================
   EMAIL MODAL
   ============================================================================ */

function showEmailModal(emailId) {
    const modal = document.getElementById('emailModal');
    const screenshot = document.getElementById('emailScreenshot');
    const subject = document.getElementById('modalSubject');

    // Get subject and screenshot from row
    const row = document.getElementById(`email-${emailId}`);
    const subjectText = row.querySelector('td:nth-child(3) > div:first-child').textContent;
    subject.textContent = subjectText;

    // Get screenshot path from preview div
    const previewImg = row.querySelector('.screenshot-preview img');
    if (previewImg) {
        screenshot.src = previewImg.src;
        screenshot.classList.remove('zoomed');
        modal.style.display = 'block';
    } else {
        alert('No screenshot available for this email');
    }
}

function toggleZoom(img) {
    img.classList.toggle('zoomed');
}

function closeEmailModal() {
    const modal = document.getElementById('emailModal');
    modal.style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('emailModal');
    if (event.target == modal) {
        closeEmailModal();
    }
}

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeEmailModal();
    }
});

/* ============================================================================
   INBOX SCANNING
   ============================================================================ */

let progressInterval = null;

async function scanInbox(range) {
    const scanButtons = document.querySelectorAll('.btn-group button');
    const abortBtn = document.getElementById('abortBtn');
    const progressContainer = document.getElementById('progressContainer');

    // Disable scan buttons
    scanButtons.forEach(btn => btn.disabled = true);
    abortBtn.style.display = 'inline-block';
    progressContainer.style.display = 'block';

    try {
        const response = await fetch('/api/review/scan-inbox', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({range: range})
        });

        const data = await response.json();

        if (data.success) {
            // Start progress polling
            progressInterval = setInterval(updateProgress, 500);
        } else {
            alert('Failed to start scan: ' + data.error);
            resetUI();
        }
    } catch (error) {
        alert('Network error: ' + error.message);
        resetUI();
    }
}

async function updateProgress() {
    try {
        const response = await fetch('/api/review/scan-progress');
        const progress = await response.json();

        // Update progress bar
        const percent = progress.total > 0 ? (progress.current / progress.total * 100) : 0;
        document.getElementById('progressBar').style.width = percent + '%';
        document.getElementById('progressBar').textContent = Math.round(percent) + '%';

        // Update status
        document.getElementById('progressStatus').textContent = progress.status;

        // Update time estimate
        if (progress.estimated_seconds > 0) {
            const mins = Math.floor(progress.estimated_seconds / 60);
            const secs = progress.estimated_seconds % 60;
            document.getElementById('progressTime').textContent =
                mins > 0 ? `~${mins}m ${secs}s remaining` : `~${secs}s remaining`;
        } else {
            document.getElementById('progressTime').textContent = 'Calculating...';
        }

        // Update stats
        document.getElementById('progressStats').textContent =
            `${progress.current}/${progress.total} emails processed`;
        document.getElementById('progressNew').textContent = progress.new_count;
        document.getElementById('progressExisting').textContent = progress.existing_count;

        // Check if complete
        if (!progress.active) {
            clearInterval(progressInterval);
            progressInterval = null;

            // Show completion message
            setTimeout(() => {
                if (progress.status.includes('complete')) {
                    alert(`Scan complete!\n\nNew: ${progress.new_count}\nExisting: ${progress.existing_count}`);
                    location.reload();
                } else if (progress.status.includes('borted')) {
                    alert('Scan aborted');
                    resetUI();
                } else {
                    alert('Scan ended: ' + progress.status);
                    resetUI();
                }
            }, 500);
        }
    } catch (error) {
        console.error('Progress update error:', error);
    }
}

async function abortScan() {
    if (!confirm('Abort the current scan?')) {
        return;
    }

    try {
        const response = await fetch('/api/review/scan-abort', {method: 'POST'});
        const data = await response.json();

        if (data.success) {
            document.getElementById('progressStatus').textContent = 'Aborting...';
        }
    } catch (error) {
        alert('Failed to abort: ' + error.message);
    }
}

function resetUI() {
    const scanButtons = document.querySelectorAll('.btn-group button');
    const abortBtn = document.getElementById('abortBtn');
    const progressContainer = document.getElementById('progressContainer');

    scanButtons.forEach(btn => btn.disabled = false);
    abortBtn.style.display = 'none';
    progressContainer.style.display = 'none';

    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}
