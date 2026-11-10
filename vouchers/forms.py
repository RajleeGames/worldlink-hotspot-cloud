from django import forms
from networks.models import WifiPlan
from .models import ManualSale, VoucherBatch

class BatchForm(forms.Form):
    plan=forms.ModelChoiceField(queryset=WifiPlan.objects.none(),widget=forms.Select(attrs={'class':'input'}))
    label=forms.CharField(max_length=120,required=False,widget=forms.TextInput(attrs={'class':'input','placeholder':'e.g. Front desk November'}))
    quantity=forms.IntegerField(min_value=1,max_value=500,initial=20,widget=forms.NumberInput(attrs={'class':'input','min':1,'max':500}))
    def __init__(self,*args,company,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['plan'].queryset=WifiPlan.objects.filter(company=company,is_active=True)

class ManualSaleForm(forms.Form):
    method=forms.ChoiceField(choices=ManualSale.PaymentMethod.choices,widget=forms.Select(attrs={'class':'input'}))
    notes=forms.CharField(required=False,max_length=250,widget=forms.TextInput(attrs={'class':'input'}))


class BatchLabelForm(forms.ModelForm):
    class Meta:
        model = VoucherBatch
        fields = ['label']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['label'].widget.attrs['class']='input'
