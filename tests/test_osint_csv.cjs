const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../backend/cyber/web/osint.html'), 'utf8');
const start = html.indexOf('function parseCSV(text) {');
const end = html.indexOf("byId('importForm').onsubmit", start);
const parser = vm.runInNewContext(`${html.slice(start, end)}; parseCSV`);

test('CSV imports preserve quoted commas, escaped quotes, multiline notes and lists', () => {
  const rows = parser('\uFEFFname,entity_type,phones,emails,payment_identifiers,notes\r\n"Example, Shop",business,+12025550101,contact@example.invalid;support@example.invalid,DEMO,"Quoted ""note""\nsecond line"\r\n');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, 'Example, Shop');
  assert.equal(rows[0].notes, 'Quoted "note"\nsecond line');
  assert.equal(rows[0].emails.length, 2);
});

test('Malformed or ambiguous CSV imports fail instead of losing column values', () => {
  for (const text of [
    'name,unknown\nExample,value',
    'name,name\nFirst,Second',
    'name,notes\nExample,too,many',
    'name\n"unclosed',
    'name\n"Example"extra',
  ]) {
    assert.throws(() => parser(text));
  }
});
