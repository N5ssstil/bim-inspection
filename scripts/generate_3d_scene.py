"""
生成3D交互场景脚本
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np
import laspy
import open3d as o3d
from visualization import DeviationVisualizer

print('='*60)
print('生成3D交互场景')
print('='*60)

# 加载点云
las = laspy.read('data/项目点云2.las')
pts = np.vstack([las.x, las.y, las.z]).transpose()

pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(pts)
pts_down = np.asarray(pcd.voxel_down_sample(voxel_size=0.02).points)

# 检测墙面
z_min = np.min(pts_down[:, 2])
ground_mask = pts_down[:, 2] < z_min + 0.3
ground_z = np.mean(pts_down[ground_mask][:, 2])

above_mask = pts_down[:, 2] > ground_z + 0.5
above_pts = pts_down[above_mask]

wall_pcd = o3d.geometry.PointCloud()
wall_pcd.points = o3d.utility.Vector3dVector(above_pts)

fp, fi = wall_pcd.segment_plane(0.02, 3, 1000)
remaining = wall_pcd
if abs(fp[2]) > 0.5:
    remaining = wall_pcd.select_by_index(fi, invert=True)

walls_data = []
wid = 0
while len(remaining.points) > 3000 and wid < 4:
    plane, inliers = remaining.segment_plane(0.02, 3, 1000)
    if len(inliers) < 3000:
        break
    
    seg = remaining.select_by_index(inliers)
    remaining = remaining.select_by_index(inliers, invert=True)
    
    if abs(plane[2]) < 0.15:
        wpts = np.asarray(seg.points)
        
        walls_data.append({
            'id': wid,
            'name': f'Wall {wid}',
            'length': max(np.max(wpts[:, 0]) - np.min(wpts[:, 0]), np.max(wpts[:, 1]) - np.min(wpts[:, 1])),
            'height': np.max(wpts[:, 2]) - np.min(wpts[:, 2]),
            'center': np.mean(wpts, axis=0)
        })
        wid += 1

print(f'检测到 {len(walls_data)} 面墙')

# 生成3D HTML场景
viz = DeviationVisualizer()
os.makedirs('output', exist_ok=True)
html_path = viz.generate_3d_scene('data/项目点云2.las', walls_data, 'output/3d_scene.html')

if html_path:
    print(f'\n✓ 3D交互场景已生成: {html_path}')
    print('  可在浏览器中打开查看')
else:
    print('\n提示: 安装 plotly 可生成交互式3D场景')