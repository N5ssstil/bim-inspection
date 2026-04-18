"""
根据点云实测数据生成IFC模型（简化方法）
直接使用ifcopenshell创建IFC实体
"""

import ifcopenshell
from datetime import datetime
import numpy as np


def create_simple_ifc(walls_data, room_data, output_path):
    """
    创建简化IFC模型
    """
    
    # 创建新的IFC文件
    ifc = ifcopenshell.file(schema="IFC4")
    
    # 文件头信息
    ifc.create_entity(
        "IfcOrganization",
        Name="OpenClaw",
        Description="Point Cloud Measurement Generated BIM"
    )
    
    # 创建项目
    project = ifc.create_entity(
        "IfcProject",
        GlobalId=ifcopenshell.guid.new(),
        Name="实测BIM模型-点云生成",
        Description=f"根据点云扫描生成的BIM模型，时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    
    # 创建单位
    unit_assignment = ifc.create_entity("IfcUnitAssignment")
    length_unit = ifc.create_entity(
        "IfcSIUnit",
        UnitType="LENGTHUNIT",
        Prefix="MILLI"
    )
    unit_assignment.Units = [length_unit]
    project.UnitsInContext = unit_assignment
    
    # 创建几何表示上下文
    geometric_context = ifc.create_entity(
        "IfcGeometricRepresentationContext",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1.0
    )
    
    # 创建场地
    site_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=ifc.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=ifc.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        )
    )
    
    site = ifc.create_entity(
        "IfcSite",
        GlobalId=ifcopenshell.guid.new(),
        Name="实测场地",
        ObjectPlacement=site_placement
    )
    
    # 创建建筑
    building = ifc.create_entity(
        "IfcBuilding",
        GlobalId=ifcopenshell.guid.new(),
        Name="实测建筑"
    )
    
    # 创建楼层
    floor_z = room_data.get('floor_z', -5600)  # mm
    
    storey = ifc.create_entity(
        "IfcBuildingStorey",
        GlobalId=ifcopenshell.guid.new(),
        Name="标高1",
        Elevation=float(floor_z)
    )
    
    # 建立层级关系
    # 项目 -> 场地 -> 建筑 -> 楼层
    spatial_structure = [
        ("IfcRelAggregates", project, [site]),
        ("IfcRelAggregates", site, [building]),
        ("IfcRelContainedInSpatialStructure", storey, [])  # 空列表，稍后填充
    ]
    
    # 创建墙体
    floor_height = room_data.get('floor_height', 3571)  # mm
    wall_entities = []
    
    for wall_info in walls_data:
        wall_id = wall_info['id']
        wall_name = f"实测墙{wall_id}_点云生成"
        
        # 中心位置（mm）
        center_x = wall_info['center'][0] * 1000
        center_y = wall_info['center'][1] * 1000
        
        # 尺寸（mm）
        length = wall_info['length'] * 1000
        height = wall_info['height'] * 1000
        thickness = 120
        
        # 创建墙体位置
        wall_placement = ifc.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=ifc.create_entity(
                "IfcAxis2Placement3D",
                Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(float(center_x), float(center_y), float(floor_z))),
                Axis=ifc.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=ifc.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
            )
        )
        
        # 创建墙体实体
        wall = ifc.create_entity(
            "IfcWallStandardCase",
            GlobalId=ifcopenshell.guid.new(),
            Name=wall_name,
            ObjectPlacement=wall_placement
        )
        
        wall_entities.append(wall)
        
        print(f"创建墙体: {wall_name}")
        print(f"  位置: ({center_x:.0f}, {center_y:.0f}, {floor_z:.0f}) mm")
        print(f"  尺寸: {length:.0f} x {height:.0f} x {thickness:.0f} mm")
    
    # 创建楼板
    if walls_data:
        # 计算楼板边界
        all_centers_x = [w['center'][0]*1000 for w in walls_data]
        all_centers_y = [w['center'][1]*1000 for w in walls_data]
        
        # 根据墙体方向计算边界
        x_walls = [w for w in walls_data if w['dir'] == 'X']
        y_walls = [w for w in walls_data if w['dir'] == 'Y']
        
        if x_walls:
            slab_x_min = min(w['center'][0]*1000 for w in x_walls)
            slab_x_max = max(w['center'][0]*1000 for w in x_walls)
        else:
            slab_x_min = min(all_centers_x)
            slab_x_max = max(all_centers_x)
        
        if y_walls:
            slab_y_min = min(w['center'][1]*1000 for w in y_walls)
            slab_y_max = max(w['center'][1]*1000 for w in y_walls)
        else:
            slab_y_min = min(all_centers_y)
            slab_y_max = max(all_centers_y)
        
        slab_z = floor_z + floor_height
        slab_center_x = (slab_x_min + slab_x_max) / 2
        slab_center_y = (slab_y_min + slab_y_max) / 2
        
        # 创建楼板位置
        slab_placement = ifc.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=ifc.create_entity(
                "IfcAxis2Placement3D",
                Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(float(slab_center_x), float(slab_center_y), float(slab_z))),
                Axis=ifc.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=ifc.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
            )
        )
        
        # 创建楼板实体
        slab = ifc.create_entity(
            "IfcSlab",
            GlobalId=ifcopenshell.guid.new(),
            Name="实测楼板_点云生成",
            ObjectPlacement=slab_placement,
            PredefinedType="FLOOR"
        )
        
        print(f"\n创建楼板:")
        print(f"  位置: ({slab_center_x:.0f}, {slab_center_y:.0f}, {slab_z:.0f}) mm")
        print(f"  尺寸: {slab_x_max-slab_x_min:.0f} x {slab_y_max-slab_y_min:.0f} x 150 mm")
        
        wall_entities.append(slab)
    
    # 将实体添加到楼层
    for entity in wall_entities:
        ifc.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            RelatedElements=[entity],
            RelatingStructure=storey
        )
    
    # 保存IFC文件
    ifc.write(output_path)
    print(f"\n✓ IFC文件已保存: {output_path}")
    
    return ifc


if __name__ == "__main__":
    # 点云提取的数据
    walls_data = [
        {
            'id': 0,
            'dir': 'X',
            'center': [2.17, -1.03],
            'length': 5.29,
            'height': 3.06,
            'thickness': 0.120
        },
        {
            'id': 1,
            'dir': 'X',
            'center': [-1.59, -0.76],
            'length': 4.75,
            'height': 3.06,
            'thickness': 0.120
        },
        {
            'id': 2,
            'dir': 'Y',
            'center': [0.37, -3.74],
            'length': 3.56,
            'height': 3.06,
            'thickness': 0.120
        },
        {
            'id': 3,
            'dir': 'Y',
            'center': [-0.14, 1.54],
            'length': 3.70,
            'height': 3.05,
            'thickness': 0.120
        }
    ]
    
    room_data = {
        'floor_z': -5600,  # mm
        'floor_height': 3571,  # mm
        'room_width': 3759,  # mm
        'room_depth': 5285  # mm
    }
    
    print("="*60)
    print("根据点云实测数据生成IFC模型")
    print("="*60)
    
    output_path = "data/实测BIM模型.ifc"
    
    create_simple_ifc(walls_data, room_data, output_path)
    
    print("\n" + "="*60)
    print("生成完成!")
    print("="*60)
    print("\n文件对比:")
    print("  原始设计BIM: data/教学楼测量墙体.ifc")
    print("  点云实测BIM: data/实测BIM模型.ifc")
    
    print("\n数据对比:")
    print("  | 项目 | 设计值 | 实测值 | 偏差 |")
    print("  |------|--------|--------|------|")
    print("  | 开间 | 4.06m | 3.76m | -300mm |")
    print("  | 进深 | 5.41m | 5.28m | -130mm |")
    print("  | 净高 | - | 3.57m | - |")