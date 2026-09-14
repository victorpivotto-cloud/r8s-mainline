// SPDX-License-Identifier: GPL-2.0-only
/*
 * Concessao pontual de DMA no S2MPU do Exynos 990 para o bloco HSI1
 * (onde vive o PCIe do Wi-Fi).
 *
 * POR QUE: o firmware do QCA6390 sobe por DMA do endpoint para a memoria do
 * host. Sem permissao no S2MPU o dispositivo aborta e reporta erro no BHI:
 *     mhi mhi0: Image transfer failed
 *     mhi mhi0: MHI did not load image over BHI, ret: -5
 *
 * MEDIDO EM 13/09 (r8s): conceder a faixa baixa INTEIRA de uma vez
 * (32.430 granules) NAO funciona — piora, o link fica inacessivel antes mesmo
 * do BHI. Por isso aqui a concessao e por buffer, no momento do uso, que e o
 * que o porte do z3s faz para o BCM4375
 * (kernel/drivers/wifi-brcmfmac/s2mpu.c). O mecanismo e do bloco HSI1, nao do
 * chip Broadcom.
 *
 * Construido embutido (obj-y) de proposito: o chamador e o driver mhi, e assim
 * nao ha ordem de carga de modulo para acertar.
 */
#include <linux/arm-smccc.h>
#include <linux/exynos-s2mpu-wifi.h>
#include <linux/module.h>
#include <linux/sizes.h>

#define EXYNOS_HVC_SET_S2MPU_FOR_WIFI	0xc6000101UL
#define EXYNOS_S2MPU_WIFI_VID		1UL
#define EXYNOS_S2MPU_HSI1_INDEX		24UL
#define EXYNOS_S2MPU_ARG1		((EXYNOS_S2MPU_WIFI_VID << 16) | \
					 EXYNOS_S2MPU_HSI1_INDEX)
#define EXYNOS_S2MPU_NO_ACCESS		0UL
#define EXYNOS_S2MPU_READ_WRITE		3UL
#define EXYNOS_S2MPU_GRANULE		SZ_64K
#define LOW_RAM_BASE			0x80000000ULL
#define LOW_RAM_END			0x100000000ULL

static bool enabled = true;
module_param(enabled, bool, 0644);
MODULE_PARM_DESC(enabled, "conceder DMA ao HSI1 (0 desliga, para A/B)");

static bool verbose;
module_param(verbose, bool, 0644);

static unsigned long s2mpu_hvc(u64 addr, unsigned long perm)
{
	struct arm_smccc_res res = {};

	/* o exynos_hvc() da Samsung poe uma barreira de sistema em volta */
	mb();
	arm_smccc_hvc(EXYNOS_HVC_SET_S2MPU_FOR_WIFI, EXYNOS_S2MPU_ARG1,
		      addr, EXYNOS_S2MPU_GRANULE, perm, 0, 0, 0, &res);
	mb();
	return res.a0;
}

/*
 * Concede (ou revoga) acesso do HSI1 a [base, base+size), arredondando para o
 * granule de 64K. Fora da RAM baixa nao ha o que fazer: o EL2 recusa com 0x700
 * (medido), e o QCA6390 so enderecar 32 bits mesmo.
 */
int exynos990_s2mpu_wifi_grant(dma_addr_t base, size_t size, bool grant)
{
	unsigned long perm = grant ? EXYNOS_S2MPU_READ_WRITE :
				     EXYNOS_S2MPU_NO_ACCESS;
	u64 ini, fim, addr;
	unsigned long r;
	int n = 0;

	if (!enabled || !size)
		return 0;

	ini = round_down((u64)base, EXYNOS_S2MPU_GRANULE);
	fim = round_up((u64)base + size, EXYNOS_S2MPU_GRANULE);

	if (ini < LOW_RAM_BASE || fim > LOW_RAM_END) {
		pr_warn_once("s2mpu-wifi: buffer 0x%llx+0x%zx fora da RAM baixa; DMA vai falhar\n",
			     (u64)base, size);
		return -ERANGE;
	}

	for (addr = ini; addr < fim; addr += EXYNOS_S2MPU_GRANULE) {
		r = s2mpu_hvc(addr, perm);
		if (r) {
			pr_err("s2mpu-wifi: HVC %s falhou em 0x%llx: 0x%lx\n",
			       grant ? "grant" : "revoke", addr, r);
			/* desfaz o que ja foi concedido nesta chamada */
			if (grant)
				while (addr > ini) {
					addr -= EXYNOS_S2MPU_GRANULE;
					s2mpu_hvc(addr, EXYNOS_S2MPU_NO_ACCESS);
				}
			return -EIO;
		}
		n++;
	}

	if (verbose)
		pr_info("s2mpu-wifi: %s 0x%llx-0x%llx (%d granules)\n",
			grant ? "concedido" : "revogado", ini, fim, n);
	return 0;
}
EXPORT_SYMBOL_GPL(exynos990_s2mpu_wifi_grant);

/*
 * Concessao em massa da RAM baixa inteira.
 *
 * HISTORICO: quando testei isto pela primeira vez pareceu PIORAR o quadro, mas
 * o MSI ainda nao estava ligado no driver do PCIe (faltava o bit 29 do ELBI) —
 * o "Device link is not accessible" era consequencia disso, nao da concessao.
 * A transferencia do BHI, essa, funcionou.
 *
 * Serve para os buffers que o ath11k e o MHI alocam em dezenas de pontos
 * diferentes; conceder um a um exigiria patchar cada chamada de DMA, que e o
 * que o porte do z3s fez para o BCM4375. Isto e uma concessao AMPLA: boa de
 * bancada, a revisar antes do estado final.
 */
static bool bulk = true;
module_param(bulk, bool, 0444);
MODULE_PARM_DESC(bulk, "conceder a RAM baixa inteira ao HSI1 no boot");

static int __init s2mpu_wifi_bulk(void)
{
	u64 addr;
	unsigned long ok = 0, falhas = 0;

	if (!bulk || !enabled)
		return 0;

	for (addr = LOW_RAM_BASE; addr < LOW_RAM_END;
	     addr += EXYNOS_S2MPU_GRANULE) {
		if (s2mpu_hvc(addr, EXYNOS_S2MPU_READ_WRITE))
			falhas++;   /* buracos reservados: esperado */
		else
			ok++;
	}
	pr_info("s2mpu-wifi: massa 0x%llx-0x%llx: %lu concedidos, %lu recusados\n",
		LOW_RAM_BASE, LOW_RAM_END, ok, falhas);
	return 0;
}
/* depois do PCIe subir, antes de qualquer driver de endpoint */
late_initcall(s2mpu_wifi_bulk);
