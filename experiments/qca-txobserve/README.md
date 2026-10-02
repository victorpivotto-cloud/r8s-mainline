# QCA6390: baud-command software TX observation

Opt-in diagnostic delta for the r8s Exynos 990 Samsung serdev UART. This is not a Bluetooth enablement fix.

Apply to the same kernel base used by the existing experiments, in this order:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `txobserve.patch`

Build `hci_uart.ko` on the host with the matching kernel configuration/ABI and `W=1`. Both read-only parameters must be explicitly enabled at load: `r8s_qca_lab_rxphase=1 r8s_serdev_lab_tx=1`. The inherited QCA guard allows one diagnostic setup per module load and aborts before TLV/NVM/IBS/retry. Use the bounded trial and restoration conditions from the RX experiment; never overwrite installed modules.

Only the known five-byte H4 `0xfc48` baud-command skb is tagged. Up to eight serdev write return values are logged (remaining length, accepted length, observation time); no TX payloads. QCA also records queue-empty and wait-until-sent return times. Partial writes retain the tag. This deliberately observes the existing queue/drain ordering without adding a flush or waiting for a new completion.

## Observed on r8s, 2026-10-02

At 3 Mbaud with the inherited 20 ms delay:

- One write accepted all five bytes, about 235 us before queue-empty was observed.
- Wait-until-sent returned about 7.440 ms after the queue-empty observation.
- RX phase counters again reported 21 bytes for the first version query at 115200, zero during baud/high-speed query/host return, and 21 bytes for the final host-only 115200 query.
- The high-speed query timed out; returning only the host to 115200 produced a version response. No baud Command Complete was observed.
- UART counters increased by TX20/RX42. The MGMT controller list remained empty.
- A single bounded trial ended normally; original modules, hashes, parameters and frequency limits were restored, without a reboot or firmware upload.

The suspected queue-before-write race did not occur in this sample. This does not establish controller receipt, physical baud, or FIFO/shift-register completion. `wait_until_sent` returns void; a timeout is not explicitly reported. Log timestamps are observations after each call and printk can perturb timing. Do not infer universal correctness from one run.

## Instrumentation limits

The lab uses `skb->mark` as a temporary tag. This aliases reserved tailroom, so this is restricted to this linear command path, which performs write/pull/free and does not request skb available room afterward. It must not be generalized to arbitrary TX traffic. A longer packet's continuation could theoretically resemble the command; the inherited lab sends only its fixed commands, with no discovery, ACL or firmware payload. The eight-entry cap can omit final acceptance if many zero/partial writes occur; a trace exhausting the cap is inconclusive. No partial write or exhausted cap occurred in the recorded sample.

The counter continues incrementing after the log cap; wraparound is outside the bounded one-shot trial. Negative write handling is an existing transport issue, not corrected here. Do not ship this instrumentation as a production driver or change transport ordering without new evidence.
