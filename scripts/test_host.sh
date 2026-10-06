#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir=$(mktemp -d /tmp/fermentador-tests.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
compiler=${CXX:-c++}
for name in cooling_guard thermal_controller; do
    "$compiler" -std=c++11 -Wall -Wextra -Werror -Iinclude "test/${name}_test.cpp" -o "$build_dir/$name"
    "$build_dir/$name" > "$build_dir/${name}.log"
    cat "$build_dir/${name}.log"
done
python3 - "$build_dir/thermal_controller.log" <<'PY'
import json
import sys
from pathlib import Path
rows = [json.loads(line[5:]) for line in Path(sys.argv[1]).read_text().splitlines() if line.startswith('JSON ')]
assert len(rows) == 2
for row in rows:
    assert row['ambiente'] is None and row['ambiente_valid'] is False
    assert row['mqtt'] is False and row['relay'] is False and row['dry_run'] is True
    assert row['message_seq'] == 42 and row['mqtt_losses'] == 1
assert rows[1]['fault'] == 'mosto_sensor' and rows[1]['controller_state'] == 'SENSOR_FAULT'
assert rows[1]['mosto'] is None
print('PASS telemetry JSON parsed and checked')
PY
python3 -m unittest discover -s test -p 'test_*.py' -v
