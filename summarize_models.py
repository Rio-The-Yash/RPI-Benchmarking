import csv, glob, sys
from statistics import mean

directory = sys.argv[1] if len(sys.argv) > 1 else "results"
rows = []

for path in sorted(glob.glob(f"{directory}/*_all_profiles.csv")):
    for row in csv.DictReader(open(path, newline="")):
        profile = (row.get("profile") or "").strip()
        if not profile or "TOTAL" in profile.upper():
            continue
        if not (row.get("status") or "").strip():
            continue
        rows.append(row)

if not rows:
    sys.exit("no rows found")

def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def avg(group, key):
    vals = [fnum(r.get(key)) for r in group]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None

def fmt(v, d=2):
    return "-" if v is None else f"{v:.{d}f}"

models = sorted({r["model"] for r in rows})

print()
print("| Model | Runs | OK | Err | Trunc | Out tok/s | TPOT ms | TTFT ms | Prompt tok/s | RAM MB | Temp C | Power W | J/token |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

for model in models:
    group = [r for r in rows if r["model"] == model]
    ok = sum(1 for r in group if r["status"] in ("success", "truncated"))
    err = sum(1 for r in group if r["status"] == "error")
    trunc = sum(1 for r in group if r["truncated"] == "True")
    jt = [fnum(r["estimated_energy_j"]) / fnum(r["output_tokens"])
          for r in group
          if fnum(r.get("estimated_energy_j")) and fnum(r.get("output_tokens"))]
    print("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
        model, len(group), ok, err, trunc,
        fmt(avg(group, "output_tps")), fmt(avg(group, "tpot_ms"), 1),
        fmt(avg(group, "ttft_ms"), 0), fmt(avg(group, "prompt_tps")),
        fmt(avg(group, "ram_peak_mb"), 0), fmt(avg(group, "cpu_temp_peak_c"), 1),
        fmt(avg(group, "power_avg_w")), fmt(mean(jt) if jt else None)))
