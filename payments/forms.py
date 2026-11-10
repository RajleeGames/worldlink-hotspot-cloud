import re
from django import forms
from .models import PaymentMethod


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ['channel', 'label', 'account_name', 'account_number', 'instructions', 'is_active']
        widgets = {'instructions': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'check-input' if isinstance(field.widget, forms.CheckboxInput) else 'input'

    def clean(self):
        data = super().clean()
        if data.get('channel') != PaymentMethod.Channel.CASH and (not data.get('account_number') or not data.get('account_name')):
            raise forms.ValidationError('Account name and merchant/account number are required for non-cash methods.')
        return data


class PublicOrderForm(forms.Form):
    customer_name = forms.CharField(max_length=90, min_length=2, widget=forms.TextInput(attrs={'class': 'input', 'autocomplete': 'name'}))
    customer_phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'input', 'autocomplete': 'tel', 'inputmode': 'tel', 'placeholder': '07XX XXX XXX'}))
    method = forms.ModelChoiceField(queryset=PaymentMethod.objects.none(), widget=forms.RadioSelect)

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['method'].queryset = PaymentMethod.objects.filter(company=company, is_active=True).order_by('channel', 'id')
        self.fields['method'].empty_label = None

    def clean_customer_phone(self):
        value = re.sub(r'[\s()\-]', '', self.cleaned_data['customer_phone'])
        if not re.fullmatch(r'(?:\+?255[67]\d{8}|0[67]\d{8})', value):
            raise forms.ValidationError('Enter a valid Tanzanian phone number, e.g. 0712345678.')
        if value.startswith('0'):
            value = '255' + value[1:]
        return value.lstrip('+')


class EvPayTestForm(forms.Form):
    operator = forms.ChoiceField(choices=[
        ('Mpesa', 'M-Pesa'), ('AirtelMoney', 'Airtel Money'),
        ('TigoPesa', 'Mixx by Yas'), ('HaloPesa', 'HaloPesa'),
    ], widget=forms.Select(attrs={'class':'input'}))
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
        'class':'input', 'inputmode':'tel', 'autocomplete':'off', 'placeholder':'255712345678',
    }))
    authorized = forms.BooleanField(required=True)
    amount = forms.IntegerField(min_value=100, max_value=1000000, initial=500,
        widget=forms.NumberInput(attrs={'class':'input','min':'100','step':'1'}))

    def clean_phone(self):
        from .evpay import normalize_msisdn
        try:
            return normalize_msisdn(self.cleaned_data['phone'])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
