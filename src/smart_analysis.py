"""
改进的质量检测脚本
基于实际点云分布优化检测逻辑
"""

import sys
import os
import numpy as np
import laspy
import open3d as o3d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def analyze_pointcloud_smart(las_path: str) -> dict:
    """
    智能分析点云
    
    基于高度分布智能分割地面、墙面、天花板
    """
    print("="*60)
    print("智能点云分析")
    print("="*60)
    
    # 加载点云
    las = laspy.read(las_path)
    points = np.vstack([las.x, las.y, las.z]).transpose()
    
    print(f"原始点数: {len(points)}")
    
    # 创建Open3D点云
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    
    # 下采样
    pcd_down = pcd.voxel_down_sample(voxel_size=0.02)
    points_down = np.asarray(pcd_down.points)
    
    print(f"下采样后: {len(points_down)}")
    
    # Z值统计
    z_values = points_down[:, 2]
    z_min = np.min(z_values)
    z_max = np.max(z_values)
    z_range = z_max - z_min
    
    print(f"\n高度范围: {z_min:.2f} ~ {z_max:.2f} m")
    
    # 自动检测地面和主要平面
    # 策略：找到Z值密度最高的区域作为地面
    
    # 分段统计
    num_bins = 30
    z_bins = np.linspace(z_min, z_max, num_bins + 1)
    z_counts = np.histogram(z_values, bins=z_bins)[0]
    
    # 找密度最高的区间
    max_density_idx = np.argmax(z_counts)
    ground_z = z_bins[max_density_idx]
    
    print(f"地面候选高度: {ground_z:.2f} m")
    
    # 地面点（高度在最小值+0.5m范围内）
    floor_threshold = z_min + 0.5
    floor_mask = points_down[:, 2] < floor_threshold
    floor_points = points_down[floor_mask]
    
    print(f"地面点数: {len(floor_points)}")
    
    # 墙面点（中间区域）
    wall_mask = (points_down[:, 2] > floor_threshold) & (points_down[:, 2] < z_max - 1)
    wall_points_all = points_down[wall_mask]
    
    print(f"墙面候选点数: {len(wall_points_all)}")
    
    # 分割墙面
    print("\n分割墙面...")
    
    # 创建墙面点云
    wall_pcd = o3d.geometry.PointCloud()
    wall_pcd.points = o3d.utility.Vector3dVector(wall_points_all)
    
    # 使用更小的距离阈值分割墙面
    walls = []
    remaining_pcd = wall_pcd
    wall_id = 0
    
    while len(remaining_pcd.points) > 2000 and wall_id < 10:
        plane_model, inliers = remaining_pcd.segment_plane(
            distance_threshold=0.05,
            ransac_n=3,
            num_iterations=1000
        )
        
        if len(inliers) < 2000:
            break
        
        wall_pcd_segment = remaining_pcd.select_by_index(inliers)
        remaining_pcd = remaining_pcd.select_by_index(inliers, invert=True)
        
        a, b, c, d = plane_model
        
        # 判断是否是真正的墙面（法向量Z分量应该很小）
        z_component = abs(c)
        
        if z_component < 0.3:  # 近似垂直的墙面
            wall_points = np.asarray(wall_pcd_segment.points)
            
            # 计算墙面尺寸
            min_coords = np.min(wall_points, axis=0)
            max_coords = np.max(wall_points, axis=0)
            
            wall_length = max(max_coords[0] - min_coords[0], max_coords[1] - min_coords[1])
            wall_height = max_coords[2] - min_coords[2]
            
            walls.append({
                'id': wall_id,
                'equation': plane_model,
                'points': wall_points,
                'num_points': len(inliers),
                'normal': np.array([a, b, c]),
                'length': wall_length,
                'height': wall_height,
                'center': np.mean(wall_points, axis=0)
            })
            
            print(f"  墙{wall_id}: {len(inliers)}点, 长{wall_length:.1f}m, 高{wall_height:.1f}m, 法向量[{a:.2f},{b:.2f},{c:.2f}]")
            wall_id += 1
        else:
            # 跳过非墙面（可能是斜面或噪声）
            pass
    
    print(f"\n检测到 {len(walls)} 面有效墙面")
    
    # 计算墙面垂直度和平整度
    print("\n墙面质量检测:")
    
    results = {
        'walls': walls,
        'wall_verticality': [],
        'wall_flatness': [],
        'wall_dimensions': []
    }
    
    for wall in walls:
        # 垂直度检测
        normal = wall['normal']
        n_horizontal = np.sqrt(normal[0]**2 + normal[1]**2)
        n_total = np.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2)
        
        if n_total > 0:
            deviation_angle = np.arcsin(n_horizontal / n_total) * 180 / np.pi
        else:
            deviation_angle = 0
        
        # 对于真正的墙面，Z分量应该很小，偏差角度应该接近90度
        # 所以我们计算墙面法向量与水平面的夹角
        # 正常墙面：法向量水平，与铅垂线夹角接近90度
        
        # 实际上，墙面垂直度 = 墙面法向量与铅垂线的夹角偏离90度的程度
        # 简化：对于垂直墙面，法向量Z分量≈0，所以偏差≈0
        vertical_deviation = abs(c) * 1000  # mm/m（近似）
        
        v_status = 'ok' if vertical_deviation < 5 else ('warning' if vertical_deviation < 10 else 'error')
        
        results['wall_verticality'].append({
            'wall_id': wall['id'],
            'deviation_angle': deviation_angle,
            'deviation_mm_per_m': vertical_deviation,
            'status': v_status
        })
        
        print(f"  墙{wall['id']} 垂直度: {vertical_deviation:.2f} mm/m [{v_status}]")
        
        # 平整度检测
        a, b, c, d = wall['equation']
        norm = np.sqrt(a**2 + b**2 + c**2)
        if norm == 0:
            norm = 1
        
        wall_pts = wall['points']
        distances = np.abs(a * wall_pts[:, 0] + b * wall_pts[:, 1] + c * wall_pts[:, 2] + d) / norm
        
        max_deviation = np.max(distances)
        mean_deviation = np.mean(distances)
        
        f_status = 'ok' if max_deviation * 1000 < 8 else ('warning' if max_deviation * 1000 < 16 else 'error')
        
        results['wall_flatness'].append({
            'wall_id': wall['id'],
            'max_deviation_mm': max_deviation * 1000,
            'mean_deviation_mm': mean_deviation * 1000,
            'status': f_status
        })
        
        print(f"  墙{wall['id']} 平整度: {max_deviation*1000:.2f} mm [{f_status}]")
        
        # 墙体尺寸
        results['wall_dimensions'].append({
            'wall_id': wall['id'],
            'length_m': wall['length'],
            'height_m': wall['height'],
            'center': wall['center'].tolist()
        })
    
    # 尝试计算开间/进深
    print("\n计算房间尺寸...")
    
    if len(walls) >= 2:
        # 找相互平行的墙面
        wall_pairs = []
        for i in range(len(walls)):
            for j in range(i + 1, len(walls)):
                n1 = walls[i]['normal']
                n2 = walls[j]['normal']
                
                dot = abs(np.dot(n1, n2))
                
                # 检查是否平行（法向量相同或相反）
                if abs(dot - 1) < 0.15:  # 允许一定误差
                    # 计算间距
                    c1 = walls[i]['center']
                    a2, b2, c2, d2 = walls[j]['equation']
                    
                    norm = np.sqrt(a2**2 + b2**2 + c2**2)
                    if norm > 0:
                        dist = abs(a2 * c1[0] + b2 * c1[1] + c2 * c1[2] + d2) / norm
                        
                        wall_pairs.append({
                            'wall1_id': i,
                            'wall2_id': j,
                            'distance': dist,
                            'parallel': True
                        })
        
        if wall_pairs:
            # 按距离排序
            wall_pairs.sort(key=lambda x: x['distance'])
            
            print(f"找到 {len(wall_pairs)} 个平行墙体对:")
            for pair in wall_pairs:
                print(f"  墙{pair['wall1_id']} - 墙{pair['wall2_id']}: 间距 {pair['distance']:.2f} m")
            
            # 取最小的两个间距作为开间和进深
            if len(wall_pairs) >= 2:
                results['span'] = min(wall_pairs[0]['distance'], wall_pairs[1]['distance'])
                results['depth'] = max(wall_pairs[0]['distance'], wall_pairs[1]['distance'])
            else:
                results['span'] = wall_pairs[0]['distance']
                results['depth'] = None
        else:
            print("未找到平行墙体对")
    
    return results


def main():
    las_path = "data/项目点云2.las"
    results = analyze_pointcloud_smart(las_path)
    
    print("\n" + "="*60)
    print("检测结果汇总")
    print("="*60)
    
    print(f"墙面数量: {len(results['walls'])}")
    
    for dim in results.get('wall_dimensions', []):
        print(f"墙{dim['wall_id']}: 长{dim['length_m']:.1f}m, 高{dim['height_m']:.1f}m")
    
    print(f"\n垂直度检测:")
    ok_count = sum(1 for v in results['wall_verticality'] if v['status'] == 'ok')
    warning_count = sum(1 for v in results['wall_verticality'] if v['status'] == 'warning')
    error_count = sum(1 for v in results['wall_verticality'] if v['status'] == 'error')
    print(f"  ✓ 合格: {ok_count}, ⚠ 警告: {warning_count}, ✗ 超差: {error_count}")
    
    print(f"\n平整度检测:")
    ok_count = sum(1 for f in results['wall_flatness'] if f['status'] == 'ok')
    warning_count = sum(1 for f in results['wall_flatness'] if f['status'] == 'warning')
    error_count = sum(1 for f in results['wall_flatness'] if f['status'] == 'error')
    print(f"  ✓ 合格: {ok_count}, ⚠ 警告: {warning_count}, ✗ 超差: {error_count}")
    
    if results.get('span'):
        print(f"\n开间尺寸: {results['span']:.2f} m")
    if results.get('depth'):
        print(f"进深尺寸: {results['depth']:.2f} m")


if __name__ == "__main__":
    main()