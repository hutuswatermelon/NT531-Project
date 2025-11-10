# analyze_summary_comparison.py
# -----------------------------------------------------------------
# Chỉ 6 biểu đồ tổng hợp, dễ so sánh toàn môi trường & QoS
# Phân tách ENV / QoS / Scaling (K8S)

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# ---------------- CONFIG ----------------
INPUT_FILE = "summary_comparison.csv"
OUT_DIR = Path("plots_summary")
OUT_DIR.mkdir(exist_ok=True)
sns.set(style="whitegrid", font_scale=1.15)
plt.rcParams["figure.dpi"] = 150

# ---------------- LOAD DATA ----------------
df = pd.read_csv(INPUT_FILE)

# ---------------- CLEAN / CHECK ----------------
for col in ["env", "qos", "pod_config", "category"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.upper().str.strip()

# ---------------- TÁCH NHÓM ----------------
env_df = df[df["category"] == "ENV_FAIR"]
qos_df = df[df["category"] == "QOS_EFFECT"]
k8s_df = df[df["category"] == "K8S_POD_SCALING"]

# ---------------- VẼ BIỂU ĐỒ ----------------

def save_plot(fig, name):
    fig.tight_layout()
    fig.savefig(OUT_DIR / name)
    plt.close(fig)
    print(f"Saved: {OUT_DIR/name}")

# ENV – Throughput, CPU, Latency
if not env_df.empty:
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    sns.barplot(data=env_df, x="env", y="throughput_mbps_mean", ax=axes[0])
    axes[0].set_title("Throughput trung bình (Mbps)")
    sns.barplot(data=env_df, x="env", y="cpu_mean_mean", ax=axes[1])
    axes[1].set_title("CPU trung bình (%)")
    sns.barplot(data=env_df, x="env", y="latency_ms_mean", ax=axes[2])
    axes[2].set_title("Độ trễ trung bình (ms)")
    fig.suptitle("So sánh môi trường (NOQoS – FAIR)")
    save_plot(fig, "1_env_fair_comparison.png")

# ENV – Jitter Stability
if not env_df.empty:
    fig, ax = plt.subplots(figsize=(6,5))
    sns.barplot(data=env_df, x="env", y="jitter_ms_mean", ax=ax)
    ax.set_title("Độ ổn định truyền (Jitter trung bình, ms)")
    save_plot(fig, "2_env_fair_jitter.png")

# QoS – Throughput normalized (%)
if not qos_df.empty:
    fig, ax = plt.subplots(figsize=(8,5))
    sns.barplot(data=qos_df, x="qos", y="throughput_norm", hue="env")
    ax.set_title("Ảnh hưởng QoS – Throughput normalized (%)")
    ax.set_ylabel("Throughput so với Native (%)")
    save_plot(fig, "3_qos_throughput_norm.png")

# QoS – Latency & Jitter
if not qos_df.empty:
    fig, axes = plt.subplots(1, 2, figsize=(12,5))
    sns.barplot(data=qos_df, x="qos", y="latency_ms_mean", hue="env", ax=axes[0])
    axes[0].set_title("Độ trễ (ms)")
    sns.barplot(data=qos_df, x="qos", y="jitter_ms_mean", hue="env", ax=axes[1])
    axes[1].set_title("Độ dao động Jitter (ms)")
    fig.suptitle("Ảnh hưởng QoS – Latency & Jitter")
    save_plot(fig, "4_qos_latency_jitter.png")

# K8S – Scaling theo số Pod
if not k8s_df.empty:
    fig, axes = plt.subplots(1, 2, figsize=(12,5))
    sns.barplot(data=k8s_df, x="pod_config", y="throughput_mbps_mean", ax=axes[0])
    axes[0].set_title("Throughput theo số Pod")
    sns.barplot(data=k8s_df, x="pod_config", y="cpu_mean_mean", ax=axes[1])
    axes[1].set_title("CPU trung bình theo số Pod")
    fig.suptitle("K8S Scaling – Hiệu năng theo số Pod")
    save_plot(fig, "5_k8s_scaling.png")

# Tổng hợp – ENV vs CPU efficiency
if not env_df.empty:
    fig, ax = plt.subplots(figsize=(6,5))
    env_df["cpu_efficiency"] = env_df["cpu_mean_mean"] / env_df["throughput_mbps_mean"]
    sns.barplot(data=env_df, x="env", y="cpu_efficiency", ax=ax)
    ax.set_title("Hiệu suất CPU (% CPU per Mbps)")
    save_plot(fig, "6_cpu_efficiency.png")

print(f"Đã sinh 6 biểu đồ tổng hợp tại: {OUT_DIR.resolve()}")
