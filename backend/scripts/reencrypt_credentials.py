"""
One-time migration utility for legacy plaintext integration credentials.

Usage:
  cd backend
  python scripts/reencrypt_credentials.py --dry-run
  python scripts/reencrypt_credentials.py
"""

import argparse
import asyncio

from sqlalchemy import select

from app.core.crypto import encrypt_json, is_encrypted_payload
from app.core.database import async_session
from app.models.integration import IntegrationCredential


async def reencrypt_legacy_credentials(dry_run: bool = True) -> tuple[int, int]:
    scanned = 0
    migrated = 0

    async with async_session() as db:
        result = await db.execute(select(IntegrationCredential))
        credentials = result.scalars().all()

        for cred in credentials:
            scanned += 1
            payload = cred.credentials_encrypted or {}

            if is_encrypted_payload(payload):
                continue

            if not isinstance(payload, dict):
                continue

            if not dry_run:
                cred.credentials_encrypted = encrypt_json(payload)
            migrated += 1

        if not dry_run and migrated > 0:
            await db.commit()

    return scanned, migrated


async def main():
    parser = argparse.ArgumentParser(
        description="Re-encrypt legacy plaintext integration credential blobs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only and print how many records would be migrated.",
    )
    args = parser.parse_args()

    scanned, migrated = await reencrypt_legacy_credentials(dry_run=args.dry_run)

    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"[{mode}] scanned={scanned} migrated={migrated}")
    if args.dry_run:
        print("Re-run without --dry-run to apply encryption migration.")


if __name__ == "__main__":
    asyncio.run(main())
