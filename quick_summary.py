import csv, glob, sys
from statistics import mean

files = sorted(glob.glob(sys.argv[1] + "/*_all_profiles.csv")) if len(sys.argv) > 1 else sorted(glob.glob("results/*_all_profiles.csv"))
rows = []
for path in files:
    for row in csv.DictReader(open(path, newline="")):
        profile = (row.get("profile") or "").strip()
        if not profile or "TOTAL" in profile.upper() or not (row.get("status") or "").strip():
            continue
        rows.append(row)
if not rows:
    sys.exit("no rows found")

def avg(key):
    vals = [float(r[key]) for r in rows if r.get(key) not in ("", None)]
    return mean(vals) if vals else float("nan")

jt = [float(r["estimated_energy_j"]) / float(r["output_tokens"]) for r in rows
      if r.get("estimated_energy_j") not in ("", None) and float(r.get("output_tokens") or 0)]

print(f"\nModel: {rows[0]['model']}   quant: {rows[0].get('quantization')}   rows: {len(rows)}")
print(f"success: {sum(1 for r in rows if r['status']=='success')}   "
      f"truncated: {sum(1 for r in rows if r['truncated']=='True')}   "
      f"throttled: {any((r.get('throttle_occurred') or '').lower()=='true' for r in rows)}")
print(f"output tok/s  {avg('output_tps'):8.2f}")
print(f"prompt tok/s  {avg('prompt_tps'):8.2f}")
print(f"TPOT ms       {avg('tpot_ms'):8.1f}")
print(f"TTFT ms       {avg('ttft_ms'):8.0f}")
print(f"peak RAM MB   {avg('ram_peak_mb'):8.0f}")
print(f"peak temp C   {avg('cpu_temp_peak_c'):8.1f}")
print(f"avg power W   {avg('power_avg_w'):8.2f}")
print(f"J per token   {mean(jt) if jt else float('nan'):8.2f}")

print("\nper-profile output tok/s:")
seen = {}
for r in rows:
    seen.setdefault(r["profile"], []).append(float(r["output_tps"]))
for profile, vals in seen.items():
    print(f"  {profile:28} {mean(vals):6.2f}  (n={len(vals)})")
