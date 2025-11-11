# analyze_summary_overview.py
# Gộp 6 biểu đồ tổng hợp (ENV, QoS, K8S, CPU) vào 1 bảng duy nhất

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# ---------------- CONFIG ----------------
INPUT_FILE = "summary_comparison.csv"
OUT_DIR = Path("plots_summary")
OUT_DIR.mkdir(exist_ok=True)
sns.set(style="whitegrid", font_scale=1.1)
plt.rcParams["figure.dpi"] = 150

# ---------------- LOAD ----------------
df = pd.read_csv(INPUT_FILE)
for col in ["env", "qos", "pod_config", "category"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.upper().str.strip()

env_df = df[df["category"] == "ENV_FAIR"]
qos_df = df[df["category"] == "QOS_EFFECT"]
k8s_df = df[df["category"] == "K8S_POD_SCALING"]

# Lọc representative nic_mode cho QoS comparison
if not qos_df.empty:
    qos_representative = qos_df[
        ((qos_df["env"] == "DOCKER") & (qos_df["nic_mode"] == "BRIDGED")) |
        ((qos_df["env"] == "VM") & (qos_df["nic_mode"] == "CROSS-HOSTS")) |
        ((qos_df["env"] == "KUBERNETES") & (qos_df["nic_mode"] == "K8S_1 POD")) |
        (qos_df["env"] == "NATIVE")
    ].copy()
else:
    qos_representative = qos_df

# ---------------- VẼ 6 BIỂU ĐỒ TRÊN 1 BẢNG ----------------
fig, axes = plt.subplots(3, 2, figsize=(13, 12))
fig.subplots_adjust(hspace=0.4, wspace=0.25)

# ENV Fair – Throughput, CPU
if not env_df.empty:
    sns.barplot(data=env_df, x="env", y="throughput_mbps_mean", ax=axes[0,0])
    axes[0,0].set_title("ENV – Throughput (Mbps)")
    sns.barplot(data=env_df, x="env", y="cpu_mean_mean", ax=axes[0,1])
    axes[0,1].set_title("ENV – CPU trung bình (%)")

# QoS Effect – Throughput (% so với NOQOS cùng env) - dùng representative
if not qos_representative.empty:
    sns.barplot(data=qos_representative, x="qos", y="qos_effect_pct", hue="env", ax=axes[1,0])
    axes[1,0].set_title("QoS Effect – Throughput (% NOQOS)")
    axes[1,0].axhline(y=100, color='red', linestyle='--', linewidth=0.8, alpha=0.5)
    axes[1,0].legend(fontsize=7, loc='best')
    axes[1,0].set_ylim(bottom=0)

# QoS Effect – Latency (ms) - dùng representative
if not qos_representative.empty:
    sns.barplot(data=qos_representative, x="qos", y="latency_ms_mean", hue="env", ax=axes[1,1])
    axes[1,1].set_title("QoS ảnh hưởng – Latency (ms)")
    axes[1,1].legend(fontsize=7, loc='best')

# K8S Scaling – Pod throughput
if not k8s_df.empty:
    sns.barplot(data=k8s_df, x="pod_config", y="throughput_mbps_mean", ax=axes[2,0])
    axes[2,0].set_title("K8S – Throughput theo số Pod")
    sns.barplot(data=k8s_df, x="pod_config", y="cpu_mean_mean", ax=axes[2,1])
    axes[2,1].set_title("K8S – CPU trung bình theo số Pod")

# ---------------- TỔNG QUAN & GHI CHÚ ----------------
fig.suptitle("Tổng hợp So sánh Hiệu năng – ENV / QoS / K8S Scaling", fontsize=16, y=0.98)
for ax in axes.flat:
    if not ax.has_data():
        ax.set_visible(False)

plt.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT_DIR / "overview_summary_all.png")
plt.close(fig)

print(f"Đã sinh biểu đồ tổng hợp duy nhất tại: {OUT_DIR/'overview_summary_all.png'}")
