# QCA6390: one GPIO RTS baud diagnostic at 1 Mbaud

Diagnostic only; this does not enable Bluetooth. It tests one distinct
hypothesis after the corrected 3 and 3.2 Mbaud GPIO trials: integer-divisor
quantization. With the DT's declared 200 MHz clock, 1 Mbaud has total divisor
200, UBRDIV 11 and fraction 8, with zero nominal quantization error. The
previous rates have about 1% error. These calculations do not measure the
physical UART clock, establish receiver tolerance or prove clock causality.

Linux maps 1 Mbaud to QCA code `0x0b`, giving H4 command
`01 48 fc 01 0b`. Inclusion in that table does not establish support by this
specific Hastings ROM. This is one comparison, not a baud sweep; a negative
result must not trigger repeated trials or firmware/parser changes.

Apply on the matching kernel base, in this order:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `../qca-txobserve/txobserve.patch`
5. `../qca-delay-before-drain/delay-before-drain.patch`
6. The corrected `../qca-rts-gpio/rts-gpio.patch` from `6e602d7` or later.
7. `rts-1m.patch` here, instead of the 3.2 Mbaud delta.

Use the RAM-only GPIO DT include from `../qca-rts-gpio/`. Preserve the original
kernel/ramdisk and installed modules. Raw DT max-speed remains 3 Mbaud as a
probe guard; only the opt-in OPER path returns 1 Mbaud. This experiment needs
no UART ceiling patch or clock change. The first-member hci_uart assertion,
board/SoC/descriptor checks and one-shot guard remain intact.

Build matching modules on the host with W=1. Explicitly load
`r8s_qca_lab_rts_1m=1 r8s_serdev_lab_tx=1` and verify both flags. QCA defaults
off with read-only permissions. Setup validates version at 115200, raises
GPIO RTS, sends one baud command, waits 20 ms before draining TX, switches
the host to 1 Mbaud and restores LOW before querying. API-selected rates must
match the requested rates. Only after a timeout does it make one host-only
return/query at 115200. All exits restore LOW and abort before TLV/NVM, IBS,
retries or ordinary HCI initialization. GPIO DAT readback is not pad voltage.

Use a finite 30 s supervisor with warning, boot, thermal, failsafe and frequency
guards, bounded unload, original hashes/srcversion/flags/limits and LOW
restoration checks. After successful restoration and health checks, return
to the original control kernel/DT in a separate bounded RAM boot. Stop active
tests and automatic boots on warning, access loss, guard or restoration
failure. Do not write partitions, change Wi-Fi, raise limits, perform pairing
or start the deferred 24 h qualification. Keep raw logs/images/firmware private.

## Result

One finite trial on 2026-10-02 produced:

- Initial version at 115200 matched product 0x10, ROM 0x0200 and SoC 0x400a0200.
- GPIO DAT readback changed LOW → HIGH → LOW; the HIGH-to-LOW observation
  interval was 23.818923 ms. Serdev accepted all five command bytes before
  draining TX. The API reported 1000000 after the host switch.
- The 1 Mbaud version query timed out after about 2.02 s. One host-only return
  to 115200 received a valid version again.
- RX phases 1/5 each had 21 bytes and one event; phases 2/3/4 were empty,
  without H4 errors, registration refusals, partial frames or an observed
  fc48 Command Complete. UART counters increased TX 20/RX 42; MGMT was empty
  because the diagnostic deliberately aborted HCI setup.
- The finite window passed without new warnings or health faults. Both
  module removals completed and original hashes/srcversion/flags/limits and
  GPIO LOW were restored.

This negative result does not support high-rate divisor quantization as a
sufficient explanation for the failure: a rate with zero nominal error also
failed in this sequence. It does not rule out physical clock/signal problems,
unsupported 1 Mbaud in this ROM or a different command/state contract. No
physical rate was measured, and UART divisors were calculated from source,
not read back in this trial. Do not repeat the unchanged baud matrix.

W=1 compilation and exact patch-sequence checks passed; original sources were
restored byte for byte. Final control RAM restoration is recorded in the
shared UART document.
