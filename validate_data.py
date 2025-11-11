# validate_data.py
# Script kiểm tra tính hợp lệ và nhất quán của dữ liệu đã tổng hợp

import pandas as pd
import numpy as np
from pathlib import Path

print("=" * 80)
print("VALIDATION REPORT - Kiểm tra dữ liệu tổng hợp")
print("=" * 80)

# ---------------- 1. ĐỌC DỮ LIỆU ----------------
client_df = pd.read_csv("summary_client_only.csv")
grouped_df = pd.read_csv("summary_full_grouped.csv")
comparison_df = pd.read_csv("summary_comparison.csv")
invalid_df = pd.read_csv("invalid_records.csv") if Path("invalid_records.csv").exists() else pd.DataFrame()

print(f"\n1. SỐ LƯỢNG RECORDS")
print(f"   - Client raw: {len(client_df)} records")
print(f"   - Grouped: {len(grouped_df)} groups")
print(f"   - Comparison: {len(comparison_df)} summary rows")
print(f"   - Invalid (loại bỏ): {len(invalid_df)} records")

# ---------------- 2. PHÂN BỐ THEO ENV ----------------
print(f"\n2. PHÂN BỐ THEO ENVIRONMENT")
env_counts = client_df.groupby("env").size()
for env, count in env_counts.items():
    print(f"   - {env}: {count} runs")

# ---------------- 3. PHÂN BỐ THEO QoS ----------------
print(f"\n3. PHÂN BỐ THEO QoS")
qos_counts = client_df.groupby(["env", "qos"]).size()
for (env, qos), count in qos_counts.head(20).items():
    print(f"   - {env:12} / {qos:10}: {count:3} runs")

# ---------------- 4. KIỂM TRA THROUGHPUT ----------------
print(f"\n4. THROUGHPUT STATISTICS (Mbps)")
print(f"   Overall:")
print(f"   - Mean: {client_df['throughput_mbps'].mean():.2f}")
print(f"   - Median: {client_df['throughput_mbps'].median():.2f}")
print(f"   - Min: {client_df['throughput_mbps'].min():.2f}")
print(f"   - Max: {client_df['throughput_mbps'].max():.2f}")

print(f"\n   By Environment (NOQOS only):")
noqos = client_df[client_df["qos"] == "NOQOS"]
for env in sorted(noqos["env"].unique()):
    env_data = noqos[noqos["env"] == env]["throughput_mbps"]
    print(f"   - {env:12}: mean={env_data.mean():8.2f}, std={env_data.std():8.2f}, count={len(env_data):3}")

# ---------------- 5. KIỂM TRA LATENCY ----------------
print(f"\n5. LATENCY STATISTICS (ms)")
latency_data = client_df["latency_ms"].dropna()
print(f"   - Mean: {latency_data.mean():.2f}")
print(f"   - Median: {latency_data.median():.2f}")
print(f"   - Min: {latency_data.min():.2f}")
print(f"   - Max: {latency_data.max():.2f}")

# ---------------- 6. KIỂM TRA NETWORK TYPE ----------------
if "network_type" in grouped_df.columns:
    print(f"\n6. NETWORK TYPE CLASSIFICATION")
    net_type_counts = grouped_df.groupby("network_type").size()
    for net_type, count in net_type_counts.items():
        print(f"   - {net_type}: {count} groups")
    
    print(f"\n   Network Type by Environment:")
    for env in sorted(grouped_df["env"].unique()):
        net_types = grouped_df[grouped_df["env"]==env]["network_type"].unique()
        print(f"   - {env:12}: {', '.join(net_types)}")

# ---------------- 7. KIỂM TRA THROUGHPUT_NORM ----------------
print(f"\n7. THROUGHPUT NORMALIZATION CHECK")
norm_data = grouped_df[["env", "qos", "throughput_mbps_mean", "throughput_norm"]].dropna(subset=["throughput_norm"])
print(f"   Records with valid throughput_norm: {len(norm_data)}/{len(grouped_df)}")

# NOQOS baseline
noqos_norm = norm_data[norm_data["qos"]=="NOQOS"]
print(f"\n   NOQOS Baseline (should be 100% for internal):")
for idx, row in noqos_norm.iterrows():
    print(f"   - {row['env']:12} / {row['qos']:10}: {row['throughput_norm']:6.1f}%")

# QoS effect
print(f"\n   QoS Effect (sample, should be < 100% typically):")
qos_effect = norm_data[norm_data["qos"]!="NOQOS"].head(10)
for idx, row in qos_effect.iterrows():
    print(f"   - {row['env']:12} / {row['qos']:10}: {row['throughput_norm']:6.1f}%")

# ---------------- 8. KIỂM TRA INVALID RECORDS ----------------
if not invalid_df.empty:
    print(f"\n8. INVALID RECORDS ANALYSIS")
    print(f"   Total invalid: {len(invalid_df)}")
    invalid_reasons = invalid_df["invalid_reason"].value_counts()
    for reason, count in invalid_reasons.items():
        print(f"   - {reason}: {count} records")
    
    print(f"\n   Invalid by Environment:")
    invalid_env = invalid_df.groupby("env").size()
    for env, count in invalid_env.items():
        print(f"   - {env}: {count} records")

# ---------------- 9. COMPARISON SUMMARY ----------------
print(f"\n9. COMPARISON SUMMARY")
for category in comparison_df["category"].unique():
    cat_data = comparison_df[comparison_df["category"]==category]
    print(f"   - {category}: {len(cat_data)} rows")

# ---------------- 10. DATA QUALITY CHECKS ----------------
print(f"\n10. DATA QUALITY CHECKS")

# Check 1: Throughput > 0
valid_throughput = (client_df["throughput_mbps"] > 0).sum()
print(f"   ✓ Valid throughput (>0): {valid_throughput}/{len(client_df)} ({valid_throughput/len(client_df)*100:.1f}%)")

# Check 2: Latency reasonable
reasonable_latency = ((client_df["latency_ms"] >= 0) & (client_df["latency_ms"] < 10000)).sum()
print(f"   ✓ Reasonable latency (0-10000ms): {reasonable_latency}/{len(client_df)} ({reasonable_latency/len(client_df)*100:.1f}%)")

# Check 3: CPU < 100%
valid_cpu = (client_df["cpu_mean"] <= 100).sum()
print(f"   ✓ Valid CPU (≤100%): {valid_cpu}/{len(client_df)} ({valid_cpu/len(client_df)*100:.1f}%)")

# Check 4: No extreme outliers in grouped data
if "throughput_mbps_cv" in grouped_df.columns:
    high_cv = (grouped_df["throughput_mbps_cv"] > 50).sum()
    print(f"   ⚠ High CV (>50%): {high_cv}/{len(grouped_df)} groups")

# ---------------- 11. RECOMMENDATIONS ----------------
print(f"\n11. RECOMMENDATIONS")
issues = []

# Check invalid rate
invalid_rate = len(invalid_df) / (len(client_df) + len(invalid_df)) * 100 if not invalid_df.empty else 0
if invalid_rate > 10:
    issues.append(f"   ⚠ Invalid rate cao ({invalid_rate:.1f}%) - kiểm tra lại quy trình đo")

# Check throughput variance
if "throughput_mbps_cv" in grouped_df.columns:
    high_variance = grouped_df[grouped_df["throughput_mbps_cv"] > 30]
    if len(high_variance) > 0:
        issues.append(f"   ⚠ {len(high_variance)} groups có CV > 30% - độ ổn định kém")

# Check missing data
missing_latency = client_df["latency_ms"].isna().sum()
if missing_latency > 0:
    issues.append(f"   ⚠ {missing_latency} records thiếu latency data")

if not issues:
    print("   ✓ Dữ liệu tốt, không có vấn đề nghiêm trọng")
else:
    for issue in issues:
        print(issue)

print("\n" + "=" * 80)
print("VALIDATION COMPLETED")
print("=" * 80)
