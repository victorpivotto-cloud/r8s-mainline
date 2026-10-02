# QCA6390: exclusive GPIO RTS diagnostic on r8s

Experimental diagnostic, not a Bluetooth enablement fix. The previous r8s configuration holds active-low RTS low through a GPIO hog. Samsung UART flow-control calls manipulate UART registers and do not prove a transition on this GPIO.

Apply matching kernel patches in order:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `../qca-txobserve/txobserve.patch`
5. `../qca-delay-before-drain/delay-before-drain.patch`
6. `rts-gpio.patch`

Include `rts-lab.dtsi` last in the matching r8s board DTS. It removes the GPIO hog, selects GPIO output-low on the parent UART's default pinctrl, and gives the Bluetooth child an experimental descriptor property. TX/RX/CTS remain on their original UART mux. Pull1/drive2 preserve the control board's observed configuration; these values are board-specific. Do not reuse global GPIO numbers or steal a descriptor from the hog. This property is a lab interface, not an upstream binding.

Use a RAM boot only, with the original kernel/ramdisk and a reviewed DT. Verify the live DT, GPIO CON1/DAT0/PUD1/DRV2, original modules and health before the trial. Build matching modules on the host with W=1; preserve installed originals. Load the lab explicitly with `r8s_qca_lab_rts_gpio=1 r8s_serdev_lab_tx=1`, and verify both flags. An omitted flag selects ordinary driver behavior.

Probe validates the r8s machine, QCA6390, GPIO bank gpq0, offset2 and active-high descriptor flags. It acquires an exclusive output-low descriptor and registers a devres action to restore LOW before releasing it. Setup remains one-shot and checks the inherited serdev/init115200/oper3M guards. A valid initial version is required before raising RTS, sending one baud command, waiting20ms before drain, switching host to3M and lowering RTS. A failed high-speed query permits one host-only return/query at115200. Every exit restores LOW and aborts normal HCI initialization before firmware/NVM/IBS/retries.

Use a finite30s supervisor with thermal/failsafe/boot/frequency guards, bounded unload, original hash/srcversion/flag verification, and LOW readback after cleanup. Return to the original DT via a separate bounded RAM boot only after successful restoration and health checks. Stop active work on access loss or restoration/health failure. No partition write, shared-chip reset, Wi-Fi configuration change or24h qualification is involved.

## Layout correction — supersedes the initial trial

The initial public patch in commit e5c7d00 is invalid and must not be used.
It inserted `lab_rts` before `qca_serdev.serdev_hu`. Serdev RX/write-wakeup
callbacks cast `serdev_device_get_drvdata()` directly to `struct hci_uart *`,
so the embedded hci_uart must remain the first member. The invalid module
triggered WARN_ON in those callbacks, before the RX instrumentation, and
rejected delivery. UART RX21/QCA RX0 is explained by that instrumentation
error; it is not evidence of a physical RTS fault or a UART→TTY loss.

The current patch keeps hci_uart first, places lab_rts after it, and adds
`BUILD_BUG_ON(offsetof(struct qca_serdev, serdev_hu) != 0)` at probe. W=1 and
exact public source checks validate this invariant. Treat the observations
below as an invalid historical trial. The GPIO pulse still has no valid
hardware result until a corrected module passes the initial version guard.
Future supervisors must check full new kernel logs for WARNING/BUG/Oops/panic,
not just protocol counters, and stop active testing on a new warning.

## Initial invalid trial, 2026-10-02

The RAM candidate booted normally. GPIO configuration matched the control and the lab acquired the descriptor LOW. However, the initial version query at115200 timed out after about2.036s. All active QCA RX phase counters remained zero. The guard aborted setup: **RTS HIGH and the baud transition were not executed**. This result neither validates nor rejects the pulse hypothesis.

UART counters increased TX5/RX21 across the30s window, despite the zero active QCA counters. Those21bytes are not a validated version response in this trace. The callback WARN_ON caused by the invalid structure layout accounts for rejected delivery before the instrumentation. GPIO DAT readback is not an electrical pad measurement.

Both module removals completed; original modules, hashes, flags and limits were restored with RTS LOW and normal health. A single bounded RAM return restored the original DT and GPIO hog. The follow-up `../qca-rxgate/` control kept the correct structure layout and delivered a valid version, without another baud command or GPIO pulse. It does not validate the invalid GPIO module.

The public patch sequence was checked against the exact compiled sources. The DTS include compiles against the board tree; the RAM image's semantic changes were independently restricted to the five relevant DT nodes, with kernel/ramdisk/header preserved except DT size. Raw logs, images and device identifiers remain private.
