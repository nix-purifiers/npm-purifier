"""Exercise each selected Node point through native and ordinary registry workflows."""
import json
import pathlib
import subprocess
import sys

system = subprocess.check_output(
    ['nix', 'eval', '--impure', '--raw', '--expr', 'builtins.currentSystem'], text=True
).strip()
points = [('legacy-node', '12.22.12')]
points += [('node-lts-' + major, version) for major, version in [
    ('8', '8.17.0'), ('10', '10.24.1'), ('14', '14.21.3'),
    ('16', '16.20.2'), ('18', '18.20.8'), ('20', '20.19.0'),
    ('22', '22.14.0'), ('26', '26.0.0'),
]]
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
        str(pathlib.Path(outputs['metadata']) / 'catalog.json'),
    ], check=True)
