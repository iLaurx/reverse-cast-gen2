"""Strict input parsing; no arbitrary URL is fetched."""
import ipaddress
import math
import re
from urllib.parse import urlsplit, parse_qs

VIDEO = re.compile(r'[A-Za-z0-9_-]{11}\Z')

def position(value):
    if isinstance(value, bool):
        raise ValueError('La posición debe ser un número de segundos.')
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 86400:
        raise ValueError('La posición debe estar entre 0 y 86400 segundos.')
    return number

def host(value):
    ip = ipaddress.IPv4Address(value)
    if not any(ip in ipaddress.IPv4Network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')) or str(ip).endswith('.255'):
        raise ValueError('Usa la IPv4 privada del Chromecast en tu red local.')
    return str(ip)

def youtube_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Pega un enlace de YouTube válido.')
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError('Solo se aceptan enlaces HTTP o HTTPS de YouTube.')
    domain = parsed.hostname
    query = parse_qs(parsed.query)
    if domain == 'youtu.be':
        video = parsed.path.removeprefix('/')
    elif domain in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        parts = parsed.path.strip('/').split('/')
        if parsed.path == '/watch' and len(query.get('v', [])) == 1:
            video = query['v'][0]
        elif len(parts) == 2 and parts[0] in ('shorts', 'live', 'embed'):
            video = parts[1]
        else:
            raise ValueError('El enlace debe identificar un video de YouTube.')
    else:
        raise ValueError('El dominio debe ser youtube.com o youtu.be.')
    if not VIDEO.fullmatch(video):
        raise ValueError('El identificador del video debe tener 11 caracteres válidos.')
    raw = query.get('t', query.get('start', ['0']))[0]
    if raw.isdigit():
        seconds = int(raw)
    else:
        match = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', raw)
        if not match or not any(match.groups()):
            raise ValueError('El tiempo del enlace no es válido.')
        seconds = sum(int(n or 0) * factor for n, factor in zip(match.groups(), (3600, 60, 1)))
    return video, position(seconds)
