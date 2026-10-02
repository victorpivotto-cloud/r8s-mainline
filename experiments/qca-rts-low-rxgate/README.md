# QCA6390: RTS low-only query with receive-gate observations

Diagnostic only, not a Bluetooth enablement patch. This combines the read-only
RX-gate query with exclusive ownership of gpq0-2 in the RAM-only RTS DT. It preserves the serdev first-member layout and tests version delivery before
any RTS pulse. The initial discrepancy came from an invalid lab structure
layout, not an established UART/TTY fault.

Apply these patches in order on the matching kernel base:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `../qca-rxgate/rxgate.patch`
5. `rts-low-rxgate.patch`

Use the RAM-only DT include and control/restoration checks described in
[`../qca-rts-gpio/`](../qca-rts-gpio/README.md). Do not combine this branch with
the RTS-pulse or TX/timing branch. Kernel and ramdisk remain the control;
GPIO CON1/DAT0/PUD1/DRV2 and unchanged TX/RX/CTS mux must be verified live.
No GPIO global numbers, hog descriptor theft or raw GPIO register writes.

Build matching modules on the host with W=1, preserving installed originals.
Explicitly load `r8s_qca_lab_rts_low_rxgate=1 r8s_serdev_lab_rxgate=1` and verify
both sysfs flags. The new flag is false/0400. Probe checks r8s, QCA6390,
gpq0/offset2/active-high flags and acquires output-low exclusively. Its managed
cleanup action restores LOW before descriptor release. LOW readback failures
must stop active testing; readback is not an electrical pad measurement.

Setup retains the one-shot and serdev/init115200/DT-oper3M guards. It powers the
Bluetooth function through the existing sequencer, holds RTS LOW, sets only the
host baud115200, queries version and checks product/ROM/SoC. It always exits
negatively before ordinary HCI initialization. `serdev_hu` remains the first member,
checked by `BUILD_BUG_ON(offsetof(struct qca_serdev, serdev_hu) != 0)`. No HIGH call, baud command,
firmware/NVM upload, IBS, retry, build-info query or pairing is performed.

The inherited serdev hook observes at most eight RX callbacks before its ready
gate, and QCA logs at most eight receives including phase0. This delta adds
power-on/host-init/query-exit timestamps using the same `ktime_get_ns` basis.
No packet payload or address is logged. Phase boundaries and the log cap remain
measurement limits; UART counts alone do not identify or timestamp a response.

Run one finite30s trial with health/boot/frequency guards, bounded unload,
original hash/srcversion/flag verification and LOW readback after cleanup.
Check full new kernel logs for WARNING/BUG/Oops/panic/KASAN/UBSAN and stop on
a new warning or a lost log window; checking RX counters alone is insufficient.
Only after successful restoration and health checks, return to the control DT
via a separate bounded RAM boot. Stop on access loss or restoration/health
failure. Do not write partitions, alter Wi-Fi or increase thermal/frequency
limits. The24h qualification remains deferred.

## Corrected result, 2026-10-02

With hci_uart at offset zero, the exclusive GPIO-low version query succeeded.
The query exit occurred3.727456ms after its start on the same ktime clock.
Serdev received21bytes with READY1/REGISTERED1; QCA received the same21bytes in
phase1, one event, no H4 error, refusal or partial frame. Version IDs matched
product0x10/ROM0x0200/SoC0x400a0200. UART TX5/RX21 matched these observations.
No new warning occurred; the negative exit deliberately kept MGMT empty.

The30s supervisor completed, both modules unloaded, and original modules,
hashes/srcversion/flags/limits and GPIO LOW were restored. This validates the
low-only diagnostic in this sample and supports the diagnosed layout error.
It does not qualify permanent GPIO ownership, suspend, the electrical pad or
Bluetooth operation. The subsequent corrected3M pulse is recorded in
[`../qca-rts-gpio/`](../qca-rts-gpio/README.md).

An earlier private trial put GPIO before hci_uart, causing RX/write-wakeup
WARN_ON before instrumentation. Its timeout was invalid evidence of a UART or
physical RTS fault. Those artifacts are retired; only the corrected branch is
published here. The original RX-gate control retained the correct layout.

W=1 compilation, the offset-zero assertion and exact public patch sequence
checks passed; original sources were restored byte for byte. No firmware/NVM,
GPIO HIGH, baud command, pairing or24h qualification occurred in this low-only
trial. Images, firmware and raw logs remain private.
