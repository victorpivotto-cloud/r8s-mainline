#!/usr/bin/env python3
"""Execute the real C functions against a concurrent single-slot mailbox mock.

Builds baseline and edited function bodies, not a Python rewrite of the driver.
The mock checks slot ownership and error propagation, not firmware correctness.
"""
import argparse
import pathlib
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", type=pathlib.Path, required=True, help="unpatched kernel source tree")
parser.add_argument("--kernel", type=pathlib.Path, required=True, help="patched kernel source tree")
args = parser.parse_args()
TREE = args.kernel
BASELINE = args.baseline


def function(path, name):
    source = path.read_text()
    match = re.search(r"^(?:static )?int " + re.escape(name) + r"\(", source, re.MULTILINE)
    if match is None:
        raise ValueError("Function definition not found: " + name)
    start = match.start()
    end = source.index("\n}", start) + 2
    return source[start:end]


COMMON = r'''
#define _GNU_SOURCE
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
struct mutex { pthread_mutex_t lock; };
#define DEFINE_MUTEX(n) struct mutex n = { PTHREAD_MUTEX_INITIALIZER }
static void mutex_lock(struct mutex *m) { pthread_mutex_lock(&m->lock); }
static void mutex_unlock(struct mutex *m) { pthread_mutex_unlock(&m->lock); }
#define pr_warn_ratelimited(...) ((void)0)
static atomic_int active, overlaps, force_error;
static pthread_barrier_t start;
static void begin_request(void) {
    if (atomic_fetch_add(&active, 1)) atomic_fetch_add(&overlaps, 1);
}
static int finish_request(void) {
    usleep(1000);
    atomic_fetch_sub(&active, 1);
    return 0;
}
'''

CPU = r'''
#define ACPM_DVFS_CHANNEL 5
#define HZ_PER_KHZ 1000
struct cpufreq_frequency_table { unsigned int frequency; };
struct z3s_cluster { unsigned int acpm_id, cur_khz; };
struct cpufreq_policy {
    struct z3s_cluster *driver_data;
    struct cpufreq_frequency_table *freq_table;
};
struct acpm_handle;
struct ops { struct { int (*set_rate)(struct acpm_handle *, unsigned int,
                                     unsigned int, unsigned long); } dvfs; };
struct acpm_handle { struct ops *ops; };
static int set_rate(struct acpm_handle *h, unsigned int ch, unsigned int id,
                    unsigned long rate) {
    if (atomic_load(&force_error)) return -ETIMEDOUT;
    begin_request();
    return finish_request();
}
static struct ops ops = { .dvfs = { .set_rate = set_rate } };
static struct acpm_handle handle = { .ops = &ops };
static struct acpm_handle *z3s_acpm = &handle;
static DEFINE_MUTEX(z3s_dvfs_lock);
'''

CPU_MAIN = r'''
static void *worker(void *arg) {
    struct z3s_cluster cl = { .acpm_id = (uintptr_t)arg, .cur_khz = 442000 };
    struct cpufreq_frequency_table ft = { .frequency = 650000 };
    struct cpufreq_policy p = { .driver_data = &cl, .freq_table = &ft };
    pthread_barrier_wait(&start);
    for (int i = 0; i < 80; i++)
        if (z3s_target_index(&p, 0)) abort();
    return NULL;
}
int main(void) {
    pthread_t t[3];
    pthread_barrier_init(&start, NULL, 3);
    for (uintptr_t i = 0; i < 3; i++) pthread_create(&t[i], NULL, worker, (void *)i);
    for (int i = 0; i < 3; i++) pthread_join(t[i], NULL);
    struct z3s_cluster cl = { .acpm_id = 2, .cur_khz = 442000 };
    struct cpufreq_frequency_table ft = { .frequency = 650000 };
    struct cpufreq_policy p = { .driver_data = &cl, .freq_table = &ft };
    atomic_store(&force_error, 1);
    if (z3s_target_index(&p, 0) != -ETIMEDOUT || cl.cur_khz != 442000) return 2;
    atomic_store(&force_error, 0);
    if (z3s_target_index(&p, 0) || cl.cur_khz != 650000) return 3;
    printf("overlaps=%d; timeout preserved; cache unchanged on failure\n", overlaps);
    return 0;
}
'''

ACPM = r'''
typedef uint32_t u32;
#define ACPM_PROTOCOL_SEQNUM 0x3f0000
#define FIELD_GET(mask, x) (((x) & (mask)) >> 16)
#define EXYNOS_MBOX_CHAN_TYPE_DOORBELL 1
struct guard { struct mutex *m; int done; };
static struct guard guard_enter(struct mutex *m) { mutex_lock(m); return (struct guard){m,0}; }
static void guard_exit(struct guard *g) { mutex_unlock(g->m); }
#define scoped_guard(type, lock) \
    for (struct guard g __attribute__((cleanup(guard_exit))) = guard_enter(lock); !g.done; g.done=1)
struct acpm_xfer { u32 acpm_chan_id; u32 *txd, *rxd; unsigned int txcnt, rxcnt; };
struct exynos_mbox_msg { unsigned int chan_id, chan_type; };
struct queue { void *front, *base; };
struct acpm_info;
struct acpm_chan {
    struct acpm_info *acpm;
    struct mutex tx_lock;
    unsigned int qlen, mlen, id, seq;
    int poll_completion;
    struct queue tx;
    void *chan;
    atomic_ulong bitmap_seqnum[1];
};
struct acpm_info { unsigned int num_chans; struct acpm_chan *chans; void *dev; };
struct acpm_handle { struct acpm_info *info; };
#define handle_to_acpm_info(h) ((h)->info)
#define dev_dbg(...) ((void)0)
static u32 readl(void *p) { return *(u32 *)p; }
static void writel(u32 v, void *p) { *(u32 *)p = v; }
static void __iowrite32_copy(void *p, const u32 *s, unsigned int n) { memcpy(p,s,n*4); }
static void clear_bit_unlock(unsigned int b, atomic_ulong *p) { atomic_fetch_and(p, ~(1UL << b)); }
static int acpm_wait_for_queue_slots(struct acpm_chan *a, u32 idx) { return 0; }
static int acpm_prepare_xfer(struct acpm_chan *a, const struct acpm_xfer *x) {
    unsigned int bit = a->seq++ % 63;
    atomic_fetch_or(a->bitmap_seqnum, 1UL << bit);
    x->txd[0] = (bit + 1) << 16;
    return 0;
}
static int mbox_send_message(void *c, void *msg) {
    if (atomic_load(&force_error)) return -EIO;
    begin_request();
    return 0;
}
static void mbox_client_txdone(void *c, int err) { }
static int acpm_wait_for_singleslot_response(struct acpm_chan *a, const struct acpm_xfer *x) {
    int ret = finish_request();
    clear_bit_unlock(FIELD_GET(ACPM_PROTOCOL_SEQNUM, x->txd[0])-1, a->bitmap_seqnum);
    return ret;
}
static int acpm_wait_for_message_response(struct acpm_chan *a, const struct acpm_xfer *x) {
    /* Multi-slot response wait must remain outside the TX lock. */
    if (pthread_mutex_trylock(&a->tx_lock.lock)) abort();
    mutex_unlock(&a->tx_lock);
    return acpm_wait_for_singleslot_response(a,x);
}
'''

ACPM_MAIN = r'''
static u32 front, slot[20];
static struct acpm_chan channel = {
    .tx_lock = {PTHREAD_MUTEX_INITIALIZER}, .qlen=1, .mlen=16,
    .tx = {.front=&front, .base=slot},
};
static struct acpm_info info = {.num_chans=1, .chans=&channel};
static struct acpm_handle handle = {.info=&info};
static void *worker(void *arg) {
    pthread_barrier_wait(&start);
    for (int i=0; i<80; i++) {
        u32 cmd[4] = {0};
        struct acpm_xfer x = {.txd=cmd, .txcnt=4};
        if (acpm_do_xfer(&handle, &x)) abort();
    }
    return NULL;
}
int main(int argc, char **argv) {
    pthread_t t[3];
    channel.acpm=&info;
    pthread_barrier_init(&start,NULL,3);
    for (int i=0; i<3; i++) pthread_create(&t[i],NULL,worker,NULL);
    for (int i=0; i<3; i++) pthread_join(t[i],NULL);
    u32 cmd[4]={0};
    struct acpm_xfer x = {.txd=cmd,.txcnt=4};
    /* Both versions must retain the concurrent multi-slot response path. */
    channel.qlen=5;
    if (acpm_do_xfer(&handle,&x)) return 4;
    channel.qlen=1;
    atomic_store(&force_error,1);
    if (acpm_do_xfer(&handle,&x)!=-EIO) return 5;
    unsigned long leaked=atomic_load(channel.bitmap_seqnum);
    if (argc>1 && leaked) return 6;
    printf("overlaps=%d; multi-slot wait outside TX lock; send_error_bitmap=%lu\n",overlaps,leaked);
    return 0;
}
'''


def run(label, source, fixed, tmp):
    c = tmp / (label + ".c")
    exe = tmp / label
    c.write_text(source)
    subprocess.run(["cc", "-std=gnu11", "-pthread", "-O1", str(c), "-o", str(exe)], check=True)
    out = subprocess.check_output([str(exe)] + (["fixed"] if fixed else []), text=True)
    count = int(out.split("overlaps=")[1].split(";")[0])
    if fixed:
        assert count == 0, out
    else:
        assert count > 0, "Baseline failed to reproduce concurrent slot ownership"
    print(label + ": " + out.strip())


with tempfile.TemporaryDirectory(prefix="r8s-dvfs-test-") as d:
    tmp = pathlib.Path(d)
    for fixed in (False, True):
        cpu = TREE / "drivers/cpufreq/exynos990-cpufreq.c" if fixed else BASELINE / "drivers/cpufreq/exynos990-cpufreq.c"
        acpm = TREE / "drivers/firmware/samsung/exynos-acpm.c" if fixed else BASELINE / "drivers/firmware/samsung/exynos-acpm.c"
        tag = "fixed" if fixed else "baseline"
        run("cpufreq-" + tag, COMMON + CPU + function(cpu, "z3s_target_index") + CPU_MAIN, fixed, tmp)
        run("acpm-" + tag, COMMON + ACPM + function(acpm, "acpm_do_xfer") + ACPM_MAIN, fixed, tmp)
