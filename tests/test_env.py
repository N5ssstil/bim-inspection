#!/usr/bin/env python
"""
测试 Python 环境和依赖
"""

import sys

print("=" * 50)
print("Python 环境检查")
print("=" * 50)
print(f"Python 版本: {sys.version}")
print()

# 测试各模块
modules = [
    ('numpy', 'np'),
    ('laspy', None),
    ('open3d', 'o3d'),
    ('ifcopenshell', None),
    ('pandas', 'pd'),
    ('scipy', None),
    ('openpyxl', None),
]

print("依赖检查:")
for mod_name, alias in modules:
    try:
        mod = __import__(mod_name)
        if alias:
            globals()[alias] = mod
        version = getattr(mod, '__version__', 'N/A')
        print(f"  ✓ {mod_name}: {version}")
    except ImportError as e:
        print(f"  ✗ {mod_name}: 未安装")

print()
print("=" * 50)

# 快速测试 Open3D
try:
    import open3d as o3d
    import numpy as np

    print("\nOpen3D 功能测试:")
    # 创建一个简单的点云
    points = np.random.rand(100, 3)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    print(f"  ✓ 成功创建点云: {len(pcd.points)} 个点")

    # RANSAC 平面分割测试
    plane_model, inliers = pcd.segment_plane(
        distance_threshold=0.1,
        ransac_n=3,
        num_iterations=100
    )
    print(f"  ✓ RANSAC 分割正常")

except Exception as e:
    print(f"  ✗ 测试失败: {e}")

print()
print("环境就绪!")