#!/usr/bin/env python3
"""
Direct Lambda deployment using boto3 (more reliable than AWS CLI for large files)
"""
import boto3
import sys

def deploy_lambda(zip_path, function_name, region='us-east-1'):
    """Deploy Lambda function using boto3"""
    lambda_client = boto3.client('lambda', region_name=region)

    print(f"📦 Reading ZIP file: {zip_path}")
    with open(zip_path, 'rb') as f:
        zip_data = f.read()

    print(f"📏 ZIP size: {len(zip_data) / 1024 / 1024:.2f} MB")
    print(f"☁️  Uploading to Lambda: {function_name}")

    try:
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_data
        )

        print(f"✅ Deployment successful!")
        print(f"   Function: {response['FunctionName']}")
        print(f"   Code Size: {response['CodeSize'] / 1024:.1f} KB")
        print(f"   Last Modified: {response['LastModified']}")
        print(f"   Runtime: {response['Runtime']}")
        return True

    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        return False

if __name__ == '__main__':
    success = deploy_lambda(
        zip_path='enricher-with-deps.zip',
        function_name='reitsheet-enricher'
    )
    sys.exit(0 if success else 1)
