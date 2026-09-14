// SPDX-License-Identifier: GPL-2.0-only
/*
 * Liga os trilhos que o bootloader deixa DESLIGADOS, no S2MPS19, via ACPM.
 *
 * Cobre microSD (vmmc/vqmmc) e o nucleo do Wi-Fi (BUCK4M / VDD_WIFI_0P95).
 *
 * POR QUE: o nó mmc@132e0000 do mainline não declara alimentação nenhuma, e o
 * bootloader deixa os dois trilhos DESLIGADOS. O cartão fica mudo — CMD0 dá
 * timeout em laço e o kernel vai baixando o clock (400k -> 300k -> 200k) sem
 * nunca obter resposta. Medido no r8s em 14/09:
 *
 *     mmc_host mmc0: Timeout sending command (cmd 0x202000 arg 0x0 ...)
 *
 * QUAIS TRILHOS, e como sei: três fontes independentes concordam.
 *   1. dtbo.img de estoque do próprio r8s: LDO2M tem regulator-name "vqmmc" e
 *      LDO15M tem "vmmc" (fixo em 2.950.000 uV);
 *   2. header do kernel de estoque (hz128/SM-G780F-CIS-RR-Kernel,
 *      s2mps19-regulator.h): L2CTRL = 0x47, L15CTRL = 0x54;
 *   3. o porte do z3s chegou nos mesmos dois registradores na tentativa e erro
 *      (kernel/drivers/acpm-pmic/exynos990-pmic-probe.c).
 *
 * TENSÃO: campo de 6 bits, 1,8 V + passo de 25 mV. 0x2e = 46 -> 2,95 V, que é
 * exatamente o que o DT de fábrica declara para o vmmc. O bootloader do r8s
 * deixa 0x30 (3,0 V) e 0x28 (2,8 V); ambos funcionam, mas 2,95 V é o ponto de
 * projeto e é o que o z3s usa.
 *
 * SEGURANÇA: este driver só LIGA, nunca desliga, e nunca toca em outro
 * registrador. Escrever no registrador errado de um PMIC pode cortar o trilho
 * do núcleo da CPU — foi assim que eu estraguei a DVFS uma vez, escrevendo em
 * BUCKRAMP achando que era o trilho do Wi-Fi.
 *
 * O mmc usa 'broken-cd' (sondagem), então não importa se este driver chega
 * depois: o controlador fica tentando e acha o cartão assim que houver energia.
 */
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/firmware/samsung/exynos-acpm-protocol.h>

#define ACPM_CHAN		2
#define TYPE_PMIC		0x01
#define SPEEDY_CHAN		0

#define S2MPS19_REG_L2CTRL	0x47	/* vqmmc — E/S do cartao */
#define S2MPS19_REG_L15CTRL	0x54	/* vmmc  — alimentacao do cartao */
#define S2MPS19_REG_B4MCTRL	0x26	/* BUCK4M = VDD_WIFI_0P95, nucleo do QCA6390 */
#define LDO_EN_ALWAYS		0xC0	/* bits 7:6 = 11 */
#define BUCK_EN_ALWAYS		0xE0	/* bits 7:5, como os BUCKs vizinhos ligados */
#define LDO_VSEL_2V95		0x2e	/* 1,8 V + 46 * 25 mV */

/*
 * DESCOBERTO NO PRIMEIRO BOOT FRIO DE VERDADE (14/09), e vale registrar porque
 * enganou por um dia inteiro: o BUCK4M estava LIGADO desde o Android e
 * sobrevivia aos reinicios A QUENTE. Todo o Wi-Fi foi portado em cima desse
 * estado herdado. No primeiro desligamento real ele veio 0x18 (bits 7:5
 * zerados), o PCIe nao teve o que treinar ("Phy link never came up") e o
 * ath11k nem carregou. Ou seja: o Wi-Fi NUNCA tinha subido do zero.
 *
 * Licao: estado de PMIC atravessa reboot a quente. Enquanto nao houver um
 * ciclo frio, nao se sabe o que o proprio porte liga e o que ele apenas herda.
 */

static bool ligar = true;
module_param(ligar, bool, 0444);
MODULE_PARM_DESC(ligar, "ligar os trilhos (0 = deixar como esta)");

static void liga_trilho(struct device *dev, struct acpm_handle *acpm,
			u8 reg, u8 bits_on, u8 vsel, const char *nome)
{
	u8 antes = 0, depois = 0;
	int ret;

	ret = acpm->ops->pmic.read_reg(acpm, ACPM_CHAN, TYPE_PMIC, reg,
				       SPEEDY_CHAN, &antes);
	if (ret) {
		dev_err(dev, "rails: leitura de 0x%02x (%s) falhou: %d\n",
			reg, nome, ret);
		return;
	}
	if ((antes & 0xC0) == 0xC0) {
		dev_info(dev, "rails: %s (0x%02x) ja ligado = 0x%02x\n",
			 nome, reg, antes);
		return;
	}

	/*
	 * vsel != 0: LDO, impomos a tensao junto (o campo mora no mesmo
	 * registrador). vsel == 0: BUCK, a tensao esta em OUT1 e nao se toca —
	 * so acendemos os bits de habilitacao, preservando o resto.
	 */
	ret = acpm->ops->pmic.write_reg(acpm, ACPM_CHAN, TYPE_PMIC, reg,
					SPEEDY_CHAN,
					vsel ? (bits_on | vsel)
					     : (antes | bits_on));
	msleep(5);
	acpm->ops->pmic.read_reg(acpm, ACPM_CHAN, TYPE_PMIC, reg,
				 SPEEDY_CHAN, &depois);
	dev_info(dev, "rails: %s (0x%02x): 0x%02x -> 0x%02x (ret=%d)\n",
		 nome, reg, antes, depois, ret);
}

static int sd_rails_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np;
	struct acpm_handle *acpm;

	if (!ligar)
		return 0;

	np = of_find_compatible_node(NULL, NULL, "samsung,exynos990-acpm-ipc");
	if (!np)
		return -ENODEV;
	acpm = devm_acpm_get_by_node(dev, np);
	of_node_put(np);
	if (IS_ERR(acpm))
		return PTR_ERR(acpm);	/* inclui -EPROBE_DEFER */

	/* microSD: LDOs, tensao no mesmo registrador */
	liga_trilho(dev, acpm, S2MPS19_REG_L15CTRL, LDO_EN_ALWAYS, LDO_VSEL_2V95, "vmmc");
	liga_trilho(dev, acpm, S2MPS19_REG_L2CTRL,  LDO_EN_ALWAYS, LDO_VSEL_2V95, "vqmmc");
	/* Wi-Fi: BUCK, tensao fica em B4M_OUT1 (0x27) e nao se mexe */
	liga_trilho(dev, acpm, S2MPS19_REG_B4MCTRL, BUCK_EN_ALWAYS, 0, "wifi-0p95");
	return 0;
}

static struct platform_driver sd_rails_drv = {
	.probe = sd_rails_probe,
	.driver = { .name = "exynos990-rails" },
};

static struct platform_device *sd_rails_pdev;

static int __init sd_rails_init(void)
{
	int ret = platform_driver_register(&sd_rails_drv);

	if (ret)
		return ret;
	sd_rails_pdev = platform_device_register_simple("exynos990-rails",
							-1, NULL, 0);
	if (IS_ERR(sd_rails_pdev)) {
		platform_driver_unregister(&sd_rails_drv);
		return PTR_ERR(sd_rails_pdev);
	}
	return 0;
}
device_initcall(sd_rails_init);
