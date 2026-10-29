"""Bounded local/CI daemon fixture with exact-run cleanup; never a deployment."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
import build as builder

ROOT = Path(__file__).resolve().parents[2]
LABEL = "infrastructure.ynab.gateway.fixture"


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=240, **kwargs)


def cleanup(identity):
    if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid fixture identity")
    run([sys.executable, str(ROOT / "tests/test_ynab_egress.py"), "--cleanup",
         identity.replace("ynab-gateway-test-", "ynab-egress-test-")])
    containers = subprocess.check_output(["docker", "ps", "-aq", "--filter",
                                          "label=" + LABEL + "=" + identity], text=True).split()
    if containers:
        subprocess.run(["docker", "rm", "-f", *containers], check=False, timeout=30)
    subprocess.run(["docker", "volume", "rm", identity + "-secret"], check=False, timeout=30)
    subprocess.run(["docker", "image", "rm", identity + ":fixture"], check=False, timeout=30)


PREPARE = """
from pathlib import Path
import json, os
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk, jwt
import time
pair=RSAKeyPair.generate()
root=Path('/run/secrets')
config={'issuer':'https://issuer.fixture.example','owner':'owner-fixture','clients':['client-fixture']}
for name,value in [('gateway_identity.json',json.dumps(config)),('oauth_public_key.pem',pair.public_key),('ynab_api_token','synthetic-fixture-only')]:
 p=root/name; p.write_text(value); p.chmod(0o400); os.chown(p,65532,65532)
claims={'iss':config['issuer'],'sub':config['owner'],'client_id':'client-fixture','aud':'https://ynab.judeandrewalaba.com/mcp','iat':int(time.time()),'exp':int(time.time())+300,'scope':'ynab:read'}
print(jwt.encode({'alg':'RS256','typ':'at+jwt'},claims,jwk.import_key(pair.private_key.get_secret_value(),'RSA'),algorithms=['RS256']))
"""

PROBE = """
import json, sys, time, urllib.request, urllib.error
token=sys.stdin.read().strip()
base='http://127.0.0.1:8000'
def request(path,body=None,authorized=False,sid=None):
 headers={'Host':'ynab.judeandrewalaba.com','Accept':'application/json, text/event-stream'}
 if authorized: headers['Authorization']='Bearer '+token
 if sid: headers.update({'MCP-Session-ID':sid,'MCP-Protocol-Version':'2025-11-25'})
 if body is not None: headers['Content-Type']='application/json'
 req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 try: response=urllib.request.urlopen(req,timeout=10)
 except urllib.error.HTTPError as error: response=error
 data=response.read()
 return response.status, response.headers, json.loads(data) if data else None
for attempt in range(30):
 try:
  if request('/health/ready')[0]==200: break
 except (OSError,urllib.error.URLError): pass
 time.sleep(0.2)
else: raise SystemExit('Production entrypoint readiness failed')
assert request('/mcp',{})[0]==401
status,headers,payload=request('/mcp',{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'entrypoint-fixture','version':'1'}}},True)
assert status==200 and payload['result']['protocolVersion']=='2025-11-25'
sid=headers['MCP-Session-ID']
assert request('/mcp',{'jsonrpc':'2.0','method':'notifications/initialized'},True,sid)[0]==202
status,headers,payload=request('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/list'},True,sid)
names={tool['name'] for tool in payload['result']['tools']}
assert status==200 and 'list_budgets' in names and 'create_payee' not in names
assert request('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'create_payee','arguments':{}}},True,sid)[0]==403
print('Production ENTRYPOINT: private readiness, real Node policy/upstream initialize/list, anonymous rejection and write denial passed without network')
"""


def production_entrypoint(identity, image):
    volume = identity + "-secret"
    run(["docker", "volume", "create", "--label", LABEL + "=" + identity, volume], capture_output=True)
    token = run(["docker", "run", "--rm", "--label", LABEL + "=" + identity, "--network", "none",
                 "--read-only", "--user", "0", "--mount", "type=volume,source=" + volume + ",target=/run/secrets",
                 "--entrypoint", "/usr/local/bin/python", image, "-c", PREPARE], capture_output=True, text=True).stdout.strip()
    name = identity + "-production"
    run(["docker", "run", "-d", "--name", name, "--label", LABEL + "=" + identity,
         "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
         "--pids-limit", "64", "--memory", "512m", "--cpus", "0.5", "--tmpfs",
         "/tmp:rw,noexec,nosuid,size=32m,uid=65532,gid=65532,mode=0700", "--mount",
         "type=volume,source=" + volume + ",target=/run/secrets,readonly", image], capture_output=True)
    run(["docker", "exec", "-i", name, "/usr/local/bin/python", "-c", PROBE], input=token, text=True)


def main(identity):
    if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid fixture identity")
    image = identity + ":fixture"
    try:
        with tempfile.TemporaryDirectory(prefix=identity) as temp:
            builder.build(image, Path(temp) / "record.json")
            run(["docker", "run", "--rm", "--label", LABEL + "=" + identity,
                 "--network", "none", "--read-only", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--pids-limit", "64",
                 "--memory", "512m", "--cpus", "0.5", "--tmpfs",
                 "/tmp:rw,noexec,nosuid,size=32m,uid=65532,gid=65532,mode=0700",
                 "--mount", "type=bind,source=" + str(ROOT) + ",target=/workspace,readonly",
                 "-e", "PYTHONPATH=/gateway:/opt/gateway-deps", "--entrypoint", "/usr/local/bin/python",
                 image, "-P", "/workspace/services/ynab-gateway/test_gateway.py"])
            # Docker inspect is configuration evidence, not full image scanning.
            config = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]["Config"]
            if config["User"] != "65532:65532" or config.get("ExposedPorts"):
                raise ValueError("Unexpected gateway image privilege/port configuration")
            production_entrypoint(identity, image)
            run([sys.executable, str(ROOT / "tests/test_ynab_egress.py")], env=dict(os.environ,
                YNAB_GATEWAY_TEST_IMAGE=image, YNAB_GATEWAY_TEST_SECRET=identity + "-secret",
                YNAB_EGRESS_TEST_ID=identity.replace("ynab-gateway-test-", "ynab-egress-test-")))
    finally:
        cleanup(identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.cleanup)
    else:
        main(os.environ.get("YNAB_GATEWAY_TEST_ID", "ynab-gateway-test-" + uuid.uuid4().hex))
