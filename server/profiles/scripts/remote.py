"""Helper ejecutado en edge-01. No imprime flujos ni material de credenciales."""
import copy
import base64
import re
import shutil
import sqlite3
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.request

DATA = Path('/opt/telemetria_birra/nodered')
URL = 'http://127.0.0.1:1880/flows'
CONTAINER = 'birra_nodered'
TAB = '6a09c3f845bb0be5'
request = json.load(sys.stdin)
PROFILES = Path('/opt/telemetria_birra/perfiles')

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4*1024*1024), b''): digest.update(block)
    return digest.hexdigest()

def get():
    req = urllib.request.Request(URL, headers={'Node-RED-API-Version':'v2'})
    with urllib.request.urlopen(req, timeout=15) as response: return json.load(response)

def post(rev, flows):
    req = urllib.request.Request(URL, data=json.dumps({'rev':rev, 'flows':flows}).encode(), method='POST',
        headers={'Node-RED-API-Version':'v2','Node-RED-Deployment-Type':'flows','Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=45) as response: return json.load(response)

def run(args):
    return subprocess.run(args, check=True, capture_output=True)

def private_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    path.chmod(0o600)

def backup():
    if sha(DATA/'flows.json') != request['base_sha256']: raise RuntimeError('La base cambió; no se modificó el runtime')
    runtime = get()
    if runtime['flows'] != json.loads((DATA/'flows.json').read_text()): raise RuntimeError('Runtime y disco difieren')
    root = Path.home()/'.local/state/fermentador/backups'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    directory = root/('nodered-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    archive = directory/'nodered.tar.gz'
    paused = False
    started = time.monotonic()
    try:
        run(['docker','pause',CONTAINER]); paused = True
        if sha(DATA/'flows.json') != request['base_sha256']: raise RuntimeError('La base cambió antes del respaldo')
        run(['tar','-I','gzip -1','-cpf',str(archive),'-C',str(DATA.parent),DATA.name])
        archive.chmod(0o600)
    finally:
        if paused: run(['docker','unpause',CONTAINER])
    pause_seconds = round(time.monotonic()-started, 2)
    expected = {}
    for name in ('flows.json','flows_cred.json','.config.runtime.json','settings.js','package.json','package-lock.json'):
        file = DATA/name
        if file.is_file(): expected[name] = sha(file)
    checked = []
    with tarfile.open(archive,'r:gz') as tar:
        for name,digest in expected.items():
            handle = tar.extractfile('nodered/'+name)
            if handle is None or hashlib.sha256(handle.read()).hexdigest()!=digest: raise RuntimeError('Fallo de integridad del respaldo: '+name)
            checked.append(name)
        # Reading the archive through to its end also checks gzip integrity.
        for _ in tar: pass
    now = get()
    if now['rev'] != runtime['rev']: raise RuntimeError('Cambio concurrente durante el respaldo; no se desplegó')
    private_json(directory/'original-runtime.json',runtime)
    manifest = {'backup':str(directory),'archive_sha256':sha(archive),'base_disk_sha256':request['base_sha256'],
                'revision':runtime['rev'],'critical_files_sha256':expected,'pause_seconds':pause_seconds,
                'context_scope':'Snapshot del contexto persistido; no incluye estado volátil en RAM'}
    private_json(directory/'manifest.json',manifest)
    if PROFILES.exists():
        saved = directory/'perfiles'
        saved.mkdir(mode=0o700)
        for name in ('app','compose.yml','.env'):
            source = PROFILES/name
            if source.is_dir(): shutil.copytree(source,saved/name)
            elif source.is_file(): shutil.copy2(source,saved/name)
        original_db=sqlite3.connect('file:'+str(PROFILES/'data/profiles.sqlite')+'?mode=ro',uri=True)
        snapshot_db=sqlite3.connect(saved/'profiles.sqlite')
        original_db.backup(snapshot_db)
        if snapshot_db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('SQLite backup inválido')
        snapshot_db.close();original_db.close()
        (saved/'profiles.sqlite').chmod(0o600)
        manifest['profiles_sqlite_sha256']=sha(saved/'profiles.sqlite')
        private_json(directory/'manifest.json',manifest)
    return {'backup':str(directory),'archive_bytes':archive.stat().st_size,'archive_sha256':manifest['archive_sha256'],
            'critical_files_verified':checked,'pause_seconds':pause_seconds,'node_count':len(runtime['flows']),
            'runtime_revision_unchanged':True,'private_mode':oct(directory.stat().st_mode & 0o777)}

def deploy():
    directory = Path(request['backup'])
    manifest = json.loads((directory/'manifest.json').read_text())
    original = json.loads((directory/'original-runtime.json').read_text())
    patch = request['patch']
    if sha(directory/'nodered.tar.gz') != manifest['archive_sha256']: raise RuntimeError('Integridad del respaldo incorrecta')
    if sha(DATA/'flows.json') != patch['base_disk_sha256']: raise RuntimeError('La base cambió; abortado sin aplicar')
    current = get()
    if current['rev'] != original['rev'] or current['flows'] != original['flows']: raise RuntimeError('Hay cambios concurrentes; abortado')
    ids = {n['id'] for n in current['flows']}
    if not set(patch['updates']).issubset(ids): raise RuntimeError('Faltan nodos originales')
    if any(n['id'] in ids for n in patch['additions']): raise RuntimeError('Conflicto de IDs nuevos')
    for n in current['flows']:
        if n['id'] in patch['updates'] and n.get('z') != TAB and n['id'] != TAB: raise RuntimeError('Cambio fuera de la pestaña autorizada')
    candidate = copy.deepcopy(current['flows'])
    for n in candidate: n.update(patch['updates'].get(n['id'],{}))
    candidate.extend(copy.deepcopy(patch['additions']))
    by_id = {n['id']:n for n in candidate}
    for node_id in ('ea2429329788f701','416924024672d3bd','91228d4897e037d4','2851528834bc5f7c'):
        if by_id[node_id].get('d') is not True: raise RuntimeError('Falta un bloqueo aprobado')
    for n in current['flows']:
        if n.get('z') != TAB and n['id'] != TAB and n != by_id[n['id']]: raise RuntimeError('Se alteraría configuración compartida')
    private_json(directory/'candidate-runtime.json',{'flows':candidate})
    credential_before = sha(DATA/'flows_cred.json')
    try:
        result = post(current['rev'],candidate)
    except Exception:
        # A timeout may occur after saving; do not issue a second POST blindly.
        observed = get()
        if observed['flows'] != candidate: raise
        result = {'rev':observed['rev']}
    observed = get()
    if observed['flows'] != candidate:
        raise RuntimeError('La configuración observada no coincide; no sobrescribir cambios concurrentes')
    disk = json.loads((DATA/'flows.json').read_text())
    report = {'backup':str(directory),'new_revision':result['rev'],'node_count':len(candidate),
              'runtime_equals_candidate':True,'disk_equals_runtime':disk==candidate,
              'credentials_file_unchanged':sha(DATA/'flows_cred.json')==credential_before,
              'shared_configs_and_clima_unchanged':True,
              'blocked_nodes':['mqtt_setpoint','telegram_sender','start_batch','legacy_timeout'],
              'deployed_disk_sha256':sha(DATA/'flows.json')}
    private_json(directory/'deployment.json',report)
    return report

def rollback():
    directory = Path(request['backup'])
    original = json.loads((directory/'original-runtime.json').read_text())
    candidate = json.loads((directory/'candidate-runtime.json').read_text())['flows']
    current = get()
    if current['flows'] != candidate: raise RuntimeError('Hay cambios concurrentes; no se fuerza rollback')
    result = post(current['rev'], original['flows'])
    if get()['flows'] != original['flows']: raise RuntimeError('Rollback no verificado')
    return {'rollback':True,'rev':result['rev'],'node_count':len(original['flows'])}

def inspect():
    current=get()
    if current['flows']!=json.loads((DATA/'flows.json').read_text()): raise RuntimeError('Runtime y disco difieren')
    nodered=json.loads(run(['docker','inspect',CONTAINER]).stdout)[0]
    if len(nodered['NetworkSettings']['Networks'])!=1: raise RuntimeError('Elegir red explícitamente')
    network=next(iter(nodered['NetworkSettings']['Networks']))
    image=json.loads(run(['docker','image','inspect',request['runtime_image']]).stdout)[0]['Id']
    return {'base_sha256':sha(DATA/'flows.json'),'revision':current['rev'],'node_count':len(current['flows']),
            'network':network,'runtime_image':image,'already_installed':PROFILES.exists()}

def install():
    if PROFILES.exists(): raise RuntimeError('Ya existe el gestor: no se sobrescribe una instalación activa')
    if os.getuid()!=1000: raise RuntimeError('Verificar UID del usuario del contenedor antes de instalar')
    directory=Path(request['backup'])
    original=json.loads((directory/'original-runtime.json').read_text())
    current=get()
    if current!=original or sha(DATA/'flows.json')!=request['base_sha256']: raise RuntimeError('Cambio concurrente: repetir revisión y respaldo')
    env={}
    exec(compile(request['patch_builder'],'nodered_patch.py','exec'),env)
    patch=env['build'](current['flows'],request['base_sha256'])
    image=request['runtime_image'];network=request['network']
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',image) or not re.fullmatch(r'[a-zA-Z0-9_.-]+',network): raise RuntimeError('Runtime/red inválidos')
    existing={c['Name']:c['Id'] for c in json.loads(run(['docker','inspect',CONTAINER,'birra_grafana','birra_broker','birra_influxdb']).stdout)}
    PROFILES.mkdir(mode=0o700)
    (PROFILES/'data').mkdir(mode=0o700)
    for name,content in request['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or not (name.startswith('app/server/') or name=='compose.yml'):
            raise RuntimeError('Ruta de entrega inválida')
        target=PROFILES/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(base64.b64decode(content));target.chmod(0o644)
    (PROFILES/'.env').write_text('PROFILES_IMAGE='+image+'\nPROFILES_NETWORK='+network+'\n')
    (PROFILES/'.env').chmod(0o600)
    compose=['docker','compose','--project-directory',str(PROFILES),'-f',str(PROFILES/'compose.yml')]
    run(compose+['config','--quiet'])
    run(compose+['up','-d','--no-build','--pull','never'])
    health=None
    for _ in range(15):
        result=subprocess.run(['docker','exec','birra_perfiles','python','-c',"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8787/health',timeout=2).read().decode())"],capture_output=True)
        if result.returncode==0:
            health=json.loads(result.stdout);break
        time.sleep(1)
    if not health or health['remote_commands_enabled'] is not False: raise RuntimeError('El servicio nuevo no superó su healthcheck; no se tocó Node-RED')
    # Fixtures solo en /tmp del contenedor; no usan el SQLite activo ni red.
    isolated_tests=run(['docker','exec','birra_perfiles','python','-m','unittest','server.profiles.test_store','-v'])
    request['patch']=patch
    result=deploy()
    after={c['Name']:c['Id'] for c in json.loads(run(['docker','inspect',CONTAINER,'birra_grafana','birra_broker','birra_influxdb']).stdout)}
    if existing!=after: raise RuntimeError('Cambió un contenedor original durante el despliegue')
    result.update(service_health=health,existing_containers_unchanged=True,runtime_image=image,
                  isolated_store_tests_passed=True,
                  app_files_sha256={name:sha(PROFILES/name) for name in request['files']})
    private_json(directory/'profiles-deployment.json',result)
    return result

def verify():
    current=get();by_id={n['id']:n for n in current['flows']}
    blocked=all(by_id[n].get('d') is True for n in ('ea2429329788f701','416924024672d3bd','91228d4897e037d4','2851528834bc5f7c'))
    req=urllib.request.Request('http://127.0.0.1:1880/perfiles/api')
    with urllib.request.urlopen(req,timeout=10) as r: state=json.load(r)
    db=sqlite3.connect('file:'+str(PROFILES/'data/profiles.sqlite')+'?mode=ro',uri=True)
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0];db.close()
    status=json.loads(run(['docker','inspect','birra_perfiles']).stdout)[0]
    return {'node_count':len(current['flows']),'disk_equals_runtime':current['flows']==json.loads((DATA/'flows.json').read_text()),
            'existing_commands_blocked':blocked,'remote_commands_enabled':state['remote_commands_enabled'],
            'recipes':len(state['recipes']),'batches':len(state['batches']),'telemetry_fresh':state['telemetry']['fresh'],
            'mosto_valid':state['telemetry'].get('mosto_valid'),'applied_c':state['telemetry'].get('setpoint_applied'),
            'sqlite_integrity':integrity,'container_state':status['State']['Status'],
            'host_ports_published':bool(status['HostConfig']['PortBindings']),
            'deployed_disk_sha256':sha(DATA/'flows.json')}

def update():
    directory=Path(request['backup'])
    if not (directory/'perfiles/profiles.sqlite').is_file(): raise RuntimeError('Se necesita respaldo SQLite antes de actualizar')
    if get()!=json.loads((directory/'original-runtime.json').read_text()): raise RuntimeError('Cambió Node-RED durante la revisión')
    for name,digest in request['expected_files_sha256'].items():
        if sha(PROFILES/name)!=digest: raise RuntimeError('Código remoto modificado: revisar diferencias antes de actualizar')
    for name,content in request['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or not (name.startswith('app/server/') or name=='compose.yml'):
            raise RuntimeError('Ruta de entrega inválida')
        target=PROFILES/path;target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.new')
        temporary.write_bytes(base64.b64decode(content));temporary.chmod(0o644);temporary.replace(target)
    compose=['docker','compose','--project-directory',str(PROFILES),'-f',str(PROFILES/'compose.yml')]
    run(compose+['config','--quiet'])
    run(compose+['up','-d','--no-build','--pull','never','--force-recreate','perfiles'])
    run(['docker','exec','birra_perfiles','python','-m','unittest','server.profiles.test_store'])
    result={'backup':str(directory),'app_files_sha256':{name:sha(PROFILES/name) for name in request['files']},'node_red_unchanged':get()==json.loads((directory/'original-runtime.json').read_text()),'isolated_store_tests_passed':True}
    private_json(directory/'profiles-update.json',result)
    return result

def assets():
    name='app/server/profiles/index.html'
    if set(request['files'])!={name}: raise RuntimeError('Esta acción solo actualiza HTML')
    expected=request['expected_files_sha256']
    for filename,digest in expected.items():
        if sha(PROFILES/filename)!=digest: raise RuntimeError('Código remoto modificado: revisar antes de continuar')
    directory=Path.home()/'.local/state/fermentador/backups'/('perfiles-assets-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    shutil.copy2(PROFILES/name,directory/'index.html')
    source=sqlite3.connect('file:'+str(PROFILES/'data/profiles.sqlite')+'?mode=ro',uri=True)
    destination=sqlite3.connect(directory/'profiles.sqlite');source.backup(destination)
    if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('Copia SQLite inválida')
    source.close();destination.close();(directory/'profiles.sqlite').chmod(0o600)
    before=sha(DATA/'flows.json')
    target=PROFILES/name;temporary=target.with_suffix('.new')
    temporary.write_bytes(base64.b64decode(request['files'][name]));temporary.chmod(0o644);temporary.replace(target)
    hashes=dict(expected);hashes[name]=sha(target)
    result={'backup':str(directory),'sqlite_backup_sha256':sha(directory/'profiles.sqlite'),
            'app_files_sha256':hashes,'node_red_unchanged':sha(DATA/'flows.json')==before,'service_restarted':False}
    private_json(directory/'manifest.json',result)
    return result

def snapshot():
    root=Path.home()/'.local/state/fermentador/backups'
    root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
    directory=root/('perfiles-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));directory.mkdir(mode=0o700)
    shutil.copytree(PROFILES/'app',directory/'app')
    for name in ('compose.yml','.env'): shutil.copy2(PROFILES/name,directory/name)
    (directory/'data').mkdir(mode=0o700)
    source=sqlite3.connect('file:'+str(PROFILES/'data/profiles.sqlite')+'?mode=ro',uri=True)
    destination=sqlite3.connect(directory/'data/profiles.sqlite');source.backup(destination)
    integrity=destination.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity!='ok': raise RuntimeError('Copia SQLite inválida')
    source.close();destination.close();(directory/'data/profiles.sqlite').chmod(0o600)
    private_json(directory/'nodered-runtime.json',get())
    manifest={'backup':str(directory),'sqlite_sha256':sha(directory/'data/profiles.sqlite'),'integrity':integrity,
              'files_sha256':{str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file()},
              'service_paused':False,'nodered_paused':False}
    private_json(directory/'manifest.json',manifest)
    return manifest

action = request['action']
if action == 'inspect': result=inspect()
elif action == 'backup': result = backup()
elif action == 'install': result=install()
elif action == 'verify': result=verify()
elif action == 'update': result=update()
elif action == 'assets': result=assets()
elif action == 'snapshot': result=snapshot()
elif action == 'deploy': result = deploy()
elif action == 'rollback': result = rollback()
else: raise RuntimeError('Acción desconocida')
print(json.dumps(result,ensure_ascii=False))
