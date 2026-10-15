// Parse only, in Node. No browser, network, rendering, or dependency installation.
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const [modulePath, ...files] = process.argv.slice(2);
if (!modulePath || !files.length) {
  console.error('Usage: node check_mermaid.mjs /installed/mermaid.esm.mjs diagram.mmd ...');
  process.exit(2);
}
let mermaid;
try {
  const imported = await import(pathToFileURL(resolve(modulePath)).href);
  mermaid = imported.default || imported;
  if (typeof mermaid.parse !== 'function') throw new Error('Module exposes no Mermaid parse API');
  mermaid.initialize?.({ startOnLoad: false, securityLevel: 'strict' });
} catch (error) {
  console.log(JSON.stringify({ status: 'unavailable', error: String(error).slice(0, 400) }));
  process.exit(2);
}
const results = [];
for (const file of files) {
  try {
    const result = await mermaid.parse(await readFile(file, 'utf8'));
    if (result === false) throw new Error('Parser rejected diagram');
    results.push({ file, status: 'passed' });
  } catch (error) {
    results.push({ file, status: 'failed', error: String(error).slice(0, 600) });
  }
}
console.log(JSON.stringify({ parser: resolve(modulePath), results }));
process.exit(results.some(r => r.status !== 'passed') ? 1 : 0);
