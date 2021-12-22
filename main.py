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
    INVALID     = 0
    READONLY    = 1
    READWRITE   = 2
    UNFORMATTED = 3


STATUS_STR = {
    Status.INVALID    : 'Invalid',
    Status.READONLY   : 'RO',
    Status.READWRITE  : 'R/W',
    Status.UNFORMATTED: 'Unformatted',
}


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

    parser_dd = actions.add_parser('dd', help='set the default disks to mount in the drives')
    parser_dd.add_argument('drive0', type=index, help='the index of the disk to mount in drive 0')
    parser_dd.add_argument('drive1', type=index, help='the index of the disk to mount in drive 1')
    parser_dd.add_argument('drive2', type=index, help='the index of the disk to mount in drive 2')
    parser_dd.add_argument('drive3', type=index, help='the index of the disk to mount in drive 3')

    parser_ls = actions.add_parser('ls', help='list disks')
    parser_ls.add_argument('-a', '--all', action='store_true', help='list all disks')
    parser_ls.add_argument('index', type=index, nargs='*',     help='the indices of the disks to list (default: all)')

    parser_rm = actions.add_parser('rm', help='remove disks')
    parser_rm.add_argument('index', type=index, nargs='+', help='the indices of the disks to remove')

    parser_im = actions.add_parser('im', help='import a disk image')
    parser_im.add_argument('-f', '--force', action='store_true', help='overwrite an existing disk')
    parser_im.add_argument('-i', '--index', type=index,          help='the index to import the disk at (default: first available)')
    parser_im.add_argument('-r', '--ro',    action='store_true', help='make the disk read-only')
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

    parser_ro = actions.add_parser('ro', help='marks a disk read-only')
    parser_ro.add_argument('index', type=index, nargs='+', help='the indices of the disks to mark')

    parser_rw = actions.add_parser('rw', help='marks a disk read/write')
    parser_rw.add_argument('index', type=index, nargs='+', help='the indices of the disks to mark')

    parser_un = actions.add_parser('un', help='undelete a removed disk')
    parser_un.add_argument('index', type=index, nargs='+', help='the indices of the disks to undelete')

    return parser.parse_args()


def parse_status(status):
    status = int(status[0])

    if status == 0:
        return Status.READONLY

    if 1 <= status <= 0x7F:
        return Status.READWRITE

    if 0x80 <= status <= 0xFE:
        return Status.UNFORMATTED

    return Status.INVALID


def as_status(status):
    s = {
        Status.INVALID    : b'\xFF',
        Status.READONLY   : b'\x00',
        Status.READWRITE  : b'\x0F',
        Status.UNFORMATTED: b'\xF0',
    }
    return s[status]


def parse_name(s):
    return s.rstrip(b' \t\n\r\x00').decode('utf-8')


def as_name(s):
    s = s[:12]
    n = 12 - len(s)
    s += '\x00' * n
    return s.encode('utf-8')


def read_mapping(f):
    f.seek(0)
    mapping = f.read(8)
    return [int(hi) * 256 + int(lo) for lo, hi in zip(mapping[:4], mapping[4:])]


def read_catalog(f):
    catalog = []

    f.seek(16)
    for index in range(511):
        name    = parse_name(f.read(12))
        padding = f.read(3)
        status  = parse_status(f.read(1))

        disk = Disk(name=name, status=status)
        catalog.append(disk)

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


def action_dd(mmb, d0, d1, d2, d3):
    ensure(len(set([d0, d1, d2, d3])) == 4, f'disk numbers must be unique')

    mapping = [
        d0 &  255, d1 &  255, d2 &  255, d3 &  255,
        d0 // 256, d1 // 256, d2 // 256, d3 // 256
    ]
    with open(mmb, 'rb+') as f:
        f.write(bytes(mapping))


def is_formatted(disk):
    return disk.status in {Status.READONLY, Status.READWRITE}


def action_ls(mmb, show_all):
    with open(mmb, 'rb') as f:
        mapping = read_mapping(f)
        catalog = read_catalog(f)

    disks = 0
    for index, disk in enumerate(catalog):
        if show_all or is_formatted(disk):
            print(f'{index:03d}: {disk.name:12s} {STATUS_STR[disk.status]}')
        if is_formatted(disk):
            disks += 1

    print(f'{disks}/511 disks in use, drive mapping {" ".join(str(d) for d in mapping)}')


def visit(mmb, indices, assertion, action):
    if not isinstance(indices, list):
        indices = [indices]

    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        for index in indices:
            if assertion:
                assertion(index, catalog[index])

            f.seek(16 + index * 16)
            action(f)


def mk_ensurer(status):
    return lambda index, disk: ensure(disk.status == status, f'disk {index} is {STATUS_STR[disk.status]}')


def mk_marker(status):
    def marker(f):
        f.seek(f.tell() + 15)
        f.write(as_status(status))

    return marker


def action_rm(mmb, indices):
    visit(mmb, indices, mk_ensurer(Status.READWRITE), mk_marker(Status.UNFORMATTED))


def action_un(mmb, indices):
    visit(mmb, indices, mk_ensurer(Status.UNFORMATTED), mk_marker(Status.READWRITE))


def action_ro(mmb, indices):
    visit(mmb, indices, mk_ensurer(Status.READWRITE), mk_marker(Status.READONLY))


def action_rw(mmb, indices):
    visit(mmb, indices, mk_ensurer(Status.READONLY), mk_marker(Status.READWRITE))


def action_rn(mmb, index, name):
    visit(mmb, index, mk_ensurer(Status.READWRITE), lambda f: f.write(as_name(name)))
        

def action_im(mmb, index, ssd, name, readonly, force):
    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        if index is None:
            formatted = set(index for index, disk in enumerate(catalog) if is_formatted(disk))
            available = list(set(range(511)) - formatted)
            ensure(available, 'no free indices')
            index = sorted(available)[0]

        size = os.path.getsize(ssd)
        ensure(size > 0, 'ssd cannot be empty')
        ensure(size <= 200 * 1024, 'ssd cannot be larger than 200 KiB')

        ensure(not is_formatted(catalog[index]) or force, f'index {index} is occupied')

        with open(ssd, 'rb') as g:
            disk = g.read()

        if name is None:
            name, _ = os.path.splitext(os.path.basename(ssd))

        f.seek(16 + index * 16)
        f.write(as_name(name))
        f.write(b'\x00\x00\x00')
        f.write(b'\x00' if readonly else b'\x0F')

        f.seek(8192 + index * 200 * 1024)
        f.write(disk)


def action_ex(mmb, indices, force):
    if not isinstance(indices, list):
        indices = [indices]

    with open(mmb, 'rb') as f:
        catalog = read_catalog(f)

        for index in indices:
            ensure(is_formatted(catalog[index]), f'no disk in index {index}')

            name = catalog[index].name + '.ssd'  # TODO escape?
            ensure(not os.path.exists(name) or force, f'file {name} exists')

            f.seek(8192 + index * 200 * 1024)
            disk = f.read(200 * 1024)

            with open(name, 'wb') as g:
                g.write(disk)
            

def action_cp(mmb, src, dst, force):
    with open(mmb, 'rb+') as f:
        catalog = read_catalog(f)

        ensure(is_formatted(catalog[src]), f'no disk in index {src}')
        ensure(not is_formatted(catalog[dst]) or force, f'index {dst} occupied')

        f.seek(8192 + src * 200 * 1024)
        disk = f.read(200 * 1024)

        f.seek(8192 + dst * 200 * 1024)
        f.write(disk)

        f.seek(16 + src * 16)
        name_etc = f.read(16)

        f.seek(16 + dst * 16)
        f.write(name_etc)


def action_mv(mmb, src, dst, force):
    action_cp(mmb, src, dst, force)
    action_rm(mmb, src)


def main():
    args = parse_args()

    actions = dict(nw=lambda: action_nw(args.mmb, args.force),
                   dd=lambda: action_dd(args.mmb, args.drive0, args.drive1, args.drive2, args.drive3),
                   ls=lambda: action_ls(args.mmb, args.all),
                   rm=lambda: action_rm(args.mmb, args.index),
                   im=lambda: action_im(args.mmb, args.index, args.ssd, args.name, args.ro, args.force),
                   ex=lambda: action_ex(args.mmb, args.index, args.force),
                   cp=lambda: action_cp(args.mmb, args.src, args.dst, args.force),
                   mv=lambda: action_mv(args.mmb, args.src, args.dst, args.force),
                   rn=lambda: action_rn(args.mmb, args.index, args.name),
                   ro=lambda: action_ro(args.mmb, args.index),
                   rw=lambda: action_rw(args.mmb, args.index),
                   un=lambda: action_un(args.mmb, args.index))
        
    try:
        actions[args.action]()
    except Oops as oops:
        print(f'Oops: {oops}', file=sys.stderr)
        exit(1)


if __name__ == '__main__':
    main()
