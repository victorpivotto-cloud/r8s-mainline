# QCA6390: corrected GPIO RTS pulse at3.2Mbaud

Experimental diagnostic, not Bluetooth enablement. This tests the distinct
combination of a GPIO RTS transition and the3.2M rate selected by the reference
Hastings HAL. Earlier3.2M trials kept RTS on a static-low hog. The initial GPIO
patch in e5c7d00 had an invalid structure layout; do not use it.

The built-in UART needs `../qca-uart-3200/uart-ceiling.patch`, with its opt-in
parameter default off. Apply the following Bluetooth patches separately:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `../qca-txobserve/txobserve.patch`
5. `../qca-delay-before-drain/delay-before-drain.patch`
6. The **corrected** `../qca-rts-gpio/rts-gpio.patch` from6e602d7 or later.
7. `rts-3200.patch` here, instead of the old `qca-3200.patch`.

Use the RAM-only GPIO DT include from `../qca-rts-gpio/`. The DT max-speed stays
3M as a control guard; this lab overrides only OPER to3.2M. Probe validates raw
DT-oper3M, r8s/QCA6390/gpq0/offset2/flags0 before exclusive output-low acquisition.
The embedded hci_uart stays first and its offset-zero assertion is retained.
No production binding or installed module is changed.

Build matching modules on the host with W=1, preserve originals, and verify
kernel/ABI, DT, GPIO LOW, flags and health. Enable the existing UART ceiling only
within the finite trial. Load `r8s_qca_lab_rts_3200=1 r8s_serdev_lab_tx=1`; both
must be verified. The QCA flag is false/0400. The UART flag is false/0600 and
must return to N **before** original modules are reloaded.

The one-shot branch first validates version at115200, raises GPIO RTS, sends
one fc48 baud command, waits20ms before drain, changes host to3.2M and lowers
RTS. API-selected baud must equal115200 or3200000 as appropriate. After a
high-speed timeout, it makes one host-only return/query at115200. All exits
restore GPIO LOW and abort normal HCI setup before TLV/NVM/IBS/retries.

Use a30s supervisor with kernel-warning, health, boot and frequency guards,
bounded unload, original hash/srcversion/parameter/LOW restoration, then a
separate bounded RAM return to the original kernel/DT after checks pass.
Stop on warning, access loss, guard failure or incomplete restoration; do not
cycle boots automatically. No partition write, CMU/thermal/frequency increase,
Wi-Fi change, pairing or24h qualification is part of this experiment.

## Observed, 2026-10-02

One corrected3.2M trial ran after the corrected GPIO-low and3M trials:

- Initial version115200 matched product0x10/ROM0x0200/SoC0x400a0200.
- GPIO DAT readback changed0→1→0, with a HIGH-to-LOW observation interval of
  23.879406ms. Serdev accepted all five baud-command bytes.
- The API and UART selected3200000, with UBRDIV2/frac14 and declared clock200MHz.
  AFC was0 during the change and1 before the query.
- The3.2M query timed out after about2s. Returning only the host to115200
  produced another valid version. RX phases1/5 each had21bytes/one event;
  phases2/3/4 were empty, without H4 errors, registration refusals, partial
  frames or an observed fc48 Command Complete. UART TX20/RX42 matched.
- The30s window completed without warnings or health faults. Both removals
  completed; the UART ceiling returned toN before original module reload.
  Original hashes/srcversion/flags/limits and GPIO LOW were confirmed.

This does not resolve high-baud communication. It tests this3.2M GPIO/timing
combination once; it does not measure physical baud or voltage at the pad,
prove controller receipt, identify command/state semantics or rule out late
responses outside the window. Do not repeat this unchanged matrix or relax
parsers/upload full firmware on these observations. The remaining useful
investigation is the fc48 command/controller-state contract and independent
verification of the UART clock/signals.

Host W=1 compilation and exact public patch sequences passed; original sources
were restored byte for byte. Images, firmware, raw logs and device identifiers
remain private. Final control restoration is recorded in the shared UART doc.
