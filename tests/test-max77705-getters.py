#!/usr/bin/env python3
"""Exercise actual MAX77705 getters with field-read failures and conversion boundaries."""
import argparse
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', action='store_true')
a = p.parse_args()
s = a.source.read_text()
functions = []
for name in ('max77705_get_input_current', 'max77705_get_charge_current', 'max77705_get_float_voltage'):
 start = s.index('static int ' + name + '(')
 functions.append(s[start:s.index('\n}\n', start) + 3])
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stddef.h>
enum { MAX77705_CHG_CC_LIM, MAX77705_CHG_CHGIN_LIM, MAX77705_CHG_CV_PRM };
#define MAX77705_CURRENT_CHGIN_MIN 100000
#define MAX77705_CURRENT_CHGIN_STEP 25000
#define MAX77705_CURRENT_CHG_STEP 50000
struct regmap_field { int error; unsigned int data; unsigned int reads; };
struct max77705_charger_data { struct regmap_field *rfield[3]; };
static int regmap_field_read(struct regmap_field *field, unsigned int *value)
{
 ++field->reads;
 /* Defined output even on failure: expose ignored error without undefined C. */
 *value = field->data;
 return field->error;
}
'''
main = r'''
typedef int (*getter)(struct max77705_charger_data *, int *);
struct test_case { unsigned int raw; int expected; };
int main(void)
{
 struct regmap_field fields[3] = {{0}};
 struct max77705_charger_data chg = {{&fields[0], &fields[1], &fields[2]}};
 const getter getters[3] = { max77705_get_charge_current,
  max77705_get_input_current, max77705_get_float_voltage };
 const struct test_case cases[3][5] = {
  {{0,100000},{2,100000},{3,150000},{18,900000},{63,3150000}},
  {{0,100000},{3,100000},{4,125000},{35,900000},{127,3200000}},
  {{0,4000000},{4,4200000},{5,4210000},{18,4340000},{63,4790000}}
 };
 for (unsigned int i=0; i<3; ++i) {
  for (unsigned int j=0; j<5; ++j) {
   int value=-12345;
   fields[i].data=cases[i][j].raw; fields[i].reads=0;
   assert(getters[i](&chg,&value)==0);
   assert(value==cases[i][j].expected && fields[i].reads==1);
  }
  const int errors[2]={-EIO,-ETIMEDOUT};
  for (unsigned int j=0; j<2; ++j) {
   int value=-12345, ret;
   fields[i].error=errors[j]; fields[i].data=0; fields[i].reads=0;
   ret=getters[i](&chg,&value);
#ifdef BASELINE
   assert(ret==0 && value!=-12345);
#else
   assert(ret==errors[j] && value==-12345);
#endif
   assert(fields[i].reads==1);
  }
  fields[i].error=0;
 }
#ifdef BASELINE
 puts("BASELINE reproduced: all three getters hide I/O failure as values");
#else
 puts("PASS: three getters, conversion boundaries, EIO/timeout propagation, output untouched on error");
#endif
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='max77705-getters-test-') as d:
 c=Path(d)/'test.c'; exe=Path(d)/'test'
 c.write_text(prefix+'\n'.join(functions)+main)
 cmd=['cc','-std=c11','-Wall','-Wextra','-Werror',
      '-fsanitize=address,undefined',str(c),'-o',str(exe)]
 if a.baseline: cmd.insert(1,'-DBASELINE')
 subprocess.run(cmd,check=True)
 subprocess.run([str(exe)],check=True)
