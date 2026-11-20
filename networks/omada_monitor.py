"""Strictly read-only Omada Open API monitoring for reviewed routers.

This does NOT configure an AP, approve a business, or authorize Wi-Fi clients.
Only the controller URL and credentials configured by WorldLink on the VPS
are used. Tenant-provided URLs are never network destinations.
"""

import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from payments.omada import normalize_mac
from .models import OmadaDeviceObservation, OmadaOnboarding, Router


class OmadaMonitorError(RuntimeError):
    """A public-safe explanation, never a raw provider response or credential."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_id(value):
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value or ''))


def approved_pilot_router():
    """Require a staff-reviewed exact match to the pre-existing EvPay pilot."""
    if not settings.OMADA_LIVE_ENABLED or settings.OMADA_PILOT_COMPANY_ID <= 0:
        raise OmadaMonitorError('Omada live pilot is disabled.')
    try:
        ap_mac = normalize_mac(settings.OMADA_AP_MAC)
    except ValueError as exc:
        raise OmadaMonitorError('Configure the approved pilot AP MAC first.') from exc

    matches = []
    for router in Router.objects.filter(
        company_id=settings.OMADA_PILOT_COMPANY_ID, family=Router.Family.OMADA,
        omada_onboarding__status=OmadaOnboarding.Status.REVIEWED,
    ).select_related('omada_onboarding'):
        p = router.omada_onboarding
        if (not p.reviewed_by_id or p.connection_mode != OmadaOnboarding.ConnectionMode.VPN
                or p.controller_origin.rstrip('/') != settings.OMADA_CONTROLLER_URL.rstrip('/')
                or p.controller_id != settings.OMADA_CONTROLLER_ID or p.ssid_name != settings.OMADA_SSID):
            continue
        try:
            if normalize_mac(p.ap_mac) == ap_mac:
                matches.append(router)
        except ValueError:
            continue
    if len(matches) != 1:
        raise OmadaMonitorError('Expected exactly one WorldLink-reviewed router matching the Omada pilot settings.')
    return matches[0]


class OmadaReadOnlyClient:
    PAGE_SIZE = 50
    MAX_SITE_PAGES = 4
    MAX_DEVICE_PAGES = 10

    def __init__(self):
        parsed = urlsplit(settings.OMADA_CONTROLLER_URL)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise OmadaMonitorError('Set a trusted HTTPS private-VPN Omada controller origin.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,80}', settings.OMADA_CONTROLLER_ID):
            raise OmadaMonitorError('Omada Controller ID is not configured.')
        if settings.OMADA_OPENAPI_SITE_ID and not _safe_id(settings.OMADA_OPENAPI_SITE_ID):
            raise OmadaMonitorError('Omada Open API site ID has an invalid format.')
        self.controller_id = settings.OMADA_CONTROLLER_ID
        self.origin = settings.OMADA_CONTROLLER_URL.rstrip('/')
        api_key = settings.OMADA_OPENAPI_API_KEY
        client_id = settings.OMADA_OPENAPI_CLIENT_ID
        client_secret = settings.OMADA_OPENAPI_CLIENT_SECRET
        if any('\r' in value or '\n' in value for value in (api_key, client_id, client_secret)):
            raise OmadaMonitorError('Omada API credentials contain an invalid character.')
        if api_key and (client_id or client_secret):
            raise OmadaMonitorError('Choose API Key OR Client credentials, not both.')
        if not api_key and not (client_id and client_secret):
            raise OmadaMonitorError('Configure a view-only Omada Open API Client pair or API Key in the VPS environment.')
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret
        self.opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context(cafile=settings.OMADA_CA_FILE or None)),
            _NoRedirect(),
        )

    def _json(self, path, *, payload=None, auth=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if auth:
            headers['Authorization'] = auth
        req = Request(self.origin + path, method='POST' if payload is not None else 'GET',
                      headers=headers, data=json.dumps(payload).encode('utf-8') if payload is not None else None)
        try:
            with self.opener.open(req, timeout=12) as response:
                raw = response.read(250001)
            if len(raw) > 250000:
                raise OmadaMonitorError('Omada response exceeded the safe size limit.')
            body = json.loads(raw.decode('utf-8'))
        except (HTTPError, URLError, OSError, ssl.SSLError, UnicodeError, ValueError) as exc:
            # Never echo the URL/HTTP headers/response: some providers put tokens there.
            raise OmadaMonitorError('Omada Open API request failed or returned invalid JSON.') from exc
        if not isinstance(body, dict) or body.get('errorCode') != 0:
            raise OmadaMonitorError('Omada Open API rejected a read-only request; check permissions and API version.')
        return body.get('result')

    def _authorization(self):
        if self.api_key:
            return 'Bearer ' + self.api_key
        result = self._json('/openapi/authorize/token?grant_type=client_credentials', payload={
            'omadacId': self.controller_id,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        })
        token = result.get('accessToken') if isinstance(result, dict) else None
        if not isinstance(token, str) or not token or '\r' in token or '\n' in token:
            raise OmadaMonitorError('Omada did not issue an Open API access token.')
        return 'AccessToken=' + token

    def _pages(self, resource, auth, max_pages):
        """Accept Omada array/paginated objects. Incomplete lists never mean not found."""
        found = []
        previous = None
        for page in range(1, max_pages + 1):
            result = self._json(f'/openapi/v1/{self.controller_id}/{resource}?page={page}&pageSize={self.PAGE_SIZE}', auth=auth)
            if isinstance(result, list):
                batch, total = result, None
            elif isinstance(result, dict):
                batch = result.get('data')
                total = result.get('totalRows', result.get('total'))
            else:
                raise OmadaMonitorError('Omada returned an unfamiliar Open API list format.')
            if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
                raise OmadaMonitorError('Omada returned an unfamiliar Open API list format.')
            if batch == previous and batch:
                raise OmadaMonitorError('Omada pagination did not advance; cannot verify the AP.')
            previous = batch
            found.extend(batch)
            if isinstance(total, int) and total >= 0:
                if len(found) >= total:
                    return found
                if not batch:
                    raise OmadaMonitorError('Omada reported more records than it returned.')
            elif len(batch) < self.PAGE_SIZE:
                return found
        raise OmadaMonitorError('Omada result was too large to verify completely.')

    def visible_sites(self):
        """Read-only site inventory for trusted VPS staff (never exposed to tenants)."""
        return self._pages('sites', self._authorization(), self.MAX_SITE_PAGES)

    def _site_id(self, auth, requested_site_id=None):
        sites = self._pages('sites', auth, self.MAX_SITE_PAGES)
        ids = [row.get('siteId', row.get('id')) for row in sites]
        ids = [site for site in ids if isinstance(site, str) and _safe_id(site)]
        requested = requested_site_id or settings.OMADA_OPENAPI_SITE_ID
        if requested_site_id and not _safe_id(requested_site_id):
            raise OmadaMonitorError('The assigned Omada Open API site ID is invalid.')
        if requested:
            if requested not in ids:
                raise OmadaMonitorError('The configured Omada site is not visible to the read-only credential.')
            return requested
        if len(ids) != 1:
            raise OmadaMonitorError('Select one authorized site using OMADA_OPENAPI_SITE_ID.')
        return ids[0]

    def get_ap_state(self, mac, *, site_id=None):
        """Retrieve one AP state within the exact authorized site. No writes."""
        target = normalize_mac(mac)
        auth = self._authorization()
        site_id = self._site_id(auth, requested_site_id=site_id)
        devices = self._pages(f'sites/{site_id}/devices', auth, self.MAX_DEVICE_PAGES)
        for device in devices:
            candidate = device.get('mac', device.get('macAddress', device.get('deviceMac')))
            try:
                if normalize_mac(candidate) != target:
                    continue
            except ValueError:
                continue
            status = device.get('status', device.get('deviceStatus'))
            if isinstance(status, str):
                normalized = status.strip().upper().replace(' ', '_').replace('-', '_')
                if normalized in ('CONNECTED', 'ONLINE'):
                    state = OmadaDeviceObservation.State.CONNECTED
                elif normalized in ('DISCONNECTED', 'OFFLINE', 'ISOLATED', 'HEARTBEAT_MISSED'):
                    state = OmadaDeviceObservation.State.OFFLINE
                elif normalized in ('0', '3', '4'):
                    state = OmadaDeviceObservation.State.OFFLINE
                elif normalized == '1':
                    state = OmadaDeviceObservation.State.CONNECTED
                else:
                    state = OmadaDeviceObservation.State.UNKNOWN
            elif type(status) is int:
                # Omada *Open API* device-list status (not the legacy /api/v2
                # grid/devices field): 0=disconnected, 1=connected, 2=pending,
                # 3=heartbeat missed, 4=isolated. Pending/unknown must not
                # appear as a successfully connected AP.
                if status == 1:
                    state = OmadaDeviceObservation.State.CONNECTED
                elif status in (0, 3, 4):
                    state = OmadaDeviceObservation.State.OFFLINE
                else:
                    state = OmadaDeviceObservation.State.UNKNOWN
            elif type(device.get('connected')) is bool:
                state = (OmadaDeviceObservation.State.CONNECTED if device['connected']
                         else OmadaDeviceObservation.State.OFFLINE)
            else:
                # Other/unexpected types are not evidence that the AP is online.
                state = OmadaDeviceObservation.State.UNKNOWN
            reported = re.sub(r'[^a-zA-Z0-9_ -]', '', str(status))[:60] if status is not None else ''
            return state, reported
        return OmadaDeviceObservation.State.NOT_FOUND, ''


def poll_approved_pilot():
    router = approved_pilot_router()
    try:
        state, reported = OmadaReadOnlyClient().get_ap_state(router.omada_onboarding.ap_mac)
    except OmadaMonitorError:
        # A failed check must never leave an old green status looking current.
        OmadaDeviceObservation.objects.update_or_create(router=router, defaults={
            'state': OmadaDeviceObservation.State.ERROR, 'reported_status': '', 'checked_at': timezone.now(),
        })
        raise
    obs, _ = OmadaDeviceObservation.objects.update_or_create(router=router, defaults={
        'state': state, 'reported_status': reported, 'checked_at': timezone.now(),
    })
    return obs


def approved_managed_routers():
    """Explicitly staff-mapped APs only; no tenant-provided API destinations."""
    return Router.objects.filter(
        family=Router.Family.OMADA,
        omada_onboarding__status=OmadaOnboarding.Status.REVIEWED,
        omada_onboarding__reviewed_by__isnull=False,
        omada_onboarding__connection_mode=OmadaOnboarding.ConnectionMode.CENTRAL,
        omada_onboarding__managed_site__isnull=False,
        omada_onboarding__managed_site__company_id=F('company_id'),
    ).select_related('omada_onboarding__managed_site').order_by('pk')


def poll_approved_managed(limit=50):
    """Observe independently approved APs. Failures never retain green status."""
    if not 1 <= limit <= 200:
        raise OmadaMonitorError('Choose a limit from 1 to 200.')
    routers = list(approved_managed_routers()[:limit])
    if not routers:
        return []
    # One trusted controller endpoint and credential, never URLs from a tenant.
    try:
        client = OmadaReadOnlyClient()
    except OmadaMonitorError:
        for router in routers:
            OmadaDeviceObservation.objects.update_or_create(router=router, defaults={
                'state': OmadaDeviceObservation.State.ERROR, 'reported_status': '',
                'checked_at': timezone.now(),
            })
        raise
    results = []
    for router in routers:
        profile = router.omada_onboarding
        try:
            if not profile.ap_mac or not profile.ssid_name or not profile.managed_site.openapi_site_id:
                raise OmadaMonitorError('Approved AP is missing required central-site details.')
            state, reported = client.get_ap_state(
                profile.ap_mac, site_id=profile.managed_site.openapi_site_id,
            )
        except (OmadaMonitorError, ValueError):
            state, reported = OmadaDeviceObservation.State.ERROR, ''
        observation, _ = OmadaDeviceObservation.objects.update_or_create(router=router, defaults={
            'state': state, 'reported_status': reported, 'checked_at': timezone.now(),
        })
        results.append(observation)
    return results
