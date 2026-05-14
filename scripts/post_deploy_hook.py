#!/usr/bin/env python3
"""
Post-Deployment Hook - Automated Documentation Updates
=======================================================
Automatically updates deployment documentation after successful Lambda deployment.

Updates:
1. infrastructure/DEPLOYED_STATE.md (deployment table)
2. Git tags (deployed-<lambda>-YYYY-MM-DD)
3. Deployment timestamp tracking

Usage:
    python3 scripts/post_deploy_hook.py <lambda_name> <zip_name> <size_mb>

Example:
    python3 scripts/post_deploy_hook.py parser parser-latest.zip 1.5

Integration:
    Called automatically by deploy_lambda.py after successful deployment
"""

import sys
import re
from datetime import datetime
from pathlib import Path
import subprocess


def update_deployed_state(lambda_name, zip_name, size_mb):
    """
    Update infrastructure/DEPLOYED_STATE.md with new deployment info

    Args:
        lambda_name: Name of Lambda (parser, enricher, etc.)
        zip_name: Name of ZIP file deployed
        size_mb: Size of ZIP in MB
    """
    deployed_state_path = Path("infrastructure/DEPLOYED_STATE.md")

    if not deployed_state_path.exists():
        print(f"⚠️  WARNING: {deployed_state_path} not found (skipping)")
        return False

    content = deployed_state_path.read_text()

    # Current timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update pattern: Find table row for this Lambda
    # Example row:
    # | Parser          | parser-latest.zip       | 1.5 MB | 2026-03-11 | ✅ CURRENT |

    lambda_display_name = lambda_name.replace('-', ' ').title()

    # Try to find existing row
    pattern = rf'\|\s*{lambda_display_name}\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|'

    if re.search(pattern, content):
        # Update existing row
        def replace_row(match):
            return f"| {lambda_display_name:<15} | {zip_name:<23} | {size_mb:<6} MB | {now[:10]:<10} | ✅ CURRENT |"

        updated_content = re.sub(pattern, replace_row, content)
        deployed_state_path.write_text(updated_content)
        print(f"✅ Updated {deployed_state_path} ({lambda_display_name} row)")
    else:
        print(f"⚠️  WARNING: Could not find {lambda_display_name} row in deployment table")
        print(f"   Please manually update {deployed_state_path}")

    return True


def create_git_tag(lambda_name):
    """
    Create git tag for this deployment

    Args:
        lambda_name: Name of Lambda

    Returns:
        Tag name created (or None if failed)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    tag_name = f"deployed-{lambda_name}-{today}"

    try:
        # Check if tag already exists
        result = subprocess.run(
            ['git', 'tag', '-l', tag_name],
            capture_output=True,
            text=True,
            check=False
        )

        if result.stdout.strip():
            print(f"⚠️  Tag {tag_name} already exists (skipping)")
            return tag_name

        # Create lightweight tag
        subprocess.run(
            ['git', 'tag', tag_name],
            check=True,
            capture_output=True
        )

        print(f"✅ Created git tag: {tag_name}")
        return tag_name

    except subprocess.CalledProcessError as e:
        print(f"⚠️  Failed to create git tag: {e}")
        return None


def update_deployment_history(lambda_name, zip_name, size_mb):
    """
    Optional: Add entry to deployment history log

    Args:
        lambda_name: Name of Lambda
        zip_name: Name of ZIP deployed
        size_mb: Size in MB
    """
    history_path = Path("infrastructure/DEPLOYMENT_HISTORY.md")

    if not history_path.exists():
        # Create if doesn't exist
        history_path.write_text("# Deployment History\n\n")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"- **{now}**: Deployed `{lambda_name}` ({zip_name}, {size_mb} MB)\n"

    # Prepend to file (most recent first)
    content = history_path.read_text()
    lines = content.split('\n')

    # Find where to insert (after header)
    insert_index = 2  # After "# Deployment History\n\n"

    lines.insert(insert_index, entry)
    history_path.write_text('\n'.join(lines))

    print(f"✅ Added entry to {history_path}")


def main():
    """Execute post-deployment updates"""

    if len(sys.argv) != 4:
        print("Usage: post_deploy_hook.py <lambda_name> <zip_name> <size_mb>")
        print("Example: post_deploy_hook.py parser parser-latest.zip 1.5")
        sys.exit(1)

    lambda_name = sys.argv[1]
    zip_name = sys.argv[2]
    size_mb = sys.argv[3]

    print("=" * 60)
    print(f"Post-Deployment Hook: {lambda_name}")
    print("=" * 60)

    # 1. Update DEPLOYED_STATE.md
    update_deployed_state(lambda_name, zip_name, size_mb)

    # 2. Create git tag
    tag = create_git_tag(lambda_name)

    # 3. Update deployment history (optional)
    update_deployment_history(lambda_name, zip_name, size_mb)

    print("\n" + "=" * 60)
    print("✅ Post-deployment updates complete")
    print("=" * 60)
    print("\nNext steps:")
    print(f"  1. Review changes: git diff infrastructure/DEPLOYED_STATE.md")
    print(f"  2. Commit documentation: git commit -m 'docs: deployed {lambda_name}'")

    if tag:
        print(f"  3. Push tag (optional): git push origin {tag}")

    print("\nRemember to:")
    print("  - Update infrastructure/terraform/lambda-*.tf if ZIP name changed")
    print("  - Run smoke tests to verify deployment")
    print("  - Update session handoff document")

    return 0


if __name__ == '__main__':
    sys.exit(main())
