from django import forms
from .models import Client

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['id', 'ime', 'pib', 'mbr', 'jbkjs', 'adresa', 'mesto', 'postbr', 'kontakt', 'email', 'telefon', 'tekuci', 'website', 'defcode']
