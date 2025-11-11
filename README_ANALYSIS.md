# 📊 Data Analysis Pipeline - Hướng dẫn sử dụng

## 📁 Cấu trúc dữ liệu

```
NT531-Project/
├── runs/                          # Dữ liệu thô từ các lần chạy
│   ├── aggregate_results.py       # Script tổng hợp raw data
│   ├── 0. NATIVE/
│   ├── 1. VM/
│   ├── 2. DOCKER/
│   └── 3. KUBERNETES/
├── summary_all_full.csv           # Tất cả records (client + server)
├── summary_client_only.csv        # Chỉ client data (477 records)
├── summary_server_only.csv        # Chỉ server data (bỏ qua trong analysis)
├── summary_full_grouped.csv       # Dữ liệu đã group (48 groups)
├── summary_comparison.csv         # Bảng so sánh tổng hợp (23 rows)
├── invalid_records.csv            # Records bị loại bỏ (70 records)
├── analyze_summary_full.py        # Script phân tích chi tiết
├── analyze_summary_comparison.py  # Script tạo 6 biểu đồ so sánh
├── analyze_summary_overview.py    # Script tạo biểu đồ tổng hợp
├── validate_data.py               # Script kiểm tra dữ liệu
├── plots_client/                  # Biểu đồ chi tiết client
└── plots_summary/                 # Biểu đồ tổng hợp
```

## 🔧 Các thay đổi đã thực hiện

### 1. **Phân loại Network Type** (NEW!)
- **External** (cross-host, real network): NATIVE, VM CROSS-HOSTS, KUBERNETES
- **Internal** (same-host, virtual): DOCKER (all), VM (BRIDGED/NAT/HOST-ONLY)

### 2. **Throughput Normalization đã sửa**

#### ❌ Trước (SAI):
- Tất cả so với NATIVE NOQOS → DOCKER = 103,115% (vô lý!)
- QoS1/QoS2 không có baseline → NaN

#### ✅ Sau (ĐÚNG):
- **External**: so với NATIVE NOQOS (baseline = 40.69 Mbps)
  - NATIVE NOQOS = 100%
  - VM CROSS NOQOS = 92.2%
  - KUBERNETES NOQOS = 61.3%
  
- **Internal**: mỗi env so với chính NOQOS của nó
  - DOCKER BRIDGED NOQOS = 100% (baseline = 41,958 Mbps)
  - DOCKER BRIDGED QOS1 = ~40% (giảm do QoS limit)
  
- **QoS Effect**: so với NOQOS cùng env
  - VD: DOCKER QOS1 / DOCKER NOQOS = 40%

### 3. **Weighted Average trong Summary**
- Trước: Tính mean của mean → sai lệch trọng số
- Sau: Dùng `np.average()` với weights=count → chính xác hơn

### 4. **Loại bỏ Invalid Records**
- 70 records bị loại (12.8%) vì:
  - throughput_nan: 62 (chủ yếu KUBERNETES)
  - cpu_nan: 7
  - throughput_zero: 1

## 🚀 Cách chạy pipeline

### Bước 1: Tổng hợp dữ liệu thô
```powershell
cd runs
python aggregate_results.py
```
**Output:**
- `summary_all_full.csv`
- `summary_client_only.csv`
- `summary_server_only.csv`

### Bước 2: Phân tích và tạo grouped data
```powershell
cd ..
python analyze_summary_full.py
```
**Output:**
- `summary_full_grouped.csv` (48 groups)
- `summary_comparison.csv` (23 rows)
- `invalid_records.csv` (70 invalid)
- `plots_client/*.png` (nhiều biểu đồ chi tiết)

### Bước 3: Tạo biểu đồ so sánh
```powershell
python analyze_summary_comparison.py
python analyze_summary_overview.py
```
**Output:**
- `plots_summary/1_env_fair_comparison.png`
- `plots_summary/2_env_fair_jitter.png`
- `plots_summary/3_qos_throughput_norm.png`
- `plots_summary/4_qos_latency_jitter.png`
- `plots_summary/5_k8s_scaling.png`
- `plots_summary/6_cpu_efficiency.png`
- `plots_summary/overview_summary_all.png`

### Bước 4: Kiểm tra dữ liệu (optional)
```powershell
python validate_data.py
```
**Output:** In ra terminal report chi tiết

## 📈 Hiểu kết quả

### `summary_comparison.csv`

#### ENV_FAIR (So sánh môi trường NOQOS, external network)
| env | throughput_mbps_mean | latency_ms_mean | cpu_mean_mean |
|-----|---------------------|-----------------|---------------|
| NATIVE | 40.69 | 6.00 | 84.99 |
| VM | 27.93 | 22.01 | 2.63 |
| KUBERNETES | 24.93 | 583.66 | 29.64 |

**Giải thích:**
- NATIVE: Baseline (100%), throughput thấp nhất vì cross-host real network
- VM CROSS: 92% của NATIVE, latency tăng 3.7x
- KUBERNETES: 61% của NATIVE, latency cao nhất (583ms) do overhead orchestration

#### QOS_EFFECT (Ảnh hưởng QoS)
| env | qos | throughput_norm | latency_ms_mean |
|-----|-----|----------------|-----------------|
| DOCKER | NOQOS | 100% | 0.11 |
| DOCKER | QOS1 C-_S | 40.6% | 0.10 |
| DOCKER | QOS2 C-_S | 75.6% | 19.36 |

**Giải thích:**
- NOQOS = 100% (baseline)
- QOS1 giảm ~60% throughput (limit bandwidth)
- QOS2 giảm ~25% throughput, tăng latency 180x

#### K8S_POD_SCALING (Scaling theo số Pod)
| pod_config | throughput_mbps_mean | cpu_mean_mean |
|-----------|---------------------|---------------|
| 1 POD | 60.38 | 72.03 |
| 5 POD | 6.99 | 13.33 |
| 10 POD | 1.06 | 12.27 |

**Giải thích:**
- 1 POD: Performance tốt nhất
- 5 POD: Giảm 88% throughput (overhead scheduling)
- 10 POD: Giảm 98% throughput (quá tải cluster)

## ⚠️ Lưu ý quan trọng

### 1. Internal vs External không thể so sánh trực tiếp
- **Internal** (DOCKER, VM BRIDGED): ~30,000-40,000 Mbps (virtual switch nội bộ)
- **External** (NATIVE, VM CROSS, K8S): ~20-40 Mbps (real network card)
- → Chỉ so trong cùng nhóm!

### 2. Server data bị bỏ qua
- Theo yêu cầu, chỉ phân tích **client-side metrics**
- Server data chỉ dùng để đối chiếu (nếu cần debug)

### 3. Invalid rate cao (12.8%)
- Chủ yếu từ KUBERNETES (62/70)
- Nguyên nhân: iperf client không chạy được hoặc không ghi JSON
- → Cần kiểm tra lại quy trình đo K8S

### 4. Coefficient of Variation (CV)
- 15/48 groups có CV > 30% → độ ổn định kém
- Nguyên nhân: network congestion, scheduling overhead
- → Cần tăng số lần chạy hoặc cải thiện điều kiện đo

## 🛠️ Troubleshooting

### Lỗi: `KeyError: 'network_type'`
→ Chạy lại `python analyze_summary_full.py` (đã sửa)

### Lỗi: throughput_norm = NaN hoặc > 100,000%
→ Đã sửa bằng logic phân loại network_type mới

### Warning: SettingWithCopyWarning
→ Đã sửa bằng `.copy()` trong analyze_summary_comparison.py

### Invalid rate quá cao
→ Kiểm tra:
1. File iperf_client.json có tồn tại không?
2. JSON có đúng format không? (dùng `safe_load_json`)
3. sys_usage.log có dữ liệu không?

## 📊 Ý nghĩa các metrics

| Metric | Đơn vị | Ý nghĩa | Giá trị tốt |
|--------|--------|---------|-------------|
| throughput_mbps | Mbps | Băng thông truyền dữ liệu | Càng cao càng tốt |
| latency_ms | ms | Độ trễ mạng | Càng thấp càng tốt |
| packet_loss_pct | % | Tỷ lệ mất gói | 0% |
| jitter_ms | ms | Độ dao động độ trễ | Càng thấp càng tốt |
| cpu_mean | % | CPU sử dụng trung bình | < 80% OK |
| throughput_norm | % | So với baseline | 100% = ngang baseline |
| cpu_per_mbps | %/Mbps | Hiệu suất CPU | Càng thấp càng tốt |

## 📞 Hỗ trợ

Nếu có vấn đề, kiểm tra:
1. `invalid_records.csv` - records bị loại
2. `validate_data.py` - chạy để xem báo cáo chi tiết
3. Logs trong terminal khi chạy scripts

---
**Cập nhật**: 2025-11-11  
**Version**: 2.0 (đã sửa normalization và network classification)
