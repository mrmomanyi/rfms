from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Measurement


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class MeasurementForm(forms.ModelForm):
    class Meta:
        model = Measurement
        fields = ('measured_on', 'dbh_cm', 'height_m')
        widgets = {
            'measured_on': forms.DateInput(attrs={'type': 'date'}),
            'dbh_cm': forms.NumberInput(attrs={'step': '0.1', 'min': '0.1', 'placeholder': 'e.g. 24.5'}),
            'height_m': forms.NumberInput(attrs={'step': '0.1', 'min': '0.1', 'placeholder': 'optional'}),
        }
        labels = {
            'measured_on': 'Date measured',
            'dbh_cm': 'Trunk diameter at 1.3 m (cm)',
            'height_m': 'Height (m)',
        }
