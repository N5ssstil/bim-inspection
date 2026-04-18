"""
配准模块
实现BIM模型与点云的坐标对齐
"""

import numpy as np
import open3d as o3d
from typing import Dict, List, Tuple, Optional
import ifcopenshell
import ifcopenshell.util.element


class AlignmentEngine:
    """配准引擎 - BIM与点云坐标对齐"""
    
    def __init__(self):
        self.bim_points = None
        self.pcd_points = None
        self.transformation = None
        self.alignment_quality = None
    
    def extract_bim_geometry(self, ifc_path: str) -> Dict:
        """
        从IFC提取几何点
        
        Args:
            ifc_path: IFC文件路径
            
        Returns:
            Dict: BIM几何数据
        """
        ifc = ifcopenshell.open(ifc_path)
        
        bim_data = {
            'walls': [],
            'slabs': [],
            'points': []
        }
        
        # 单位转换（IFC通常用mm，转为m）
        scale = 0.001  # mm -> m
        
        walls = ifc.by_type('IfcWall')
        for wall in walls:
            wall_info = {
                'id': wall.id(),
                'name': wall.Name or f'Wall_{wall.id()}',
                'global_id': wall.GlobalId,
                'points': [],
                'bounds': None
            }
            
            # 获取墙体位置
            if hasattr(wall, 'ObjectPlacement'):
                placement = wall.ObjectPlacement
                if hasattr(placement, 'RelativePlacement'):
                    loc = placement.RelativePlacement.Location
                    if loc and hasattr(loc, 'Coordinates'):
                        coords = list(loc.Coordinates)
                        # 转换为米
                        pos = np.array(coords) * scale
                        wall_info['position'] = pos.tolist()
                        # 添加墙体中心点
                        bim_data['points'].append(pos)
            
            # 尝试获取几何表示
            if hasattr(wall, 'Representation'):
                rep = wall.Representation
                if rep:
                    # 简化处理：使用位置点
                    pass
            
            # 获取尺寸属性
            props = ifcopenshell.util.element.get_psets(wall)
            for pset_name, pset in props.items():
                wall_info['properties'] = pset
                if 'Length' in pset:
                    wall_info['length_m'] = float(pset['Length']) * scale if isinstance(pset['Length'], (int, float)) else None
                if 'Width' in pset or 'Thickness' in pset:
                    val = pset.get('Width') or pset.get('Thickness')
                    wall_info['width_m'] = float(val) * scale if isinstance(val, (int, float)) else None
                if 'Height' in pset:
                    wall_info['height_m'] = float(pset['Height']) * scale if isinstance(pset['Height'], (int, float)) else None
            
            bim_data['walls'].append(wall_info)
        
        # 提取楼板
        slabs = ifc.by_type('IfcSlab')
        for slab in slabs:
            slab_info = {
                'id': slab.id(),
                'name': slab.Name or f'Slab_{slab.id()}',
                'points': []
            }
            
            if hasattr(slab, 'ObjectPlacement'):
                placement = slab.ObjectPlacement
                if hasattr(placement, 'RelativePlacement'):
                    loc = placement.RelativePlacement.Location
                    if loc and hasattr(loc, 'Coordinates'):
                        coords = list(loc.Coordinates)
                        pos = np.array(coords) * scale
                        slab_info['position'] = pos.tolist()
                        bim_data['points'].append(pos)
            
            bim_data['slabs'].append(slab_info)
        
        # 转换点列表
        if bim_data['points']:
            bim_data['points'] = np.array(bim_data['points'])
        
        return bim_data
    
    def estimate_initial_alignment(self, 
                                   bim_data: Dict,
                                   pcd_points: np.ndarray) -> np.ndarray:
        """
        估算初始配准变换
        
        方法：基于墙体位置的粗匹配
        
        Args:
            bim_data: BIM几何数据
            pcd_points: 点云坐标
            
        Returns:
            np.ndarray: 4x4变换矩阵
        """
        if bim_data['points'].shape[0] == 0:
            # 没有BIM点，返回单位矩阵
            return np.eye(4)
        
        # BIM中心点
        bim_center = np.mean(bim_data['points'], axis=0)
        
        # 点云中心点
        pcd_center = np.mean(pcd_points, axis=0)
        
        # 计算平移向量（将BIM移动到点云坐标系）
        translation = pcd_center - bim_center
        
        # 构建变换矩阵
        transform = np.eye(4)
        transform[:3, 3] = translation
        
        print(f"粗配准估算:")
        print(f"  BIM中心: ({bim_center[0]:.2f}, {bim_center[1]:.2f}, {bim_center[2]:.2f})")
        print(f"  点云中心: ({pcd_center[0]:.2f}, {pcd_center[1]:.2f}, {pcd_center[2]:.2f})")
        print(f"  平移: ({translation[0]:.2f}, {translation[1]:.2f}, {translation[2]:.2f})")
        
        return transform
    
    def refine_alignment_icp(self,
                             bim_pcd: o3d.geometry.PointCloud,
                             scan_pcd: o3d.geometry.PointCloud,
                             init_transform: np.ndarray = None,
                             max_iterations: int = 50,
                             tolerance: float = 1e-6) -> Tuple[np.ndarray, float]:
        """
        ICP精细配准
        
        Args:
            bim_pcd: BIM点云
            scan_pcd: 扫描点云
            init_transform: 初始变换矩阵
            max_iterations: 最大迭代次数
            tolerance: 收敛阈值
            
        Returns:
            Tuple: (变换矩阵, 配准误差)
        """
        if init_transform is None:
            init_transform = np.eye(4)
        
        # 下采样以提高ICP速度
        bim_down = bim_pcd.voxel_down_sample(voxel_size=0.05)
        scan_down = scan_pcd.voxel_down_sample(voxel_size=0.05)
        
        # 计算初始对齐后的位置
        bim_down.transform(init_transform)
        
        # ICP配准
        result = o3d.pipelines.registration.registration_icp(
            source=bim_down,
            target=scan_down,
            max_correspondence_distance=0.5,
            init=init_transform,
            estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
                max_iteration=max_iterations,
                relative_rmse=tolerance
            )
        )
        
        print(f"\nICP精细配准结果:")
        print(f"  配准误差 (RMSE): {result.inlier_rmse:.4f}")
        print(f"  对应点数: {len(result.correspondence_set)}")
        print(f"  fitness: {result.fitness:.4f}")
        
        return result.transformation, result.inlier_rmse
    
    def create_bim_point_cloud(self, bim_data: Dict) -> o3d.geometry.PointCloud:
        """
        从BIM数据创建点云表示
        
        Args:
            bim_data: BIM几何数据
            
        Returns:
            o3d.geometry.PointCloud: BIM点云
        """
        points = []
        
        for wall in bim_data['walls']:
            pos = wall.get('position')
            if pos:
                # 为每面墙生成边界点
                length = wall.get('length_m', 5.0)  # 默认5米
                width = wall.get('width_m', 0.12)  # 默认120mm墙
                height = wall.get('height_m', 3.0)  # 默认3米高
                
                # 生成墙体表面的点
                # 这里简化处理，生成墙顶、墙底、墙角的点
                center = np.array(pos)
                
                # 生成墙面点（简化为8个角点）
                for dx in [-length/2, length/2]:
                    for dy in [-width/2, width/2]:
                        for dz in [0, height]:
                            pt = center + np.array([dx, dy, dz])
                            points.append(pt)
        
        if points:
            points = np.array(points)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            return pcd
        else:
            # 使用BIM提取的点
            if bim_data['points'].shape[0] > 0:
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(bim_data['points'])
                return pcd
        
        return None
    
    def full_alignment(self,
                       ifc_path: str,
                       las_path: str) -> Dict:
        """
        完整配准流程
        
        Args:
            ifc_path: IFC文件路径
            las_path: LAS文件路径
            
        Returns:
            Dict: 配准结果
        """
        import laspy
        
        print("\n" + "="*50)
        print("配准流程开始")
        print("="*50)
        
        # 1. 提取BIM几何
        print("\n[1] 提取BIM几何...")
        bim_data = self.extract_bim_geometry(ifc_path)
        print(f"  提取到 {len(bim_data['walls'])} 面墙, {len(bim_data['slabs'])} 块楼板")
        print(f"  BIM点数: {bim_data['points'].shape[0]}")
        
        # 2. 加载点云
        print("\n[2] 加载点云...")
        las = laspy.read(las_path)
        pcd_points = np.vstack([las.x, las.y, las.z]).transpose()
        print(f"  点云点数: {len(pcd_points)}")
        
        # 3. 估算初始对齐
        print("\n[3] 估算初始配准...")
        init_transform = self.estimate_initial_alignment(bim_data, pcd_points)
        
        # 4. 创建BIM点云
        print("\n[4] 创建BIM点云表示...")
        bim_pcd = self.create_bim_point_cloud(bim_data)
        if bim_pcd:
            print(f"  BIM点云点数: {len(bim_pcd.points)}")
        
        # 5. 创建扫描点云对象
        scan_pcd = o3d.geometry.PointCloud()
        scan_pcd.points = o3d.utility.Vector3dVector(pcd_points)
        
        # 6. ICP精细配准（如果BIM点云有效）
        if bim_pcd and len(bim_pcd.points) > 10:
            print("\n[5] ICP精细配准...")
            final_transform, rmse = self.refine_alignment_icp(
                bim_pcd, scan_pcd, init_transform
            )
        else:
            print("\n[5] 跳过ICP（BIM点云不足）")
            final_transform = init_transform
            rmse = None
        
        # 保存结果
        self.bim_points = bim_data['points']
        self.pcd_points = pcd_points
        self.transformation = final_transform
        self.alignment_quality = {
            'init_transform': init_transform,
            'final_transform': final_transform,
            'rmse': rmse,
            'bim_data': bim_data
        }
        
        print("\n" + "="*50)
        print("配准完成")
        print("="*50)
        
        return self.alignment_quality
    
    def apply_alignment(self, bim_data: Dict) -> Dict:
        """
        应用配准变换到BIM数据
        
        Args:
            bim_data: 原始BIM数据
            
        Returns:
            Dict: 配准后的BIM数据（点云坐标系）
        """
        if self.transformation is None:
            return bim_data
        
        aligned_data = bim_data.copy()
        
        # 变换墙体位置
        for wall in aligned_data['walls']:
            if 'position' in wall:
                pos = np.array(wall['position'])
                # 应用变换
                pos_h = np.append(pos, 1)  # 齐次坐标
                pos_aligned = self.transformation @ pos_h
                wall['aligned_position'] = pos_aligned[:3].tolist()
        
        return aligned_data


if __name__ == "__main__":
    # 测试代码
    align = AlignmentEngine()
    # result = align.full_alignment("model.ifc", "scan.las")