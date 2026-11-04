"""Exercise each selected Node point through native and ordinary registry workflows."""
import json
import pathlib
import subprocess
import sys

system = subprocess.check_output(
    ['nix', 'eval', '--impure', '--raw', '--expr', 'builtins.currentSystem'], text=True
).strip()
points = [('shrinkwrap-node-4', '4.9.1'), ('shrinkwrap-node-6', '6.17.1')]
for name, version in points:
    print('Native registry workflow: Node ' + version, flush=True)
    def build(attribute):
        return pathlib.Path(subprocess.check_output(
            ['nix', 'build', '--no-link', '--print-out-paths',
             '.#checks.' + system + '.' + attribute], text=True
        ).strip())
    tools = build(name + '-tools')
    release = build(name + '.release')
    outputs = json.loads(subprocess.check_output(
        ['nix', 'build', '--no-link', '--json',
         '.#checks.' + system + '.' + name + '.repository^*'], text=True
    ))[0]['outputs']
    subprocess.run([
        sys.executable, 'tests/legacy-native.py', str(tools),
        str(release / 'legacy-npm-app.tgz'), version, outputs['out'],
        str(pathlib.Path(outputs['metadata']) / 'catalog.json'), name,
    ], check=True)
