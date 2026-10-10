import hashlib,json,os,pathlib,sqlite3,subprocess,tarfile,time
from datetime import datetime,timezone

def run(args): return subprocess.run(args,check=True,capture_output=True,timeout=120)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def save(p,data):p.write_text(json.dumps(data,indent=2)+'\n');p.chmod(0o600)
root=pathlib.Path.home()/'.local/state/fermentador/backups';root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
d=root/('grafana-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));d.mkdir(mode=0o700)
c=json.loads(run(['docker','inspect','birra_grafana']).stdout)[0]
save(d/'container-inspect.private.json',c)
compose=pathlib.Path('/opt/telemetria_birra/docker-compose.yml')
(d/'docker-compose.yml').write_bytes(compose.read_bytes());(d/'docker-compose.yml').chmod(0o600)
run(['docker','cp','birra_grafana:/etc/grafana',str(d/'etc-grafana')])
paused=False;started=time.monotonic()
try:
 run(['docker','pause','birra_grafana']);paused=True
 run(['docker','cp','birra_grafana:/var/lib/grafana',str(d/'data')])
finally:
 if paused:run(['docker','unpause','birra_grafana'])
pause=round(time.monotonic()-started,2)
db=sqlite3.connect('file:'+str(d/'data/grafana.db')+'?mode=ro',uri=True)
check=db.execute('PRAGMA integrity_check').fetchone()[0]
if check!='ok':raise RuntimeError('Falló integridad SQLite del respaldo')
rows=db.execute('SELECT uid,title,data FROM dashboard').fetchall()
save(d/'dashboards.private.json',[{'uid':x[0],'title':x[1],'data':json.loads(x[2])} for x in rows]);db.close()
archive=d/'grafana.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as t:
 for p in [d/'data',d/'etc-grafana',d/'docker-compose.yml',d/'container-inspect.private.json',d/'dashboards.private.json']:t.add(p,arcname=p.name)
archive.chmod(0o600)
with tarfile.open(archive,'r:gz') as t:
 extracted=t.extractfile('data/grafana.db')
 if hashlib.sha256(extracted.read()).hexdigest()!=sha(d/'data/grafana.db'):raise RuntimeError('Fallo hash SQLite archivado')
 with t.extractfile('etc-grafana/provisioning/dashboards/auto/dashboard.json') as f:original=json.load(f)
manifest={'backup':str(d),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'sqlite_integrity':check,'pause_seconds':pause,'compose_sha256':sha(compose),'provisioned_dashboard_sha256':sha(d/'etc-grafana/provisioning/dashboards/auto/dashboard.json'),'grafana_image':c['Config']['Image'],'original_container_id':c['Id'],'dashboards':len(rows),'created_at_utc':datetime.now(timezone.utc).isoformat()}
save(d/'manifest.json',manifest)
print(json.dumps(manifest))
