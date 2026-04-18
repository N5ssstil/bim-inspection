"""
点云处理模块
负责读取、预处理和提取点云中的几何信息
"""

import numpy as np
import open3d as o3d
import laspy


class PointCloudProcessor:
    """点云处理器"""

    def __init__(self):
        self.points = None
        self.pcd = None

    def load_las(self, filepath: str) -> bool:
        """
        加载 .las 格式点云文件

        Args:
            filepath: .las 文件路径

        Returns:
            bool: 是否加载成功
        """
        try:
            # 使用 laspy 读取
            las = laspy.read(filepath)

            # 提取 XYZ 坐标
            points = np.vstack([
                las.x,
                las.y,
                las.z
            ]).transpose()

            self.points = points

            # 转换为 Open3D 点云对象
            self.pcd = o3d.geometry.PointCloud()
            self.pcd.points = o3d.utility.Vector3dVector(points)

            # 如果有颜色信息
            if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                colors = np.vstack([
                    las.red,
                    las.green,
                    las.blue
                ]).transpose() / 65535.0  # 归一化到 0-1
                self.pcd.colors = o3d.utility.Vector3dVector(colors)

            print(f"✓ 已加载点云: {len(points):,} 个点")
            return True

        except Exception as e:
            print(f"✗ 加载点云失败: {e}")
            return False

    def preprocess(self,
                   voxel_size: float = 0.01,
                   remove_outliers: bool = True) -> None:
        """
        点云预处理

        Args:
            voxel_size: 体素下采样尺寸（米）
            remove_outliers: 是否移除离群点
        """
        if self.pcd is None:
            raise ValueError("请先加载点云")

        original_count = len(self.pcd.points)

        # 体素下采样
        self.pcd = self.pcd.voxel_down_sample(voxel_size)
        print(f"  下采样: {original_count:,} → {len(self.pcd.points):,} 个点")

        # 移除离群点
        if remove_outliers:
            self.pcd, _ = self.pcd.remove_statistical_outlier(
                nb_neighbors=20,
                std_ratio=2.0
            )
            print(f"  去噪后: {len(self.pcd.points):,} 个点")

    def segment_planes(self,
                       distance_threshold: float = 0.02,
                       ransac_n: int = 3,
                       num_iterations: int = 1000,
                       min_points: int = 1000) -> list:
        """
        分割平面（用于提取墙面、地面、天花板）

        Args:
            distance_threshold: RANSAC 距离阈值（米）
            ransac_n: RANSAC 采样点数
            num_iterations: RANSAC 迭代次数
            min_points: 最小平面点数

        Returns:
            list: 平面列表，每个元素包含 (平面方程, 点云, 法向量)
        """
        if self.pcd is None:
            raise ValueError("请先加载点云")

        planes = []
        remaining_pcd = self.pcd

        while len(remaining_pcd.points) > min_points:
            # RANSAC 分割平面
            plane_model, inliers = remaining_pcd.segment_plane(
                distance_threshold=distance_threshold,
                ransac_n=ransac_n,
                num_iterations=num_iterations
            )

            if len(inliers) < min_points:
                break

            # 提取平面点云
            plane_pcd = remaining_pcd.select_by_index(inliers)
            remaining_pcd = remaining_pcd.select_by_index(inliers, invert=True)

            # 平面方程: ax + by + cz + d = 0
            a, b, c, d = plane_model
            normal = np.array([a, b, c])

            planes.append({
                'equation': plane_model,  # [a, b, c, d]
                'point_cloud': plane_pcd,
                'normal': normal,
                'num_points': len(inliers)
            })

            print(f"  发现平面 #{len(planes)}: {len(inliers):,} 个点, 法向量: [{a:.3f}, {b:.3f}, {c:.3f}]")

        print(f"✓ 共发现 {len(planes)} 个平面")
        return planes

    def classify_planes(self, planes: list,
                        vertical_threshold: float = 0.1) -> dict:
        """
        分类平面（地面、天花板、墙面）

        Args:
            planes: 平面列表
            vertical_threshold: 垂直度判断阈值（法向量Z分量）

        Returns:
            dict: {'floor': ..., 'ceiling': ..., 'walls': [...]}
        """
        floors = []
        ceilings = []
        walls = []

        for plane in planes:
            normal = plane['normal']

            # 判断是否水平面（地面或天花板）
            if abs(abs(normal[2]) - 1.0) < vertical_threshold:
                # 根据高度判断是地面还是天花板
                # 获取平面中心点高度
                plane_points = np.asarray(plane['point_cloud'].points)
                mean_z = np.mean(plane_points[:, 2])

                # 假设较低的为地面
                plane['mean_z'] = mean_z
                if normal[2] > 0:  # 法向量向上
                    floors.append(plane)
                else:
                    ceilings.append(plane)
            else:
                # 墙面
                walls.append(plane)

        # 排序：地面从低到高，天花板从低到高
        floors.sort(key=lambda x: x.get('mean_z', 0))
        ceilings.sort(key=lambda x: x.get('mean_z', 0))

        print(f"✓ 分类结果: {len(floors)} 地面, {len(ceilings)} 天花板, {len(walls)} 墙面")

        return {
            'floor': floors[0] if floors else None,
            'ceiling': ceilings[0] if ceilings else None,
            'walls': walls
        }

    def get_room_dimensions(self, classified_planes: dict) -> dict:
        """
        计算房间尺寸

        Args:
            classified_planes: 分类后的平面

        Returns:
            dict: 房间尺寸 {'height': ..., 'walls': [...]}
        """
        dimensions = {}

        # 计算房间高度
        floor = classified_planes.get('floor')
        ceiling = classified_planes.get('ceiling')

        if floor and ceiling:
            floor_d = floor['equation'][3]
            ceiling_d = ceiling['equation'][3]

            # 平面方程: ax + by + cz + d = 0
            # 对于水平面: z = -d (当 a=b=0, c=1)
            # 高度差
            if floor['normal'][2] > 0:
                floor_height = -floor['equation'][3] / floor['normal'][2]
            else:
                floor_height = -floor['equation'][3] / floor['normal'][2]

            if ceiling['normal'][2] > 0:
                ceiling_height = -ceiling['equation'][3] / ceiling['normal'][2]
            else:
                ceiling_height = -ceiling['equation'][3] / ceiling['normal'][2]

            dimensions['height'] = abs(ceiling_height - floor_height)

        # 计算墙体尺寸
        walls = classified_planes.get('walls', [])
        wall_dimensions = []

        for i, wall in enumerate(walls):
            wall_points = np.asarray(wall['point_cloud'].points)

            # 计算墙的边界框
            min_coords = np.min(wall_points, axis=0)
            max_coords = np.max(wall_points, axis=0)

            # 墙的尺寸（长和宽）
            wall_dims = max_coords - min_coords

            # 墙面法向量方向
            normal = wall['normal']

            wall_dimensions.append({
                'id': i + 1,
                'normal': normal.tolist(),
                'width': float(max(wall_dims[0], wall_dims[1])),  # 墙宽
                'height': float(wall_dims[2]),  # 墙高
                'center': ((min_coords + max_coords) / 2).tolist()
            })

        dimensions['walls'] = wall_dimensions

        return dimensions

    def calculate_wall_verticality(self, wall: dict) -> dict:
        """
        计算墙面垂直度
        
        原理：墙面法向量与铅垂线(0,0,1)的夹角
        
        Args:
            wall: 墙面平面数据
            
        Returns:
            dict: 垂直度检测结果
        """
        normal = wall['normal']  # [a, b, c]
        
        # 铅垂线方向 (垂直向上)
        vertical = np.array([0, 0, 1])
        
        # 计算法向量在水平面上的分量
        n_horizontal = np.sqrt(normal[0]**2 + normal[1]**2)
        n_vertical = abs(normal[2])
        n_total = np.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2)
        
        # 垂直度偏差角度（度）
        if n_total > 0:
            # 偏差角度 = arcsin(水平分量/总长度)
            deviation_angle = np.arcsin(n_horizontal / n_total) * 180 / np.pi
        else:
            deviation_angle = 0
        
        # 每米偏差（mm/m）
        wall_points = np.asarray(wall['point_cloud'].points)
        wall_height = np.max(wall_points[:, 2]) - np.min(wall_points[:, 2])
        deviation_per_meter = deviation_angle / 90 * 1000 if wall_height > 0 else deviation_angle * 1000
        
        return {
            'wall_id': wall.get('id', 0),
            'deviation_angle': float(deviation_angle),  # 角度偏差（度）
            'deviation_mm_per_m': float(deviation_per_meter),  # 每米偏差（mm）
            'normal_vector': normal.tolist(),
            'status': 'ok' if deviation_per_meter <= 5 else ('warning' if deviation_per_meter <= 10 else 'error')
        }

    def calculate_wall_flatness(self, wall: dict, threshold: float = 0.008) -> dict:
        """
        计算墙面平整度
        
        原理：计算每个点到拟合平面的距离
        
        Args:
            wall: 墙面平面数据
            threshold: 平整度阈值（米），默认8mm
            
        Returns:
            dict: 平整度检测结果
        """
        wall_points = np.asarray(wall['point_cloud'].points)
        plane_equation = wall['equation']  # [a, b, c, d]
        
        a, b, c, d = plane_equation
        
        # 计算每个点到平面的距离
        # 距离 = |ax + by + cz + d| / sqrt(a² + b² + c²)
        norm = np.sqrt(a**2 + b**2 + c**2)
        if norm == 0:
            norm = 1
        
        distances = np.abs(a * wall_points[:, 0] + 
                          b * wall_points[:, 1] + 
                          c * wall_points[:, 2] + d) / norm
        
        # 统计平整度
        max_deviation = np.max(distances)  # 最大偏差
        mean_deviation = np.mean(distances)  # 平均偏差
        std_deviation = np.std(distances)  # 标准差
        
        # 超差点数（距离超过阈值）
        exceeded_count = np.sum(distances > threshold)
        exceeded_percent = exceeded_count / len(distances) * 100
        
        return {
            'wall_id': wall.get('id', 0),
            'max_deviation_mm': float(max_deviation * 1000),  # 最大偏差（mm）
            'mean_deviation_mm': float(mean_deviation * 1000),  # 平均偏差（mm）
            'std_deviation_mm': float(std_deviation * 1000),  # 标准差（mm）
            'exceeded_count': int(exceeded_count),  # 超差点数
            'exceeded_percent': float(exceeded_percent),  # 超差百分比
            'threshold_mm': float(threshold * 1000),  # 阈值（mm）
            'status': 'ok' if max_deviation <= threshold else ('warning' if max_deviation <= threshold * 2 else 'error')
        }

    def calculate_room_span_depth(self, classified_planes: dict) -> dict:
        """
        计算房间开间和进深
        
        原理：找出相互平行的墙体对，计算间距
        
        Args:
            classified_planes: 分类后的平面
            
        Returns:
            dict: {'span': 开间, 'depth': 进深, 'wall_pairs': 墙体对}
        """
        walls = classified_planes.get('walls', [])
        
        if len(walls) < 2:
            return {'span': None, 'depth': None, 'wall_pairs': []}
        
        # 计算每面墙的属性
        wall_info = []
        for i, wall in enumerate(walls):
            wall_points = np.asarray(wall['point_cloud'].points)
            normal = wall['normal']
            
            # 墙的中心位置
            center = np.mean(wall_points, axis=0)
            
            # 墙的边界框
            min_coords = np.min(wall_points, axis=0)
            max_coords = np.max(wall_points, axis=0)
            
            # 墙的长度（水平方向的最大跨度）
            length = max(max_coords[0] - min_coords[0], max_coords[1] - min_coords[1])
            
            wall_info.append({
                'id': i,
                'normal': normal,
                'center': center,
                'length': length,
                'min_x': min_coords[0],
                'max_x': max_coords[0],
                'min_y': min_coords[1],
                'max_y': max_coords[1],
                'min_z': min_coords[2],
                'max_z': max_coords[2]
            })
        
        # 找出平行墙体对（法向量平行或反向）
        wall_pairs = []
        for i in range(len(wall_info)):
            for j in range(i + 1, len(wall_info)):
                n1 = wall_info[i]['normal']
                n2 = wall_info[j]['normal']
                
                # 检查是否平行（法向量相同或相反）
                dot_product = np.dot(n1, n2)
                if abs(abs(dot_product) - 1) < 0.1:  # 允许一定误差
                    # 计算墙体间距
                    # 使用墙体中心点到另一个墙平面的距离
                    
                    c1 = wall_info[i]['center']
                    a2, b2, c2, d2 = walls[j]['equation']
                    
                    # 点到平面距离
                    norm = np.sqrt(a2**2 + b2**2 + c2**2)
                    if norm > 0:
                        distance = abs(a2 * c1[0] + b2 * c1[1] + c2 * c1[2] + d2) / norm
                        
                        wall_pairs.append({
                            'wall1_id': i,
                            'wall2_id': j,
                            'distance': float(distance),
                            'wall1_length': wall_info[i]['length'],
                            'wall2_length': wall_info[j]['length'],
                            'parallel': True
                        })
        
        # 根据墙体长度判断开间和进深
        # 开间 = 短边间距，进深 = 长边间距
        if wall_pairs:
            # 按距离排序
            wall_pairs.sort(key=lambda x: x['distance'])
            
            # 取最小的两个间距作为开间和进深
            if len(wall_pairs) >= 2:
                span = wall_pairs[0]['distance']
                depth = wall_pairs[1]['distance']
            else:
                span = wall_pairs[0]['distance']
                depth = None
        else:
            span = None
            depth = None
        
        return {
            'span': span,  # 开间（米）
            'depth': depth,  # 进深（米）
            'wall_pairs': wall_pairs
        }

    def full_quality_analysis(self, classified_planes: dict) -> dict:
        """
        完整质量分析
        
        Args:
            classified_planes: 分类后的平面
            
        Returns:
            dict: 包含所有检测结果
        """
        results = {}
        
        # 1. 楼层净高
        dimensions = self.get_room_dimensions(classified_planes)
        results['floor_height'] = dimensions.get('height')
        
        # 2. 墙面垂直度
        walls = classified_planes.get('walls', [])
        results['wall_verticality'] = []
        for wall in walls:
            v_result = self.calculate_wall_verticality(wall)
            results['wall_verticality'].append(v_result)
        
        # 3. 墙面平整度
        results['wall_flatness'] = []
        for wall in walls:
            f_result = self.calculate_wall_flatness(wall)
            results['wall_flatness'].append(f_result)
        
        # 4. 开间/进深
        span_depth = self.calculate_room_span_depth(classified_planes)
        results['span'] = span_depth.get('span')
        results['depth'] = span_depth.get('depth')
        
        # 5. 原始尺寸信息
        results['walls'] = dimensions.get('walls', [])
        
        return results


if __name__ == "__main__":
    # 测试代码
    pcp = PointCloudProcessor()
    # pcp.load_las("path/to/pointcloud.las")
    # pcp.preprocess()
    # planes = pcp.segment_planes()
    # classified = pcp.classify_planes(planes)
    # dims = pcp.get_room_dimensions(classified)
    # print(dims)