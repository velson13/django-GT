def iznos_slovima(iznos: float) -> str:
    ceo = int(iznos)
    dec = int(round((iznos - ceo) * 100))

    def nize(ceo):
        jedinice = ["", "jedan", "dva", "tri", "četiri", "pet", "šest", "sedam", "osam", "devet"]
        naest = ["deset","jedanaest","dvanaest","trinaest","četrnaest",
                 "petnaest","šesnaest","sedamnaest","osamnaest","devetnaest"]
        desetice = ["","", "dvadeset","trideset","četrdeset",
                "pedeset","šezdeset","sedamdeset","osamdeset","devedeset"]
        stotice = ["","sto","dvesta","trista","četiristo",
                    "petsto","šeststo","sedamsto","osamsto","devetsto"]

        if ceo == 0: return ""
        if ceo < 10: return jedinice[ceo]
        if ceo < 20: return naest[ceo-10]
        if ceo < 100: return desetice[ceo//10] + jedinice[ceo%10]
        return stotice[ceo//100] + nize(ceo%100)

    def hiljade_blok(ceo):
        if ceo == 1:
            return "hiljadu"
        blok = nize(ceo)
        if ceo % 100 not in (11,12,13,14):
            if blok.endswith("jedan"):
                blok = blok[:-len("jedan")] + "jedna"
            elif blok.endswith("dva"):
                blok = blok[:-len("dva")] + "dve"
        if ceo % 100 in (11,12,13,14):
            blok += "hiljada"
        elif ceo % 10 in (2,3,4):
            blok += "hiljade"
        else:
            blok += "hiljada"
        return blok

    izlaz = ""

    milioni = ceo // 1_000_000
    hiljade = (ceo // 1_000) % 1_000
    ostalo = ceo % 1_000

    # ---------- milioni ----------
    if milioni:
        izlaz += "milion" if milioni == 1 else nize(milioni) + "miliona"

    # ---------- hiljade ----------
    if hiljade:
        izlaz += hiljade_blok(hiljade)

    # ---------- ostalo ----------
    izlaz += nize(ostalo)

    # ---------- DINAR/DINARA ----------
    # last_unit = nize(ostalo % 10)
    if izlaz.endswith("jedan"):
        din = "dinar"
    else:
        din = "dinara"
    izlaz += din

    if dec > 0:
        return f"{izlaz} i {dec:02d}/100"
    else:
        return izlaz
