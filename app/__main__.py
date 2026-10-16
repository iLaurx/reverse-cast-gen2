import argparse
import ipaddress
import logging
import os
import uvicorn


def main():
    parser = argparse.ArgumentParser(description='Panel local para Chromecast; un solo proceso.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if not address.is_loopback:
        if len(os.environ.get('CAST_WEB_TOKEN', '')) < 20:
            parser.error('Para LAN configura CAST_WEB_TOKEN con al menos 20 caracteres.')
        if not os.environ.get('CAST_WEB_HOSTS'):
            parser.error('Para LAN configura CAST_WEB_HOSTS con la IP privada de esta PC.')
        if not (address.is_private or address.is_unspecified):
            parser.error('Solo se admite localhost o la red privada.')
    for name in ('pychromecast','casttube','urllib3'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    uvicorn.run('app.web:create_app', factory=True, host=args.host, port=args.port, workers=1, access_log=False)

if __name__ == '__main__':
    main()
