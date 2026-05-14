// CloudFront Function: Archive URL handler
// Handles /news/archive/{date} URLs for newsletter archives

function handler(event) {
    var request = event.request;
    var uri = request.uri;

    // Only process archive URLs
    if (!uri.startsWith('/news/archive/')) {
        return request;
    }

    // Match date pattern (YYYY-MM-DD)
    var match = uri.match(/^\/news\/archive\/(\d{4}-\d{2}-\d{2})/);
    if (!match) {
        return request;
    }

    // Pass through to origin (Flask app handles archive rendering)
    return request;
}
