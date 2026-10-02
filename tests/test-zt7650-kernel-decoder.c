/* SPDX-License-Identifier: GPL-2.0-only */
#define ZT7650_HOST_TEST
#include <assert.h>
#include <stdio.h>
#include "../experiments/zt7650-probe/zt7650_events.h"

int main(void)
{
	u8 b[160] = { 0x40, 0xab, 0xde, 0xcf, 3, 4, 0xa5, 0x40 };
	struct zt_event events[10], old[10];
	unsigned int nr = 999;

	memset(events, 0x77, sizeof(events));
	assert(zt_decode(b, 16, 4095, 4095, events, &nr) == 0);
	assert(nr == 1 && events[0].id == 0 && events[0].status == 1);
	assert(events[0].x == 0xabc && events[0].y == 0xdef);
	assert(events[0].type == 9 && events[0].pressure == 37);
	assert(events[0].major == 3 && events[0].minor == 4);
	b[0] = 0xc0; /* Release ID0 with unusable coordinates. */
	assert(zt_decode(b, 16, 1079, 2399, events, &nr) == 0);
	assert(nr == 1 && events[0].status == 3);
	assert(events[0].x == 0 && events[0].y == 0);
	b[0] = 0x3c; /* NONE skips ID15 and coordinates, but counts in batch. */
	assert(zt_decode(b, 16, 1079, 2399, events, &nr) == 0 && nr == 0);
	memset(b, 0, sizeof(b)); b[7] = 9;
	for (int i = 0; i < 10; i++) b[i * 16] = 0x40 | (i << 2);
	assert(zt_decode(b, 160, 1079, 2399, events, &nr) == 0 && nr == 10);
	assert(events[9].id == 9);
	memcpy(old, events, sizeof(old)); nr = 123;
	b[9 * 16] = 0x68; /* Active ID10 in the final packet, entire batch rejected. */
	assert(zt_decode(b, 160, 1079, 2399, events, &nr) == -EPROTO);
	assert(nr == 123 && memcmp(old, events, sizeof(old)) == 0);
	b[9 * 16] = 0x65; /* Bad EID in a later packet. */
	assert(zt_decode(b, 160, 1079, 2399, events, &nr) == -EPROTO);
	assert(nr == 123 && memcmp(old, events, sizeof(old)) == 0);
	b[7] = 10;
	assert(zt_decode(b, 160, 1079, 2399, events, &nr) == -EPROTO);
	b[7] = 9;
	assert(zt_decode(b, 159, 1079, 2399, events, &nr) == -EPROTO);
	assert(zt_decode(b, 15, 1079, 2399, events, &nr) == -EINVAL);
	memset(b, 0, sizeof(b)); b[0] = 0x80;
	b[1] = 0x43; b[2] = 0x95; b[3] = 0x7f; /* X1079 Y2399. */
	assert(zt_decode(b, 16, 1079, 2399, events, &nr) == 0);
	assert(events[0].x == 1079 && events[0].y == 2399);
	b[3] = 0x8f;
	assert(zt_decode(b, 16, 1079, 2399, events, &nr) == -ERANGE);
	assert(zt_decode(b, 16, 4096, 2399, events, &nr) == -EINVAL);
	puts("PASS: C decoder nibbles, type, release, NONE, bounds, count and atomicity");
	return 0;
}
