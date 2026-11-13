"""Hard VM power-off/on drill for a dedicated DigitalOcean SYNERGY DR test host.

This proves VM interruption and recovery, not physical data-centre host failure.
"""
from __future__ import annotations
import json, os, subprocess, time, urllib.error, urllib.request
API="https://api.digitalocean.com/v2"

def required(name):
    value=os.environ.get(name,"")
    if not value or value!=value.strip(): raise SystemExit(f"required environment variable is missing: {name}")
    return value

def api(method,path,token,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    request=urllib.request.Request(API+path,data=data,method=method,
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            raw=response.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8","replace")
        raise SystemExit(f"DigitalOcean API failed: HTTP {exc.code}: {detail[:500]}")

def wait_status(droplet_id,expected,token,timeout=900):
    deadline=time.time()+timeout
    while time.time()<deadline:
        item=api("GET",f"/droplets/{droplet_id}",token)["droplet"]
        if item["status"]==expected: return item
        time.sleep(10)
    raise SystemExit(f"test VM did not reach {expected!r} within {timeout}s")

def main():
    token=required("DO_API_TOKEN"); droplet_id=required("DR_DROPLET_ID")
    ssh_key=required("DR_SSH_PRIVATE_KEY_PATH"); ssh_user=required("DR_SSH_USER")
    remote_command=required("DR_REMOTE_VERIFY_COMMAND")
    if not droplet_id.isdigit() or not os.path.isfile(ssh_key): raise SystemExit("invalid droplet ID or SSH key path")
    droplet=api("GET",f"/droplets/{droplet_id}",token)["droplet"]
    if "synergy-dr-test" not in droplet.get("tags",[]): raise SystemExit("refusing power operation: missing synergy-dr-test tag")
    if droplet["status"]!="active": raise SystemExit(f"refusing power operation: droplet status is {droplet['status']!r}")
    networks=droplet.get("networks",{}).get("v4",[])
    public=[n["ip_address"] for n in networks if n.get("type")=="public"]
    if not public: raise SystemExit("test droplet has no public IPv4")
    ip=public[0]
    api("POST",f"/droplets/{droplet_id}/actions",token,{"type":"power_off"})
    wait_status(droplet_id,"off",token)
    api("POST",f"/droplets/{droplet_id}/actions",token,{"type":"power_on"})
    active=wait_status(droplet_id,"active",token)
    command=["ssh","-i",ssh_key,"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new",
        "-o","ConnectTimeout=10","-o","ServerAliveInterval=5","-o","ServerAliveCountMax=12",
        f"{ssh_user}@{ip}",remote_command]
    deadline=time.time()+600; last_error=None
    while time.time()<deadline:
        result=subprocess.run(command,capture_output=True,text=True,timeout=90)
        if result.returncode==0:
            try: evidence=json.loads(result.stdout.strip().splitlines()[-1])
            except (IndexError,json.JSONDecodeError): raise SystemExit("remote verifier did not return JSON evidence")
            if evidence.get("status")!="PASS" or evidence.get("registers_verified")!=6:
                raise SystemExit("remote verifier did not attest all six authoritative registers")
            if not isinstance(evidence.get("event_root"),str) or len(evidence["event_root"])!=64:
                raise SystemExit("remote verifier omitted the common event root")
            print(json.dumps({"status":"PASS","droplet_id":droplet_id,"region":active.get("region",{}).get("slug"),
                "vm_outage":"power_off_then_power_on","remote_recovery_evidence":evidence},sort_keys=True))
            return
        last_error=(result.stderr or result.stdout)[-1000:]; time.sleep(10)
    raise SystemExit(f"VM restarted but six-register recovery verification failed: {last_error}")

if __name__=="__main__": main()
