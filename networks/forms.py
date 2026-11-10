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
        fields = ['name', 'location', 'family', 'model_name', 'address', 'serial', 'notes']
    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = Location.objects.filter(company=company).order_by('name')

class WifiPlanForm(BaseStyledForm):
    class Meta:
        model = WifiPlan
        fields = ['name','duration_minutes','price','download_kbps','upload_kbps','data_limit_mb','device_limit','is_active']
