# run_full_pipeline.py
# Script tổng hợp chạy toàn bộ pipeline phân tích

import subprocess
import sys
from pathlib import Path

def run_script(script_path, description):
    """Chạy một Python script và báo cáo kết quả"""
    print(f"\n{'='*80}")
    print(f"▶ {description}")
    print(f"  Script: {script_path}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        
        # In output
        if result.stdout:
            print(result.stdout)
        
        # Kiểm tra lỗi
        if result.returncode != 0:
            print(f"❌ LỖI khi chạy {script_path}:")
            print(result.stderr)
            return False
        else:
            print(f"✅ Hoàn thành: {script_path}")
            return True
            
    except Exception as e:
        print(f"❌ Exception khi chạy {script_path}: {e}")
        return False

def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                   DATA ANALYSIS PIPELINE - NT531 PROJECT                  ║
║                      Phân tích dữ liệu đo hiệu năng mạng                  ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
    
    success_count = 0
    total_count = 0
    
    # Pipeline steps
    steps = [
        ("runs/aggregate_results.py", "Bước 1: Tổng hợp dữ liệu thô từ runs/"),
        ("analyze_summary_full.py", "Bước 2: Phân tích chi tiết và tạo grouped data"),
        ("analyze_summary_comparison.py", "Bước 3: Tạo biểu đồ so sánh (6 charts)"),
        ("analyze_summary_overview.py", "Bước 4: Tạo biểu đồ tổng hợp"),
        ("validate_data.py", "Bước 5: Kiểm tra và validate dữ liệu"),
    ]
    
    for script_path, description in steps:
        total_count += 1
        if run_script(script_path, description):
            success_count += 1
        else:
            print(f"\n⚠️  Pipeline dừng lại tại: {script_path}")
            print("   Vui lòng kiểm tra lỗi và chạy lại.")
            break
    
    # Summary
    print(f"\n{'='*80}")
    print(f"PIPELINE SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Thành công: {success_count}/{total_count} bước")
    
    if success_count == total_count:
        print(f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                          🎉 HOÀN THÀNH PIPELINE 🎉                        ║
╚═══════════════════════════════════════════════════════════════════════════╝

📁 OUTPUT FILES:
   - summary_all_full.csv          (all records: client + server)
   - summary_client_only.csv       (client only: 477 records)
   - summary_full_grouped.csv      (grouped: 48 groups)
   - summary_comparison.csv        (comparison: 23 rows)
   - invalid_records.csv           (invalid: 70 records)

📊 PLOTS:
   - plots_client/                 (detailed charts)
   - plots_summary/                (summary charts)
     • 1_env_fair_comparison.png
     • 2_env_fair_jitter.png
     • 3_qos_throughput_norm.png
     • 4_qos_latency_jitter.png
     • 5_k8s_scaling.png
     • 6_cpu_efficiency.png
     • overview_summary_all.png

📖 Xem README_ANALYSIS.md để biết chi tiết!
        """)
    else:
        print(f"\n❌ Pipeline không hoàn thành. Vui lòng kiểm tra lỗi.")
    
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
