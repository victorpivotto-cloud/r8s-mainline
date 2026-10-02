#!/bin/sh
# Fault injection and stalled-poll tests, no heating workload.
set -eu
fault=/sys/module/r8s_acpm_thermal/parameters/fault_mask
mask=/sys/module/exynos990_cpufreq/parameters/failsafe_mask
cleanup() {
    # Restore the module for the running kernel even after a failed assertion.
    modprobe r8s_acpm_thermal 2>/dev/null || true
    [ ! -e "$fault" ] || printf 0 > "$fault"
    for z in /sys/class/thermal/thermal_zone*; do
        case $(cat "$z/type") in r8s_*) printf enabled > "$z/mode" || true;; esac
    done
}
trap cleanup EXIT HUP INT TERM
wait_mask() {
    attempts=0
    while [ "$(cat "$mask")" != "$1" ]; do
        [ "$attempts" -lt 15 ] || { echo "FAIL: mask expected $1 actual $(cat "$mask")"; exit 1; }
        sleep 1
        attempts=$((attempts + 1))
    done
}
cap() { cat /sys/devices/system/cpu/cpufreq/policy$1/scaling_max_freq; }
show() { printf '%s mask=%s caps=%s/%s/%s\n' "$1" "$(cat "$mask")" "$(cap 0)" "$(cap 4)" "$(cap 6)"; }
wait_mask 0
show baseline
printf 1 > "$fault"
wait_mask 4
[ "$(cap 6)" = 546000 ] && [ "$(cap 4)" = 2600000 ] && [ "$(cap 0)" = 2002000 ]
show BIG_sensor_error
printf 0 > "$fault"
wait_mask 0
show recovered
for mid in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$mid/type")" != r8s_mid ] || break
done
[ "$(cat "$mid/type")" = r8s_mid ]
printf disabled > "$mid/mode"
wait_mask 2
[ "$(cap 4)" = 507000 ]
show MID_polling_stopped
printf enabled > "$mid/mode"
wait_mask 0
printf 7 > "$fault"
wait_mask 7
[ "$(cap 0)" = 442000 ] && [ "$(cap 4)" = 507000 ] && [ "$(cap 6)" = 546000 ]
show all_sensor_errors
printf 0 > "$fault"
wait_mask 0
if rmmod exynos990_cpufreq 2>/dev/null; then
    echo 'FAIL: CPU driver unloaded while sensor module depends on it'
    exit 1
fi
echo 'PASS: CPU driver unload correctly refused while sensors loaded'
rmmod r8s_acpm_thermal
wait_mask 7
show sensors_unloaded
modprobe r8s_acpm_thermal
wait_mask 0
show sensors_reloaded
echo 'PASS: failures, missing polling, recovery, dependency and sensor unload'
