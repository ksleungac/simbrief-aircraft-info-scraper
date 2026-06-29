"""
ICAO flight-plan equipment code reference (Doc 4444, post-2012 format).
  EQUIP_10A : Item 10a - radio comm / nav / approach aid equipment & capabilities
  EQUIP_10B : Item 10b - surveillance (SSR / ADS) equipment
  PBN_CODES : Item 18  - PBN/ navigation specifications
Use to decode/build SimBrief airframe equipment strings.
B-HND example: 10a filed blank ("Not available"), 10b = S (Mode S, alt + ID).
"""

EQUIP_10A = {
    "N":  "No COM/NAV/approach equipment for the route, or unserviceable",
    "S":  "Standard: VHF RTF + VOR + ILS",
    "A":  "GBAS landing system",
    "B":  "LPV (APV with SBAS)",
    "C":  "LORAN C",
    "D":  "DME",
    "E1": "FMC WPR ACARS",
    "E2": "D-FIS ACARS",
    "E3": "PDC ACARS",
    "F":  "ADF",
    "G":  "GNSS",
    "H":  "HF RTF",
    "I":  "Inertial navigation",
    "J1": "CPDLC ATN VDL Mode 2",
    "J2": "CPDLC FANS 1/A HFDL",
    "J3": "CPDLC FANS 1/A VDL Mode A",
    "J4": "CPDLC FANS 1/A VDL Mode 2",
    "J5": "CPDLC FANS 1/A SATCOM (INMARSAT)",
    "J6": "CPDLC FANS 1/A SATCOM (MTSAT)",
    "J7": "CPDLC FANS 1/A SATCOM (Iridium)",
    "K":  "MLS",
    "L":  "ILS",
    "M1": "ATC RTF SATCOM (INMARSAT)",
    "M2": "ATC RTF (MTSAT)",
    "M3": "ATC RTF (Iridium)",
    "O":  "VOR",
    "P1": "Reserved for RCP (required communication performance)",
    "P2": "Reserved for RCP",
    "P3": "Reserved for RCP",
    "R":  "PBN approved (see PBN/ in field 18)",
    "T":  "TACAN",
    "U":  "UHF RTF",
    "V":  "VHF RTF",
    "W":  "RVSM approved",
    "X":  "MNPS / NAT HLA approved",
    "Y":  "VHF 8.33 kHz channel spacing capable",
    "Z":  "Other equipment/capabilities (see COM/ NAV/ DAT/ in field 18)",
}

EQUIP_10B = {
    "N":  "Nil - no surveillance equipment",
    "A":  "Transponder Mode A (4096 codes)",
    "C":  "Transponder Mode A + Mode C",
    "E":  "Mode S: ident + pressure-altitude + extended squitter (ADS-B)",
    "H":  "Mode S: ident + pressure-altitude + enhanced surveillance",
    "I":  "Mode S: ident, no pressure-altitude",
    "L":  "Mode S: ident + alt + extended squitter (ADS-B) + enhanced surveillance",
    "P":  "Mode S: pressure-altitude, no ident",
    "S":  "Mode S: ident + pressure-altitude",          # <- B-HND
    "X":  "Mode S: neither ident nor pressure-altitude",
    "B1": "ADS-B 'out', dedicated 1090 MHz",
    "B2": "ADS-B 'out' + 'in', dedicated 1090 MHz",
    "U1": "ADS-B 'out' using UAT",
    "U2": "ADS-B 'out' + 'in' using UAT",
    "V1": "ADS-B 'out' using VDL Mode 4",
    "V2": "ADS-B 'out' + 'in' using VDL Mode 4",
    "D1": "ADS-C with FANS 1/A capabilities",
    "G1": "ADS-C with ATN capabilities",
}

PBN_CODES = {
    "A1": "RNAV 10 (RNP 10)",
    "B1": "RNAV 5 - all permitted sensors",
    "B2": "RNAV 5 - GNSS",
    "B3": "RNAV 5 - DME/DME",
    "B4": "RNAV 5 - VOR/DME",
    "B5": "RNAV 5 - INS or IRS",
    "B6": "RNAV 5 - LORAN C",
    "C1": "RNAV 2 - all permitted sensors",
    "C2": "RNAV 2 - GNSS",
    "C3": "RNAV 2 - DME/DME",
    "C4": "RNAV 2 - DME/DME/IRU",
    "D1": "RNAV 1 - all permitted sensors",
    "D2": "RNAV 1 - GNSS",
    "D3": "RNAV 1 - DME/DME",
    "D4": "RNAV 1 - DME/DME/IRU",
    "L1": "RNP 4",
    "O1": "Basic RNP 1 - all permitted sensors",
    "O2": "Basic RNP 1 - GNSS",
    "O3": "Basic RNP 1 - DME/DME",
    "O4": "Basic RNP 1 - DME/DME/IRU",
    "S1": "RNP APCH",
    "S2": "RNP APCH with BARO-VNAV",
    "T1": "RNP AR APCH with RF (special authorization)",
    "T2": "RNP AR APCH without RF (special authorization)",
}

def decode_10a(s):  return _decode(s, EQUIP_10A)
def decode_10b(s):  return _decode(s, EQUIP_10B)
def decode_pbn(s):  return _decode(s, PBN_CODES)

def _decode(s, table):
    """Greedy 2-then-1 char tokenizer over an equipment string."""
    s = s.replace(" ", "").upper(); out = []; i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i:i+2] in table:
            out.append((s[i:i+2], table[s[i:i+2]])); i += 2
        elif s[i] in table:
            out.append((s[i], table[s[i]])); i += 1
        else:
            out.append((s[i], "?? unknown")); i += 1
    return out
