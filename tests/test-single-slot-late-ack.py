#!/usr/bin/env python3
"""Characterize the actual provider's late-ACK gap; never access hardware.

REPRODUCED is an unsafe assumption demonstrated by a mock, not firmware proof.
MODELED cases assume a shared, coalescing ACK latch and reusable RX slot;
they are counterexamples to recovery assumptions, not a hardware contract.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, type=Path)
args = parser.parse_args()
source = args.source.read_text()
name = 'acpm_wait_for_singleslot_response'
start = source.index('static int '+name+'(')
function = source[start:source.index('\n}', start)+2]
constants=[]
for symbol in ('ACPM_PROTOCOL_SEQNUM','ACPM_POLL_TIMEOUT_US','ACPM_MBOX_INTCR1','ACPM_MBOX_INTSR1'):
    match=re.search(r'^#define\s+'+symbol+r'\s+(.+)$',source,re.MULTILINE)
    if not match: parser.error('missing constant '+symbol)
    constants.append('#define '+symbol+' '+match.group(1))
mock=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
#define USEC_PER_MSEC 1000
#define GENMASK(h,l) (((~0u) >> (31-(h))) & ((~0u) << (l)))
#define FIELD_GET(mask,value) (((value)&(mask)) >> __builtin_ctz(mask))
struct acpm_info { unsigned char *mbox_intr; };
struct acpm_chan { struct acpm_info *acpm; u32 id; unsigned long *bitmap_seqnum; struct { void *base; } rx; unsigned int mlen; };
struct acpm_xfer { u32 *txd,*rxd; size_t rxcnt; };
static unsigned char registers[64];
_Static_assert(ACPM_MBOX_INTSR1+sizeof(u32)<=sizeof registers &&
               ACPM_MBOX_INTCR1+sizeof(u32)<=sizeof registers,
               "mock register offsets outside storage");
static int inject_timeout;
static bool inject_response_before_clear;
static u32 *injected_rx;
static u32 injected_seq;
static bool acpm_diag_once __attribute__((unused));
static unsigned int diag_logs __attribute__((unused));
static u32 diag_tx __attribute__((unused)),diag_rx __attribute__((unused));
#define xchg(ptr,value) ({ bool old=*(ptr); *(ptr)=(value); old; })
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value,new_value) ((value)=(new_value))
#define dev_info(dev,format,tx,rx,...) do { \
    (void)(format); diag_logs++; diag_tx=(tx); diag_rx=(rx); \
    assert(readl(registers+ACPM_MBOX_INTSR1)==0); \
} while (0)
static u32 readl(void *address) { u32 v; memcpy(&v,address,4); return v; }
static void writel(u32 value,void *address) {
    if(address == registers+ACPM_MBOX_INTCR1) {
        if (inject_response_before_clear) {
            // Model a second response published after polling/copy but before clear.
            // The already asserted channel bit coalesces both events.
            u32 status=readl(registers+ACPM_MBOX_INTSR1)|value;
            injected_rx[0]=injected_seq<<16;
            memcpy(registers+ACPM_MBOX_INTSR1,&status,4);
            inject_response_before_clear=false;
        }
        u32 status=readl(registers+ACPM_MBOX_INTSR1)&~value;
        memcpy(registers+ACPM_MBOX_INTSR1,&status,4);
    } else memcpy(address,&value,4);
}
#define memcpy_fromio(dst,src,n) memcpy(dst,src,n)
static void clear_bit_unlock(unsigned int n,unsigned long *bits) { *bits &= ~(1ul<<n); }
#define readl_poll_timeout(address,val,condition,delay,timeout) \
 ({ (val)=readl(address); (void)(delay); (void)(timeout); inject_timeout || !(condition) ? -ETIMEDOUT : 0; })
'''
main=r'''
int main(void) {
 unsigned long bitmap=1;
 u32 tx[4]={1u<<16,0,0,0}, rx[4]={1u<<16,1066000,0,0}, output[4]={0};
 struct acpm_info info={registers};
 struct acpm_chan chan={&info,5,&bitmap,{rx},16};
 struct acpm_xfer transfer={tx,output,4};
 u32 ack=1u<<5;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0);
 assert(output[1]==1066000 && bitmap==0);
 puts("CONTROL: matching sequence completes and releases ownership");
 // Command1 times out before any ACK; then its response arrives during command2.
 bitmap=1; inject_timeout=1; memset(output,0,sizeof output);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==-ETIMEDOUT);
 assert(bitmap==0);
 inject_timeout=0;
 tx[0]=2u<<16; bitmap=1ul<<1;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4); // Late ACK of command1, not command2.
 assert(FIELD_GET(ACPM_PROTOCOL_SEQNUM,rx[0])==1);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0);
 assert(FIELD_GET(ACPM_PROTOCOL_SEQNUM,output[0])==1 && bitmap==0);
 assert(readl(registers+ACPM_MBOX_INTSR1)==0);
 puts("REPRODUCED: command2 accepted command1 late ACK and released its own sequence");
 // CPU set-rate can request no RX payload; it still consumes the old ACK.
 transfer.rxcnt=0; transfer.rxd=NULL; tx[0]=3u<<16; bitmap=1ul<<2;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0 && bitmap==0);
 puts("REPRODUCED: no-RX transfer also accepts stale ACK; matching payload is not required");
 return 0;
}
'''
if 'acpm_diag_once' in function:
    cases=r'''
 // An armed timeout is not consumed; a later successful ACK logs once after clear.
 acpm_diag_once=true; inject_timeout=1; tx[0]=4u<<16; bitmap=1ul<<3;
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==-ETIMEDOUT);
 assert(acpm_diag_once && diag_logs==0);
 inject_timeout=0; rx[0]=4u<<16; bitmap=1ul<<3;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0);
 assert(!acpm_diag_once && diag_logs==1 && diag_tx==tx[0] && diag_rx==rx[0]);
 tx[0]=5u<<16; bitmap=1ul<<4; memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0 && diag_logs==1);
 puts("CONTROL: opt-in capture consumes one success, preserves timeout arm, logs after ACK clear");
'''
    main=main.replace(' return 0;',cases+' return 0;')

interleavings=r'''
 // Model a stale ACK with a new response arriving just before the old clear.
 transfer.rxcnt=4; transfer.rxd=output;
 tx[0]=6u<<16; rx[0]=1u<<16; bitmap=1ul<<5;
 injected_rx=rx; injected_seq=6; inject_response_before_clear=true;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0);
 assert(!inject_response_before_clear && bitmap==0);
 assert(FIELD_GET(ACPM_PROTOCOL_SEQNUM,output[0])==1);
 assert(FIELD_GET(ACPM_PROTOCOL_SEQNUM,rx[0])==6);
 assert(readl(registers+ACPM_MBOX_INTSR1)==0);
 puts("MODELED: helper copy-before-clear loses a coalesced response notification");
 // After reuse, an expired response can carry the same sequence as the new owner.
 // Even a hypothetical equality-only check would accept this RX word.
 tx[0]=1u<<16; tx[1]=0x12345678u;
 rx[0]=1u<<16; rx[1]=0xdeadbeefu; bitmap=1;
 memcpy(registers+ACPM_MBOX_INTSR1,&ack,4);
 assert(FIELD_GET(ACPM_PROTOCOL_SEQNUM,tx[0])==FIELD_GET(ACPM_PROTOCOL_SEQNUM,rx[0]));
 assert(acpm_wait_for_singleslot_response(&chan,&transfer)==0 && bitmap==0);
 assert(output[1]==0xdeadbeefu && output[1]!=tx[1]);
 puts("MODELED: if expired RX survives sequence reuse, equality also matches its stale payload");
'''
main=main.replace(' return 0;',interleavings+' return 0;')

with tempfile.TemporaryDirectory(prefix='acpm-late-ack-') as directory:
    p=Path(directory);c=p/'probe.c';c.write_text(mock.split('static unsigned char')[0]+'\n'.join(constants)+'\nstatic unsigned char'+mock.split('static unsigned char',1)[1]+function+main)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(c),'-o',str(p/'probe')],check=True)
    subprocess.run([str(p/'probe')],check=True)
