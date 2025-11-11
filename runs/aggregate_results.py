# aggregate_results.py
# ------------------------------------------
# Hợp nhất logic v4 + fix đọc iperf JSON nhiều đối tượng
# ------------------------------------------

import json, re, pandas as pd, numpy as np
from pathlib import Path

root = Path("runs")
rows = []

# ----------------- PING PARSER -----------------
def parse_ping_log(path: Path):
    if not path.exists():
        return np.nan, np.nan, np.nan
    text = path.read_text(errors="ignore")
    latency, loss, jitter = np.nan, np.nan, np.nan
    if "Average" in text:
        m_avg = re.search(r"Average = (\d+)ms", text)
        m_min = re.search(r"Minimum = (\d+)ms", text)
        m_max = re.search(r"Maximum = (\d+)ms", text)
        m_loss = re.search(r"Lost = \d+ \((\d+)% loss", text)
        if m_avg: latency = float(m_avg.group(1))
        if m_loss: loss = float(m_loss.group(1))
        if m_min and m_max: jitter = abs(float(m_max.group(1)) - float(m_min.group(1)))
    elif "rtt" in text:
        m = re.search(r"rtt .* = [\d\.]+/([\d\.]+)/([\d\.]+)/([\d\.]+)", text)
        if m:
            latency = float(m.group(1))
            jitter = float(m.group(3))
        m2 = re.search(r"(\d+)% packet loss", text)
        loss = float(m2.group(1)) if m2 else np.nan
    return latency, loss, jitter


# ----------------- SYS USAGE PARSER -----------------
def parse_sys_usage(path: Path):
    if not path.exists():
        return np.nan, np.nan
    try:
        df = pd.read_csv(path)
        if df.empty:
            return np.nan, np.nan
        return df["cpu_percent"].mean(), df["mem_used_mb"].mean()
    except Exception:
        return np.nan, np.nan


# ----------------- UTILS -----------------
def clean_name(name: str):
    return re.sub(r"^\d+\.\s*", "", name).strip()

def safe_load_json(path: Path):
    """Đọc iperf JSON an toàn (xử lý file có nhiều đối tượng JSON)"""
    try:
        text = path.read_text(encoding="utf-8")
        parts = re.split(r"}\s*{", text.strip())
        if len(parts) > 1:
            text = "{" + parts[-1]  # chỉ lấy JSON cuối
        return json.loads(text)
    except Exception:
        return {}

def extract_env_info(parts):
    """Trích xuất env, NIC, QoS, hướng, và pod_config"""
    env = next(
        (p for p in parts if any(x in p.upper() for x in ["KUBERNETES", "K8S", "NATIVE", "VM", "DOCKER"])),
        "unknown"
    )
    if "K8S" in env.upper() or "KUBERNETES" in env.upper():
        env = "KUBERNETES"

    nic_mode = next(
        (p for p in parts if any(x in p.upper() for x in ["CROSS", "BRIDGED", "NAT", "HOST", "MACVLAN"])),
        "unknown"
    )

    qos = next(
        (p for p in parts if re.search(r"QOS\d+|NOQOS", p, re.IGNORECASE)),
        "NOQOS"
    ).upper()

    # Hướng đo (chỉ áp dụng khi QoS != NOQOS)
    direction = "none"
    joined = "_".join(parts).lower()
    if qos != "NOQOS":
        if re.search(r"s[-_]*c", joined):
            direction = "sc"
        elif re.search(r"c[-_]*s", joined):
            direction = "cs"

    pod_config = next(
        (p for p in parts if re.search(r"\b\d+\s*POD", p, re.IGNORECASE)),
        "none"
    )

    return clean_name(env), clean_name(nic_mode), qos, direction, clean_name(pod_config)


# ----------------- SERVER -----------------
for server_dir in root.rglob("*SERVER"):
    if not server_dir.is_dir():
        continue

    parts = [clean_name(p) for p in server_dir.parts]
    env, nic_mode, qos, direction, pod_cfg = extract_env_info(parts)
    cpu, ram = parse_sys_usage(server_dir / "sys_usage.log")

    json_dir = server_dir / "server_json"
    if json_dir.exists():
        for f in sorted(json_dir.glob("session_*.json")):
            data = safe_load_json(f)
            end = data.get("end", {})
            sum_stats = end.get("sum_sent") or end.get("sum") or {}
            bits = sum_stats.get("bits_per_second", np.nan) / 1e6
            retrans = sum_stats.get("retransmits", np.nan)
            rows.append({
                "env": env, "nic_mode": nic_mode, "qos": qos,
                "direction": direction, "pod_config": pod_cfg, "role": "server",
                "throughput_mbps": bits, "retransmits": retrans,
                "cpu_mean": cpu, "ram_mean": ram, "path": str(f)
            })


# ----------------- CLIENT -----------------
for run_dir in root.rglob("*CLIENT/run_*"):
    if not run_dir.is_dir():
        continue

    parts = [clean_name(p) for p in run_dir.parts]
    env, nic_mode, qos, direction, pod_cfg = extract_env_info(parts)
    iperf_path = run_dir / "iperf_client.json"

    bits, retrans = np.nan, np.nan
    if iperf_path.exists():
        data = safe_load_json(iperf_path)
        end = data.get("end", {})
        sent = end.get("sum_sent") or end.get("sum") or {}
        bits = sent.get("bits_per_second", np.nan) / 1e6
        retrans = sent.get("retransmits", np.nan)

    latency, loss, jitter = parse_ping_log(run_dir / "ping.log")
    cpu, ram = parse_sys_usage(run_dir / "sys_usage.log")

    rows.append({
        "env": env, "nic_mode": nic_mode, "qos": qos,
        "direction": direction, "pod_config": pod_cfg, "role": "client",
        "throughput_mbps": bits, "retransmits": retrans,
        "latency_ms": latency, "packet_loss_pct": loss, "jitter_ms": jitter,
        "cpu_mean": cpu, "ram_mean": ram, "path": str(run_dir)
    })


# ----------------- OUTPUT -----------------
df = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
df.to_csv("summary_all_full.csv", index=False)
df[df["role"]=="client"].to_csv("summary_client_only.csv", index=False)
df[df["role"]=="server"].to_csv("summary_server_only.csv", index=False)

print(f"Tổng hợp {len(df)} bản ghi → summary_all_full.csv")
print(f"Tổng hợp {len(df[df['role']=='client'])} bản ghi client → summary_client_only.csv")
print(f"Tổng hợp {len(df[df['role']=='server'])} bản ghi server → summary_server_only.csv")
