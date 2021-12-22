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
    parser.add_argument('--mmb', '-m', default='BEEB.MMB', help='the MMB file (default: ./BEEB.MMB)')

    actions = parser.add_subparsers(required=True, dest='action', help='action to perform')

    parser_nw = actions.add_parser('nw', help='create a new empty MMB file')
    parser_nw.add_argument('-f', '--force', action='store_true', help='overwrite an existing file')

    parser_ls = actions.add_parser('ls', help='list disks')
    parser_ls.add_argument('index', type=index, nargs='*', help='the indices of the disks to list (default: all)')

    parser_rm = actions.add_parser('rm', help='remove disks')
    parser_rm.add_argument('index', type=index, nargs='+', help='the indices of the disks to remove')

    parser_im = actions.add_parser('im', help='import a disk image')
    parser_im.add_argument('-f', '--force', action='store_true', help='overwrite an existing disk')
    parser_im.add_argument('-i', '--index', type=index,          help='the index to import the disk at (default: first available)')
    parser_im.add_argument('-l', '--lock',  action='store_true', help='lock the disk, making it read-only')
    parser_im.add_argument('-n', '--name',                       help='the name for the disk')
    parser_im.add_argument('ssd',                                help='the SSD disk file to insert')

    parser_ex = actions.add_parser('ex', help='export a disk image')
    parser_ex.add_argument('-f', '--force', action='store_true', help='overwrite an existing disk')
    parser_ex.add_argument('index', type=index,                  help='the indices of the disks to export')

    parser_cp = actions.add_parser('cp', help='copies a disk image')
    parser_cp.add_argument('-f', '--force', action='store_true', help='overwrite an existing disk')
    parser_cp.add_argument('src',           type=index,          help='the index of the disk to copy')
    parser_cp.add_argument('dst',           type=index,          help='the index to copy the disk to')

    parser_mv = actions.add_parser('mv', help='moves a disk image')
    parser_mv.add_argument('-f', '--force', action='store_true', help='overwrite an existing disk')
    parser_mv.add_argument('src',           type=index,          help='the index of the disk to move')
    parser_mv.add_argument('dst',           type=index,          help='the index to move the disk to')

    parser_rn = actions.add_parser('rn', help='renames a disk image')
    parser_rn.add_argument('index', type=index, help='the index of the disk to rename')
    parser_rn.add_argument('name',              help='the new name of the disk')

    return parser.parse_args()


def parse_status(status):
    if status == 0:
        return Status.READONLY

    if 1 <= status <= 0x7F:
        return Status.READWRITE

    if 0x80 <= status <= 0xFE:
        return Status.UNFORMATTED

    return Status.INVALID


def parse_name(s):
    return s.rstrip(b' \t\n\r\x00').decode('utf-8')


def as_name(s):
    s = s[:12]
    n = 12 - len(s)
    s += '\x00' * n
    return s.encode('utf-8')


def read_catalog(f):
    catalog = {}

    f.seek(16)
    for index in range(511):
        name    = parse_name(f.read(12))
        padding = f.read(3)
        status  = parse_status(int(f.read(1)[0]))

        if status not in [Status.INVALID, Status.UNFORMATTED]:
            catalog[index] = Disk(name=name, status=status)

    return catalog


def action_nw(mmb, force):
    ensure(not os.path.exists(mmb) or force, f'file {mmb} exists')

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

    with open(mmb, 'rb+') as f:
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
            name, _ = os.path.splitext(os.path.basename(ssd))

        f.seek(16 + index * 16)
        f.write(as_name(name))
        f.write(b'\x00\x00\x00')
        f.write(b'\x00' if lock else b'\x0F')

        f.seek(8192 + index * 200 * 1024)
        f.write(disk)


def action_ex(mmb, indices, force):
    if not isinstance(indices, list):
        indices = [indices]

    with open(mmb, 'rb') as f:
        catalog = read_catalog(f)

        for index in indices:
            ensure(index in catalog, f'no disk in index {index}')

            name = catalog[index].name + '.ssd'  # TODO escape?
            ensure(not os.path.exists(name) or force, f'file {name} exists')

            f.seek(8192 + index * 200 * 1024)
            disk = f.read(200 * 1024)

            with open(name, 'wb') as g:
                g.write(disk)
            

def action_cp(mmb, src, dst, force, mv=False):
    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        ensure(src in catalog, f'no disk in index {src}')
        ensure(dst not in catalog or force, f'index {dst} occupied')

        f.seek(8192 + src * 200 * 1024)
        disk = f.read(200 * 1024)

        f.seek(8192 + dst * 200 * 1024)
        f.write(disk)

        f.seek(16 + src * 16)
        name_etc = f.read(16)

        f.seek(16 + dst * 16)
        f.write(name_etc)

    if mv:
        action_rm(mmb, src)


def action_rn(mmb, index, name):
    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        ensure(index in catalog, f'no disk in index {index}')

        f.seek(16 + index * 16)
        f.write(as_name(name))
        

def main():
    args = parse_args()

    actions = dict(nw=lambda: action_nw(args.mmb, args.force),
                   ls=lambda: action_ls(args.mmb),
                   rm=lambda: action_rm(args.mmb, args.index),
                   im=lambda: action_im(args.mmb, args.index, args.ssd, args.name, args.lock, args.force),
                   ex=lambda: action_ex(args.mmb, args.index, args.force),
                   cp=lambda: action_cp(args.mmb, args.src, args.dst, args.force),
                   mv=lambda: action_cp(args.mmb, args.src, args.dst, args.force, mv=True),
                   rn=lambda: action_rn(args.mmb, args.index, args.name))
        
    try:
        actions[args.action]()
    except Oops as oops:
        print(f'{oops}', file=sys.stderr)
        exit(1)


if __name__ == '__main__':
    main()
