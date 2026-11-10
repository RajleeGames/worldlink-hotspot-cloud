"""EvPay API client for a single-company *pilot*.

No payouts, automatic router activation, or shared multi-tenant wallet routing.
All secrets are read from environment, never from browser-provided values.
"""
import hashlib
import hmac
import json
import re
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from django.conf import settings
from django.core.cache import cache


class EvPayError(RuntimeError):
    pass


def pilot_enabled_for(company):
    return bool(getattr(settings, 'EVPAY_ENABLED', False) and
                getattr(settings, 'EVPAY_COMPANY_ID', 0) == company.pk)


def normalize_msisdn(value):
    value = re.sub(r'[\s()+-]', '', str(value))
    if re.fullmatch(r'0[67]\d{8}', value):
        value = '255' + value[1:]
    if not re.fullmatch(r'255[67]\d{8}', value):
        raise ValueError('Enter a Tanzanian number, e.g. 0712345678 or 255712345678.')
    return value


def sign_payload(secret, timestamp, raw_body):
    return hmac.new(secret.encode('utf-8'), str(timestamp).encode('ascii') + b'.' + raw_body, hashlib.sha256).hexdigest()


def verify_webhook(raw_body, signature_header, secret, now=None):
    if not secret or not signature_header:
        return False
    pairs = dict(p.strip().split('=', 1) for p in signature_header.split(',') if '=' in p)
    t, actual = pairs.get('t', ''), pairs.get('v1', '')
    if not re.fullmatch(r'\d{10,11}', t) or not re.fullmatch(r'[a-fA-F0-9]{64}', actual):
        return False
    if abs(int(now if now is not None else time.time()) - int(t)) > 300:
        return False
    expected = sign_payload(secret, t, raw_body)
    return hmac.compare_digest(expected, actual.lower())


def ensure_settings_ready(require_callback=False):
    if not settings.EVPAY_ENABLED:
        raise EvPayError('EvPay is disabled. Set EVPAY_ENABLED=True after configuring sandbox credentials.')
    needed = ['EVPAY_BASE_URL', 'EVPAY_CLIENT_ID', 'EVPAY_CLIENT_SECRET', 'EVPAY_SIG_KEY']
    if require_callback:
        needed += ['EVPAY_WEBHOOK_TOKEN', 'EVPAY_PUBLIC_BASE_URL', 'EVPAY_WEBHOOK_SECRET']
    missing = [key for key in needed if not getattr(settings, key, '')]
    if missing:
        raise EvPayError('Missing EvPay settings: ' + ', '.join(missing))
    api = urlsplit(settings.EVPAY_BASE_URL)
    cb = urlsplit(settings.EVPAY_PUBLIC_BASE_URL)
    if api.scheme != 'https' or not api.hostname or api.username or api.password or api.query or api.fragment or api.path not in ('', '/'):
        raise EvPayError('EVPAY_BASE_URL must be a trusted HTTPS API origin, without paths or credentials.')
    if not (api.hostname == 'evpay.co' or api.hostname.endswith('.evpay.co') or api.hostname == 'evpay.co.tz' or api.hostname.endswith('.evpay.co.tz')):
        raise EvPayError('API hostname is not an approved EvPay host. Confirm the URL with EvPay.')
    if settings.EVPAY_ENVIRONMENT == 'sandbox' and not any(x in api.hostname for x in ('sandbox', 'uat', 'test')):
        raise EvPayError('Sandbox mode requires a verified EvPay sandbox/UAT API hostname, never the production API.')
    if require_callback and (cb.scheme != 'https' or not cb.hostname or cb.username or cb.password or cb.query or cb.fragment or cb.path not in ('', '/')):
        raise EvPayError('EVPAY_PUBLIC_BASE_URL must be your publicly reachable HTTPS origin.')
    if settings.EVPAY_ENVIRONMENT not in ('sandbox', 'live'):
        raise EvPayError('EVPAY_ENVIRONMENT must be sandbox or live.')
    if settings.EVPAY_ENVIRONMENT == 'live' and not settings.EVPAY_PRODUCTION_CHARGES_ENABLED:
        raise EvPayError('Live payments locked. EVPAY_PRODUCTION_CHARGES_ENABLED must be deliberately enabled.')


def callback_url():
    ensure_settings_ready(require_callback=True)
    return settings.EVPAY_PUBLIC_BASE_URL.rstrip('/') + '/payments/evpay/webhook/' + settings.EVPAY_WEBHOOK_TOKEN + '/'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward merchant authorization to a redirected host.
        return None


def _request(method, path, payload=None, token=None, signed=False, idem_key=None):
    ensure_settings_ready()
    raw = b'' if payload is None else json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'User-Agent': 'curl/8.5.0',
}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if signed:
        timestamp = str(int(time.time() * 1000))
        headers['X-Timestamp'] = timestamp
        headers['X-Signature'] = sign_payload(settings.EVPAY_SIG_KEY, timestamp, raw)
    if idem_key:
        headers['Idempotency-Key'] = idem_key
    url = settings.EVPAY_BASE_URL.rstrip('/') + path
    req = Request(url, data=raw if method == 'POST' else None, headers=headers, method=method)
    try:
        with build_opener(_NoRedirect).open(req, timeout=12) as response:
            result = json.loads(response.read(250000).decode('utf-8'))
    except HTTPError as exc:
        raise EvPayError(f'EvPay returned HTTP {exc.code}. Check merchant access, request fields or credentials.') from None
    except (URLError, TimeoutError) as exc:
        raise EvPayError('EvPay is unreachable or timed out. Do NOT retry the charge automatically; reconcile using the original request reference.') from None
    except (ValueError, UnicodeDecodeError):
        raise EvPayError('EvPay returned an invalid JSON response.') from None
    if not isinstance(result, dict) or result.get('success') is not True or not isinstance(result.get('data'), dict):
        raise EvPayError('EvPay rejected the request. Check enabled collections and API configuration.')
    return result['data']


def access_token():
    ensure_settings_ready()
    key = 'evpay_token_' + hashlib.sha256((settings.EVPAY_BASE_URL + settings.EVPAY_CLIENT_ID).encode()).hexdigest()
    token = cache.get(key)
    if token:
        return token
    data = _request('POST', '/api/auth/v1', {'clientId': settings.EVPAY_CLIENT_ID, 'clientSecret': settings.EVPAY_CLIENT_SECRET})
    token = data.get('accessToken')
    if not isinstance(token, str) or len(token) < 16:
        raise EvPayError('EvPay authentication did not return an access token.')
    ttl = max(1, min(int(data.get('expiresIn') or 3600) - 30, 35970))
    cache.set(key, token, ttl)
    return token


def initiate_ussd(test):
    amount = Decimal(test.amount)
    if amount != amount.to_integral_value() or amount < 100:
        raise EvPayError('EvPay requires at least TZS 100 in whole shillings.')
    if settings.EVPAY_ENVIRONMENT == 'live' and amount > 1000:
        raise EvPayError('Live pilot is capped at TZS 1,000 per test request.')
    phone = normalize_msisdn(test.phone)
    payload = {
        'fsOperator': test.operator, 'amount': int(amount),
        'product': 'WorldLink Wi-Fi payment test',
        'callbackUrl': callback_url(),
        'payerAccountId': phone, 'requestId': test.reference,
        'currency': 'TZS', 'payerName': 'WorldLink pilot',
        'narrative': 'WorldLink payment gateway validation',
    }
    return _request('POST', '/api/v1/payment/ussd', payload, token=access_token(), signed=True, idem_key=test.reference)


def retrieve_ussd(reference):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', reference):
        raise EvPayError('Invalid payment reference')
    return _request('GET', '/api/v1/payment/' + quote(reference), token=access_token(), signed=True)
