"""Fetch exactly two public ALOHA files and the first official DROID debug shard."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

FILES = [
    ('episode_0.hdf5', '11M3Ye0r5agMaaicPbVGD0q2Hb3rGklbb', 140154944, '15551ae5d56de56400eb0600fa3b853c3b665702617f87e28e38b1217ad21406'),
    ('episode_1.hdf5', '1-tx7SvYYgSvXCvnf_EI2OVdwK-CkFY6S', 143802944, '980d199afab651b7291073c17d23d64488274f87ebaf23997403b2bb5e599598'),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--proxy', help='Optional HTTP proxy URL; no proxy is hardcoded')
    a = p.parse_args()
    root = Path(a.output)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({'https': a.proxy}) if a.proxy else urllib.request.ProxyHandler())
    receipts = []
    def request(url):
        for attempt in range(5):
            try:
                return op.open(url, timeout=60)
            except OSError:
                if attempt == 4:
                    raise
    def fetch(url, target, expected_size=None, expected_hash=None, drive=False):
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            response = request(url)
            if drive and 'text/html' in response.headers.get('Content-Type', ''):
                page = response.read().decode()
                response.close()
                form = re.search(r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>', page, re.S)
                if not form:
                    raise ValueError('Google Drive download form unavailable')
                fields = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form[2]))
                direct = html.unescape(form[1])+'?'+urllib.parse.urlencode({k: html.unescape(v) for k,v in fields.items()})
                response = request(direct)
            temporary = target.with_suffix(target.suffix+'.part')
            with response, temporary.open('wb') as out:
                while block := response.read(1024*1024):
                    out.write(block)
            temporary.replace(target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if (expected_size and target.stat().st_size != expected_size) or (expected_hash and digest != expected_hash):
            raise ValueError(f'{target}: download checksum/size mismatch')
        receipts.append({'url': url, 'file': str(target), 'bytes': target.stat().st_size, 'sha256': digest})
        print(target, target.stat().st_size, flush=True)
    for name, ident, size, digest in FILES:
        fetch(f'https://drive.google.com/uc?export=download&id={ident}', root/'aloha'/name, size, digest, True)
    base = 'https://storage.googleapis.com/gresearch/robotics/droid_100/1.0.0/'
    for name in ['dataset_info.json', 'features.json', 'r2d2_faceblur-train.tfrecord-00000-of-00031']:
        fetch(base+name, root/'droid/1.0.0'/name)
    (root/'receipts.json').write_text(json.dumps(receipts, indent=2))


if __name__ == '__main__':
    main()
