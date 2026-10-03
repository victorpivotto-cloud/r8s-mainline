#!/usr/bin/env python3
"""Compile the actual battery-health function against a deterministic regmap mock."""
import argparse
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', action='store_true')
a = p.parse_args()
s = a.source.read_text()
start = s.index('static int max77705_get_battery_health(')
end = s.index('\n}\n', start) + 3
fn = s[start:end]
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
enum { POWER_SUPPLY_HEALTH_UNKNOWN, POWER_SUPPLY_HEALTH_GOOD,
 POWER_SUPPLY_HEALTH_DEAD, POWER_SUPPLY_HEALTH_NO_BATTERY,
 POWER_SUPPLY_HEALTH_OVERVOLTAGE, POWER_SUPPLY_HEALTH_UNSPEC_FAILURE };
/* Enum order/mask from max77705-private.h/max77705_charger.h. */
enum { MAX77705_BATTERY_NOBAT, MAX77705_BATTERY_PREQUALIFICATION,
 MAX77705_BATTERY_DEAD, MAX77705_BATTERY_GOOD, MAX77705_BATTERY_LOWVOLTAGE,
 MAX77705_BATTERY_OVERVOLTAGE, MAX77705_BATTERY_RESERVED };
#define MAX77705_CHG_REG_DETAILS_01 0xb4
#define MAX77705_BAT_DTLS 0x70
#define MAX77705_BAT_DTLS_SHIFT 4
#define dev_dbg(...) ((void)0)
struct regmap { int error; unsigned int data; };
struct max77705_charger_data { struct regmap *regmap; void *dev; };
static int regmap_read(struct regmap *map, unsigned int reg, unsigned int *v)
{
 (void)reg;
 /* Define data even in error: reproduce ignored error without invoking UB. */
 *v = map->data;
 return map->error;
}
'''
main = r'''
int main(void)
{
 struct regmap map = { 0, 0 };
 struct max77705_charger_data chg = { &map, NULL };
 const int expected[8] = { POWER_SUPPLY_HEALTH_NO_BATTERY,
  POWER_SUPPLY_HEALTH_UNKNOWN, POWER_SUPPLY_HEALTH_DEAD,
  POWER_SUPPLY_HEALTH_GOOD, POWER_SUPPLY_HEALTH_GOOD,
  POWER_SUPPLY_HEALTH_OVERVOLTAGE, POWER_SUPPLY_HEALTH_UNSPEC_FAILURE,
  POWER_SUPPLY_HEALTH_UNSPEC_FAILURE };
 int value, ret;
 for (unsigned int i = 0; i < 8; ++i) {
  map.data = (i << MAX77705_BAT_DTLS_SHIFT) | 0x8f;
  value = 9876;
  ret = max77705_get_battery_health(&chg, &value);
  assert(ret == 0);
#ifdef BASELINE
  if (i == MAX77705_BATTERY_PREQUALIFICATION) assert(value == 9876);
  else assert(value == expected[i]);
#else
  assert(value == expected[i]);
#endif
 }
 map.error = -EIO;
 map.data = MAX77705_BATTERY_GOOD << MAX77705_BAT_DTLS_SHIFT;
 value = 9876;
 ret = max77705_get_battery_health(&chg, &value);
#ifdef BASELINE
 assert(ret == 0 && value == POWER_SUPPLY_HEALTH_GOOD);
 puts("BASELINE reproduced: ignored I/O error and untouched prequalification output");
#else
 assert(ret == -EIO && value == 9876);
 puts("PASS: eight states, unrelated bits, explicit prequalification and I/O propagation");
#endif
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='max77705-health-test-') as d:
 c = Path(d)/'test.c'; exe = Path(d)/'test'
 c.write_text(prefix + fn + main)
 cmd = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-fsanitize=address,undefined', str(c), '-o', str(exe)]
 if a.baseline:
  cmd.insert(1, '-DBASELINE')
 subprocess.run(cmd, check=True)
 subprocess.run([str(exe)], check=True)
