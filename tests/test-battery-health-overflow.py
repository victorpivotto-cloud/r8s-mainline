#!/usr/bin/env python3
"""Compile the real battery-health function to verify voltage-limit arithmetic."""
import argparse
import pathlib
import re
import subprocess
import tempfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',required=True,type=pathlib.Path)
parser.add_argument('--baseline',action='store_true')
args=parser.parse_args()
s=args.source.read_text(); start=s.index('static int max17042_get_battery_health(')
fn=s[start:s.index('\n}',start)+2]
mock=r'''
#include <assert.h>
#include <stdint.h>
#include <limits.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
typedef int64_t s64;
#define MAX17042_AvgVCELL 1
#define MAX17042_VCELL 2
#define MAX17042_VMAX_TOLERANCE 50
#define POWER_SUPPLY_HEALTH_GOOD 0
#define POWER_SUPPLY_HEALTH_DEAD 1
#define POWER_SUPPLY_HEALTH_OVERVOLTAGE 2
#define POWER_SUPPLY_HEALTH_COLD 3
#define POWER_SUPPLY_HEALTH_OVERHEAT 4
struct pdata { int vmin,vmax,temp_min,temp_max; };
struct max17042_chip { int *regmap; struct pdata *pdata; };
static int voltage=4300,temp=341,io_error=0;
static int regmap_read(int *map,int reg,u32 *val) {
 if(io_error) return -EIO;
 *val=(u32)(voltage*1000*8/625); return 0;
}
static int max17042_get_temperature(struct max17042_chip *chip,int *value) { *value=temp; return 0; }
'''
main=r'''
int main(void) {
 struct pdata p={INT_MIN,INT_MAX,INT_MIN,INT_MAX};
 struct max17042_chip chip={NULL,&p}; int health=-1;
 assert(!max17042_get_battery_health(&chip,&health));
#ifdef BASELINE
 assert(health==POWER_SUPPLY_HEALTH_OVERVOLTAGE);
 puts("REPRODUCED: absent max voltage falsely reports overvoltage due to signed overflow");
#else
 assert(health==POWER_SUPPLY_HEALTH_GOOD);
 p.vmax=4200; voltage=4250;
 assert(!max17042_get_battery_health(&chip,&health)); assert(health==POWER_SUPPLY_HEALTH_GOOD);
 voltage=4260;
 assert(!max17042_get_battery_health(&chip,&health)); assert(health==POWER_SUPPLY_HEALTH_OVERVOLTAGE);
 p.vmax=INT_MAX; p.vmin=3200; voltage=3100;
 assert(!max17042_get_battery_health(&chip,&health)); assert(health==POWER_SUPPLY_HEALTH_DEAD);
 voltage=4000; p.temp_min=0; p.temp_max=600; temp=700;
 assert(!max17042_get_battery_health(&chip,&health)); assert(health==POWER_SUPPLY_HEALTH_OVERHEAT);
 temp=-10;
 assert(!max17042_get_battery_health(&chip,&health)); assert(health==POWER_SUPPLY_HEALTH_COLD);
 io_error=1; assert(max17042_get_battery_health(&chip,&health)==-EIO);
 puts("PASS: absent limit, voltage boundary, real overvoltage, low voltage, temperatures and IO failures");
#endif
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='max17042-health-') as d:
 p=pathlib.Path(d); (p/'test.c').write_text(mock+fn+main)
 command=['cc','-std=gnu11','-Wall','-Wextra','-Wno-unused-parameter','-Werror','-fwrapv']
 if args.baseline: command+=['-DBASELINE']
 subprocess.run(command+[str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
