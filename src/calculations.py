"""Zet de cijfers uit de NBB-CSV's plus de AI-tekst (lijst van dicts) om in een berekend Pandas-DataFrame.

Bevat de M&A-logica voor Fase 1 t/m 4:
- Fase 1: EBITDA & normalisaties
- Fase 2: Equity Bridge (Debt-Like Items, Adjusted Net Debt) & Trade Working Capital
- Fase 3: Meerjarentrends (Omzetgroei %, EBITDA-groei %, Marge-evolutie in pp)
- Fase 4: 3-statement LBO-model op drivers uit de NBB-cijfers (zie lbo_model.py)

Een LBO gebeurt cash-free/debt-free: de bestaande schuld wordt geherfinancierd. Ze
bepaalt dus wat de verkoper overhoudt, niet of de deal kan. Het oordeel kijkt daarom
naar de equity value voor de verkoper en naar de bediening van de nieuwe schuld.
"""
import pandas as pd

from . import assumpties, config, labels, normalisaties, structurering, vlaggen
from .lbo_model import bereken_scenarios, kies_multiples, net_debt

NIET_BESCHIKBAAR = float("nan")  # verschijnt als lege cel in Excel, niet als 0%

# Alleen deze tekstvelden mogen ontbreken: elke andere ontbrekende kolom is een fout
OPTIONELE_TEKSTKOLOMMEN = (
    "Normalisatie_Voorstellen",
    "Buitenbalans_Verplichtingen",
    "Kwalitatief_LBO_Oordeel",
    "Gebruikt_Model",
    "AI_Business_Model",
)
OPTIONELE_AI_LIJSTEN = ("AI_Normalisaties", "AI_Red_Flags", "AI_Buitenbalans", "AI_Investment_Thesis", "AI_DD_Vragen")


def _pct(teller, noemer):
    return round(teller / noemer * 100, 2) if noemer > 0 else NIET_BESCHIKBAAR


def _groei_pct(huidig, vorig):
    """Op basis van abs(vorig), zodat een negatieve basis het teken niet omdraait."""
    return round((huidig - vorig) / abs(vorig) * 100, 2) if vorig != 0 else NIET_BESCHIKBAAR


def bouw_dataframe(resultaten):
    df = pd.DataFrame(resultaten)

    getal_kolommen = [
        "Omzet_of_Brutomarge",
        "Omzet_of_Brutomarge_Vorig_Jaar",
        "Brutomarge",
        "Brutomarge_Vorig_Jaar",
        "Bedrijfswinst_EBIT",
        "Bedrijfswinst_EBIT_Vorig_Jaar",
        "Afschrijvingen",
        "Afschrijvingen_Vorig_Jaar",
        "Voorzieningen_Mutatie",
        "Voorzieningen_Mutatie_Vorig_Jaar",
        "Waardeverminderingen_Vlottend",
        "Waardeverminderingen_Vlottend_Vorig_Jaar",
        "Personeelskosten",
        "Inkoop",
        "VTE",
        "Capex_Laatste_Jaar",
        "Capex_Gemiddeld",
        "Normalisatie_Bedrag",
        "Financiele_Schulden_LT",
        "Financiele_Schulden_KT",
        "Voorzieningen_en_Uitgestelde_Belastingen",
        "Belasting_en_Vervallen_RSZ_Schulden",
        "Overige_Schulden_LT_en_KT",
        "Liquide_Middelen",
        "Eigen_Aandelen",
        "Voorraden",
        "Handelsvorderingen",
        "Handelsschulden",
        "Ontvangen_Vooruitbetalingen",
        "Eigen_Vermogen",
        "Balanstotaal",
        "Overgedragen_Resultaat",
        "Memo_Sociale_Schulden",
        "Memo_Zekerheden_Derden",
        "Memo_Vorderingen_Bestuurders",
        "Memo_Vorderingen_Verbonden",
    ]
    # Vorig jaar is leeg (NaN) als er geen aansluitende CSV is, nooit 0
    for kol in getal_kolommen:
        df[kol] = pd.to_numeric(df[kol])

    # Fase 1: EBITDA rekent Python zelf uit, nooit de AI. Waardeverminderingen (631/4) blijven
    # een kost; voorzieningen (635/8) gaan terug omdat code 16 al debt-like is.
    df["Gerapporteerde_EBITDA"] = (
        df["Bedrijfswinst_EBIT"] + df["Afschrijvingen"] + df["Voorzieningen_Mutatie"]
    )
    df["Gerapporteerde_EBITDA_Vorig_Jaar"] = (
        df["Bedrijfswinst_EBIT_Vorig_Jaar"]
        + df["Afschrijvingen_Vorig_Jaar"]
        + df["Voorzieningen_Mutatie_Vorig_Jaar"]
    )
    # Adjustment ledger: alleen goedgekeurde items met een geverifieerd bedrag (zie normalisaties.py)
    if "LBO_Adjustments" not in df:
        df["LBO_Adjustments"] = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    df["Ledger_EBITDA"] = [
        normalisaties.totaal(items, maanden) for items, maanden in zip(df["LBO_Adjustments"], df["Boekjaar_Maanden"])
    ]
    df["Genormaliseerde_EBITDA"] = df["Gerapporteerde_EBITDA"] + df["Normalisatie_Bedrag"] + df["Ledger_EBITDA"]

    # Fase 3: Meerjarentrends (groei en margestabiliteit)
    df["Omzetgroei_Pct"] = df.apply(
        lambda r: _groei_pct(r["Omzet_of_Brutomarge"], r["Omzet_of_Brutomarge_Vorig_Jaar"]), axis=1
    )
    df["EBITDA_Groei_Pct"] = df.apply(
        lambda r: _groei_pct(r["Gerapporteerde_EBITDA"], r["Gerapporteerde_EBITDA_Vorig_Jaar"]), axis=1
    )

    # Een marge op brutomarge is niet vergelijkbaar met een marge op omzet: dus twee kolommen.
    # De marge op brutomarge bestaat voor elk schema, die op omzet alleen als de omzet openbaar is.
    heeft_omzet = df["Omzet_Basis"] == labels.BASIS_REVENUE
    df["EBITDA_Marge_Op_Omzet_Pct"] = df.apply(
        lambda r: _pct(r["Gerapporteerde_EBITDA"], r["Omzet_of_Brutomarge"]), axis=1
    ).where(heeft_omzet)
    df["EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct"] = df.apply(
        lambda r: _pct(r["Gerapporteerde_EBITDA_Vorig_Jaar"], r["Omzet_of_Brutomarge_Vorig_Jaar"]), axis=1
    ).where(heeft_omzet)
    df["EBITDA_Marge_Op_Brutomarge_Pct"] = df.apply(
        lambda r: _pct(r["Gerapporteerde_EBITDA"], r["Brutomarge"]), axis=1
    )
    df["EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct"] = df.apply(
        lambda r: _pct(r["Gerapporteerde_EBITDA_Vorig_Jaar"], r["Brutomarge_Vorig_Jaar"]), axis=1
    )
    df["Marge_Verandering_pp"] = (
        (df["EBITDA_Marge_Op_Omzet_Pct"] - df["EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct"])
        .where(heeft_omzet, df["EBITDA_Marge_Op_Brutomarge_Pct"] - df["EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct"])
        .round(2)
    )

    # DSO as a KPI: receivables include 21% VAT, revenue does not (display only)
    df["Driver_DSO_Excl_BTW"] = pd.to_numeric(df["Driver_DSO"]) / config.BTW_FACTOR

    # Fase 2: Equity Bridge & Trade Working Capital
    df["Totale_Financiele_Schuld"] = df["Financiele_Schulden_LT"] + df["Financiele_Schulden_KT"]
    df["Debt_Like_Items"] = (
        df["Voorzieningen_en_Uitgestelde_Belastingen"]
        + df["Belasting_en_Vervallen_RSZ_Schulden"]
        + df["Overige_Schulden_LT_en_KT"]
    )
    # Cash die nodig is voor de bedrijfsvoering, is niet vrij en telt dus niet als aftrek.
    # De behoefte hangt niet af van het schema: code 62 en 44 bestaan in elk schema.
    # Cash-opex = personeel + overige kosten (netto, nooit negatief), dezelfde lijnen als de historiek in de Excel
    df["Overige_Kosten_Cash"] = (
        df["Omzet_of_Brutomarge"] - df["Inkoop"] - df["Personeelskosten"]
        - (df["Gerapporteerde_EBITDA"] + df["Normalisatie_Bedrag"])
    ).clip(lower=0)
    df["Minimum_Cash_Behoefte"] = (
        (df["Personeelskosten"] + df["Overige_Kosten_Cash"]) * config.MIN_CASH_MAANDEN_OPEX / 12
        + df["Inkoop"] * config.MIN_CASH_PCT_INKOOP
    )
    df["Minimum_Operationele_Cash"] = df["Minimum_Cash_Behoefte"].clip(lower=0, upper=df["Liquide_Middelen"])
    df["Net_Debt"] = net_debt(
        "bank_covenant", df["Totale_Financiele_Schuld"], df["Liquide_Middelen"], df["Minimum_Operationele_Cash"]
    )
    # Groepsvorderingen in 41 die vóór closing vereffend worden (config.INTERCOMPANY_BEHANDELING = "cash_like")
    df["Intercompany_Cash_Like"] = pd.to_numeric(df["Open_Intercompany_Cash_Like"]).fillna(0.0)
    df["Adjusted_Net_Debt"] = net_debt(
        "waardering",
        df["Totale_Financiele_Schuld"],
        df["Liquide_Middelen"],
        df["Minimum_Operationele_Cash"],
        df["Debt_Like_Items"],
    ) - df["Intercompany_Cash_Like"]
    df["Trade_Working_Capital"] = (
        df["Voorraden"]
        + df["Handelsvorderingen"]
        - df["Handelsschulden"]
        - df["Ontvangen_Vooruitbetalingen"]
    )

    # Bestaande schuldgraad is informatie: de schuld wordt bij een LBO geherfinancierd
    df["Huidige_Net_Debt_to_EBITDA"] = df.apply(
        lambda r: round(r["Adjusted_Net_Debt"] / r["Genormaliseerde_EBITDA"], 2)
        if r["Genormaliseerde_EBITDA"] > 0
        else NIET_BESCHIKBAAR,
        axis=1,
    )
    multiples = df["Genormaliseerde_EBITDA"].apply(kies_multiples)
    df["Instap_Multiple"] = [instap for instap, _ in multiples]
    df["Senior_Multiple"] = [senior for _, senior in multiples]
    df["Indicatieve_EV"] = df["Genormaliseerde_EBITDA"] * df["Instap_Multiple"]
    # NWC-peg: werkkapitaal boven het normale niveau wordt aan de verkoper betaald (en omgekeerd)
    df["NWC_Aanpassing"] = pd.to_numeric(df["NWC_Aanpassing"]).fillna(0.0)
    df["Indicatieve_Equity_Value"] = df["Indicatieve_EV"] - df["Adjusted_Net_Debt"] + df["NWC_Aanpassing"]

    # Fase 4: 3-statement LBO-model. De assumpties komen van Gemini of, zonder AI, uit de mechanische drivers.
    if "LBO_Assumpties" not in df:
        df["LBO_Assumpties"] = None
    if "LBO_Assumptie_Bron" not in df:
        df["LBO_Assumptie_Bron"] = labels.ASSUMPTIONS_FALLBACK_NO_AI
    if "LBO_Driver_Pack" not in df:
        df["LBO_Driver_Pack"] = None
    df["LBO_Assumpties"] = pd.Series(
        [
            r["LBO_Assumpties"] if r["LBO_Assumpties"] is not None
            else assumpties.mechanische_assumpties(r, r["LBO_Assumptie_Bron"])
            for _, r in df.iterrows()
        ],
        index=df.index,
        dtype=object,
    )
    # Approved ledger adjustments are lasting cost savings: the AI scenarios get the same lower cost ratio
    # (the mechanical drivers already start from the adjusted EBITDA)
    df["LBO_Assumpties"] = pd.Series(
        [
            assumpties.met_ledger(r["LBO_Assumpties"], r["Ledger_EBITDA"], r["Omzet_of_Brutomarge"])
            if r["LBO_Assumptie_Bron"] == labels.ASSUMPTIONS_AI
            else r["LBO_Assumpties"]
            for _, r in df.iterrows()
        ],
        index=df.index,
        dtype=object,
    )
    # The screening case is always added: it never depends on Gemini
    df["LBO_Assumpties"] = pd.Series(
        [{**r["LBO_Assumpties"], **assumpties.screening_assumpties(r)} for _, r in df.iterrows()],
        index=df.index,
        dtype=object,
    )
    for kol in ("LBO_Snapshot_Naam", "LBO_Snapshot_Datum", "LBO_Snapshot_Status"):
        if kol not in df:
            df[kol] = "-"
    df["LBO_Assumptie_Vlaggen"] = pd.Series(
        [
            assumpties.controleer(
                r["LBO_Assumpties"],
                r["LBO_Driver_Pack"]["Fiscal_Years"],
                r["Omzet_of_Brutomarge"],
                r["Personeelskosten"],
                ebitda_0=r["Genormaliseerde_EBITDA"],
                hist_ebitda_cagr=r["Driver_EBITDA_CAGR_Pct"],
            )
            if r["LBO_Driver_Pack"] is not None
            else []
            for _, r in df.iterrows()
        ],
        index=df.index,
        dtype=object,
    )
    scenario_modellen = df.apply(bereken_scenarios, axis=1)
    lbo_modellen = [modellen["base"] for modellen in scenario_modellen]
    lbo_velden = [
        "LBO_Instap_EV",
        "LBO_Transactiekosten",
        "LBO_Financieringskosten",
        "LBO_Kosten",
        "LBO_Senior_Schuld",
        "LBO_Vendor_Loan",
        "LBO_Sponsor_Equity_Instap",
        "LBO_Closing_Datum",
        "LBO_Duur_Jaren",
        "LBO_EBITDA_Jaar5",
        "LBO_EBITDA_Marge_Exit_Pct",
        "LBO_FCF_Cumulatief_5J",
        "LBO_Dividend_Cumulatief",
        "LBO_Eind_Net_Debt_Jaar5",
        "LBO_Eind_Net_Debt_to_EBITDA",
        "LBO_Schuld_Onder_2x_5J",
        "LBO_Laagste_DSCR",
        "LBO_Laagste_Rentedekking",
        "LBO_Hoogste_Leverage",
        "LBO_Laagste_Cash",
        "LBO_Cash_Onder_Minimum",
        "LBO_RCF_Limiet",
        "LBO_RCF_Piek",
        "LBO_RCF_Eind",
        "LBO_Convenanten",
        "LBO_Exit_EV_Jaar5",
        "LBO_Exit_Equity_Jaar5",
        "Indicatieve_MoIC",
        "Indicatieve_IRR_Pct",
    ]
    for veld in lbo_velden:
        df[veld] = [m[veld] for m in lbo_modellen]
    # Een fout in één scenario is een fout in het model, ook al is de base toevallig schoon
    df["LBO_Balanscheck"] = [
        next((m["LBO_Balanscheck"] for m in modellen.values() if m["LBO_Balanscheck"] != labels.CHECK_OK), labels.CHECK_OK)
        for modellen in scenario_modellen
    ]
    df["LBO_Downside_IRR_Pct"] = [m["downside"]["Indicatieve_IRR_Pct"] for m in scenario_modellen]
    df["LBO_Downside_MoIC"] = [m["downside"]["Indicatieve_MoIC"] for m in scenario_modellen]
    df["LBO_Downside_Convenanten"] = [m["downside"]["LBO_Convenanten"] for m in scenario_modellen]
    df["LBO_Upside_IRR_Pct"] = [m["upside"]["Indicatieve_IRR_Pct"] for m in scenario_modellen]
    # Screening case: rule-based and identical for every run, shown next to the analyst case.
    # The assessment does not use it yet (phase 5 of the roadmap).
    df["LBO_Screening_IRR_Pct"] = [m["screening_base"]["Indicatieve_IRR_Pct"] for m in scenario_modellen]
    df["LBO_Screening_MoIC"] = [m["screening_base"]["Indicatieve_MoIC"] for m in scenario_modellen]
    df["LBO_Screening_Convenanten"] = [m["screening_base"]["LBO_Convenanten"] for m in scenario_modellen]
    df["LBO_Stress_IRR_Pct"] = [m["screening_stress"]["Indicatieve_IRR_Pct"] for m in scenario_modellen]
    df["LBO_Stress_Laagste_DSCR"] = [m["screening_stress"]["LBO_Laagste_DSCR"] for m in scenario_modellen]
    df["LBO_Stress_Convenanten"] = [m["screening_stress"]["LBO_Convenanten"] for m in scenario_modellen]
    # Phase 4: debt capacity (Screening Stress) and ability-to-pay (Screening Base, and AI base as information)
    structuur = pd.DataFrame([structurering.analyseer(r) for _, r in df.iterrows()], index=df.index)
    df = pd.concat([df, structuur], axis=1)
    df["LBO_IRR_Exact_Pct"] = [m["LBO_IRR_Exact_Pct"] for m in lbo_modellen]
    df["LBO_MoIC_Exact"] = [m["LBO_MoIC_Exact"] for m in lbo_modellen]
    df["LBO_Forecast_Groei_Pct"] = [
        ((m["Jaren"][-1]["Omzet"] / r) ** (1 / m["LBO_Duur_Jaren"]) - 1) * 100 if m["Jaren"] and r > 0 else NIET_BESCHIKBAAR
        for m, r in zip(lbo_modellen, df["Omzet_of_Brutomarge"])
    ]
    # De export toont dit resultaat en rekent het model niet opnieuw door
    df["LBO_Jaren"] = pd.Series([m["Jaren"] for m in lbo_modellen], index=df.index, dtype=object)
    df["LBO_Integriteit"] = pd.Series([m["Integriteit"] for m in lbo_modellen], index=df.index, dtype=object)
    df["LBO_Scenarios"] = pd.Series(list(scenario_modellen), index=df.index, dtype=object)

    # Phase 5.1: structured red flags (source, category, severity); the text column is the summary
    if "AI_Red_Flags" not in df:
        df["AI_Red_Flags"] = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    df["Red_Flag_Lijst"] = pd.Series([vlaggen.bouw_vlaggen(r) for _, r in df.iterrows()], index=df.index, dtype=object)
    df["Red_Flags"] = [vlaggen.als_tekst(lijst) for lijst in df["Red_Flag_Lijst"]]
    df["Aantal_Hoge_Vlaggen"] = [vlaggen.tel(lijst, "hoog") for lijst in df["Red_Flag_Lijst"]]
    df["Aantal_Middel_Vlaggen"] = [vlaggen.tel(lijst, "middel") for lijst in df["Red_Flag_Lijst"]]

    def bepaal_status(rij):
        if rij["Check_Data"] != labels.CHECK_OK:
            return labels.STATUS_REVIEW_DATA
        if rij["LBO_Balanscheck"] == labels.CHECK_ERROR:
            return labels.STATUS_REVIEW_MODEL
        if rij["Data_Volledigheid"].startswith(labels.DATA_INSUFFICIENT):
            return labels.STATUS_INSUFFICIENT
        if rij["Genormaliseerde_EBITDA"] <= 0:
            return labels.STATUS_NO_GO_EBITDA
        if rij["Genormaliseerde_EBITDA"] < config.LBO_MIN_EBITDA:
            return labels.STATUS_NO_GO_SIZE
        if rij["LBO_Convenanten"].startswith(labels.NOT_APPLICABLE):
            return labels.STATUS_INSUFFICIENT
        if rij["Indicatieve_Equity_Value"] <= 0:
            return labels.STATUS_NO_GO_EQUITY.format(multiple=rij["Instap_Multiple"])
        if rij["LBO_Convenanten"] != labels.COVENANTS_OK or rij["LBO_Laagste_Cash"] < 0:
            return labels.STATUS_NO_GO_DEBT
        if rij["Indicatieve_IRR_Pct"] < 0:
            return labels.STATUS_NO_GO_RETURN
        if rij["Aantal_Hoge_Vlaggen"]:
            return labels.STATUS_POSSIBLE_FLAGS
        if (
            rij["Data_Volledigheid"] == labels.DATA_COMPLETE
            and rij["LBO_Eind_Net_Debt_to_EBITDA"] < config.LBO_TARGET_END_LEVERAGE
            and rij["Indicatieve_IRR_Pct"] >= config.LBO_MIN_IRR_PCT
        ):
            return labels.STATUS_STRONG
        return labels.STATUS_POSSIBLE_CASHFLOW

    df["LBO_Status"] = df.apply(bepaal_status, axis=1)

    volgorde = [
        "Bedrijfsnaam",
        "Ondernemingsnummer",
        "Boekjaar",
        "Boekjaar_Begin",
        "Boekjaar_Einde",
        "Boekjaar_Maanden",
        "Boekjaar_Maanden_Vorig_Jaar",
        "Schema_Type",
        "LBO_Status",
        "Data_Volledigheid",
        "Omzet_Basis",
        "Omzet_of_Brutomarge_Vorig_Jaar",
        "Omzet_of_Brutomarge",
        "Omzetgroei_Pct",
        "Brutomarge_Vorig_Jaar",
        "Brutomarge",
        "Bedrijfswinst_EBIT_Vorig_Jaar",
        "Bedrijfswinst_EBIT",
        "Afschrijvingen_Vorig_Jaar",
        "Afschrijvingen",
        "Voorzieningen_Mutatie_Vorig_Jaar",
        "Voorzieningen_Mutatie",
        "Gerapporteerde_EBITDA_Vorig_Jaar",
        "Gerapporteerde_EBITDA",
        "EBITDA_Groei_Pct",
        "Waardeverminderingen_Vlottend_Vorig_Jaar",
        "Waardeverminderingen_Vlottend",
        "Inkoop",
        "Personeelskosten",
        "VTE",
        "Normalisatie_Bedrag",
        "Ledger_EBITDA",
        "Genormaliseerde_EBITDA",
        "EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct",
        "EBITDA_Marge_Op_Omzet_Pct",
        "EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct",
        "EBITDA_Marge_Op_Brutomarge_Pct",
        "Marge_Verandering_pp",
        "Check_Data",
        "Financiele_Schulden_LT",
        "Financiele_Schulden_KT",
        "Totale_Financiele_Schuld",
        "Liquide_Middelen",
        "Eigen_Aandelen",
        "Net_Debt",
        "Voorzieningen_en_Uitgestelde_Belastingen",
        "Belasting_en_Vervallen_RSZ_Schulden",
        "Overige_Schulden_LT_en_KT",
        "Debt_Like_Items",
        "Intercompany_Cash_Like",
        "Overige_Kosten_Cash",
        "Minimum_Cash_Behoefte",
        "Minimum_Operationele_Cash",
        "Adjusted_Net_Debt",
        "Memo_Sociale_Schulden",
        "Memo_Zekerheden_Derden",
        "Memo_Vorderingen_Bestuurders",
        "Memo_Vorderingen_Verbonden",
        "Memo_Schulden_Verbonden",
        "Voorraden",
        "Handelsvorderingen",
        "Handelsschulden",
        "Ontvangen_Vooruitbetalingen",
        "Trade_Working_Capital",
        "NWC_Peg_Pct",
        "NWC_Peg",
        "NWC_Peg_Jaren",
        "NWC_Aanpassing",
        "Capex_Laatste_Jaar",
        "Capex_Gemiddeld",
        "Capex_Aantal_Jaren",
        "Huidige_Net_Debt_to_EBITDA",
        "Driver_Aantal_Jaren",
        "Driver_Historische_CAGR_Pct",
        "Driver_Omzetgroei_Pct",
        "Driver_EBITDA_CAGR_Pct",
        "Driver_EBITDA_Marge_Gemiddeld_Pct",
        "Driver_EBITDA_Marge_Pct",
        "Driver_Inkoop_Pct",
        "Driver_Overige_Kosten_Pct",
        "Driver_DA_Pct_Vaste_Activa",
        "Driver_Capex_Pct",
        "Driver_DSO",
        "Driver_DSO_Excl_BTW",
        "Driver_DIO",
        "Driver_DPO",
        "Driver_Dagen_Vooruitbetaling",
        "Driver_Kosten_60_Pct",
        "Driver_Kosten_6061_Pct",
        "Open_Vaste_Activa",
        "Open_Financiele_Vaste_Activa",
        "Open_Overige_Activa_Operationeel",
        "Open_Overige_Activa_Niet_Operationeel",
        "Open_Intercompany_Cash_Like",
        "Open_Sociale_Schulden",
        "Open_Overige_Passiva",
        "Instap_Multiple",
        "Senior_Multiple",
        "Indicatieve_EV",
        "Indicatieve_Equity_Value",
        "LBO_Instap_EV",
        "LBO_Transactiekosten",
        "LBO_Financieringskosten",
        "LBO_Kosten",
        "LBO_Senior_Schuld",
        "LBO_Vendor_Loan",
        "LBO_Sponsor_Equity_Instap",
        "LBO_Closing_Datum",
        "LBO_Duur_Jaren",
        "LBO_EBITDA_Jaar5",
        "LBO_EBITDA_Marge_Exit_Pct",
        "LBO_FCF_Cumulatief_5J",
        "LBO_Dividend_Cumulatief",
        "LBO_Eind_Net_Debt_Jaar5",
        "LBO_Eind_Net_Debt_to_EBITDA",
        "LBO_Schuld_Onder_2x_5J",
        "LBO_Laagste_DSCR",
        "LBO_Laagste_Rentedekking",
        "LBO_Hoogste_Leverage",
        "LBO_Laagste_Cash",
        "LBO_Cash_Onder_Minimum",
        "LBO_RCF_Limiet",
        "LBO_RCF_Piek",
        "LBO_RCF_Eind",
        "LBO_Convenanten",
        "LBO_Balanscheck",
        "LBO_Exit_EV_Jaar5",
        "LBO_Exit_Equity_Jaar5",
        "Indicatieve_MoIC",
        "Indicatieve_IRR_Pct",
        "LBO_Downside_IRR_Pct",
        "LBO_Downside_MoIC",
        "LBO_Downside_Convenanten",
        "LBO_Upside_IRR_Pct",
        "LBO_Screening_IRR_Pct",
        "LBO_Screening_MoIC",
        "LBO_Screening_Convenanten",
        "LBO_Stress_IRR_Pct",
        "LBO_Stress_Laagste_DSCR",
        "LBO_Stress_Convenanten",
        "Debt_Capacity_Multiple",
        "Debt_Capacity_EUR",
        "Debt_Capacity_Bindend",
        "Debt_Capacity_Status",
        "ATP_Senior_Multiple",
        "ATP_Max_Entry_Multiple",
        "ATP_Max_EV",
        "ATP_IRR_Pct",
        "ATP_Headroom_Pct",
        "ATP_Max_Equity_Price",
        "ATP_Status",
        "ATP_AI_Max_Entry_Multiple",
        "ATP_AI_Max_EV",
        "ATP_AI_Headroom_Pct",
        "ATP_AI_Status",
        "LBO_IRR_Exact_Pct",
        "LBO_MoIC_Exact",
        "LBO_Forecast_Groei_Pct",
        "LBO_Assumptie_Bron",
        "LBO_Snapshot_Naam",
        "LBO_Snapshot_Datum",
        "LBO_Snapshot_Status",
        "LBO_Assumpties",
        "LBO_Assumptie_Vlaggen",
        "LBO_Driver_Pack",
        "LBO_Jaren",
        "LBO_Integriteit",
        "LBO_Scenarios",
        "Eigen_Vermogen",
        "Balanstotaal",
        "Overgedragen_Resultaat",
        "Normalisatie_Toelichting",
        "Normalisatie_Voorstellen",
        "Commissaris_Oordeel",
        "Buitenbalans_Verplichtingen",
        "Red_Flags",
        "Aantal_Hoge_Vlaggen",
        "Aantal_Middel_Vlaggen",
        "Red_Flag_Lijst",
        "Eigendom",
        "Kwalitatief_LBO_Oordeel",
        "AI_Business_Model",
        "AI_Normalisaties",
        "LBO_Adjustments",
        "AI_Red_Flags",
        "AI_Eigendom",
        "AI_Buitenbalans",
        "AI_Investment_Thesis",
        "AI_DD_Vragen",
        "Bronbestand",
        "Gebruikt_Model",
    ]
    for kol in OPTIONELE_TEKSTKOLOMMEN:
        if kol not in df:
            df[kol] = ""
    # Structured AI output (text pass and second pass): lists, empty without Gemini
    for kol in OPTIONELE_AI_LIJSTEN:
        if kol not in df:
            df[kol] = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    if "AI_Eigendom" not in df:
        df["AI_Eigendom"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    if "Eigendom" not in df:
        df["Eigendom"] = labels.OWNERSHIP_TYPES["onbekend"]
    ontbrekend = [kol for kol in volgorde if kol not in df]
    if ontbrekend:
        raise ValueError(f"Kolommen ontbreken in het resultaat: {', '.join(ontbrekend)}")
    return df[volgorde]
