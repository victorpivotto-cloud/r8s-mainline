#!/bin/sh
set -eu
mask=/sys/module/exynos990_cpufreq/parameters/failsafe_mask
zone=
for z in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$z/type")" != r8s_big ] || zone=$z
done
[ -n "$zone" ]
cleanup() {
    modprobe r8s_acpm_thermal || true
    if [ -e "$zone/mode" ]; then printf enabled > "$zone/mode"; fi
}
trap cleanup EXIT
printf disabled > "$zone/mode"
sleep 1
[ "$(cat "$mask")" = 4 ]
[ "$(cat /sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq)" = 546000 ]
for n in $(seq 1 30); do
    if cat "$zone/temp" >/dev/null 2>&1; then
        echo 'FAIL: disabled zone returned temperature'
        exit 1
    fi
done
[ "$(cat "$mask")" = 4 ]
printf enabled > "$zone/mode"
# Rapid reads cannot satisfy the spaced recovery samples.
for n in $(seq 1 30); do cat "$zone/temp" >/dev/null; done
[ "$(cat "$mask")" = 4 ]
sleep 6
[ "$(cat "$mask")" = 0 ]
[ "$(cat /sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq)" = 2730000 ]
echo 'PASS: disabled manual reads stay clamped; enable recovers after spaced samples'
for n in 1 2; do
    rmmod r8s_acpm_thermal
    count=0
    for h in /sys/class/hwmon/hwmon*; do
        [ "$(cat "$h/name")" != r8s_acpm ] || count=$((count + 1))
    done
    [ "$count" = 0 ]
    [ "$(cat "$mask")" = 7 ]
    modprobe r8s_acpm_thermal
    sleep 6
    count=0
    for h in /sys/class/hwmon/hwmon*; do
        [ "$(cat "$h/name")" != r8s_acpm ] || count=$((count + 1))
    done
    [ "$count" = 1 ]
    [ "$(cat "$mask")" = 0 ]
done
echo 'PASS: two unload/reload cycles remove hwmon completely and restore exactly one'
