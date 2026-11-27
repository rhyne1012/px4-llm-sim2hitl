#!/usr/bin/env python3
"""Mark where a repository sits in the shared overview diagram.

    python3 images/mark_overview.py <out.svg> --layer glue                       # the toolkit's README
    python3 <toolkit>/images/mark_overview.py images/overview.svg --layer vehicle --name SkySurfer   # a vehicle repository

Every repository shows the same diagram (images/overview.svg of the toolkit, the one source); only the marker differs:
a heavy frame around its layer and the tag "This repository" (with the repository's name, if given). A vehicle
repository keeps its marked copy in its own tree (a README shows only images of its own repository) and makes it again
when it moves to another toolkit version. Standard library only. The name must be ASCII or use only characters the
diagram already contains (its embedded font is a subset).
"""
import argparse
import hashlib
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().with_name('overview.svg')
INK = '#2F2F2F'


def width(text, latin, cjk):
    return sum(cjk if ord(c) > 0x2e80 else latin for c in text)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('out')
    p.add_argument('--layer', required=True, choices=['glue', 'vehicle'])
    p.add_argument('--name', help='the repository name shown in the tag')
    p.add_argument('--source', default=str(SOURCE))
    a = p.parse_args()
    source = Path(a.source).read_text(encoding='utf-8')
    m = re.search(rf'<rect id="layer-{a.layer}" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="([\d.]+)"',
                  source)
    if not m:
        raise SystemExit(f'{a.source}: no layer-{a.layer} rectangle')
    x, y, w, h, rx = (float(v) for v in m.groups())
    used = set(''.join(re.findall(r'>([^<>]*)<', source)))
    name = a.name or ''
    missing = sorted(c for c in set(name) if ord(c) > 0x7e and c not in used)
    if missing:
        raise SystemExit(f'--name has characters the embedded font lacks: {"".join(missing)}')
    en = f'This repository: {name}' if name else 'This repository'
    zh = '　本儲存庫'
    tag_w = width(en, 8.8, 16) + width(zh, 8, 15) + 28
    tag_x, tag_y = x + 24, y - 13
    marker = (f'\n  <g id="this-repository">\n'
              f'    <rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" fill="none" stroke="{INK}" stroke-width="4"/>\n'
              f'    <rect x="{tag_x:g}" y="{tag_y:g}" width="{tag_w:.0f}" height="26" rx="13" fill="{INK}"/>\n'
              f'    <text x="{tag_x + tag_w / 2:.0f}" y="{tag_y + 19:g}" text-anchor="middle" class="on-accent h4">{en}'
              f'<tspan class="on-accent-zh small">{zh}</tspan></text>\n  </g>\n')
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]
    out = source.replace('</svg>', marker + '</svg>')
    # (no double hyphen inside an XML comment)
    out = out.replace('<title>', f'<!-- made by px4-llm-sim2hitl images/mark_overview.py: layer {a.layer}'
                      f'{", name " + name if name else ""}, from overview.svg sha256 {digest} -->\n  <title>', 1)
    out = re.sub(r'\(this repository / 本儲存庫\)', f'({en} / 本儲存庫)', out, count=1)
    Path(a.out).write_text(out, encoding='utf-8')
    print(f'{a.out}: layer {a.layer}, tag "{en}", source sha256 {digest}')


if __name__ == '__main__':
    main()
