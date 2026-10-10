"""Respalda Grafana o ejecuta la migración inicial mediante SSH con clave."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['backup', 'migrate'])
    p.add_argument('--host', required=True, help='Destino SSH usuario@servidor')
    p.add_argument('--identity', type=Path, help='Clave privada existente; nunca se imprime')
    p.add_argument('--backup', help='Directorio de respaldo remoto devuelto por backup')
    p.add_argument('--dashboard-uid', help='UID del dashboard existente que se preservará')
    p.add_argument('--output', type=Path, help='Guardar solamente metadata no secreta localmente')
    a = p.parse_args()
    if a.action == 'migrate' and not (a.backup and a.dashboard_uid):
        p.error('migrate requiere --backup y --dashboard-uid')
    request = {}
    if a.action == 'migrate':
        request = {'backup': a.backup, 'uid': a.dashboard_uid,
                   'dashboard': json.loads((ROOT/'dashboard.json').read_text())}
    helper = ROOT/'scripts'/('backup_remote.py' if a.action == 'backup' else 'migrate_remote.py')
    argv = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=8']
    if a.identity: argv += ['-i', str(a.identity.expanduser())]
    argv += [a.host, 'python3 -c '+shlex.quote(helper.read_text())]
    result = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr or 'Falló la operación remota; revisar el respaldo antes de repetir.')
    data = json.loads(result.stdout)
    text = json.dumps(data, ensure_ascii=False, indent=2)+'\n'
    if a.output: a.output.write_text(text)
    print(text, end='')


if __name__ == '__main__': main()
