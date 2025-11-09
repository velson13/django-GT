# gtbook/models.py
from datetime import date
from django.db import models
from django.core.validators import RegexValidator
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

numeric_validator = RegexValidator(r'^\d+$', 'Dozvoljeni su samo brojevi.')

DEF_OPT = [
    (1 << 0, "Kupac"),
    (1 << 1, "Dobavljač"),
    (1 << 2, "SEF"),
    (1 << 3, "CRF"),
    (1 << 4, "Aktivan"),
]

class Mesto(models.Model):
    grad = models.CharField(max_length=100, unique=True)
    post_code = models.CharField(max_length=10)

    class Meta:
        ordering = ['grad']

    def __str__(self):
        return f"{self.grad} ({self.post_code})"

class Klijenti(models.Model):
    ime = models.CharField(max_length=200)       # naziv klijenta
    pib = models.CharField(
        max_length=9,
        validators=[RegexValidator(r'^\d{9}$', 'PIB mora imati tačno 9 cifara.')]
    )
    mbr = models.CharField(
        max_length=8,
        validators=[RegexValidator(r'^\d{8}$', 'MBR mora imati tačno 8 cifara.')]
    )
    jbkjs = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d{5}$', 'JBKJS mora imati tačno 5 cifara.')]
    )
    adresa = models.CharField(max_length=255)#, default=0)
    mesto = models.ForeignKey(Mesto, on_delete=models.SET_NULL, null=True, blank=True) # linked to lookup table
    kontakt = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefon = models.CharField(max_length=100, blank=True, null=True)
    tekuci = models.CharField(max_length=100, blank=True, null=True)  # racun u banci
    website = models.URLField(blank=True, null=True)
    defcode = models.IntegerField(default=17) # 5-bitni bitmask za kupac/dobavljac/sef/crf/aktivan <- default kupac-aktivan

    def __str__(self):
        return f"{self.id} - {self.ime}"

    def get_defcode_options(self):
        # Vrati citku definiciju klijenta kupac/dobavljac/sef/crf/aktivan
        #return [label for value, label in self.DEF_OPT if self.defcode & value]
        return [label for value, label in DEF_OPT if self.defcode & value]
    
def validate_file_extension(value):
    if value and not value.name.endswith(('.pdf', '.xml')):
        raise ValidationError("Dozvoljeni su samo PDF i XML fajlovi.")

class Dokumenti (models.Model):
    TIPOVI_DOK = [
        ('IZF', 'IZLAZNA FAKTURA'),
        ('ULF', 'ULAZNA FAKTURA'),
        ('OTP', 'OTPREMNICA'),
        # ('RAC', 'faktura (van SEF-a)'),
    ]
    FAK_STATUS = [
        ("NEP", "Neplaćen"),
        ("DEL", "Delimično plaćen"),
        ("PLA", "Plaćen"),
    ]
    SEF_STATUS = [
        ("NAC", "Nacrt"), ("POS", "Poslato"), ("OTK", "Otkazana"), ("STO", "Stornirano"), ("SLA", "Slanje"), ("NOV", "Nova"), ("PRI", "Prihvaćeno"), ("ODB", "Odbijeno"), ("GRE", "Greška prilikom slanja"), ("PRE", "Pregledano"), ("PON", "Ponovo obavešteni"), ("NP", "Nije primenljivo")
    ]
    klijent = models.ForeignKey(Klijenti, on_delete=models.PROTECT)
    dok_tip = models.CharField(max_length=3, choices=TIPOVI_DOK)
    dok_br = models.CharField(max_length=50) # npr. 250001 za fakturu, O-250001 za otpremnicu
    dok_datum = models.DateField(default=date.today)
    val_datum = models.DateField(blank=True, null=True) # za otpremnice NULL
    prm_datum = models.DateField(default=date.today) # datum prometa (ActualDeliveryDate)
    br_ponude = models.CharField(max_length=25, blank=True, null=True) # samo ako ide u CRF
    valuta = models.CharField(max_length=3, default='RSD')
    iznos_P = models.DecimalField(max_digits=12, decimal_places=2, default=0) # prodaja
    iznos_U = models.DecimalField(max_digits=12, decimal_places=2, default=0) # usluge
    status_SEF = models.CharField(max_length=25, choices=SEF_STATUS, default='NAC') # Nacrt, Poslato, Otkazana, Stornirano, Slanje, Nova, Prihvaceno, Odbijeno, Greska prilikom slanja, Pregledano, Ponovo obavesteni, NP
    status_fak = models.CharField(max_length=25, choices=FAK_STATUS, default='NEP') # Neplacen, Delimicno placen, Placen, Storno
    status_dok = models.BooleanField(default=False) # 0 = nacrt, 1 = izdat
    requestId = models.CharField(max_length=25)
    salesInvoiceId = models.CharField(max_length=25)
    purchaseInvoiceId = models.CharField(max_length=25)
    documentId = models.CharField(max_length=25)
    napomena = models.TextField(blank=True, null=True)
    # Self-referential ForeignKey - veza otpremnice sa fakturom
    faktura = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,               # samo otpremnice imaju ovu vrednost (id fakture)
        blank=True,
        related_name='otpremnice'
    )
    file = models.FileField(
        upload_to="documents/%Y/%m/%d/",
        validators=[validate_file_extension],
        null=True,
        blank=True
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['dok_tip', 'dok_br'],
                name='idx_dokumenti_unique'
            )
        ]

    def __str__(self):
        #return f"{self.dok_tip} {self.dok_br}"
        #return f"{self.get_doc_type_display()} #{self.number}"
        return f"{self.get_dok_tip_display()} #{self.dok_br}"

class DokumentStavke(models.Model):
    TIPOVI_PROMETA = [('U', 'usluga'), ('P', 'prodaja')]
    JEDINICE_MERE = [
        ('KT', 'kompl.'),
        ('H87', 'kom.'),
        ('HUR', 'h'),
    ]
    dokument = models.ForeignKey(Dokumenti, related_name='stavke', on_delete=models.CASCADE, null=False, blank=False)
    naziv = models.TextField(blank=True, null=True)
    tip_prometa = models.CharField(max_length=7, choices=TIPOVI_PROMETA, default='U')
    kolicina = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    cena = models.DecimalField(max_digits=12, decimal_places=2)
    jed_mere = models.CharField(_("Jedinica mere"), choices=JEDINICE_MERE, default='H87', max_length=3)
    iznos_stavke = models.GeneratedField(
        expression=models.F('kolicina') * models.F('cena'),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True   # True → stored in DB, False → virtual / computed only
    )
    @property
    def iznos(self):
        return self.kolicina * self.cena

    def __str__(self):
        return f"{self.naziv} ({self.kolicina} × {self.cena})"
    
class Transakcije(models.Model):
    TIP_TRANSAKCIJE = [
        ('debit', 'Isplata'),
        ('credit', 'Uplata'),
    ]
    VRSTA_TRANSAKCIJE =[
        ('bank', 'Banka'),
        ('cash', 'Gotovina'),
        ('other', 'Drugo'),
    ]
    klijent = models.ForeignKey(Klijenti, on_delete=models.CASCADE)
    dokument = models.ForeignKey(Dokumenti, null=True, on_delete=models.SET_NULL)
    benefit = models.CharField(max_length=10, choices=TIP_TRANSAKCIJE)
    iznos = models.DecimalField(max_digits=12, decimal_places=2)
    tra_datum = models.DateField(default=date.today)
    tra_vrsta = models.CharField(max_length=10, choices=VRSTA_TRANSAKCIJE)
    napomena = models.TextField(blank=True, null=True)
