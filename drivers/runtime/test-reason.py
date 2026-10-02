#!/usr/bin/env python3
"""Run the actual reason preparation function against a register mock."""
import pathlib
import re
import subprocess
import tempfile

source = pathlib.Path(__file__).with_name("r8s-reboot-reason.c").read_text()
constants = "\n".join(line for line in source.splitlines() if line.startswith("#define R8S_"))
start = source.index("static int r8s_prepare_reason(")
body = source[start:source.index("\n}", start) + 2]
mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static void *r8s_pmu;
static unsigned int magic, reason, mode, calls, fail_at;
static int regmap_update_bits(void *p, unsigned int r, unsigned int mask, unsigned int value) {
 assert(r==0x808); if (++calls==fail_at) return -EIO;
 magic=(magic & ~mask) | (value & mask); return 0;
}
static int regmap_write(void *p, unsigned int r, unsigned int value) {
 if (++calls==fail_at) return -EIO;
 if(r==0x80c) reason=value; else { assert(r==0x810); mode=value; } return 0;
}
static int regmap_read(void *p, unsigned int r, unsigned int *out) {
 assert(r==0x810); if (++calls==fail_at) return -EIO; *out=mode; return 0;
}
static void reset(void) { magic=0xabcd1234; reason=0x98765432; mode=0x11; calls=0; fail_at=0; }
'''
test = r'''
int main(void) {
 const char *cmds[]={NULL,"","bootloader","fastboot"};
 for(unsigned int i=0;i<4;i++) {
  reset(); assert(r8s_prepare_reason(cmds[i])==0);
  assert(magic==0xab4e1234); assert(reason==0x12345600); assert(mode==(i<2 ? 0 : 0x4c)); assert(calls==4);
 }
 reset(); assert(r8s_prepare_reason("download")==-EOPNOTSUPP);
 assert(calls==0 && magic==0xabcd1234 && reason==0x98765432 && mode==0x11);
 for(unsigned int i=1;i<=4;i++) { reset(); fail_at=i; assert(r8s_prepare_reason("bootloader")==-EIO); assert(calls==i); }
 puts("PASS: normal/lk3rd modes, preserved debug bits, unsupported command no writes, all IO failures propagated");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    (root / "test.c").write_text(mock + constants + "\n" + body + "\n" + test)
    subprocess.run(["cc", "-Wall", "-Werror", "-o", str(root / "test"), str(root / "test.c")], check=True)
    subprocess.run([str(root / "test")], check=True)
