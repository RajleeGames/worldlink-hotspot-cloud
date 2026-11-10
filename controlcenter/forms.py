from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from tenants.models import Company, Membership
from cloud.models import PlatformBranding

User = get_user_model()


def decorate(form):
    for field in form.fields.values():
        field.widget.attrs['class'] = 'input'
    return form


class CompanyStatusForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['status', 'subscription_ends']
        widgets = {'subscription_ends': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)


class StaffInviteForm(forms.Form):
    name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'placeholder': 'First and last name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'person@worldlinksecurity.co.tz'}))
    role = forms.ChoiceField(choices=[('SUPPORT', 'Support · view only'), ('MANAGER', 'Manager · manage businesses and staff')])

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        if not actor or not actor.is_superuser:
            self.fields['role'].choices = [('SUPPORT', 'Support · view only')]
        decorate(self)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already associated with an account.')
        return email

    def clean_role(self):
        role = self.cleaned_data['role']
        if role == 'MANAGER' and (not self.actor or not self.actor.is_superuser):
            raise forms.ValidationError('Only a WorldLink Super Admin can appoint managers.')
        return role


class BusinessCreateForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'email', 'phone', 'city', 'status', 'subscription_ends']
        widgets = {'subscription_ends': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)


class BusinessOwnerInviteForm(forms.Form):
    name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'placeholder': 'Business owner name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'owner@example.com'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already registered. Use the existing account membership flow instead.')
        return email


class MembershipAddForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'existing-user@example.com'}))
    role = forms.ChoiceField(choices=Membership.Role.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        try:
            self.existing_user = User.objects.get(username__iexact=email, is_active=True, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            raise forms.ValidationError('No active business account was found for this email.')
        return email


class BrandingForm(forms.ModelForm):
    class Meta:
        model = PlatformBranding
        fields = ['name', 'product_name', 'tagline', 'logo']
        widgets = {'name': forms.TextInput(attrs={'placeholder': 'WORLDLINK SECURITY SYSTEMS'}),
                   'product_name': forms.TextInput(attrs={'placeholder': 'WorldLink Hotspot Cloud'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)


class InvitationPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decorate(self)
        self.fields['new_password1'].widget.attrs.update({'autocomplete': 'new-password'})
        self.fields['new_password2'].widget.attrs.update({'autocomplete': 'new-password'})
