#!/usr/bin/env python3
"""Decode a saved DWC3 debugfs regdump; never access or write MMIO."""
import argparse
import pathlib
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("regdump", type=pathlib.Path)
args = parser.parse_args()
registers = dict((name, int(value, 16)) for name, value in
                 re.findall(r"^(\w+(?:\(0\))?) = (0x[0-9a-fA-F]+)$",
                            args.regdump.read_text(), re.MULTILINE))
for required in ("GUCTL", "GFLADJ"):
    if required not in registers:
        parser.error("missing register " + required)
g = registers["GUCTL"]
f = registers["GFLADJ"]
print("GUCTL REFCLKPER:", (g >> 22) & 0x3ff)
print("GUCTL DTOUT:", g & 0x7ff)
print("GUCTL NOEXTRDL:", int(bool(g & (1 << 21))))
print("GUCTL USBHSTINAUTORETRYEN:", int(bool(g & (1 << 14))))
print("GFLADJ 240MHZDECR:", (f >> 24) & 0x7f)
print("GFLADJ REFCLK_FLADJ:", (f >> 8) & 0x3fff)
print("GFLADJ REFCLK_LPM_SEL:", int(bool(f & (1 << 23))))
print("GFLADJ 30MHZ_SDBND_SEL:", int(bool(f & (1 << 7))))
print("GFLADJ 30MHZ:", f & 0x3f)
print("Samsung Exynos9830 EVT1 reference: REFCLKPER=50, DECR=12, FLADJ=0.")
print("Comparison only: a different value is not proof of the USB failure cause.")
