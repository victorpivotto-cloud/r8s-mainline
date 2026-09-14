/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef __EXYNOS_S2MPU_WIFI_H
#define __EXYNOS_S2MPU_WIFI_H

#include <linux/types.h>

#if IS_ENABLED(CONFIG_EXYNOS990_S2MPU_WIFI)
int exynos990_s2mpu_wifi_grant(dma_addr_t base, size_t size, bool grant);
#else
static inline int exynos990_s2mpu_wifi_grant(dma_addr_t base, size_t size,
					     bool grant)
{
	return 0;
}
#endif

#endif /* __EXYNOS_S2MPU_WIFI_H */
