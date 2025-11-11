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

# QoS – Throughput effect (% so với NOQOS cùng env)
# Lọc representative nic_mode cho mỗi env để tránh average sai
if not qos_df.empty:
    # Chọn nic_mode chính cho mỗi env
    representative = qos_df[
        ((qos_df["env"] == "DOCKER") & (qos_df["nic_mode"] == "BRIDGED")) |
        ((qos_df["env"] == "VM") & (qos_df["nic_mode"] == "CROSS-HOSTS")) |
        ((qos_df["env"] == "KUBERNETES") & (qos_df["nic_mode"] == "K8S_1 POD")) |
        (qos_df["env"] == "NATIVE")
    ].copy()
    
    if not representative.empty:
        fig, ax = plt.subplots(figsize=(11,6))
        sns.barplot(data=representative, x="qos", y="qos_effect_pct", hue="env", ax=ax)
        ax.set_title("Ảnh hưởng QoS – Throughput (% so với NOQOS)", fontsize=14)
        ax.set_ylabel("% so với NOQOS cùng môi trường")
        ax.set_xlabel("QoS Level")
        ax.axhline(y=100, color='red', linestyle='--', linewidth=1, alpha=0.7)
        ax.legend(title="Environment", loc='best')
        ax.set_ylim(bottom=0)
        save_plot(fig, "3_qos_throughput_norm.png")
    
    # Vẽ riêng từng env (detailed)
    for env_name in ["DOCKER", "VM", "KUBERNETES"]:
        env_data = qos_df[qos_df["env"] == env_name]
        if not env_data.empty and len(env_data["nic_mode"].unique()) > 1:
            fig, ax = plt.subplots(figsize=(10,6))
            sns.barplot(data=env_data, x="qos", y="qos_effect_pct", hue="nic_mode", ax=ax)
            ax.set_title(f"QoS Effect – {env_name} (chi tiết theo NIC/Pod)")
            ax.set_ylabel("% so với NOQOS")
            ax.axhline(y=100, color='red', linestyle='--', linewidth=1, alpha=0.5)
            ax.legend(title="NIC Mode", loc='best', fontsize=8)
            save_plot(fig, f"3_qos_detail_{env_name}.png")

# QoS – Latency & Jitter (dùng representative data)
if not qos_df.empty and not representative.empty:
    fig, axes = plt.subplots(1, 2, figsize=(12,5))
    sns.barplot(data=representative, x="qos", y="latency_ms_mean", hue="env", ax=axes[0])
    axes[0].set_title("Độ trễ (ms)")
    sns.barplot(data=representative, x="qos", y="jitter_ms_mean", hue="env", ax=axes[1])
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
    env_df_copy = env_df.copy()
    env_df_copy["cpu_efficiency"] = env_df_copy["cpu_mean_mean"] / env_df_copy["throughput_mbps_mean"]
    sns.barplot(data=env_df_copy, x="env", y="cpu_efficiency", ax=ax)
    ax.set_title("Hiệu suất CPU (% CPU per Mbps)")
    save_plot(fig, "6_cpu_efficiency.png")

print(f"Đã sinh 6 biểu đồ tổng hợp tại: {OUT_DIR.resolve()}")
