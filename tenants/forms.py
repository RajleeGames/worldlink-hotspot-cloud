from django import forms
from .models import Company

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'email', 'phone', 'city', 'logo']
        widgets = {key: forms.TextInput(attrs={'class': 'input'}) for key in ['name','phone','city']}
        widgets['email'] = forms.EmailInput(attrs={'class': 'input'})
        widgets['logo'] = forms.ClearableFileInput(attrs={'class': 'file-input', 'accept': 'image/png,image/jpeg,image/webp,image/gif', 'data-logo-input': ''})
