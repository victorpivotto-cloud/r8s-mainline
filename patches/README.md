# Patches — what is ours and what is not

**Read this before submitting anything anywhere.** Some of these files are not
our work, and we do not want to take credit for them.

| Patch | Origin |
|---|---|
| `0000-pci-exynos-suporte-exynos990-DA-COMUNIDADE.patch` | **Not ours.** Exynos 990 support for `pci-exynos.c` (regmap, CMU gates, `is_exynos990`, PERST), from the exynos990-mainline / z3s work. Included only so the tree builds. |
| `0001-pci-exynos-msi-host-v0-NOSSO.patch` | **Ours.** MSI on the host-v0 ELBI layout: bit 29 in status/enable, dispatch to `dw_handle_msi_irq()`. 31 lines added. **This is the upstream candidate.** |
| `0002-dwc-host-export-msi-irq-e-conceder-doorbell.patch` | Ours. `EXPORT_SYMBOL_GPL(dw_handle_msi_irq)` (needed once the glue is a module) + S2MPU grant for the MSI doorbell page. |
| `0003-mhi-conceder-s2mpu-nos-buffers.patch` | Ours. S2MPU grants around the BHI buffer and BHIE table, plus diagnostics. |
| `0004-ath11k-mascara-dma-32-bits.patch` | Ours. `ATH11K_PCI_DMA_MASK` 36 → 32, because EL2 refuses to grant above 4 GB. |
| `0005-kconfig-makefile.patch` | Ours. Wiring for the new drivers. |
| `0006-qrtr-diagnostico.patch` | Ours, **diagnostics only** — prints the offending buffer's physical address. Drop it for anything but debugging. |

## About 0001, the upstream candidate

It is deliberately small and does one thing. Before sending it to
`linux-pci` / `linux-samsung-soc`, note:

- It depends on `0000`, which is not upstream. Upstreaming the MSI change on its
  own only makes sense once Exynos 990 support for `pci-exynos.c` lands.
- Samsung's own device tree sets `use-msi = "false"`, so **no Samsung device
  needs this**. The justification is that `ath11k` has no INTx path at all.
- It was tested on exactly one device (SM-G780F). The bit-29 layout is documented
  for "host-v0" ELBI; other Exynos generations use a different layout.

## Diagnostics to drop before production

`0003` and `0006` add `dev_info` calls that were essential while debugging and
are noise afterwards. `0003`'s grants are functional and must stay; its prints
are not.

## Runtime patches

- `0007-acpm-single-slot-ownership.patch`: ownership until response consumption,
  sequence cleanup on send failure and ACK readback; focused changes to the
  community provider, not a vendored copy of it.
- `0008-cpufreq-thermal-sensor-failsafe.patch`: shared transaction mutex,
  cooling registration and independent sensor/heartbeat QoS safety request;
  includes the new exported API header. Baselines and limits in
  `docs/ACPM-DVFS-TERMICA.md`.
- `0009-mesa-g77-model-DA-COMUNIDADE.patch`: **not ours**, Mali-G77 model and
  tilebuffer entry documented by the z3s port; tested here on the FE using
  an isolated Mesa prefix. See `docs/GPU-MALI-G77.md`.

The runtime modules/tests accompany these patches. New code and modifications
are experimental; provider/cpufreq origins remain the Exynos990 community port.

`0010-thermal-mode-hwmon.patch` is a follow-up to the runtime module.
Build, callback mock and hardware mode/unload/recovery tests passed on #25.
Runtime sources include it; sustained qualification remains pending. See `docs/ACPM-DVFS-TERMICA.md`.

`0011-max17042-health-overflow.patch` widens the absent-voltage-limit arithmetic
to s64. Source-function mock and hardware RAM boot passed; charging settings
are unchanged. See `docs/BATERIA-HEALTH.md`.


`0012-acpm-descriptor-diagnostic.patch` is diagnostic only: one raw shared
memory word in the existing channel initialization log, with an offset
assertion. arm64 build, patch reproduction and RAM boot passed; the active
DVFS descriptor reports word_0c=2 with poll0/qlen1. It does not fix late ACK or alter DVFS. Baseline and
interpretation are in `docs/ACPM-DVFS-TERMICA.md`.


`0013-acpm-rx-snapshot-diagnostic.patch` adds a disabled-by-default, root-only
one-shot channel-5 TX/RX snapshot after a normal ACK. arm64 object build,
source-function mock, patch reproduction and RAM boot passed. One normal
no-payload transaction showed matching TX/RX sequence; freshness and timeout
recovery remain unverified. Printing happens after ACK cleanup while the transaction mutex is
held, so it can affect timing. This does not fix stale ACK acceptance.

`0014-max77705-health-read.patch` propagates failed health-register reads and
defines UNKNOWN for prequalification instead of returning an untouched output.
Actual-function baseline/corrected mocks, arm64 W=1 object compilation and exact
patch reproduction passed. **No hardware load yet; does not fix PD or charging.**
See `docs/BATERIA-HEALTH.md` and `tests/test-max77705-health.py`.

`0015-max77705-getters-read-errors.patch` propagates field-read errors from
the input-current, charge-current and float-voltage getters before conversion.
Real-function baseline/corrected mocks and arm64 W=1 object compilation passed;
0014+0015 reproduced the compiled source without fuzz. **Host validation only;
does not change setters, charging policy or PD negotiation.** See
`tests/test-max77705-getters.py` and `docs/BATERIA-HEALTH.md`.
