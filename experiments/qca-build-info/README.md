# QCA6390: read-only build-info and HCI error origin

Diagnostic only, not a Bluetooth enablement patch. This branch stays at115200 and queries `0xfc00/subcommand0x20` (EDL_GET_BUILD_INFO), present in Linux btqca and the reference Hastings HAL. It does not change baud or upload firmware. Apply after:

1. `../qca-baud-ack/baud-ack.patch`
2. `../qca-baud20/baud20-3m.patch`
3. `../qca-rxphase/rxphase.patch`
4. `build-info.patch` here, instead of the TX/timing branches.

Build matching ARM64 modules on the host with W=1. The parameter is renamed to `r8s_qca_lab_build_info`, false/0400; explicitly load with `r8s_qca_lab_build_info=1` and verify its sysfs valueY and lab log before interpreting a run. Do not pass the old RX parameter or install for autoload. A flag mismatch can select ordinary driver setup, so use a validated finite supervisor with the correct module/ABI/parameter, preserved originals and a single trial. All inherited QCA6390/serdev/INIT115200/DT-oper3M and one-shot guards remain. DT3M is a control-hardware guard; the query itself uses115200.

The lab confirms version IDs, makes one build-info query, logs bounded event metadata and aborts before TLV/NVM/IBS/retries. If the query returns `-ETIMEDOUT`, the final same-opcode version query is skipped, conservatively avoiding ambiguous late-response matching. Otherwise its result is only another observation. The setup exit always returns an error (the measured error, or ECANCELED if zero); the HCI core is not allowed to proceed with normal initialization.

Up to four phase2 event headers are logged. Command Complete includes its five-byte event/header/opcode fields; other events include at most four bytes. The first return byte is separately recorded only when len>=6, event=CommandComplete and opcode=0xfc00. No build label or remaining return payload is logged by this event hook. The query helper reports at most three return-prefix bytes if the transport returns a buffer; it does not parse or claim firmware semantic success.

## Results on r8s, 2026-10-02

Three bounded30s rounds added instrumentation only as needed:

- Initial query: version21bytes, build-info10bytes/one event, final version21bytes. The build-info API returned-110. UART TX+15/RX+52; final version responded, but a same-opcode post-error query requires correlation caution.
- Event classification: build-info returned Command Complete, event0x0e, event-skb len9 (10bytes including H4), ncmd1/opcode0xfc00. Return-110 occurred about2.66ms after starting the query. UART TX+10/RX+31; final query skipped.
- Status observation: same event/header and first return byte16 decimal=`0x10`; API returned-110 within a few milliseconds. Final query skipped. RX phases1/2 each one event,21/10bytes; no H4 errors or REGISTERED refusals. UART TX+10/RX+31. MGMT still had no controller.

In this kernel, `hci_cmd_complete_evt` treats the first return byte of an opcode without a dedicated CC handler as status. `__hci_cmd_sync_sk` maps a completed request's result through `bt_to_errno`, which maps0x10 toETIMEDOUT. Therefore this build-info result is an error response translated to errno, not expiry of the host response-wait window. The vendor meaning of0x10 and the current application/download state are not established by that mapping.

This does not reinterpret the earlier high-baud trials: those waited roughly2s and had zero RX in their baud/query phases. It does not justify ignoring status, relaxing a parser, entering another chip mode, resetting the shared chip or uploading full firmware. The next investigation remains the command/state contract and physical RTS behavior.

All rounds ended with successful unload, original hashes/srcversion/flags/frequency limits restored, same kernel/boot, clean guard masks, normal sensors and no failed units. No reboot, partition write, firmware upload, Wi-Fi configuration change or24h qualification occurred. W=1 builds and exact public patch sequence were checked. Claude reviewed sanitized public source only, without tools/MCP; local checks verified the inherited negative setup exit, explicit new flag and same-opcode ambiguity. Raw logs and device identifiers remain private.
