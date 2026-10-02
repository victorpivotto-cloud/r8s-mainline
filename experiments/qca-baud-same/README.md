# QCA6390: baud command with unchanged speed

Diagnostic only, not Bluetooth enablement. Apply the four patches listed in `../qca-txobserve/README.md`, then this `baud-same.patch` (an alternative to the delay-before-drain branch). Build matching host modules with W=1 and enable the same two lab parameters. Use a single bounded trial and restore the installed modules afterward. No firmware, discovery or pairing is attempted.

The QCA6390 opt-in path overrides only the local operational speed to 115200, mapping to baud-command value0. DT remains 3M, and the existing QCA6390/DT/one-shot safety guards remain. The host and controller are asked to stay at the known responsive speed. The subsequent version query is relabelled accurately; timeout fallback remains bounded and only runs if needed.

Observed on r8s, 2026-10-02: all five command bytes were accepted in one serdev write, about13.7us before queue-empty; drain-return followed about7.836ms later. The subsequent 115200 version query succeeded in about3.61ms, but no baud Command Complete was observed. RX phases1 and3 each had21bytes/one event; all other phases had zero. UART totals TX+15/RX+42 matched the fixed commands and version responses. MGMT had no controller. Original modules/settings were restored without reboot.

This removes high-speed UART divisors from this sample, but does not establish that the chip ignored the command: unchanged-baud semantics are not proven. No physical UART measurement or full firmware qualification was done. Instrumentation limits from qca-txobserve still apply.
