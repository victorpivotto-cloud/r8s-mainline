#!/bin/sh
# Finite idle qualification. Does not generate load or change device settings.
set -eu
duration=${1:-86400}
interval=${2:-60}
case "$duration:$interval" in *[!0-9:]*|:*|*:) exit 2 ;; esac
[ "$duration" -ge 1 ] && [ "$duration" -le 86400 ]
[ "$interval" -ge 1 ] && [ "$interval" -le 300 ]
dir=/var/log/qualificacao-s20
mkdir -p "$dir"
chmod 700 "$dir"
start=$(date '+%Y-%m-%d %H:%M:%S')
boot=$(cat /proc/sys/kernel/random/boot_id)
# Cursor avoids missing errors if NTP corrects the clock backwards after boot.
cursor=$(journalctl -k -b -n 1 --show-cursor -o cat | sed -n 's/^-- cursor: //p')
[ -n "$cursor" ] || exit 1
file="$dir/$(date '+%Y%m%d-%H%M%S')-$boot.tsv"
printf '# start=%s duration=%s interval=%s kernel=%s boot=%s\n' \
    "$start" "$duration" "$interval" "$(uname -r)" "$boot" > "$file"
printf 'timestamp\tuptime_s\tload1\tbattery_pct\tbattery_mC\tBIG_mC\tMID_mC\tLITTLE_mC\tG3D_mC\tISP_mC\tNPU_mC\tmax0_kHz\tmax4_kHz\tmax6_kHz\tcooling0\tcooling4\tcooling6\tdvfs_errors_since_start\tfailed_units\tfailsafe_mask\tboot_id\n' >> "$file"
read_or_na() { cat "$1" 2>/dev/null || printf NA; }
uptime_seconds() { cut -d. -f1 /proc/uptime; }
begin=$(uptime_seconds)
completed=no
finish() { printf '# finished=%s completed=%s\n' "$(date -Is)" "$completed" >> "$file"; }
trap finish EXIT
# An intentional service stop is an incomplete run, not an execution failure.
trap 'exit 0' HUP INT TERM
echo "Qualification log: $file"
while :; do
    hwmon=
    for h in /sys/class/hwmon/hwmon*; do
        [ "$(cat "$h/name" 2>/dev/null)" != r8s_acpm ] || hwmon=$h
    done
    errors=$(journalctl -k -b --after-cursor="$cursor" --no-pager -o cat | \
        awk '/Failed to change cpu frequency|exynos990-cpufreq:.*failed:/{n++} END{print n+0}')
    failed=$(systemctl --failed --no-legend --plain | awk 'END{print NR+0}')
    battery_temp=$(read_or_na /sys/class/power_supply/max170xx_battery/temp)
    case "$battery_temp" in
        ''|*[!0-9]*) battery_temp=NA ;;
        *) battery_temp=$((battery_temp * 100)) ;;
    esac
    printf '%s\t%s\t%s\t%s\t%s' "$(date -Is)" "$(uptime_seconds)" \
        "$(cut -d' ' -f1 /proc/loadavg)" \
        "$(read_or_na /sys/class/power_supply/max170xx_battery/capacity)" \
        "$battery_temp" >> "$file"
    for n in 1 2 3 4 5 6; do
        printf '\t%s' "$(read_or_na "$hwmon/temp${n}_input")" >> "$file"
    done
    for n in 0 4 6; do
        printf '\t%s' "$(read_or_na /sys/devices/system/cpu/cpufreq/policy$n/scaling_max_freq)" >> "$file"
    done
    for n in 0 4 6; do
        state=NA
        for c in /sys/class/thermal/cooling_device*; do
            [ "$(cat "$c/type")" != "cpufreq-cpu$n" ] || state=$(read_or_na "$c/cur_state")
        done
        printf '\t%s' "$state" >> "$file"
    done
    printf '\t%s\t%s\t%s\t%s\n' "$errors" "$failed" \
        "$(read_or_na /sys/module/exynos990_cpufreq/parameters/failsafe_mask)" \
        "$(cat /proc/sys/kernel/random/boot_id)" >> "$file"
    now=$(uptime_seconds)
    if [ "$((now - begin))" -ge "$duration" ]; then
        completed=yes
        break
    fi
    sleep "$interval"
done
