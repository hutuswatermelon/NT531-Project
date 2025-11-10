# analyze_summary_full.py
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import numpy as np
import warnings

# ---------------- CONFIG ----------------
INPUT_FILE = "summary_client_only.csv"
OUT_DIR = Path("plots_client")
OUT_DIR.mkdir(exist_ok=True)
sns.set(style="whitegrid", font_scale=1.05)
plt.rcParams["figure.dpi"] = 120
ERRORBAR_MODE = "se"

# ---------------- LOAD DATA ----------------
df = pd.read_csv(INPUT_FILE)
num_cols = ["throughput_mbps", "latency_ms", "packet_loss_pct", "jitter_ms", "cpu_mean", "ram_mean"]
df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)

# Chuẩn hoá cột dạng chuỗi
df["env"] = df["env"].astype(str).str.upper().str.strip()
df["qos"] = df["qos"].fillna("NOQOS").astype(str).str.upper().str.strip()
df["nic_mode"] = df["nic_mode"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
df["direction"] = df["direction"].fillna("NONE").astype(str).str.lower().str.strip()
if "pod_config" not in df.columns:
    df["pod_config"] = "NONE"

# ---------------- LỌC BẢN GHI KHÔNG HỢP LỆ ----------------
# Loại bỏ các bản ghi có throughput hoặc cpu_mean rỗng hoặc bằng 0
invalid_mask = (
    df["throughput_mbps"].isna() | (df["throughput_mbps"] <= 0) |
    df["cpu_mean"].isna() | (df["cpu_mean"] <= 0)
)

# Gắn lý do bị loại
df["invalid_reason"] = np.select(
    [
        df["throughput_mbps"].isna(),
        df["throughput_mbps"] <= 0,
        df["cpu_mean"].isna(),
        df["cpu_mean"] <= 0,
    ],
    [
        "throughput_nan",
        "throughput_zero_or_neg",
        "cpu_nan",
        "cpu_zero_or_neg",
    ],
    default=""
)

# Xuất bản ghi không hợp lệ
invalid_df = df[invalid_mask].copy()
if not invalid_df.empty:
    invalid_df.to_csv("invalid_records.csv", index=False)
    print(f"Đã xuất {len(invalid_df)} bản ghi không hợp lệ → invalid_records.csv")

# Giữ lại bản ghi hợp lệ
valid_mask = ~invalid_mask
before, after = len(df), valid_mask.sum()
df = df[valid_mask].reset_index(drop=True)
print(f"Loại bỏ {before - after} bản ghi không hợp lệ ({before} → {after})")


# Bỏ chiều với NoQoS hoặc Native
df.loc[(df["qos"] == "NOQOS") | (df["env"] == "NATIVE"), "direction"] = "none"

# ---------------- PHÂN LOẠI FAIR ----------------
def classify_fair(row):
    env, nic = row["env"], row["nic_mode"]
    if "NATIVE" in env or "K8S" in env or "KUBERNETES" in env:
        return True
    if "VM" in env and "CROSS" in nic:
        return True
    return False

df["is_fair"] = df.apply(classify_fair, axis=1)

# ---------------- GROUP ----------------
agg_cols = ["throughput_mbps","latency_ms","packet_loss_pct","jitter_ms","cpu_mean","ram_mean"]
agg_df = (
    df.groupby(["env","nic_mode","qos","direction","pod_config","is_fair"],dropna=False)[agg_cols]
    .agg(["mean","std","count","sem"])
)
agg_df.columns = ["_".join(c) for c in agg_df.columns]
agg_df = agg_df.reset_index()

for col in ["throughput_mbps","latency_ms","jitter_ms","cpu_mean"]:
    agg_df[f"{col}_cv"] = (agg_df[f"{col}_std"]/agg_df[f"{col}_mean"]*100).replace([np.inf,-np.inf],np.nan)

agg_df["cpu_per_mbps"] = agg_df["cpu_mean_mean"]/agg_df["throughput_mbps_mean"]

# normalize throughput theo Native
native_ref = agg_df[agg_df["env"].str.contains("NATIVE")].groupby("qos")["throughput_mbps_mean"].mean().to_dict()
agg_df["throughput_norm"] = agg_df.apply(
    lambda r: r["throughput_mbps_mean"]/native_ref.get(r["qos"],np.nan)*100 if r["qos"] in native_ref and native_ref[r["qos"]]>0 else np.nan,
    axis=1
)

# ---------------- TIỆN ÍCH ----------------
def plot_bar(data,x,y,hue,title,fname,ylabel,log=False):
    if data.empty: return
    plt.figure(figsize=(9,5))
    sns.barplot(data=data,x=x,y=y,hue=hue,errorbar=ERRORBAR_MODE)
    if log: plt.yscale("log")
    plt.title(title); plt.ylabel(ylabel)
    if hue: plt.legend(title=hue,frameon=True)
    plt.tight_layout(); plt.savefig(OUT_DIR/fname); plt.close()

def plot_box(data,x,y,hue,title,fname,ylabel):
    if data.empty: return
    plt.figure(figsize=(9,5))
    sns.boxplot(data=data,x=x,y=y,hue=hue)
    plt.title(title); plt.ylabel(ylabel)
    plt.tight_layout(); plt.savefig(OUT_DIR/fname); plt.close()

# ---------------- TÁCH DỮ LIỆU ----------------
internal_df = agg_df[~agg_df["is_fair"]]
fair_df = agg_df[(agg_df["is_fair"]) & (agg_df["qos"]=="NOQOS")]

# ---------------- PHẦN A: INTERNAL ----------------
plot_bar(internal_df,"env","throughput_mbps_mean","qos","A1. Internal Throughput","1_internal_throughput.png","Mbps",log=True)
plot_bar(internal_df,"env","latency_ms_mean","qos","A2. Internal Latency","2_internal_latency.png","ms")
plot_bar(internal_df,"env","cpu_mean_mean","qos","A3. Internal CPU","3_internal_cpu.png","%")
plot_bar(internal_df,"env","jitter_ms_mean","qos","A4. Internal Jitter","4_internal_jitter.png","ms")

# ---------------- PHẦN B: FAIR ----------------
plot_bar(fair_df,"env","throughput_mbps_mean",None,"B1. Fair Throughput (NOQOS only)","5_fair_throughput.png","Mbps")
plot_bar(fair_df,"env","latency_ms_mean",None,"B2. Fair Latency (NOQOS only)","6_fair_latency.png","ms")
plot_bar(fair_df,"env","cpu_mean_mean",None,"B3. Fair CPU (NOQOS only)","7_fair_cpu.png","%")
plot_bar(fair_df,"env","jitter_ms_mean",None,"B4. Fair Jitter (NOQOS only)","8_fair_jitter.png","ms")

# ---------------- PHẦN C: QoS normalized ----------------
qos_df = agg_df[agg_df["qos"]!="NOQOS"]
plot_bar(qos_df,"qos","throughput_norm","env","C1. QoS ảnh hưởng – Throughput (%)","9_qos_effect_throughput_norm.png","%")
plot_bar(qos_df,"qos","latency_ms_mean","env","C2. QoS ảnh hưởng – Latency","9b_qos_effect_latency_norm.png","ms")
plot_bar(qos_df,"qos","jitter_ms_mean","env","C3. QoS ảnh hưởng – Jitter","9c_qos_effect_jitter_norm.png","ms")

# ---------------- PHẦN D: NIC TRONG TỪNG ENV ----------------
for env_name in sorted(agg_df["env"].unique()):
    subset = agg_df[agg_df["env"]==env_name]
    plot_bar(subset,"nic_mode","throughput_mbps_mean","qos",f"NIC Throughput – {env_name}",f"nic_throughput_{env_name}.png","Mbps",log=True)
    plot_bar(subset,"nic_mode","latency_ms_mean","qos",f"NIC Latency – {env_name}",f"nic_latency_{env_name}.png","ms")
    plot_bar(subset,"nic_mode","cpu_mean_mean","qos",f"NIC CPU – {env_name}",f"nic_cpu_{env_name}.png","%")

# ---------------- PHẦN E: QoS theo NIC ----------------
for nic in sorted(agg_df["nic_mode"].unique()):
    subset = agg_df[agg_df["nic_mode"]==nic]
    plot_bar(subset,"qos","throughput_mbps_mean","env",f"QoS theo NIC – {nic}",f"qos_effect_{nic}.png","Mbps")

# ---------------- PHẦN F: CPU efficiency ----------------
plot_bar(agg_df,"env","cpu_per_mbps","qos","CPU Efficiency (CPU%/Mbps)","cpu_efficiency.png","%/Mbps")

# Scatter CPU vs Throughput
plt.figure(figsize=(7,5))
sns.scatterplot(data=df,x="throughput_mbps",y="cpu_mean",hue="env",style="nic_mode")
plt.title("CPU vs Throughput (client)"); plt.tight_layout()
plt.savefig(OUT_DIR/"cpu_vs_throughput_scatter.png"); plt.close()

# ---------------- PHẦN G: Direction ----------------
if set(df["direction"].unique()) & {"cs","sc"}:
    plot_bar(agg_df,"direction","throughput_mbps_mean","env","Direction – Throughput","direction_throughput.png","Mbps")
    plot_bar(agg_df,"direction","latency_ms_mean","env","Direction – Latency","direction_latency.png","ms")
    plot_bar(agg_df,"direction","jitter_ms_mean","env","Direction – Jitter","direction_jitter.png","ms")

# ---------------- PHẦN H: CV ----------------
plot_bar(agg_df,"env","throughput_mbps_cv","qos","CV Throughput","cv_throughput.png","CV%")
plot_bar(agg_df,"env","latency_ms_cv","qos","CV Latency","cv_latency.png","CV%")
plot_bar(agg_df,"env","jitter_ms_cv","qos","CV Jitter","cv_jitter.png","CV%")

# ---------------- PHẦN I: ENV tổng hợp ----------------
plot_bar(agg_df,"env","throughput_mbps_mean","qos","ENV – Throughput","env_throughput.png","Mbps",log=True)
plot_bar(agg_df,"env","latency_ms_mean","qos","ENV – Latency","env_latency.png","ms")
plot_bar(agg_df,"env","cpu_mean_mean","qos","ENV – CPU","env_cpu.png","%")

# ---------------- PHẦN J: BOX ----------------
plot_box(df,"env","throughput_mbps","qos","Throughput Distribution","box_throughput.png","Mbps")

# ---------------- PHẦN K: K8S ----------------
kube_df = agg_df[agg_df["env"].str.contains("K8S|KUBERNETES",na=False)]
if not kube_df.empty:
    plot_bar(kube_df,"pod_config","throughput_mbps_mean","qos","K8S Pod – Throughput","k8s_pod_throughput.png","Mbps")
    plot_bar(kube_df,"pod_config","latency_ms_mean","qos","K8S Pod – Latency","k8s_pod_latency.png","ms")
    plot_bar(kube_df,"pod_config","cpu_mean_mean","qos","K8S Pod – CPU","k8s_pod_cpu.png","%")

# ---------------- PHẦN L: CORRELATION ----------------
corr_cols = ["throughput_mbps","cpu_mean","ram_mean","latency_ms","jitter_ms"]
corr_overall = df[corr_cols].corr()
plt.figure(figsize=(6,5))
sns.heatmap(corr_overall,annot=True,cmap="coolwarm",fmt=".2f")
plt.title("Correlation – Overall"); plt.tight_layout()
plt.savefig(OUT_DIR/"correlation_heatmap_overall.png"); plt.close()

for env_name in sorted(df["env"].unique()):
    sub = df[df["env"]==env_name]
    if len(sub)<3: continue
    corr_env = sub[corr_cols].corr()
    plt.figure(figsize=(6,5))
    sns.heatmap(corr_env,annot=True,cmap="coolwarm",fmt=".2f")
    plt.title(f"Correlation – {env_name}")
    plt.tight_layout(); plt.savefig(OUT_DIR/f"correlation_heatmap_{env_name}.png"); plt.close()

# Pairplot
try:
    pp = sns.pairplot(df.dropna(subset=corr_cols),vars=corr_cols,hue="env",corner=True,
                      plot_kws=dict(alpha=0.6,s=25,linewidth=0))
    pp.fig.suptitle("Pairplot Metrics",y=1.02)
    pp.savefig(OUT_DIR/"pairplot_metrics.png"); plt.close('all')
except Exception as e:
    warnings.warn(f"Pairplot fail: {e}")

# ---------------- XUẤT CSV ----------------
agg_df.to_csv("summary_full_grouped.csv",index=False)
print(f"Đã sinh biểu đồ đầy đủ tại: {OUT_DIR.resolve()}")
