from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User=get_user_model()

class EmailLoginForm(AuthenticationForm):
    username=forms.EmailField(label='Email address',widget=forms.EmailInput(attrs={'class':'input','autofocus':True,'autocomplete':'username','placeholder':'you@business.com'}))
    password=forms.CharField(widget=forms.PasswordInput(attrs={'class':'input','autocomplete':'current-password','placeholder':'Enter your password'}))

class SignupForm(forms.Form):
    business=forms.CharField(max_length=160,widget=forms.TextInput(attrs={'class':'input','placeholder':'Your business name'}))
    name=forms.CharField(max_length=150,widget=forms.TextInput(attrs={'class':'input','placeholder':'Your full name'}))
    email=forms.EmailField(widget=forms.EmailInput(attrs={'class':'input','placeholder':'you@business.com'}))
    password1=forms.CharField(widget=forms.PasswordInput(attrs={'class':'input','autocomplete':'new-password'}))
    password2=forms.CharField(widget=forms.PasswordInput(attrs={'class':'input','autocomplete':'new-password'}))
    def clean_email(self):
        email=self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email
    def clean(self):
        data=super().clean()
        if data.get('password1') and data.get('password1')!=data.get('password2'):
            self.add_error('password2','Passwords do not match.')
        elif data.get('password1'):
            try:
                user=User(username=data.get('email',''),email=data.get('email',''),first_name=data.get('name',''))
                validate_password(data['password1'],user)
            except ValidationError as exc:
                self.add_error('password1',exc)
        return data


from .models import Expense

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date','category','description','amount']
        widgets = {'date':forms.DateInput(attrs={'type':'date'}), 'description':forms.TextInput(attrs={'placeholder':'e.g. Access point maintenance'})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields.values():
            field.widget.attrs['class']='input'
