// Prueba el Function Node exacto generado, incluidas barreras CSRF y conservación del grafo.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const cp = require('node:child_process');
const source = require('../nodered/reference/flows.review.disabled.json');
const patch = JSON.parse(cp.execFileSync('python3', ['-c',
  'import json,sys;from server.profiles.nodered_patch import build;print(json.dumps(build(json.load(sys.stdin),"fixture")))'],
  { input: JSON.stringify(source), encoding: 'utf8' }));
assert.deepEqual(Object.keys(patch.updates), ['nr10_validar']);
assert.equal(patch.additions.some(n => ['mqtt out','telegram sender','influxdb out'].includes(n.type)), false);
const input = source.find(n => n.id === 'nr10_validar');
assert.deepEqual(patch.updates.nr10_validar.wires[0].slice(0,-1), input.wires[0]);
assert.equal(patch.updates.nr10_validar.wires[0].at(-1), 'profiles_telemetry');
const fn = patch.additions.find(n => n.id === 'profiles_prepare_post');
const run = (headers) => {
  let sent;
  const msg = { req: { headers }, payload: { action: 'save_recipe' } };
  const result = new vm.Script('(function(){'+fn.func+'})()').runInNewContext({msg,node:{send:m=>sent=m}});
  return {result,sent};
};
for (const headers of [
  {host:'localhost:1880'},
  {host:'localhost:1880',origin:'http://other.test','x-perfiles-request':'1','content-type':'application/json'},
  {host:'localhost:1880',origin:'http://localhost:1880','content-type':'application/json'},
  {host:'localhost:1880',origin:'http://localhost:1880','x-perfiles-request':'1','content-type':'text/plain'}
]) { const r=run(headers);assert.equal(r.result,null);assert.equal(r.sent[1].statusCode,403); }
const allowed=run({host:'localhost:1880',origin:'http://localhost:1880','x-perfiles-request':'1','content-type':'application/json'});
assert.equal(allowed.result.method,'POST');assert.equal(allowed.result.url,'http://birra_perfiles:8787/api');
assert.equal(allowed.result.req.headers.host,'localhost:1880');
console.log('Proxy: grafo conservado, sin salidas de control, cuatro rechazos CSRF y petición válida: OK');
