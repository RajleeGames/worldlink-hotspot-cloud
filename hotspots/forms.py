from django import forms
from .models import HotspotCustomer

class CustomerForm(forms.ModelForm):
    class Meta:
        model=HotspotCustomer
        fields=['full_name','phone','email','notes']
        widgets={'notes':forms.TextInput(attrs={'placeholder':'Optional notes'})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields.values(): field.widget.attrs['class']='input'
