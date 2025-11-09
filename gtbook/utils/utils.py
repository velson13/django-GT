# gtbook/utils.py
from django.db.models import Max, Q, F, IntegerField, ExpressionWrapper
from datetime import date
from ..models import Dokumenti, Klijenti

def next_dok_number(tip):
    year_suffix = str(date.today().year)[-2:]  # e.g. '25'
    base_year_prefix = f"{year_suffix}"

    if tip == "IZF":
        last_dok = (
            Dokumenti.objects
            .filter(dok_tip="IZF", dok_br__startswith=base_year_prefix)
            .aggregate(Max("dok_br"))["dok_br__max"]
        )
        if last_dok:
            next_num = int(str(last_dok)[-4:]) + 1
        else:
            next_num = 1
        return f"{year_suffix}{next_num:04d}"

    elif tip == "OTP":
        # Separate numbering for OTP
        prefix = f"OT-{year_suffix}"
        last_dok = (
            Dokumenti.objects
            .filter(dok_tip="OTP", dok_br__startswith=prefix)
            .aggregate(Max("dok_br"))["dok_br__max"]
        )
        if last_dok:
            next_num = int(str(last_dok).split(year_suffix)[-1]) + 1
        else:
            next_num = 1
        return f"OT-{year_suffix}{next_num:04d}"

    # fallback
    return f"{year_suffix}0001"

def filter_klijenti_by_tip_sqlite(tip):
    all_clients = Klijenti.objects.all()
    filtered_ids = []

    for c in all_clients:
        kupac = c.defcode & 1
        dobavljac = c.defcode & 2
        sef = c.defcode & 4
        #crf = c.defcode & 8
        aktivan = c.defcode & 16

        if not aktivan:
            continue

        if tip == "IZF" and kupac:# and sef:
            filtered_ids.append(c.id)
        elif tip == "ULF" and dobavljac:
            filtered_ids.append(c.id)
        elif tip == "OTP" and kupac:
            filtered_ids.append(c.id)
        elif tip not in ("IZF", "ULF", "OTP"):
            filtered_ids.append(c.id)
        
    return Klijenti.objects.filter(id__in=filtered_ids)