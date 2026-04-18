"""
3D可视化标注模块
展示点云与BIM模型的偏差对比
"""

import numpy as np
import open3d as o3d
import laspy
import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import json


class DeviationVisualizer:
    """偏差可视化器"""
    
    def __init__(self):
        self.pcd_points = None
        self.bim_walls = None
        self.walls_analysis = None
        self.alignment_transform = None
    
    def load_pointcloud(self, las_path: str) -> np.ndarray:
        """加载点云"""
        las = laspy.read(las_path)
        pts = np.vstack([las.x, las.y, las.z]).transpose()
        self.pcd_points = pts
        return pts
    
    def load_bim_walls(self, ifc_path: str) -> List[Dict]:
        """加载BIM墙体"""
        ifc = ifcopenshell.open(ifc_path)
        scale = 0.001
        
        walls = []
        for wall in ifc.by_type('IfcWall'):
            wall_info = {
                'id': wall.id(),
                'name': wall.Name or f'墙{wall.id()}',
                'global_id': wall.GlobalId
            }
            
            # 位置
            if hasattr(wall, 'ObjectPlacement'):
                try:
                    loc = wall.ObjectPlacement.RelativePlacement.Location
                    pos = np.array(list(loc.Coordinates)) * scale
                    wall_info['position'] = pos
                except: pass
            
            # 尝试获取几何形状
            props = ifcopenshell.util.element.get_psets(wall)
            for pset_name, pset in props.items():
                if 'Length' in pset:
                    try: wall_info['length'] = float(pset['Length']) * scale
                    except: pass
                if 'Width' in pset or 'Thickness' in pset:
                    try: wall_info['width'] = float(pset.get('Width') or pset.get('Thickness')) * scale
                    except: pass
                if 'Height' in pset:
                    try: wall_info['height'] = float(pset['Height']) * scale
                    except: pass
            
            walls.append(wall_info)
        
        self.bim_walls = walls
        return walls
    
    def set_alignment(self, transform: np.ndarray):
        """设置配准变换"""
        self.alignment_transform = transform
    
    def analyze_wall_deviation(self, 
                               wall_points: np.ndarray,
                               wall_normal: np.ndarray,
                               design_position: np.ndarray,
                               design_normal: np.ndarray) -> Dict:
        """
        分析墙体偏差
        
        Args:
            wall_points: 墙面点云
            wall_normal: 点云墙面法向量
            design_position: BIM设计位置
            design_normal: BIM设计法向量
            
        Returns:
            Dict: 偏差分析结果
        """
        # 计算位置偏差
        measured_center = np.mean(wall_points, axis=0)
        position_deviation = measured_center[:2] - design_position[:2]  # 仅XY
        position_deviation_mm = np.linalg.norm(position_deviation) * 1000
        
        # 计算角度偏差（垂直度）
        angle_deviation = np.arccos(np.clip(np.dot(wall_normal, design_normal), -1, 1))
        angle_deviation_deg = angle_deviation * 180 / np.pi
        
        # 计算平整度
        # 拟合平面
        a, b, c = wall_normal
        d = -np.dot(wall_normal, measured_center)
        norm = np.sqrt(a*a + b*b + c*c)
        
        distances = np.abs(a * wall_points[:,0] + 
                          b * wall_points[:,1] + 
                          c * wall_points[:,2] + d) / norm
        
        flatness_max = np.max(distances) * 1000  # mm
        flatness_mean = np.mean(distances) * 1000
        flatness_p95 = np.percentile(distances, 95) * 1000
        
        # 计算每点的偏差（用于可视化）
        point_deviation = distances * 1000  # mm
        
        return {
            'position_deviation_mm': position_deviation_mm,
            'angle_deviation_deg': angle_deviation_deg,
            'flatness_max': flatness_max,
            'flatness_mean': flatness_mean,
            'flatness_p95': flatness_p95,
            'point_deviation': point_deviation,
            'measured_center': measured_center
        }
    
    def create_colored_point_cloud(self,
                                   points: np.ndarray,
                                   deviations: np.ndarray,
                                   threshold_ok: float = 8,
                                   threshold_warning: float = 16) -> o3d.geometry.PointCloud:
        """
        根据偏差创建彩色点云
        
        Args:
            points: 点坐标
            deviations: 每点偏差值（mm）
            threshold_ok: 合格阈值
            threshold_warning: 警告阈值
            
        Returns:
            o3d.geometry.PointCloud: 彩色点云
        """
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        # 创建颜色映射
        # 绿色(合格) -> 黄色(警告) -> 红色(超差)
        colors = np.zeros((len(points), 3))
        
        for i, dev in enumerate(deviations):
            if dev <= threshold_ok:
                # 绿色
                colors[i] = [0, 1, 0]  # RGB
            elif dev <= threshold_warning:
                # 渐变到黄色
                ratio = (dev - threshold_ok) / (threshold_warning - threshold_ok)
                colors[i] = [ratio, 1, 0]  # 绿->黄
            else:
                # 渐变到红色
                ratio = min((dev - threshold_warning) / 50, 1)
                colors[i] = [1, 1 - ratio, 0]  # 黄->红
        
        pcd.colors = o3d.utility.Vector3dVector(colors)
        
        return pcd
    
    def create_bim_wall_mesh(self,
                             wall_info: Dict,
                             height: float = 3.0) -> o3d.geometry.TriangleMesh:
        """
        创建BIM墙体网格（用于可视化）
        
        Args:
            wall_info: 墙体信息
            height: 墙体高度
            
        Returns:
            o3d.geometry.TriangleMesh: 墙体网格
        """
        pos = wall_info.get('position', np.array([0, 0, 0]))
        length = wall_info.get('length', 5.0)
        width = wall_info.get('width', 0.12)
        
        # 创建简单的墙体盒子
        # 根据位置和长度创建墙体
        mesh = o3d.geometry.TriangleMesh.create_box(
            width=length,
            height=height,
            depth=width
        )
        
        # 移动到正确位置
        mesh.translate([pos[0] - length/2, pos[1] - width/2, pos[2]])
        
        # 设置颜色（半透明蓝色表示设计）
        mesh.paint_uniform_color([0.2, 0.6, 1.0])
        
        return mesh
    
    def visualize_comparison(self,
                             wall_pcd: o3d.geometry.PointCloud,
                             bim_mesh: o3d.geometry.TriangleMesh,
                             title: str = "施工偏差对比"):
        """
        可视化对比
        
        Args:
            wall_pcd: 点云墙面（带颜色）
            bim_mesh: BIM墙体网格
            title: 标题
        """
        # 创建坐标系
        coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=1.0, origin=[0, 0, 0]
        )
        
        # 可视化
        o3d.visualization.draw_geometries(
            [wall_pcd, bim_mesh, coord_frame],
            window_name=title,
            width=1200,
            height=800,
            left=50,
            top=50,
            point_show_normal=False
        )
    
    def create_deviation_heatmap(self,
                                 wall_points: np.ndarray,
                                 deviations: np.ndarray,
                                 wall_name: str = "墙体") -> str:
        """
        创建偏差热力图
        
        Args:
            wall_points: 墙面点云
            deviations: 偏差值
            wall_name: 墙体名称
            
        Returns:
            str: 图片保存路径
        """
        # 投影到2D平面（XY或XZ）
        # 假设墙面主要在XY平面
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 创建颜色映射
        cmap = LinearSegmentedColormap.from_list(
            'deviation',
            ['green', 'yellow', 'orange', 'red']
        )
        
        # 绘制散点图
        scatter = ax.scatter(
            wall_points[:, 0],
            wall_points[:, 1],
            c=deviations,
            cmap=cmap,
            s=2,
            vmin=0,
            vmax=30
        )
        
        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('偏差 (mm)', fontsize=12)
        
        # 标注阈值线
        cbar.ax.axhline(y=8, color='black', linestyle='--', linewidth=1)
        cbar.ax.text(4, 8, '合格线(8mm)', fontsize=8, va='center')
        cbar.ax.axhline(y=16, color='black', linestyle='--', linewidth=1)
        cbar.ax.text(4, 16, '警告线(16mm)', fontsize=8, va='center')
        
        ax.set_xlabel('X (m)', fontsize=12)
        ax.set_ylabel('Y (m)', fontsize=12)
        ax.set_title(f'{wall_name} 偏差分布热力图', fontsize=14)
        
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        
        # 添加统计信息
        max_dev = np.max(deviations)
        mean_dev = np.mean(deviations)
        p95_dev = np.percentile(deviations, 95)
        
        stats_text = f'最大偏差: {max_dev:.1f}mm\n平均偏差: {mean_dev:.1f}mm\nP95偏差: {p95_dev:.1f}mm'
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存图片
        output_path = f'output/{wall_name}_偏差热力图.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def create_summary_visualization(self,
                                     walls_data: List[Dict],
                                     output_dir: str = 'output') -> Dict:
        """
        创建汇总可视化
        
        Args:
            walls_data: 所有墙体数据
            output_dir: 输出目录
            
        Returns:
            Dict: 生成的图片路径
        """
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        results = {
            'heatmaps': [],
            'summary_chart': None,
            'statistics': {}
        }
        
        # 为每面墙生成热力图
        for wall_data in walls_data:
            wall_name = wall_data.get('name', f'墙{wall_data.get("id", 0)}')
            points = wall_data.get('points')
            deviations = wall_data.get('deviations')
            
            if points is not None and deviations is not None:
                heatmap_path = self.create_deviation_heatmap(
                    points, deviations, wall_name
                )
                results['heatmaps'].append({
                    'wall': wall_name,
                    'path': heatmap_path
                })
        
        # 创建汇总柱状图
        fig, ax = plt.subplots(figsize=(10, 6))
        
        wall_names = [w.get('name', f'墙{w.get("id", i)}') for i, w in enumerate(walls_data)]
        flatness_values = [w.get('flatness_p95', 0) for w in walls_data]
        verticality_values = [w.get('verticality', 0) for w in walls_data]
        
        x = np.arange(len(wall_names))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, flatness_values, width, label='平整度 P95 (mm)', color='steelblue')
        bars2 = ax.bar(x + width/2, verticality_values, width, label='垂直度 (mm/m)', color='coral')
        
        # 添加阈值线
        ax.axhline(y=8, color='green', linestyle='--', label='平整度合格线(8mm)')
        ax.axhline(y=5, color='orange', linestyle='--', label='垂直度合格线(5mm/m)')
        
        ax.set_xlabel('墙体', fontsize=12)
        ax.set_ylabel('偏差值', fontsize=12)
        ax.set_title('墙体质量检测汇总', fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(wall_names)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        summary_path = os.path.join(output_dir, '墙体质量汇总.png')
        plt.savefig(summary_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        results['summary_chart'] = summary_path
        
        # 统计汇总
        results['statistics'] = {
            'total_walls': len(walls_data),
            'flatness_ok': sum(1 for w in walls_data if w.get('flatness_p95', 100) < 8),
            'flatness_warning': sum(1 for w in walls_data if 8 <= w.get('flatness_p95', 100) < 16),
            'flatness_error': sum(1 for w in walls_data if w.get('flatness_p95', 100) >= 16),
            'verticality_ok': sum(1 for w in walls_data if w.get('verticality', 100) < 5),
            'verticality_warning': sum(1 for w in walls_data if 5 <= w.get('verticality', 100) < 10),
            'verticality_error': sum(1 for w in walls_data if w.get('verticality', 100) >= 10)
        }
        
        return results
    
    def generate_3d_scene(self,
                          las_path: str,
                          walls_analysis: List[Dict],
                          output_path: str = 'output/3d_scene.html') -> str:
        """
        生成3D交互场景（使用Plotly或类似工具）
        
        Args:
            las_path: 点云路径
            walls_analysis: 墙面分析数据
            output_path: 输出路径
            
        Returns:
            str: HTML文件路径
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            print("需要安装 plotly: pip install plotly")
            return None
        
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 加载点云（下采样）
        las = laspy.read(las_path)
        pts = np.vstack([las.x, las.y, las.z]).transpose()
        
        # 随机采样（减少数据量）
        sample_idx = np.random.choice(len(pts), min(len(pts), 50000), replace=False)
        pts_sample = pts[sample_idx]
        
        fig = make_subplots(rows=1, cols=1)
        
        # 点云（根据墙面分析着色）
        colors = np.ones(len(pts_sample)) * 5  # 默认灰色
        
        # 添加点云
        fig.add_trace(go.Scatter3d(
            x=pts_sample[:, 0],
            y=pts_sample[:, 1],
            z=pts_sample[:, 2],
            mode='markers',
            marker=dict(
                size=2,
                color=colors,
                colorscale='RdYlGn_r',
                cmin=0,
                cmax=30,
                colorbar=dict(title='偏差(mm)')
            ),
            name='点云'
        ))
        
        # 添加BIM墙体（线框）
        for wall in walls_analysis:
            center = wall.get('center', np.array([0,0,0]))
            length = wall.get('length', 5)
            height = wall.get('height', 3)
            
            # 绘制墙体线框
            x = [center[0] - length/2, center[0] + length/2, 
                 center[0] + length/2, center[0] - length/2,
                 center[0] - length/2]
            y = [center[1], center[1], center[1], center[1], center[1]]
            z = [center[2], center[2], 
                 center[2] + height, center[2] + height,
                 center[2]]
            
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode='lines',
                line=dict(color='blue', width=3),
                name=f'BIM-{wall.get("name", "墙")}'
            ))
        
        fig.update_layout(
            title='施工偏差3D可视化',
            scene=dict(
                xaxis_title='X (m)',
                yaxis_title='Y (m)',
                zaxis_title='Z (m)',
                aspectmode='data'
            ),
            width=1200,
            height=800
        )
        
        fig.write_html(output_path)
        
        return output_path


def create_visualization_from_analysis(las_path: str,
                                       ifc_path: str,
                                       walls_analysis: List[Dict],
                                       output_dir: str = 'output') -> Dict:
    """
    从分析结果创建可视化
    
    Args:
        las_path: 点云路径
        ifc_path: BIM路径
        walls_analysis: 墙面分析数据
        output_dir: 输出目录
        
    Returns:
        Dict: 可视化结果
    """
    viz = DeviationVisualizer()
    
    # 加载数据
    viz.load_pointcloud(las_path)
    viz.load_bim_walls(ifc_path)
    
    # 生成可视化
    results = viz.create_summary_visualization(walls_analysis, output_dir)
    
    # 生成3D场景
    html_path = viz.generate_3d_scene(las_path, walls_analysis, 
                                       os.path.join(output_dir, '3d_scene.html'))
    results['3d_scene'] = html_path
    
    return results


if __name__ == "__main__":
    # 测试
    import sys
    
    print("="*60)
    print("3D可视化标注模块测试")
    print("="*60)
    
    # 模拟数据
    test_walls = [
        {
            'id': 0,
            'name': '墙0',
            'points': np.random.uniform(-2, 2, (1000, 3)),
            'deviations': np.random.uniform(0, 20, 1000),
            'flatness_p95': 6.2,
            'verticality': 0.95,
            'length': 5.3,
            'height': 3.1,
            'center': np.array([0, 0, 0])
        },
        {
            'id': 1,
            'name': '墙1',
            'points': np.random.uniform(-1, 1, (500, 3)),
            'deviations': np.random.uniform(0, 15, 500),
            'flatness_p95': 2.7,
            'verticality': 0.58,
            'length': 4.8,
            'height': 3.1,
            'center': np.array([3, 0, 0])
        }
    ]
    
    viz = DeviationVisualizer()
    results = viz.create_summary_visualization(test_walls, 'output')
    
    print(f"\n生成的可视化:")
    print(f"  热力图: {len(results['heatmaps'])} 张")
    print(f"  汇总图: {results['summary_chart']}")
    print(f"  统计数据: {results['statistics']}")
    
    print("\n✓ 测试完成")