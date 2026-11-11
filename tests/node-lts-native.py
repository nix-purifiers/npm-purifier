"""Exercise each selected Node point through native and ordinary registry workflows."""
import json
import argparse
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--current', action='store_true', help='Run only the pinned default SDK.')
parser.add_argument('--supported', action='store_true', help='Run the exact current upstream SDK and npm points.')
parser.add_argument('--latest-npm', action='store_true', help='Run only the current npm CLI point.')
parser.add_argument('--major', action='append', choices=[version.split('.')[0] for _, version in points],
                    help='Run selected exact regression points; omitted runs every point.')
options = parser.parse_args()
selected = options.major
current_version = subprocess.check_output(
    ['nix', 'eval', '--raw', '.#checks.' + system + '.current-node.nodeVersion'], text=True
).strip()
if options.supported or options.latest_npm:
    names = ('latest-npm',) if options.latest_npm else ('supported-node-22', 'supported-node-24', 'supported-node-26', 'latest-npm')
    points = [(name, subprocess.check_output(
        ['nix', 'eval', '--raw', '.#checks.' + system + '.' + name + '.nodeVersion'], text=True
    ).strip()) for name in names]
elif options.current:
    points = [('current-node', current_version)]
elif selected:
    points = [(name, version) for name, version in points if version.split('.')[0] in selected]
else:
    points.insert(0, ('current-node', current_version))
for name, version in points:
    print('Native registry workflow: ' + system + ' Node ' + version, flush=True)
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
        str(pathlib.Path(outputs['metadata']) / 'catalog.json'), 'legacy-node', name,
    ], check=True)
