"""Genera un dashboard clásico para Grafana 10.4 sin datos ni credenciales."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DS = {"type": "influxdb", "uid": "${DS_INFLUXDB}"}
FRESH_NS = 900_000_000_000

def source(measurement='fermentador', fresh=True):
    return ('from(bucket: "telemetria_birra")\n'
            '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r._measurement == "{measurement}")\n'
            + (f'  |> filter(fn: (r) => int(v: v.timeRangeStop) - int(v: r._time) <= {FRESH_NS})\n' if fresh else ''))

def snapshot(fields):
    # message_seq aporta el timestamp del último sobre aun si MOSTO no es válido.
    fields = sorted(set(fields) | {'message_seq'})
    return (source() + '  |> filter(fn: (r) => ' + ' or '.join(f'r._field == "{f}"' for f in fields) + ')\n'
            '  |> map(fn: (r) => ({r with _value: string(v: r._value)}))\n'
            '  |> group(columns: ["_measurement"])\n'
            '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
            '  |> group()\n  |> sort(columns: ["_time"], desc: true)\n  |> limit(n: 1)\n')

APPLIED='float(v: if exists r.setpoint_applied then r.setpoint_applied else r.setpoint)'
VALID_MOSTO='exists r.mosto and float(v: r.mosto) >= -5.0 and float(v: r.mosto) <= 40.0 and (if exists r.mosto_valid then r.mosto_valid == "true" else true)'
queries={
'mosto':snapshot(['mosto','mosto_valid'])+f'  |> filter(fn: (r) => {VALID_MOSTO})\n  |> map(fn: (r) => ({{_time: r._time, _field: "MOSTO", _value: float(v: r.mosto)}}))\n',
'aplicada':snapshot(['setpoint_applied','setpoint'])+f'  |> filter(fn: (r) => exists r.setpoint_applied or exists r.setpoint)\n  |> map(fn: (r) => ({{_time: r._time, _field: "Aplicada", _value: {APPLIED}}}))\n',
'desvio':snapshot(['mosto','mosto_valid','setpoint_applied','setpoint'])+f'  |> filter(fn: (r) => {VALID_MOSTO} and (exists r.setpoint_applied or exists r.setpoint))\n  |> map(fn: (r) => ({{_time: r._time, _field: "Desvío", _value: float(v: r.mosto) - {APPLIED}}}))\n',
'estado':snapshot(['controller_state'])+'  |> filter(fn: (r) => exists r.controller_state)\n  |> map(fn: (r) => ({_time: r._time, _field: "Controlador", _value: r.controller_state}))\n',
'antiguedad':source(fresh=False)+'  |> filter(fn: (r) => r._field == "message_seq")\n  |> group()\n  |> last()\n  |> map(fn: (r) => ({_time: r._time, _field: "Antigüedad", _value: float(v: int(v: v.timeRangeStop) - int(v: r._time)) / 1000000000.0}))\n',
'curva_temperaturas':source(fresh=False)+'''  |> filter(fn: (r) => r._field == "mosto" or r._field == "ambiente")
  |> filter(fn: (r) => (r._field == "mosto" and r._value >= -5.0 and r._value <= 40.0) or (r._field == "ambiente" and r._value >= -20.0 and r._value <= 60.0))
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: true)
  |> map(fn: (r) => ({r with _field: if r._field == "mosto" then "MOSTO" else "AMBIENTE"}))
''',
'curva_aplicada':source(fresh=False)+'''  |> filter(fn: (r) => r._field == "setpoint_applied" or r._field == "setpoint")
  |> group(columns: ["_measurement", "_start", "_stop"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
'''+f'  |> map(fn: (r) => ({{_start: r._start, _stop: r._stop, _time: r._time, _field: "Consigna aplicada", _value: {APPLIED}}}))\n'+'''  |> group(columns: ["_field"])
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: true, timeSrc: "_start")
''',
'perfil':source('estado_orquestador')+'''  |> filter(fn: (r) => r._field == "setpoint" or r._field == "transcurridos" or r._field == "restantes" or r._field == "total")
  |> group(columns: ["_field"])
  |> last()
  |> map(fn: (r) => ({r with _field: if r._field == "setpoint" then "Consigna calculada" else if r._field == "transcurridos" then "Días transcurridos" else if r._field == "restantes" then "Días restantes" else "Días del perfil"}))
''',
'diagnostico':source()+'''  |> filter(fn: (r) => r._field == "uptime_s" or r._field == "message_seq" or r._field == "control_cycles" or r._field == "control_max_gap_ms" or r._field == "hysteresis" or r._field == "lockout_remaining_s")
  |> group(columns: ["_field"])
  |> last()
  |> map(fn: (r) => ({
      Indicador: if r._field == "uptime_s" then "Tiempo encendido (s)" else if r._field == "message_seq" then "Secuencia MQTT" else if r._field == "control_cycles" then "Ciclos de control" else if r._field == "control_max_gap_ms" then "Intervalo máximo del control (ms)" else if r._field == "hysteresis" then "Histéresis (°C)" else "Protección restante (s)",
      Valor: float(v: r._value)
  }))
  |> group()
  |> sort(columns: ["Indicador"])
'''
}
# Normalizar _value a texto antes de agrupar evita colisiones bool/float.
queries['sensores']=source()+'''  |> filter(fn: (r) => r._field == "mosto_valid" or r._field == "ambiente_valid" or r._field == "wifi" or r._field == "mqtt" or r._field == "relay")
  |> map(fn: (r) => ({r with _value: string(v: r._value)}))
  |> group(columns: ["_field"])
  |> last()
  |> map(fn: (r) => ({r with
      Señal: if r._field == "mosto_valid" then "Sonda MOSTO" else if r._field == "ambiente_valid" then "Sonda AMBIENTE" else if r._field == "wifi" then "Wi-Fi (último informe)" else if r._field == "mqtt" then "MQTT (último informe)" else "Salida del relé",
      Estado: if r._field == "relay" then (if r._value == "true" then "Encendida" else "Apagada") else if r._field == "mosto_valid" or r._field == "ambiente_valid" then (if r._value == "true" then "Válida" else "Inválida") else (if r._value == "true" then "Conectado" else "Desconectado")
  }))
  |> group()
  |> sort(columns: ["Señal"])
'''
# Las consignas se muestran como escalones reales, sin promediar cambios.
queries['curva_aplicada']=queries['curva_aplicada'].replace('fn: mean, createEmpty: true, timeSrc: "_start"','fn: last, createEmpty: false')

def panel(pid,title,typ,x,y,w,h,query_names=(),unit='none',description=''):
    return {'id':pid,'title':title,'type':typ,'gridPos':{'x':x,'y':y,'w':w,'h':h},'datasource':DS,
            'description':description,'targets':[{'refId':chr(65+i),'datasource':DS,'query':queries[n]} for i,n in enumerate(query_names)],
            'fieldConfig':{'defaults':{'unit':unit,'noValue':'Sin dato vigente','decimals':2,'color':{'mode':'fixed','fixedColor':'blue'},'mappings':[]},'overrides':[]},
            'options':{}}

def stat(pid,title,x,w,q,unit='none',desc=''):
    p=panel(pid,title,'stat',x,2,w,4,[q],unit,desc)
    p['options']={'colorMode':'value','graphMode':'none','textMode':'value','orientation':'auto','reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False},'justifyMode':'center'}
    return p

banner=panel(4,'Ensayo de banco','text',0,0,24,2)
banner.pop('datasource');banner.pop('targets');banner['options']={'mode':'markdown','content':'**Ensayo de banco sin compresor; FASE D pendiente.** Perfil y progreso de prueba. Las consignas remotas están bloqueadas.'}
panels=[banner,
 stat(5,'Temperatura del MOSTO',0,4,'mosto','celsius','Última lectura del sobre más reciente, solo si la sonda es válida y tiene como máximo 900 s de antigüedad al cierre del intervalo.'),
 stat(6,'Consigna aplicada por ESP32',4,4,'aplicada','celsius','setpoint_applied; para datos antiguos se usa setpoint del mismo sobre. No usa la consigna calculada del servidor.'),
 stat(2,'MOSTO − consigna aplicada',8,4,'desvio','celsius','Desvío firmado con ambos valores del mismo timestamp. No mide por sí solo la calidad del control ni la refrigeración.'),
 stat(7,'Estado del controlador',12,6,'estado',desc='Último estado informado, vigente hasta 900 s. COOLING expresa una orden de enfriamiento; el compresor no está conectado.'),
 stat(8,'Edad de la última telemetría',18,6,'antiguedad','s','Segundos entre la última muestra y el final del intervalo seleccionado. En una vista histórica se evalúa al cierre de ese intervalo. Más de 900 s indica telemetría atrasada; sin muestras muestra Sin dato vigente.')]
panels[-1]['fieldConfig']['defaults'].update(decimals=0,color={'mode':'thresholds'},thresholds={'mode':'absolute','steps':[{'color':'green','value':None},{'color':'red','value':900}]})
panels[-2]['options']['reduceOptions']['fields']='/^_value$/'
panels[-2]['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{k:{'text':v} for k,v in {'COOLING':'Enfriamiento solicitado','IDLE':'En espera','BOOT_HOLD':'Protección de arranque','COMPRESSOR_LOCKOUT':'Protección del compresor','SENSOR_FAULT':'Falla de sonda','MAINTENANCE':'Mantenimiento'}.items()}}]
curve=panel(1,'Temperaturas y consigna aplicada','timeseries',0,6,16,10,['curva_temperaturas','curva_aplicada'],'celsius','MOSTO y AMBIENTE: promedio por ventana del intervalo seleccionado; valores fuera del rango físico se omiten. Consigna: último valor por ventana. Los huecos de temperatura no se rellenan. Datos de banco.')
curve['interval']='10s' # Cadencia de telemetría: evitar ventanas vacías artificiales.
curve['options']={'tooltip':{'mode':'multi','sort':'none'},'legend':{'displayMode':'list','placement':'bottom','calcs':['lastNotNull']}}
curve['fieldConfig']['defaults']['displayName']='${__field.labels._field}'
curve['fieldConfig']['defaults']['custom']={'drawStyle':'line','lineWidth':2,'fillOpacity':5,'spanNulls':False,'showPoints':'never','axisLabel':'°C'}
for name,color in [('MOSTO','orange'),('AMBIENTE','blue'),('Consigna aplicada','green')]:
 props=[{'id':'color','value':{'mode':'fixed','fixedColor':color}}]
 if name=='Consigna aplicada':props += [{'id':'custom.lineInterpolation','value':'stepAfter'},{'id':'custom.lineStyle','value':{'fill':'dash','dash':[8,4]}},{'id':'custom.fillOpacity','value':0}]
 curve['fieldConfig']['overrides'].append({'matcher':{'id':'byName','options':name},'properties':props})
panels.append(curve)
sensors=panel(9,'Sensores, conexión y salida','table',16,6,8,10,['sensores'],description='Últimos flags recibidos dentro de 900 s del cierre del intervalo. Wi-Fi/MQTT describen el último informe; durante una desconexión, la vigencia se determina por la edad de telemetría. El relé no demuestra funcionamiento del compresor.')
sensors['options']={'showHeader':True,'cellHeight':'md','footer':{'show':False}}
# Ocultar metadatos en Grafana, después de la consulta: conservar r evita que
# el optimizador de Flux elimine _value antes de last() en streams booleanos.
sensors['transformations']=[{'id':'organize','options':{'excludeByName':{k:True for k in ['_field','_measurement','_start','_stop','_time','_value']},'indexByName':{'Señal':0,'Estado':1},'renameByName':{}}}]
panels.append(sensors)
profile=panel(3,'Perfil de prueba · sin publicación','stat',0,16,8,7,['perfil'],description='Estado calculado por Node-RED, no desde la primera medición ni desde densidad. No demuestra avance biológico de fermentación. Solo muestra cálculos recientes (900 s).')
profile['options']={'colorMode':'value','graphMode':'none','textMode':'value_and_name','orientation':'auto','reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False}}
profile['fieldConfig']['defaults'].update(unit='suffix: días',displayName='${__field.labels._field}')
profile['fieldConfig']['overrides']=[{'matcher':{'id':'byRegexp','options':'.*Consigna calculada.*'},'properties':[{'id':'unit','value':'celsius'}]}]
panels.append(profile)
diag=panel(10,'Diagnóstico del control local','table',8,16,16,7,['diagnostico'],description='Último informe vigente del ESP32. El intervalo máximo es el máximo acumulado reportado por el dispositivo, no el promedio de las muestras del gráfico.')
diag['options']={'showHeader':True,'cellHeight':'sm','footer':{'show':False}}
diag['transformations']=[{'id':'organize','options':{'indexByName':{'Indicador':0,'Valor':1},'excludeByName':{},'renameByName':{}}}]
panels.append(diag)
dashboard={'id':None,'uid':'fermentador-inteligente','title':'Telemetria de Fermentacion','description':'Supervisión del controlador autónomo ESP32. Ensayo de banco sin compresor; FASE D pendiente. Sin acciones de control desde Grafana.',
 'schemaVersion':39,'version':1,'editable':True,'timezone':'browser','refresh':'10s','time':{'from':'now-6h','to':'now'},'timepicker':{'refresh_intervals':['10s','30s','1m','5m']},'tags':['fermentacion','banco','esp32'],'templating':{'list':[]},'annotations':{'list':[]},'links':[],'panels':panels,
 '__inputs':[{'name':'DS_INFLUXDB','label':'InfluxDB Flux','type':'datasource','pluginId':'influxdb','pluginName':'InfluxDB'}]}

def build():
    (ROOT/'queries').mkdir(exist_ok=True)
    for name,query in queries.items():(ROOT/'queries'/(name+'.flux')).write_text(query)
    (ROOT/'dashboard.json').write_text(json.dumps(dashboard,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':build()
