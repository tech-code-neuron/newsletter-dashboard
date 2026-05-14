#!/usr/bin/env python3
"""
CloudTrail Query Tool
=====================
Query recent AWS CloudTrail events for infrastructure debugging.

Usage:
    python3 scripts/query_cloudtrail.py                           # Last 24h, all events
    python3 scripts/query_cloudtrail.py --resource reitsheet-homepage
    python3 scripts/query_cloudtrail.py --event-name DeleteBucketWebsite
    python3 scripts/query_cloudtrail.py --hours 48 --resource reitsheet
    python3 scripts/query_cloudtrail.py --event-name PutBucketWebsite --hours 72

Examples:
    # Debug S3 bucket issues
    python3 scripts/query_cloudtrail.py --resource reitsheet-homepage --hours 48

    # Find all bucket website changes
    python3 scripts/query_cloudtrail.py --event-name PutBucketWebsite

    # Lambda function updates
    python3 scripts/query_cloudtrail.py --event-name UpdateFunctionCode --hours 24
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

import boto3


# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text):
    """Print colored header"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")


def format_event(event):
    """Format a CloudTrail event for display"""
    event_time = event.get('EventTime', 'Unknown')
    event_name = event.get('EventName', 'Unknown')
    event_source = event.get('EventSource', 'Unknown')
    username = event.get('Username', 'Unknown')

    # Parse CloudTrailEvent JSON for details
    details = {}
    if 'CloudTrailEvent' in event:
        try:
            details = json.loads(event['CloudTrailEvent'])
        except json.JSONDecodeError:
            pass

    # Extract useful info
    error_code = details.get('errorCode', '')
    error_message = details.get('errorMessage', '')
    resources = event.get('Resources', [])

    return {
        'time': event_time,
        'event': event_name,
        'source': event_source.replace('.amazonaws.com', ''),
        'user': username,
        'resources': [r.get('ResourceName', 'N/A') for r in resources],
        'error': error_code,
        'error_message': error_message
    }


def query_cloudtrail(hours=24, resource_name=None, event_name=None, max_results=50):
    """Query CloudTrail for recent events"""
    client = boto3.client('cloudtrail', region_name='us-east-1')

    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    end_time = datetime.now(timezone.utc)

    # Build lookup attributes
    lookup_attrs = []
    if resource_name:
        lookup_attrs.append({
            'AttributeKey': 'ResourceName',
            'AttributeValue': resource_name
        })
    if event_name:
        lookup_attrs.append({
            'AttributeKey': 'EventName',
            'AttributeValue': event_name
        })

    kwargs = {
        'StartTime': start_time,
        'EndTime': end_time,
        'MaxResults': max_results
    }
    if lookup_attrs:
        kwargs['LookupAttributes'] = lookup_attrs

    try:
        response = client.lookup_events(**kwargs)
        return response.get('Events', [])
    except Exception as e:
        print(f"{RED}Error querying CloudTrail: {e}{RESET}")
        return []


def display_events(events, resource_filter=None):
    """Display events in a readable table format"""
    if not events:
        print(f"{YELLOW}No events found matching criteria{RESET}")
        return

    # Filter by resource if partial match requested
    if resource_filter:
        filtered = []
        for event in events:
            resources = event.get('Resources', [])
            resource_names = [r.get('ResourceName', '') for r in resources]
            if any(resource_filter.lower() in name.lower() for name in resource_names):
                filtered.append(event)
            # Also check CloudTrailEvent for resource references
            elif 'CloudTrailEvent' in event:
                if resource_filter.lower() in event['CloudTrailEvent'].lower():
                    filtered.append(event)
        events = filtered

    if not events:
        print(f"{YELLOW}No events found matching resource filter: {resource_filter}{RESET}")
        return

    print(f"\n{CYAN}Found {len(events)} events:{RESET}\n")

    # Header
    print(f"{BOLD}{'Time (UTC)':<22} {'Event':<30} {'Source':<12} {'User':<20} {'Resources'}{RESET}")
    print("-" * 120)

    for event in sorted(events, key=lambda e: e.get('EventTime', datetime.min), reverse=True):
        formatted = format_event(event)

        # Color based on event type
        event_color = RESET
        if formatted['error']:
            event_color = RED
        elif 'Delete' in formatted['event']:
            event_color = YELLOW
        elif 'Create' in formatted['event'] or 'Put' in formatted['event']:
            event_color = GREEN

        time_str = formatted['time'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(formatted['time'], 'strftime') else str(formatted['time'])[:19]
        resources_str = ', '.join(formatted['resources'][:2]) or 'N/A'
        if len(formatted['resources']) > 2:
            resources_str += f' (+{len(formatted["resources"]) - 2})'

        print(f"{time_str:<22} {event_color}{formatted['event']:<30}{RESET} {formatted['source']:<12} {formatted['user']:<20} {resources_str}")

        if formatted['error']:
            print(f"  {RED}ERROR: {formatted['error']} - {formatted['error_message'][:80]}{RESET}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Query AWS CloudTrail for infrastructure events',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --resource reitsheet-homepage --hours 48
  %(prog)s --event-name PutBucketWebsite
  %(prog)s --event-name UpdateFunctionCode --hours 24
        """
    )
    parser.add_argument('--hours', type=int, default=24,
                        help='Hours of history to query (default: 24)')
    parser.add_argument('--resource', type=str,
                        help='Filter by resource name (partial match)')
    parser.add_argument('--event-name', type=str,
                        help='Filter by event name (exact match)')
    parser.add_argument('--max-results', type=int, default=50,
                        help='Maximum results to return (default: 50)')

    args = parser.parse_args()

    print_header(f"CloudTrail Query - Last {args.hours} hours")

    if args.resource:
        print(f"Resource filter: {CYAN}{args.resource}{RESET}")
    if args.event_name:
        print(f"Event filter: {CYAN}{args.event_name}{RESET}")

    # For CloudTrail API, we can only use exact match on EventName
    # We'll do partial match on resource client-side
    events = query_cloudtrail(
        hours=args.hours,
        resource_name=None,  # Client-side filter for partial match
        event_name=args.event_name,
        max_results=args.max_results
    )

    display_events(events, resource_filter=args.resource)


if __name__ == '__main__':
    main()
