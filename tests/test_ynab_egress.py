"""Exact-run, network-isolated CONNECT/real-stdio proof; run by gateway acceptance.

No live YNAB endpoint: the only API alias is a disposable TLS fixture. The one
positive private-IP exception exists only in a temporary test copy of the ACL.
"""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from test_ingress import docker, OPENSSL, ROOT

LABEL = "infrastructure.ynab.egress.fixture"
SQUID = os.environ.get("YNAB_EGRESS_TEST_IMAGE")
PYTHON = "python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487"
IDENTITY = os.environ.get("YNAB_EGRESS_TEST_ID", "ynab-egress-test-" + uuid.uuid4().hex)
IMAGE = os.environ.get("YNAB_GATEWAY_TEST_IMAGE")
SECRET = os.environ.get("YNAB_GATEWAY_TEST_SECRET")
API = """import ssl,json
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  assert self.path=='/v1/plans'
  assert self.headers.get('Authorization')=='Bearer synthetic-fixture-only'
  data=json.dumps({'data':{'plans':[{'id':'fixture-budget','name':'Synthetic TLS budget'}]}}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=HTTPServer(('0.0.0.0',443),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain('/fixture/ca.pem','/fixture/key.pem')
server.socket=context.wrap_socket(server.socket,server_side=True);server.serve_forever()
"""


def cleanup(identity):
    if not re.fullmatch(r"ynab-egress-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid egress fixture identity")
    for kind in ("container", "network"):
        ids = docker(kind, "ls", "-aq" if kind == "container" else "-q", "--filter", "label=" + LABEL + "=" + identity).stdout.split()
        if ids:
            docker(kind, "rm", *( ["-f"] if kind == "container" else []), *ids, check=False)


@unittest.skipUnless(IMAGE and SECRET and SQUID, "Run through services/ynab-gateway/run_tests.py with its synthetic images/volume")
class EgressTests(unittest.TestCase):
    def test_fixed_connect_acl_and_real_upstream_use_the_proxy_without_direct_egress(self):
        if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}:fixture", IMAGE):
            raise ValueError("Use an exact disposable gateway fixture image")
        if SQUID != IMAGE.removesuffix(":fixture") + ":egress-fixture":
            raise ValueError("Use the matching disposable egress image")
        if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}-secret", SECRET):
            raise ValueError("Use an exact synthetic fixture volume")
        if not re.fullmatch(r"ynab-egress-test-[a-f0-9]{32}", IDENTITY):
            raise ValueError("Invalid fixture identity")
        label = LABEL + "=" + IDENTITY
        network = IDENTITY + "-private"
        api_network = IDENTITY + "-api-private"
        proxy = IDENTITY + "-proxy"
        source = (ROOT / "services/ynab-gateway/squid.conf").read_bytes()
        with tempfile.TemporaryDirectory(prefix=IDENTITY) as directory:
            temp = Path(directory)
            (temp / "openssl.cnf").write_text("[req]\ndistinguished_name=dn\n[dn]\n")
            subprocess.run([OPENSSL, "req", "-config", str(temp / "openssl.cnf"), "-x509", "-newkey", "rsa:2048",
                            "-nodes", "-days", "1", "-subj", "/CN=api.ynab.com", "-addext", "subjectAltName=DNS:api.ynab.com",
                            "-keyout", str(temp / "key.pem"), "-out", str(temp / "ca.pem")], check=True, capture_output=True, timeout=30)
            policy = temp / "squid.conf"
            policy.write_bytes(source)
            try:
                docker("network", "create", "--internal", "--label", label, network)
                docker("network", "create", "--internal", "--label", label, api_network)
                docker("run", "-d", "--label", label, "--name", IDENTITY + "-api", "--network", api_network,
                       "--network-alias", "api.ynab.com", "--read-only", "--mount",
                       "type=bind,source=" + str(temp) + ",target=/fixture,readonly", PYTHON, "python", "-c", API)
                def start_proxy(address=None):
                    docker("run", "-d", "--label", label, "--name", proxy, "--network", network,
                           "--network-alias", "ynab-egress", "--user", "13:13", "--read-only", "--cap-drop", "ALL",
                           "--security-opt", "no-new-privileges", "--pids-limit", "32", "--memory", "128m",
                           "--tmpfs", "/tmp:rw,noexec,nosuid,size=8m,uid=13,gid=13,mode=0700", "--mount",
                           "type=bind,source=" + str(policy) + ",target=/etc/squid/squid.conf,readonly",
                           *(["--add-host", "api.ynab.com:" + address] if address else []),
                           "--entrypoint", "/usr/sbin/squid", SQUID,
                           "-N", "-f", "/etc/squid/squid.conf", "-d0")
                    docker("network", "connect", api_network, proxy)
                    ready = "import socket,time\nfor attempt in range(40):\n try:\n  socket.create_connection(('ynab-egress',3128),timeout=1).close();break\n except OSError:time.sleep(0.1)\nelse:raise SystemExit('Fixture proxy did not start')"
                    docker("run", "--rm", "--label", label, "--network", network, "--read-only", "--cap-drop", "ALL",
                           PYTHON, "python", "-c", ready)
                def status(request):
                    probe = "import socket,sys\nwith socket.create_connection(('ynab-egress',3128),timeout=8) as stream:\n stream.sendall(sys.argv[1].encode());print(int(stream.recv(1024).split(b' ')[1]))"
                    return int(docker("run", "--rm", "--label", label, "--network", network, "--read-only", "--cap-drop", "ALL",
                                      PYTHON, "python", "-c", probe, request).stdout.strip())
                start_proxy()
                for request in ("CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n",
                                "CONNECT api.ynab.com:80 HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n",
                                "CONNECT 169.254.169.254:443 HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n",
                                "CONNECT api.ynab.com.evil.example:443 HTTP/1.1\r\nHost: api.ynab.com.evil.example\r\n\r\n",
                                "CONNECT evil.api.ynab.com:443 HTTP/1.1\r\nHost: evil.api.ynab.com\r\n\r\n",
                                "GET http://api.ynab.com/v1/plans HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n",
                                "CONNECT api.ynab.com:443 HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n"):
                    self.assertEqual(status(request), 403)
                # Production ACL must deny a private resolved address, even for the exact name.
                api = json.loads(docker("inspect", IDENTITY + "-api").stdout)[0]
                api_ip = api["NetworkSettings"]["Networks"][api_network]["IPAddress"]
                direct = "import socket,sys\ntry: socket.create_connection((sys.argv[1],443),timeout=1)\nexcept OSError: pass\nelse: raise SystemExit('Direct fixture API access bypassed isolation')"
                docker("run", "--rm", "--label", label, "--network", network, "--read-only", "--cap-drop", "ALL",
                       PYTHON, "python", "-c", direct, api_ip)
                for reserved in ("192.0.2.2", "198.51.100.2", "203.0.113.2", "3fff::1", "100:0:0:1::1"):
                    docker("rm", "-f", proxy)
                    start_proxy(reserved)
                    self.assertEqual(status("CONNECT api.ynab.com:443 HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n"), 403)
                # A public-address control must get a connection failure rather
                # than ACL403, proving the host override affected resolution.
                # Both networks are internal: no actual external connection can occur.
                docker("rm", "-f", proxy)
                start_proxy("8.8.8.8")
                self.assertEqual(status("CONNECT api.ynab.com:443 HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n"), 503)
                exception = "acl fixture_destination dst " + api_ip + "/32\n"
                fixture_policy = source.decode().replace("http_access deny private_dst", exception + "http_access deny private_dst !fixture_destination")
                docker("rm", "-f", proxy)
                policy.write_text(fixture_policy)
                start_proxy()
                self.assertEqual(status("CONNECT api.ynab.com:443 HTTP/1.1\r\nHost: api.ynab.com\r\n\r\n"), 200)
                # Read the actual compiled image's fixed child command/environment.
                inspect_child = "import sys,json;sys.path.insert(0,'/gateway');from gateway import child_transport;t=child_transport();print(json.dumps({'command':t.command,'args':t.args,'env':t.env}))"
                child = json.loads(docker("run", "--rm", "--label", label, "--network", "none", "--entrypoint",
                                         "/usr/local/bin/python", IMAGE, "-c", inspect_child).stdout)
                self.assertEqual(child["env"]["HTTPS_PROXY"], "http://ynab-egress:3128")
                self.assertEqual(child["env"]["NO_PROXY"], "")
                self.assertIn("--use-env-proxy", child["args"])
                args = ["docker", "run", "--rm", "-i", "--label", label, "--name", IDENTITY + "-stdio",
                        "--network", network, "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--pids-limit", "32", "--memory", "256m", "--mount",
                        "type=volume,source=" + SECRET + ",target=/run/secrets,readonly", "--mount",
                        "type=bind,source=" + str(temp / "ca.pem") + ",target=/fixture-ca.pem,readonly",
                        "-e", "NODE_EXTRA_CA_CERTS=/fixture-ca.pem"]
                for key, value in child["env"].items():
                    args += ["-e", key + "=" + value]
                args += ["--entrypoint", child["command"], IMAGE, *child["args"]]
                replies = queue.Queue()
                process = subprocess.Popen(args, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                def read_replies():
                    for line in process.stdout:
                        replies.put(json.loads(line))
                reader = threading.Thread(target=read_replies, daemon=True)
                reader.start()
                def rpc(payload):
                    process.stdin.write(json.dumps(payload) + "\n")
                    process.stdin.flush()
                    if "id" in payload:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            reply = replies.get(timeout=max(0.01, deadline - time.monotonic()))
                            if reply.get("id") == payload["id"]:
                                return reply
                        self.fail("Fixture stdio reply deadline exceeded")
                    return None
                try:
                    initialized = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "egress-fixture", "version": "1"}}})
                    self.assertIn("result", initialized)
                    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
                    result = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_budgets", "arguments": {}}})
                    self.assertFalse(result["result"].get("isError"), result)
                    self.assertIn("Synthetic TLS budget", json.dumps(result))
                    process.stdin.close()
                    process.wait(timeout=10)
                    self.assertEqual(process.returncode, 0)
                finally:
                    docker("rm", "-f", IDENTITY + "-stdio", check=False)
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
                    reader.join(timeout=2)
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        if pipe is not None and not pipe.closed:
                            pipe.close()
                # No public-egress network exists in the fixture. Direct internet
                # cannot be the positive result's path; Node used the CONNECT proxy.
                self.assertTrue(json.loads(docker("network", "inspect", network).stdout)[0]["Internal"])
                self.assertTrue(json.loads(docker("network", "inspect", api_network).stdout)[0]["Internal"])
                self.assertEqual((ROOT / "services/ynab-gateway/squid.conf").read_bytes(), source)
            finally:
                cleanup(IDENTITY)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--cleanup":
        cleanup(sys.argv[2])
    else:
        unittest.main(verbosity=2)
