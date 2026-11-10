"""Small, guarded patch to keep SQLite and uploads outside the Git checkout.

Run in the WorldLink project root before pushing to GitHub:
    python deploy/patch_settings.py
Works with v0.8 settings.py; does not change the Windows default paths.
"""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
settings = root / 'config' / 'settings.py'
original = settings.read_text(encoding='utf-8')
patches = [
    (
        "'NAME': BASE_DIR / 'db.sqlite3'",
        "'NAME': Path(os.environ.get('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3'))), 'OPTIONS': {'timeout': 20}",
        "SQLite path and timeout",
    ),
    (
        "MEDIA_ROOT = BASE_DIR / 'media'",
        "MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT_PATH', str(BASE_DIR / 'media')))",
        "persistent media path",
    ),
    (
        'SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0',
        "SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0')) if not DEBUG else 0",
        "HSTS rollout control",
    ),
]
updated = original
for old, new, label in patches:
    if new in updated:
        print(f'Already configured: {label}')
    elif old in updated:
        updated = updated.replace(old, new, 1)
        print(f'Configured: {label}')
    else:
        raise SystemExit(f'STOP: expected source not found for {label}. No files changed; inspect config/settings.py manually.')

if updated != original:
    backup = root / 'config' / 'settings.py.before_vps_patch'
    if not backup.exists():
        backup.write_text(original, encoding='utf-8')
    settings.write_text(updated, encoding='utf-8')

ignore_path = root / '.gitignore'
ignore = ignore_path.read_text(encoding='utf-8') if ignore_path.exists() else ''
extra = '''
# Local secrets/backups and SQLite sidecars (never commit)
.env.*
!.env.example
*.sqlite3-*
*.sqlite3.*
*.before_vps_patch
*.backup-*
'''
if '# Local secrets/backups and SQLite sidecars' not in ignore:
    ignore_path.write_text(ignore.rstrip()+'\n'+extra, encoding='utf-8')
print('Done. Windows still uses local db.sqlite3 and media/ by default.')
