"""Omada v6.2.10+ External Portal authorization through trusted HTTPS.

Keep the central controller API IP-restricted and TLS verified. Never publish
controller credentials to browsers or disable certificate verification.
Use a dedicated WorldLink Hotspot Operator account.
"""
import ipaddress
import json
import re
import ssl
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler

from django.conf import settings
from django.utils import timezone

from .collections import EARNING_STATUSES


class OmadaError(RuntimeError):
    pass


MAC_RE = re.compile(r'^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')


def normalize_mac(mac):
    mac = str(mac or '')
    if not MAC_RE.fullmatch(mac):
        raise ValueError('Invalid device MAC.')
    return mac.upper().replace(':', '-')


def controller_context(request, company):
    """Capture a recent, correctly shaped Omada redirect into signed session.

    These URL parameters are NOT authenticated. Server-side payment confirmation
    and a fixed site/SSID/AP allowlist remain mandatory before authorization.
    """
    from .collections import collection_enabled_for, approved_payment_route
    if not collection_enabled_for(company):
        return None
    params = request.GET
    if not any(key in params for key in ('clientMac', 'apMac', 'ssidName')):
        return None
    try:
        client_mac = normalize_mac(params.get('clientMac'))
        ap_mac = normalize_mac(params.get('apMac'))
        ssid = params.get('ssidName', '')
        if not approved_payment_route(company.pk, ap_mac, ssid):
            return None
        radio = int(params.get('radioId', ''))
        if radio not in (0, 1):
            return None
        # Omada v6.3 EAP redirects can supply 10-digit epoch seconds, while
        # the documented external-portal format uses 13-digit milliseconds.
        # Accept either representation without relaxing the 5-minute window.
        timestamp = params.get('t', '')
        if not re.fullmatch(r'(?:\d{10}|\d{13})', timestamp):
            return None
        epoch_seconds = int(timestamp) if len(timestamp) == 10 else int(timestamp) / 1000
        if abs(time.time() - epoch_seconds) > 300:
            return None
        client_ip = str(ipaddress.ip_address(params.get('clientIp', '')))
    except (ValueError, TypeError):
        return None
    payload = {'clientMac': client_mac, 'clientIp': client_ip,
               'apMac': ap_mac, 'ssidName': ssid, 'radioId': radio,
               'capturedAt': int(time.time())}
    request.session[f'whc_omada_client_{company.pk}'] = payload
    return payload


def recent_controller_context(request, company):
    context = request.session.get(f'whc_omada_client_{company.pk}')
    if not isinstance(context, dict) or not isinstance(context.get('capturedAt'), int):
        return None
    if not 0 <= time.time() - context['capturedAt'] <= 600:
        request.session.pop(f'whc_omada_client_{company.pk}', None)
        return None
    return context


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _controller_origin():
    parsed = urlsplit(settings.OMADA_CONTROLLER_URL)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise OmadaError('Configure a trusted HTTPS Omada Controller origin on the private VPN.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,80}', settings.OMADA_CONTROLLER_ID):
        raise OmadaError('Invalid Omada Controller ID.')
    return settings.OMADA_CONTROLLER_URL.rstrip('/') + '/' + settings.OMADA_CONTROLLER_ID


def authorize_paid_collection(collection):
    """Request one bounded Wi-Fi authorization; called only by a trusted worker."""
    from tenants.models import Company
    from .collections import collection_enabled_for, approved_payment_route
    company = Company.objects.filter(pk=collection.company_id).first()
    if not company or not collection_enabled_for(company):
        raise OmadaError('Live hotspot payments are not approved for this business.')
    if collection.status not in EARNING_STATUSES or not collection.confirmed_at:
        raise OmadaError('Payment has not been verified by EvPay.')
    if collection.omada_activated_at:
        return True
    if not collection.client_mac or not collection.ap_mac or not collection.ssid_name:
        raise OmadaError('No captive portal session is bound to this payment.')
    if not approved_payment_route(collection.company_id, collection.ap_mac, collection.ssid_name):
        raise OmadaError('Unexpected AP or SSID for this payment.')
    remaining_ms = int((collection.confirmed_at.timestamp() + collection.plan.duration_minutes * 60
                        - time.time()) * 1000)
    if remaining_ms <= 0:
        raise OmadaError('Paid package expired before the controller was reachable; contact support.')
    origin = _controller_origin()
    if not settings.OMADA_OPERATOR_NAME or not settings.OMADA_OPERATOR_PASSWORD:
        raise OmadaError('Dedicated Omada Hotspot Operator credentials are missing.')
    try:
        context = ssl.create_default_context(cafile=settings.OMADA_CA_FILE or None)
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context),
                              HTTPCookieProcessor(CookieJar()), _NoRedirect())

        def post(path, payload, csrf=None):
            headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            if csrf:
                headers['Csrf-Token'] = csrf
            req = Request(origin + path, method='POST', headers=headers,
                          data=json.dumps(payload, separators=(',', ':')).encode('utf-8'))
            with opener.open(req, timeout=12) as response:
                result = json.loads(response.read(100000).decode('utf-8'))
            if not isinstance(result, dict) or result.get('errorCode') != 0:
                raise OmadaError('Omada rejected the authorization request.')
            return result

        login = post('/api/v2/hotspot/login', {
            'name': settings.OMADA_OPERATOR_NAME, 'password': settings.OMADA_OPERATOR_PASSWORD})
        csrf = (login.get('result') or {}).get('token')
        if not isinstance(csrf, str) or not csrf:
            raise OmadaError('Omada did not return an authentication token.')
        body = {
            'clientMac': collection.client_mac, 'clientIp': collection.client_ip,
            'apMac': collection.ap_mac, 'ssidName': collection.ssid_name,
            'radioId': collection.radio_id, 'time': remaining_ms,
            'authType': 4, 'originUrl': '',
            'downloadRateLimitKbps': collection.plan.download_kbps,
            'uploadRateLimitKbps': collection.plan.upload_kbps,
        }
        if collection.plan.data_limit_mb:
            body['totalTrafficLimitBytes'] = collection.plan.data_limit_mb * 1024 * 1024
        post('/api/v2/hotspot/extPortal/auth', body, csrf=csrf)
    except (OSError, URLError, HTTPError, ssl.SSLError, ValueError, json.JSONDecodeError) as exc:
        raise OmadaError('Omada Controller is unreachable or its TLS/API response is invalid.') from exc
    return True
