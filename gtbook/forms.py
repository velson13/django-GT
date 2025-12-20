from decimal import Decimal
from django import forms
# from django.utils import timezone
from datetime import date, datetime, timedelta
from django.forms import inlineformset_factory
from .models import FakturaStavka, Klijenti, Dokumenti, DEF_OPT, OtpremnicaStavka, UlaznaFakturaStavka


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
        model = Klijenti
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
            'pib': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{9}', 'maxlength': 9, 'title': '9 cifara'}),
            'mbr': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{8}', 'maxlength': 8, 'title': '8 cifara'}),
            'jbkjs': forms.TextInput(attrs={'type': 'text', 'pattern': r'\d{5}', 'maxlength': 5, 'title': '5 cifara'}),
        }

    def clean_pib(self):
        pib = self.cleaned_data.get('pib')
        qs = Klijenti.objects.filter(pib=pib)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)  # allow same value on edit for the same record

        if qs.exists() and pib != '000000000':
            raise forms.ValidationError("Ovaj PIB već postoji u bazi.")
        return pib

    def clean_mbr(self):
        mbr = self.cleaned_data.get('mbr')
        qs = Klijenti.objects.filter(mbr=mbr)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists() and mbr != '00000000':
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
    
class DokumentForm(forms.ModelForm):
    # Add read-only fields to display client info
    klijent_adresa = forms.CharField(label="Adresa", required=False, disabled=True)
    klijent_mesto = forms.CharField(label="Mesto", required=False, disabled=True)
    klijent_pib    = forms.CharField(label="PIB", required=False, disabled=True)
    klijent_mbr    = forms.CharField(label="MBR", required=False, disabled=True)
    dok_datum = forms.DateField(
        widget=forms.DateInput(format='%d.%m.%Y', attrs={'type': 'date'}),
        input_formats=['%d.%m.%Y'],
        required=True
    )
    prm_datum = forms.DateField(
        widget=forms.DateInput(format='%d.%m.%Y', attrs={'type': 'date'}),
        input_formats=['%d.%m.%Y'],
        required=True
    )
    val_datum = forms.DateField(
        widget=forms.DateInput(format='%d.%m.%Y', attrs={'type': 'date'}),
        input_formats=['%d.%m.%Y'],
        required=False
    )
    
    class Meta:
        model = Dokumenti
        # dok_br is excluded – it will be generated automatically
        fields = [
            'klijent', 'dok_br', 'dok_datum', 'val_datum',
            'prm_datum', 'napomena'
        ]
        widgets = {
            'klijent': forms.Select(attrs={'class': 'form-select', 'id': 'klijent-select'}), # fixed ID for JS
            'dok_datum': forms.TextInput(attrs={'class': 'form-control datepicker'}),
            'val_datum': forms.TextInput(attrs={'class': 'form-control datepicker'}),
            'prm_datum': forms.TextInput(attrs={'class': 'form-control datepicker'}),
            'dok_br': forms.TextInput(attrs={'class': 'form-control text-center fw-bold', 'required': 'required'}),
        }
        
    def __init__(self, *args, **kwargs):
        tip = kwargs.get('initial', {}).get('dok_tip')
        super().__init__(*args, **kwargs)

        # # Ensure dok_datum is a date object
        # if self.instance and hasattr(self.instance, 'dok_datum'):
        #     dok_datum_val = self.instance.dok_datum
        #     if dok_datum_val and not isinstance(dok_datum_val, date):
        #         try:
        #             # Try parsing string format
        #             self.instance.dok_datum = datetime.strptime(str(dok_datum_val), "%Y-%m-%d").date()
        #         except Exception:
        #             self.instance.dok_datum = None
        
        if tip != "ULF":
            self.fields['dok_br'].widget.attrs['readonly'] = True

        # Hide val_datum for OTP
        if self.instance and self.instance.dok_tip == 'OTP':
            self.fields['val_datum'].widget = forms.HiddenInput()
            self.fields['val_datum'].required = False
        
        # Bootstrap styling
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': ' '
                })
    
    def clean(self):
        cleaned_data = super().clean()
        dok_tip = cleaned_data.get('dok_tip')
        prm_datum = cleaned_data.get('prm_datum')

        # Auto-calculate val_datum for non-OTP
        if dok_tip != 'OTP' and prm_datum:
            cleaned_data['val_datum'] = prm_datum + timedelta(days=30)
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Auto-generate dok_br based on dok_tip
        if instance.dok_tip == 'IZF' and not instance.dok_br:
            # Get max number for IZF
            last_doc = Dokumenti.objects.filter(dok_tip='IZF').order_by('-id').first()
            if last_doc and last_doc.dok_br.isdigit():
                instance.dok_br = str(int(last_doc.dok_br) + 1)
            else:
                instance.dok_br = '250001'
        elif instance.dok_tip == 'OTP' and not instance.dok_br:
            # Auto-generate OTP with prefix
            last_otp = Dokumenti.objects.filter(dok_tip='OTP').order_by('-id').first()
            if last_otp and last_otp.dok_br.startswith('OT-'):
                last_number = int(last_otp.dok_br.replace('OT-', ''))
                instance.dok_br = f'OT-{last_number + 1}'
            else:
                instance.dok_br = 'OT-250001'
        # ULF: manual, do nothing

        if commit:
            instance.save()
        return instance
 
class DokumentStavkeForm(forms.ModelForm):
    class Meta:
        model = None  # will set dynamically
        fields = ["tip_prometa", "naziv", "kolicina", "cena", "jed_mere"]
        widgets = {
            'tip_prometa': forms.Select(attrs={"class": "form-select form-select-sm"}),
            'naziv': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '', 'required': 'required', 'oninvalid': "this.setCustomValidity('Unesi naziv artikla/usluge')", 'oninput': "this.setCustomValidity('')"}),
            'kolicina': forms.NumberInput(attrs={"class": "form-control form-control-sm text-center", 'required': 'required', 'oninvalid': "this.setCustomValidity('Unesi količinu')", 'oninput': "this.setCustomValidity('')", "step": "0.01", "min": "0.01", "inputmode": "decimal", "style": "-moz-appearance:textfield;"}),
            'cena': forms.NumberInput(attrs={"class": "form-control form-control-sm text-end", 'required': 'required', 'oninvalid': "this.setCustomValidity('Unesi cenu')", 'oninput': "this.setCustomValidity('')", "step": "0.01", "min": "0.01", "inputmode": "decimal", "style": "-moz-appearance:textfield;"}),
            'jed_mere': forms.Select(attrs={"class": "form-select form-select-sm text-center"}),
        }
    def get_stavka_form(tip):
        class StavkaForm(DokumentStavkeForm):
            class Meta(DokumentStavkeForm.Meta):
                if tip == "IZF":
                    model = FakturaStavka
                elif tip == "OTP":
                    model = OtpremnicaStavka
                elif tip == "ULF":
                    model = UlaznaFakturaStavka
        return StavkaForm
            
    def clean(self):
        cleaned = super().clean()
        kolicina = cleaned.get("kolicina")
        cena = cleaned.get("cena")
        jed_mere = cleaned.get("jed_mere")
        print("clean(self)" + jed_mere)
        # negative check
        if kolicina is not None and kolicina < 0:
            self.add_error("kolicina", "Količina ne može biti negativna.")
        if cena is not None and cena < 0:
            self.add_error("cena", "Cena ne može biti negativna.")

        # integer requirement when not 'h'
        if kolicina is not None and jed_mere != "HUR":
             # check if kolicina has decimal part
                if kolicina % 1 != 0:
                    self.add_error(
                        "kolicina",
                        "Količina mora biti ceo broj kada jedinica mere nije 'h'.",
                    )

        return cleaned
        
    def clean_cena(self):
        cena = self.cleaned_data.get("cena")
        if cena is not None:
            # Round to 2 decimal places
            return round(cena, 2)
        return cena
    
    # def clean_kolicina(self):
    #     kolicina = self.cleaned_data.get("kolicina")
    #     jed_mere = self.cleaned_data.get("jed_mere")
    #     if jed_mere: print("clean_kolicina(self)" + jed_mere)
    #     if kolicina is not None and jed_mere not in ("HUR", "h"):
    #     # validate integer requirement WITHOUT casting
    #         if kolicina % Decimal("1") != 0:
    #             raise forms.ValidationError(
    #             "Količina mora biti ceo broj kada jedinica mere nije 'h'."
    #         )
    #     return kolicina

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # kolicina = self.initial.get('kolicina', None)
        # jed_mere = self.initial.get('jed_mere', None)
        # if kolicina is not None:
        #     if jed_mere not in ("HUR", "h"):
        #         self.initial['kolicina'] = int(kolicina)
        #     else:
        #         self.initial['kolicina'] = round(kolicina, 2)    
    
def get_stavke_formset(tip):

    model = {
        "IZF": FakturaStavka,
        "OTP": OtpremnicaStavka,
        "ULF": UlaznaFakturaStavka,
    }[tip]

    return inlineformset_factory(
        Dokumenti,
        model,
        form=DokumentStavkeForm,
        fields=["tip_prometa", "naziv", "kolicina", "jed_mere", "cena"],
        extra=1,
        can_delete=True,
    )