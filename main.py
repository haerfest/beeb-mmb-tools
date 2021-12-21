#!/usr/bin/env python3


import os
import sys

from argparse    import ArgumentParser
from collections import namedtuple
from enum        import Enum


Disk = namedtuple('Disk', ['name', 'status'])


class Oops(RuntimeError):
    pass


def ensure(condition, message):
    if not condition:
        raise Oops(message)


class Status(Enum):
    UNFORMATTED = 0
    READWRITE   = 1
    READONLY    = 2
    INVALID     = 3


def index(s):
    i = int(s)

    if not (0 <= i <= 511):
        return ValueError(s)

    return i

    
def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--mmb', '-m', default='BEEB.MMB', help='the mmb file (default: ./BEEB.MMB)')

    actions = parser.add_subparsers(required=True, dest='action', help='action to perform')

    parser_new = actions.add_parser('new', help='create new mmb')
    parser_new.add_argument('-f', '--force', action='store_true', help='overwrite existing mmb')

    parser_ls = actions.add_parser('ls', help='list enclosed disk')
    parser_ls.add_argument('index', type=index, nargs='*', help='index of disk to list (default: all)')

    parser_rm = actions.add_parser('rm', help='remove enclosed disk image')
    parser_rm.add_argument('index', type=index, nargs='+', help='index of disk to remove')

    parser_im = actions.add_parser('im', help='imports a disk image')
    parser_im.add_argument('-f', '--force', action='store_true', help='overwrite occupied index')
    parser_im.add_argument('-i', '--index', type=index,          help='index to import disk at (default: first available)')
    parser_im.add_argument('-l', '--lock',  action='store_true', help='lock disk')
    parser_im.add_argument('-n', '--name',                       help='name for disk')
    parser_im.add_argument('ssd',                                help='disk to insert')

    parser_ex = actions.add_parser('ex', help='exports a disk image')
    parser_ex.add_argument('-f', '--force', action='store_true', help='overwrite existing disk')
    parser_ex.add_argument('index', type=index,                  help='index to export disk from')

    return parser.parse_args()


def parse_status(status):
    if status == 0:
        return Status.READONLY

    if 1 <= status <= 0x7F:
        return Status.READWRITE

    if 0x80 <= status <= 0xFE:
        return Status.UNFORMATTED

    return Status.INVALID


def read_catalog(f):
    catalog = {}

    f.seek(16)
    for index in range(511):
        name    = f.read(12).rstrip(b' \t\n\r\x00').decode('utf-8')
        padding = f.read(3)
        status  = parse_status(int(f.read(1)[0]))

        if status not in [Status.INVALID, Status.UNFORMATTED]:
            catalog[index] = Disk(name=name, status=status)

    return catalog


def action_new(mmb, force):
    ensure(not os.path.exists(mmb) or force, 'mmb exists')

    with open(mmb, 'wb') as f:
        f.write(b'\x00\x01\x02\x03\x00\x00\x00\x00')
        f.write(b'\x00\x00\x00\x00\x00\x00\x00\x00')

        for index in range(511):
            f.seek(16 + index * 16 + 15)
            f.write(b'\xF0')

        f.seek(8192 + 511 * 200 * 1024 - 1)
        f.write(b'\x00')


def action_ls(mmb):
    s = {
        Status.READWRITE: 'R/W',
        Status.READONLY:  'RO',
    }

    with open(mmb, 'rb') as f:
        catalog = read_catalog(f)

    for index, disk in catalog.items():
        print(f'{index:03d}: {disk.name:12s} {s[disk.status]}')


def action_rm(mmb, indices):
    if not isinstance(indices, list):
        indices = [indices]

    with open(mmb, 'wb+') as f:
        for index in indices:
            f.seek(16 + index * 16 + 15)
            f.write(b'\xF0')


def action_im(mmb, index, ssd, name, lock, force):
    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        if index is None:
            available = list(set(range(511)) - set(catalog))
            ensure(available, 'no free indices')
            index = sorted(available)[0]

        size = os.path.getsize(ssd)
        ensure(size > 0, 'ssd cannot be empty')
        ensure(size <= 200 * 1024, 'ssd cannot be larger than 200 KiB')

        ensure(index not in catalog or force, f'index {index} is occupied')

        with open(ssd, 'rb') as g:
            disk = g.read()

        if name is None:
            name = os.path.basename(ssd)[:12]

        n = 12 - len(name)
        name += '\x00' * n

        f.seek(16 + index * 16)
        f.write(name.encode('utf-8'))
        f.write(b'\x00\x00\x00')
        f.write(b'\x00' if lock else b'\x0F')

        f.seek(8192 + index * 200 * 1024)
        f.write(disk)


def action_ex(mmb, index, force):
    with open(mmb, 'rb') as f:
        catalog = read_catalog(f)

        ensure(index in catalog, f'no disk in index {index}')

        name = catalog[index].name + '.ssd'  # TODO escape?
        ensure(not os.path.exists(name) or force, f'file {name} exists')

        f.seek(8192 + index * 200 * 1024)
        disk = f.read(200 * 1024)

    with open(name, 'wb') as f:
        f.write(disk)
            

def main():
    args = parse_args()

    try:
        if args.action == 'new':
            return action_new(args.mmb, args.force)

        if args.action == 'ls':
            return action_ls(args.mmb)

        if args.action == 'rm':
            return action_rm(args.mmb, args.index)

        if args.action == 'im':
            return action_im(args.mmb, args.index, args.ssd, args.name, args.lock, args.force)

        if args.action == 'ex':
            return action_ex(args.mmb, args.index, args.force)

    except Oops as oops:
        print(f'Oops: {oops}', file=sys.stderr)
        exit(1)


if __name__ == '__main__':
    main()
