"""
BIM/IFC 模型处理模块
负责读取 IFC 文件并提取房间几何信息
"""

import numpy as np
import ifcopenshell
import ifcopenshell.util.element
from typing import Optional, Dict, List, Any


class BIMProcessor:
    """BIM 模型处理器"""

    def __init__(self):
        self.ifc_file = None
        self.project = None

    def load_ifc(self, filepath: str) -> bool:
        """
        加载 IFC 文件

        Args:
            filepath: .ifc 文件路径

        Returns:
            bool: 是否加载成功
        """
        try:
            self.ifc_file = ifcopenshell.open(filepath)
            self.project = self.ifc_file.by_type('IfcProject')[0]
            print(f"✓ 已加载 IFC 文件: {filepath}")
            print(f"  项目名称: {self.project.Name}")
            return True
        except Exception as e:
            print(f"✗ 加载 IFC 文件失败: {e}")
            return False

    def get_spaces(self) -> List[Any]:
        """
        获取所有空间/房间

        Returns:
            List: IfcSpace 列表
        """
        if self.ifc_file is None:
            raise ValueError("请先加载 IFC 文件")

        spaces = self.ifc_file.by_type('IfcSpace')
        print(f"✓ 找到 {len(spaces)} 个空间")
        return spaces

    def get_walls(self) -> List[Any]:
        """
        获取所有墙体

        Returns:
            List: IfcWall 列表
        """
        if self.ifc_file is None:
            raise ValueError("请先加载 IFC 文件")

        walls = self.ifc_file.by_type('IfcWall')
        print(f"✓ 找到 {len(walls)} 面墙")
        return walls

    def get_slabs(self) -> List[Any]:
        """
        获取所有楼板（地面/天花板）

        Returns:
            List: IfcSlab 列表
        """
        if self.ifc_file is None:
            raise ValueError("请先加载 IFC 文件")

        slabs = self.ifc_file.by_type('IfcSlab')
        print(f"✓ 找到 {len(slabs)} 块楼板")
        return slabs

    def extract_wall_dimensions(self, wall) -> Optional[Dict]:
        """
        提取墙体尺寸

        Args:
            wall: IfcWall 对象

        Returns:
            Dict: 墙体尺寸信息
        """
        try:
            # 获取墙体属性
            property_sets = ifcopenshell.util.element.get_psets(wall)

            # 尝试获取尺寸属性
            dimensions = {
                'id': wall.id(),
                'name': wall.Name,
                'global_id': wall.GlobalId,
                'length': None,
                'width': None,
                'height': None,
                'area': None,
                'volume': None,
                'location': None
            }

            # 从属性集中提取尺寸
            for pset_name, pset in property_sets.items():
                if 'Dimensions' in pset or 'Pset_WallCommon' in pset_name:
                    if 'Length' in pset:
                        dimensions['length'] = pset['Length']
                    if 'Width' in pset:
                        dimensions['width'] = pset['Width']
                    if 'Height' in pset:
                        dimensions['height'] = pset['Height']
                    if 'Area' in pset:
                        dimensions['area'] = pset['Area']
                    if 'Volume' in pset:
                        dimensions['volume'] = pset['Volume']

            # 获取墙体位置（从局部坐标）
            if hasattr(wall, 'ObjectPlacement'):
                placement = wall.ObjectPlacement
                if hasattr(placement, 'RelativePlacement'):
                    location = placement.RelativePlacement.Location
                    if location:
                        dimensions['location'] = list(location.Coordinates)

            return dimensions

        except Exception as e:
            print(f"  警告: 提取墙体 {wall.id()} 尺寸失败: {e}")
            return None

    def extract_slab_elevation(self, slab) -> Optional[Dict]:
        """
        提取楼板标高

        Args:
            slab: IfcSlab 对象

        Returns:
            Dict: 楼板信息
        """
        try:
            info = {
                'id': slab.id(),
                'name': slab.Name,
                'global_id': slab.GlobalId,
                'elevation': None,
                'thickness': None,
                'type': None
            }

            # 获取属性集
            property_sets = ifcopenshell.util.element.get_psets(slab)

            for pset_name, pset in property_sets.items():
                if 'Elevation' in pset:
                    info['elevation'] = pset['Elevation']
                if 'Thickness' in pset or 'Width' in pset:
                    info['thickness'] = pset.get('Thickness') or pset.get('Width')

            # 判断楼板类型（地面/天花板）
            if slab.PredefinedType:
                info['type'] = slab.PredefinedType

            return info

        except Exception as e:
            print(f"  警告: 提取楼板 {slab.id()} 信息失败: {e}")
            return None

    def extract_room_info(self, space) -> Optional[Dict]:
        """
        提取房间信息

        Args:
            space: IfcSpace 对象

        Returns:
            Dict: 房间信息
        """
        try:
            info = {
                'id': space.id(),
                'name': space.Name,
                'global_id': space.GlobalId,
                'long_name': space.LongName if hasattr(space, 'LongName') else None,
                'elevation': None,
                'area': None,
                'volume': None,
                'boundaries': []
            }

            # 获取属性集
            property_sets = ifcopenshell.util.element.get_psets(space)

            for pset_name, pset in property_sets.items():
                if 'Elevation' in pset:
                    info['elevation'] = pset['Elevation']
                if 'Area' in pset:
                    info['area'] = pset['Area']
                if 'Volume' in pset:
                    info['volume'] = pset['Volume']
                if 'NetArea' in pset:
                    info['area'] = pset['NetArea']

            return info

        except Exception as e:
            print(f"  警告: 提取房间 {space.id()} 信息失败: {e}")
            return None

    def get_all_dimensions(self) -> Dict:
        """
        获取所有几何尺寸信息

        Returns:
            Dict: 包含墙体、楼板、房间信息的字典
        """
        if self.ifc_file is None:
            raise ValueError("请先加载 IFC 文件")

        result = {
            'project_name': self.project.Name if self.project else 'Unknown',
            'walls': [],
            'slabs': [],
            'spaces': []
        }

        # 提取墙体
        print("\n提取墙体尺寸...")
        for wall in self.get_walls():
            dim = self.extract_wall_dimensions(wall)
            if dim:
                result['walls'].append(dim)

        # 提取楼板
        print("\n提取楼板信息...")
        for slab in self.get_slabs():
            info = self.extract_slab_elevation(slab)
            if info:
                result['slabs'].append(info)

        # 提取房间
        print("\n提取房间信息...")
        for space in self.get_spaces():
            info = self.extract_room_info(space)
            if info:
                result['spaces'].append(info)

        return result


if __name__ == "__main__":
    # 测试代码
    bim = BIMProcessor()
    # bim.load_ifc("path/to/model.ifc")
    # dims = bim.get_all_dimensions()
    # print(dims)