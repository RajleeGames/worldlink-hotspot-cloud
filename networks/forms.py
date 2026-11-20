from django import forms
from .models import Location, Router, WifiPlan

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
        if not self.fields['location'].queryset.exists():
            self.fields['location'].required = False
            self.fields['location'].help_text = 'A "Main site" location will be created when you save.'

    def clean_management_port(self):
        port = self.cleaned_data['management_port']
        if not 1 <= port <= 65535:
            raise forms.ValidationError('Choose a valid port from 1 to 65535.')
        return port


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

class WifiPlanForm(BaseStyledForm):
    class Meta:
        model = WifiPlan
        fields = ['name','duration_minutes','price','download_kbps','upload_kbps','data_limit_mb','device_limit','is_active']
