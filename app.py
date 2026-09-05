#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


TRUE_VALUES = {"1", "true", "yes", "on"}


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def read_secret(value_name, file_name):
    value = os.environ.get(value_name)
    if value is not None:
        return value
    path = os.environ.get(file_name)
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to read {file_name}: {exc}") from exc


def feature_config():
    return {
        "electrs": {"enabled": env_bool("ELECTRS_ENABLED")},
        "tor": {"enabled": env_bool("TOR_ENABLED")},
        "mempool_explorer": {
            "enabled": env_bool("MEMPOOL_EXPLORER_ENABLED"),
            "url": os.environ.get("MEMPOOL_EXPLORER_URL", ""),
        },
        "host_metrics": {"enabled": env_bool("HOST_METRICS_ENABLED")},
    }


def dashboard_instance_name():
    for variable in ("DASHBOARD_INSTANCE_NAME", "NODE_NAME"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    return "bitcoin-knots"


def knots_version_label(subversion):
    if not subversion:
        return ""
    text = str(subversion)
    satoshi = re.search(r"Satoshi:([^/]+)", text)
    knots = re.search(r"Knots:([^/]+)", text)
    if satoshi and knots:
        return f"{satoshi.group(1)} (Knots {knots.group(1)})"
    if knots:
        return f"Knots {knots.group(1)}"
    if satoshi:
        return satoshi.group(1)
    return text.strip("/")


def dashboard_version():
    value = os.environ.get("APP_VERSION", "").strip()
    if value:
        return value
    path = APP_DIR / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def blockchain_sync_status(blockchain):
    verification_progress = blockchain.get("verificationprogress")
    progress_percent = (
        round(verification_progress * 100, 2)
        if verification_progress is not None
        else None
    )
    return {
        "blocks": blockchain.get("blocks"),
        "headers": blockchain.get("headers"),
        "progress_percent": progress_percent,
        "initial_block_download": blockchain.get("initialblockdownload"),
        "best_block_time": blockchain.get("time"),
        "size_on_disk_bytes": blockchain.get("size_on_disk"),
        "pruned": blockchain.get("pruned"),
        "prune_height": blockchain.get("pruneheight"),
        "automatic_pruning": blockchain.get("automatic_pruning"),
        "prune_target_size_bytes": blockchain.get("prune_target_size"),
    }


def bitcoin_rpc(method, params=None):
    url = os.environ.get("BITCOIN_RPC_URL", "http://bitcoin-knots:8332")
    user = os.environ.get("BITCOIN_RPC_USER", "")
    password = read_secret("BITCOIN_RPC_PASSWORD", "BITCOIN_RPC_PASSWORD_FILE")
    timeout = env_int("BITCOIN_RPC_TIMEOUT_SECONDS", 10)
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    data = json.dumps({"jsonrpc": "1.0", "id": "dashboard", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            if "error" in result and result["error"]:
                raise RuntimeError(result["error"])
            return result.get("result")
    except Exception as e:
        raise RuntimeError(str(e))


APP_DIR = Path(__file__).resolve().parent
CACHE = None
CACHE_LOCK = threading.Lock()
REFRESHING = False
REFRESH_INTERVAL_SECONDS = env_int("REFRESH_INTERVAL_SECONDS", 30)


def get_electrs_status():
    if not env_bool("ELECTRS_ENABLED"):
        return None
    try:
        url = os.environ.get("ELECTRS_METRICS_URL", "http://electrs:4224")
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read().decode("utf-8")
        height = None
        for line in data.splitlines():
            if line.startswith('electrs_index_height{type="tip"}'):
                height = int(line.split()[-1])
                break
        return {
            "running": True,
            "height": height,
        }
    except Exception as e:
        return {"running": False, "error": str(e)}

def get_system_metrics():
    if not env_bool("HOST_METRICS_ENABLED"):
        return None

    metrics = {
        "cpu_temp_c": None,
        "load_1m": None,
        "load_5m": None,
        "load_15m": None,
    }

    # CPU temperature - try multiple methods (Pi 5 friendly)
    try:
        temp_path = os.environ.get("CPU_TEMP_PATH", "/sys/class/thermal/thermal_zone0/temp")
        with open(temp_path) as f:
            temp_raw = int(f.read().strip())
            metrics["cpu_temp_c"] = round(temp_raw / 1000.0, 1)
    except Exception:
        pass

    try:
        loadavg_path = os.environ.get("LOADAVG_PATH", "/proc/loadavg")
        with open(loadavg_path) as f:
            parts = f.read().strip().split()
            metrics["load_1m"] = float(parts[0])
            metrics["load_5m"] = float(parts[1])
            metrics["load_15m"] = float(parts[2])
    except Exception:
        pass

    return metrics


def get_tor_status(network):
    if not env_bool("TOR_ENABLED"):
        return None
    onion_network = next(
        (item for item in network.get("networks", []) if item.get("name") == "onion"),
        {},
    )
    return {
        "name": "tor",
        "running": bool(onion_network.get("reachable")),
        "status": "docker",
        "health": None,
        "started_at": None,
        "uptime_seconds": None,
    }

def collect_status():
    started = time.time()
    errors = []
    features = feature_config()

    try:
        blockchain = bitcoin_rpc("getblockchaininfo")
    except Exception as e:
        blockchain = {}
        errors.append({"source": "getblockchaininfo", "message": str(e)})

    collect_optional_rpc = blockchain.get("initialblockdownload") is False

    # Recent blocks (last 8) for mini-list
    recent_blocks = []
    if collect_optional_rpc:
        try:
            height = blockchain.get("blocks")
            if height is not None:
                for i in range(8):
                    h = height - i
                    if h < 0:
                        break
                    try:
                        block_hash = bitcoin_rpc("getblockhash", [h])
                        header = bitcoin_rpc("getblockheader", [block_hash])
                        stats = bitcoin_rpc("getblockstats", [h])
                        recent_blocks.append({
                            "height": header.get("height"),
                            "time": header.get("time"),
                            "tx_count": stats.get("txs", header.get("nTx")),
                            "size": stats.get("total_size"),
                            "hash": header.get("hash"),
                        })
                    except Exception as e:
                        errors.append({"source": "recent_block_" + str(h), "message": str(e)})
                        # skip bad block instead of breaking the whole collection
        except Exception as e:
            errors.append({"source": "recent_blocks", "message": str(e)})

    try:
        network = bitcoin_rpc("getnetworkinfo")
    except Exception as e:
        network = {}
        errors.append({"source": "getnetworkinfo", "message": str(e)})

    mempool = {}
    if collect_optional_rpc:
        try:
            mempool = bitcoin_rpc("getmempoolinfo")
        except Exception as e:
            errors.append({"source": "getmempoolinfo", "message": str(e)})

    # Fee estimates (targets 1 = next block, 3 ≈30min, 6 ≈1h)
    fee_estimates = {}
    if collect_optional_rpc:
        for target_blocks, label in [(1, "next_block"), (3, "30min"), (6, "1h")]:
            try:
                est = bitcoin_rpc("estimatesmartfee", [target_blocks])
                fee_estimates[label] = {
                    "feerate": est.get("feerate"),
                    "blocks": est.get("blocks"),
                }
            except Exception as e:
                errors.append({"source": f"estimatesmartfee {target_blocks}", "message": str(e)})
                fee_estimates[label] = None

    try:
        uptime = bitcoin_rpc("uptime")
    except Exception as e:
        uptime = None
        errors.append({"source": "uptime", "message": str(e)})

    peerinfo = []
    if collect_optional_rpc:
        try:
            peerinfo = bitcoin_rpc("getpeerinfo")
        except Exception:
            pass

    electrs = get_electrs_status()
    if electrs and electrs.get("running") and electrs.get("height") is not None:
        node_height = blockchain.get("blocks")
        if node_height:
            progress = min(100.0, (electrs["height"] / node_height) * 100)
            electrs["progress_percent"] = round(progress, 2)

    tor = get_tor_status(network)

    peers = []
    inbound = outbound = 0
    onion_peers = clearnet_peers = 0
    for peer in peerinfo:
        is_inbound = bool(peer.get("inbound"))
        inbound += int(is_inbound)
        outbound += int(not is_inbound)
        network_name = peer.get("network") or "unknown"
        onion_peers += int(network_name == "onion")
        clearnet_peers += int(network_name != "onion")
        peers.append({
            "id": peer.get("id"),
            "addr": peer.get("addr"),
            "network": network_name,
            "inbound": is_inbound,
            "connection_type": peer.get("connection_type"),
            "subver": peer.get("subver"),
            "startingheight": peer.get("startingheight"),
            "synced_blocks": peer.get("synced_blocks"),
            "synced_headers": peer.get("synced_headers"),
            "pingtime_ms": round(peer.get("pingtime", 0) * 1000, 0) if peer.get("pingtime") is not None else None,
        })

    warnings = []
    for source in (blockchain, network):
        item = source.get("warnings")
        if isinstance(item, list):
            warnings.extend(str(w) for w in item if w)
        elif item:
            warnings.append(str(item))

    disk_monitor_path = os.environ.get("DISK_MONITOR_PATH", "").strip()
    if disk_monitor_path:
        try:
            import shutil
            free = shutil.disk_usage(disk_monitor_path).free
            threshold_gb = env_int("DISK_WARNING_FREE_GB", 100)
            if free < threshold_gb * 1024**3:
                warnings.append(
                    f"Low disk space on {disk_monitor_path}: only {free // (1024**3)} GB free"
                )
        except Exception as exc:
            errors.append({"source": "disk_monitor", "message": str(exc)})

    # High mempool warning
    try:
        mempool_bytes = mempool.get("bytes") or 0
        if mempool_bytes > 300 * 1024**2:  # > 300 MB
            warnings.append(f"Large mempool: {mempool_bytes // (1024**2)} MB")
    except Exception:
        pass

    networks = network.get("networks", [])
    network_reachability = {item.get("name"): bool(item.get("reachable")) for item in networks if item.get("name")}

    # Extract onion hostname for the Tor row
    onion_hostname = None
    for item in network.get("localaddresses", []):
        addr = item.get("address", "")
        if addr.endswith(".onion"):
            onion_hostname = f"{addr}:{item.get('port', 8333)}"
            break

    services = {
        "knots": {
            "name": "bitcoind",
            "running": bool(blockchain),
            "status": "docker",
            "health": "rpc" if blockchain else None,
            "started_at": None,
            "uptime_seconds": uptime,
        },
        "knots_uptime_seconds": uptime,
        "onion_hostname": onion_hostname,
    }
    if features["tor"]["enabled"]:
        services["tor"] = tor
    if features["electrs"]["enabled"]:
        services["electrs"] = electrs

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((time.time() - started) * 1000),
        "dashboard": {"version": dashboard_version()},
        "node": {"name": dashboard_instance_name()},
        "features": features,
        "chain": blockchain.get("chain"),
        "sync": blockchain_sync_status(blockchain),
        "connections": {
            "total": network.get("connections"),
            "in": network.get("connections_in", inbound),
            "out": network.get("connections_out", outbound),
            "onion_peers": onion_peers,
            "clearnet_peers": clearnet_peers,
        },
        "network": {
            "version": network.get("version"),
            "subversion": network.get("subversion"),
            "version_label": knots_version_label(network.get("subversion")),
            "protocolversion": network.get("protocolversion"),
            "localaddresses": network.get("localaddresses", []),
            "reachable": network_reachability,
        },
        "mempool": {
            "loaded": mempool.get("loaded"),
            "size": mempool.get("size"),
            "bytes": mempool.get("bytes"),
            "usage": mempool.get("usage"),
            "mempoolminfee": mempool.get("mempoolminfee"),
            "minrelaytxfee": mempool.get("minrelaytxfee"),
            "fee_estimates": fee_estimates,
        },
        "services": services,
        "system": get_system_metrics(),
        "warnings": warnings,
        "errors": errors,
        "peers": peers,
        "recent_blocks": recent_blocks,
        "cache": {"fresh": True, "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS},
    }

def empty_status():
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 0,
        "dashboard": {"version": dashboard_version()},
        "node": {"name": dashboard_instance_name()},
        "features": feature_config(),
        "chain": None,
        "sync": {},
        "connections": {},
        "network": {"localaddresses": [], "reachable": {}},
        "mempool": {},
        "services": {},
        "warnings": [],
        "errors": [{"source": "dashboard", "message": "Status collection is starting."}],
        "peers": [],
        "recent_blocks": [],
        "cache": {"fresh": False, "refreshing": True, "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS},
    }

def refresh_cache():
    global CACHE, REFRESHING
    try:
        status = collect_status()
        with CACHE_LOCK:
            CACHE = status
    finally:
        with CACHE_LOCK:
            REFRESHING = False

def ensure_refresh():
    global REFRESHING
    with CACHE_LOCK:
        if REFRESHING:
            return
        if CACHE is not None:
            generated_at = datetime.fromisoformat(CACHE["generated_at"])
            age = (datetime.now(timezone.utc) - generated_at).total_seconds()
            if age < REFRESH_INTERVAL_SECONDS:
                return
        REFRESHING = True
    threading.Thread(target=refresh_cache, daemon=True).start()

def refresh_loop():
    while True:
        ensure_refresh()
        time.sleep(REFRESH_INTERVAL_SECONDS)

def cached_status():
    with CACHE_LOCK:
        if CACHE is None:
            return empty_status()
        status = dict(CACHE)
        status["cache"] = dict(status.get("cache", {}))
        status["cache"]["fresh"] = (datetime.now(timezone.utc) - datetime.fromisoformat(status["generated_at"])).total_seconds() < REFRESH_INTERVAL_SECONDS * 2
        status["cache"]["refreshing"] = REFRESHING
        return status

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self.send_json(cached_status())
            return
        if path == "/healthz":
            self.send_json({"ok": True})
            return
        if path == "/readyz":
            status = cached_status()
            ready = bool(status.get("services", {}).get("knots", {}).get("running"))
            self.send_json({"ok": ready}, status=200 if ready else 503)
            return
        super().do_GET()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "0.0.0.0"))
    parser.add_argument("--port", default=env_int("DASHBOARD_PORT", 8335), type=int)
    args = parser.parse_args()

    hosts = [host.strip() for host in args.host.split(",") if host.strip()]
    servers = [ThreadingHTTPServer((host, args.port), DashboardHandler) for host in hosts]
    for server in servers:
        host, port = server.server_address[:2]
        print(f"Knots dashboard listening on http://{host}:{port}", flush=True)
    threading.Thread(target=refresh_loop, daemon=True).start()
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    servers[0].serve_forever()

if __name__ == "__main__":
    main()
