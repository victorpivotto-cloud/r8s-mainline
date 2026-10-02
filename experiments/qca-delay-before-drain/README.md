# QCA6390: 20 ms delay before UART drain

This diagnostic branch applies after the four patches in `../qca-txobserve/README.md`, instead of `../qca-baud-same/baud-same.patch`. It moves the opt-in 20 ms wait from after `serdev_device_wait_until_sent` to before it. DT and target baud remain3M. Defaults and the inherited QCA6390/one-shot/abort-before-firmware guards remain unchanged. Enable the same two read-only lab parameters and use a single bounded trial followed by original-module restoration.

The reference HAL `SetBaudRateReq` uses write -> sleep20ms -> tcdrain -> hostbaud -> flowon -> readACK. The previous lab used drain -> sleep20ms. This branch tests that ordering difference only; queue-empty is still not guaranteed full acceptance, `msleep` is not an exact20ms delay, and the lab does not implement a synchronous ACK wait or prove physical RTS movement. It is not a complete HAL port.

Observed on r8s, 2026-10-02: one write accepted5/5bytes about205us before queue-empty. From the pre-delay marker to drain-return was about23.328ms (includes the sleep and drain); the next high-speed query began almost immediately afterward. The3M query still timed out (~2.009s). Returning only the host to115200 restored the version response (~3.65ms). RX phases1/5 each had21bytes/one event; others had zero, including no baud ACK. UART TX+20/RX+42; MGMT controllers empty.

The30s trial completed with successful unload/restoration of original module hashes, parameters and limits, without reboot, firmware upload or partition writes. Reordering the delay did not resolve this sample. Instrumentation and physical-measurement limits from qca-txobserve apply. Avoid repeating timing variants without a new, testable cause.
