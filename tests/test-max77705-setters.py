#!/usr/bin/env python3
"""Test actual MAX77705 setters offline with bit-0 field stubs; no hardware I/O.

The clamp stub matches the int-valued callers, not kernel compile-time checks.
Exact-code fixtures follow the vendor source encoding, not a physical test.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--header', type=Path, required=True)
args = parser.parse_args()
source = args.source.read_text()
header = args.header.read_text()
functions = []
for name in ('max77705_set_integer', 'max77705_set_property',
             'max77705_get_input_current', 'max77705_get_charge_current'):
    start = source.index('static int ' + name + '(')
    functions.append(source[start:source.index('\n}', start) + 2])
macros = '\n'.join(line for line in header.splitlines()
                   if re.match(r'#define MAX77705_CURRENT_', line))
PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#define clamp_val(v,lo,hi) ((v)<(int)(lo)?(int)(lo):((v)>(int)(hi)?(int)(hi):(v)))
enum max77705_field_idx { MAX77705_CHG_CHGIN_LIM, MAX77705_CHG_CC_LIM };
enum power_supply_property { POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT, POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT, OTHER };
union power_supply_propval { int intval; };
struct regmap_field { unsigned int mask,reg,requested,writes; int error; };
struct max77705_charger_data { struct regmap_field *rfield[2]; };
struct power_supply { struct max77705_charger_data *data; };
static struct max77705_charger_data *power_supply_get_drvdata(struct power_supply *p) { return p->data; }
static int regmap_field_write(struct regmap_field *f,unsigned int v) {
 ++f->writes;f->requested=v;
 if (f->error) return f->error;
 f->reg=(f->reg&~f->mask)|(v&f->mask);return 0;
}
static int regmap_field_read(struct regmap_field *f,unsigned int *v) { *v=f->reg&f->mask;return 0; }
'''
MAIN = r'''
static unsigned long cases;
static void verify(struct power_supply *p,unsigned int i,int value) {
 struct regmap_field *f=p->data->rfield[i];
 enum power_supply_property prop=i?POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT:POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT;
 union power_supply_propval v={value};int decoded,clamped=value;
 int max=i?3150000:3200000,step=i?50000:25000;
 if(clamped<100000) clamped=100000;
 if(clamped>max) clamped=max;
 f->reg=i?0xc0:0x80;f->writes=0;
 assert(max77705_set_property(p,prop,&v)==0 && f->writes==1);
 assert(f->requested<=f->mask);
 assert((f->reg&~f->mask)==(i?0xc0u:0x80u));
 assert((i?max77705_get_charge_current(p->data,&decoded):max77705_get_input_current(p->data,&decoded))==0);
 assert(decoded==clamped/step*step && decoded<=clamped);
 ++cases;
}
int main(void) {
 struct regmap_field f[2]={{.mask=127},{.mask=63}};
 struct max77705_charger_data d={{&f[0],&f[1]}};struct power_supply p={&d};
 assert(MAX77705_CURRENT_CHG_MAX==3150000);
 for(unsigned int i=0;i<2;i++) {
  verify(&p,i,INT_MIN);verify(&p,i,-1);verify(&p,i,INT_MAX);
  for(int v=99999;v<=3200001;v++) verify(&p,i,v);
  const int errors[]={-EIO,-ETIMEDOUT};
  for(unsigned int j=0;j<2;j++) {
   union power_supply_propval v={1800000};f[i].error=errors[j];f[i].writes=0;f[i].reg=i?0xc5:0x86;
   assert(max77705_set_property(&p,i?POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT:POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,&v)==errors[j]);
   assert(f[i].writes==1 && f[i].reg==(i?0xc5u:0x86u));f[i].error=0;
  }
 }
 /* Pin codes independently of the getters, per vendor source encoding. */
 const struct { unsigned int field; int value; unsigned int code; } exact[] = {
  {0,100000,3},{0,124999,3},{0,125000,4},{0,3200000,127},
  {1,100000,2},{1,150000,3},{1,3150000,63}
 };
 for(unsigned int j=0;j<sizeof(exact)/sizeof(exact[0]);j++) {
  verify(&p,exact[j].field,exact[j].value);
  assert(f[exact[j].field].requested==exact[j].code);
 }
 union power_supply_propval v={1800000};f[0].writes=f[1].writes=0;
 assert(max77705_set_property(&p,OTHER,&v)==-EINVAL && f[0].writes==0 && f[1].writes==0);
 printf("PASS: %lu roundtrips, integer clamps, code masks, neighbouring bits, EIO/timeout, dispatcher\n",cases);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='max77705-setters-test-') as directory:
    test = Path(directory) / 'test.c'
    executable = Path(directory) / 'test'
    test.write_text(PREFIX + macros + '\n' + '\n'.join(functions) + MAIN)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-O1', str(test),
                    '-o', str(executable)], check=True, timeout=30)
    subprocess.run([str(executable)], check=True, timeout=20)
