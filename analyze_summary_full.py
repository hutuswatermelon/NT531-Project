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

# Bổ sung: gán nic_mode cho K8S = "K8S_<số pod>"
mask_k8s = df["env"].str.contains("K8S|KUBERNETES", na=False)
df.loc[mask_k8s, "nic_mode"] = df.loc[mask_k8s, "pod_config"].apply(
    lambda x: f"K8S_{x.upper()}" if isinstance(x, str) and x != "NONE" else "K8S_UNKNOWN"
)


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

# ---------------- PHÂN LOẠI NETWORK TYPE ----------------
# Fair comparison (cross-host, real network): NATIVE, VM CROSS-HOSTS, K8S
# Internal (same-host, virtual): DOCKER all, VM BRIDGED/NAT/HOST-ONLY, K8S internal

def classify_network_type(row):
    """
    Phân loại: 'external' (cross-host) vs 'internal' (same-host virtual)
    """
    env, nic = row["env"], row["nic_mode"]
    if "NATIVE" in env:
        return "external"
    if "VM" in env and "CROSS" in nic:
        return "external"
    if "K8S" in env or "KUBERNETES" in env:
        return "external"  # K8S có thể cross-node
    return "internal"

df["network_type"] = df.apply(classify_network_type, axis=1)

# Legacy is_fair column (for backward compatibility)
df["is_fair"] = df["network_type"] == "external"

# ---------------- CHUẨN HÓA NIC CHO K8S ----------------
mask_k8s = df["env"].str.contains("K8S|KUBERNETES", na=False)

# Chuẩn hóa cột pod_config: viết hoa, bỏ khoảng trắng
df["pod_config"] = df["pod_config"].astype(str).str.upper().str.strip()

# Gán lại nic_mode = K8S_<POD_CONFIG> (nếu có), ngược lại K8S_UNKNOWN
df.loc[mask_k8s, "nic_mode"] = df.loc[mask_k8s, "pod_config"].apply(
    lambda x: f"K8S_{x}" if pd.notna(x) and x not in ["NONE", "NAN", ""] else "K8S_UNKNOWN"
)

# ---------------- GROUP ----------------
agg_cols = ["throughput_mbps","latency_ms","packet_loss_pct","jitter_ms","cpu_mean","ram_mean"]
agg_df = (
    df.groupby(["env","nic_mode","qos","direction","pod_config","is_fair","network_type"],dropna=False)[agg_cols]
    .agg(["mean","std","count","sem"])
)
agg_df.columns = ["_".join(c) for c in agg_df.columns]
agg_df = agg_df.reset_index()

for col in ["throughput_mbps","latency_ms","jitter_ms","cpu_mean"]:
    agg_df[f"{col}_cv"] = (agg_df[f"{col}_std"]/agg_df[f"{col}_mean"]*100).replace([np.inf,-np.inf],np.nan)

agg_df["cpu_per_mbps"] = agg_df["cpu_mean_mean"]/agg_df["throughput_mbps_mean"]

# ===== NORMALIZE THROUGHPUT =====
# Tính baseline riêng cho external và internal
# External: so với NATIVE NOQOS
# Internal: so với DOCKER/VM internal NOQOS (avg của chính group đó)

# 1. External baseline (NATIVE NOQOS only)
external_baseline = agg_df[
    (agg_df["env"]=="NATIVE") & (agg_df["qos"]=="NOQOS")
]["throughput_mbps_mean"].mean()

# 2. Internal baseline (DOCKER/VM internal NOQOS - avg của nhóm)
internal_noqos = agg_df[
    (agg_df["network_type"]=="internal") & (agg_df["qos"]=="NOQOS")
].groupby("env")["throughput_mbps_mean"].mean().to_dict()

def calc_throughput_norm(row):
    """
    Normalize throughput:
    - External → so với NATIVE NOQOS
    - Internal → so với chính env đó NOQOS (nếu có)
    - QoS != NOQOS → so với NOQOS cùng env
    """
    env, qos, net_type = row["env"], row["qos"], row["network_type"]
    throughput = row["throughput_mbps_mean"]
    
    if pd.isna(throughput) or throughput <= 0:
        return np.nan
    
    # External: so với NATIVE
    if net_type == "external":
        if pd.notna(external_baseline) and external_baseline > 0:
            return throughput / external_baseline * 100
        return np.nan
    
    # Internal: so với chính env NOQOS
    if qos == "NOQOS":
        # Tự nó là baseline
        return 100.0
    else:
        # QoS effect: so với NOQOS cùng env
        baseline = internal_noqos.get(env, np.nan)
        if pd.notna(baseline) and baseline > 0:
            return throughput / baseline * 100
        return np.nan

agg_df["throughput_norm"] = agg_df.apply(calc_throughput_norm, axis=1)

# ===== QoS EFFECT (so với NOQOS cùng env + nic_mode) =====
# Tính baseline NOQOS chi tiết cho MỖI (env, nic_mode)
# Điều này quan trọng cho K8S vì có nhiều pod_config khác nhau
env_nic_noqos_baseline = (
    agg_df[agg_df["qos"]=="NOQOS"]
    .groupby(["env","nic_mode"])["throughput_mbps_mean"]
    .mean()
    .to_dict()
)

def calc_qos_effect(row):
    """
    Tính % throughput so với NOQOS của chính (env, nic_mode) đó
    - NOQOS: 100%
    - QoS1/QoS2/QoS3: % so với NOQOS cùng env+nic_mode
    """
    env, nic, qos = row["env"], row["nic_mode"], row["qos"]
    throughput = row["throughput_mbps_mean"]
    
    if pd.isna(throughput) or throughput <= 0:
        return np.nan
    
    # Tìm baseline cho (env, nic_mode)
    baseline = env_nic_noqos_baseline.get((env, nic), np.nan)
    
    if pd.notna(baseline) and baseline > 0:
        return throughput / baseline * 100
    return np.nan

agg_df["qos_effect_pct"] = agg_df.apply(calc_qos_effect, axis=1)

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
# Tách internal (same-host virtual) vs external (cross-host real network)
internal_df = agg_df[agg_df["network_type"]=="internal"]
external_df = agg_df[agg_df["network_type"]=="external"]

# Fair comparison (external + NOQOS only)
fair_df = agg_df[(agg_df["network_type"]=="external") & (agg_df["qos"]=="NOQOS")]

# ---------------- PHẦN A: INTERNAL ----------------
plot_bar(internal_df,"env","throughput_mbps_mean","qos","A1. Internal Throughput","1_internal_throughput.png","Mbps",log=True)
plot_bar(internal_df,"env","latency_ms_mean","qos","A2. Internal Latency","2_internal_latency.png","ms")
plot_bar(internal_df,"env","cpu_mean_mean","qos","A3. Internal CPU","3_internal_cpu.png","%")
plot_bar(internal_df,"env","jitter_ms_mean","qos","A4. Internal Jitter","4_internal_jitter.png","ms")

# ---------------- PHẦN B: FAIR (EXTERNAL NOQOS) ----------------
plot_bar(fair_df,"env","throughput_mbps_mean",None,"B1. External Network Throughput (NOQOS)","5_fair_throughput.png","Mbps")
plot_bar(fair_df,"env","latency_ms_mean",None,"B2. External Network Latency (NOQOS)","6_fair_latency.png","ms")
plot_bar(fair_df,"env","cpu_mean_mean",None,"B3. External Network CPU (NOQOS)","7_fair_cpu.png","%")
plot_bar(fair_df,"env","jitter_ms_mean",None,"B4. External Network Jitter (NOQOS)","8_fair_jitter.png","ms")

# ---------------- PHẦN B2: EXTERNAL ALL QoS ----------------
plot_bar(external_df,"env","throughput_mbps_mean","qos","B5. External Network - All QoS","5b_external_all_qos.png","Mbps")
plot_bar(external_df,"env","latency_ms_mean","qos","B6. External Latency - All QoS","6b_external_latency_qos.png","ms")

# ---------------- PHẦN C: QoS Effect (so với NOQOS cùng env) ----------------
# Hiển thị TẤT CẢ QoS (bao gồm NOQOS = 100%) để dễ so sánh
plot_bar(agg_df,"qos","qos_effect_pct","env","C1. QoS Effect – Throughput (% so với NOQOS)","9_qos_effect_throughput.png","% của NOQOS")
plot_bar(agg_df,"qos","latency_ms_mean","env","C2. QoS Effect – Latency","9b_qos_effect_latency.png","ms")
plot_bar(agg_df,"qos","jitter_ms_mean","env","C3. QoS Effect – Jitter","9c_qos_effect_jitter.png","ms")

# Biểu đồ riêng cho từng env (dễ nhìn hơn)
for env_name in ["DOCKER", "VM", "KUBERNETES"]:
    env_qos = agg_df[agg_df["env"]==env_name]
    if not env_qos.empty:
        plot_bar(env_qos,"qos","qos_effect_pct",None,f"QoS Effect – {env_name} (% so với NOQOS)",f"qos_effect_{env_name}.png","% của NOQOS")

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

# ---------------- BẢNG GỘP SO SÁNH TỔNG HỢP ----------------
summary_tables = []

# ===== 1. So sánh ENV (NOQOS, EXTERNAL only - fair comparison) =====
env_summary = (
    agg_df[(agg_df["qos"]=="NOQOS") & (agg_df["network_type"]=="external")]
    .groupby("env", as_index=False)
    .apply(lambda g: pd.Series({
        "throughput_mbps_mean": np.average(g["throughput_mbps_mean"], weights=g["throughput_mbps_count"]),
        "latency_ms_mean": np.average(g["latency_ms_mean"], weights=g["latency_ms_count"]),
        "cpu_mean_mean": np.average(g["cpu_mean_mean"], weights=g["cpu_mean_count"]),
        "jitter_ms_mean": np.average(g["jitter_ms_mean"], weights=g["jitter_ms_count"])
    }))
    .reset_index(drop=True)
)
env_summary["category"] = "ENV_FAIR"
summary_tables.append(env_summary)

# ===== 2. So sánh ảnh hưởng QoS =====
# KHÔNG average qua nic_mode vì mỗi nic_mode có baseline khác nhau
# Giữ chi tiết (env, nic_mode, qos) để so sánh chính xác
qos_summary = agg_df[["env", "nic_mode", "qos", "qos_effect_pct", "latency_ms_mean", "jitter_ms_mean", "cpu_mean_mean"]].copy()
qos_summary["category"] = "QOS_EFFECT"

# Chỉ lấy các cột cần thiết cho summary
qos_summary = qos_summary[[
    "env", "nic_mode", "qos", "qos_effect_pct", 
    "latency_ms_mean", "jitter_ms_mean", "cpu_mean_mean", "category"
]]
summary_tables.append(qos_summary)

# ===== 3. So sánh K8S theo Pod (nếu có) =====
k8s_data = agg_df[agg_df["env"].str.contains("K8S|KUBERNETES",na=False)]
if not k8s_data.empty:
    k8s_summary = (
        k8s_data.groupby("pod_config", as_index=False)
        .apply(lambda g: pd.Series({
            "throughput_mbps_mean": np.average(g["throughput_mbps_mean"], weights=g["throughput_mbps_count"]),
            "latency_ms_mean": np.average(g["latency_ms_mean"], weights=g["latency_ms_count"]),
            "cpu_mean_mean": np.average(g["cpu_mean_mean"], weights=g["cpu_mean_count"]),
            "jitter_ms_mean": np.average(g["jitter_ms_mean"], weights=g["jitter_ms_count"])
        }))
        .reset_index(drop=True)
    )
    k8s_summary["category"] = "K8S_POD_SCALING"
    summary_tables.append(k8s_summary)

# Gộp tất cả
if summary_tables:
    summary_combined = pd.concat(summary_tables, ignore_index=True)
    summary_combined.to_csv("summary_comparison.csv", index=False)
    print(f"Đã xuất bảng tổng hợp so sánh → summary_comparison.csv ({len(summary_combined)} dòng)")
else:
    print("Không có dữ liệu để xuất summary_comparison.csv")
