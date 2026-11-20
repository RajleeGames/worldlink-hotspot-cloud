import ipaddress
import re
from urllib.parse import urlsplit

from django import forms
from .models import Location, OmadaOnboarding, Router, WifiPlan

class BaseStyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'checkbox-input' if isinstance(field.widget, forms.CheckboxInput) else 'input'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3

class LocationForm(BaseStyledForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.company and Location.objects.filter(company=self.company, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A location with this name already exists in this business.')
        return name

    class Meta:
        model = Location
        fields = ['name', 'address']

class RouterForm(BaseStyledForm):
    class Meta:
        model = Router
        fields = ['name', 'location', 'family', 'model_name', 'address', 'management_port', 'serial', 'notes']
    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = Location.objects.filter(company=company).order_by('name')
        self.fields['address'].help_text = ('MikroTik only: private LAN/VPN management IP. '
                                            'For Omada, leave this empty and use the Omada setup page.')
        self.fields['management_port'].help_text = ('MikroTik HTTPS REST port, normally 443. '
                                                     'Omada HTTPS controller URL is configured separately.')
        if not self.fields['location'].queryset.exists():
            self.fields['location'].required = False
            self.fields['location'].help_text = 'A "Main site" location will be created when you save.'

    def clean_management_port(self):
        port = self.cleaned_data['management_port']
        if not 1 <= port <= 65535:
            raise forms.ValidationError('Choose a valid port from 1 to 65535.')
        return port

    def clean(self):
        data = super().clean()
        if data.get('family') == Router.Family.OMADA:
            for field in ('model_name', 'serial'):
                if (self.instance.pk and self.instance.family == Router.Family.OMADA
                        and not getattr(self.instance, field, '')):
                    # Legacy registered routers may lack label metadata; do
                    # not block editing their other fields during migration.
                    continue
                if not (data.get(field) or '').strip():
                    self.add_error(field, 'Required for a remote Omada access point. Find it on the device label.')
        return data


class MikroTikLoginForm(forms.Form):
    username = forms.CharField(max_length=80, label='RouterOS username')
    password = forms.CharField(
        max_length=200, label='RouterOS password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'off'}),
    )
    verify_tls = forms.BooleanField(
        required=False, initial=True, label='Verify HTTPS certificate',
        help_text='Required in production. For a local test with a self-signed certificate, '
                  'you may uncheck this only when Django DEBUG is enabled.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'input'


class OmadaOnboardingForm(BaseStyledForm):
    """Captures safe connection metadata, never hotspot credentials."""

    class Meta:
        model = OmadaOnboarding
        fields = ['connection_mode', 'controller_origin', 'controller_id', 'ap_mac', 'ssid_name', 'setup_notes']

    def __init__(self, *args, submit=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.submit = submit

    def clean_controller_origin(self):
        value = self.cleaned_data['controller_origin'].strip()
        if not value:
            return ''
        try:
            parts = urlsplit(value)
            if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                    or parts.path not in ('', '/') or parts.query or parts.fragment
                    or not 1 <= (parts.port or 443) <= 65535):
                raise ValueError('not an HTTPS origin')
        except ValueError:
            raise forms.ValidationError('Enter an HTTPS origin only, for example https://my-controller.example.ts.net (no path or login).')
        if parts.hostname.lower() == 'localhost':
            raise forms.ValidationError('localhost points to the server itself. Use your private VPN controller address instead.')
        try:
            ip = ipaddress.ip_address(parts.hostname)
        except ValueError:
            pass
        else:
            if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                raise forms.ValidationError('A local-only or non-routable controller address cannot reach WorldLink. Use private VPN access.')
        return value.rstrip('/')

    def clean_controller_id(self):
        value = self.cleaned_data['controller_id'].strip()
        if value and not re.fullmatch(r'[A-Za-z0-9_-]{10,80}', value):
            raise forms.ValidationError('Enter a controller ID of 10–80 letters, numbers, underscores or hyphens.')
        return value

    def clean_ap_mac(self):
        value = self.cleaned_data['ap_mac'].strip()
        if not value:
            return ''
        if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', value):
            raise forms.ValidationError('Enter a valid AP MAC, for example B8-FB-B3-79-B5-60.')
        return value.upper().replace(':', '-')

    def clean_ssid_name(self):
        return self.cleaned_data['ssid_name'].strip()

    def clean_setup_notes(self):
        value = self.cleaned_data['setup_notes'].strip()
        if re.search(r'\b(?:password|api[_ -]?key|client[_ -]?secret|token)\s*[:=]\s*\S+', value, re.I):
            raise forms.ValidationError('Remove credentials or tokens from your notes. WorldLink will arrange a secure handoff.')
        return value

    def clean(self):
        data = super().clean()
        if data.get('connection_mode') == OmadaOnboarding.ConnectionMode.CENTRAL:
            # A central onboarding request must not retain a user URL/ID.
            data['controller_origin'] = ''
            data['controller_id'] = ''
        if self.submit:
            if data.get('connection_mode') == OmadaOnboarding.ConnectionMode.CENTRAL:
                for name in ('ap_mac', 'ssid_name'):
                    if not data.get(name):
                        self.add_error(name, 'Required to connect this AP to WorldLink central Omada.')
            elif data.get('connection_mode') == OmadaOnboarding.ConnectionMode.VPN:
                for name in ('controller_origin', 'controller_id', 'ap_mac', 'ssid_name'):
                    if not data.get(name):
                        self.add_error(name, 'Required for a private controller connection request.')
            elif not data.get('setup_notes') and not data.get('ssid_name'):
                self.add_error('setup_notes', 'Describe your router or Wi-Fi setup so WorldLink can help you.')
        return data


class OmadaCentralAssignmentForm(forms.Form):
    """WorldLink-only site mapping. The IDs are not customer editable."""

    site_name = forms.CharField(max_length=120, label='Central Omada site name')
    inform_site_id = forms.CharField(max_length=80, label='Site inform ID (omadacId)')
    openapi_site_id = forms.CharField(max_length=80, label='Open API siteId')

    def clean_inform_site_id(self):
        value = self.cleaned_data['inform_site_id'].strip().lower()
        if not re.fullmatch(r'[a-f0-9]{16,64}', value):
            raise forms.ValidationError('Copy the 16–64-character hexadecimal omadacId from this site’s Inform URL.')
        return value

    def clean_openapi_site_id(self):
        value = self.cleaned_data['openapi_site_id'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
            raise forms.ValidationError('Copy the exact siteId from the read-only Omada Open API sites list.')
        return value

    def clean_site_name(self):
        name = self.cleaned_data['site_name'].strip()
        if not name:
            raise forms.ValidationError('Name this customer’s site on the central controller.')
        return name

class WifiPlanForm(BaseStyledForm):
    class Meta:
        model = WifiPlan
        fields = ['name','duration_minutes','price','download_kbps','upload_kbps','data_limit_mb','device_limit','is_active']
