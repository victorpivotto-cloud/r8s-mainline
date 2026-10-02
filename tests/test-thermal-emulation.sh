#!/bin/sh
# Exercise Linux thermal/QoS with synthetic temperatures, no CPU workload.
set -eu
reset() {
    for z in /sys/class/thermal/thermal_zone*; do
        case $(cat "$z/type") in
            r8s_big|r8s_mid|r8s_little) printf 0 > "$z/emul_temp" || true ;;
        esac
    done
}
trap reset EXIT HUP INT TERM
show() {
    printf 'zone=%s temp=%s cdev=%s state=%s max_khz=%s\n' \
        "$(cat "$zone/type")" "$(cat "$zone/temp")" "$(cat "$cdev/type")" \
        "$(cat "$cdev/cur_state")" "$(cat "$policy/scaling_max_freq")"
}
count=0
for zone in /sys/class/thermal/thermal_zone*; do
    case $(cat "$zone/type") in
        r8s_big) policy=/sys/devices/system/cpu/cpufreq/policy6 ;;
        r8s_mid) policy=/sys/devices/system/cpu/cpufreq/policy4 ;;
        r8s_little) policy=/sys/devices/system/cpu/cpufreq/policy0 ;;
        *) continue ;;
    esac
    count=$((count + 1))
    [ "$(cat "$zone/trip_point_0_type")" = passive ]
    [ "$(cat "$zone/trip_point_0_temp")" = 83000 ]
    [ "$(cat "$zone/trip_point_0_hyst")" = 5000 ]
    [ "$(cat "$zone/policy")" = step_wise ]
    cdev="$zone/cdev0"
    [ -e "$cdev/cur_state" ]
    base=$(cat "$policy/scaling_max_freq")
    printf 0 > "$zone/emul_temp"
    show
    printf 86000 > "$zone/emul_temp"
    sleep 4
    show
    [ "$(cat "$cdev/cur_state")" -gt 0 ]
    [ "$(cat "$policy/scaling_max_freq")" -lt "$base" ]
    # Inside hysteresis: cooling must remain active.
    printf 81000 > "$zone/emul_temp"
    sleep 2
    show
    [ "$(cat "$cdev/cur_state")" -gt 0 ]
    printf 0 > "$zone/emul_temp"
    # Allow step_wise to walk back through the full frequency table.
    attempts=0
    while [ "$(cat "$cdev/cur_state")" -ne 0 ]; do
        [ "$attempts" -lt 20 ]
        sleep 1
        attempts=$((attempts + 1))
    done
    show
    [ "$(cat "$policy/scaling_max_freq")" = "$base" ]
done
[ "$count" = 3 ]
echo 'PASS: all three CPU bindings, QoS caps, hysteresis and restoration'
