"""Actual optional authorization vhost: exact paths, cookies, DNS and containment."""
import http.client
import json
import os
from pathlib import Path
import random
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from test_ingress import docker, OPENSSL, ROOT, STUB
from test_ynab_ingress import PYTHON
sys.path.insert(0, str(ROOT / "scripts"))
import gateway_profile

AUTH = "auth.judeandrewalaba.com"
AUTH_STUB = """from http.server import BaseHTTPRequestHandler,HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):self.respond()
 def do_POST(self):self.respond()
 def respond(self):
  body=self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()
  self.send_response(200);self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','public,max-age=999');self.send_header('Set-Cookie','session=synthetic; Secure; HttpOnly');self.end_headers()
  self.wfile.write(json.dumps({'path':self.path,'headers':dict(self.headers),'body':body}).encode())
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
"""


class AuthorizationIngressTests(unittest.TestCase):
    def test_exact_auth_routes_forward_secure_cookies_preserve_apps_and_disable(self):
        prefix = "auth-ingress-test-" + uuid.uuid4().hex[:10]
        containers, networks = [], []
        with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
            root = Path(temporary)
            certs = root / "certs"
            certs.mkdir()
            cnf = root / "openssl.cnf"
            cnf.write_text("[req]\ndistinguished_name=dn\n[dn]\n")
            subprocess.run([OPENSSL, "req", "-config", str(cnf), "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "1", "-subj", "/CN=" + AUTH,
                "-addext", "subjectAltName=DNS:" + AUTH + ",DNS:notoli.judeandrewalaba.com,DNS:macromapper.judeandrewalaba.com",
                "-keyout", str(certs / "origin.key"), "-out", str(certs / "origin.pem")],
                check=True, capture_output=True, timeout=30)
            env = dict(os.environ, INGRESS_CERTS_DIR=str(certs))
            model = json.loads(docker("compose", "-f", str(ROOT / "compose.yml"), "config", "--format", "json", env=env).stdout)
            gateway_profile.apply(model, "enabled", auth=True)
            vhosts = root / "vhosts"
            shutil.copytree(ROOT / "nginx/vhosts", vhosts)
            shutil.copyfile(ROOT / "nginx/optional/mcp-auth/zz-mcp-auth.conf", vhosts / "zz-mcp-auth.conf")
            proxy = model["services"]["proxy"]
            for volume in proxy["volumes"]:
                if volume["target"] == "/etc/nginx/conf.d":
                    volume["source"] = str(vhosts)
            suffix = random.randrange(1, 250)
            addresses = {"notoli_backend": f"10.237.{suffix}", "mcp_auth_route": f"10.238.{suffix}", "macromapper": f"10.240.{suffix}"}
            proxy_name = prefix + "-proxy"
            proxy["container_name"], proxy["restart"] = proxy_name, "no"
            proxy["ports"] = [{"target": 443, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp"}]
            definition = root / "compose.json"
            try:
                for key in model["networks"]:
                    name = prefix + "-" + key
                    extra = ["--internal", "--subnet", addresses[key] + ".0/29"] if key in addresses else []
                    docker("network", "create", *extra, name)
                    networks.append(name)
                    model["networks"][key]["name"] = name
                    if key in addresses:
                        proxy["networks"][key]["ipv4_address"] = addresses[key] + (".3" if key == "macromapper" else ".2")
                network_ids = {name: json.loads(docker("network", "inspect", name).stdout)[0]["Id"] for name in networks}
                companions = {}
                for app in ("notoli", "macromapper"):
                    for role in ("backend", "frontend"):
                        key = ("notoli_backend" if role == "backend" else "notoli_frontend") if app == "notoli" else "macromapper"
                        name = prefix + "-" + app + "-" + role
                        containers.append(name)
                        extra = (["--ip", addresses[key] + ".3"] if key == "notoli_backend" else
                                 ["--ip", addresses[key] + (".2" if role == "backend" else ".4")] if key == "macromapper" else [])
                        docker("run", "-d", "--name", name, "--network", prefix + "-" + key, *extra,
                            "--network-alias", app + "-" + role, "-e", "SERVICE=" + app + "-" + role,
                            "-e", "PORT=" + ("8000" if role == "backend" else "80"), PYTHON, "python", "-u", "-c", STUB)
                        companions[name] = json.loads(docker("inspect", name).stdout)[0]["Id"]
                definition.write_text(json.dumps(model))
                containers.append(proxy_name)
                docker("compose", "-p", prefix, "-f", str(definition), "up", "-d", "--no-deps", "proxy")
                syntax = docker("exec", proxy_name, "nginx", "-t", check=False)
                logs = docker("logs", proxy_name, check=False)
                self.assertEqual(syntax.returncode, 0, syntax.stderr + logs.stdout + logs.stderr)
                port = int(docker("port", proxy_name, "443/tcp").stdout.strip().rsplit(":", 1)[1])
                context = ssl.create_default_context(cafile=str(certs / "origin.pem"))

                def request(host, path, expected=200, method="GET", body=None, extra=None):
                    headers = {"X-Forwarded-Proto": "http", "X-Forwarded-For": "untrusted", "Forwarded": "host=evil",
                               "X-Forwarded-Host": "evil", "X-API-Key": "private-sentinel", "X-Forwarded-User": "evil",
                               "CF-Connecting-IP": "evil", "Cookie": "session=synthetic",
                               "Authorization": "Basic synthetic-client"}
                    headers.update(extra or {})
                    deadline, last = time.monotonic() + 20, "no response"
                    while time.monotonic() < deadline:
                        connection = http.client.HTTPSConnection(host, timeout=3, context=context)
                        connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
                            ("127.0.0.1", port), timeout, source_address)
                        try:
                            connection.request(method, path, body=body, headers=headers)
                            response = connection.getresponse()
                            data = response.read()
                            last = str(response.status)
                            if response.status == expected:
                                return dict(response.getheaders()), data
                        except OSError as error:
                            last = type(error).__name__
                        finally:
                            connection.close()
                        time.sleep(0.3)
                    self.fail(f"Fixture route expected {expected}; last result {last}")

                request(AUTH, "/.well-known/oauth-authorization-server", 502)
                server = prefix + "-authorization"
                containers.append(server)
                docker("run", "-d", "--name", server, "--network", prefix + "-mcp_auth_route", "--network-alias", "mcp-auth",
                       PYTHON, "python", "-B", "-c", AUTH_STUB)
                headers, data = request(AUTH, "/accounts/login/?next=%2Fo%2Fauthorize%2F")
                received = json.loads(data)["headers"]
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertIn("Secure", headers["Set-Cookie"])
                self.assertEqual(received["Cookie"], "session=synthetic")
                self.assertEqual(received["Authorization"], "Basic synthetic-client")
                self.assertEqual(received["Host"], AUTH)
                self.assertEqual(received["X-Forwarded-Proto"], "https")
                for protocol in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
                    context.minimum_version = protocol
                    context.maximum_version = protocol
                    request(AUTH, "/accounts/login/")
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
                self.assertNotEqual(received["X-Forwarded-For"], "untrusted")
                for header in ("Forwarded", "X-Forwarded-Host", "X-API-Key", "X-Forwarded-User", "CF-Connecting-IP"):
                    self.assertNotIn(header, received)
                _, data = request(AUTH, "/o/token/", method="POST", body=b"code=synthetic&resource=fixed")
                self.assertEqual(json.loads(data)["body"], "code=synthetic&resource=fixed")
                for path in ("/", "/o/token", "/o/token/extra", "/o/%74oken/", "/admin/", "/health/ready", "/o/applications/register/", "/.well-known/openid-configuration"):
                    request(AUTH, path, 404)
                request(AUTH, "/o/token/", 413, method="POST", body=b"a" * (33 * 1024))
                for host in ("notoli.judeandrewalaba.com", "macromapper.judeandrewalaba.com"):
                    request(host, "/api/")
                docker("rm", "-f", server)
                request(AUTH, "/o/token/", 502, method="POST", body=b"fixture")
                shutil.copyfile(ROOT / "nginx/optional/mcp-auth-disabled/zz-mcp-auth.conf", vhosts / "zz-mcp-auth.conf")
                docker("exec", proxy_name, "nginx", "-t")
                docker("exec", proxy_name, "nginx", "-s", "reload")
                for path in ("/o/authorize/", "/o/token/", "/o/introspect/", "/accounts/login/", "/.well-known/oauth-authorization-server"):
                    headers, _ = request(AUTH, path, 410)
                    self.assertEqual(headers["Cache-Control"], "no-store")
                for host in ("notoli.judeandrewalaba.com", "macromapper.judeandrewalaba.com"):
                    request(host, "/api/")
                self.assertEqual({name: json.loads(docker("inspect", name).stdout)[0]["Id"] for name in companions}, companions)
                self.assertEqual({name: json.loads(docker("network", "inspect", name).stdout)[0]["Id"] for name in networks}, network_ids)
                logs = docker("logs", proxy_name)
                self.assertNotIn("private-sentinel", logs.stdout + logs.stderr)
            finally:
                for name in reversed(containers):
                    docker("rm", "-f", name, check=False)
                for name in reversed(networks):
                    docker("network", "rm", name, check=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
