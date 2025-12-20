# gtbook/utils.py
from django.db.models import Max, Q, F, IntegerField, ExpressionWrapper
from datetime import date
from ..models import Dokumenti, Klijenti

def next_dok_number(tip):
    year_suffix = str(date.today().year)[-2:]  # e.g. '25'

    # IZF numbering: YY0001, YY0002, ...
    if tip == "IZF":
        last = (
            Dokumenti.objects
            .filter(dok_tip="IZF", dok_br__startswith=year_suffix)
            .aggregate(Max("dok_br"))["dok_br__max"]
        )

        if last:
            # take the last 4 digits safely
            seq = int(last[-4:])
            next_num = seq + 1
        else:
            next_num = 1

        return f"{year_suffix}{next_num:04d}"

    # OTP numbering: OT-YY0001, OT-YY0002, ...
    if tip == "OTP":
        prefix = f"OT-{year_suffix}"

        last = (
            Dokumenti.objects
            .filter(dok_tip="OTP", dok_br__startswith=prefix)
            .aggregate(Max("dok_br"))["dok_br__max"]
        )

        if last:
            # Example last: OT-250025
            # Extract last 4 digits:
            seq = int(last[-4:])   # "0025" → 25
            next_num = seq + 1
        else:
            next_num = 1

        return f"OT-{year_suffix}{next_num:04d}"

    # fallback if someone adds a new type but forgets numbering:
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

def format_qty(x):
    return int(x) if float(x).is_integer() else x
