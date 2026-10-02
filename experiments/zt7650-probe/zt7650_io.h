/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef ZT7650_IO_H
#define ZT7650_IO_H
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/unaligned.h>
#include <linux/string.h>

static inline int zt_read(struct i2c_client *client, u16 reg, void *data, int len)
{
	u8 address[2];
	int ret;

	put_unaligned_le16(reg, address);
	ret = i2c_master_send(client, address, sizeof(address));
	if (ret != sizeof(address))
		return ret < 0 ? ret : -EIO;
	usleep_range(50, 100);
	/* Diagnostic canary: distinguish actual RX from a stale untouched buffer. */
	memset(data, 0xa5, len);
	ret = i2c_master_recv(client, data, len);
	if (ret != len)
		return ret < 0 ? ret : -EIO;
	usleep_range(10, 20);
	return 0;
}

static inline int zt_write_u16(struct i2c_client *client, u16 reg, u16 value)
{
	u8 packet[4];
	int ret;

	put_unaligned_le16(reg, packet);
	put_unaligned_le16(value, packet + 2);
	ret = i2c_master_send(client, packet, sizeof(packet));
	if (ret != sizeof(packet))
		return ret < 0 ? ret : -EIO;
	usleep_range(10, 20);
	return 0;
}

static inline int zt_command(struct i2c_client *client, u16 command)
{
	u8 packet[2];
	int ret;

	put_unaligned_le16(command, packet);
	ret = i2c_master_send(client, packet, sizeof(packet));
	if (ret != sizeof(packet))
		return ret < 0 ? ret : -EIO;
	usleep_range(10, 20);
	return 0;
}

static inline int zt_resident_start(struct i2c_client *client)
{
	int ret;

	/* Normal resident boot from vendor zt_power_sequence, not an upgrade. */
	ret = zt_command(client, 0x14f0);
	if (ret)
		return ret;
	ret = zt_write_u16(client, 0x12f0, 1);
	if (ret)
		return ret;
	msleep(2);
	ret = zt_write_u16(client, 0x11f0, 1);
	if (!ret)
		msleep(150);
	return ret;
}

#endif
