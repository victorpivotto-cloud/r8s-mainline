// SPDX-License-Identifier: GPL-2.0-only
/* Opt-in finite polling experiment. No flash writes, NVM save or IRQ handler. */
#include <linux/atomic.h>
#include <linux/i2c.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/input/touchscreen.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/property.h>
#include <linux/regulator/consumer.h>
#include <linux/workqueue.h>
#include "zt7650_io.h"
#include "zt7650_events.h"

static bool arm;
static unsigned int lab_seconds = 120;
static atomic_t used = ATOMIC_INIT(0);
module_param(arm, bool, 0400);
module_param(lab_seconds, uint, 0400);
MODULE_PARM_DESC(arm, "Explicit opt-in to the finite polling input experiment");
MODULE_PARM_DESC(lab_seconds, "Auto-stop deadline, 1..180 seconds; default 120");

struct zt_input {
	struct i2c_client *client;
	struct regulator *supply;
	struct input_dev *input;
	struct touchscreen_properties prop;
	struct mutex lock;
	struct delayed_work deadline;
	bool powered, stopped, registered;
	unsigned int errors, frames, events;
};

static void zt_release_all(struct zt_input *ts)
{
	int i;

	if (!ts->registered)
		return;
	for (i = 0; i < ZT_SLOTS; i++) {
		input_mt_slot(ts->input, i);
		input_mt_report_slot_state(ts->input, MT_TOOL_FINGER, false);
	}
	input_mt_sync_frame(ts->input);
	input_sync(ts->input);
}

/* Caller holds lock. Polling remains scheduled but performs no I/O after stop. */
static void zt_stop_locked(struct zt_input *ts)
{
	int ret;

	ts->stopped = true;
	zt_release_all(ts);
	if (ts->powered) {
		ret = regulator_disable(ts->supply);
		if (ret) {
			dev_crit(&ts->client->dev, "LDO disable failed: %d; stop tests\n", ret);
			return;
		}
		ts->powered = false;
		msleep(300);
		ret = regulator_is_enabled(ts->supply);
		if (ret)
			dev_crit(&ts->client->dev, "LDO off state not confirmed: %d\n", ret);
	}
}

static void zt_power_cleanup(void *data)
{
	struct zt_input *ts = data;

	mutex_lock(&ts->lock);
	/* Input devres has already unregistered input at this point. */
	ts->registered = false;
	zt_stop_locked(ts);
	mutex_unlock(&ts->lock);
}

static void zt_deadline(struct work_struct *work)
{
	struct zt_input *ts = container_of(to_delayed_work(work),
						 struct zt_input, deadline);

	mutex_lock(&ts->lock);
	if (!ts->stopped) {
		zt_stop_locked(ts);
		dev_info(&ts->client->dev, "polling deadline reached, frames=%u, events=%u, LDO powered=%d\n",
			 ts->frames, ts->events, ts->powered);
	}
	mutex_unlock(&ts->lock);
}

static void zt_poll(struct input_dev *input)
{
	struct zt_input *ts = input_get_drvdata(input);
	struct zt_event events[ZT_SLOTS];
	u8 bytes[ZT_SLOTS * ZT_EVENT_BYTES];
	unsigned int extra, nr, i;
	unsigned long seen = 0;
	int ret, ack_ret;

	mutex_lock(&ts->lock);
	if (ts->stopped)
		goto out;
	ret = zt_read(ts->client, 0x0200, bytes, ZT_EVENT_BYTES);
	if (ret)
		goto failed;
	extra = bytes[7] & 15;
	if (extra >= ZT_SLOTS) {
		ret = -EPROTO;
		goto failed;
	}
	if (extra) {
		ret = zt_read(ts->client, 0x0201, bytes + ZT_EVENT_BYTES,
			      extra * ZT_EVENT_BYTES);
		if (ret)
			goto failed;
	}
	ret = zt_decode(bytes, (1 + extra) * ZT_EVENT_BYTES,
			ts->prop.max_x, ts->prop.max_y, events, &nr);
	if (ret) {
		/* Drop a completely read invalid batch; never publish its events. */
		ack_ret = zt_command(ts->client, 0x0003);
		if (ack_ret)
			ret = ack_ret;
		goto failed;
	}
	/* Never publish coordinates until the complete read AND ACK succeeded. */
	ret = zt_command(ts->client, 0x0003);
	if (ret)
		goto failed;
	ts->errors = 0;
	ts->frames++;
	for (i = 0; i < nr; i++) {
		struct zt_event *e = &events[i];
		bool active = e->status != 3 && e->type == 0;

		/* Preserve a press/release of the same ID in this ordered batch. */
		if (seen & BIT(e->id)) {
			input_mt_sync_frame(input);
			input_sync(input);
			seen = 0;
		}
		seen |= BIT(e->id);
		ts->events++;
		input_mt_slot(input, e->id);
		input_mt_report_slot_state(input, MT_TOOL_FINGER, active);
		if (active) {
			touchscreen_report_pos(input, &ts->prop, e->x, e->y, true);
			input_report_abs(input, ABS_MT_TOUCH_MAJOR, e->major);
			input_report_abs(input, ABS_MT_TOUCH_MINOR, e->minor);
			input_report_abs(input, ABS_MT_PRESSURE, e->pressure);
		}
	}
	input_mt_sync_frame(input);
	input_sync(input);
	goto out;
failed:
	zt_release_all(ts);
	dev_warn_ratelimited(&ts->client->dev, "polling read/decode/ACK failed: %d\n", ret);
	if (++ts->errors >= 3) {
		dev_warn(&ts->client->dev, "stopping after three failures, frames=%u, events=%u\n",
			 ts->frames, ts->events);
		zt_stop_locked(ts);
	}
out:
	mutex_unlock(&ts->lock);
}

static int zt_boot_resident(struct zt_input *ts)
{
	u8 bytes[2];
	int ret, i;

	ret = regulator_enable(ts->supply);
	if (ret)
		return ret;
	ts->powered = true;
	msleep(100);
	ret = zt_write_u16(ts->client, 0x10f0, 1);
	if (!ret)
		ret = zt_read(ts->client, 0x17f0, bytes, 2);
	if (ret)
		return ret;
	if (get_unaligned_le16(bytes) != 0xe650)
		return -ENODEV;
	ret = zt_resident_start(ts->client);
	if (!ret)
		ret = zt_read(ts->client, 0x012c, bytes, 2);
	if (ret)
		return ret;
	if (get_unaligned_le16(bytes) != 0x55aa)
		return -EILSEQ;
	ret = zt_command(ts->client, 0x0000);
	if (!ret)
		ret = zt_write_u16(ts->client, 0x0010, 0);
	if (!ret)
		ret = zt_write_u16(ts->client, 0x023e, 0x0200);
	if (!ret)
		ret = zt_write_u16(ts->client, 0x0116, 0);
	for (i = 0; !ret && i < 10; i++)
		ret = zt_command(ts->client, 0x0003);
	return ret;
}

static int zt_input_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct device_node *vdd, *vddo;
	struct zt_input *ts;
	u32 size_x, size_y;
	int ret;

	if (!arm)
		return -ENODEV;
	if (!lab_seconds || lab_seconds > 180)
		return -EINVAL;
	if (!of_machine_is_compatible("samsung,r8s") || client->addr != 0x20 ||
	    !dev->of_node || !of_device_is_compatible(dev->of_node, "zinitix,bt541") ||
	    of_property_present(dev->of_node, "reset-gpios") ||
	    !i2c_check_functionality(client->adapter, I2C_FUNC_I2C))
		return -ENODEV;
	vdd = of_parse_phandle(dev->of_node, "vdd-supply", 0);
	vddo = of_parse_phandle(dev->of_node, "vddo-supply", 0);
	ret = vdd && vdd == vddo && of_device_is_compatible(vdd, "regulator-fixed") &&
		(of_property_present(vdd, "gpio") || of_property_present(vdd, "gpios")) &&
		!of_property_read_bool(vdd, "regulator-always-on") ? 0 : -EINVAL;
	of_node_put(vdd);
	of_node_put(vddo);
	if (ret)
		return ret;
	if (atomic_xchg(&used, 1))
		return -ENODEV;
	ts = devm_kzalloc(dev, sizeof(*ts), GFP_KERNEL);
	if (!ts)
		return -ENOMEM;
	ts->client = client;
	mutex_init(&ts->lock);
	INIT_DELAYED_WORK(&ts->deadline, zt_deadline);
	i2c_set_clientdata(client, ts);
	ts->supply = devm_regulator_get(dev, "vdd");
	if (IS_ERR(ts->supply)) {
		ret = PTR_ERR(ts->supply);
		return ret == -EPROBE_DEFER ? -ENODEV : ret;
	}
	ret = regulator_is_enabled(ts->supply);
	if (ret)
		return ret < 0 ? ret : -EBUSY;
	ret = devm_add_action_or_reset(dev, zt_power_cleanup, ts);
	if (ret)
		return ret;
	ts->input = devm_input_allocate_device(dev);
	if (!ts->input)
		return -ENOMEM;
	if (device_property_read_u32(dev, "touchscreen-size-x", &size_x) ||
	    device_property_read_u32(dev, "touchscreen-size-y", &size_y) ||
	    !size_x || !size_y || size_x > 4096 || size_y > 4096)
		return -EINVAL;
	ts->input->name = "ZT7650 finite polling experiment";
	ts->input->id.bustype = BUS_I2C;
	input_set_drvdata(ts->input, ts);
	input_set_abs_params(ts->input, ABS_MT_POSITION_X, 0, size_x - 1, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_POSITION_Y, 0, size_y - 1, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_TOUCH_MAJOR, 0, 255, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_TOUCH_MINOR, 0, 255, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_PRESSURE, 0, 63, 0, 0);
	touchscreen_parse_properties(ts->input, true, &ts->prop);
	ret = input_mt_init_slots(ts->input, ZT_SLOTS, INPUT_MT_DIRECT);
	if (ret)
		return ret;
	ret = input_setup_polling(ts->input, zt_poll);
	if (ret)
		return ret;
	input_set_poll_interval(ts->input, 20);
	input_set_min_poll_interval(ts->input, 20);
	ret = zt_boot_resident(ts);
	if (ret)
		return dev_err_probe(dev, ret, "resident input initialization failed\n");
	/* A handler can open/poll during input_register_device itself. */
	mutex_lock(&ts->lock);
	ts->registered = true;
	mutex_unlock(&ts->lock);
	ret = input_register_device(ts->input);
	if (ret) {
		mutex_lock(&ts->lock);
		ts->registered = false;
		mutex_unlock(&ts->lock);
		return ret;
	}
	schedule_delayed_work(&ts->deadline, msecs_to_jiffies(lab_seconds * 1000));
	dev_info(dev, "finite polling input registered for %us, no IRQ handler\n", lab_seconds);
	return 0;
}

static void zt_input_remove(struct i2c_client *client)
{
	struct zt_input *ts = i2c_get_clientdata(client);

	cancel_delayed_work_sync(&ts->deadline);
	mutex_lock(&ts->lock);
	zt_stop_locked(ts);
	mutex_unlock(&ts->lock);
}

static const struct i2c_device_id zt_input_ids[] = { { "bt541", 0 }, { } };
static struct i2c_driver zt_input_driver = {
	.driver.name = "zt7650-input-lab",
	.probe = zt_input_probe,
	.remove = zt_input_remove,
	.shutdown = zt_input_remove,
	.id_table = zt_input_ids,
};
module_i2c_driver(zt_input_driver);
MODULE_DESCRIPTION("Finite opt-in ZT7650 polling input experiment, no flash writes");
MODULE_LICENSE("GPL");
