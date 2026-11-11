// node --test tests/test_escenario_core.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const E = createRequire(import.meta.url)('../v7/escenario_core.js');

const ESC = { fichas: [{ id: 990000001, nombre: 'Ana' }], citas: { 990000001: [{ id: 990000101, id_paciente: 990000001, fecha: '2026-11-13', hora_inicio: '10:40:00', id_estado: 7 }] } };

test('con el celular de Lucas o sintético lee el escenario', () => {
  assert.ok(E.leer(JSON.stringify(ESC), '5491161461034'));
  assert.ok(E.leer(JSON.stringify(ESC), '5490000000651'));
  assert.ok(E.leer(JSON.stringify(ESC), '5499991234567'));
});

test('con el celular de un paciente NUNCA usa el escenario', () => {
  assert.equal(E.leer(JSON.stringify(ESC), '5493885123456'), null);
  assert.equal(E.leer(JSON.stringify(ESC), ''), null);
  assert.equal(E.leer(JSON.stringify(ESC), undefined), null);
});

test('sin escenario o roto: null (la herramienta lee Dentalink)', () => {
  assert.equal(E.leer(null, '5491161461034'), null);
  assert.equal(E.leer('', '5491161461034'), null);
  assert.equal(E.leer('{roto', '5491161461034'), null);
  assert.equal(E.leer('{"fichas":[]}', '5491161461034'), null);
});

test('busca una cita por id', () => {
  assert.equal(E.cita(ESC, 990000101).hora_inicio, '10:40:00');
  assert.equal(E.cita(ESC, '990000101').fecha, '2026-11-13');
  assert.equal(E.cita(ESC, 1), null);
});
