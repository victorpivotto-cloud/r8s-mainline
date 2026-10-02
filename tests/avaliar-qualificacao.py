#!/usr/bin/env python3
"""Check completeness and anomalies in the finite S20 idle qualification log."""
import csv
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
metadata = lines[0]
duration = int(re.search(r"duration=(\d+)", metadata).group(1))
interval = int(re.search(r"interval=(\d+)", metadata).group(1))
rows = list(csv.DictReader((line for line in lines if not line.startswith("#")), delimiter="\t"))
if not rows:
    sys.exit("INDETERMINADO: nenhuma amostra")
issues = []
complete = any(line.startswith("# finished=") and "completed=yes" in line for line in lines)
uptimes = [int(row["uptime_s"]) for row in rows]
elapsed = uptimes[-1] - uptimes[0]
if not complete:
    issues.append("coleta em andamento ou interrompida")
if duration != 86400 or elapsed < 86400:
    issues.append("menos de 24 horas completas")
if len({row["boot_id"] for row in rows}) != 1:
    issues.append("boot ID mudou")
gaps = [b - a for a, b in zip(uptimes, uptimes[1:])]
if any(gap <= 0 or gap > interval + 15 for gap in gaps):
    issues.append("intervalo de amostragem irregular")
fields = ["battery_pct", "battery_mC", "BIG_mC", "MID_mC", "LITTLE_mC",
          "G3D_mC", "ISP_mC", "NPU_mC", "max0_kHz", "max4_kHz", "max6_kHz",
          "cooling0", "cooling4", "cooling6", "dvfs_errors_since_start", "failed_units", "failsafe_mask"]
for field in fields:
    if any(not (row.get(field) or "").isdigit() for row in rows):
        issues.append(f"leitura ausente/invalida: {field}")
for field in ["dvfs_errors_since_start", "failed_units", "failsafe_mask"]:
    values = [int(row[field]) for row in rows if (row.get(field) or "").isdigit()]
    if values and max(values) > 0:
        issues.append(f"{field}: maximo {max(values)}")
for zone in ["BIG", "MID", "LITTLE", "G3D", "ISP", "NPU"]:
    values = [int(row[zone + "_mC"]) for row in rows if (row.get(zone + "_mC") or "").isdigit()]
    if values:
        print(f"{zone}: {min(values)/1000:.1f} a {max(values)/1000:.1f} C")
        if zone in ["BIG", "MID", "LITTLE"] and max(values) >= 83000:
            issues.append(f"{zone} atingiu o limite passivo; avaliar causa e resposta")
print(f"Amostras: {len(rows)}; duracao observada: {elapsed}s; maior intervalo: {max(gaps, default=0)}s")
if issues:
    print("PENDENTE/ANOMALIA: " + "; ".join(issues))
    sys.exit(2)
print("PASS: 24h de estabilidade em repouso, sem anomalias nos criterios coletados")
print("Nao certifica carga, calibracao termica, TSHUT nem recuperacao de energia.")
