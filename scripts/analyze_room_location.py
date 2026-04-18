"""
深度分析：点云房间定位
找出与BIM尺寸匹配的房间区域
"""

import numpy as np
import laspy
import open3d as o3d

print('='*60)
print('深度分析：点云房间定位')
print('='*60)

# 加载点云
las = laspy.read('data/项目点云2.las')
pts = np.vstack([las.x, las.y, las.z]).transpose()

print(f'点云总点数: {len(pts):,}')
print(f'扫描范围: X={np.min(pts[:,0]):.1f}~{np.max(pts[:,0]):.1f}, Y={np.min(pts[:,1]):.1f}~{np.max(pts[:,1]):.1f}')

# 下采样
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(pts)
pts_down = np.asarray(pcd.voxel_down_sample(voxel_size=0.02).points)

# 分析空间分布：寻找独立的房间区域
print('\n【空间区域分析】')

# 按XY区域分组，找出密度高的区域（可能是房间）
x_bins = np.linspace(np.min(pts_down[:,0]), np.max(pts_down[:,0]), 20)
y_bins = np.linspace(np.min(pts_down[:,1]), np.max(pts_down[:,1]), 20)

# 创建网格密度图
grid_density = np.zeros((19, 19))
x_range = np.max(pts_down[:,0]) - np.min(pts_down[:,0])
y_range = np.max(pts_down[:,1]) - np.min(pts_down[:,1])
x_min_val = np.min(pts_down[:,0])
y_min_val = np.min(pts_down[:,1])

for pt in pts_down:
    x_idx = int((pt[0] - x_min_val) / x_range * 18)
    y_idx = int((pt[1] - y_min_val) / y_range * 18)
    x_idx = min(max(x_idx, 0), 18)
    y_idx = min(max(y_idx, 0), 18)
    grid_density[y_idx, x_idx] += 1

print('XY平面密度分布（高密度区域可能是房间）:')

# 找出高密度区域
threshold = np.max(grid_density) * 0.3
high_density_regions = []

for i in range(19):
    for j in range(19):
        if grid_density[i, j] > threshold:
            x_center = x_bins[j] + (x_bins[j+1] - x_bins[j]) / 2
            y_center = y_bins[i] + (y_bins[i+1] - y_bins[i]) / 2
            high_density_regions.append({
                'x': x_center,
                'y': y_center,
                'density': grid_density[i, j]
            })

print(f'\n发现 {len(high_density_regions)} 个高密度区域')

# Z分层分析（找不同楼层）
z_min = np.min(pts_down[:, 2])
z_values = pts_down[:, 2]
z_bins_list = np.linspace(z_min, np.max(z_values), 10)
z_counts = np.histogram(z_values, bins=z_bins_list)[0]

print('\n高度分布:')
for i, count in enumerate(z_counts):
    if count > 5000:
        print(f'  Z={z_bins_list[i]:.1f}~{z_bins_list[i+1]:.1f}m: {count:,} 点')

# 提取底部房间（Z最小的区域）
bottom_mask = pts_down[:, 2] < z_min + 3.5
bottom_pts = pts_down[bottom_mask]

print(f'\n底部区域点数: {len(bottom_pts):,}')
print(f'底部区域范围: X={np.min(bottom_pts[:,0]):.1f}~{np.max(bottom_pts[:,0]):.1f}, Y={np.min(bottom_pts[:,1]):.1f}~{np.max(bottom_pts[:,1]):.1f}')

# 在底部区域检测房间
ground_z = np.min(bottom_pts[:, 2])
above_mask = bottom_pts[:, 2] > ground_z + 0.5
above_pts = bottom_pts[above_mask]

wall_pcd = o3d.geometry.PointCloud()
wall_pcd.points = o3d.utility.Vector3dVector(above_pts)

fp, fi = wall_pcd.segment_plane(0.02, 3, 1000)
remaining = wall_pcd
if abs(fp[2]) > 0.5:
    remaining = wall_pcd.select_by_index(fi, invert=True)

# 检测所有墙面并分析尺寸
print('\n墙面尺寸分析:')
all_walls = []
wid = 0
while len(remaining.points) > 2000 and wid < 10:
    plane, inliers = remaining.segment_plane(0.02, 3, 1000)
    if len(inliers) < 2000:
        break
    
    seg = remaining.select_by_index(inliers)
    remaining = remaining.select_by_index(inliers, invert=True)
    
    if abs(plane[2]) < 0.15:
        wpts = np.asarray(seg.points)
        min_c = np.min(wpts, axis=0)
        max_c = np.max(wpts, axis=0)
        center = np.mean(wpts, axis=0)
        length = max(max_c[0]-min_c[0], max_c[1]-min_c[1])
        height = max_c[2]-min_c[2]
        
        all_walls.append({
            'id': wid,
            'center': center,
            'min': min_c,
            'max': max_c,
            'length': length,
            'height': height,
            'points': len(inliers),
            'normal': plane[:3]
        })
        
        print(f'  墙{wid}: 中心({center[0]:.1f},{center[1]:.1f}), 长{length:.1f}m, 高{height:.1f}m')
        wid += 1

print(f'\n共检测到 {len(all_walls)} 面墙')

# 寻找约4x5m的房间
print('\n寻找匹配BIM尺寸的房间 (约4x5m):')

# 按墙方向分组
x_walls = [w for w in all_walls if abs(w['normal'][0]) > abs(w['normal'][1])]
y_walls = [w for w in all_walls if abs(w['normal'][1]) >= abs(w['normal'][0])]

print(f'X方向墙: {len(x_walls)} 面')
print(f'Y方向墙: {len(y_walls)} 面')

# 检查所有可能的房间组合
rooms = []
for x1 in x_walls:
    for x2 in x_walls:
        if x1['id'] != x2['id']:
            x_spacing = abs(x1['center'][0] - x2['center'][0])
            if 3.5 < x_spacing < 5.0:  # 接近4m
                for y1 in y_walls:
                    for y2 in y_walls:
                        if y1['id'] != y2['id']:
                            y_spacing = abs(y1['center'][1] - y2['center'][1])
                            if 4.5 < y_spacing < 6.5:  # 接近5.4m
                                # 找到匹配的房间
                                room_center_x = (x1['center'][0] + x2['center'][0]) / 2
                                room_center_y = (y1['center'][1] + y2['center'][1]) / 2
                                
                                rooms.append({
                                    'walls': [x1['id'], x2['id'], y1['id'], y2['id']],
                                    'x_span': x_spacing,
                                    'y_span': y_spacing,
                                    'center': (room_center_x, room_center_y)
                                })

if rooms:
    print(f'\n找到 {len(rooms)} 个可能的房间:')
    for r in rooms[:5]:
        print(f'  房间: 开间{r["x_span"]:.2f}m, 进深{r["y_span"]:.2f}m, 中心({r["center"][0]:.1f},{r["center"][1]:.1f})')
else:
    print('\n未找到完全匹配的房间')
    
    # 显示最接近的尺寸组合
    if x_walls and y_walls:
        x_spans = []
        for i, x1 in enumerate(x_walls):
            for j, x2 in enumerate(x_walls):
                if i < j:
                    x_spans.append(abs(x1['center'][0] - x2['center'][0]))
        
        y_spans = []
        for i, y1 in enumerate(y_walls):
            for j, y2 in enumerate(y_walls):
                if i < j:
                    y_spans.append(abs(y1['center'][1] - y2['center'][1]))
        
        print('\n现有墙面间距:')
        print(f'  X方向间距: {sorted(x_spans) if x_spans else "无"}')
        print(f'  Y方向间距: {sorted(y_spans) if y_spans else "无"}')
        
        print('\n可能原因:')
        print('  1. 点云扫描区域与BIM模型区域不对应')
        print('  2. 点云中的房间尺寸与BIM设计存在较大偏差')
        print('  3. 需要用户提供配准控制点')