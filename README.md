# Mainline Linux on the Samsung Galaxy S20 FE (SM-G780F, `r8s`)

Debian 13 on a mainline 6.12 kernel, booting on its own, with **Wi-Fi, microSD,
USB gadget networking and CPU DVFS working**.

> **Docs are in Portuguese.** This README is in English because the findings
> below are useful to anyone working on Exynos 990. Sorry for the mix.

```
S-Boot -> lk3rd (sda13) -> our kernel (sda33) -> Debian 13     ~22 s, no PC
```

---

## ⚠️ Read this first

- **Unlocking the bootloader trips Knox permanently.** Warranty is void, Samsung
  Pay / Secure Folder / Health stop working. There is no way back.
- **This can brick your phone.** Write **only** to `BOOT`, `RECOVERY`,
  `USERDATA` and the microSD. Never touch `BOOTLOADER` (sboot.bin), `EFS`,
  `SEC_EFS`, `KEYSTORAGE`, `UL_KEYS` or `HARX`.
- This is a **bench port**, not a product. See *Known problems* below — in
  particular, the S2MPU DMA grant is deliberately broad.

---

## What works

| | |
|---|---|
| Boot | autonomous, ~22 s, no host PC |
| Storage | UFS (root), **microSD** (33.58 MHz, auto-mounted) |
| **Wi-Fi** | **QCA6390 via ath11k**, 2.4 + 5 GHz, ~258 Mbit/s (Wi-Fi 6, 2 streams) |
| Networking | USB gadget (RNDIS + ACM) as a rescue path |
| CPU | DVFS on all 3 clusters (A55 / A76 / M5) |
| GPU | panfrost probes, render node present |
| Display | `simpledrm` on the bootloader framebuffer |
| Power | battery gauge + charger; **USB-C OTG VBUS** (max77705 boost) |
| Clock | `fake-hwclock` + `systemd-timesyncd` (the hardware RTC does not retain) |

## What does not

| | |
|---|---|
| Bluetooth | needs a UART node with `qcom,qca6390-bt` (same chip, rail already on) |
| Touch | Zinitix **ZT7650**; mainline `zinitix` speaks bt4xx/bt5xx only |
| Audio | ABOX not ported — no sound cards at all |
| Camera | no mainline support for the Exynos 990 ISP |
| **USB host** | xHCI comes up, but nothing enumerates (`-71`). See below |
| Thermal | no TMU node: the only zone is the battery gauge, stuck at 25 °C |
| Power-on | the phone **does not boot by itself** when power returns — needs the button |

---

## Three findings that were not published anywhere

### 1. MSI on the Exynos 990 PCIe controller

Upstream `pci-exynos.c` is the **exynos5433** driver and **does not wire MSI at
all**: `pp->msi_irq[0] = -ENODEV`, the handler only clears the pulse register,
and only INTA–INTD are enabled.

On the Exynos 990 ("host-v0" ELBI layout) the **MSI rising pulse is bit 29** of
both the status register (ELBI `0x000`) and the enable register (ELBI `0x00c`).
Samsung never uses this path — their device tree sets `use-msi = "false"` and
runs Wi-Fi on legacy INTx. **`ath11k` has no INTx path, so MSI is mandatory.**

Effect, measured:

| | before | after |
|---|---|---|
| BHI firmware wait | 20.3 s (timeout) | **57 ms** |
| controller IRQ count | 0 | fires |
| device `ERRCODE` | 0x9 | **0x0** |

→ `patches/0001-pci-exynos-msi-host-v0-NOSSO.patch` — 31 lines, **the upstream
candidate**. It sits on top of `0000-...-DA-COMUNIDADE.patch`, which is the
community's Exynos 990 support and **not our work**. See `patches/README.md`.

### 2. QCA6390 behind the Samsung S2MPU

The Exynos 990 blocks device DMA unless EL2 grants it. The QCA6390 reports the
denial itself: `BHI_STATUS = ERROR`, i.e. `Image transfer failed`.

```
HVC 0xc6000101, arg1 = (VID 1 << 16) | HSI1 index 24, 64 KiB granule, perm 3 = RW
```

Two things that cost a lot of time:

- **The EL2 refuses anything above 4 GB** (returns `0x700`). `ath11k` defaults to
  `ATH11K_PCI_DMA_MASK = 36`, so streaming buffers landed in high RAM and the
  device's writes were silently dropped — QRTR then read recycled kernel memory
  (`Invalid version 16`, with kernel pointers in the buffer). Setting the mask to
  **32** makes swiotlb bounce them into grantable RAM.
- The stock `board-2.bin` here is an **ELF** (Samsung's raw BDF), not the
  `QCA-ATH11K-BOARD` container. It works as **`board.bin`** via the api_1 path.

### 3. Rails nobody turns on — and why a cold boot is mandatory

The mainline nodes declare no supplies, and the bootloader leaves these **off**:

| Rail | Register | Role |
|---|---|---|
| `LDO15` (vmmc) | `0x54` | microSD card power, 2.95 V |
| `LDO2` (vqmmc) | `0x47` | microSD I/O |
| `BUCK4M` | `0x26` | `VDD_WIFI_0P95`, QCA6390 core |

Without vmmc/vqmmc the card never answers `CMD0`. Without BUCK4M the PCIe PHY
never trains.

> **The lesson that cost a day: PMIC state survives a warm reboot.** `BUCK4M` had
> been on since Android and persisted across every `reboot`. The entire Wi-Fi
> bring-up was built on that inherited state — **it had never once come up from a
> real cold start**. Only a true power-off exposed it.
>
> Until you do a cold cycle, you do not know what your port *enables* and what it
> merely *inherits*.

There is also an ordering trap: `drivers/pci/` links before `drivers/firmware/`
and both use `device_initcall`, so the PCIe controller probed *before* the rail
driver. Fix: build `PCI_EXYNOS` as a **module** so it loads after the initcalls.

→ `drivers/exynos990-rails.c`

---

## Known problems with this port

- **The S2MPU grant is broad.** It currently grants RW over all low RAM to the
  HSI1 block, which defeats the protection the S2MPU exists to provide. Fine on a
  bench, wrong for production. Per-buffer grants belong in the `ath11k`/`mhi` DMA
  paths, as the z3s port does for the BCM4375.
- **USB host does not enumerate.** xHCI comes up (USB 2.0 + 3.1 root hubs), VBUS
  works, the device is detected — and then `-71`. Seven hypotheses were ruled out
  (orientation, VBUS, Type-C/CC, PHY tuning, full-speed, DWC31 park mode,
  `U2_FREECLK_EXISTS`). The stock device tree carries vendor properties mainline
  does not implement (`adj-sof-accuracy`, `usb_host_device_timeout`,
  `samsung,no-extra-delay`), which is where the answer probably lives.
- **`broken-cd` on the microSD** means the driver cannot tell a missing card from
  a failing one, and it retries forever. A bad card can hang the whole system.

---

## Layout

```
patches/   kernel patches, by subject
drivers/   new files (rails, S2MPU grant helper)
dts/       exynos990-r8s-b.dts
scripts/   on-device helpers (card prep, rotation, Wi-Fi, OTG VBUS)
docs/      detailed write-ups, in Portuguese
```

Patches apply on the `exynos990-fu` branch of
[exynos990-mainline/linux](https://github.com/exynos990-mainline/linux)
(6.12.0-rc5) with the z3s patch stack on top.

## Not included, on purpose

**Proprietary firmware.** `amss.bin`, `board.bin` (`bdwlan.elf`), `m3.bin`,
`regdb.bin` for the QCA6390 are Samsung/Qualcomm blobs — extract them from your
own device's stock firmware. Same for the Bluetooth `.tlv`.

## Credit

This port stands on [exynos990-mainline](https://github.com/exynos990-mainline)
and on the **z3s** (Galaxy S20 Ultra) port, which mapped the ACPM/PMIC path, the
`lk3rd` boot flow and the S2MPU HVC interface. Their reference material is
GPL-2.0-only and is **linked, not vendored**, here.

The z3s port targets a **Broadcom BCM4375**; this one targets a **Qualcomm
QCA6390**, which is why the Wi-Fi work diverges.

## License

GPL-2.0-only, matching the kernel sources these patches derive from.
