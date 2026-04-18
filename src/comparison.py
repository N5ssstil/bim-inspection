"""
对比分析模块
对比 BIM 模型和点云数据的尺寸差异
支持：楼层净高、开间、进深、墙面垂直度、墙面平整度
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DimensionComparison:
    """尺寸对比结果"""
    name: str
    bim_value: float
    pointcloud_value: float
    deviation: float  # 偏差值
    deviation_percent: float  # 偏差百分比
    status: str  # 'ok', 'warning', 'error'
    category: str = '尺寸'  # 检测类别


@dataclass
class QualityCheck:
    """质量检测结果（不对比BIM）"""
    name: str
    measured_value: float
    threshold: float
    deviation: float
    status: str  # 'ok', 'warning', 'error'
    category: str = '质量'


# 质量标准阈值（单位：mm）
QUALITY_THRESHOLDS = {
    'floor_height': 10,      # 楼层净高偏差 ±10mm
    'span': 15,              # 开间尺寸偏差 ±15mm
    'depth': 15,             # 进深尺寸偏差 ±15mm
    'verticality': 5,        # 墙面垂直度 ≤5mm/m
    'flatness': 8,           # 墙面平整度 ≤8mm/2m
}


class ComparisonEngine:
    """对比分析引擎"""

    def __init__(self, tolerance: float = 0.01):
        """
        初始化

        Args:
            tolerance: 容差范围（米），默认 1cm
        """
        self.tolerance = tolerance
        self.results = []

    def compare_height(self,
                       bim_height: float,
                       pointcloud_height: float,
                       name: str = "房间高度") -> DimensionComparison:
        """
        对比房间高度

        Args:
            bim_height: BIM 模型中的高度
            pointcloud_height: 点云测量高度
            name: 名称

        Returns:
            DimensionComparison: 对比结果
        """
        deviation = pointcloud_height - bim_height
        deviation_percent = (deviation / bim_height) * 100 if bim_height != 0 else 0

        # 判断状态
        if abs(deviation) <= self.tolerance:
            status = 'ok'
        elif abs(deviation) <= self.tolerance * 3:
            status = 'warning'
        else:
            status = 'error'

        result = DimensionComparison(
            name=name,
            bim_value=bim_height,
            pointcloud_value=pointcloud_height,
            deviation=deviation,
            deviation_percent=deviation_percent,
            status=status
        )

        self.results.append(result)
        return result

    def compare_wall(self,
                     bim_wall: Dict,
                     pointcloud_wall: Dict,
                     wall_id: int) -> Dict:
        """
        对比墙体尺寸

        Args:
            bim_wall: BIM 墙体信息
            pointcloud_wall: 点云墙体信息
            wall_id: 墙体编号

        Returns:
            Dict: 对比结果
        """
        result = {
            'wall_id': wall_id,
            'comparisons': [],
            'status': 'ok'
        }

        # 对比宽度（长度）
        if bim_wall.get('length') and pointcloud_wall.get('width'):
            width_comp = self.compare_height(
                bim_height=bim_wall['length'],
                pointcloud_height=pointcloud_wall['width'],
                name=f"墙{wall_id} 长度"
            )
            result['comparisons'].append({
                'dimension': 'length',
                'bim': bim_wall['length'],
                'pointcloud': pointcloud_wall['width'],
                'deviation': width_comp.deviation,
                'deviation_percent': width_comp.deviation_percent,
                'status': width_comp.status
            })

        # 对比高度
        if bim_wall.get('height') and pointcloud_wall.get('height'):
            height_comp = self.compare_height(
                bim_height=bim_wall['height'],
                pointcloud_height=pointcloud_wall['height'],
                name=f"墙{wall_id} 高度"
            )
            result['comparisons'].append({
                'dimension': 'height',
                'bim': bim_wall['height'],
                'pointcloud': pointcloud_wall['height'],
                'deviation': height_comp.deviation,
                'deviation_percent': height_comp.deviation_percent,
                'status': height_comp.status
            })

        # 更新墙体状态
        for comp in result['comparisons']:
            if comp['status'] == 'error':
                result['status'] = 'error'
                break
            elif comp['status'] == 'warning':
                result['status'] = 'warning'

        return result

    def compare_elevation(self,
                          bim_elevation: float,
                          pointcloud_floor_z: float,
                          name: str = "标高") -> DimensionComparison:
        """
        对比标高

        Args:
            bim_elevation: BIM 设计标高
            pointcloud_floor_z: 点云测量标高
            name: 名称

        Returns:
            DimensionComparison: 对比结果
        """
        deviation = pointcloud_floor_z - bim_elevation
        # 标高偏差不计算百分比

        if abs(deviation) <= self.tolerance:
            status = 'ok'
        elif abs(deviation) <= self.tolerance * 3:
            status = 'warning'
        else:
            status = 'error'

        result = DimensionComparison(
            name=name,
            bim_value=bim_elevation,
            pointcloud_value=pointcloud_floor_z,
            deviation=deviation,
            deviation_percent=0,  # 标高不计算百分比
            status=status
        )

        self.results.append(result)
        return result

    def generate_report(self) -> Dict:
        """
        生成对比报告

        Returns:
            Dict: 报告数据
        """
        report = {
            'summary': {
                'total': len(self.results),
                'ok': 0,
                'warning': 0,
                'error': 0
            },
            'details': []
        }

        for result in self.results:
            report['summary'][result.status] += 1
            report['details'].append({
                'name': result.name,
                'bim_value': result.bim_value,
                'pointcloud_value': result.pointcloud_value,
                'deviation': result.deviation,
                'deviation_percent': result.deviation_percent,
                'status': result.status
            })

        return report

    def print_report(self) -> None:
        """打印对比报告"""
        report = self.generate_report()

        print("\n" + "=" * 60)
        print("验房对比报告")
        print("=" * 60)

        print(f"\n总览:")
        print(f"  ✓ 合格: {report['summary']['ok']}")
        print(f"  ⚠ 警告: {report['summary']['warning']}")
        print(f"  ✗ 超差: {report['summary']['error']}")

        print(f"\n详细结果:")
        print("-" * 60)

        for detail in report['details']:
            status_icon = {
                'ok': '✓',
                'warning': '⚠',
                'error': '✗'
            }.get(detail['status'], '?')

            print(f"\n{status_icon} {detail['name']}")
            print(f"  BIM 设计值: {detail['bim_value']:.3f} m")
            print(f"  实测值:     {detail['pointcloud_value']:.3f} m")
            print(f"  偏差:       {detail['deviation']:+.3f} m ({detail['deviation_percent']:+.2f}%)")

        print("\n" + "=" * 60)

    def export_excel(self, filepath: str) -> bool:
        """
        导出为 Excel 文件

        Args:
            filepath: 导出路径

        Returns:
            bool: 是否成功
        """
        try:
            import pandas as pd

            report = self.generate_report()
            df = pd.DataFrame(report['details'])
            df.to_excel(filepath, index=False, sheet_name='验房对比')
            print(f"✓ 已导出报告: {filepath}")
            return True

        except Exception as e:
            print(f"✗ 导出失败: {e}")
            return False

    def check_floor_height(self,
                           bim_height: float,
                           measured_height: float,
                           name: str = "楼层净高") -> DimensionComparison:
        """
        检测楼层净高
        
        Args:
            bim_height: BIM 设计净高
            measured_height: 点云测量净高
            name: 检测项名称
            
        Returns:
            DimensionComparison: 检测结果
        """
        deviation = measured_height - bim_height
        deviation_mm = abs(deviation) * 1000
        
        # 阈值：±10mm
        threshold = QUALITY_THRESHOLDS['floor_height'] / 1000  # 转为米
        
        if deviation_mm <= QUALITY_THRESHOLDS['floor_height']:
            status = 'ok'
        elif deviation_mm <= QUALITY_THRESHOLDS['floor_height'] * 2:
            status = 'warning'
        else:
            status = 'error'
        
        result = DimensionComparison(
            name=name,
            bim_value=bim_height,
            pointcloud_value=measured_height,
            deviation=deviation,
            deviation_percent=(deviation / bim_height) * 100 if bim_height > 0 else 0,
            status=status,
            category='楼层净高'
        )
        self.results.append(result)
        return result

    def check_room_span(self,
                        bim_span: float,
                        measured_span: float,
                        name: str = "开间尺寸") -> DimensionComparison:
        """
        检测房间开间
        
        Args:
            bim_span: BIM 设计开间
            measured_span: 点云测量开间
            name: 检测项名称
            
        Returns:
            DimensionComparison: 检测结果
        """
        deviation = measured_span - bim_span
        deviation_mm = abs(deviation) * 1000
        
        # 阈值：±15mm
        if deviation_mm <= QUALITY_THRESHOLDS['span']:
            status = 'ok'
        elif deviation_mm <= QUALITY_THRESHOLDS['span'] * 2:
            status = 'warning'
        else:
            status = 'error'
        
        result = DimensionComparison(
            name=name,
            bim_value=bim_span,
            pointcloud_value=measured_span,
            deviation=deviation,
            deviation_percent=(deviation / bim_span) * 100 if bim_span > 0 else 0,
            status=status,
            category='房间尺寸'
        )
        self.results.append(result)
        return result

    def check_room_depth(self,
                         bim_depth: float,
                         measured_depth: float,
                         name: str = "进深尺寸") -> DimensionComparison:
        """
        检测房间进深
        
        Args:
            bim_depth: BIM 设计进深
            measured_depth: 点云测量进深
            name: 检测项名称
            
        Returns:
            DimensionComparison: 检测结果
        """
        deviation = measured_depth - bim_depth
        deviation_mm = abs(deviation) * 1000
        
        # 阈值：±15mm
        if deviation_mm <= QUALITY_THRESHOLDS['depth']:
            status = 'ok'
        elif deviation_mm <= QUALITY_THRESHOLDS['depth'] * 2:
            status = 'warning'
        else:
            status = 'error'
        
        result = DimensionComparison(
            name=name,
            bim_value=bim_depth,
            pointcloud_value=measured_depth,
            deviation=deviation,
            deviation_percent=(deviation / bim_depth) * 100 if bim_depth > 0 else 0,
            status=status,
            category='房间尺寸'
        )
        self.results.append(result)
        return result

    def check_wall_verticality(self,
                               wall_id: int,
                               deviation_mm_per_m: float,
                               name: str = None) -> QualityCheck:
        """
        检测墙面垂直度
        
        Args:
            wall_id: 墙体编号
            deviation_mm_per_m: 每米偏差值（mm/m）
            name: 检测项名称
            
        Returns:
            QualityCheck: 检测结果
        """
        if name is None:
            name = f"墙面{wall_id} 垂直度"
        
        # 阈值：≤5mm/m
        threshold = QUALITY_THRESHOLDS['verticality']
        
        if deviation_mm_per_m <= threshold:
            status = 'ok'
        elif deviation_mm_per_m <= threshold * 2:
            status = 'warning'
        else:
            status = 'error'
        
        result = QualityCheck(
            name=name,
            measured_value=deviation_mm_per_m,
            threshold=threshold,
            deviation=deviation_mm_per_m,
            status=status,
            category='墙面垂直度'
        )
        self.results.append(result)
        return result

    def check_wall_flatness(self,
                            wall_id: int,
                            max_deviation_mm: float,
                            name: str = None) -> QualityCheck:
        """
        检测墙面平整度
        
        Args:
            wall_id: 墙体编号
            max_deviation_mm: 最大偏差值（mm）
            name: 检测项名称
            
        Returns:
            QualityCheck: 检测结果
        """
        if name is None:
            name = f"墙面{wall_id} 平整度"
        
        # 阈值：≤8mm
        threshold = QUALITY_THRESHOLDS['flatness']
        
        if max_deviation_mm <= threshold:
            status = 'ok'
        elif max_deviation_mm <= threshold * 2:
            status = 'warning'
        else:
            status = 'error'
        
        result = QualityCheck(
            name=name,
            measured_value=max_deviation_mm,
            threshold=threshold,
            deviation=max_deviation_mm,
            status=status,
            category='墙面平整度'
        )
        self.results.append(result)
        return result

    def process_quality_analysis(self,
                                 bim_data: Dict,
                                 pointcloud_data: Dict) -> Dict:
        """
        处理完整的质量分析结果
        
        Args:
            bim_data: BIM 模型数据
            pointcloud_data: 点云分析数据
            
        Returns:
            Dict: 完整报告
        """
        # 1. 楼层净高
        if pointcloud_data.get('floor_height') and bim_data.get('spaces'):
            # 尝试从BIM获取设计高度
            for space in bim_data['spaces']:
                if space.get('elevation'):
                    # 假设房间高度信息
                    pass
            # 如果没有BIM高度，直接记录测量值
            self.check_floor_height(
                bim_height=pointcloud_data.get('floor_height', 0),  # 临时使用实测值
                measured_height=pointcloud_data.get('floor_height', 0),
                name="楼层净高"
            )
        
        # 2. 开间/进深
        if pointcloud_data.get('span'):
            self.check_room_span(
                bim_span=pointcloud_data['span'],  # 临时使用实测值
                measured_span=pointcloud_data['span'],
                name="开间尺寸"
            )
        
        if pointcloud_data.get('depth'):
            self.check_room_depth(
                bim_depth=pointcloud_data['depth'],
                measured_depth=pointcloud_data['depth'],
                name="进深尺寸"
            )
        
        # 3. 墙面垂直度
        for v_data in pointcloud_data.get('wall_verticality', []):
            self.check_wall_verticality(
                wall_id=v_data.get('wall_id', 0),
                deviation_mm_per_m=v_data.get('deviation_mm_per_m', 0)
            )
        
        # 4. 墙面平整度
        for f_data in pointcloud_data.get('wall_flatness', []):
            self.check_wall_flatness(
                wall_id=f_data.get('wall_id', 0),
                max_deviation_mm=f_data.get('max_deviation_mm', 0)
            )
        
        return self.generate_report()

    def generate_full_report(self) -> Dict:
        """
        生成完整报告（包含新检测项）
        
        Returns:
            Dict: 报告数据
        """
        report = {
            'summary': {
                'total': len(self.results),
                'ok': 0,
                'warning': 0,
                'error': 0
            },
            'categories': {},
            'details': []
        }
        
        for result in self.results:
            # 统计状态
            report['summary'][result.status] += 1
            
            # 按类别分组
            category = result.category
            if category not in report['categories']:
                report['categories'][category] = {
                    'count': 0,
                    'ok': 0,
                    'warning': 0,
                    'error': 0
                }
            report['categories'][category]['count'] += 1
            report['categories'][category][result.status] += 1
            
            # 详细结果
            if isinstance(result, DimensionComparison):
                report['details'].append({
                    'name': result.name,
                    'category': result.category,
                    'bim_value': result.bim_value,
                    'measured_value': result.pointcloud_value,
                    'deviation': result.deviation,
                    'deviation_mm': abs(result.deviation) * 1000,
                    'deviation_percent': result.deviation_percent,
                    'status': result.status
                })
            elif isinstance(result, QualityCheck):
                report['details'].append({
                    'name': result.name,
                    'category': result.category,
                    'bim_value': '-',  # 质量检测无BIM对比
                    'measured_value': result.measured_value,
                    'deviation': result.deviation,
                    'deviation_mm': result.deviation,
                    'threshold': result.threshold,
                    'status': result.status
                })
        
        return report

    def print_full_report(self) -> None:
        """打印完整验房报告"""
        report = self.generate_full_report()
        
        print("\n" + "=" * 70)
        print("            房屋施工质量检测报告")
        print("=" * 70)
        
        print(f"\n【检测汇总】")
        print(f"  总检测项: {report['summary']['total']}")
        print(f"  ✓ 合格: {report['summary']['ok']}")
        print(f"  ⚠ 警告: {report['summary']['warning']}")
        print(f"  ✗ 超差: {report['summary']['error']}")
        
        # 按类别显示
        print(f"\n【分类统计】")
        for category, stats in report['categories'].items():
            print(f"  {category}: {stats['count']}项")
            print(f"    ✓ {stats['ok']}  ⚠ {stats['warning']}  ✗ {stats['error']}")
        
        # 详细结果
        print(f"\n【详细检测结果】")
        print("-" * 70)
        
        for detail in report['details']:
            status_icon = {
                'ok': '✓',
                'warning': '⚠',
                'error': '✗'
            }.get(detail['status'], '?')
            
            print(f"\n{status_icon} [{detail['category']}] {detail['name']}")
            
            if detail.get('bim_value') != '-':
                print(f"  设计值: {detail['bim_value']:.3f} m")
            print(f"  实测值: {detail['measured_value']:.3f} {'m' if detail['category'] in ['楼层净高', '房间尺寸'] else 'mm'}")
            print(f"  偏差:   {detail['deviation_mm']:.1f} mm")
            if detail.get('threshold'):
                print(f"  阈值:   {detail['threshold']} mm")
        
        print("\n" + "=" * 70)

    def export_full_report_excel(self, filepath: str) -> bool:
        """
        导出完整报告为 Excel
        
        Args:
            filepath: 导出路径
            
        Returns:
            bool: 是否成功
        """
        try:
            import pandas as pd
            
            report = self.generate_full_report()
            
            # 创建多个sheet
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # 汇总表
                summary_data = {
                    '检测项': ['总数', '合格', '警告', '超差'],
                    '数量': [
                        report['summary']['total'],
                        report['summary']['ok'],
                        report['summary']['warning'],
                        report['summary']['error']
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='汇总', index=False)
                
                # 详细结果表
                df_details = pd.DataFrame(report['details'])
                df_details.to_excel(writer, sheet_name='详细结果', index=False)
            
            print(f"✓ 已导出完整报告: {filepath}")
            return True
            
        except Exception as e:
            print(f"✗ 导出失败: {e}")
            return False


if __name__ == "__main__":
    # 测试代码
    engine = ComparisonEngine(tolerance=0.01)

    # 模拟对比
    engine.compare_height(3.0, 3.02, "房间高度")
    engine.compare_elevation(0.0, 0.015, "地面标高")

    engine.print_report()