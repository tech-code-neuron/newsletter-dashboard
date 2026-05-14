"""
DynamoDB Utility Functions

Reusable utilities for common DynamoDB operations:
- DynamoDBUpdateBuilder: Build UPDATE expressions with SET/REMOVE
- paginated_scan: Generic paginated table scan with filtering
"""
from typing import Any, Callable, Dict, List, Optional, Tuple


class DynamoDBUpdateBuilder:
    """
    Builds DynamoDB UpdateExpression with SET and REMOVE clauses.

    Handles:
    - Skipping primary key fields
    - Using REMOVE for None values (deletes attribute)
    - Using SET for non-None values

    Usage:
        builder = DynamoDBUpdateBuilder(primary_key='ticker')
        kwargs = builder.build({'name': 'New Name', 'old_field': None})
        table.update_item(Key={'ticker': 'ABC'}, **kwargs)
    """

    def __init__(self, primary_key: str = None, primary_keys: List[str] = None):
        """
        Args:
            primary_key: Single primary key field name to skip
            primary_keys: Multiple key field names to skip (for composite keys)
        """
        self.skip_keys = set()
        if primary_key:
            self.skip_keys.add(primary_key)
        if primary_keys:
            self.skip_keys.update(primary_keys)

    def build(self, data: Dict[str, Any], remove_none: bool = True) -> Optional[Dict[str, Any]]:
        """
        Build update kwargs for table.update_item().

        Args:
            data: Field names to values
            remove_none: If True, None values become REMOVE clauses;
                        if False, None values are skipped entirely

        Returns:
            Dict with UpdateExpression, ExpressionAttributeNames,
            and optionally ExpressionAttributeValues.
            Returns None if no updates to apply.
        """
        set_parts = []
        remove_parts = []
        expr_values = {}
        expr_names = {}

        for i, (key, value) in enumerate(data.items()):
            if key in self.skip_keys:
                continue

            name_placeholder = f'#attr{i}'

            if value is None:
                if remove_none:
                    expr_names[name_placeholder] = key
                    remove_parts.append(name_placeholder)
                # else: skip entirely - don't add name placeholder
            else:
                expr_names[name_placeholder] = key
                value_placeholder = f':val{i}'
                set_parts.append(f'{name_placeholder} = {value_placeholder}')
                expr_values[value_placeholder] = value

        # Build combined expression
        if not set_parts and not remove_parts:
            return None

        update_expr = ''
        if set_parts:
            update_expr = 'SET ' + ', '.join(set_parts)
        if remove_parts:
            if update_expr:
                update_expr += ' '
            update_expr += 'REMOVE ' + ', '.join(remove_parts)

        result = {
            'UpdateExpression': update_expr,
            'ExpressionAttributeNames': expr_names
        }
        if expr_values:
            result['ExpressionAttributeValues'] = expr_values

        return result


def paginated_scan(
    table,
    filter_expression=None,
    limit: int = 200,
    sort_key: Callable[[Dict], Any] = None,
    sort_reverse: bool = True
) -> List[Dict[str, Any]]:
    """
    Paginated DynamoDB scan with optional filtering and sorting.

    DynamoDB's Limit parameter limits items EVALUATED, not items RETURNED.
    This function paginates through all matching items up to the limit.

    Args:
        table: boto3 DynamoDB Table resource
        filter_expression: boto3 FilterExpression (from Attr conditions)
        limit: Maximum items to return
        sort_key: Lambda for sorting (e.g., lambda x: x.get('date', ''))
        sort_reverse: Sort descending if True

    Returns:
        List of item dictionaries

    Usage:
        from boto3.dynamodb.conditions import Attr

        items = paginated_scan(
            table,
            filter_expression=Attr('status').eq('active'),
            limit=100,
            sort_key=lambda x: x.get('created_at', ''),
            sort_reverse=True
        )
    """
    items = []
    last_key = None

    while True:
        scan_kwargs = {}
        if filter_expression is not None:
            scan_kwargs['FilterExpression'] = filter_expression
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = last_key

        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

        # Check if we have enough items
        if len(items) >= limit:
            items = items[:limit]
            break

        # Check for more pages
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break

    # Sort if requested
    if sort_key:
        items.sort(key=sort_key, reverse=sort_reverse)

    return items
