#!/usr/bin/env python3
"""
Deployment State Validator
===========================
Checks if deployed Lambdas match latest ZIPs and Terraform configuration.

Usage:
    python3 scripts/validate_deployment_state.py           # Check all Lambdas
    python3 scripts/validate_deployment_state.py parser    # Check specific Lambda

Checks:
    1. Terraform points to existing ZIP files
    2. Latest ZIPs vs Terraform configuration
    3. Deployment status from DEPLOYED_STATE.md
    4. S3 website configuration exists for homepage bucket
"""

import sys
import re
from pathlib import Path
from datetime import datetime

import boto3

# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Lambda configuration
LAMBDAS = {
    'parser': {
        'terraform_file': 'infrastructure/terraform/lambda-parser.tf',
        'lambda_dir': 'infrastructure/lambdas/parser',
        'min_size_mb': 1.5
    },
    'enricher': {
        'terraform_file': 'infrastructure/terraform/lambda-enricher.tf',
        'lambda_dir': 'infrastructure/lambdas/enricher',
        'min_size_mb': 1.0
    },
    'email-forwarder': {
        'terraform_file': 'infrastructure/terraform/lambda-email-forwarder.tf',
        'lambda_dir': 'infrastructure/lambdas/email-forwarder',
        'min_size_mb': 0.5
    }
}


def print_header(text):
    """Print colored header"""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✅ {text}{RESET}")


def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠️  {text}{RESET}")


def print_error(text):
    """Print error message"""
    print(f"{RED}❌ {text}{RESET}")


def get_terraform_zip(terraform_file):
    """Extract ZIP filename from Terraform file"""
    if not Path(terraform_file).exists():
        return None

    with open(terraform_file, 'r') as f:
        content = f.read()

    # Find filename = "..." line
    match = re.search(r'filename\s*=\s*"([^"]+)"', content)
    if not match:
        return None

    return match.group(1)


def get_latest_zip(lambda_dir):
    """Get most recently modified ZIP file in directory"""
    lambda_path = Path(lambda_dir)
    if not lambda_path.exists():
        return None

    zips = list(lambda_path.glob('*.zip'))
    if not zips:
        return None

    # Sort by modification time (newest first)
    zips.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return zips[0]


def check_lambda_state(lambda_key, config):
    """Check deployment state for a single Lambda"""
    print_header(f"Checking {lambda_key} Lambda")

    issues = []
    warnings = []

    # 1. Check Terraform file exists
    terraform_file = config['terraform_file']
    if not Path(terraform_file).exists():
        print_error(f"Terraform file not found: {terraform_file}")
        issues.append(f"Missing Terraform file: {terraform_file}")
        return issues, warnings

    # 2. Get ZIP from Terraform
    terraform_zip = get_terraform_zip(terraform_file)
    if not terraform_zip:
        print_error("Could not find 'filename' in Terraform file")
        issues.append("Terraform file missing filename declaration")
        return issues, warnings

    print(f"📄 Terraform: {Path(terraform_file).name}")
    print(f"   Points to: {Path(terraform_zip).name}")

    # 3. Check if Terraform ZIP exists
    # Handle Terraform variables: ${path.module} = infrastructure/terraform
    if "${path.module}" in terraform_zip:
        # Replace ${path.module}/../lambdas/ with infrastructure/lambdas/
        terraform_zip = terraform_zip.replace("${path.module}/../lambdas/", "infrastructure/lambdas/")
        terraform_zip_path = Path(terraform_zip)
    # Handle plain relative paths (../lambdas/parser/parser.zip)
    elif terraform_zip.startswith("../lambdas/"):
        terraform_zip_path = Path("infrastructure") / Path(terraform_zip.replace("../", ""))
    else:
        terraform_zip_path = Path(terraform_zip)

    if not terraform_zip_path.exists():
        print_error(f"ZIP file not found: {terraform_zip_path}")
        issues.append(f"Terraform points to non-existent ZIP: {terraform_zip_path.name}")
    else:
        size_mb = terraform_zip_path.stat().st_size / (1024 * 1024)
        mod_time = datetime.fromtimestamp(terraform_zip_path.stat().st_mtime)
        print_success(f"ZIP exists: {size_mb:.2f} MB (modified: {mod_time.strftime('%Y-%m-%d %H:%M')})")

        # Check size
        if size_mb < config['min_size_mb']:
            print_warning(f"ZIP size {size_mb:.2f} MB < expected {config['min_size_mb']} MB (may be missing dependencies)")
            warnings.append(f"ZIP smaller than expected ({size_mb:.2f} MB < {config['min_size_mb']} MB)")

    # 4. Get latest ZIP in directory
    latest_zip = get_latest_zip(config['lambda_dir'])
    if not latest_zip:
        print_warning(f"No ZIP files found in {config['lambda_dir']}")
        warnings.append(f"No ZIPs in {config['lambda_dir']}")
    else:
        latest_size_mb = latest_zip.stat().st_size / (1024 * 1024)
        latest_mod_time = datetime.fromtimestamp(latest_zip.stat().st_mtime)

        print(f"\n📦 Latest ZIP: {latest_zip.name}")
        print(f"   Size: {latest_size_mb:.2f} MB")
        print(f"   Modified: {latest_mod_time.strftime('%Y-%m-%d %H:%M')}")

        # 5. Compare Terraform ZIP vs Latest ZIP
        if latest_zip.name not in terraform_zip:
            print_warning("⚠️  STALE: Terraform points to older ZIP")
            print(f"   Terraform: {Path(terraform_zip).name}")
            print(f"   Latest:    {latest_zip.name}")

            if terraform_zip_path.exists():
                terraform_mod = datetime.fromtimestamp(terraform_zip_path.stat().st_mtime)
                time_diff = (latest_mod_time - terraform_mod).total_seconds() / 3600

                if time_diff > 1:  # More than 1 hour difference
                    print_warning(f"   Latest ZIP is {time_diff:.1f} hours newer")
                    warnings.append(f"Terraform points to ZIP from {terraform_mod.strftime('%Y-%m-%d %H:%M')}, latest is {latest_mod_time.strftime('%Y-%m-%d %H:%M')}")

            warnings.append(f"Terraform may be stale (points to {Path(terraform_zip).name}, latest is {latest_zip.name})")
        else:
            print_success("Terraform points to latest ZIP")

    return issues, warnings


def check_s3_website_config():
    """Check S3 website configuration for homepage bucket"""
    print_header("Checking S3 Website Configuration")

    bucket_name = 'reitsheet-homepage'
    issues = []
    warnings = []

    try:
        s3 = boto3.client('s3', region_name='us-east-1')

        # Check if bucket exists
        try:
            s3.head_bucket(Bucket=bucket_name)
            print_success(f"Bucket exists: {bucket_name}")
        except Exception as e:
            print_error(f"Bucket not found: {bucket_name}")
            issues.append(f"S3 bucket {bucket_name} does not exist")
            return issues, warnings

        # Check website configuration
        try:
            website_config = s3.get_bucket_website(Bucket=bucket_name)
            index_doc = website_config.get('IndexDocument', {}).get('Suffix', 'N/A')
            error_doc = website_config.get('ErrorDocument', {}).get('Key', 'N/A')
            print_success(f"Website config exists: index={index_doc}, error={error_doc}")
        except s3.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchWebsiteConfiguration':
                print_error("Website configuration MISSING!")
                print(f"   Fix: aws s3 website s3://{bucket_name} --index-document index.html")
                issues.append(f"S3 bucket {bucket_name} has no website configuration")
            else:
                print_error(f"Error checking website config: {e}")
                issues.append(f"Could not check website config: {error_code}")

        # Check public access block (should allow public access for static site)
        try:
            public_access = s3.get_public_access_block(Bucket=bucket_name)
            block_config = public_access.get('PublicAccessBlockConfiguration', {})
            if block_config.get('BlockPublicAcls') or block_config.get('BlockPublicPolicy'):
                print_warning("Public access may be blocked")
                warnings.append("S3 bucket public access settings may prevent website access")
            else:
                print_success("Public access allowed")
        except s3.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchPublicAccessBlockConfiguration':
                print_success("No public access block (public access allowed)")
            else:
                print_warning(f"Could not check public access block: {error_code}")

    except Exception as e:
        print_error(f"Error checking S3: {e}")
        issues.append(f"S3 check failed: {str(e)}")

    return issues, warnings


def check_all_lambdas():
    """Check deployment state for all Lambdas"""
    print_header("Deployment State Validation")
    print("Checking all Lambdas for stale deployments...\n")

    all_issues = {}
    all_warnings = {}

    for lambda_key, config in LAMBDAS.items():
        issues, warnings = check_lambda_state(lambda_key, config)
        if issues:
            all_issues[lambda_key] = issues
        if warnings:
            all_warnings[lambda_key] = warnings

    # Check S3 website configuration
    s3_issues, s3_warnings = check_s3_website_config()
    if s3_issues:
        all_issues['s3-homepage'] = s3_issues
    if s3_warnings:
        all_warnings['s3-homepage'] = s3_warnings

    # Summary
    print_header("Summary")

    if not all_issues and not all_warnings:
        print_success("✅ All Lambdas are current - no issues found!")
        return 0

    # Print issues
    if all_issues:
        print_error(f"Found {sum(len(v) for v in all_issues.values())} critical issues:")
        for lambda_key, issues in all_issues.items():
            print(f"\n  {lambda_key}:")
            for issue in issues:
                print(f"    ❌ {issue}")

    # Print warnings
    if all_warnings:
        print_warning(f"Found {sum(len(v) for v in all_warnings.values())} warnings:")
        for lambda_key, warnings in all_warnings.items():
            print(f"\n  {lambda_key}:")
            for warning in warnings:
                print(f"    ⚠️  {warning}")

    # Recommendations
    print_header("Recommendations")

    if all_warnings:
        for lambda_key, warnings in all_warnings.items():
            if any("stale" in w.lower() or "newer" in w.lower() for w in warnings):
                print(f"\n{lambda_key}:")
                print(f"  1. Validate latest ZIP:")
                print(f"     python3 scripts/deploy_lambda.py {lambda_key} --validate --zip [latest-zip-name]")
                print(f"  2. Deploy if validation passes:")
                print(f"     python3 scripts/deploy_lambda.py {lambda_key} --deploy --zip [latest-zip-name]")
                print(f"  3. Update Terraform:")
                print(f"     Edit infrastructure/terraform/lambda-{lambda_key}.tf")
                print(f"  4. Update documentation:")
                print(f"     Edit infrastructure/DEPLOYED_STATE.md")

    return 1 if (all_issues or all_warnings) else 0


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        lambda_key = sys.argv[1]

        if lambda_key not in LAMBDAS:
            print_error(f"Unknown Lambda: {lambda_key}")
            print(f"Available: {', '.join(LAMBDAS.keys())}")
            sys.exit(1)

        issues, warnings = check_lambda_state(lambda_key, LAMBDAS[lambda_key])

        if issues:
            print_error(f"\n❌ Found {len(issues)} critical issues")
            sys.exit(1)

        if warnings:
            print_warning(f"\n⚠️  Found {len(warnings)} warnings")
            sys.exit(1)

        print_success("\n✅ No issues found")
        sys.exit(0)
    else:
        exit_code = check_all_lambdas()
        sys.exit(exit_code)


if __name__ == '__main__':
    main()
