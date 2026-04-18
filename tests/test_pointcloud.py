"""
测试脚本 - 验证点云读取功能
"""

import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pointcloud import PointCloudProcessor


def test_load_las():
    """测试加载 LAS 文件"""
    pcp = PointCloudProcessor()

    # 查找测试文件
    test_file = None
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    for f in os.listdir(data_dir):
        if f.endswith('.las') or f.endswith('.laz'):
            test_file = os.path.join(data_dir, f)
            break

    if test_file:
        print(f"测试文件: {test_file}")
        pcp.load_las(test_file)
        print(f"✓ 点云加载成功，共 {len(pcp.points)} 个点")
    else:
        print("未找到测试 LAS 文件")
        print("请将测试文件放入 data/ 目录")


if __name__ == "__main__":
    test_load_las()