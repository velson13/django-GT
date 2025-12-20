def attach_otpremnice_to_faktura(faktura, otpremnice_ids):
    from gtbook.models import Dokumenti, OtpremnicaStavka, FakturaStavka

    otpremnice = Dokumenti.objects.filter(id__in=otpremnice_ids, dok_tip='OTP')

    for otp in otpremnice:
        # link
        otp.faktura = faktura
        otp.save()

        # copy items
        items = otp.stavke_otp.all()
        for item in items:
            FakturaStavka.objects.create(
                faktura=faktura,
                naziv=item.naziv,
                tip_prometa=item.tip_prometa,
                kolicina=item.kolicina,
                cena=item.cena,
                jed_mere=item.jed_mere,
            )

    # update totals
    recalc_faktura_totals(faktura)

def recalc_faktura_totals(faktura):
    total_P = 0
    total_U = 0

    for item in faktura.stavke_izf.all():
        if item.tip_prometa == "P":
            total_P += item.iznos
        else:
            total_U += item.iznos

    faktura.iznos_P = total_P
    faktura.iznos_U = total_U
    faktura.save()



