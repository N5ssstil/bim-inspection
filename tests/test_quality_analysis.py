"""
质量分析功能测试脚本
测试新增的检测功能：垂直度、平整度、开间/进深
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pointcloud import PointCloudProcessor
from comparison import ComparisonEngine, QUALITY_THRESHOLDS


def create_test_pointcloud():
    """
    创建测试点云数据
    模拟一个房间：地面、天花板、四面墙
    """
    pcp = PointCloudProcessor()
    
    # 创建模拟点云
    # 地面 (z=0)
    floor_points = np.random.uniform(0, 5, (1000, 2))
    floor_points = np.column_stack([floor_points, np.zeros(1000)])
    
    # 天花板 (z=3)
    ceiling_points = np.random.uniform(0, 5, (1000, 2))
    ceiling_points = np.column_stack([ceiling_points, np.full(1000, 3.0)])
    
    # 墙面1 (x=0, y方向墙)
    wall1_points = np.random.uniform(0, 3, (1000, 2))
    wall1_points = np.column_stack([np.zeros(1000), wall1_points[:, 0], wall1_points[:, 1]])
    
    # 墙面2 (x=5, 对面墙)
    wall2_points = np.random.uniform(0, 3, (1000, 2))
    wall2_points = np.column_stack([np.full(1000, 5.0), wall2_points[:, 0], wall2_points[:, 1]])
    
    # 墙面3 (y=0)
    wall3_points = np.random.uniform(0, 3, (1000, 2))
    wall3_points = np.column_stack([wall3_points[:, 0], np.zeros(1000), wall3_points[:, 1]])
    
    # 墙面4 (y=5)
    wall4_points = np.random.uniform(0, 3, (1000, 2))
    wall4_points = np.column_stack([wall4_points[:, 0], np.full(1000, 5.0), wall4_points[:, 1]])
    
    # 合并所有点
    all_points = np.vstack([
        floor_points, ceiling_points,
        wall1_points, wall2_points, wall3_points, wall4_points
    ])
    
    # 创建 Open3D 点云
    import open3d as o3d
    pcp.pcd = o3d.geometry.PointCloud()
    pcp.pcd.points = o3d.utility.Vector3dVector(all_points)
    pcp.points = all_points
    
    print(f"✓ 创建测试点云: {len(all_points)} 个点")
    print(f"  房间尺寸: 5m x 5m x 3m")
    
    return pcp


def test_plane_segmentation():
    """测试平面分割"""
    print("\n" + "="*50)
    print("测试1: 平面分割")
    print("="*50)
    
    pcp = create_test_pointcloud()
    
    # 分割平面
    planes = pcp.segment_planes(distance_threshold=0.1)
    
    print(f"\n✓ 检测到 {len(planes)} 个平面")
    for i, plane in enumerate(planes):
        print(f"  平面{i+1}: {plane['num_points']} 点, 法向量 {plane['normal']}")
    
    return planes


def test_plane_classification():
    """测试平面分类"""
    print("\n" + "="*50)
    print("测试2: 平面分类")
    print("="*50)
    
    pcp = create_test_pointcloud()
    planes = pcp.segment_planes(distance_threshold=0.1)
    
    classified = pcp.classify_planes(planes)
    
    print(f"\n分类结果:")
    if classified.get('floor'):
        print(f"  ✓ 地面: 找到")
    else:
        print(f"  ✗ 地面: 未找到")
    
    if classified.get('ceiling'):
        print(f"  ✓ 天花板: 找到")
    else:
        print(f"  ✗ 天花板: 未找到")
    
    print(f"  墙面: {len(classified.get('walls', []))} 面")
    
    return classified


def test_verticality():
    """测试墙面垂直度检测"""
    print("\n" + "="*50)
    print("测试3: 墙面垂直度检测")
    print("="*50)
    
    pcp = create_test_pointcloud()
    planes = pcp.segment_planes(distance_threshold=0.1)
    classified = pcp.classify_planes(planes)
    
    walls = classified.get('walls', [])
    
    print(f"\n检测 {len(walls)} 面墙的垂直度:")
    for wall in walls:
        result = pcp.calculate_wall_verticality(wall)
        print(f"\n  墙{result['wall_id']}:")
        print(f"    垂直度偏差: {result['deviation_angle']:.2f}°")
        print(f"    每米偏差: {result['deviation_mm_per_m']:.2f} mm/m")
        print(f"    状态: {result['status']}")


def test_flatness():
    """测试墙面平整度检测"""
    print("\n" + "="*50)
    print("测试4: 墙面平整度检测")
    print("="*50)
    
    pcp = create_test_pointcloud()
    planes = pcp.segment_planes(distance_threshold=0.1)
    classified = pcp.classify_planes(planes)
    
    walls = classified.get('walls', [])
    
    print(f"\n检测 {len(walls)} 面墙的平整度:")
    for wall in walls:
        result = pcp.calculate_wall_flatness(wall)
        print(f"\n  墙{result['wall_id']}:")
        print(f"    最大偏差: {result['max_deviation_mm']:.2f} mm")
        print(f"    平均偏差: {result['mean_deviation_mm']:.2f} mm")
        print(f"    标准差: {result['std_deviation_mm']:.2f} mm")
        print(f"    状态: {result['status']}")


def test_span_depth():
    """测试开间/进深计算"""
    print("\n" + "="*50)
    print("测试5: 开间/进深计算")
    print("="*50)
    
    pcp = create_test_pointcloud()
    planes = pcp.segment_planes(distance_threshold=0.1)
    classified = pcp.classify_planes(planes)
    
    result = pcp.calculate_room_span_depth(classified)
    
    print(f"\n房间尺寸:")
    if result.get('span'):
        print(f"  开间: {result['span']:.2f} m")
    else:
        print(f"  开间: 未检测到")
    
    if result.get('depth'):
        print(f"  进深: {result['depth']:.2f} m")
    else:
        print(f"  进深: 未检测到")
    
    print(f"\n墙体对数: {len(result.get('wall_pairs', []))}")


def test_full_analysis():
    """测试完整质量分析"""
    print("\n" + "="*50)
    print("测试6: 完整质量分析")
    print("="*50)
    
    pcp = create_test_pointcloud()
    planes = pcp.segment_planes(distance_threshold=0.1)
    classified = pcp.classify_planes(planes)
    
    results = pcp.full_quality_analysis(classified)
    
    print(f"\n完整分析结果:")
    print(f"  楼层净高: {results.get('floor_height', 'N/A'):.2f} m" if results.get('floor_height') else "  楼层净高: N/A")
    print(f"  开间: {results.get('span', 'N/A'):.2f} m" if results.get('span') else "  开间: N/A")
    print(f"  进深: {results.get('depth', 'N/A'):.2f} m" if results.get('depth') else "  进深: N/A")
    print(f"  墙面垂直度: {len(results.get('wall_verticality', []))} 项")
    print(f"  墙面平整度: {len(results.get('wall_flatness', []))} 项")


def test_comparison_engine():
    """测试对比分析引擎"""
    print("\n" + "="*50)
    print("测试7: 对比分析引擎")
    print("="*50)
    
    engine = ComparisonEngine()
    
    # 测试楼层净高检测
    print("\n楼层净高检测:")
    result = engine.check_floor_height(bim_height=3.0, measured_height=3.01)
    print(f"  设计值: {result.bim_value:.3f} m")
    print(f"  实测值: {result.pointcloud_value:.3f} m")
    print(f"  偏差: {abs(result.deviation) * 1000:.1f} mm")
    print(f"  状态: {result.status}")
    
    # 测试墙面垂直度检测
    print("\n墙面垂直度检测:")
    result = engine.check_wall_verticality(wall_id=1, deviation_mm_per_m=3.5)
    print(f"  实测值: {result.measured_value:.2f} mm/m")
    print(f"  阈值: {result.threshold} mm/m")
    print(f"  状态: {result.status}")
    
    # 测试墙面平整度检测
    print("\n墙面平整度检测:")
    result = engine.check_wall_flatness(wall_id=1, max_deviation_mm=6.0)
    print(f"  实测值: {result.measured_value:.2f} mm")
    print(f"  阈值: {result.threshold} mm")
    print(f"  状态: {result.status}")
    
    # 打印完整报告
    print("\n" + "="*50)
    engine.print_full_report()


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("    质量分析功能测试")
    print("="*60)
    
    try:
        test_plane_segmentation()
        test_plane_classification()
        test_verticality()
        test_flatness()
        test_span_depth()
        test_full_analysis()
        test_comparison_engine()
        
        print("\n" + "="*60)
        print("    所有测试通过!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)