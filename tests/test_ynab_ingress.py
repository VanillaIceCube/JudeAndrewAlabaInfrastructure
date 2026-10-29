"""Optional YNAB ingress on a disposable daemon; no account APIs or live runbook."""
import json
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
from test_ingress import docker, OPENSSL, ROOT, STUB

PYTHON = "python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487"
YNAB_STUB = """from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json,time
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
  self.wfile.write(json.dumps({'resource':'https://ynab.judeandrewalaba.com/mcp'}).encode())
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length','0')))
  if self.headers.get('Authorization')!='Bearer synthetic-fixture':
   self.send_response(401);self.send_header('WWW-Authenticate','Bearer resource_metadata="https://ynab.judeandrewalaba.com/.well-known/oauth-protected-resource/mcp"');self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','public,max-age=300');self.end_headers()
  if self.headers.get('X-Fixture-Stream')=='1':
   self.wfile.write(b'{"phase":');self.wfile.flush();time.sleep(1);self.wfile.write(b'"done"}')
  else:self.wfile.write(json.dumps({'service':'ynab','headers':dict(self.headers)}).encode())
ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
"""


class YNABIngressTests(unittest.TestCase):
    def test_optional_route_dns_streaming_isolation_and_disable_rollback(self):
        identity = "ynab-ingress-test-" + uuid.uuid4().hex[:12]
        containers, networks = [], []
        with tempfile.TemporaryDirectory(prefix=identity) as directory:
            temp = Path(directory)
            certs = temp / "certs"
            certs.mkdir()
            config_file = temp / "openssl.cnf"
            config_file.write_text("[req]\ndistinguished_name=dn\n[dn]\n")
            subprocess.run([OPENSSL, "req", "-config", str(config_file), "-x509", "-newkey", "rsa:2048",
                            "-nodes", "-days", "1", "-subj", "/CN=localhost", "-keyout", str(certs / "origin.key"),
                            "-out", str(certs / "origin.pem")], check=True, capture_output=True, timeout=30)
            env = dict(os.environ, INGRESS_CERTS_DIR=str(certs))
            base = json.loads(docker("compose", "-f", str(ROOT / "compose.yml"), "config", "--format", "json", env=env).stdout)
            config = json.loads(docker("compose", "-f", str(ROOT / "compose.yml"), "-f", str(ROOT / "compose.ynab.yml"),
                                      "config", "--format", "json", env=env).stdout)
            proxy = config["services"]["proxy"]
            self.assertEqual({k: v for k, v in proxy["networks"].items() if k != "ynab_route"}, base["services"]["proxy"]["networks"])
            self.assertEqual({k: v for k, v in config["networks"].items() if k != "ynab_route"}, base["networks"])
            self.assertEqual(proxy["image"], base["services"]["proxy"]["image"])
            self.assertNotIn("ynab_route", base["networks"])
            optional = temp / "optional"
            shutil.copytree(ROOT / "nginx/optional/ynab", optional)
            for volume in proxy["volumes"]:
                if volume["target"] == "/etc/nginx/conf.d":
                    volume["source"] = str(optional)
            suffix = random.randrange(1, 250)
            addresses = {"notoli_backend": f"10.233.{suffix}", "ynab_route": f"10.234.{suffix}"}
            project = identity
            proxy_name = identity + "-proxy"
            proxy["container_name"] = proxy_name
            proxy["restart"] = "no"
            proxy["ports"] = [{"target": 443, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp"}]
            definition = temp / "compose.json"
            config["name"] = project
            try:
                for key in config["networks"]:
                    name = identity + "-" + key
                    extra = ["--internal", "--subnet", addresses[key] + ".0/29"] if key in addresses else []
                    docker("network", "create", *extra, name)
                    networks.append(name)
                    config["networks"][key]["name"] = name
                    if key in addresses:
                        proxy["networks"][key]["ipv4_address"] = addresses[key] + ".2"
                before_networks = {name: json.loads(docker("network", "inspect", name).stdout)[0]["Id"] for name in networks}
                companion_ids = {}
                for app in ("notoli", "macromapper"):
                    for service in ("backend", "frontend"):
                        name = identity + "-" + app + "-" + service
                        key = ("notoli_backend" if service == "backend" else "notoli_frontend") if app == "notoli" else "macromapper"
                        extra = ["--ip", addresses[key] + ".3"] if key == "notoli_backend" else []
                        containers.append(name)
                        docker("run", "-d", "--name", name, "--network", identity + "-" + key, *extra,
                               "--network-alias", app + "-" + service, "-e", "SERVICE=" + app + "-" + service,
                               "-e", "PORT=" + ("8000" if service == "backend" else "80"), PYTHON, "python", "-u", "-c", STUB)
                        companion_ids[name] = json.loads(docker("inspect", name).stdout)[0]["Id"]
                definition.write_text(json.dumps(config))
                containers.append(proxy_name)
                docker("compose", "-p", project, "-f", str(definition), "up", "-d", "--no-deps", "proxy")
                docker("exec", proxy_name, "nginx", "-t")
                proxy_id = json.loads(docker("inspect", proxy_name).stdout)[0]["Id"]
                port = docker("port", proxy_name, "443/tcp").stdout.strip().rsplit(":", 1)[1]
                def request(host, path, *, method="GET", auth=False, expected=200, extra=None):
                    headers = {"Host": host, "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "http",
                               "X-Forwarded-For": "evil", "Forwarded": "host=evil", "X-Forwarded-User": "evil",
                               "X-API-Key": "private-sentinel", "Cookie": "private-sentinel", "CF-Connecting-IP": "evil"}
                    if auth:
                        headers["Authorization"] = "Bearer synthetic-fixture"
                    headers.update(extra or {})
                    req = urllib.request.Request("https://127.0.0.1:" + port + path, headers=headers,
                                                 data=b"{}" if method == "POST" else None, method=method)
                    for _ in range(45):
                        try:
                            try:
                                response = urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=3)
                            except urllib.error.HTTPError as error:
                                response = error
                            if response.status == expected:
                                return response, response.read()
                            response.close()
                        except (OSError, urllib.error.URLError):
                            pass
                        time.sleep(0.3)
                    self.fail(f"Fixture {host} {path} did not return {expected}")
                domain = "ynab.judeandrewalaba.com"
                request(domain, "/mcp", method="POST", expected=502)
                request("notoli.judeandrewalaba.com", "/api/")
                request("macromapper.judeandrewalaba.com", "/api/")
                backend_name = identity + "-ynab"
                def start_backend():
                    if backend_name not in containers:
                        containers.append(backend_name)
                    docker("run", "-d", "--name", backend_name, "--network", identity + "-ynab_route",
                           "--network-alias", "ynab-mcp-gateway", PYTHON, "python", "-u", "-c", YNAB_STUB)
                    return json.loads(docker("inspect", backend_name).stdout)[0]
                old_backend = start_backend()
                response, _ = request(domain, "/mcp", method="POST", expected=401)
                self.assertIn("/.well-known/oauth-protected-resource/mcp", response.headers["WWW-Authenticate"])
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                response, body = request(domain, "/mcp", method="POST", auth=True)
                actual_headers = json.loads(body)["headers"]
                self.assertEqual(actual_headers["Host"], domain)
                self.assertEqual(actual_headers["X-Forwarded-Proto"], "https")
                self.assertNotEqual(actual_headers["X-Forwarded-For"], "evil")
                for forbidden in ("X-Forwarded-Host", "Forwarded", "X-Forwarded-User", "X-API-Key", "Cookie", "CF-Connecting-IP"):
                    self.assertNotIn(forbidden, actual_headers)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                _, metadata = request(domain, "/.well-known/oauth-protected-resource/mcp")
                self.assertEqual(json.loads(metadata)["resource"], "https://" + domain + "/mcp")
                for path in ("/mcp/", "/%6dcp", "/mcp?code=private-sentinel", "/health/ready", "/auth/mcp/authorize", "/.well-known/oauth-authorization-server"):
                    request(domain, path, method="POST", auth=True, expected=404)
                unknown = json.loads(request("unknown.fixture.example", "/")[1])
                self.assertEqual(unknown["service"], "notoli-frontend")
                stream = urllib.request.Request("https://127.0.0.1:" + port + "/mcp", data=b"{}",
                    headers={"Host": domain, "Authorization": "Bearer synthetic-fixture", "X-Fixture-Stream": "1"})
                started = time.monotonic()
                with urllib.request.urlopen(stream, context=ssl._create_unverified_context(), timeout=3) as response:
                    self.assertEqual(response.read(1), b"{")
                    self.assertLess(time.monotonic() - started, 0.8)
                    self.assertEqual(json.loads(b"{" + response.read())["phase"], "done")
                docker("rm", "-f", backend_name)
                request(domain, "/mcp", method="POST", expected=502)
                request("notoli.judeandrewalaba.com", "/api/")
                request("macromapper.judeandrewalaba.com", "/api/")
                holder = identity + "-holder"
                containers.append(holder)
                old_ip = old_backend["NetworkSettings"]["Networks"][identity + "-ynab_route"]["IPAddress"]
                docker("run", "-d", "--name", holder, "--network", identity + "-ynab_route", "--ip", old_ip,
                       PYTHON, "python", "-c", "import time; time.sleep(300)")
                replacement = start_backend()
                self.assertNotEqual(replacement["NetworkSettings"]["Networks"][identity + "-ynab_route"]["IPAddress"], old_ip)
                request(domain, "/mcp", method="POST", expected=401)
                self.assertEqual(json.loads(docker("inspect", proxy_name).stdout)[0]["Id"], proxy_id)
                shutil.copyfile(ROOT / "nginx/optional/ynab-disabled/zz-ynab.conf", optional / "zz-ynab.conf")
                docker("exec", proxy_name, "nginx", "-t")
                docker("exec", proxy_name, "nginx", "-s", "reload")
                request(domain, "/mcp", method="POST", expected=410)
                request("notoli.judeandrewalaba.com", "/api/")
                request("macromapper.judeandrewalaba.com", "/api/")
                for name, expected_id in companion_ids.items():
                    self.assertEqual(json.loads(docker("inspect", name).stdout)[0]["Id"], expected_id)
                for name, expected_id in before_networks.items():
                    self.assertEqual(json.loads(docker("network", "inspect", name).stdout)[0]["Id"], expected_id)
                logs = docker("logs", proxy_name)
                self.assertNotIn("private-sentinel", logs.stdout + logs.stderr)
            finally:
                for name in reversed(containers):
                    docker("rm", "-f", name, check=False)
                for name in reversed(networks):
                    docker("network", "rm", name, check=False)


if __name__ == "__main__":
    unittest.main()
