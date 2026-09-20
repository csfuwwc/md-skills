"""Verify larger static covers using only returned URLs for the same resource."""
import json
import struct
import subprocess
from urllib.parse import urlparse


def resource_path(url):
    u = urlparse(url)
    if (u.scheme != 'https' or not (u.hostname or '').endswith('.douyinpic.com')
            or u.username or u.password or u.port not in (None, 443)):
        return None
    return u.path.removeprefix('/obj/').lstrip('/').split('~', 1)[0]


def cover_candidates(video):
    display = video.get('cover') or {}
    uri = display.get('uri')
    if not isinstance(uri, str) or not uri:
        return []
    result, seen = [], set()
    for field in ('cover', 'raw_cover'):
        value = video.get(field) or {}
        if value.get('uri') != uri:
            continue
        for url in value.get('url_list') or []:
            if not isinstance(url, str) or url in seen:
                continue
            try:
                matches = resource_path(url) == uri
            except ValueError:
                matches = False
            if matches:
                seen.add(url)
                result.append({'url': url, 'source': 'video.' + field, 'uri': uri})
    return result[:6]


def image_dimensions(data):
    """Read actual JPEG/PNG headers; reject animation and unsupported formats."""
    if data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xDA, 0xD9):
                break
            length = int.from_bytes(data[pos:pos + 2], 'big')
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 8:
                height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
                if width and height:
                    return width, height, 'jpeg'
            pos += length
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        pos, size = 8, None
        while pos + 12 <= len(data):
            length = int.from_bytes(data[pos:pos + 4], 'big')
            kind = data[pos + 4:pos + 8]
            end = pos + length + 12
            if end > len(data) or kind == b'acTL':
                break
            if kind == b'IHDR' and length == 13:
                size = struct.unpack('>II', data[pos + 8:pos + 16])
            if kind == b'IEND' and size and all(size):
                return *size, 'png'
            pos = end
    raise ValueError('Unsupported, animated or incomplete image')


def probe_image(url):
    if not resource_path(url) or any(c in url for c in '\r\n\x00'):
        raise ValueError('Not an approved image CDN URL')
    # No cookies, curlrc, redirects, disabled TLS checks, or signed URLs in argv/logs.
    result = subprocess.run(['curl', '--disable', '--fail', '--silent', '--show-error',
        '--proto', '=https', '--max-time', '12', '--max-filesize', '8388608',
        '--referer', 'https://www.douyin.com/', '--config', '-'],
        input=('url = ' + json.dumps(url) + '\n').encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if result.returncode:
        raise OSError('Cover request failed')
    data = result.stdout
    if len(data) > 8388608:
        raise ValueError('Cover exceeds 8 MiB')
    return image_dimensions(data)


def upgrade_cover(record, probe=probe_image):
    result = dict(record)
    candidates = record.get('coverCandidates') or []
    if record.get('type') != 'video' or record.get('coverFallback') or not candidates:
        return result
    result.update(coverQuality='unverified_fallback', coverWidth=None, coverHeight=None,
                  coverFormat=None, coverQualityErrors=[])
    best, checked_paths = None, set()
    # Compare the existing cover first. Successful CDN mirrors are not separate qualities.
    candidates = sorted(candidates, key=lambda c: c['url'] != record.get('cover'))
    for candidate in candidates:
        url = candidate['url']
        if resource_path(url) != candidate['uri']:
            continue
        path = urlparse(url).path
        if path in checked_paths:
            continue
        try:
            width, height, fmt = probe(url)
            if fmt not in ('jpeg', 'png') or width <= 0 or height <= 0:
                raise ValueError('Not a verified static image')
            checked_paths.add(path)
            if best is None or width * height > best[0]:
                best = (width * height, candidate, width, height, fmt)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result['coverQualityErrors'].append(type(exc).__name__)
    if best:
        _, candidate, width, height, fmt = best
        result.update(cover=candidate['url'], coverSource=candidate['source'],
                      coverQuality='largest_verified_static', coverWidth=width,
                      coverHeight=height, coverFormat=fmt)
    return result
