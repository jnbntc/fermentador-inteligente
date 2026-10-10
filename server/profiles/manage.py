"""Instalación inicial, respaldo y verificación por SSH; copias privadas en el servidor."""
import argparse
import base64
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect','backup','snapshot','install','update','assets','verify','rollback'])
    parser.add_argument('--host',required=True)
    parser.add_argument('--identity',type=Path)
    parser.add_argument('--runtime-image',default='telemetria_birra-agente_forecasting')
    parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    args.state_dir.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parent
    request={'action':args.action,'runtime_image':args.runtime_image}
    if args.action in ('backup','install','update'):
        observed=json.loads((args.state_dir/'inspect.json').read_text())
        request.update(observed)
    if args.action in ('install','update','rollback'):
        request['backup']=json.loads((args.state_dir/'backup.json').read_text())['backup']
    if args.action in ('install','update','assets'):
        request['patch_builder']=(root/'nodered_patch.py').read_text()
        files={'compose.yml':root/'compose.yml','app/server/__init__.py':root.parent/'__init__.py',
               'app/server/fermentation.py':root.parent/'fermentation.py'}
        files.update({'app/server/profiles/'+p.name:p for p in root.iterdir() if p.suffix in ('.py','.html') and p.name not in ('manage.py','nodered_patch.py')})
        request['files']={name:base64.b64encode(path.read_bytes()).decode() for name,path in files.items()}
        if args.action in ('update','assets'):
            prior=max((p for p in (args.state_dir/'install.json',args.state_dir/'update.json',args.state_dir/'assets.json') if p.exists()),key=lambda p:p.stat().st_mtime)
            request['expected_files_sha256']=json.loads(prior.read_text())['app_files_sha256']
        if args.action=='assets':
            request['files']={'app/server/profiles/index.html':request['files']['app/server/profiles/index.html']}
    command=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no','-o','ConnectTimeout=8']
    if args.identity: command+=['-i',str(args.identity)]
    command += [args.host,'python3 -c '+shlex.quote((root/'scripts/remote.py').read_text())]
    result=subprocess.run(command,input=json.dumps(request).encode(),capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr.decode())
    data=json.loads(result.stdout)
    (args.state_dir/(args.action+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
