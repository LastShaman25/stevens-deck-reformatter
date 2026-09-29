"""Opt-in shared state for the container deployment; local mode stays available."""
import os


def enabled():
    return os.environ.get('STEVENS_STORAGE_MODE') == 'shared'


def require_configuration():
    if os.environ.get('VERCEL') and not enabled():
        raise RuntimeError('Vercel requires STEVENS_STORAGE_MODE=shared; local state is not deployment-safe.')
    if not enabled():
        return
    required = ('DATABASE_URL', 'STEVENS_STORAGE_NAMESPACE', 'STEVENS_S3_BUCKET',
                'STEVENS_S3_ACCESS_KEY_ID', 'STEVENS_S3_SECRET_ACCESS_KEY', 'CRON_SECRET')
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError('Missing shared deployment settings: ' + ', '.join(missing))
    if os.environ.get('STEVENS_AUTH_MODE', 'invitation') == 'invitation' and len(os.environ.get('STEVENS_ADMIN_CODE', '')) < 20:
        raise RuntimeError('Shared invitation sign-in requires a random STEVENS_ADMIN_CODE of at least 20 characters.')
