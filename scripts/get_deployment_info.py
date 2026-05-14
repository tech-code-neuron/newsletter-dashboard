#!/usr/bin/env python3
"""
Get Production Deployment Information

This script reads deployment-config.json and provides deployment commands.
Claude Code should use this BEFORE attempting any deployment to know:
- Where Flask is running
- How to deploy updates
- How to restart services

Usage:
    python3 scripts/get_deployment_info.py              # Show all info
    python3 scripts/get_deployment_info.py --restart    # Get restart command
    python3 scripts/get_deployment_info.py --deploy     # Get deploy steps
    python3 scripts/get_deployment_info.py --ssh        # Get SSH command
"""

import json
import sys
from pathlib import Path

def load_config():
    """Load deployment configuration from JSON file"""
    config_path = Path("infrastructure/deployment-config.json")

    if not config_path.exists():
        print("❌ ERROR: deployment-config.json not found!")
        print(f"   Expected: {config_path.absolute()}")
        print("\n   This file is required to know where Flask is deployed.")
        print("   Run from project root directory.")
        sys.exit(1)

    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: deployment-config.json is invalid JSON")
        print(f"   {e}")
        sys.exit(1)

def show_all_info(config):
    """Show all deployment information"""
    print("=" * 70)
    print("PRODUCTION DEPLOYMENT INFORMATION")
    print("=" * 70)

    # EC2 Instance
    ec2 = config['deployment']['ec2_instance']
    print(f"\n📍 EC2 Instance:")
    print(f"   IP:      {ec2['ip']}")
    print(f"   Region:  {ec2['region']}")
    print(f"   SSH Key: {ec2['ssh_key']}")
    print(f"   User:    {ec2['ssh_user']}")

    # Application
    app = config['deployment']['application']
    print(f"\n📂 Application:")
    print(f"   Path:       {app['path']}")
    print(f"   Entry:      {app['entry_point']}")
    print(f"   Git Repo:   {app['is_git_repo']}")
    print(f"   Note:       {app['deployment_note']}")

    # Process Manager
    pm = config['deployment']['process_manager']
    print(f"\n⚙️  Process Manager:")
    print(f"   Type:    {pm['type']}")
    print(f"   Command: {pm['command']}")
    print(f"   Args:    {pm['args']}")

    # Domain
    domain = config['deployment']['domain']
    print(f"\n🌐 Domain:")
    print(f"   URL: {domain['url']}")

    # Quick Commands
    print(f"\n🚀 Quick Commands:")
    print(f"   SSH:     ssh -i {ec2['ssh_key']} {ec2['ssh_user']}@{ec2['ip']}")
    print(f"   Restart: {pm['restart_command']}")
    print(f"   Health:  curl -I {domain['url']}")

def show_restart_command(config):
    """Show command to restart Gunicorn"""
    ec2 = config['deployment']['ec2_instance']
    pm = config['deployment']['process_manager']

    ssh_cmd = f"ssh -i {ec2['ssh_key']} {ec2['ssh_user']}@{ec2['ip']}"
    restart_cmd = pm['restart_command']

    print(f"{ssh_cmd} '{restart_cmd}'")

def show_deploy_steps(config):
    """Show deployment steps"""
    print("=" * 70)
    print("DEPLOYMENT STEPS (Quick Fix)")
    print("=" * 70)

    for step_info in config['deploy_steps']['quick_fix']:
        step = step_info['step']
        action = step_info['action']
        cmd = step_info['command']

        print(f"\nStep {step}: {action}")
        print(f"  {cmd}")

def show_ssh_command(config):
    """Show SSH command"""
    ec2 = config['deployment']['ec2_instance']
    print(f"ssh -i {ec2['ssh_key']} {ec2['ssh_user']}@{ec2['ip']}")

def main():
    config = load_config()

    if len(sys.argv) == 1:
        show_all_info(config)
    elif sys.argv[1] == '--restart':
        show_restart_command(config)
    elif sys.argv[1] == '--deploy':
        show_deploy_steps(config)
    elif sys.argv[1] == '--ssh':
        show_ssh_command(config)
    elif sys.argv[1] == '--help':
        print(__doc__)
    else:
        print(f"Unknown option: {sys.argv[1]}")
        print("Use --help for usage information")
        sys.exit(1)

if __name__ == '__main__':
    main()
