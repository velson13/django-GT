from django import forms
from .models import Client, DEF_OPT

class ClientForm(forms.ModelForm):
    # 5-bit checkboxes
    defcode_bits = forms.MultipleChoiceField(
        choices=DEF_OPT,
        # choices=[(1 << i, f"Option {i+1}") for i in range(5)],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        # label="Definicija"
    )
    
    class Meta:
        model = Client
        exclude = ['id', 'defcode']
        # fields = "__all__"
        # fields = [
        #     'id', 'ime', 'pib', 'mbr', 'jbkjs', 'adresa', 'mesto', 'postbr',
        #     'kontakt', 'email', 'telefon', 'tekuci', 'website'
        # ]
        labels = {
            'ime': 'Naziv klijenta',
            'pib': 'PIB',
            'mbr': 'Matični broj',
            'jbkjs': 'JBKJS',
            'adresa': 'Adresa',
            'mesto': 'Mesto',
            # 'postbr': 'Poštanski broj',
            'kontakt': 'Kontakt osoba',
            'email': 'e-mail adresa',
            'telefon': 'Broj telefona',
            'tekuci': 'Tekući račun',
            'website': 'Internet stranica',
        }
        widgets = {
            'mesto': forms.Select(attrs={'class': 'form-select'}),
            # 'postbr': forms.TextInput(attrs={
            #     'class': 'form-control',
            #     'readonly': 'readonly',  # user cannot edit, auto-filled
            # }),
            'pib': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{9}', 'maxlength': 9, 'title': '9 cifara'}),
            'mbr': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{8}', 'maxlength': 8, 'title': '8 cifara'}),
            'jbkjs': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{5}', 'maxlength': 5, 'title': '5 cifara'}),
            #'postbr': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{5}', 'maxlength': 5, 'title': '5 cifara'}),
        }

    def clean_pib(self):
        pib = self.cleaned_data.get('pib')
        qs = Client.objects.filter(pib=pib)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)  # allow same value on edit for the same record

        if qs.exists():
            raise forms.ValidationError("Ovaj PIB već postoji u bazi.")
        return pib

    def clean_mbr(self):
        mbr = self.cleaned_data.get('mbr')
        qs = Client.objects.filter(mbr=mbr)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError("Ovaj matični broj već postoji u bazi.")
        return mbr

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': ' '  # required for floating labels
                })
        if self.instance and self.instance.defcode is not None:
            self.fields["defcode_bits"].initial = [
                str(value) for value, label in DEF_OPT
                if self.instance.defcode & value
                # str(1 << i) for i in range(5) if self.instance.defcode & (1 << i)
            ]
        self.fields["defcode_bits"].widget.attrs.update({
            "class": "form-check-input"
        })

    def save(self, commit=True):
        instance = super().save(commit=False)
        bits = self.cleaned_data.get("defcode_bits", [])
        val = 0
        for b in bits:
            val |= int(b)
            
        # enforce CRF bit based on JBKJS
        if self.cleaned_data.get("jbkjs"):
            val |= 8  # force CRF ON
        else:
            val &= ~8  # force CRF OFF


        instance.defcode = val
        if commit:
            instance.save()
        return instance