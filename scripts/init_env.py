"""Create a strong unique Django secret without overwriting existing settings."""
import secrets
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
path=ROOT/'.env'
if path.exists():
    print('.env already exists; leaving untouched.')
else:
    key=secrets.token_urlsafe(64)
    path.write_text(f'DJANGO_SECRET_KEY={key}\nDJANGO_DEBUG=True\nDJANGO_ALLOWED_HOSTS=127.0.0.1,localhost\nALLOW_PUBLIC_SIGNUP=True\n',encoding='utf-8')
    print('Created local .env with a unique secret. Never commit it to Git.')
