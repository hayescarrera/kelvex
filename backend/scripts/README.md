## Backend Scripts

### Re-encrypt Legacy Credentials

Migrates legacy plaintext values in `integration_credentials.credentials_encrypted`
to the encrypted payload format used by `app.core.crypto`.

Run from the `backend` directory:

- Dry run: `python scripts/reencrypt_credentials.py --dry-run`
- Apply migration: `python scripts/reencrypt_credentials.py`
