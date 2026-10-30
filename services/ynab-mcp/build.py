"""Build a pinned local artifact; never publish, deploy or load live credentials."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
PIN = json.loads((HERE / 'upstream.json').read_text(encoding='utf-8'))


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=180, **kwargs)


def prepare(root):
    source = root / 'source'
    run(['git', '-c', 'core.autocrlf=false', 'clone', '--quiet', '--no-checkout', PIN['repository'], str(source)])
    run(['git', '-c', 'core.autocrlf=false', 'checkout', '--quiet', '--detach', PIN['commit']], cwd=source)
    for ref, expected in [('HEAD', PIN['commit']), ('refs/tags/' + PIN['tag'], PIN['tag_object']),
                          ('refs/tags/' + PIN['tag'] + '^{}', PIN['commit'])]:
        if subprocess.check_output(['git', 'rev-parse', ref], cwd=source, text=True).strip() != expected:
            raise ValueError('Upstream ref mismatch')
    if hashlib.sha256((source / 'package-lock.json').read_bytes()).hexdigest() != PIN['lock_sha256']:
        raise ValueError('Lockfile hash mismatch')
    with urllib.request.urlopen(PIN['package_url'], timeout=30) as response:
        package = response.read(4 * 1024 * 1024 + 1)
    if hashlib.sha256(package).hexdigest() != PIN['package_sha256']:
        raise ValueError('Published package hash mismatch')
    count = 0
    with tarfile.open(fileobj=io.BytesIO(package)) as archive:
        for member in archive:
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith('package/') or '..' in PurePosixPath(member.name).parts:
                raise ValueError('Unexpected package member')
            relative = member.name[len('package/'):]
            original = subprocess.check_output(['git', 'show', PIN['commit'] + ':' + relative], cwd=source)
            if original != archive.extractfile(member).read():
                raise ValueError('Package/source mismatch')
            count += 1
    if count != 49:
        raise ValueError('Unexpected package file count')
    return source


def validate_recipe(dockerfile):
    if hashlib.sha256(dockerfile.replace('\r\n', '\n').encode()).hexdigest() != PIN['recipe_sha256']:
        raise ValueError('Dockerfile does not match the reviewed complete recipe')
    stages = re.findall(r'(?im)^FROM[ \t]+([^ \t\r\n]+)(?:[ \t]+AS[ \t]+(\w+))?[ \t]*$', dockerfile)
    copies = re.findall(r'(?im)^COPY[ \t]+(.+)$', dockerfile)
    if stages != [(PIN['build_image'], 'dependencies'), (PIN['runtime_image'], '')] or copies != [
        '--from=upstream package.json package-lock.json ./',
        '--from=dependencies /app/node_modules ./node_modules',
        '--from=upstream package.json index.js LICENSE ./',
        '--from=upstream lib ./lib', '--from=upstream modules ./modules',
        'entrypoint.mjs /policy/entrypoint.mjs',
    ]:
        raise ValueError('Dockerfile does not match the source/base pins')


def build(tag, record):
    if not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*', tag):
        raise ValueError('Invalid image tag')
    if record.exists():
        raise ValueError('Refusing to overwrite an existing build record')
    validate_recipe((HERE / 'Dockerfile').read_text(encoding='utf-8'))
    policy = (HERE / 'entrypoint.mjs').read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(policy).hexdigest() != PIN['entrypoint_sha256']:
        raise ValueError('Entrypoint does not match the reviewed policy')
    with tempfile.TemporaryDirectory(prefix='ynab-source-') as temp:
        source = prepare(Path(temp))
        run(['docker', 'build', '--no-cache', '--platform', 'linux/amd64', '--build-context', 'upstream=' + str(source),
             '--file', str(HERE / 'Dockerfile'), '--tag', tag, str(HERE)])
        image_id = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
        evidence = {'source_commit': PIN['commit'], 'package_sha256': PIN['package_sha256'],
                    'package_source_files': 49, 'image_id': image_id, 'tag': tag,
                    'build_image': PIN['build_image'], 'runtime_image': PIN['runtime_image'],
                    'recipe_sha256': PIN['recipe_sha256'], 'entrypoint_sha256': PIN['entrypoint_sha256'],
                    'published': False, 'production_approved': False}
        with record.open('x', encoding='utf-8') as output:
            output.write(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--record', required=True, type=Path)
    args = parser.parse_args()
    build(args.tag, args.record)
