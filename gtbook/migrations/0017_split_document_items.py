from django.db import migrations

def migrate_stavke(apps, schema_editor):
    Dokumenti = apps.get_model("gtbook", "Dokumenti")
    OldStavka = apps.get_model("gtbook", "DokumentStavke")
    FakturaStavka = apps.get_model("gtbook", "FakturaStavka")
    OtpremnicaStavka = apps.get_model("gtbook", "OtpremnicaStavka")
    UlaznaFakturaStavka = apps.get_model("gtbook", "UlaznaFakturaStavka")

    for old in OldStavka.objects.all():

        dok = old.dokument

        if not dok:
            continue

        if dok.dok_tip == "IZF":
            FakturaStavka.objects.create(
                faktura=dok,
                naziv=old.naziv,
                tip_prometa=old.tip_prometa,
                kolicina=old.kolicina,
                cena=old.cena,
                jed_mere=old.jed_mere,
            )

        elif dok.dok_tip == "OTP":
            OtpremnicaStavka.objects.create(
                otpremnica=dok,
                naziv=old.naziv,
                tip_prometa=old.tip_prometa,
                kolicina=old.kolicina,
                cena=old.cena,
                jed_mere=old.jed_mere,
            )

        elif dok.dok_tip == "ULF":
            UlaznaFakturaStavka.objects.create(
                ulazna_faktura=dok,
                naziv=old.naziv,
                tip_prometa=old.tip_prometa,
                kolicina=old.kolicina,
                cena=old.cena,
                jed_mere=old.jed_mere,
            )

def reverse_migration(apps, schema_editor):
    # We won't reverse this migration
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('gtbook', '0016_fakturastavka_otpremnicastavka_ulaznafakturastavka'),
    ]

    operations = [
        migrations.RunPython(migrate_stavke, reverse_migration),
    ]
