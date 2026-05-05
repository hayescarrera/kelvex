#!/usr/bin/env python3
"""
Create the first admin user and organization for a fresh production deployment.

Usage (inside Docker):
  docker compose exec backend python scripts/create_admin.py

Or with args:
  docker compose exec backend python scripts/create_admin.py \
    --email you@example.com \
    --password "changeme" \
    --name "Your Name" \
    --org "Your Company"
"""
import argparse
import asyncio
import sys
import os

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import async_session
from app.core.security import get_password_hash
from app.models.user import Organization, User, ROLE_OWNER


async def create_admin(email: str, password: str, full_name: str, org_name: str) -> None:
    async with async_session() as db:
        # Check for existing user
        existing = await db.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none():
            print(f"ERROR: User {email} already exists.")
            sys.exit(1)

        # Check for existing org slug
        slug = org_name.lower().replace(" ", "-")
        slug = "".join(c if c.isalnum() or c == "-" else "" for c in slug)
        existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
        if existing_org.scalar_one_or_none():
            import uuid
            slug = f"{slug}-{str(uuid.uuid4())[:8]}"

        org = Organization(name=org_name, slug=slug, plan_tier="pro")
        db.add(org)
        await db.flush()

        user = User(
            email=email.lower(),
            hashed_password=get_password_hash(password),
            full_name=full_name,
            org_id=org.id,
            is_active=True,
            is_admin=True,
            role=ROLE_OWNER,
        )
        db.add(user)
        await db.commit()

        print(f"✓ Organization created: {org_name} (slug: {slug})")
        print(f"✓ Admin user created:   {email}")
        print(f"  Role: owner | Plan: pro")
        print()
        print("Log in at https://app.kelvex.io")


def prompt(label: str, secret: bool = False) -> str:
    import getpass
    fn = getpass.getpass if secret else input
    val = fn(f"{label}: ").strip()
    if not val:
        print(f"ERROR: {label} cannot be empty.")
        sys.exit(1)
    return val


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create first admin user")
    parser.add_argument("--email", help="Admin email")
    parser.add_argument("--password", help="Admin password")
    parser.add_argument("--name", help="Full name")
    parser.add_argument("--org", help="Organization name")
    args = parser.parse_args()

    email = args.email or prompt("Email")
    password = args.password or prompt("Password", secret=True)
    full_name = args.name or prompt("Full name")
    org_name = args.org or prompt("Organization name")

    asyncio.run(create_admin(email, password, full_name, org_name))
