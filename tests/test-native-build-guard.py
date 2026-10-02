#!/usr/bin/env python3
"""Finite native-build diagnostic; no install, reboot, firmware or partitions."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

BASE = Path('/sys/devices/system/cpu/cpufreq')
CAPS = {0: 1066000, 4: 1264000, 6: 1248000}
READ = lambda p: Path(p).read_text().strip()
BOOT = Path('/proc/sys/kernel/random/boot_id')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--state', required=True, type=Path)
parser.add_argument('--build-dir', type=Path)
parser.add_argument('--seconds', type=int, default=60)
parser.add_argument('--restore', action='store_true')
args = parser.parse_args()

def restore():
    if not args.state.exists():
        return
    state = json.loads(args.state.read_text())
    if state['boot'] != READ(BOOT):
        raise RuntimeError('different boot: do not replay previous limits')
    failures = []
    for number, value in state['old_max'].items():
        try:
            (BASE/f'policy{number}/scaling_max_freq').write_text(str(value))
        except OSError as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError('; '.join(failures))
    args.state.rename(args.state.with_name(args.state.name+'.restored'))
    descriptor = os.open(args.state.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps({'event': 'limits-restored', 'max_kHz': state['old_max']}), flush=True)

if args.restore:
    if args.state.exists():
        with (args.state.parent/'build.lock').open('a') as restore_lock:
            fcntl.flock(restore_lock, fcntl.LOCK_EX)
            restore()
    raise SystemExit(0)
if not 1 <= args.seconds <= 180 or args.build_dir is None:
    parser.error('duration 1..180s and build directory required')
if not (args.build_dir/'build.ninja').is_file():
    parser.error('missing configured native build.ninja')
args.state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(args.state.parent, 0o700)
lock = (args.state.parent/'build.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
if args.state.exists():
    parser.error('state already exists: preserve previous run')
hwmon = next((p for p in Path('/sys/class/hwmon').glob('hwmon*')
              if READ(p/'name') == 'r8s_acpm'), None)
if hwmon is None:
    raise SystemExit('missing ACPM hwmon')
start = time.monotonic()
child = None
state_saved = False
code = 2
log = args.state.with_suffix('.jsonl').open('x')
os.chmod(log.name, 0o600)
compiler_log = args.state.with_suffix('.compiler.log').open('x')
os.chmod(compiler_log.name, 0o600)

def emit(row):
    line = json.dumps(row)
    log.write(line+'\n'); log.flush(); os.fsync(log.fileno())
    print(line, flush=True)

def sample():
    battery = Path('/sys/class/power_supply/max170xx_battery')
    row = {'event': 'sample', 'elapsed': round(time.monotonic()-start, 2),
           'temps_mC': [int(READ(hwmon/f'temp{n}_input')) for n in range(1, 7)],
           'battery_mC': int(READ(battery/'temp'))*100,
           'voltage_uV': int(READ(battery/'voltage_now')),
           'failsafe': int(READ('/sys/module/exynos990_cpufreq/parameters/failsafe_mask')),
           'max_kHz': [int(READ(BASE/f'policy{n}/scaling_max_freq')) for n in CAPS]}
    # Save the triggering sample as well, unlike the previous synthetic harness.
    emit(row)
    if any(not 1000 <= t <= 127000 for t in row['temps_mC']):
        raise RuntimeError('invalid ACPM temperature')
    if max(row['temps_mC']) >= 70000 or not 0 <= row['battery_mC'] < 43000:
        raise RuntimeError('temperature guard')
    if row['failsafe'] or not 3600000 <= row['voltage_uV'] <= 4500000:
        raise RuntimeError('failsafe or voltage guard')

def interrupted(number, frame):
    raise RuntimeError('signal '+str(number))

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
signal.signal(signal.SIGHUP, interrupted)
try:
    sample()
    old_max = {}
    for number, cap in CAPS.items():
        policy = BASE/f'policy{number}'
        minimum = int(READ(policy/'scaling_min_freq'))
        old = int(READ(policy/'scaling_max_freq'))
        available = [int(x) for x in READ(policy/'scaling_available_frequencies').split()]
        if cap not in available or minimum > cap:
            raise RuntimeError('cap is not an available safe frequency')
        old_max[str(number)] = old
    state = {'boot': READ(BOOT), 'old_max': old_max, 'caps': CAPS}
    pending = args.state.with_name(args.state.name+'.pending')
    with pending.open('x') as output:
        os.chmod(pending, 0o600)
        json.dump(state, output); output.flush(); os.fsync(output.fileno())
    pending.rename(args.state)
    state_saved = True
    for number, cap in CAPS.items():
        (BASE/f'policy{number}/scaling_max_freq').write_text(str(min(cap, old_max[str(number)])))
    sample()
    emit({'event': 'build-start', 'seconds': args.seconds, 'jobs': 1, 'cpu': 0})
    blocked = {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    try:
        child = subprocess.Popen(['timeout', '--signal=TERM', '--kill-after=3', str(args.seconds),
                                  'taskset', '-c', '0', 'nice', '-n', '15',
                                  'ninja', '-C', str(args.build_dir), '-j1'],
                                  stdout=compiler_log, stderr=subprocess.STDOUT, start_new_session=True,
                                  preexec_fn=lambda: signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask))
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    while child.poll() is None:
        sample()
        time.sleep(0.5)
    sample()
    result = child.returncode
    if result not in (0, 124):
        raise RuntimeError('native build failed: '+str(result))
    emit({'event': 'build-complete' if result == 0 else 'bounded-window-ended',
          'returncode': result, 'elapsed': round(time.monotonic()-start, 2),
          'qualification': False})
    code = 0
except Exception as error:
    emit({'event': 'abort', 'reason': str(error)})
finally:
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, signal.SIG_IGN)
    try:
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
    finally:
        # Restoration still runs if process termination or log close fails.
        try:
            compiler_log.close()
        finally:
            if state_saved:
                try:
                    restore()
                except Exception as error:
                    code = 3
                    try:
                        emit({'event': 'restore-failed', 'reason': str(error)})
                    except OSError:
                        pass
            log.close()
raise SystemExit(code)
