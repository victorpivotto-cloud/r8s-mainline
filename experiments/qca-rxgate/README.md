# QCA6390: read-only version and RX readiness control

Diagnostic only. This branch follows the RTS candidate's unexpected UART RX21/QCA active-phase RX0 discrepancy. It runs on the original r8s DT with the static RTS-low GPIO hog. It observes serdev RX readiness before the existing gate and QCA receive entry, including phase0, without changing either transport's return behavior.

Apply after `../qca-baud-ack/baud-ack.patch`, `../qca-baud20/baud20-3m.patch`, and `../qca-rxphase/rxphase.patch`. Apply `rxgate.patch` instead of the TX/RTS/build-info branches. Build matching modules on the host with W=1. Preserve originals and load explicitly with `r8s_qca_lab_rxgate=1 r8s_serdev_lab_rxgate=1`; verify both flags. Do not install or enable autoload of the lab modules.

The inherited guard checks QCA6390/serdev/INIT115200/DT-oper3M and permits only one setup per module load. Actual traffic is just a host initialization at115200 and one version query, followed by product/ROM/SoC checks and a negative diagnostic exit. No baud command, GPIO transition, build-info query, TLV/NVM, IBS or retry occurs. A zero query result still aborts setup with ECANCELED, preventing normal HCI initialization.

Each RX hook logs at most eight observations: count, readiness/registration or phase, and time. No packet payload, address or firmware is logged. Serdev observation is after validating `hu` but before PROTO_READY; the original not-ready return remains unchanged. QCA observation is before its REGISTERED check. The inherited active-phase counters remain available. Instrumentation can perturb timing; no hook measures the physical wire or UART FIFO directly. The cap and phase boundaries can omit activity, so absence of a log is not a universal loss diagnosis.

Use a single finite30s supervisor with health/boot/frequency guards and original DT/hog checks, bounded unload, then hash/srcversion/flag restoration. Stop on access loss or restoration/health failure. No reboot or partition write is needed for this control query.

## Observed on r8s, 2026-10-02

After the separate bounded RAM return to the original DT, one control query succeeded:

- Serdev received21bytes with PROTO_READY1/REGISTERED1.
- QCA received the same21bytes in phase1, REGISTERED1.
- The version IDs matched product0x10, ROM0x0200 and SoC0x400a0200.
- Phase1 recorded one event, no H4 error, refusal or partial frame; other phases were empty. No phase0 observation was logged during this control sample.
- UART TX+5/RX+21 matched the QCA observation. MGMT had no controller because setup deliberately aborted.
- Both module removals completed; original hashes/srcversion/parameters/limits, RTS-low hog and normal health were confirmed. No lab unit remained active.

This demonstrates successful delivery through these gates in the control sample. It does not locate the RTS candidate's21bytes, establish their payload or prove that descriptor ownership caused its timeout: the two samples have different RAM boots and instrumentation. The planned RTS HIGH pulse remains unexecuted. A useful next experiment would add these bounded entry observations to a low-only candidate query before attempting any pulse, controlling startup/baud state and requiring initial version success.

The public patch sequence equals the compiled source, W=1 completed without warnings, and original source files were restored byte for byte. Raw logs, images and device identifiers remain private. Bluetooth enablement and24h qualification remain pending.
