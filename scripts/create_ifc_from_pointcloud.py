"""
根据点云实测数据生成对应的BIM模型（IFC格式）
"""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.unit
from datetime import datetime
import numpy as np


def create_ifc_from_pointcloud(walls_data, room_data, output_path):
    """
    从点云数据创建IFC模型
    
    Args:
        walls_data: 墙体数据列表
        room_data: 房间数据
        output_path: 输出文件路径
    """
    
    # 创建新的IFC文件
    ifc = ifcopenshell.api.run("project.create_file")
    
    # 设置单位为毫米
    unit_assignment = ifcopenshell.api.run("unit.assign_unit", ifc_file=ifc)
    length_unit = ifcopenshell.api.run("unit.add_si_unit", ifc_file=ifc, 
                                        unit_type="LENGTHUNIT", prefix="MILLI")
    ifcopenshell.api.run("unit.assign_unit", ifc_file=ifc, units=[length_unit])
    
    # 创建项目
    project = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                    ifc_class="IfcProject", name="实测BIM模型-点云生成")
    
    # 创建场地
    site = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                ifc_class="IfcSite", name="Site")
    ifcopenshell.api.run("aggregate.assign_object", ifc_file=ifc,
                         relating_object=project, product=site)
    
    # 创建建筑
    building = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                    ifc_class="IfcBuilding", name="实测建筑")
    ifcopenshell.api.run("aggregate.assign_object", ifc_file=ifc,
                         relating_object=site, product=building)
    
    # 创建楼层
    storey = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                  ifc_class="IfcBuildingStorey", name="标高1")
    ifcopenshell.api.run("aggregate.assign_object", ifc_file=ifc,
                         relating_object=building, product=storey)
    
    # 创建墙体类型
    wall_type = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                      ifc_class="IfcWallType", name="实测墙体-120mm")
    
    # 楼层高度
    floor_z = room_data.get('floor_z', -5600)  # mm
    floor_height = room_data.get('floor_height', 3571)  # mm
    
    # 创建墙体
    wall_entities = []
    
    for wall_info in walls_data:
        # 墙体参数
        wall_name = f"实测墙{wall_info['id']}"
        
        # 中心位置
        center_x = wall_info['center'][0] * 1000  # mm
        center_y = wall_info['center'][1] * 1000  # mm
        
        # 墙体尺寸
        length = wall_info['length'] * 1000  # mm
        height = wall_info['height'] * 1000  # mm
        thickness = 120  # mm
        
        # 创建墙体实体
        wall = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                    ifc_class="IfcWallStandardCase", name=wall_name)
        
        # 设置墙体放置位置
        # 使用IfcLocalPlacement
        placement = ifc.by_type("IfcLocalPlacement")[0] if ifc.by_type("IfcLocalPlacement") else \
                    ifcopenshell.api.run("geometry.add_placement", ifc_file=ifc)
        
        # 创建新的位置
        axis2placement = ifc.createIfcAxis2Placement3D(
            ifc.createIfcCartesianPoint([center_x, center_y, floor_z]),
            ifc.createIfcDirection([0.0, 0.0, 1.0]),
            ifc.createIfcDirection([1.0, 0.0, 0.0])
        )
        
        local_placement = ifc.createIfcLocalPlacement(placement, axis2placement)
        wall.ObjectPlacement = local_placement
        
        # 创建墙体几何表示
        # 使用IfcExtrudedAreaSolid
        
        # 创建矩形截面
        if wall_info['dir'] == 'X':
            # X方向墙，截面是Y方向矩形
            rect_profile = ifc.createIfcRectangleProfileDef(
                "AREA",
                wall_name + "_Profile",
                None,  # position
                thickness,
                length
            )
            extrude_direction = ifc.createIfcDirection([0.0, 0.0, 1.0])
        else:
            # Y方向墙，截面是X方向矩形
            rect_profile = ifc.createIfcRectangleProfileDef(
                "AREA",
                wall_name + "_Profile",
                None,
                length,
                thickness
            )
            extrude_direction = ifc.createIfcDirection([0.0, 0.0, 1.0])
        
        # 创建拉伸实体
        extruded_area = ifc.createIfcExtrudedAreaSolid(
            rect_profile,
            None,  # position
            extrude_direction,
            height
        )
        
        # 创建几何表示
        shape_representation = ifc.createIfcShapeRepresentation(
            ifc.by_type("IfcGeometricRepresentationContext")[0],
            "Body",
            "SweptSolid",
            [extruded_area]
        )
        
        # 创建产品定义形状
        product_shape = ifc.createIfcProductDefinitionShape(
            None, None, [shape_representation]
        )
        wall.Representation = product_shape
        
        # 添加到楼层
        ifcopenshell.api.run("spatial.assign_container", ifc_file=ifc,
                             relating_object=storey, product=wall)
        
        wall_entities.append(wall)
        
        print(f"创建墙体: {wall_name}")
        print(f"  位置: ({center_x:.0f}, {center_y:.0f}, {floor_z:.0f}) mm")
        print(f"  尺寸: {length:.0f} x {height:.0f} x {thickness:.0f} mm")
    
    # 创建楼板
    # 计算楼板边界（从墙体位置）
    if walls_data:
        all_x = [w['min'][0]*1000 for w in walls_data] + [w['max'][0]*1000 for w in walls_data]
        all_y = [w['min'][1]*1000 for w in walls_data] + [w['max'][1]*1000 for w in walls_data]
        
        slab_x_min = min(all_x)
        slab_x_max = max(all_x)
        slab_y_min = min(all_y)
        slab_y_max = max(all_y)
        slab_z = floor_z + floor_height
        
        # 创建楼板
        slab = ifcopenshell.api.run("root.create_entity", ifc_file=ifc,
                                    ifc_class="IfcSlabStandardCase", name="实测楼板")
        
        # 楼板位置
        slab_center_x = (slab_x_min + slab_x_max) / 2
        slab_center_y = (slab_y_min + slab_y_max) / 2
        
        axis2placement_slab = ifc.createIfcAxis2Placement3D(
            ifc.createIfcCartesianPoint([slab_center_x, slab_center_y, slab_z]),
            ifc.createIfcDirection([0.0, 0.0, 1.0]),
            ifc.createIfcDirection([1.0, 0.0, 0.0])
        )
        
        slab_placement = ifc.createIfcLocalPlacement(placement, axis2placement_slab)
        slab.ObjectPlacement = slab_placement
        
        # 楼板几何（矩形，厚度150mm）
        slab_profile = ifc.createIfcRectangleProfileDef(
            "AREA",
            "楼板_Profile",
            None,
            slab_x_max - slab_x_min,
            slab_y_max - slab_y_min
        )
        
        slab_extruded = ifc.createIfcExtrudedAreaSolid(
            slab_profile,
            None,
            ifc.createIfcDirection([0.0, 0.0, 1.0]),
            150  # 厚度150mm
        )
        
        slab_shape_rep = ifc.createIfcShapeRepresentation(
            ifc.by_type("IfcGeometricRepresentationContext")[0],
            "Body",
            "SweptSolid",
            [slab_extruded]
        )
        
        slab.Representation = ifc.createIfcProductDefinitionShape(
            None, None, [slab_shape_rep]
        )
        
        ifcopenshell.api.run("spatial.assign_container", ifc_file=ifc,
                             relating_object=storey, product=slab)
        
        print(f"\n创建楼板:")
        print(f"  位置: ({slab_center_x:.0f}, {slab_center_y:.0f}, {slab_z:.0f}) mm")
        print(f"  尺寸: {slab_x_max-slab_x_min:.0f} x {slab_y_max-slab_y_min:.0f} x 150 mm")
    
    # 保存IFC文件
    ifc.write(output_path)
    print(f"\n✓ IFC文件已保存: {output_path}")
    
    return ifc


# 从之前的点云分析数据生成
walls_data = [
    {
        'id': 0,
        'dir': 'X',
        'center': [2.17, -1.03],
        'min': [-1.59, -3.74],
        'max': [2.17, 1.54],
        'length': 5.29,
        'height': 3.06,
        'thickness': 0.120
    },
    {
        'id': 1,
        'dir': 'X',
        'center': [-1.59, -0.76],
        'min': [-1.59, -3.74],
        'max': [-1.59, 1.54],
        'length': 4.75,
        'height': 3.06,
        'thickness': 0.120
    },
    {
        'id': 2,
        'dir': 'Y',
        'center': [0.37, -3.74],
        'min': [-1.59, -3.74],
        'max': [2.17, -3.74],
        'length': 3.56,
        'height': 3.06,
        'thickness': 0.120
    },
    {
        'id': 3,
        'dir': 'Y',
        'center': [-0.14, 1.54],
        'min': [-1.59, 1.54],
        'max': [2.17, 1.54],
        'length': 3.70,
        'height': 3.05,
        'thickness': 0.120
    }
]

room_data = {
    'floor_z': -5.60,
    'floor_height': 3.57,
    'room_width': 3.76,
    'room_depth': 5.28
}

print("="*60)
print("根据点云实测数据生成IFC模型")
print("="*60)

output_path = "data/实测BIM模型.ifc"

create_ifc_from_pointcloud(walls_data, room_data, output_path)

print("\n生成完成!")
print("文件位置: data/实测BIM模型.ifc")
print("\n与原始BIM对比:")
print("  原始设计: data/教学楼测量墙体.ifc")
print("  点云实测: data/实测BIM模型.ifc")