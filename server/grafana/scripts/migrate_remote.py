import copy,hashlib,json,pathlib,re,shutil,sqlite3,subprocess,sys,time,urllib.request
from datetime import datetime,timezone
req=json.load(sys.stdin)
backup=pathlib.Path(req['backup']);manifest=json.loads((backup/'manifest.json').read_text())
compose=pathlib.Path('/opt/telemetria_birra/docker-compose.yml')
root=pathlib.Path('/opt/telemetria_birra/grafana')
uid=req['uid']

def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=120)
 if r.returncode:raise RuntimeError('Falló comando '+args[0]+' '+args[1]+'; salida reservada en el servidor')
 return r.stdout

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def private(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
def config(path):return json.loads(run(['docker','compose','-f',str(path),'config','--format','json']))
def db_read():
 db=sqlite3.connect('file:'+str(root/'data/grafana.db')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 ds=[dict(r) for r in db.execute('SELECT * FROM data_source')]
 dash=db.execute('SELECT data FROM dashboard WHERE uid=?',(uid,)).fetchone()
 prov=[dict(r) for r in db.execute('SELECT * FROM dashboard_provisioning')]
 db.close();return ds,json.loads(dash['data']) if dash else None,prov

if sha(compose)!=manifest['compose_sha256']:raise RuntimeError('Compose cambió desde el respaldo')
if sha(backup/'grafana.tar.gz')!=manifest['archive_sha256']:raise RuntimeError('Respaldo alterado')
original=json.loads((backup/'dashboards.private.json').read_text())
old=next(d['data'] for d in original if d['uid']==uid)
ds_before,current,_=db_read()
if current!=old:raise RuntimeError('Dashboard editado después del respaldo; no se sobrescribe')
original_config=config(compose)
service=original_config['services']['grafana']
if service['image']!=manifest['grafana_image']:raise RuntimeError('La imagen cambió')
if any(v['target']=='/etc/grafana/provisioning' for v in service.get('volumes',[])):raise RuntimeError('Ya existe mount de provisioning; revisar antes de aplicar')
provision=root.parent/'grafana-provisioning'
if provision.exists():raise RuntimeError('La carpeta persistente ya existe; no se sobrescribe')
containers=json.loads(run(['docker','inspect','birra_nodered','birra_broker','birra_influxdb']))
other_before={c['Name']:c['Id'] for c in containers}
nodeflow=pathlib.Path('/opt/telemetria_birra/nodered/flows.json');flow_hash=sha(nodeflow)
# Leer datos originales privados; no se exportan conexiones ni credenciales.
selected=next(d for d in ds_before if d['type']=='influxdb' and d['is_default'])
candidate=copy.deepcopy(req['dashboard'])
def resolve(x):
 if isinstance(x,dict):return {k:resolve(v) for k,v in x.items()}
 if isinstance(x,list):return [resolve(v) for v in x]
 return selected['uid'] if x=='${DS_INFLUXDB}' else x
candidate=resolve(candidate);candidate.pop('__inputs',None);candidate['uid']=uid;candidate['title']=old['title'];candidate['version']=old.get('version',0)+1
if candidate.get('schemaVersion')!=39 or not candidate.get('title'):raise RuntimeError('Formato incompatible')
# Preparar YAML junto al original para conservar resolución de rutas y proyecto.
text=compose.read_text();lines=text.splitlines(keepends=True)
start=next(i for i,line in enumerate(lines) if re.fullmatch(r'  grafana:\s*\n?',line))
end=next((i for i in range(start+1,len(lines)) if re.match(r'  [A-Za-z0-9_-]+:\s*$',lines[i].rstrip())),len(lines))
vol=next(i for i in range(start+1,end) if re.fullmatch(r'    volumes:\s*\n?',lines[i]))
lines.insert(vol+1,'      - ./grafana-provisioning:/etc/grafana/provisioning:ro\n')
staged=compose.with_name('.docker-compose.grafana-candidate.yml');staged.write_text(''.join(lines));staged.chmod(0o600)
new_config=config(staged)
a=copy.deepcopy(original_config);b=copy.deepcopy(new_config)
before_vol=a['services']['grafana'].pop('volumes');after_vol=b['services']['grafana'].pop('volumes')
added=[v for v in after_vol if v['target']=='/etc/grafana/provisioning']
if a!=b or [v for v in after_vol if v['target']!='/etc/grafana/provisioning']!=before_vol or len(added)!=1 or added[0]['source']!=str(provision) or not added[0].get('read_only'):
 staged.unlink();raise RuntimeError('El diff de Compose excede el nuevo volumen')
shutil.copytree(backup/'etc-grafana/provisioning',provision)
for p in [provision]+list(provision.rglob('*')):p.chmod(0o755 if p.is_dir() else 0o644)
file=provision/'dashboards/auto/dashboard.json'
file.write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n');file.chmod(0o644)
private(backup/'candidate-dashboard.json',candidate)
private(backup/'compose-before.private.json',original_config)
private(backup/'compose-after.private.json',new_config)
# Revalidar justo antes de sustituir Compose y recrear únicamente Grafana.
if sha(compose)!=manifest['compose_sha256']:raise RuntimeError('Cambio concurrente de Compose')
mode=compose.stat().st_mode & 0o777
staged.chmod(mode);staged.replace(compose)
started=datetime.now(timezone.utc).isoformat()
result=run(['docker','compose','-f',str(compose),'up','-d','--no-deps','--no-build','--pull','never','grafana'])
(backup/'compose-up.private.txt').write_text(result);(backup/'compose-up.private.txt').chmod(0o600)
ready=False
for _ in range(25):
 try:
  with urllib.request.urlopen('http://127.0.0.1:3000/api/health',timeout=2) as response:
   health=json.load(response);ready=health.get('database')=='ok'
  if ready:break
 except Exception:pass
 time.sleep(1)
if not ready:raise RuntimeError('Grafana no respondió health; respaldo disponible, revisar antes de revertir')
for _ in range(15):
 ds_after,observed,prov=db_read()
 if observed and len(observed.get('panels',[]))==len(candidate['panels']) and any(p.get('name')=='OMBU-Telemetria' for p in prov):break
 time.sleep(1)
else:raise RuntimeError('Aprovisionamiento no confirmado; no se fuerza restauración de base')
if ds_after!=ds_before:raise RuntimeError('Cambió un datasource; revisar respaldo')
for key in ['title','uid','panels','time','refresh','tags']:
 if observed.get(key)!=candidate.get(key):raise RuntimeError('El dashboard activo difiere en '+key)
containers=json.loads(run(['docker','inspect','birra_grafana','birra_nodered','birra_broker','birra_influxdb']))
other_after={c['Name']:c['Id'] for c in containers if c['Name']!='/birra_grafana'}
if other_before!=other_after or sha(nodeflow)!=flow_hash:raise RuntimeError('Cambio inesperado en otros servicios')
grafana=next(c for c in containers if c['Name']=='/birra_grafana')
report={'backup':str(backup),'started_at_utc':started,'dashboard_uid':uid,'dashboard_title':observed['title'],'panels':len(observed['panels']),'health':health,'datasources_unchanged':True,'other_container_ids_unchanged':True,'nodered_flows_unchanged':True,'persistent_provisioning':any(m['Destination']=='/etc/grafana/provisioning' and not m['RW'] for m in grafana['Mounts']),'provisioned':True,'dashboard_file_sha256':sha(file),'compose_sha256':sha(compose),'services':[{'name':c['Name'],'status':c['State']['Status'],'paused':c['State']['Paused'],'restarts':c['RestartCount']} for c in containers]}
private(backup/'deployment.json',report)
print(json.dumps(report,ensure_ascii=False))
