# clients/models.py
from django.db import models
from django.core.validators import RegexValidator

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

class Client(models.Model):
    #id = models.IntegerField(primary_key=True)   # ID klijenta
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
    # mesto = models.CharField(max_length=100)#, default=0)     # link this to a lookup table
    # postbr = models.CharField(max_length=10, blank=True)  # auto-filled from Mesto
    # postbr = models.CharField(max_length=5)#, default=0)      # postanski broj
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
        return [
            label for value, label in self.DEF_OPT
            if self.defcode & value
        ]