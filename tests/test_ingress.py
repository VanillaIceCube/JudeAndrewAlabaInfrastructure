"""Run only disposable resources on the selected local/CI Docker daemon."""

import json
import gzip
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import random
import shutil
import ssl
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
OPENSSL = shutil.which("openssl") or "C:/Program Files/Git/usr/bin/openssl.exe"
STUB = """import json, os, time
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/api/slow-estimate-test/', '/mcp?slow-test=1'):
            time.sleep(65)
        if self.path == '/mcp?challenge-test=1':
            self.send_response(401)
            self.send_header('WWW-Authenticate','Bearer resource_metadata="https://'+self.headers['Host']+'/.well-known/oauth-protected-resource/mcp"')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','public, max-age=300')
        self.end_headers()
        self.wfile.write(json.dumps({'service':os.environ['SERVICE'],'path':self.path,
          'peer':self.client_address[0],'headers':dict(self.headers)}).encode())
HTTPServer(('0.0.0.0',int(os.environ['PORT'])),Handler).serve_forever()
"""


def docker(*args, check=True, env=None):
    return subprocess.run(
        ["docker", *args], check=check, capture_output=True, text=True, env=env
    )


class IngressTests(unittest.TestCase):
    def test_real_routes_dns_trust_logging_and_endpoint_reversal(self):
        prefix = "ingress-test-" + uuid.uuid4().hex[:10]
        names, networks = [], []
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            certs = target / "certs"
            certs.mkdir()
            (target / "openssl.cnf").write_text("[req]\ndistinguished_name=dn\n[dn]\n")
            subprocess.run(
                [
                    OPENSSL,
                    "req",
                    "-config",
                    str(target / "openssl.cnf"),
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                    "-keyout",
                    str(certs / "origin.key"),
                    "-out",
                    str(certs / "origin.pem"),
                ],
                check=True,
                capture_output=True,
            )
            env = dict(os.environ, INGRESS_CERTS_DIR=str(certs))
            config = json.loads(
                docker(
                    "compose",
                    "-f",
                    str(ROOT / "compose.yml"),
                    "config",
                    "--format",
                    "json",
                    env=env,
                ).stdout
            )
            proxy = config["services"]["proxy"]
            gzip_config = target / "nginx.conf"
            gzip_config.write_text((ROOT / "nginx/nginx.conf").read_text().replace(
                "http {", "http {\n  gzip on;\n  gzip_min_length 1;\n  gzip_types application/json;", 1))
            # The production address stays fixed; disposable networks use DHCP.
            proxy["networks"]["macromapper"] = None
            # Exercise the reusable include on a second enabled app without
            # activating a real production route or changing MacroMapper.
            vhosts = target / "vhosts"
            shutil.copytree(ROOT / "nginx/vhosts", vhosts)
            example = (ROOT / "docs/optional-mcp.conf.example").read_text()
            example = example.replace("app.example.com", "optional.judeandrewalaba.com")
            example = example.replace("example-backend", "optional-backend")
            example = example.replace("example-frontend", "optional-frontend")
            (vhosts / "optional.conf").write_text(example)
            for volume in proxy["volumes"]:
                if volume["target"] == "/etc/nginx/nginx.conf":
                    volume["source"] = str(gzip_config)
                if volume["target"] == "/etc/nginx/conf.d":
                    volume["source"] = str(vhosts)
            self.assertEqual(set(config["services"]), {"proxy"})
            self.assertEqual(
                proxy["networks"]["notoli_backend"]["ipv4_address"], "172.30.88.2"
            )
            self.assertTrue(all(n["external"] for n in config["networks"].values()))
            try:
                # Test-only subnet; never create the actual production networks.
                subnet = f"10.231.{random.randrange(1, 250)}"
                for key in config["networks"]:
                    name = prefix + "-" + key
                    extra = (
                        ["--internal", "--subnet", subnet + ".0/29"]
                        if key == "notoli_backend"
                        else []
                    )
                    docker("network", "create", *extra, name)
                    networks.append(name)
                    config["networks"][key]["name"] = name
                proxy["networks"]["notoli_backend"]["ipv4_address"] = subnet + ".2"
                proxy["ports"] = [
                    {
                        "target": 443,
                        "published": "0",
                        "host_ip": "127.0.0.1",
                        "protocol": "tcp",
                    }
                ]

                def start_stub(app, service):
                    name = prefix + "-" + app + "-" + service
                    if name not in names:
                        names.append(name)
                    key = (
                        (
                            "notoli_backend"
                            if service == "backend"
                            else "notoli_frontend"
                        )
                        if app == "notoli"
                        else "macromapper"
                    )
                    ip = (
                        ["--ip", subnet + ".3"]
                        if app == "notoli" and service == "backend"
                        else []
                    )
                    docker(
                        "run",
                        "-d",
                        "--name",
                        name,
                        "--network",
                        prefix + "-" + key,
                        *ip,
                        "--network-alias",
                        app + "-" + service,
                        "-e",
                        "SERVICE=" + app + "-" + service,
                        "-e",
                        "PORT=" + ("8000" if service == "backend" else "80"),
                        "python:3.12-alpine",
                        "python",
                        "-u",
                        "-c",
                        STUB,
                    )
                    return name

                start_stub("notoli", "backend")
                start_stub("notoli", "frontend")
                start_stub("optional", "backend")
                start_stub("optional", "frontend")
                definitions = {}
                for role in ("legacy", "replacement"):
                    proxy["container_name"] = prefix + "-" + role
                    config["name"] = prefix + "-" + role
                    path = target / (role + ".json")
                    path.write_text(json.dumps(config))
                    definitions[role] = path
                    names.append(prefix + "-" + role)

                def compose(role, *args, check=True):
                    return docker(
                        "compose",
                        "--project-directory",
                        str(ROOT),
                        "-p",
                        prefix + "-" + role,
                        "-f",
                        str(definitions[role]),
                        *args,
                        check=check,
                    )

                def request(role, app, path, expected=200):
                    name = prefix + "-" + role
                    port = (
                        docker("port", name, "443/tcp").stdout.strip().rsplit(":", 1)[1]
                    )
                    req = urllib.request.Request(
                        "https://127.0.0.1:" + port + path,
                        headers={
                            "Host": app + ".judeandrewalaba.com",
                            "X-Forwarded-For": "spoofed",
                            "X-Forwarded-Proto": "http",
                            "X-Forwarded-Host": "attacker.invalid",
                            "Forwarded": "host=attacker.invalid",
                        },
                    )
                    for _ in range(40):
                        try:
                            response = urllib.request.urlopen(
                                req, context=ssl._create_unverified_context(), timeout=2
                            )
                        except urllib.error.HTTPError as error:
                            response = error
                        except (OSError, urllib.error.URLError):
                            time.sleep(0.5)
                            continue
                        if response.status == expected:
                            body = response.read()
                            return response, json.loads(
                                body
                            ) if expected == 200 else body
                        response.close()
                        time.sleep(0.5)
                    self.fail(f"{app} {path} did not reach {expected}")

                compose("legacy", "up", "-d")
                docker("exec", prefix + "-legacy", "nginx", "-t")
                gzip_port = docker("port", prefix + "-legacy", "443/tcp").stdout.strip().rsplit(":", 1)[1]
                gzip_request = urllib.request.Request("https://127.0.0.1:" + gzip_port + "/api/gzip-fixture/",
                    headers={"Host": "notoli.judeandrewalaba.com", "Accept-Encoding": "gzip"})
                with urllib.request.urlopen(gzip_request, context=ssl._create_unverified_context(), timeout=5) as response:
                    self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
                    self.assertEqual(json.loads(gzip.decompress(response.read()))["service"], "notoli-backend")
                request("legacy", "macromapper", "/api/?code=NEVER_LOG_THIS", 502)
                for path in (
                    "/mcp?code=NEVER_LOG_THIS",
                    "/.well-known/oauth-authorization-server",
                    "/api/a%2Fb?x=a%2Bb",
                    "/auth/",
                    "/admin/",
                    "/static/admin/base.css",
                ):
                    response, body = request("legacy", "notoli", path)
                    self.assertEqual(body["path"], path)
                    self.assertEqual(body["service"], "notoli-backend")
                    self.assertEqual(body["peer"], subnet + ".2")
                    headers = body["headers"]
                    self.assertEqual(headers["Host"], "notoli.judeandrewalaba.com")
                    self.assertEqual(headers["X-Forwarded-Proto"], "https")
                    self.assertNotEqual(headers["X-Forwarded-For"], "spoofed")
                    self.assertNotIn("X-Forwarded-Host", headers)
                    self.assertNotIn("Forwarded", headers)
                    if path.startswith(("/mcp", "/api", "/auth", "/admin", "/.well-known")):
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                for app in ("notoli", "optional"):
                    for path in (
                        "/.well-known/oauth-protected-resource/mcp",
                        "/auth/mcp/authorize/?state=NEVER_LOG_THIS",
                        "/auth/mcp/token/", "/auth/mcp/revoke/",
                    ):
                        response, body = request("legacy", app, path)
                        self.assertEqual(body["service"], app + "-backend")
                        self.assertEqual(body["path"], path)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                    response, _ = request("legacy", app, "/mcp?challenge-test=1", 401)
                    self.assertIn(app + ".judeandrewalaba.com/.well-known/", response.headers["WWW-Authenticate"])
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(request("legacy", app, "/mcp/")[1]["service"], app + "-frontend")
                self.assertEqual(
                    request("legacy", "notoli", "/connections/authorize")[1]["service"],
                    "notoli-frontend",
                )

                start_stub("macromapper", "backend")
                start_stub("macromapper", "frontend")
                for path in (
                    "/mcp", "/mcp?code=NEVER_LOG_THIS", "/mcp/",
                    "/mcp/?state=NEVER_LOG_THIS", "/mcp/unknown?code=NEVER_LOG_THIS",
                    "/.well-known/", "/.well-known/oauth-protected-resource/mcp",
                    "/.well-known/oauth-protected-resource/mcp?resource=NEVER_LOG_THIS",
                    "/.well-known/oauth-authorization-server",
                    "/.well-known/unknown?code=NEVER_LOG_THIS",
                ):
                    with self.subTest(disabled_macromapper_path=path):
                        response, body = request("legacy", "macromapper", path, 404)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        self.assertIsNone(response.headers.get("WWW-Authenticate"))
                        self.assertNotIn(b"macromapper-frontend", body)
                for path in ("/connections/authorize", "/mcp-settings"):
                    self.assertEqual(request("legacy", "macromapper", path)[1]["service"], "macromapper-frontend")
                self.assertEqual(
                    request("legacy", "macromapper", "/api/notifications/")[1][
                        "service"
                    ],
                    "macromapper-backend",
                )
                # Real delayed upstream response exceeds Nginx's old 60s cap.
                port = (
                    docker("port", prefix + "-legacy", "443/tcp")
                    .stdout.strip()
                    .rsplit(":", 1)[1]
                )
                def slow_probe(app, path):
                    slow_request = urllib.request.Request(
                        "https://127.0.0.1:" + port + path,
                        headers={"Host": app + ".judeandrewalaba.com"},
                    )
                    with urllib.request.urlopen(
                        slow_request, context=ssl._create_unverified_context(), timeout=75
                    ) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(json.loads(response.read())["service"], app + "-backend")

                with ThreadPoolExecutor(max_workers=2) as pool:
                    probes = [
                        pool.submit(slow_probe, "optional", "/mcp?slow-test=1"),
                        pool.submit(slow_probe, "macromapper", "/api/slow-estimate-test/"),
                    ]
                    for probe in probes:
                        probe.result()
                self.assertIn(
                    "proxy_read_timeout 120s;",
                    docker("exec", prefix + "-legacy", "nginx", "-T").stdout,
                )
                backend = prefix + "-macromapper-backend"
                docker("rm", "-f", backend)
                request("legacy", "notoli", "/mcp")
                start_stub("macromapper", "backend")
                request("legacy", "macromapper", "/api/notifications/")
                self.assertNotIn(
                    "NEVER_LOG_THIS", docker("logs", prefix + "-legacy").stdout
                )
                self.assertNotIn(
                    "NEVER_LOG_THIS", docker("logs", prefix + "-legacy").stderr
                )

                # Real duplicate-address conflict and reversible proxy-only handoff.
                self.assertNotEqual(
                    compose("replacement", "up", "-d", check=False).returncode, 0
                )
                docker("rm", "-f", prefix + "-replacement", check=False)
                ids = {
                    n: docker("inspect", "--format", "{{.Id}}", n).stdout
                    for n in names
                    if n.endswith(("backend", "frontend"))
                }
                image_id = docker(
                    "inspect", "--format", "{{.Image}}", prefix + "-legacy"
                ).stdout.strip()
                docker("update", "--restart=no", prefix + "-legacy")
                docker("stop", prefix + "-legacy")
                docker("rm", prefix + "-legacy")
                compose(
                    "replacement", "up", "-d", "--no-deps", "--pull", "never", "proxy"
                )
                request("replacement", "notoli", "/mcp")
                request("replacement", "macromapper", "/auth/")
                docker("stop", prefix + "-replacement")
                docker("rm", prefix + "-replacement")
                compose("legacy", "up", "-d", "--no-deps", "--pull", "never", "proxy")
                request("legacy", "notoli", "/mcp")
                request("legacy", "macromapper", "/auth/")
                self.assertEqual(
                    docker(
                        "inspect", "--format", "{{.Image}}", prefix + "-legacy"
                    ).stdout.strip(),
                    image_id,
                )
                for name, ident in ids.items():
                    self.assertEqual(
                        docker("inspect", "--format", "{{.Id}}", name).stdout, ident
                    )
            finally:
                for name in reversed(names):
                    docker("rm", "-f", name, check=False)
                for name in reversed(networks):
                    docker("network", "rm", name, check=False)


if __name__ == "__main__":
    unittest.main()
