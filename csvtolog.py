import os

# Thư mục gốc cần tìm (sửa lại nếu cần)
root_dir = "."

for dirpath, dirnames, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename == "sys_usage.csv":
            old_path = os.path.join(dirpath, filename)
            new_path = os.path.join(dirpath, "sys_usage.log")
            os.rename(old_path, new_path)
            print(f"Đã đổi: {old_path} -> {new_path}")

print("Hoàn tất!")
