#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload build artifacts to Cloudflare R2
Supports tagging with platform, architecture, version, and signed/notarized status
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import boto3
    from botocore.client import Config
except ImportError:
    print("Error: boto3 not installed. Run: pip install boto3")
    sys.exit(1)


def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 hash of file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def upload_to_r2(
    file_path: str,
    version: str,
    platform: str,
    arch: str,
    signed: bool = False,
    notarized: bool = False,
    commit_sha: str = None
) -> bool:
    """
    Upload file to Cloudflare R2 with metadata tags

    Args:
        file_path: Path to file to upload
        version: Version string (e.g., "1.0.0")
        platform: Platform (macos, windows)
        arch: Architecture (arm64, x64)
        signed: Whether the binary is code-signed
        notarized: Whether macOS app is notarized (macOS only)
        commit_sha: Git commit SHA

    Returns:
        bool: True if upload successful
    """
    # Get R2 credentials from environment
    access_key = os.environ.get('R2_ACCESS_KEY_ID')
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY')
    endpoint = os.environ.get('R2_ENDPOINT')
    bucket = os.environ.get('R2_BUCKET')

    if not all([access_key, secret_key, endpoint, bucket]):
        print("Error: Missing R2 credentials in environment variables")
        print("Required: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET")
        return False

    # Validate file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"Error: File not found: {file_path}")
        return False

    # Get file info
    file_size = file_path_obj.stat().st_size
    file_hash = calculate_sha256(file_path)
    filename = file_path_obj.name

    print(f"📦 Uploading: {filename}")
    print(f"   Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
    print(f"   SHA256: {file_hash}")

    # Create S3 client (R2 is S3-compatible)
    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4'),
        region_name='auto'  # R2 uses 'auto' as region
    )

    # Determine platform-arch identifier
    platform_arch = f"{platform}-{arch}"

    # Prepare metadata
    metadata = {
        'version': version,
        'platform': platform,
        'arch': arch,
        'build-date': datetime.utcnow().isoformat() + 'Z',
        'sha256': file_hash,
        'signed': str(signed).lower(),
    }

    if platform == 'macos':
        metadata['notarized'] = str(notarized).lower()

    if commit_sha:
        metadata['commit-sha'] = commit_sha

    # Determine content type
    content_type = get_content_type(filename)

    # Object keys
    # 1. Versioned: releases/v1.0.0/macos-arm64/Ami-1.0.0-macos-arm64.dmg
    versioned_key = f"releases/v{version}/{platform_arch}/{filename}"

    # 2. Latest: releases/latest/macos-arm64/Ami-latest-macos-arm64.dmg
    latest_filename = f"Ami-latest-{platform_arch}{file_path_obj.suffix}"
    latest_key = f"releases/latest/{platform_arch}/{latest_filename}"

    try:
        print(f"\n📤 Uploading to R2 bucket: {bucket}")

        # Upload versioned file
        print(f"   → Versioned: {versioned_key}")
        s3_client.upload_file(
            str(file_path_obj),
            bucket,
            versioned_key,
            ExtraArgs={
                'ContentType': content_type,
                'Metadata': metadata,
            }
        )
        print(f"      ✓ Uploaded")

        # Upload to latest (overwrites previous)
        print(f"   → Latest: {latest_key}")
        s3_client.upload_file(
            str(file_path_obj),
            bucket,
            latest_key,
            ExtraArgs={
                'ContentType': content_type,
                'Metadata': metadata,
            }
        )
        print(f"      ✓ Uploaded (replaced previous)")

        # Update metadata/latest.json
        update_metadata_json(
            s3_client, bucket, version, platform_arch,
            latest_key, file_size, file_hash, signed, notarized
        )

        # Generate URLs (if bucket is public)
        print(f"\n🔗 Download URLs:")
        # R2 public URL format (if custom domain configured)
        # Otherwise, use presigned URLs or configure public access
        print(f"   Versioned: {endpoint.replace('https://', 'https://pub-')}/{bucket}/{versioned_key}")
        print(f"   Latest:    {endpoint.replace('https://', 'https://pub-')}/{bucket}/{latest_key}")
        print(f"\n💡 Configure R2 public access or custom domain to enable direct downloads")

        return True

    except Exception as e:
        print(f"\n❌ Error uploading to R2: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_metadata_json(
    s3_client, bucket: str, version: str, platform_arch: str,
    latest_key: str, file_size: int, file_hash: str,
    signed: bool, notarized: bool
):
    """Update metadata/latest.json with latest version info"""
    metadata_key = "metadata/latest.json"

    # Try to download existing metadata
    try:
        response = s3_client.get_object(Bucket=bucket, Key=metadata_key)
        metadata = json.loads(response['Body'].read().decode('utf-8'))
    except s3_client.exceptions.NoSuchKey:
        # File doesn't exist, create new
        metadata = {
            "version": version,
            "release_date": datetime.utcnow().isoformat() + 'Z',
            "downloads": {}
        }
    except Exception as e:
        print(f"   ⚠️  Warning: Could not read existing metadata: {e}")
        metadata = {
            "version": version,
            "release_date": datetime.utcnow().isoformat() + 'Z',
            "downloads": {}
        }

    # Update version and release date (assuming this is the latest)
    metadata["version"] = version
    metadata["release_date"] = datetime.utcnow().isoformat() + 'Z'

    # Update platform-specific info
    endpoint = os.environ.get('R2_ENDPOINT')
    download_info = {
        "url": f"{endpoint}/{bucket}/{latest_key}",
        "size": file_size,
        "sha256": file_hash,
        "signed": signed,
    }

    if 'macos' in platform_arch:
        download_info["notarized"] = notarized

    metadata["downloads"][platform_arch] = download_info

    # Upload updated metadata
    try:
        print(f"   → Updating metadata/latest.json")
        s3_client.put_object(
            Bucket=bucket,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2).encode('utf-8'),
            ContentType='application/json',
        )
        print(f"      ✓ Metadata updated")
    except Exception as e:
        print(f"   ⚠️  Warning: Could not update metadata: {e}")


def get_content_type(filename: str) -> str:
    """Get content type based on file extension"""
    ext = Path(filename).suffix.lower()
    content_types = {
        '.dmg': 'application/x-apple-diskimage',
        '.exe': 'application/x-msdownload',
        '.msi': 'application/x-msi',
        '.zip': 'application/zip',
        '.tar.gz': 'application/gzip',
        '.json': 'application/json',
    }
    return content_types.get(ext, 'application/octet-stream')


def main():
    parser = argparse.ArgumentParser(
        description='Upload build artifacts to Cloudflare R2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload macOS ARM64 build (signed and notarized)
  python upload_to_r2.py \\
    --file dist/Ami-1.0.0-macos-arm64.dmg \\
    --version 1.0.0 \\
    --platform macos \\
    --arch arm64 \\
    --signed \\
    --notarized

  # Upload Windows build (unsigned)
  python upload_to_r2.py \\
    --file dist/Ami-1.0.0-windows-x64.zip \\
    --version 1.0.0 \\
    --platform windows \\
    --arch x64

Environment Variables Required:
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
  R2_ENDPOINT
  R2_BUCKET
        """
    )

    parser.add_argument('--file', required=True, help='Path to file to upload')
    parser.add_argument('--version', required=True, help='Version string (e.g., 1.0.0)')
    parser.add_argument('--platform', required=True, choices=['macos', 'windows'], help='Platform')
    parser.add_argument('--arch', required=True, choices=['arm64', 'x64'], help='Architecture')
    parser.add_argument('--signed', action='store_true', help='Binary is code-signed')
    parser.add_argument('--notarized', action='store_true', help='macOS app is notarized')
    parser.add_argument('--commit-sha', help='Git commit SHA')

    args = parser.parse_args()

    success = upload_to_r2(
        file_path=args.file,
        version=args.version,
        platform=args.platform,
        arch=args.arch,
        signed=args.signed,
        notarized=args.notarized,
        commit_sha=args.commit_sha
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
