"""Resuelve referencias de datasource/UID sin leer credenciales."""
import argparse
import copy
import json
from pathlib import Path


def render(template, datasource_uid, dashboard_uid=None):
    def resolve(value):
        if isinstance(value, dict): return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list): return [resolve(v) for v in value]
        return datasource_uid if value == '${DS_INFLUXDB}' else value
    dashboard = resolve(copy.deepcopy(template))
    dashboard.pop('__inputs', None)
    if dashboard_uid: dashboard['uid'] = dashboard_uid
    return dashboard


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasource-uid', required=True)
    parser.add_argument('--dashboard-uid')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    template = json.loads((Path(__file__).parent/'dashboard.json').read_text())
    args.output.write_text(json.dumps(render(template, args.datasource_uid, args.dashboard_uid), ensure_ascii=False, indent=2)+'\n')
