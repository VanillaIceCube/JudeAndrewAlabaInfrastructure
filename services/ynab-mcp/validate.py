"""Read-only operator preflight; never start a service or print secret contents."""
import argparse
import os
from pathlib import Path
import re
import stat


def validate(image, token_file):
    if not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('Use a reviewed registry image with its sha256 digest')
    if not token_file.is_absolute() or token_file.is_symlink():
        raise ValueError('Token must be an absolute regular-file path')
    if token_file.resolve(strict=True) != token_file:
        raise ValueError('Secret path must not contain symlink components')
    parent = token_file.parent.stat()
    if os.name != 'posix' or parent.st_uid not in (0, os.geteuid()) or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('Secret parent must be operator/root-owned with mode 0700')
    for ancestor in token_file.parent.parents:
        if ancestor.stat().st_mode & 0o022:
            raise ValueError('Secret ancestors must not be group/world writable')
    metadata = token_file.stat()
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= 4096:
        raise ValueError('Token file must contain 1-4096 bytes')
    if os.name != 'posix' or metadata.st_uid != 65532 or stat.S_IMODE(metadata.st_mode) != 0o400:
        raise ValueError('Validate on the Linux operator host: secret uid 65532, mode 0400 required')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--token-file', required=True, type=Path)
    args = parser.parse_args()
    validate(args.image, args.token_file)
    print('Immutable image reference and private secret metadata validated; no service started')
