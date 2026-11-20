from django import forms
from django.core.exceptions import ValidationError

from payments.evpay import normalize_msisdn
from .models import WithdrawalDestination


def localize_wallet_form(form, request):
    if request.session.get('ui_lang') == 'sw':
        sw = {
            'Confirm your account password': 'Thibitisha nenosiri la akaunti yako',
            'Mobile-money provider': 'Mtandao wa fedha za simu',
            'Receiving phone number': 'Namba ya simu ya kupokea',
            'Registered mobile-money account name': 'Jina lililosajiliwa kwa namba',
            'Verified receiving number': 'Namba ya kupokea iliyothibitishwa',
            'Amount (TZS)': 'Kiasi (TZS)',
            'Cleared amount (TZS)': 'Kiasi kilichothibitishwa (TZS)',
            'Unique real payment reference': 'Kumbukumbu ya muamala halisi',
            'Bank / merchant settlement evidence reference': 'Kumbukumbu ya benki / uthibitisho wa malipo',
        }
        for field in form.fields.values():
            field.label = sw.get(field.label, field.label)
    return form


class AuthenticatedForm(forms.Form):
    password = forms.CharField(
        label='Confirm your account password', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise ValidationError('Your account password is incorrect.')
        return password


class DestinationForm(AuthenticatedForm, forms.ModelForm):
    class Meta:
        model = WithdrawalDestination
        fields = ['provider', 'phone', 'account_name']
        labels = {'provider': 'Mobile-money provider', 'phone': 'Receiving phone number',
                  'account_name': 'Registered mobile-money account name'}
        widgets = {'phone': forms.TextInput(attrs={'placeholder': '0712 345 678', 'autocomplete': 'tel'}),
                   'account_name': forms.TextInput(attrs={'placeholder': 'Exactly as shown by the provider'})}

    def clean_phone(self):
        try:
            return normalize_msisdn(self.cleaned_data['phone'])
        except ValueError as exc:
            raise ValidationError(str(exc)) from None

    def clean_account_name(self):
        value = ' '.join(self.cleaned_data['account_name'].split())
        if len(value) < 5:
            raise ValidationError('Enter the full name registered to this mobile-money number.')
        return value


class WithdrawalForm(AuthenticatedForm):
    destination = forms.ModelChoiceField(queryset=WithdrawalDestination.objects.none(), label='Verified receiving number')
    amount = forms.DecimalField(max_digits=15, decimal_places=0, min_value=1, label='Amount (TZS)')

    def __init__(self, *args, company, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields['destination'].queryset = WithdrawalDestination.objects.filter(
            company=company, status=WithdrawalDestination.Status.VERIFIED)
        self.fields['destination'].label_from_instance = lambda obj: (
            f'{obj.get_provider_display()} · {obj.masked_phone} · {obj.account_name}'
        )


class CollectionForm(forms.Form):
    company_id = forms.IntegerField(widget=forms.HiddenInput)
    amount = forms.DecimalField(max_digits=15, decimal_places=0, min_value=1, label='Cleared amount (TZS)')
    source_reference = forms.CharField(max_length=100, min_length=6,
                                       label='Unique real payment reference')
    settlement_reference = forms.CharField(max_length=100, min_length=6,
                                           label='Bank / merchant settlement evidence reference')


class DestinationReviewForm(forms.Form):
    evidence = forms.CharField(max_length=250, min_length=10, widget=forms.Textarea(attrs={'rows': 2}),
        label='Independent MNO/name check or rejection reason')


class WithdrawalReviewForm(forms.Form):
    payout_reference = forms.CharField(required=False, max_length=100, label='Actual mobile-money transfer ID')
    processing_note = forms.CharField(required=False, max_length=250,
                                       widget=forms.Textarea(attrs={'rows': 2}), label='Review note')
