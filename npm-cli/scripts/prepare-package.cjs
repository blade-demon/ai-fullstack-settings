'use strict';
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'assets');
fs.mkdirSync(assets, { recursive: true });
fs.copyFileSync(path.resolve(root, '../tools/start.command.in'), path.join(assets, 'start.command.in'));
fs.chmodSync(path.join(root, 'bin/team-dev-env.cjs'), 0o755);
