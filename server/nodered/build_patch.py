"""Genera un parche revisable y una vista deshabilitada; no conecta a servicios."""
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAB = '6a09c3f845bb0be5'
PIPE = 'dda619d5884cecdf'
ALERT = '4b2ac603bb7bd26b'
PROFILE = '93751e838cbcf62b'
DIAG = 'nr10_diagnostico'

def build(source, base_sha256):
    nodes = {n['id']: n for n in source}
    updates = {}
    additions = []
    def change(node_id, **values):
        if node_id not in nodes:
            raise ValueError('La base no tiene el nodo esperado: ' + node_id)
        updates.setdefault(node_id, {}).update(values)
    def body(filename):
        return (ROOT / 'functions' / filename).read_text()
    def function(node_id, name, filename, x, y, group, wires):
        additions.append(dict(id=node_id, type='function', z=TAB, g=group, name=name,
                              func=body(filename), outputs=1, noerr=0, initialize='', finalize='', libs=[], timeout=0,
                              x=x, y=y, wires=wires))
    def debug(node_id, name, group, x, y, complete='payload'):
        additions.append(dict(id=node_id, type='debug', z=TAB, g=group, name=name, active=True,
                              tosidebar=True, console=False, tostatus=False, complete=complete,
                              targetType='msg', statusVal='', statusType='auto', x=x, y=y, wires=[]))
    change(TAB, label='Fermentador · telemetría y supervisión')
    change(PIPE, name='01 · Telemetría validada y persistencia', x=44, y=39, w=1322, h=242,
           nodes=nodes[PIPE]['nodes'] + ['nr10_validar', 'nr10_sp_aplicado'])
    change(ALERT, name='02 · Alertas térmicas existentes', x=44, y=339, w=1322, h=282)
    change(PROFILE, name='03 · Perfil de prueba · publicación bloqueada', x=44, y=679, w=1322, h=282)
    change('05ef2ed6ad6fdc38', x=200, y=100, wires=[['nr10_validar']])
    function('nr10_validar', 'VALIDAR: contrato y calidad', 'validar-telemetria.js', 530, 100, PIPE,
             [['5915461a27741a55', 'fbf131f18cb09f3d', '5a0582668ed9c9ae', 'nr10_sp_aplicado']])
    change('5915461a27741a55', name='DEBUG: telemetría validada', active=False, x=580, y=220)
    change('fbf131f18cb09f3d', name='FORMAT: campos válidos para InfluxDB', func=body('preparar-influx.js'), x=880, y=100)
    change('44c07f25b44c64fe', x=1180, y=100)
    actual = copy.deepcopy(nodes['1c1a749e7a746326'])
    actual.update(id='nr10_sp_aplicado', g=PIPE, name='UI: consigna aplicada por ESP32',
                  label='Consigna aplicada ESP32 (°C)', value='payload.setpoint_applied', order=3, x=1160, y=220)
    additions.append(actual)
    change('5a0582668ed9c9ae', func=body('alarma-termica.js'), name='CHECK: desvío de consigna aplicada', x=250, y=400)
    change('48f695cfed13afd8', x=610, y=400)
    change('45246b272efb8409', x=940, y=400)
    # Telegram stays blocked during validation. No unsolicited test messages.
    change('416924024672d3bd', d=True, name='OUT: Telegram · bloqueado para pruebas', x=1180, y=480)
    change('2851528834bc5f7c', d=True, name='LEGACY: timeout por mensaje · deshabilitado', x=300, y=540)
    change('b1999152cc022d09', x=660, y=540)
    change('23a7bec7054cc411', x=1030, y=540)
    change('48dcb958f555ae77', name='CALC: perfil interpolado · sin PID', func=body('calcular-perfil.js'), x=830, y=780)
    change('183d81f953a891ba', name='TICK: cálculo de perfil de prueba', once=True, onceDelay=1, x=520, y=720)
    change('ea2429329788f701', d=True, name='OUT: consigna MQTT · bloqueada', x=1180, y=740)
    change('cd4ca9e64daadf17', name='STATE: iniciar lote una sola vez', func=body('iniciar-lote.js'), x=540, y=840)
    change('91228d4897e037d4', d=True, name='INJECT: iniciar lote · bloqueado', x=240, y=720)
    guard = '''// No reemplazar receta ni fecha de un lote ya iniciado.
const inicioExistente = flow.get("inicio_fermentacion", "file");
if (inicioExistente !== undefined && inicioExistente !== null) {
    node.error("Ya existe un lote iniciado; no se reemplaza la receta", {topic: "lote"});
    return null;
}
'''
    change('b6844984558a8c68', name='CONF: receta de prueba · no es receta real',
           func=guard + nodes['b6844984558a8c68']['func'], x=240, y=840)
    change('a54f710e658163de', name='DEBUG: inicio de lote', x=800, y=900)
    change('1c1a749e7a746326', label='Consigna calculada del perfil (°C)', name='UI: consigna calculada', x=1180, y=820)
    change('fd03135617c9bfa8', x=1180, y=900)
    diag_nodes = ['nr10_tick', 'nr10_vigencia', 'nr10_eventos', 'nr10_catch', 'nr10_errores', 'nr10_status', 'nr10_estados']
    additions.append(dict(id=DIAG, type='group', z=TAB, name='04 · Diagnóstico local · sin avisos externos',
                          style={'fill': '#e2e3ef', 'label': True, 'color': '#000000'}, nodes=diag_nodes,
                          x=44, y=1019, w=1322, h=322))
    additions.append(dict(id='nr10_tick', type='inject', z=TAB, g=DIAG, name='TICK: vigencia cada 30 s',
                          props=[{'p': 'payload'}], repeat='30', crontab='', once=True, onceDelay=0.5,
                          topic='', payload='', payloadType='date', x=240, y=1080, wires=[['nr10_vigencia']]))
    function('nr10_vigencia', 'CHECK: vigencia desde el arranque', 'comprobar-vigencia.js', 670, 1080, DIAG, [['nr10_eventos']])
    additions[-1]['initialize'] = 'context.set("startedAt", Date.now()); context.set("offline", false);'
    debug('nr10_eventos', 'DEBUG: pérdida y recuperación', DIAG, 1120, 1080)
    scoped = [n['id'] for n in source if n.get('z') == TAB and n['type'] not in ('group', 'debug')]
    scoped += ['nr10_validar', 'nr10_vigencia']
    additions.append(dict(id='nr10_catch', type='catch', z=TAB, g=DIAG, name='CATCH: errores del fermentador',
                          scope=scoped, uncaught=False, x=270, y=1180, wires=[['nr10_errores']]))
    debug('nr10_errores', 'DEBUG: errores de nodos', DIAG, 1110, 1180, 'error')
    additions.append(dict(id='nr10_status', type='status', z=TAB, g=DIAG, name='STATUS: MQTT e InfluxDB',
                          scope=['05ef2ed6ad6fdc38', '44c07f25b44c64fe', 'ea2429329788f701', 'fd03135617c9bfa8'],
                          x=270, y=1280, wires=[['nr10_estados']]))
    debug('nr10_estados', 'DEBUG: estado de conexiones', DIAG, 1110, 1280, 'status')
    return {'base_disk_sha256': base_sha256, 'scope': 'Node-RED Birra; Clima y configuraciones compartidas intactos',
            'updates': updates, 'additions': additions}

def apply(source, patch):
    existing = {n['id'] for n in source}
    if any(n['id'] in existing for n in patch['additions']):
        raise ValueError('El parche ya fue aplicado o hay conflicto de IDs')
    if not set(patch['updates']).issubset(existing):
        raise ValueError('Faltan nodos de la base')
    result = copy.deepcopy(source)
    for n in result:
        n.update(patch['updates'].get(n['id'], {}))
    return result + copy.deepcopy(patch['additions'])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    inventory = json.loads(args.inventory.read_text())
    patch = build(source, inventory['disk_sha256'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'patch.json').write_text(json.dumps(patch, ensure_ascii=False, indent=2) + '\n')
    review = apply(source, patch)
    # This is for editor review only. It is never the deployment input.
    for n in review:
        if n['type'] == 'tab': n['disabled'] = True
        if n['type'] in ('mqtt out', 'influxdb out', 'telegram sender'): n['d'] = True
        if n['type'] == 'mqtt-broker':
            n['autoConnect'] = False
            for k in ('birthTopic', 'willTopic', 'closeTopic'): n[k] = ''
    (args.output / 'flows.review.disabled.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'modified_nodes': len(patch['updates']), 'new_nodes': len(patch['additions']), 'remote_changes': False}))

if __name__ == '__main__':
    main()
