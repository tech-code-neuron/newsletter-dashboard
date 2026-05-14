/**
 * Reusable Autocomplete Component
 *
 * Usage:
 * const autocomplete = new Autocomplete({
 *     inputId: 'search-input',
 *     dropdownId: 'ac-dropdown',
 *     dataSource: () => [...], // Function that returns array of items to search
 *     searchFields: ['ticker', 'name', 'title'], // Fields to search in
 *     onSelect: (item) => { ... }, // Callback when item is selected
 *     multiSelect: true, // Enable multi-select with badges
 *     placeholder: 'Search...',
 *     minChars: 1, // Minimum characters before showing suggestions
 *     maxResults: 10 // Maximum results to show
 * });
 */

class Autocomplete {
    constructor(options) {
        this.options = {
            minChars: 1,
            maxResults: 10,
            multiSelect: false,
            searchFields: ['ticker', 'name'],
            placeholder: 'Search...',
            showCount: false, // Show count next to items
            groupBy: null, // Group results by field (e.g., 'type')
            ...options
        };

        this.input = document.getElementById(this.options.inputId);
        this.dropdown = document.getElementById(this.options.dropdownId);
        this.clearBtn = this.options.clearBtnId ? document.getElementById(this.options.clearBtnId) : null;
        this.selectedItemsDiv = this.options.selectedItemsDivId ? document.getElementById(this.options.selectedItemsDivId) : null;

        this.focusIdx = -1;
        this.selectedItems = new Set(); // For multi-select
        this.data = [];
        this.currentMatches = []; // Store current matches for selection

        if (!this.input || !this.dropdown) {
            console.error('Autocomplete: Required elements not found', {
                inputId: this.options.inputId,
                dropdownId: this.options.dropdownId
            });
            return;
        }

        this.init();
    }

    init() {
        // Event listeners
        this.input.addEventListener('input', () => this.handleInput());
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.input.addEventListener('focus', () => this.handleInput());

        // Clear button
        if (this.clearBtn) {
            this.clearBtn.addEventListener('click', () => this.clearInput());
        }

        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.dropdown.contains(e.target)) {
                this.hideDropdown();
            }
        });

        // Load initial data
        this.refreshData();
    }

    refreshData() {
        if (typeof this.options.dataSource === 'function') {
            this.data = this.options.dataSource();
        } else {
            this.data = this.options.dataSource || [];
        }
    }

    handleInput() {
        const query = this.input.value.trim();

        if (this.clearBtn) {
            this.clearBtn.style.display = query.length > 0 ? 'inline' : 'none';
        }

        if (query.length < this.options.minChars) {
            this.hideDropdown();
            return;
        }

        this.buildSuggestions(query);
    }

    buildSuggestions(query) {
        const lq = query.toLowerCase();
        this.focusIdx = -1;
        this.refreshData(); // Refresh data before searching

        // Filter and rank matches
        const matches = this.data
            .map(item => {
                const matchInfo = this.getMatchInfo(item, lq);
                return matchInfo ? { item, ...matchInfo } : null;
            })
            .filter(Boolean)
            .sort((a, b) => {
                // Sort by: 1) match type (exact > starts > contains), 2) match position, 3) alphabetical
                if (a.matchType !== b.matchType) {
                    const order = { exact: 0, starts: 1, contains: 2 };
                    return order[a.matchType] - order[b.matchType];
                }
                if (a.matchPos !== b.matchPos) {
                    return a.matchPos - b.matchPos;
                }
                return a.sortKey.localeCompare(b.sortKey);
            })
            .slice(0, this.options.maxResults);

        if (matches.length === 0) {
            this.hideDropdown();
            return;
        }

        // Store matches for selection (prevents mismatch if input changes)
        this.currentMatches = matches;
        this.renderSuggestions(matches, query);
        this.showDropdown();
    }

    getMatchInfo(item, query) {
        for (const field of this.options.searchFields) {
            const value = this.getFieldValue(item, field);
            if (!value) continue;

            const lowerValue = value.toLowerCase();
            const matchPos = lowerValue.indexOf(query);

            if (matchPos !== -1) {
                let matchType = 'contains';
                if (lowerValue === query) matchType = 'exact';
                else if (matchPos === 0) matchType = 'starts';

                return {
                    matchField: field,
                    matchPos,
                    matchType,
                    sortKey: value
                };
            }
        }
        return null;
    }

    getFieldValue(item, field) {
        if (typeof item === 'string') return item;
        return item[field] || '';
    }

    renderSuggestions(matches, query) {
        let html = '';

        if (this.options.groupBy) {
            // Group matches
            const groups = {};
            matches.forEach(match => {
                const groupKey = match.item[this.options.groupBy] || 'Other';
                if (!groups[groupKey]) groups[groupKey] = [];
                groups[groupKey].push(match);
            });

            Object.entries(groups).forEach(([groupName, items]) => {
                html += `<div class="ac-section">${this.escapeHtml(groupName)}</div>`;
                items.forEach(match => {
                    html += this.renderSuggestionItem(match, query);
                });
            });
        } else {
            matches.forEach(match => {
                html += this.renderSuggestionItem(match, query);
            });
        }

        this.dropdown.innerHTML = html;

        // Add click handlers
        this.dropdown.querySelectorAll('.ac-item').forEach((item, idx) => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                this.selectItem(idx);
            });
        });
    }

    renderSuggestionItem(match, query) {
        const item = match.item;
        const displayText = this.formatDisplayText(item, query);
        const value = this.getItemValue(item);
        const badge = this.getItemBadge(item);
        const count = this.options.showCount && item.count ? `<span class="ac-count">${item.count}</span>` : '';

        return `
            <div class="ac-item" data-idx="${this.dropdown.querySelectorAll('.ac-item').length}">
                ${badge ? `<span class="ac-badge">${badge}</span>` : ''}
                <span class="ac-name">${displayText}</span>
                ${count}
            </div>
        `;
    }

    formatDisplayText(item, query) {
        if (typeof item === 'string') {
            return this.highlightMatch(item, query);
        }

        // Use custom formatter if provided
        if (this.options.formatDisplay) {
            return this.options.formatDisplay(item, query);
        }

        // Default: show name or title
        const text = item.name || item.title || item.ticker || String(item);
        return this.highlightMatch(text, query);
    }

    getItemBadge(item) {
        if (this.options.getBadge) {
            return this.options.getBadge(item);
        }
        return item.ticker || '';
    }

    getItemValue(item) {
        if (typeof item === 'string') return item;
        if (this.options.getValue) return this.options.getValue(item);
        return item.ticker || item.id || item.name || String(item);
    }

    highlightMatch(text, query) {
        if (!query) return this.escapeHtml(text);
        const escaped = this.escapeHtml(text);
        const regex = new RegExp(`(${this.escapeRegex(query)})`, 'gi');
        return escaped.replace(regex, '<mark>$1</mark>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    escapeRegex(text) {
        return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    handleKeydown(e) {
        const items = Array.from(this.dropdown.querySelectorAll('.ac-item'));

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.focusIdx = Math.min(this.focusIdx + 1, items.length - 1);
            this.updateFocus(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.focusIdx = Math.max(this.focusIdx - 1, -1);
            this.updateFocus(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (this.focusIdx >= 0 && items[this.focusIdx]) {
                this.selectItem(this.focusIdx);
            } else if (items.length > 0) {
                this.selectItem(0); // Select first item
            }
        } else if (e.key === 'Escape') {
            this.hideDropdown();
        }
    }

    updateFocus(items) {
        items.forEach((el, i) => {
            el.classList.toggle('focused', i === this.focusIdx);
        });
    }

    selectItem(idx) {
        // Use stored matches to avoid mismatch if input changed
        const match = this.currentMatches[idx];
        if (!match) return;

        const value = this.getItemValue(match.item);

        if (this.options.multiSelect) {
            this.selectedItems.add(value);
            this.renderSelectedItems();
            this.input.value = '';
            this.hideDropdown();
            this.input.focus();
        } else {
            this.input.value = value;
            this.hideDropdown();
        }

        if (this.options.onSelect) {
            this.options.onSelect(match.item, value);
        }
    }

    renderSelectedItems() {
        if (!this.selectedItemsDiv) return;

        this.selectedItemsDiv.innerHTML = '';

        this.selectedItems.forEach(value => {
            const item = this.data.find(d => this.getItemValue(d) === value);
            if (!item) return;

            const badge = document.createElement('div');
            badge.className = 'company-badge-filter';
            badge.innerHTML = `
                <span class="badge-ticker">${this.escapeHtml(this.getItemBadge(item))}</span>
                <span class="badge-name">${this.escapeHtml(item.name || item.title || value)}</span>
                <span class="badge-remove" data-value="${this.escapeHtml(value)}">&times;</span>
            `;

            this.selectedItemsDiv.appendChild(badge);
        });

        // Add remove handlers
        this.selectedItemsDiv.querySelectorAll('.badge-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                const value = btn.dataset.value;
                this.removeItem(value);
            });
        });

        // Trigger onChange if provided
        if (this.options.onChange) {
            this.options.onChange(Array.from(this.selectedItems));
        }
    }

    removeItem(value) {
        this.selectedItems.delete(value);
        this.renderSelectedItems();
    }

    clearInput() {
        this.input.value = '';
        this.hideDropdown();
        if (this.clearBtn) {
            this.clearBtn.style.display = 'none';
        }
        this.input.focus();
    }

    showDropdown() {
        this.dropdown.classList.add('open');
    }

    hideDropdown() {
        this.dropdown.classList.remove('open');
        this.focusIdx = -1;
    }

    getSelectedItems() {
        return Array.from(this.selectedItems);
    }

    clearSelection() {
        this.selectedItems.clear();
        this.renderSelectedItems();
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Autocomplete;
}
