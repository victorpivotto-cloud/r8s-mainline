// SPDX-License-Identifier: GPL-2.0-only
/*
 * Exynos990 ACPM thermal telemetry and CPU cooling for r8s.
 * Channel 9 and zone IDs come from this device's stock DT.
 * Uses READ_TEMP only: no INIT, threshold, IRQ, emulation or control commands.
 * Passive CPU cooling uses Linux frequency QoS; firmware stays read-only.
 * 83 C / 5 C match the stock BIG/MID passive thresholds. LITTLE uses the
 * same project policy; stock LITTLE has active trips and no passive trip.
 * No shutdown trip: firmware sensor calibration remains to be qualified.
 */
#include <linux/err.h>
#include <linux/exynos990-cpufreq.h>
#include <linux/firmware/samsung/exynos-acpm-protocol.h>
#include <linux/hwmon.h>
#include <linux/hwmon-sysfs.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/thermal.h>

#define R8S_TMU_CHANNEL 9

static struct platform_device *r8s_pdev;
static struct device *r8s_hwmon;
static struct acpm_handle *r8s_acpm;
static DEFINE_MUTEX(r8s_temp_lock);
/* Test hook affects Linux CPU zone reads only, never firmware registers. */
static unsigned int r8s_fault_mask;
module_param_named(fault_mask, r8s_fault_mask, uint, 0600);
MODULE_PARM_DESC(fault_mask, "Inject CPU sensor errors: bit0 BIG, bit1 MID, bit2 LITTLE; default 0");
static const char * const r8s_labels[] = {
	"BIG", "MID", "LITTLE", "G3D", "ISP", "NPU",
};

struct r8s_cpu_zone {
	unsigned int id;
	const char *name;
	unsigned int first_cpu;
	unsigned int last_cpu;
	struct thermal_zone_device *tz;
	unsigned int bad_reads;
	unsigned int good_reads;
	bool healthy;
	bool enabled;
	unsigned long next_good_sample;
	unsigned long last_sample;
};

static struct r8s_cpu_zone r8s_cpu_zones[] = {
	{ .id = 0, .name = "r8s_big", .first_cpu = 6, .last_cpu = 7 },
	{ .id = 1, .name = "r8s_mid", .first_cpu = 4, .last_cpu = 5 },
	{ .id = 2, .name = "r8s_little", .first_cpu = 0, .last_cpu = 3 },
};

static const struct thermal_trip r8s_cpu_trip = {
	.temperature = 83000,
	.hysteresis = 5000,
	.type = THERMAL_TRIP_PASSIVE,
};

static const struct thermal_zone_params r8s_cpu_params = {
	.governor_name = "step_wise",
	.no_hwmon = true,
};

static int r8s_read_temp(unsigned int zone, int *temp)
{
	int ret;

	mutex_lock(&r8s_temp_lock);
	ret = r8s_acpm->ops->tmu.read_temp(r8s_acpm, R8S_TMU_CHANNEL,
					 zone, temp);
	mutex_unlock(&r8s_temp_lock);
	if (!ret && (*temp <= 0 || *temp > 127))
		return -ENODATA;
	return ret;
}

static int r8s_zone_get_temp(struct thermal_zone_device *tz, int *temp)
{
	struct r8s_cpu_zone *zone = thermal_zone_device_priv(tz);
	int ret;

	/* Sysfs reads must not release the clamp for a disabled governor. */
	if (!zone->enabled)
		return -EAGAIN;

	if (time_after(jiffies, zone->last_sample + 5 * HZ)) {
		zone->healthy = false;
		zone->good_reads = 0;
	}
	zone->last_sample = jiffies;
	ret = READ_ONCE(r8s_fault_mask) & BIT(zone->id) ? -EIO :
		r8s_read_temp(zone->id, temp);
	if (ret) {
		zone->good_reads = 0;
		if (zone->bad_reads < 3)
			zone->bad_reads++;
		if (zone->bad_reads >= 3) {
			zone->healthy = false;
			exynos990_cpufreq_sensor_report(zone->first_cpu, false);
		}
		return ret;
	}
	zone->bad_reads = 0;
	if (!zone->healthy) {
		if (*temp < 78) {
			if (zone->good_reads < 3 &&
			    (!zone->good_reads ||
			     time_after_eq(jiffies, zone->next_good_sample))) {
				zone->good_reads++;
				zone->next_good_sample = jiffies + HZ;
			}
		} else {
			zone->good_reads = 0;
		}
		if (zone->good_reads >= 3)
			zone->healthy = true;
	}
	exynos990_cpufreq_sensor_report(zone->first_cpu, zone->healthy);
	*temp *= 1000;
	return 0;
}

/* The thermal core serializes change_mode/get_temp under the zone lock. */
static int r8s_zone_change_mode(struct thermal_zone_device *tz,
                              enum thermal_device_mode mode)
{
	struct r8s_cpu_zone *zone = thermal_zone_device_priv(tz);

	zone->enabled = mode == THERMAL_DEVICE_ENABLED;
	zone->healthy = false;
	zone->good_reads = 0;
	zone->bad_reads = 0;
	exynos990_cpufreq_sensor_report(zone->first_cpu, false);
	return 0;
}

static bool r8s_zone_should_bind(struct thermal_zone_device *tz,
				 const struct thermal_trip *trip,
				 struct thermal_cooling_device *cdev,
				 struct cooling_spec *spec)
{
	struct r8s_cpu_zone *zone = thermal_zone_device_priv(tz);
	unsigned int cpu;
	int consumed = 0;

	if (trip->type != THERMAL_TRIP_PASSIVE ||
	    sscanf(cdev->type, "cpufreq-cpu%u%n", &cpu, &consumed) != 1 ||
	    cdev->type[consumed] || cpu < zone->first_cpu || cpu > zone->last_cpu)
		return false;
	spec->lower = 0;
	spec->upper = THERMAL_NO_LIMIT;
	spec->weight = THERMAL_WEIGHT_DEFAULT;
	return true;
}

static const struct thermal_zone_device_ops r8s_zone_ops = {
	.get_temp = r8s_zone_get_temp,
	.change_mode = r8s_zone_change_mode,
	.should_bind = r8s_zone_should_bind,
};

static void r8s_unregister_zones(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(r8s_cpu_zones); i++) {
		if (r8s_cpu_zones[i].tz) {
			thermal_zone_device_unregister(r8s_cpu_zones[i].tz);
			r8s_cpu_zones[i].tz = NULL;
		}
		/* No sensors after unload: leave an explicit CPU clamp in place. */
		exynos990_cpufreq_sensor_report(r8s_cpu_zones[i].first_cpu, false);
	}
}

static ssize_t temp_input_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	int temp, ret;

	ret = r8s_read_temp(to_sensor_dev_attr(attr)->index, &temp);
	if (ret)
		return ret;
	return sysfs_emit(buf, "%d\n", temp * 1000);
}

static ssize_t temp_label_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%s\n", r8s_labels[to_sensor_dev_attr(attr)->index]);
}

#define R8S_TEMP_ATTR(n, id) \
	static SENSOR_DEVICE_ATTR_RO(temp##n##_input, temp_input, id); \
	static SENSOR_DEVICE_ATTR_RO(temp##n##_label, temp_label, id)

R8S_TEMP_ATTR(1, 0);
R8S_TEMP_ATTR(2, 1);
R8S_TEMP_ATTR(3, 2);
R8S_TEMP_ATTR(4, 3);
R8S_TEMP_ATTR(5, 4);
R8S_TEMP_ATTR(6, 5);

#define R8S_TEMP_GROUP(n) \
	&sensor_dev_attr_temp##n##_input.dev_attr.attr, \
	&sensor_dev_attr_temp##n##_label.dev_attr.attr

static struct attribute *r8s_attrs[] = {
	R8S_TEMP_GROUP(1), R8S_TEMP_GROUP(2), R8S_TEMP_GROUP(3),
	R8S_TEMP_GROUP(4), R8S_TEMP_GROUP(5), R8S_TEMP_GROUP(6), NULL,
};
ATTRIBUTE_GROUPS(r8s);

static int __init r8s_thermal_init(void)
{
	struct device_node *np;
	unsigned int zone, valid = 0;
	int temp, ret;

	r8s_pdev = platform_device_register_simple("r8s-acpm-thermal",
						 PLATFORM_DEVID_NONE, NULL, 0);
	if (IS_ERR(r8s_pdev))
		return PTR_ERR(r8s_pdev);
	np = of_find_compatible_node(NULL, NULL, "samsung,exynos990-acpm-ipc");
	if (!np) {
		ret = -ENODEV;
		goto err;
	}
	r8s_acpm = devm_acpm_get_by_node(&r8s_pdev->dev, np);
	of_node_put(np);
	if (IS_ERR(r8s_acpm)) {
		ret = PTR_ERR(r8s_acpm);
		goto err;
	}
	if (!r8s_acpm->ops || !r8s_acpm->ops->tmu.read_temp) {
		ret = -EOPNOTSUPP;
		goto err;
	}
	for (zone = 0; zone < ARRAY_SIZE(r8s_labels); zone++) {
		ret = r8s_read_temp(zone, &temp);
		if (!ret) {
			valid++;
			dev_info(&r8s_pdev->dev, "%s: %d C (unqualified telemetry)\n",
				 r8s_labels[zone], temp);
		} else {
			dev_warn(&r8s_pdev->dev, "%s unavailable: %d\n",
				 r8s_labels[zone], ret);
		}
	}
	if (!valid) {
		ret = -ENODATA;
		goto err;
	}
	r8s_hwmon = hwmon_device_register_with_groups(&r8s_pdev->dev,
						     "r8s_acpm", NULL, r8s_groups);
	if (IS_ERR(r8s_hwmon)) {
		ret = PTR_ERR(r8s_hwmon);
		r8s_hwmon = NULL;
		goto err;
	}
	for (zone = 0; zone < ARRAY_SIZE(r8s_cpu_zones); zone++) {
		struct r8s_cpu_zone *cpu_zone = &r8s_cpu_zones[zone];
		struct thermal_zone_device *tz;

		/* A CPU zone must have a valid initial reading before activation. */
		ret = r8s_read_temp(cpu_zone->id, &temp);
		if (ret)
			goto err;
		tz = thermal_zone_device_register_with_trips(cpu_zone->name,
				&r8s_cpu_trip, 1, cpu_zone, &r8s_zone_ops,
				&r8s_cpu_params, 1000, 1000);
		if (IS_ERR(tz)) {
			ret = PTR_ERR(tz);
			goto err;
		}
		cpu_zone->tz = tz;
		ret = thermal_zone_device_enable(tz);
		if (ret)
			goto err;
	}
	return 0;
err:
	r8s_unregister_zones();
	if (r8s_hwmon) {
		hwmon_device_unregister(r8s_hwmon);
		r8s_hwmon = NULL;
	}
	platform_device_unregister(r8s_pdev);
	return ret;
}

static void __exit r8s_thermal_exit(void)
{
	r8s_unregister_zones();
	if (r8s_hwmon) {
		hwmon_device_unregister(r8s_hwmon);
		r8s_hwmon = NULL;
	}
	platform_device_unregister(r8s_pdev);
}

module_init(r8s_thermal_init);
module_exit(r8s_thermal_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("r8s ACPM read-only sensors with passive CPU frequency cooling");
