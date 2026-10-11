"""Builds SYNTHETIC seed data for Kaarigar (sample records + SOPs written by Team Sankalp,
based on general machine-shop practice; no real company data)."""
import json
from pathlib import Path

OUT = Path("data/seed")
(OUT / "sops").mkdir(parents=True, exist_ok=True)

# (date, machine, product, defect_type, severity, description, root_cause, 6M category, fix,
#  verified, supplier, batch, downtime_h, scrap_qty)
R = [
 ("2026-09-08","M2","Machine screw MS-8","burr","minor","Burrs on thread start","Worn threading insert","Machine","Replaced threading insert; set insert life to 400 parts",True,"Supplier C","C-0901",0,18),
 ("2026-09-11","M1","Flange nut FN-24","dimension_out_of_tolerance","major","Bore oversize by 0.05 mm","Wrong tool offset after insert change","Man","Corrected offset; added first-piece check after every insert change",True,"Supplier A","A-0905",0,22),
 ("2026-09-14","M3","Sprocket 28T","chatter_marks","major","Chatter marks on tooth flanks","Hob arbor bearing play","Machine","Replaced hob arbor bearing; checked runout",True,"Supplier A","A-0905",6,35),
 ("2026-09-16","M5","Round bar blanks","rough_cut","minor","Rough, angled saw cut faces","Blade tension low","Method","Re-tensioned blade; added tension check to start-up list",True,"Supplier B","B-0912",0,6),
 ("2026-09-18","M4","Keyway sleeve","dimension_out_of_tolerance","major","Keyway depth inconsistent","Loose clapper box on shaper","Machine","Tightened clapper box; adjusted gibs",True,"Supplier A","A-0905",2,14),
 ("2026-09-20","IN","EN8 round bar","rust","major","Surface rust and pitting on bar ends at receiving","Bars stored wet at supplier, no oiling","Material","Rejected 12 bars; informed supplier",True,"Supplier B","B-0912",0,12),
 ("2026-09-22","M2","Machine screw MS-8","scratch","minor","Scratches on shank","Chips trapped in collet","Method","Cleaned collet; added air blow before loading",True,"Supplier C","C-0901",0,9),
 ("2026-09-24","M1","Flange nut FN-24","burr","minor","Burr on flange edge","Chamfer tool chipped","Machine","Replaced chamfer tool",True,"Supplier A","A-0920",0,11),
 ("2026-09-25","M3","Sprocket 15T","discoloration","minor","Blue heat tint on teeth","Low coolant flow at hob","Machine","Cleaned coolant nozzle; topped up coolant",True,"Supplier A","A-0920",0,8),
 ("2026-09-27","IN","EN19 round bar","crack","critical","Hairline cracks at bar ends","Shearing cracks from supplier cutting","Material","Quarantined batch; cut 20 mm off ends; supplier informed",True,"Supplier C","C-0927",0,7),
 ("2026-09-28","IN","EN8 round bar","rust","major","Heavy rust patches on cut faces","Bars stored wet at supplier, no oiling","Material","Rejected 9 bars; requested oiled supply",True,"Supplier B","B-0912",0,9),
 ("2026-09-29","M2","Machine screw MS-8","dimension_out_of_tolerance","major","Thread pitch diameter undersize","Thermal growth at shift start","Environment","Added 15-minute warm-up before first piece",True,"Supplier C","C-0927",0,16),
 ("2026-09-30","M4","Keyway sleeve","poor_surface_finish","minor","Torn surface on keyway walls","Blunt shaper tool","Machine","Reground shaper tool",True,"Supplier A","A-0920",0,10),
 ("2026-10-01","M4","Keyway sleeve","dimension_out_of_tolerance","critical","Keyway off-centre, parts rejected","Ram / spindle misalignment","Machine","Re-aligned ram and fixture with dial indicator",True,"Supplier A","A-0920",2,27),
 ("2026-10-02","M5","Round bar blanks","burr","minor","Heavy exit burrs on saw cuts","Band saw blade worn","Machine","Replaced blade; logged blade change",True,"Supplier B","B-0930",2,15),
 ("2026-10-02","M1","Flange nut FN-24","poor_surface_finish","major","Chatter-like marks and poor finish on turned faces","Spindle bearing wear (vibration high, load normal)","Machine","Replaced spindle bearings; vibration back to normal",True,"Supplier A","A-1003",2,31),
 ("2026-10-03","M1","Flange nut FN-24","burr","major","Burrs and scratches on bore","Cutting insert worn beyond life","Machine","Replaced insert; reduced insert life to 300 parts",True,"Supplier A","A-1003",2,24),
 ("2026-10-04","M2","Machine screw MS-8","discoloration","major","Burn marks and discoloration on threads","Coolant pump blocked","Machine","Cleaned pump and filter; checked flow",True,"Supplier C","C-0927",0,20),
 ("2026-10-05","M3","Sprocket 28T","dimension_out_of_tolerance","minor","Tooth profile slightly off","Hob not re-sharpened on schedule","Method","Re-sharpened hob; added sharpening log",True,"Supplier A","A-1003",0,6),
 ("2026-10-06","IN","EN8 round bar","rust","major","Rust and pitting on incoming bars","Bars stored wet at supplier, no oiling","Material","Rejected 15 bars; escalated to supplier owner",True,"Supplier B","B-0912",0,15),
 ("2026-10-06","M2","Machine screw MS-8","burr","minor","Burrs on slot","Worn slotting cutter","Machine","Replaced slotting cutter",True,"Supplier C","C-1005",0,8),
 ("2026-10-07","M1","Flange nut FN-24","dimension_out_of_tolerance","minor","Flange thickness at upper limit","Gauge not calibrated","Measurement","Calibrated gauge; added monthly calibration",True,"Supplier A","A-1003",0,5),
 ("2026-10-07","M5","Round bar blanks","rough_cut","minor","Wavy cut surface","Feed rate too high for EN19","Method","Reduced feed for EN19; posted settings card",True,"Supplier C","C-1005",0,4),
 ("2026-10-08","M3","Sprocket 15T","burr","minor","Burrs on tooth tips","Deburring step skipped by new operator","Man","Retrained operator; added deburr checkbox",True,"Supplier A","A-1003",0,12),
 ("2026-10-08","M4","Keyway sleeve","scratch","minor","Scratch marks from handling","Parts stacked without separators","Method","Introduced separator trays",True,"Supplier A","A-1003",0,3),
 ("2026-10-09","M2","Machine screw MS-8","dimension_out_of_tolerance","minor","Length variation","Bar stop loose","Machine","Tightened bar stop",True,"Supplier C","C-1005",0,7),
 ("2026-10-09","IN","Aluminium block","pit","minor","Small pit on block face at receiving","Casting porosity at supplier","Material","Accepted with concession after customer approval",True,"Supplier D","D-0101",0,0),
 ("2026-10-10","M1","Flange nut FN-24","scratch","minor","Light scratches on flange face","Chips not cleared from chuck jaws","Method","Cleaned jaws; reminded operators",False,"Supplier A","A-1003",0,4),
]
records = [dict(defect_id=f"D{i+1:03d}", date=r[0], machine_id=r[1], product=r[2], defect_type=r[3],
                severity=r[4], description=r[5], root_cause=r[6], category_6m=r[7], fix=r[8],
                fix_verified=r[9], supplier=r[10], batch=r[11], downtime_hours=r[12], scrap_qty=r[13],
                synthetic=True) for i, r in enumerate(R)]
(OUT / "past_defects.json").write_text(json.dumps(records, indent=2))

SOPS = {
"SOP-01_cnc_lathe_daily_checks.md": """# SOP-01 CNC Lathe Daily Checks (M1, M2) — SAMPLE SOP (synthetic)
1. Warm up spindle 15 minutes before first piece (thermal growth causes undersize threads).
2. First-piece inspection after every start-up and every insert change: bore, length, thread, finish.
3. Insert life: flange nut FN-24 = 300 parts; machine screw MS-8 threading insert = 400 parts.
4. Clean chuck jaws and collets with air blow before loading (prevents scratches).
5. Vibration: normal 1.5-2.2 mm/s. Above 3.0 mm/s with normal load -> stop and inform maintenance
   (suspect spindle bearings, see SOP-02). Poor surface finish or chatter marks often appear first.
6. Record every defect in Kaarigar with machine, part, supplier and batch.""",
"SOP-02_spindle_bearing_inspection.md": """# SOP-02 Spindle Bearing Inspection & Replacement — SAMPLE SOP (synthetic)
Signs of bearing wear: vibration rising over hours without a rise in cutting load, spindle running
2-6 °C warmer than normal, humming/rumbling noise, chatter marks and poor surface finish on parts.
Steps: 1) Stop production on the machine. 2) Check spindle runout with dial indicator (limit 0.01 mm).
3) Check lubrication level. 4) If runout or noise persists, replace bearings as a set.
5) Run-in 30 minutes, then first-piece inspection. 6) Re-check vibration returns to normal.
Prevention: grease every 500 running hours; trend vibration weekly.""",
"SOP-03_coolant_system.md": """# SOP-03 Coolant System Maintenance — SAMPLE SOP (synthetic)
Signs of coolant failure: temperature rising quickly without vibration change, discoloration / blue
heat tint or burn marks on parts, smoke at the cutting zone.
Daily: check level and concentration (5-8%), check nozzle aims at the cutting zone.
Weekly: clean pump strainer and filters. If flow is weak: clean pump, check for blocked lines.""",
"SOP-04_incoming_material_inspection.md": """# SOP-04 Incoming Raw Material Inspection — SAMPLE SOP (synthetic)
For every delivery: record supplier, material grade (e.g. EN8, EN19), size, heat/batch number.
Visual check of bar ends and surface (photograph with Kaarigar):
- Light surface rust removable by wire brush: ACCEPT, oil and store dry.
- Pitting, heavy rust, scale flakes: REJECT or return to supplier.
- Cracks at bar ends: QUARANTINE; cut 20 mm and re-check; inform supplier.
- Rough/angled saw cuts or flame-cut dross: accept only if machining allowance is enough.
Repeat issues from the same supplier/batch: escalate to supplier and purchase.""",
"SOP-05_gear_hobbing_chatter.md": """# SOP-05 Gear Hobbing — Chatter Prevention (M3) — SAMPLE SOP (synthetic)
Chatter marks on tooth flanks: check hob arbor bearing play and runout first, then hob sharpness,
work-holding rigidity, and feed. Re-sharpen hob per sharpening log. Deburr all tooth tips.""",
}
for name, text in SOPS.items():
    (OUT / "sops" / name).write_text(text + "\n")

PARTS = {"rules": [
 {"prefix": "metal_nut_", "product": "Flange nut FN-24", "machine_id": "M1", "material": "EN8 steel",
  "supplier": "Supplier A", "batch": "A-1003"},
 {"prefix": "screw_", "product": "Machine screw MS-8", "machine_id": "M2", "material": "EN1A steel",
  "supplier": "Supplier C", "batch": "C-1005"},
], "synthetic": True}
(OUT / "parts.json").write_text(json.dumps(PARTS, indent=2))
print(f"Seed data: {len(records)} past defects, {len(SOPS)} SOPs, parts metadata -> {OUT}")