// SPDX-License-Identifier: GPL-2.0-only
/*
 * Opt-in host-built ZT7650 resident-firmware probe, not an input driver.
 * No OF matching. Explicit insmod arm=1 only; never install for autoload.
 * Default has no commands; vendor_window optionally enables volatile vendor
 * access for ID reading. resident_start optionally executes existing firmware
 * using normal NVM init/start; no flash write/erase or calibration.
 * No IRQ handler, input registration or automatic retry.
 * Board prerequisite: vdd and vddo reference the same fixed LDO supply.
 */
#include <linux/delay.h>
#include <linux/atomic.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>
#include <linux/unaligned.h>
#include "zt7650_io.h"

#define ZT_CHECKSUM_RESULT 0x012c
#define ZT_CHECKSUM_CORRECT 0x55aa

static bool arm;
static bool check_framing;
static bool vendor_window;
static bool resident_start;
static atomic_t used = ATOMIC_INIT(0);
module_param(arm, bool, 0400);
module_param(check_framing, bool, 0400);
module_param(vendor_window, bool, 0400);
module_param(resident_start, bool, 0400);
MODULE_PARM_DESC(arm, "Explicitly arm one resident checksum probe on module load");
MODULE_PARM_DESC(check_framing, "Also read chip/firmware revision to check address echo");
MODULE_PARM_DESC(vendor_window, "ZT7650 only: volatile vendor-enable 0x10f0 and ID read 0x17f0");
MODULE_PARM_DESC(resident_start, "ZT7650 e650 only: execute existing resident firmware, no flash writes");

struct zt_probe {
	struct regulator *supply;
	struct device *dev;
	bool powered;
};


static void zt_power_off(void *data)
{
	struct zt_probe *zt = data;
	int ret;

	if (!zt->powered)
		return;
	ret = regulator_disable(zt->supply);
	if (ret) {
		dev_err(zt->dev, "regulator disable failed: %d\n", ret);
		return;
	}
	zt->powered = false;
	msleep(300);
}




static int zt_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct device_node *vdd, *vddo;
	struct zt_probe *zt;
	u8 data[2];
	int ret, off;

	if (!arm)
		return -ENODEV;
	if (resident_start && !vendor_window)
		return -EINVAL;
	if (!of_machine_is_compatible("samsung,r8s") ||
	    client->addr != 0x20 || !dev->of_node ||
	    !of_device_is_compatible(dev->of_node, "zinitix,bt541") ||
	    of_property_present(dev->of_node, "reset-gpios") ||
	    !i2c_check_functionality(client->adapter, I2C_FUNC_I2C))
		return -ENODEV;
	/* Never silently substitute a dummy supply or assume separate rail order. */
	vdd = of_parse_phandle(dev->of_node, "vdd-supply", 0);
	vddo = of_parse_phandle(dev->of_node, "vddo-supply", 0);
	ret = vdd && vdd == vddo &&
		of_device_is_compatible(vdd, "regulator-fixed") &&
		(of_property_present(vdd, "gpio") ||
		 of_property_present(vdd, "gpios")) &&
		!of_property_read_bool(vdd, "regulator-always-on") ? 0 : -EINVAL;
	of_node_put(vdd);
	of_node_put(vddo);
	if (ret)
		return dev_err_probe(dev, ret, "requires shared vdd/vddo LDO\n");
	if (atomic_xchg(&used, 1))
		return -ENODEV;
	zt = devm_kzalloc(dev, sizeof(*zt), GFP_KERNEL);
	if (!zt)
		return -ENOMEM;
	zt->dev = dev;
	zt->supply = devm_regulator_get(dev, "vdd");
	if (IS_ERR(zt->supply)) {
		ret = PTR_ERR(zt->supply);
		/* This lab probe must not defer and later enable power unattended. */
		return dev_err_probe(dev, ret == -EPROBE_DEFER ? -ENODEV : ret,
				     "LDO unavailable\n");
	}
	ret = regulator_is_enabled(zt->supply);
	if (ret)
		return dev_err_probe(dev, ret < 0 ? ret : -EBUSY,
				     "LDO already enabled or state unknown\n");
	ret = devm_add_action_or_reset(dev, zt_power_off, zt);
	if (ret)
		return ret;
	ret = regulator_enable(zt->supply);
	if (ret)
		return dev_err_probe(dev, ret, "LDO enable failed\n");
	zt->powered = true;
	msleep(100);
	if (vendor_window) {
		/* ZT7650 branch, not legacy BT541's 0xc000/0xcc00. */
		ret = zt_write_u16(client, 0x10f0, 1);
		if (!ret)
			ret = zt_read(client, 0x17f0, data, sizeof(data));
		if (ret)
			dev_err(dev, "vendor window ID read failed: %d\n", ret);
		else
			dev_info(dev, "ZT7650 vendor ID raw=%*ph le16=%#06x\n",
				 (int)sizeof(data), data, get_unaligned_le16(data));
		if (ret || !resident_start)
			goto off;
		if (get_unaligned_le16(data) != 0xe650) {
			dev_err(dev, "resident start refused: unexpected chip ID\n");
			goto off;
		}
		ret = zt_resident_start(client);
		if (ret) {
			dev_err(dev, "resident start failed: %d\n", ret);
			goto off;
		}
	}
	ret = zt_read(client, ZT_CHECKSUM_RESULT, data, sizeof(data));
	if (ret)
		dev_err(dev, "resident checksum read failed: %d\n", ret);
	else
		dev_info(dev, "resident checksum raw=%*ph le16=%#06x match=%d\n",
			 (int)sizeof(data), data,
			 get_unaligned_le16(data),
			 get_unaligned_le16(data) == ZT_CHECKSUM_CORRECT);
	if (!ret && check_framing) {
		static const u16 regs[] = { 0x0011, 0x0012 };
		int i;

		for (i = 0; i < ARRAY_SIZE(regs); i++) {
			ret = zt_read(client, regs[i], data, sizeof(data));
			if (ret) {
				dev_err(dev, "framing read %#06x failed: %d\n", regs[i], ret);
				break;
			}
			dev_info(dev, "framing reg=%#06x raw=%*ph le16=%#06x\n",
				 regs[i], (int)sizeof(data), data, get_unaligned_le16(data));
		}
	}

off:
	/* Bound or failed probe must both leave the regulator disabled. */
	zt_power_off(zt);
	if (zt->powered) {
		dev_crit(dev, "LDO disable failed; stop tests and verify power state\n");
		return -EIO;
	}
	off = regulator_is_enabled(zt->supply);
	if (off)
		return dev_err_probe(dev, off < 0 ? off : -EBUSY,
			"LDO remains enabled by another consumer or state unknown\n");
	dev_info(dev, "checksum probe finished; LDO off, remaining unbound\n");
	return -ENODEV;
}

static const struct i2c_device_id zt_ids[] = {
	/* Existing r8s OF node has this misleading name; arm gates ALL I/O. */
	{ "bt541", 0 },
	{ }
};

static struct i2c_driver zt_driver = {
	.driver.name = "zt7650-lab",
	.probe = zt_probe,
	.id_table = zt_ids,
};
module_i2c_driver(zt_driver);

MODULE_DESCRIPTION("Opt-in bounded ZT7650 resident boot/checksum probe, no input or flash writes");
MODULE_LICENSE("GPL");
