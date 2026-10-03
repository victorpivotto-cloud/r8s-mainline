#!/usr/bin/env python3
"""Test actual status/type/presence functions with failures at each read stage."""
import argparse
from pathlib import Path
import subprocess
import tempfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--baseline',action='store_true')
a=p.parse_args();s=a.source.read_text();functions=[]
for name in ('max77705_get_status','max77705_get_charge_type','max77705_check_battery'):
 start=s.index('static int '+name+'(')
 functions.append(s[start:s.index('\n}\n',start)+3])
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
enum {POWER_SUPPLY_STATUS_UNKNOWN, POWER_SUPPLY_STATUS_CHARGING,
 POWER_SUPPLY_STATUS_DISCHARGING, POWER_SUPPLY_STATUS_NOT_CHARGING,
 POWER_SUPPLY_STATUS_FULL};
enum {POWER_SUPPLY_CHARGE_TYPE_UNKNOWN, POWER_SUPPLY_CHARGE_TYPE_NONE,
 POWER_SUPPLY_CHARGE_TYPE_TRICKLE, POWER_SUPPLY_CHARGE_TYPE_FAST};
enum {MAX77705_CHARGER_CONSTANT_CURRENT=1, MAX77705_CHARGER_CONSTANT_VOLTAGE,
 MAX77705_CHARGER_END_OF_CHARGE, MAX77705_CHARGER_DONE};
#define MAX77705_CHG_EN 0
#define MAX77705_CHG_REG_INT_OK 0xb2
#define MAX77705_CHG_REG_DETAILS_00 0xb3
#define MAX77705_CHG_REG_DETAILS_01 0xb4
#define MAX77705_CHG_DTLS 0x0f
#define MAX77705_BATP_OK 0x04
#define MAX77705_BATP_DTLS 0x01
#define dev_dbg(...) ((void)0)
struct regmap {unsigned int reads,fail_at; int error;
 unsigned int state,int_ok,details00;};
struct regmap_field {unsigned int reads,enabled; int error;};
struct max77705_charger_data {struct regmap *regmap;
 struct regmap_field *rfield[1]; void *dev;};
static int regmap_read(struct regmap *m,unsigned int reg,unsigned int *value)
{
 ++m->reads;
 switch(reg) {
 case MAX77705_CHG_REG_INT_OK:*value=m->int_ok;break;
 case MAX77705_CHG_REG_DETAILS_00:*value=m->details00;break;
 case MAX77705_CHG_REG_DETAILS_01:*value=m->state;break;
 default:assert(0);
 }
 /* Fill even on error to expose ignored errno without uninitialized C. */
 return m->reads==m->fail_at ? m->error : 0;
}
static int regmap_field_read(struct regmap_field *f,unsigned int *value)
{++f->reads;*value=f->enabled;return f->error;}
'''
main=r'''
typedef int (*getter)(struct max77705_charger_data *,int *);
int main(void)
{
 struct regmap m={0};struct regmap_field f={0};
 struct max77705_charger_data chg={&m,{&f},NULL};
 getter functions[2]={max77705_get_status,max77705_get_charge_type};
 const int statuses[16]={1,1,1,4,4,3,3,3,2,0,2,2,0,0,0,0};
 int v,ret;
 /* Disabled charging must not be decoded through the charge-type enum. */
 v=-12345;assert(max77705_get_status(&chg,&v)==0);
#ifdef BASELINE
 assert(v==POWER_SUPPLY_STATUS_CHARGING);
#else
 assert(v==POWER_SUPPLY_STATUS_NOT_CHARGING);
#endif
 assert(m.reads==0);
 v=-12345;assert(max77705_get_charge_type(&chg,&v)==0);
 assert(v==POWER_SUPPLY_CHARGE_TYPE_NONE && m.reads==0);
 f.enabled=1;
 for(unsigned int i=0;i<16;++i) {
  m.state=i|0xf0;v=-12345;assert(max77705_get_status(&chg,&v)==0);
  assert(v==statuses[i]);v=-12345;
  assert(max77705_get_charge_type(&chg,&v)==0);
  assert(v==(i<=2 ? POWER_SUPPLY_CHARGE_TYPE_FAST : POWER_SUPPLY_CHARGE_TYPE_NONE));
 }
 const int errors[2]={-EIO,-ETIMEDOUT};
 for(unsigned int fn=0;fn<2;++fn)for(unsigned int e=0;e<2;++e) {
  m.reads=0;m.state=1;f.error=errors[e];v=-12345;
  ret=functions[fn](&chg,&v);
#ifdef BASELINE
  assert(ret==0 && v!=-12345 && m.reads==1);
#else
  assert(ret==errors[e] && v==-12345 && m.reads==0);
#endif
  f.error=0;m.reads=0;m.fail_at=1;m.error=errors[e];v=-12345;
  ret=functions[fn](&chg,&v);
#ifdef BASELINE
  assert(ret==0 && v!=-12345);
#else
  assert(ret==errors[e] && v==-12345);
#endif
  assert(m.reads==1);m.fail_at=0;
 }
 const int presence[4]={1,0,1,1};
 for(unsigned int i=0;i<4;++i) {
  m.int_ok=(i/2)*MAX77705_BATP_OK;m.details00=i%2;v=-12345;
  assert(max77705_check_battery(&chg,&v)==0 && v==presence[i]);
 }
 for(unsigned int step=1;step<=2;++step)for(unsigned int e=0;e<2;++e) {
  m.reads=0;m.fail_at=step;m.error=errors[e];v=-12345;
  ret=max77705_check_battery(&chg,&v);
#ifdef BASELINE
  assert(ret==0 && v!=-12345 && m.reads==2);
#else
  assert(ret==errors[e] && v==-12345 && m.reads==step);
#endif
 }
#ifdef BASELINE
 puts("BASELINE reproduced: disabled reported Charging and failed reads hidden");
#else
 puts("PASS: disabled status, 16 states, presence cases and failures at every read stage");
#endif
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='max77705-status-test-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(prefix+'\n'.join(functions)+main)
 cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(exe)]
 if a.baseline:cmd.insert(1,'-DBASELINE')
 subprocess.run(cmd,check=True);subprocess.run([str(exe)],check=True)
