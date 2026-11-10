from django import forms
from .models import CaptivePortal


class CaptivePortalForm(forms.ModelForm):
    class Meta:
        model = CaptivePortal
        fields = ['enabled', 'headline_en', 'headline_sw', 'subtitle_en', 'subtitle_sw', 'accent_color', 'support_phone', 'terms']
        widgets = {
            'accent_color': forms.TextInput(attrs={'placeholder': '#1677b8', 'maxlength': '7'}),
            'terms': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'check-input' if isinstance(field.widget, forms.CheckboxInput) else 'input'
