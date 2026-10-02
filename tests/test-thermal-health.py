#!/usr/bin/env python3
"""Compile actual driver callbacks to test disabled-zone and recovery safety."""
import argparse
import pathlib
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, type=pathlib.Path)
args = parser.parse_args()
source = args.source.read_text()
def function(name):
    match = re.search(r'^static int ' + name + r'\(', source, re.MULTILINE)
    if not match:
        raise ValueError('missing callback ' + name)
    return source[match.start():source.index('\n}', match.start())+2]
mock = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define HZ 100UL
#define BIT(n) (1U << (n))
#define READ_ONCE(x) (x)
#define time_after(a,b) ((long)((b)-(a)) < 0)
#define time_after_eq(a,b) ((long)((a)-(b)) >= 0)
static unsigned long jiffies = 1000;
static unsigned int r8s_fault_mask;
static int calls, reports, sensor = 50;
static bool clamped = true;
enum thermal_device_mode { THERMAL_DEVICE_DISABLED, THERMAL_DEVICE_ENABLED };
struct r8s_cpu_zone {
 unsigned int id, first_cpu, bad_reads, good_reads;
 bool healthy, enabled;
 unsigned long last_sample, next_good_sample;
};
struct thermal_zone_device { struct r8s_cpu_zone *zone; };
static void *thermal_zone_device_priv(struct thermal_zone_device *tz) { return tz->zone; }
static int r8s_read_temp(unsigned int id, int *temp) { calls++; *temp=sensor; return 0; }
static int exynos990_cpufreq_sensor_report(unsigned int cpu, bool healthy) {
 reports++; clamped = !healthy; return 0;
}
'''
main = r'''
int main(void) {
 struct r8s_cpu_zone zone={0};
 struct thermal_zone_device tz={&zone};
 int temp, before;
 assert(r8s_zone_get_temp(&tz,&temp)==-EAGAIN && !calls && clamped);
 assert(!r8s_zone_change_mode(&tz,THERMAL_DEVICE_ENABLED));
 for(int i=0;i<100;i++) assert(!r8s_zone_get_temp(&tz,&temp));
 assert(zone.good_reads==1 && clamped && temp==50000);
 jiffies+=HZ; assert(!r8s_zone_get_temp(&tz,&temp)); assert(clamped);
 jiffies+=HZ; assert(!r8s_zone_get_temp(&tz,&temp)); assert(!clamped);
 assert(!r8s_zone_change_mode(&tz,THERMAL_DEVICE_DISABLED)); assert(clamped);
 before=calls;
 for(int i=0;i<100;i++) assert(r8s_zone_get_temp(&tz,&temp)==-EAGAIN);
 assert(calls==before && clamped && !zone.healthy);
 assert(!r8s_zone_change_mode(&tz,THERMAL_DEVICE_ENABLED));
 sensor=78;
 for(int i=0;i<4;i++) {jiffies+=HZ; assert(!r8s_zone_get_temp(&tz,&temp));}
 assert(clamped && zone.good_reads==0);
 sensor=50;
 for(int i=0;i<3;i++) {jiffies+=HZ; assert(!r8s_zone_get_temp(&tz,&temp));}
 assert(!clamped);
 r8s_fault_mask=1;
 for(int i=0;i<3;i++) assert(r8s_zone_get_temp(&tz,&temp)==-EIO);
 assert(clamped && !zone.healthy);
 r8s_fault_mask=0;
 for(int i=0;i<100;i++) assert(!r8s_zone_get_temp(&tz,&temp));
 assert(clamped && zone.good_reads==1);
 jiffies+=6*HZ; assert(!r8s_zone_get_temp(&tz,&temp));
 assert(clamped && zone.good_reads==1);
 puts("PASS: disabled zone stays clamped without ACPM reads; recovery samples spaced; hot/error/stale samples fail closed");
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='r8s-thermal-test-') as d:
    c=pathlib.Path(d)/'callbacks.c'; exe=pathlib.Path(d)/'test'
    c.write_text(mock + function('r8s_zone_get_temp') + function('r8s_zone_change_mode') + main)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Wno-unused-parameter','-Werror',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
