"""Inventario acotado de servicios del Chromecast seleccionado; no escanea la red."""
import argparse
import datetime as dt
import ipaddress
import json
import pathlib
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


def inspect(host):
    ipaddress.IPv4Address(host)
    result = {'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'host': host, 'ports': {}, 'dial': {}}
    for port in (22, 5555, 8008, 8009, 8443, 9222):
        try:
            with socket.create_connection((host, port), timeout=2):
                result['ports'][str(port)] = 'open'
        except ConnectionRefusedError:
            result['ports'][str(port)] = 'refused'
        except (TimeoutError, OSError) as error:
            result['ports'][str(port)] = type(error).__name__
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in ('/ssdp/device-desc.xml', '/apps/YouTube'):
        try:
            with opener.open(f'http://{host}:8008{path}', timeout=5) as response:
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise ValueError('Respuesta demasiado grande')
                item = {'status': response.status,
                        'content_type': response.headers.get('Content-Type'),
                        'server': response.headers.get('Server'),
                        'application_url': response.headers.get('Application-URL')}
            root = ET.fromstring(body)
            for element in root.iter():
                key = element.tag.rsplit('}', 1)[-1]
                if key in ('manufacturer', 'modelName', 'modelNumber', 'name', 'state'):
                    item[key] = element.text
                if key == 'options':
                    item['allow_stop_advertised'] = element.attrib.get('allowStop')
            result['dial'][path] = item
        except urllib.error.HTTPError as error:
            result['dial'][path] = {'status': error.code}
        except (OSError, ValueError, ET.ParseError) as error:
            result['dial'][path] = {'error_type': type(error).__name__}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.1.6')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = inspect(args.host)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
