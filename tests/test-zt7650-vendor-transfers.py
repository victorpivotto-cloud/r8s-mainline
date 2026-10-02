#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Characterize actual vendor helpers with synthetic I2C returns, on the host.

Supply zinitix_ts.c from the pinned vendor revision documented in
PERIFERICOS-PENDENTES.md. No device access; this is not a corrected driver.
Secure-touch paths, scheduling, timing and real concurrency are not modeled.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def extract(source, name):
    match = re.search(
        rf"^static inline s32 {name}\([^{{]*\{{.*?^\}}", source, re.M | re.S
    )
    if not match:
        raise ValueError(f"vendor helper not found: {name}")
    return match.group()


STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef int32_t s32;
enum { POWER_OFF = 0, POWER_ON = 1, NOTHING = 0, PROBE = 1, ESD_TIMER = 2 };
struct zt_ts_info;
struct i2c_client { int dev; struct zt_ts_info *info; };
struct zt_ts_info {
    int tsp_pwr_enabled, i2c_mutex, comm_err_count, work_state, tmr_work;
    struct i2c_client *client;
};
static int send_result, recv_result, sends, recvs;
static struct zt_ts_info info;
static struct i2c_client client = { .info = &info };
#define i2c_get_clientdata(c) ((c)->info)
#define input_err(...) ((void)0)
#define zt_delay(...) ((void)0)
#define usleep_range(...) ((void)0)
#define esd_timer_stop(...) ((void)0)
#define queue_work(...) ((void)0)
static void mutex_lock(int *m) { assert(*m == 0); *m = 1; }
static void mutex_unlock(int *m) { assert(*m == 1); *m = 0; }
static int i2c_master_send(struct i2c_client *c, const u8 *p, int n) {
    (void)c; (void)p; assert(n == 2); assert(info.i2c_mutex == 1);
    sends++; return send_result;
}
static int i2c_master_recv(struct i2c_client *c, u8 *p, int n) {
    (void)c; assert(n == 16); assert(info.i2c_mutex == 1);
    recvs++; assert(recv_result <= n);
    if (recv_result > 0) memset(p, 0x3c, recv_result);
    return recv_result;
}
static void reset(int tx, int rx) {
    memset(&info, 0, sizeof(info)); info.client = &client;
    info.tsp_pwr_enabled = POWER_ON; info.work_state = PROBE;
    send_result = tx; recv_result = rx; sends = recvs = 0;
}
"""

CASES = r"""
int main(void) {
    u8 bytes[16];
    reset(2, 16); memset(bytes, 0xa5, sizeof(bytes));
    assert(read_data(&client, 0x0200, bytes, 16) == 16);
    assert(sends == 1 && recvs == 1 && info.i2c_mutex == 0);
    for (int i = 0; i < 16; i++) assert(bytes[i] == 0x3c);
    reset(2, 16); assert(write_cmd(&client, 3) == I2C_SUCCESS);
    assert(sends == 1 && recvs == 0 && info.i2c_mutex == 0);

    reset(-EIO, 16); assert(read_data(&client, 0x0200, bytes, 16) == -EIO);
    assert(sends == RETRY_CNT && recvs == 0 && info.comm_err_count == 1);
    assert(info.i2c_mutex == 0);
    reset(-EIO, 16); assert(write_cmd(&client, 3) == -EIO);
    assert(sends == RETRY_CNT && recvs == 0 && info.comm_err_count == 1);
    assert(info.i2c_mutex == 0);
    reset(2, -EIO); assert(read_data(&client, 0x0200, bytes, 16) == -EIO);
    assert(sends == 1 && recvs == 1 && info.comm_err_count == 1);
    assert(info.i2c_mutex == 0);
    reset(2, 16); info.tsp_pwr_enabled = POWER_OFF;
    assert(read_data(&client, 0x0200, bytes, 16) == -EIO);
    assert(write_cmd(&client, 3) == -EIO && sends == 0 && recvs == 0);
    puts("PASS: exact lengths, negative errors, retry bound, power-off guard");

    for (int short_tx = 0; short_tx < 2; short_tx++) {
        reset(short_tx, 16);
        assert(read_data(&client, 0x0200, bytes, 16) == 16);
        assert(sends == 1 && recvs == 1 && info.comm_err_count == 0);
        assert(info.i2c_mutex == 0);
        reset(short_tx, 16); assert(write_cmd(&client, 3) == I2C_SUCCESS);
        assert(sends == 1 && recvs == 0 && info.comm_err_count == 0);
        assert(info.i2c_mutex == 0);
    }
    puts("REPRODUCED: short send 0/1 accepted by read_data and write_cmd");
    for (int short_rx = 0; short_rx < 16; short_rx++) {
        reset(2, short_rx); memset(bytes, 0xa5, sizeof(bytes));
        assert(read_data(&client, 0x0200, bytes, 16) == 16);
        assert(sends == 1 && recvs == 1 && info.comm_err_count == 0);
        assert(info.i2c_mutex == 0);
        for (int i = 0; i < 16; i++)
            assert(bytes[i] == (i < short_rx ? 0x3c : 0xa5));
    }
    puts("REPRODUCED: short receive 0..15 reported as 16, tail unchanged");
    puts("Host characterization only; no hardware transfers or driver fix.");
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cc", default="cc", help="C compiler executable")
    args = parser.parse_args()
    source = args.source.read_text()
    constants = []
    for name in ("DELAY_FOR_TRANSCATION", "DELAY_FOR_POST_TRANSCATION",
                 "I2C_SUCCESS", "RETRY_CNT"):
        match = re.search(rf"^#define\s+{name}\s+([0-9]+)\s*$", source, re.M)
        if not match:
            raise ValueError(f"numeric vendor constant not found: {name}")
        constants.append(f"#define {name} {match[1]}\n")
    program = (STUBS + "".join(constants) + extract(source, "read_data")
               + extract(source, "write_cmd") + CASES)
    with tempfile.TemporaryDirectory(prefix="zt7650-transfer-mock-") as tmp:
        path = Path(tmp)
        (path / "mock.c").write_text(program)
        subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(path / "mock.c"), "-o", str(path / "mock")], check=True)
        subprocess.run([str(path / "mock")], check=True)


if __name__ == "__main__":
    main()
