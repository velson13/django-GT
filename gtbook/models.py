# clients/models.py
from django.db import models

class Client(models.Model):
    id = models.IntegerField(primary_key=True)   # keep your existing IDs
    ime = models.CharField(max_length=200)       # customer name
    pib = models.CharField(max_length=9, default=0)         # 9-digit tax number
    mbr = models.CharField(max_length=8, default=0)         # 8-digit id number
    jbkjs = models.CharField(max_length=5, blank=True, null=True)  # optional
    adresa = models.CharField(max_length=255, default=0)
    mesto = models.CharField(max_length=100, default=0)     # we’ll later link this to a lookup table
    postbr = models.CharField(max_length=5, default=0)      # zip code
    kontakt = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefon = models.CharField(max_length=20, blank=True, null=True)
    tekuci = models.CharField(max_length=20, blank=True, null=True)  # bank account
    website = models.URLField(blank=True, null=True)

    # defcode bitmask field
    defcode = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.id} - {self.ime}"
