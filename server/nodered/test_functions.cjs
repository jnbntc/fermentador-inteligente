// Ejecuta los cuerpos exactos de Function Nodes en contextos aislados.
const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const bundle = globalThis.__bundle || {
    functions: Object.fromEntries(fs.readdirSync(path.join(__dirname, 'functions')).map(name => [name, fs.readFileSync(path.join(__dirname, 'functions', name), 'utf8')])),
    baseline: JSON.parse(fs.readFileSync(process.argv[2], 'utf8')),
    patch: JSON.parse(fs.readFileSync(process.argv[3], 'utf8')),
    review: JSON.parse(fs.readFileSync(process.argv[4], 'utf8'))
};
let passed = 0;
function test(name, fn) { fn(); passed++; console.log('OK ' + name); }
const clone = value => JSON.parse(JSON.stringify(value));
function store() {
    const maps = {default: new Map(), file: new Map()};
    return {get: (key, name = 'default') => maps[name].get(key), set: (key, value, name = 'default') => {
        if (value === undefined) maps[name].delete(key); else maps[name].set(key, value);
    }};
}
const NOW = Date.UTC(2026, 9, 10, 12);
function harness() {
    const h = {flow: store(), context: store(), now: NOW, errors: [], variables: {}};
    h.runCode = (code, payload, extra = {}) => {
        class Clock extends Date { static now() { return h.now; } }
        const sandbox = {msg: Object.assign({payload}, extra), flow: h.flow, context: h.context,
            node: {error: text => h.errors.push(text), status: () => {}, warn: text => h.errors.push(text)},
            env: {get: key => h.variables[key]}, Date: Clock, Buffer};
        return new vm.Script('(function () {\n' + code + '\n})()').runInNewContext(sandbox, {timeout: 200});
    };
    h.run = (name, payload, extra) => h.runCode(bundle.functions[name], payload, extra);
    return h;
}
const telemetry = () => ({mosto: 21, ambiente: 24, mosto_valid: true, ambiente_valid: true,
    setpoint_applied: 18, setpoint_desired: 18, setpoint: 18, hysteresis: 0.3,
    relay: true, rele: 1, wifi: true, mqtt: true, dry_run: false, degraded: false,
    cooling_request: true, cooling_active: true, controller_state: 'COOLING',
    fault: null, message_seq: 20, control_cycles: 20000, uptime_s: 400});
function recipe(h, points = [{dia: 0, temp: 18}, {dia: 10, temp: 21}]) {
    h.flow.set('receta_activa', points, 'file');
    h.flow.set('inicio_fermentacion', NOW - 5 * 86400000, 'file');
}
test('reproduce fallo original de progreso al cambiar consigna; corregido antes del retorno', () => {
    const old = harness(); recipe(old);
    const body = bundle.baseline.find(n => n.id === '48dcb958f555ae77').func;
    old.runCode(body, 0);
    assert.equal(old.flow.get('dias_transcurridos', 'file'), undefined);
    const h = harness(); recipe(h);
    const result = h.run('calcular-perfil.js', 0);
    assert.equal(result[0].payload, '19.5');
    assert.equal(h.flow.get('estado_lote', 'file').transcurridos, 5);
    assert.equal(h.flow.get('dias_restantes', 'file'), 5);
    assert.equal(h.flow.get('ultimo_setpoint', 'file'), undefined);
});
test('reproduce lectura equivocada de store original y verifica store file compartido', () => {
    const h = harness();
    h.flow.set('dias_transcurridos', 8.17, 'file');
    h.flow.set('dias_restantes', 1.83, 'file');
    const old = h.runCode(bundle.baseline.find(n => n.id === 'fbf131f18cb09f3d').func, telemetry());
    assert.equal(old.payload.dias_trans, 0);
    h.flow.set('estado_lote', {transcurridos: 8.17, restantes: 1.83}, 'file');
    const normalized = h.run('validar-telemetria.js', telemetry());
    const out = h.run('preparar-influx.js', normalized.payload);
    assert.equal(out.payload.dias_trans, 8.17);
    assert.equal(out.payload.dias_rest, 1.83);
});
test('perfil plano actual y perfil de un punto no necesitan interpolación', () => {
    for (const points of [[{dia:0,temp:3},{dia:10,temp:3}], [{dia:0,temp:18}]]) {
        const h = harness(); recipe(h, points);
        const out = h.run('calcular-perfil.js', 0);
        assert.equal(out[1].payload.setpoint, points[0].temp);
    }
});
test('actualiza progreso también si la consigna calculada no cambió', () => {
    const h = harness(); recipe(h);
    h.flow.set('ultimo_setpoint', 19.5, 'file');
    assert.equal(h.run('calcular-perfil.js', 0)[0], null);
    assert.equal(h.flow.get('estado_lote', 'file').transcurridos, 5);
});
test('rechaza perfiles desordenados, no finitos, fuera de rango o de fecha futura', () => {
    const bad = [[{dia:0,temp:18},{dia:0,temp:20}], [{dia:1,temp:18}], [{dia:0,temp:30}], [{dia:0,temp:NaN}], [{dia:0,temp:0.004}], []];
    for (const points of bad) {
        const h = harness(); recipe(h, points);
        assert.equal(h.run('calcular-perfil.js', 0), null);
        assert(h.errors.length > 0);
    }
    const h = harness(); recipe(h); h.flow.set('inicio_fermentacion', NOW+1, 'file');
    assert.equal(h.run('calcular-perfil.js', 0), null);
});
test('recibe objeto, JSON y Buffer sin cambiar el payload original', () => {
    for (const input of [telemetry(), JSON.stringify(telemetry()), Buffer.from(JSON.stringify(telemetry()))]) {
        const h = harness();
        const out = h.run('validar-telemetria.js', input);
        assert.equal(out.payload.setpoint_applied, 18);
        assert.equal(out.payload.rele, 1);
        assert.equal(h.flow.get('telemetria_recibida_ms'), NOW);
    }
});
test('rechaza entradas mal formadas sin refrescar vigencia', () => {
    const bad = [null, [], 18, '{bad', {...telemetry(), setpoint_applied:null}, {...telemetry(), setpoint_applied:30}, {...telemetry(), relay:'false'}, {...telemetry(), mosto_valid:'true'}];
    for (const input of bad) {
        const h = harness(); assert.equal(h.run('validar-telemetria.js', input), null);
        assert.equal(h.flow.get('telemetria_recibida_ms'), undefined);
        assert(h.errors.length > 0);
    }
});
test('no convierte -127, 85, NaN ni null en temperatura de proceso', () => {
    for (const value of [-127, 85, NaN, null]) {
        const h = harness(); const input = telemetry(); input.mosto = value;
        const normalized = h.run('validar-telemetria.js', input);
        assert.equal(normalized.payload.mosto_valid, false);
        assert.equal(normalized.payload.mosto, null);
        const out = h.run('preparar-influx.js', normalized.payload);
        assert(!Object.hasOwnProperty.call(out.payload, 'mosto'));
        assert.equal(out.payload.mosto_valid, false);
        assert.equal(out.payload.ambiente, 24);
    }
});
test('honra flag de sensor inválido aunque su número parezca válido', () => {
    const h = harness(); const p = telemetry(); p.mosto_valid = false;
    assert.equal(h.run('validar-telemetria.js', p).payload.mosto, null);
    assert.equal(p.mosto, 21);
});
test('conserva evento SENSOR_FAULT y omite nulls de Influx', () => {
    const h = harness(); const p = {...telemetry(), mosto:null, mosto_valid:false, relay:false, rele:0, controller_state:'SENSOR_FAULT', fault:'mosto_sensor'};
    const normalized = h.run('validar-telemetria.js', p);
    const out = h.run('preparar-influx.js', normalized.payload);
    assert.equal(out.payload.fault, 'mosto_sensor');
    assert.equal(out.payload.relay, false);
    assert.equal(out.payload.rele, 0);
    assert(Object.values(out.payload).every(v => v !== null && typeof v !== 'object'));
});
test('distingue consigna deseada rechazada de la aplicada', () => {
    const h = harness(); const p = {...telemetry(), setpoint_desired:30};
    const out = h.run('validar-telemetria.js', p);
    assert.equal(out.payload.setpoint_desired, 30);
    assert.equal(out.payload.setpoint_applied, 18);
    assert.equal(out.payload.setpoint, 18);
});
test('compatibilidad con alias rele/setpoint sin inventar estado de controlador', () => {
    const h = harness();
    const out = h.run('validar-telemetria.js', {mosto:19, ambiente:22, rele:0, setpoint:18});
    assert.equal(out.payload.relay, false);
    assert.equal(out.payload.mosto_valid, true);
    assert.equal(out.payload.controller_state, undefined);
});
test('sin lote calculado no inventa progreso cero', () => {
    const h = harness(); const p = h.run('preparar-influx.js', telemetry()).payload;
    assert(!Object.hasOwnProperty.call(p, 'dias_trans'));
    assert(!Object.hasOwnProperty.call(p, 'dias_rest'));
});
test('mensaje retenido no prueba recepción reciente', () => {
    const h = harness(); assert.equal(h.run('validar-telemetria.js', telemetry(), {retain:true}), null);
    assert.equal(h.flow.get('telemetria_recibida_ms'), undefined);
});
test('vigencia detecta ausencia desde arranque y emite una sola transición', () => {
    const h = harness();
    assert.equal(h.run('comprobar-vigencia.js', 0), null);
    h.now += 899000; assert.equal(h.run('comprobar-vigencia.js', 0), null);
    h.now += 1000; assert.equal(h.run('comprobar-vigencia.js', 0).payload.event, 'TELEMETRIA_AUSENTE');
    h.now += 1000; assert.equal(h.run('comprobar-vigencia.js', 0), null);
    h.run('validar-telemetria.js', '{bad');
    assert.equal(h.run('comprobar-vigencia.js', 0), null);
    h.run('validar-telemetria.js', telemetry());
    assert.equal(h.run('comprobar-vigencia.js', 0).payload.event, 'TELEMETRIA_RECUPERADA');
    assert.equal(h.run('comprobar-vigencia.js', 0), null);
});
test('validación de configuración de vigencia y umbral térmico', () => {
    const h = harness(); h.variables.TELEMETRIA_TIMEOUT_S = 'nan';
    assert.equal(h.run('comprobar-vigencia.js', 0), null); assert(h.errors.length);
    h.variables.THERMAL_ALERT_DELTA_C = 'nan';
    assert.equal(h.run('alarma-termica.js', telemetry()), null); assert(h.errors.length > 1);
});
test('alarma usa consigna aplicada y conserva umbral previo hasta configurarlo', () => {
    const h = harness(); const p = {...telemetry(), mosto:25, setpoint_desired:26};
    assert.equal(h.run('alarma-termica.js', p), null);
    h.variables.THERMAL_ALERT_DELTA_C = '2';
    assert(h.run('alarma-termica.js', p).payload.includes('7.00'));
    p.mosto_valid = false;
    assert.equal(h.run('alarma-termica.js', p), null);
});
test('inicio repetido no reemplaza fecha ni receta', () => {
    const h = harness(); recipe(h);
    const before = h.flow.get('inicio_fermentacion', 'file');
    assert.equal(h.run('iniciar-lote.js', 0), null);
    const guard = bundle.patch.updates.b6844984558a8c68.func;
    assert.equal(h.runCode(guard, 0), null);
    assert.equal(h.flow.get('inicio_fermentacion', 'file'), before);
    assert.equal(h.flow.get('receta_activa', 'file')[0].temp, 18);
    const fresh = harness(); assert(fresh.run('iniciar-lote.js', 0));
    assert.equal(fresh.flow.get('inicio_fermentacion', 'file'), NOW);
});
test('parche conserva Clima, credenciales y configuraciones compartidas', () => {
    const patch = bundle.patch;
    const ids = new Set(bundle.baseline.map(n => n.id));
    for (const n of bundle.baseline) {
        if (n.z === '6f187c8768edf26d' || (!n.z && n.type !== 'tab') || n.id === '6f187c8768edf26d') {
            assert.equal(patch.updates[n.id], undefined);
        }
    }
    for (const n of patch.additions) { assert(!ids.has(n.id)); ids.add(n.id); }
    assert.equal(patch.updates.ea2429329788f701.d, true);
    assert.equal(patch.updates['416924024672d3bd'].d, true);
    assert.equal(patch.updates['91228d4897e037d4'].d, true);
    const actual = bundle.baseline.map(n => Object.assign({},n,patch.updates[n.id] || {})).concat(patch.additions);
    for (const n of actual) {
        for (const output of n.wires || []) for (const id of output) assert(ids.has(id));
        if (n.type === 'group') for (const id of n.nodes) assert(ids.has(id));
        if (n.type === 'function') {
            new vm.Script('(function(){' + n.func + '\n})');
            new vm.Script('(function(){' + (n.initialize || '') + '\n})');
        }
        if (n.type === 'mqtt in' || n.type === 'mqtt out') assert(ids.has(n.broker));
    }
});
test('vista de revisión deshabilitada y sin salidas externas habilitadas', () => {
    for (const n of bundle.review) {
        if (n.type === 'tab') assert.equal(n.disabled, true);
        if (['mqtt out','influxdb out','telegram sender'].includes(n.type)) assert.equal(n.d, true);
    }
});
console.log('RESULTADO: ' + passed + ' casos aprobados; Node.js ' + process.version + '; funciones aisladas, sin MQTT ni escrituras en bases.');
