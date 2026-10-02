/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef ZT7650_EVENTS_H
#define ZT7650_EVENTS_H
#ifdef ZT7650_HOST_TEST
#include <stdint.h>
#include <errno.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
#else
#include <linux/types.h>
#include <linux/errno.h>
#include <linux/string.h>
#endif

#define ZT_EVENT_BYTES 16
#define ZT_SLOTS 10

struct zt_event {
	u8 id, status, major, minor, pressure, type;
	u16 x, y;
};

/* Output is committed only after the complete batch validates. */
static inline int zt_decode(const u8 *bytes, unsigned int len,
			    u16 max_x, u16 max_y, struct zt_event *out,
			    unsigned int *nr)
{
	struct zt_event pending[ZT_SLOTS] = { };
	unsigned int total, i, count = 0;

	if (len < ZT_EVENT_BYTES || max_x > 4095 || max_y > 4095)
		return -EINVAL;
	total = 1 + (bytes[7] & 15);
	if (total > ZT_SLOTS || len != total * ZT_EVENT_BYTES)
		return -EPROTO;
	for (i = 0; i < total; i++) {
		const u8 *b = bytes + i * ZT_EVENT_BYTES;
		struct zt_event *e = &pending[count];

		if (b[0] & 3)
			return -EPROTO;
		e->status = b[0] >> 6;
		if (!e->status)
			continue;
		e->id = (b[0] >> 2) & 15;
		if (e->id >= ZT_SLOTS)
			return -EPROTO;
		/* Release must work even when its coordinates are unusable. */
		if (e->status != 3) {
			e->x = (b[1] << 4) | (b[3] >> 4);
			e->y = (b[2] << 4) | (b[3] & 15);
			if (e->x > max_x || e->y > max_y)
				return -ERANGE;
			e->major = b[4];
			e->minor = b[5];
			e->pressure = b[6] & 63;
			e->type = ((b[6] >> 6) << 2) | (b[7] >> 6);
		}
		count++;
	}
	memcpy(out, pending, count * sizeof(*out));
	*nr = count;
	return 0;
}
#endif
