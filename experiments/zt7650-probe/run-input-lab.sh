#!/bin/bash
# Finite lab wrapper; never replaces installed modules or retries unload.
set -u
test "$#" = 1 || { echo "Usage: $0 LAB_DIRECTORY" >&2; exit 2; }
lab_dir=$1
test ! -e "$lab_dir/run.log" || { echo "Existing evidence: choose a new directory" >&2; exit 2; }
exec >"$lab_dir/run.log" 2>&1
cd "$lab_dir" || exit 1
loaded=0
capture_pid=
boot_before=$(timeout 3s cat /proc/sys/kernel/random/boot_id)
health() {
    test "$(timeout 3s cat /proc/sys/kernel/random/boot_id)" = "$boot_before" || return 1
    test "$(timeout 3s cat /sys/module/exynos990_cpufreq/parameters/failsafe_mask)" = 0 || return 1
    test "$(timeout 3s cat /sys/module/r8s_acpm_thermal/parameters/fault_mask)" = 0 || return 1
    test "$(timeout 3s cat /sys/module/acpm_protocol/parameters/single_slot_diag_once)" = N || return 1
    for sensor in /sys/class/hwmon/hwmon*/temp*_input; do
        value=$(timeout 3s cat "$sensor") || return 1
        test "$value" -lt 70000 || return 1
    done
}
rail_off() {
    matches=0
    for regulator in /sys/class/regulator/regulator.*; do
        if test "$(timeout 3s cat "$regulator/name")" = tsp_ldo_en; then
            matches=$((matches + 1))
            test "$(timeout 3s cat "$regulator/state")" = disabled || return 1
        fi
    done
    test "$matches" = 1 || return 1
    awk '$1 == "tsp_ldo_en" { found=1; if ($2 != 0 || $3 != 0) bad=1 } END { exit (!found || bad) }' /sys/kernel/debug/regulator/regulator_summary
}
cleanup() {
    trap - EXIT
    trap '' INT TERM HUP
    if test -n "$capture_pid"; then
        kill "$capture_pid" 2>/dev/null || true
        wait "$capture_pid" 2>/dev/null || true
    fi
    if test "$loaded" = 1 && test -d /sys/module/r8s_zt7650_input; then
        rmmod r8s_zt7650_input &
        unload_pid=$!
        unload_deadline=$((SECONDS + 20))
        while kill -0 "$unload_pid" 2>/dev/null; do
            if ((SECONDS >= unload_deadline)); then
                echo 'RESTORATION_FAILED: unload timeout; no retry or wait'
                kill -TERM "$unload_pid" 2>/dev/null || true
                exit 1
            fi
            sleep 1
        done
        wait "$unload_pid"
        unload_rc=$?
        echo "UNLOAD_COMMAND_RC=$unload_rc"
        if test "$unload_rc" != 0; then
            echo 'RESTORATION_FAILED: stop tests; no automatic retry'
            exit 1
        fi
    fi
    test ! -d /sys/module/r8s_zt7650_input || { echo 'RESTORATION_FAILED: module remains'; exit 1; }
    test -d /sys/bus/i2c/devices/0-0020 || { echo 'RESTORATION_FAILED: client absent'; exit 1; }
    test ! -L /sys/bus/i2c/devices/0-0020/driver || { echo 'RESTORATION_FAILED: bound client'; exit 1; }
    rail_off || { echo 'RESTORATION_FAILED: rail'; exit 1; }
    health || { echo 'RESTORATION_FAILED: health'; exit 1; }
    if test "$loaded" = 1; then echo RESTORATION_CONFIRMED; else echo NOT_STARTED; fi
}
trap cleanup EXIT
trap 'exit 1' INT TERM HUP
health || exit 1
rail_off || exit 1
test -d /sys/bus/i2c/devices/0-0020 || exit 1
test ! -L /sys/bus/i2c/devices/0-0020/driver || exit 1
test ! -d /sys/module/r8s_zt7650_input || exit 1
test "$(modinfo -F vermagic r8s_zt7650_input.ko | cut -d' ' -f1)" = "$(uname -r)" || exit 1
loaded=1
insmod ./r8s_zt7650_input.ko arm=1 lab_seconds=120 || exit 1
input_node=
input_matches=0
for name in /sys/class/input/event*/device/name; do
    if test "$(cat "$name")" = 'ZT7650 finite polling experiment'; then
        input_matches=$((input_matches + 1))
        test "$(readlink -f "$(dirname "$name")")" != '' || exit 1
        case $(readlink -f "$(dirname "$name")") in */0-0020/*) ;; *) exit 1 ;; esac
        input_node=/dev/input/$(basename "$(dirname "$(dirname "$name")")")
    fi
done
test "$input_matches" = 1 && test -n "$input_node" || exit 1
stdbuf -oL -eL evtest "$input_node" >events.log 2>&1 &
capture_pid=$!
echo "INPUT_CAPTURE_READY=$input_node"
capture_deadline=$((SECONDS + 100))
while ((SECONDS < capture_deadline)); do
    sleep 2
    health || { echo HEALTH_GUARD_ABORT; exit 1; }
    if ! kill -0 "$capture_pid" 2>/dev/null; then
        wait "$capture_pid"; echo "CAPTURE_EARLY_EXIT=$?"; capture_pid=; exit 1
    fi
done
echo CAPTURE_WINDOW_ENDED
