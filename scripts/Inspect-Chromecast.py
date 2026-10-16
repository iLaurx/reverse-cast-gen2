"""Consultas HTTP de lectura y conectividad al dispositivo seleccionado."""
import argparse
import datetime
import ipaddress
import json
import pathlib
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


def inspect(host):
    ipaddress.IPv4Address(host)
    result = {
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host": host,
        "ports": {},
        "http": {},
    }
    for port in (8008, 8009, 8443):
        try:
            with socket.create_connection((host, port), timeout=3):
                result["ports"][str(port)] = "open"
        except OSError as error:
            result["ports"][str(port)] = str(error)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for endpoint in ("/ssdp/device-desc.xml", "/setup/eureka_info"):
        try:
            with opener.open(f"http://{host}:8008{endpoint}", timeout=8) as response:
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise ValueError("Respuesta mayor a 1 MiB")
                item = {"status": response.status}
                if endpoint.endswith(".xml"):
                    root = ET.fromstring(body)
                    ns = {"d": "urn:schemas-upnp-org:device-1-0"}
                    for key in ("manufacturer", "modelName", "modelNumber"):
                        item[key] = root.findtext(f".//d:{key}", namespaces=ns)
                else:
                    info = json.loads(body)
                    for key in ("build_version", "cast_build_revision", "connected", "version"):
                        item[key] = info.get(key)
                result["http"][endpoint] = item
        except (OSError, ValueError, ET.ParseError) as error:
            result["http"][endpoint] = {"error": str(error)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.6")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    report = inspect(args.host)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)
    raise SystemExit(0 if all("error" not in value for value in report["http"].values()) else 1)
