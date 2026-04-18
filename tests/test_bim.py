"""
测试脚本 - 验证 IFC 读取功能
"""

import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bim_model import BIMProcessor


def test_load_ifc():
    """测试加载 IFC 文件"""
    bim = BIMProcessor()

    # 查找测试文件
    test_file = None
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    for f in os.listdir(data_dir):
        if f.endswith('.ifc'):
            test_file = os.path.join(data_dir, f)
            break

    if test_file:
        print(f"测试文件: {test_file}")
        bim.load_ifc(test_file)
        dims = bim.get_all_dimensions()
        print(f"✓ IFC 加载成功")
        print(f"  墙体: {len(dims['walls'])}")
        print(f"  楼板: {len(dims['slabs'])}")
        print(f"  空间: {len(dims['spaces'])}")
    else:
        print("未找到测试 IFC 文件")
        print("请将测试文件放入 data/ 目录")


if __name__ == "__main__":
    test_load_ifc()