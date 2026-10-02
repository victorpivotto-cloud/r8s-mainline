// SPDX-License-Identifier: GPL-2.0-only
/*
 * Prepare volatile Exynos990 reboot reason registers before syscon reset.
 * Register offsets and numeric protocol values are from lk3rd 2.4-hotfix,
 * platform/exynos9830/usb/usb.c and include/platform/exynos9830.h.
 * No reset trigger, RAM scratch write or persistent partition access here.
 */
#include <linux/err.h>
#include <linux/ioport.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/of_address.h>
#include <linux/reboot.h>
#include <linux/regmap.h>

#define R8S_DEBUG_MAGIC 0x808
#define R8S_RESET_REASON 0x80c
#define R8S_SYSIP_DAT0 0x810
#define R8S_NORMAL_MAGIC_MASK 0xff0000
#define R8S_NORMAL_MAGIC 0x4e0000
#define R8S_REASON_NORMAL 0x12345600
#define R8S_LK3RD_REQUEST 0x4c

static struct regmap *r8s_pmu;
static bool enabled;
module_param(enabled, bool, 0600);
MODULE_PARM_DESC(enabled, "Arm reboot preparation; defaults to false for initial inspection");

static int r8s_prepare_reason(const char *cmd)
{
	unsigned int mode = 0, readback;
	int ret;

	if (cmd && *cmd) {
		if (!strcmp(cmd, "bootloader") || !strcmp(cmd, "fastboot"))
			mode = R8S_LK3RD_REQUEST;
		else
			return -EOPNOTSUPP;
	}
	ret = regmap_update_bits(r8s_pmu, R8S_DEBUG_MAGIC,
				 R8S_NORMAL_MAGIC_MASK, R8S_NORMAL_MAGIC);
	if (ret)
		return ret;
	ret = regmap_write(r8s_pmu, R8S_RESET_REASON, R8S_REASON_NORMAL);
	if (ret)
		return ret;
	ret = regmap_write(r8s_pmu, R8S_SYSIP_DAT0, mode);
	if (ret)
		return ret;
	/* Flush posted MMIO and confirm the selected bootloader protocol value. */
	ret = regmap_read(r8s_pmu, R8S_SYSIP_DAT0, &readback);
	if (ret)
		return ret;
	return readback == mode ? 0 : -EIO;
}

static int r8s_reboot_notify(struct notifier_block *nb,
			     unsigned long event, void *data)
{
	const char *cmd = data;
	int ret;

	if (event != SYS_RESTART || !READ_ONCE(enabled))
		return NOTIFY_DONE;
	ret = r8s_prepare_reason(cmd);
	if (ret == -EOPNOTSUPP) {
		pr_warn("r8s-reboot: unsupported reboot command; registers unchanged\n");
		return NOTIFY_DONE;
	}
	if (ret)
		pr_crit("r8s-reboot: failed preparing reboot reason: %d\n", ret);
	else
		pr_info("r8s-reboot: prepared %s\n", cmd && *cmd ? "lk3rd" : "normal boot");
	return NOTIFY_DONE;
}

static struct notifier_block r8s_reboot_nb = {
	.notifier_call = r8s_reboot_notify,
	.priority = 192,
};

static int r8s_registers_get(char *buf, const struct kernel_param *kp)
{
	unsigned int magic, reason, mode;
	int ret;

	if (IS_ERR_OR_NULL(r8s_pmu))
		return -ENODEV;
	ret = regmap_read(r8s_pmu, R8S_DEBUG_MAGIC, &magic);
	if (!ret)
		ret = regmap_read(r8s_pmu, R8S_RESET_REASON, &reason);
	if (!ret)
		ret = regmap_read(r8s_pmu, R8S_SYSIP_DAT0, &mode);
	if (ret)
		return ret;
	return sysfs_emit(buf, "magic=%08x reason=%08x mode=%08x\n", magic, reason, mode);
}

static const struct kernel_param_ops r8s_registers_ops = {
	.get = r8s_registers_get,
};
module_param_cb(registers, &r8s_registers_ops, NULL, 0400);

static int __init r8s_reboot_init(void)
{
	struct device_node *np;
	struct resource res;
	int ret;

	np = of_find_compatible_node(NULL, NULL, "samsung,exynos850-pmu");
	if (!np)
		return -ENODEV;
	ret = of_address_to_resource(np, 0, &res);
	if (ret || res.start != 0x15860000 || resource_size(&res) < 0x814) {
		of_node_put(np);
		return ret ? ret : -ENODEV;
	}
	r8s_pmu = syscon_node_to_regmap(np);
	of_node_put(np);
	if (IS_ERR(r8s_pmu))
		return PTR_ERR(r8s_pmu);
	return register_reboot_notifier(&r8s_reboot_nb);
}

static void __exit r8s_reboot_exit(void)
{
	unregister_reboot_notifier(&r8s_reboot_nb);
}

module_init(r8s_reboot_init);
module_exit(r8s_reboot_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("r8s lk3rd reboot protocol via volatile PMU reason registers");
