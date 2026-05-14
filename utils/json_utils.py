"""
JSON parsing utilities for API responses.
Centralizes JSON extraction and validation logic (Single Responsibility).
"""
import json
import re


# ------------------------------------------------------------------
# CONSTANTS - JSON Parsing Configuration
# ------------------------------------------------------------------

# Markdown code fence patterns
MARKDOWN_JSON_PATTERN = r'```json\s*(.*?)\s*```'
MARKDOWN_CODE_PATTERN = r'```\s*(.*?)\s*```'


# ------------------------------------------------------------------
# JSON EXTRACTION - Single Responsibility
# ------------------------------------------------------------------

def extract_json_from_markdown(text):
    """
    Extract JSON from markdown-formatted response.

    Handles multiple formats:
    1. ```json ... ```  (explicit JSON block)
    2. ``` ... ```      (generic code block)
    3. Plain JSON       (no code fences)

    Args:
        text: Response text that may contain JSON in markdown

    Returns:
        str: Extracted JSON string (still needs json.loads())

    Raises:
        ValueError: If no JSON found in text
    """
    if not text:
        raise ValueError("Empty text provided")

    text = text.strip()

    # Strategy 1: Try explicit ```json blocks
    if '```json' in text:
        match = re.search(MARKDOWN_JSON_PATTERN, text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Strategy 2: Try generic code blocks
    if '```' in text:
        match = re.search(MARKDOWN_CODE_PATTERN, text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Strategy 3: Assume plain JSON (no markdown)
    return text


def parse_json_from_markdown(text):
    """
    Extract and parse JSON from markdown-formatted response.

    Convenience function that combines extraction and parsing.

    Args:
        text: Response text that may contain JSON in markdown

    Returns:
        dict: Parsed JSON object

    Raises:
        ValueError: If JSON extraction fails
        json.JSONDecodeError: If JSON parsing fails
    """
    json_str = extract_json_from_markdown(text)
    return json.loads(json_str)


def safe_parse_json_from_markdown(text, default=None):
    """
    Safely extract and parse JSON from markdown-formatted response.
    Returns default value on any error.

    Args:
        text: Response text that may contain JSON in markdown
        default: Default value to return on error (default: None)

    Returns:
        dict: Parsed JSON object, or default value on error
    """
    try:
        return parse_json_from_markdown(text)
    except (ValueError, json.JSONDecodeError):
        return default
