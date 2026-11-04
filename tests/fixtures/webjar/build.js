const fs = require('fs');
fs.mkdirSync('dist', { recursive: true });
fs.writeFileSync('dist/proof.js', 'globalThis.answer = 42;\n');
fs.writeFileSync('.env', 'PRIVATE_FIXTURE=not-for-publication\n');
fs.mkdirSync('node_modules/private', { recursive: true });
fs.writeFileSync('node_modules/private/secret.js', 'not-for-publication\n');
