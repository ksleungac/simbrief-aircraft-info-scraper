import os, sys, json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import equip_codes

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "SimBrief_B777_Fleet.xlsx")
with open(os.path.join(HERE, "fleet.json"), encoding="utf-8") as f:
    FLEET = json.load(f)

# ---------------------------------------------------------------------------
# Paste cards: one airframe's fields in the exact SimBrief editor order, so the
# manual paste is a top-to-bottom checklist instead of decoding a wide row.
# Rendered as the "Paste Cards" tab, and printable via `--card [REG ...]`.
# ---------------------------------------------------------------------------
def _cardval(rec, key):
    v = rec.get(key)
    if v is None or v == "":  return "(blank)"
    if v == "(SB default)":   return "leave default"
    return str(v)

# (display label, fleet.json key) in the order the SimBrief airframe editor lists them
CARD_RESEARCHED = [
    ("Base Type","Base Type"), ("Registration","Registration"), ("Name","Airframe Name"),
    ("SELCAL","SELCAL"), ("Mode-S / Hex","Hex"), ("Equipment (10a)","Equip 10a"),
    ("Transponder (10b)","Xpdr 10b"), ("PBN","PBN"), ("Units","Units"),
    ("Max Passengers","Max Pax"), ("MZFW","MZFW"), ("MTOW","MTOW"), ("MLW","MLW"),
    ("Max Fuel","Max Fuel"), ("Thrust (flat rating)","Thrust lbf"),
]
# fixed on every airframe (literals); Fuel Factor / Cost Index still read from the row
CARD_FIXED_LITERAL = [
    ("Cruise Level Offset","0"), ("Service Ceiling","FL431"),
    ("Climb/Cruise/Descent","leave default"), ("Pax / Bag weight","leave default"),
]
CARD_YOU = [("OEW","OEW"), ("Max Cargo","Max Cargo")]

def card_rows(rec):
    """-> [(label, value)] with ('__sec__', title) separators, in editor order."""
    rows = [(lbl, _cardval(rec, key)) for lbl, key in CARD_RESEARCHED]
    rows.append(("__sec__", "fixed - same on every airframe"))
    rows.append(("Fuel Factor", _cardval(rec, "Fuel Factor")))
    rows.append(("Cost Index",  _cardval(rec, "Cost Index")))
    rows += CARD_FIXED_LITERAL
    rows.append(("__sec__", "you - from in-sim loadout"))
    rows += [(lbl, _cardval(rec, key)) for lbl, key in CARD_YOU]
    return rows

def card_text(rec):
    title = f"{rec.get('Airframe Name') or '?'}  {rec.get('Registration') or '?'}"
    W = 54
    out = ["", "--- " + title + " " + "-" * max(3, W - len(title) - 5)]
    for lbl, val in card_rows(rec):
        if lbl == "__sec__":
            out.append("-- " + val + " " + "-" * max(2, W - len(val) - 4))
        else:
            out.append(f"{lbl} {'.' * max(2, 22 - len(lbl))} {val}")
    return "\n".join(out + ["-" * W])

if "--card" in sys.argv:                       # print card(s) to terminal and exit
    i = sys.argv.index("--card")
    want = [a.upper() for a in sys.argv[i+1:]] or [r.get("Registration") for r in FLEET]
    for reg in want:
        rec = next((r for r in FLEET if (r.get("Registration") or "").upper() == reg), None)
        print(card_text(rec) if rec else f"no such reg in fleet.json: {reg}")
    sys.exit(0)

wb = openpyxl.Workbook()

hdr_font   = Font(bold=True, color="FFFFFF", size=11)
title_font = Font(bold=True, size=14)
note_font  = Font(italic=True, color="555555", size=9)
thin = Side(style="thin", color="BBBBBB")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center", wrap_text=True)
left   = Alignment(horizontal="left", vertical="center", wrap_text=True)

C_INPUT = PatternFill("solid", fgColor="2E7D32")
C_TRACK = PatternFill("solid", fgColor="616161")
C_ME    = PatternFill("solid", fgColor="1565C0")
C_YOU   = PatternFill("solid", fgColor="E65100")
YOU_CELL = PatternFill("solid", fgColor="FFF3E0")
ZEBRA   = PatternFill("solid", fgColor="F5F7FA")

# ============================ Fleet ============================
ws = wb.active; ws.title = "Fleet"
# (header, width, owner)
cols = [
    ("Registration",13,"input"), ("Status",15,"track"), ("Operator",16,"me"),
    ("Base Type",10,"me"), ("Variant",11,"me"), ("Airframe Name",18,"me"),
    ("Line#/Deliv",11,"me"), ("Hex",9,"me"), ("SELCAL",9,"me"),
    ("Equip 10a",14,"me"), ("Xpdr 10b",12,"me"), ("PBN",12,"me"),
    ("Eng (real)",12,"me"), ("Eng (sim/FF)",12,"me"), ("Thrust lbf",10,"me"),
    ("Units",7,"me"), ("OEW",10,"you"), ("MZFW",10,"me"), ("MTOW",10,"me"),
    ("MLW",10,"me"), ("Max Fuel",10,"me"), ("Max Pax",9,"me"), ("Max Cargo",10,"you"),
    ("Fuel Factor",11,"me"), ("Cost Index",10,"me"), ("Source/Notes",42,"me"),
    ("Review",20,"track"),   # machine signal: enum codes; blank = auto-complete (OEW/Cargo aside)
]
owner_fill = {"input":C_INPUT,"track":C_TRACK,"me":C_ME,"you":C_YOU}
ws.cell(1,1,"SimBrief B777 Fleet - staging worksheet").font = title_font
ws.cell(2,1,"Give me a registration -> I fill blue/green -> you fill orange (OEW, Max Cargo) -> paste row into SimBrief.").font = note_font
HDR = 3
for ci,(name,width,owner) in enumerate(cols, start=1):
    c = ws.cell(HDR,ci,name); c.font=hdr_font; c.fill=owner_fill[owner]; c.alignment=center; c.border=border
    ws.column_dimensions[get_column_letter(ci)].width = width
ws.freeze_panes = "C4"

last = HDR
for ri, rec in enumerate(FLEET, start=HDR+1):
    last = ri
    for ci,(name,width,owner) in enumerate(cols, start=1):
        val = ", ".join(rec.get("review") or []) if name == "Review" else rec.get(name)
        c = ws.cell(ri,ci, val); c.alignment=left; c.border=border
        if owner == "you":
            c.fill = YOU_CELL
for r in range(last+1, HDR+60):           # blank staging rows
    for ci,(_,_,owner) in enumerate(cols, start=1):
        c = ws.cell(r,ci); c.border=border; c.alignment=left
        if owner=="you": c.fill = YOU_CELL

DataValidation
for dv,colL in [(DataValidation(type="list",formula1='"Auto,Review,Filled,Pasted"',allow_blank=True),"B"),
                (DataValidation(type="list",formula1='"B772,B77L,B77W,B77F"',allow_blank=True),"D"),
                (DataValidation(type="list",formula1='"KG,LB"',allow_blank=True),"P")]:
    ws.add_data_validation(dv); dv.add(f"{colL}{HDR+1}:{colL}{HDR+59}")

lr = HDR+61
ws.cell(lr,1,"Legend:").font = Font(bold=True)
for i,(txt,fill) in enumerate([("Green = you key in (registration)",C_INPUT),("Gray = status",C_TRACK),
        ("Blue = I fill (web / static / edi-gla)",C_ME),("Orange = you fill (OEW, Max Cargo)",C_YOU)]):
    c = ws.cell(lr+1+i,1,txt); c.fill=fill; c.font=Font(color="FFFFFF",bold=True)

# ======================= 777 Reference =======================
ref = wb.create_sheet("777 Reference")
ref.cell(1,1,"B777 static (kg, nominal max) + sim-aligned thrust").font = title_font
for ci,name in enumerate(["Base","Variant","MTOW","MLW","MZFW","Max Fuel","Thrust/eng (lbf, FF)"], start=1):
    c=ref.cell(3,ci,name); c.font=hdr_font; c.fill=C_ME; c.alignment=center; c.border=border
    ref.column_dimensions[get_column_letter(ci)].width = 16
ref.column_dimensions["G"].width = 36
for ri,row in enumerate([
    ("B772","777-200ER",297560,213180,195040,138900,"GE90-94B 93700 / PW4090 90000 / Trent892 91450"),
    ("B772","777-200 (basic)",247210,213180,195040,94240,"same 3 options"),
    ("B77W","777-300ER",351535,251290,237683,145540,"GE90-115B 115300"),
    ("B77L","777-200LR",347815,223168,209556,145540,"GE90-110B1 110100"),
    ("B77F","777F",347815,260816,248115,145540,"GE90-110B1 110100")], start=4):
    for ci,val in enumerate(row, start=1):
        c=ref.cell(ri,ci,val); c.border=border; c.alignment=center
ref.cell(10,1,"basic 777-200 = 200ER with reduced MTOW + Max Fuel only.").font = note_font
ref.cell(11,1,"Units rule: LB for US/Canada/Japan regs, KG everyone else. Service ceiling FL431, cruise offset 0.").font = note_font

# ========================= Field Map =========================
fm = wb.create_sheet("Field Map")
fm.cell(1,1,"SimBrief airframe fields -> source").font = title_font
for ci,name in enumerate(["SimBrief field","Filled by","Source / note"], start=1):
    c=fm.cell(3,ci,name); c.font=hdr_font; c.fill=C_ME; c.alignment=center; c.border=border
for ci,w in enumerate([24,12,72], start=1): fm.column_dimensions[get_column_letter(ci)].width=w
for ri,row in enumerate([
    ("Base Type","Me","ICAO type from reg lookup (rzjets/airfleets/airport-data)"),
    ("Airframe Name","Me","FF {airline ICAO} [ER] {cabin}, e.g. FF CPA C45Y291"),
    ("Registration","You","the input key"),
    ("Hex Code","Me","airport-data.com/aircraft/{REG}.html"),
    ("SELCAL","Me","edi-gla remarks SEL/ (search REG/<reg>)"),
    ("Equip 10a/10b/PBN","Me","edi-gla if a modern-format plan exists; else SimBrief base-type default"),
    ("Engine / Thrust","Me","real engine (rzjets); thrust = FlightFactor-modelled rating (verified lbf)"),
    ("Units","Me","rule: LB for US/CA/JP, else KG"),
    ("OEW","You","operator/config specific"),
    ("MZFW/MTOW/MLW/Max Fuel","Me","static 777 table (nominal)"),
    ("Max Pax","Me","cabin config from flyings.net/airfleets"),
    ("Max Cargo","You","config specific"),
    ("Fuel Factor","Me","P00 (pending in-sim calibration)"),
    ("Cost Index","Me","SimBrief base-type default (varies by airline)")], start=4):
    for ci,val in enumerate(row, start=1):
        c=fm.cell(ri,ci,val); c.border=border; c.alignment=left
        if ci==2:
            c.fill = C_YOU if val=="You" else C_ME; c.font=Font(color="FFFFFF",bold=True); c.alignment=center

# ====================== Equipment Codes ======================
ec = wb.create_sheet("Equipment Codes")
ec.column_dimensions["A"].width = 9
ec.column_dimensions["B"].width = 84
ec.cell(1,1,"ICAO Equipment Code Reference  (Doc 4444, post-2012 format)").font = title_font
ec.cell(2,1,"Verified vs FAA/ICAO conventions, Jun 2026. Filed order in 10b: transponder, then ADS-B, then ADS-C.").font = note_font
r = 4
for title, color, table in [
    ("Item 10a - Radio comm / navigation / approach aids & capabilities", "1565C0", equip_codes.EQUIP_10A),
    ("Item 10b - Surveillance (SSR transponder / ADS-B / ADS-C)",          "00695C", equip_codes.EQUIP_10B),
    ("Item 18  PBN/ - Performance-based navigation specifications",        "6A1B9A", equip_codes.PBN_CODES),
]:
    ec.merge_cells(start_row=r,start_column=1,end_row=r,end_column=2)
    c=ec.cell(r,1,title); c.fill=PatternFill("solid",fgColor=color); c.font=Font(bold=True,color="FFFFFF",size=11); c.alignment=left
    r += 1
    for ci,h in enumerate(["Code","Meaning"], start=1):
        c=ec.cell(r,ci,h); c.font=Font(bold=True); c.fill=PatternFill("solid",fgColor="EEEEEE")
        c.border=border; c.alignment=center if ci==1 else left
    r += 1
    for i,(code,meaning) in enumerate(table.items()):
        cc=ec.cell(r,1,code); cc.font=Font(bold=True); cc.alignment=center; cc.border=border
        cm=ec.cell(r,2,meaning); cm.alignment=left; cm.border=border
        if i % 2: cc.fill=ZEBRA; cm.fill=ZEBRA
        r += 1
    r += 1
ec.cell(r,1,"PBN note: specs are NOT nested by number. RNAV10/RNP10 is oceanic (GNSS or time-limited INS); "
            "RNAV5 is continental (may use DME/DME). A tighter spec covers a looser one only within the same "
            "domain (RNP4 => RNP10; RNAV1 => RNAV2/RNAV5). File what's approved - don't infer the ladder.").font = note_font

# ======================== Paste Cards ========================
pc = wb.create_sheet("Paste Cards")
pc.column_dimensions["A"].width = 24
pc.column_dimensions["B"].width = 30
pc.cell(1,1,"Paste Cards - type each row into SimBrief's airframe editor, top to bottom").font = title_font
pc.cell(2,1,"Blue = airframe header. Gray = fixed constant (same every time). "
            "Orange = you fill (from in-sim loadout).").font = note_font
r = 4
for rec in FLEET:
    pc.merge_cells(start_row=r,start_column=1,end_row=r,end_column=2)
    h = pc.cell(r,1, f"{rec.get('Airframe Name') or '?'}   {rec.get('Registration')}")
    h.fill=C_ME; h.font=Font(bold=True,color="FFFFFF",size=11); h.alignment=left; h.border=border
    pc.cell(r,2).border = border
    r += 1
    section = "air"
    for lbl, val in card_rows(rec):
        if lbl == "__sec__":
            section = "fixed" if val.startswith("fixed") else "you"
            pc.merge_cells(start_row=r,start_column=1,end_row=r,end_column=2)
            s = pc.cell(r,1, val); s.alignment=left; s.border=border
            s.fill = C_TRACK if section=="fixed" else C_YOU
            s.font = Font(italic=True,color="FFFFFF",size=9)
            pc.cell(r,2).border = border
            r += 1; continue
        lc = pc.cell(r,1,lbl); lc.alignment=left; lc.border=border; lc.font=Font(size=10,color="555555")
        vc = pc.cell(r,2,val); vc.alignment=left; vc.border=border; vc.font=Font(size=10,bold=True)
        if section == "you" or val == "(blank)":
            vc.fill = YOU_CELL
        r += 1
    r += 1                                      # spacer between cards

wb.save(OUT)
print("WROTE", OUT, "| fleet rows:", len(FLEET), "| tabs: Fleet/Reference/Field Map/Equipment Codes/Paste Cards")
