"""
Error handling utilities for Flask routes.
Centralizes error handling patterns (Single Responsibility, DRY).
"""
from flask import flash, redirect, url_for


# ------------------------------------------------------------------
# "NOT FOUND" ERROR HANDLERS - DRY Pattern
# ------------------------------------------------------------------

def handle_not_found(db, entity_name, redirect_route, **url_params):
    """
    Handle "entity not found" errors consistently.

    Centralizes the pattern:
    1. Flash error message
    2. Close database connection
    3. Redirect to target route

    Args:
        db: Database session to close
        entity_name: Name of entity (e.g., 'Company', 'Press release', 'Newsletter')
        redirect_route: Route name to redirect to
        **url_params: Additional parameters for url_for()

    Returns:
        Flask redirect response
    """
    flash(f'{entity_name} not found', 'error')
    db.close()
    return redirect(url_for(redirect_route, **url_params))


def handle_validation_error(db, error_message, redirect_route, **url_params):
    """
    Handle validation errors consistently.

    Args:
        db: Database session to close
        error_message: Error message to flash
        redirect_route: Route name to redirect to
        **url_params: Additional parameters for url_for()

    Returns:
        Flask redirect response
    """
    flash(error_message, 'error')
    db.close()
    return redirect(url_for(redirect_route, **url_params))


# ------------------------------------------------------------------
# ENTITY RETRIEVAL HELPERS - DRY Pattern
# ------------------------------------------------------------------

def get_entity_or_404(db, model_class, entity_id, entity_name, redirect_route, **url_params):
    """
    Get entity by ID or handle not found error.

    Centralizes the pattern:
    1. Query entity by ID
    2. If not found, flash error and redirect
    3. Return entity if found

    Args:
        db: Database session
        model_class: SQLAlchemy model class
        entity_id: Entity ID to retrieve
        entity_name: Display name for error message
        redirect_route: Route to redirect to on error
        **url_params: Additional URL parameters

    Returns:
        Entity object if found, or Flask redirect response if not found
    """
    entity = db.query(model_class).get(entity_id)

    if not entity:
        return handle_not_found(db, entity_name, redirect_route, **url_params)

    return entity


# ------------------------------------------------------------------
# DATABASE RESOURCE MANAGEMENT HELPERS
# ------------------------------------------------------------------

def safe_db_close(db):
    """
    Safely close database session (handles None case).

    Args:
        db: Database session to close (can be None)
    """
    if db is not None:
        try:
            db.close()
        except Exception:
            pass  # Ignore close errors
