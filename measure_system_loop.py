import argparse, psutil, subprocess, threading, time, platform
from pathlib import Path
import os, sys, json

# ---------------- ARGPARSE -----------------
parser = argparse.ArgumentParser(description="Đo hiệu năng mạng đa hướng với QoS")
parser.add_argument("--role", choices=["client", "server"], required=True)
parser.add_argument("--server-ip", default=None)
parser.add_argument("--base-dir", default="runs/test_batch")
parser.add_argument("--duration", type=int, default=30)
parser.add_argument("--repeat", type=int, default=10)
parser.add_argument("--direction", choices=["cs", "sc", "bidir"], default="cs",
                    help="Hướng đo: cs=client→server, sc=server→client, bidir=hai chiều")
parser.add_argument("--qos", choices=["noqos", "qos1", "qos2", "qos3"], default="noqos",
                    help="Áp dụng QoS: noqos, qos1(rate limit), qos2(delay), qos3(delay+loss)")
parser.add_argument("--iface", default="eth0", help="Tên interface để áp QoS (Linux)")
args = parser.parse_args()

BASE = Path(args.base_dir)
BASE.mkdir(parents=True, exist_ok=True)

# ---------------- QoS -----------------
def apply_qos():
    """Áp dụng QoS theo loại và hệ điều hành"""
    print(f"Đang áp dụng QoS: {args.qos} trên {args.iface}")

    if platform.system() == "Windows":
        print("QoS không khả dụng trực tiếp trên Windows (bỏ qua).")
        return

    # Xóa QoS cũ nếu có
    subprocess.run(["tc", "qdisc", "del", "dev", args.iface, "root"], stderr=subprocess.DEVNULL)

    # Chọn loại QoS
    if args.qos == "qos1":
        cmd = f"tc qdisc add dev {args.iface} root tbf rate 40mbit burst 32kbit latency 400ms"
    elif args.qos == "qos2":
        cmd = f"tc qdisc add dev {args.iface} root netem delay 25ms"
    elif args.qos == "qos3":
        cmd = f"tc qdisc add dev {args.iface} root netem delay 25ms loss 1%"
    else:
        print("QoS: không áp dụng (noqos).")
        return

    print(f"Thực thi: {cmd}")
    os.system(cmd)
    print("Áp dụng QoS thành công.\n")

# ---------------- System Monitor -----------------
def monitor(out_path, duration=None):
    """Theo dõi CPU/RAM và ghi ra file mỗi 1 giây"""
    log_file = out_path / "sys_usage.log"
    with open(log_file, "w") as f:
        f.write("timestamp,cpu_percent,mem_used_mb\n")
        print(f"Ghi log CPU/RAM vào {log_file}")
        try:
            while True if duration is None else duration > 0:
                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory().used / (1024 * 1024)
                f.write(f"{time.time()},{cpu:.2f},{mem:.2f}\n")
                f.flush()
                if duration is not None:
                    duration -= 1
        except KeyboardInterrupt:
            print("\nDừng ghi log CPU/RAM.")

# ---------------- Server -----------------
def start_iperf_server_in_new_window():
    """Mở iperf3 server sinh log JSON cho từng client kết nối"""
    print("📡 Mở iperf3 server, sinh JSON cho từng session...")

    if platform.system() == "Windows":
        server_logs = BASE / "server_json"
        server_logs.mkdir(exist_ok=True)
        cmd = (
            'start "iperf3 server" cmd /k '
            f'"for /L %i in (1,1,999) do (echo [SERVER] Waiting %%i & '
            f'iperf3 -s -1 -J > {server_logs}\\session_%%i.json & '
            f'echo [SERVER] Session %%i done. & timeout 3 >nul)"'
        )
        os.system(cmd)
    else:
        subprocess.Popen(
            [
                "gnome-terminal", "--", "bash", "-c",
                f'mkdir -p {BASE}/server_json; i=1; while true; do '
                f'echo "[SERVER] Waiting $i..."; '
                f'iperf3 -s -1 -J > {BASE}/server_json/session_$i.json; '
                f'echo "[SERVER] Session $i done."; sleep 3; i=$((i+1)); done'
            ]
        )

# ---------------- Client -----------------
def client_run(run_dir):
    """Chạy iperf3 + ping"""
    ping_flag = "-c" if platform.system() != "Windows" else "-n"

    # Chọn hướng đo
    iperf_cmd = ["iperf3", "-c", args.server_ip, "-t", str(args.duration), "-P", "4", "-J"]
    if args.direction == "sc":
        iperf_cmd.append("-R")  # reverse (server → client)
    elif args.direction == "bidir":
        iperf_cmd.append("--bidir")  # bidirectional

    # iperf3 test
    with open(run_dir / "iperf_client.json", "w") as f:
        print(f"Chạy: {' '.join(iperf_cmd)}")
        subprocess.run(iperf_cmd, stdout=f, stderr=subprocess.STDOUT)

    # ping test
    with open(run_dir / "ping.log", "w") as f:
        subprocess.run(
            ["ping", ping_flag, "100", args.server_ip],
            stdout=f, stderr=subprocess.STDOUT
        )

# ---------------- Meta -----------------
def write_metadata(run_dir):
    """Lưu thông tin cấu hình test"""
    meta = {
        "role": args.role,
        "server_ip": args.server_ip,
        "duration": args.duration,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.system(),
        "repeat_index": str(run_dir.name),
        "qos": args.qos,
        "direction": args.direction
    }
    with open(run_dir / "meta.txt", "w") as f:
        for k, v in meta.items():
            f.write(f"{k}={v}\n")

# ---------------- MAIN -----------------
if args.role == "server":
    apply_qos()
    start_iperf_server_in_new_window()
    monitor(BASE, None)

else:
    apply_qos()

    # Gợi ý hướng QoS
    if args.direction == "cs":
        print("QoS nên áp tại CLIENT (mô phỏng uplink).")
    elif args.direction == "sc":
        print("QoS nên áp tại SERVER (mô phỏng downlink).")
    elif args.direction == "bidir":
        print("QoS nên áp tại cả CLIENT và SERVER (mô phỏng WAN).")

    for i in range(1, args.repeat + 1):
        run_dir = BASE / f"run_{i:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nBắt đầu lần đo {i}/{args.repeat}: {run_dir}")

        t = threading.Thread(target=monitor, args=(run_dir, args.duration), daemon=True)
        t.start()
        client_run(run_dir)
        t.join()

        write_metadata(run_dir)
        print(f"Hoàn tất lần đo {i}/{args.repeat}")
        time.sleep(3)

    print(f"\nHoàn thành {args.repeat} lần đo. Kết quả lưu tại {BASE.resolve()}")
