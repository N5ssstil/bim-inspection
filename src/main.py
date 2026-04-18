"""
BIM点云验房系统 - 主程序
完整的验房流程：加载 -> 分析 -> 报告
"""

import os
import sys
import json
from datetime import datetime

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pointcloud import PointCloudProcessor
from bim_model import BIMProcessor
from comparison import ComparisonEngine


class BIMInspectionApp:
    """验房应用主类"""
    
    def __init__(self):
        self.pointcloud_processor = PointCloudProcessor()
        self.bim_processor = BIMProcessor()
        self.comparison_engine = None
        self.results = None
    
    def load_pointcloud(self, las_path: str) -> bool:
        """
        加载点云文件
        
        Args:
            las_path: .las 文件路径
            
        Returns:
            bool: 是否成功
        """
        print(f"\n{'='*50}")
        print("步骤1: 加载点云数据")
        print(f"{'='*50}")
        
        if not os.path.exists(las_path):
            print(f"✗ 文件不存在: {las_path}")
            return False
        
        if not self.pointcloud_processor.load_las(las_path):
            return False
        
        print("✓ 点云加载成功")
        return True
    
    def load_bim(self, ifc_path: str) -> bool:
        """
        加载 BIM 模型
        
        Args:
            ifc_path: .ifc 文件路径
            
        Returns:
            bool: 是否成功
        """
        print(f"\n{'='*50}")
        print("步骤2: 加载 BIM 模型")
        print(f"{'='*50}")
        
        if not os.path.exists(ifc_path):
            print(f"✗ 文件不存在: {ifc_path}")
            return False
        
        if not self.bim_processor.load_ifc(ifc_path):
            return False
        
        print("✓ BIM 加载成功")
        return True
    
    def analyze_pointcloud(self,
                           voxel_size: float = 0.01,
                           distance_threshold: float = 0.02) -> dict:
        """
        分析点云数据
        
        Args:
            voxel_size: 体素下采样尺寸
            distance_threshold: 平面分割阈值
            
        Returns:
            dict: 分析结果
        """
        print(f"\n{'='*50}")
        print("步骤3: 点云质量分析")
        print(f"{'='*50}")
        
        # 预处理
        print("\n[预处理]")
        self.pointcloud_processor.preprocess(voxel_size=voxel_size)
        
        # 平面分割
        print("\n[平面分割]")
        planes = self.pointcloud_processor.segment_planes(
            distance_threshold=distance_threshold
        )
        
        # 平面分类
        print("\n[平面分类]")
        classified = self.pointcloud_processor.classify_planes(planes)
        
        # 完整质量分析
        print("\n[质量分析]")
        quality_results = self.pointcloud_processor.full_quality_analysis(classified)
        
        # 打印结果摘要
        print("\n分析结果摘要:")
        print(f"  楼层净高: {quality_results.get('floor_height', 'N/A'):.3f} m" if quality_results.get('floor_height') else "  楼层净高: N/A")
        print(f"  开间尺寸: {quality_results.get('span', 'N/A'):.3f} m" if quality_results.get('span') else "  开间尺寸: N/A")
        print(f"  进深尺寸: {quality_results.get('depth', 'N/A'):.3f} m" if quality_results.get('depth') else "  进深尺寸: N/A")
        print(f"  检测墙面数: {len(quality_results.get('walls', []))}")
        
        # 墙面垂直度
        for v in quality_results.get('wall_verticality', []):
            print(f"  墙{v['wall_id']} 垂直度: {v['deviation_mm_per_m']:.2f} mm/m [{v['status']}]")
        
        # 墙面平整度
        for f in quality_results.get('wall_flatness', []):
            print(f"  墙{f['wall_id']} 平整度: {f['max_deviation_mm']:.2f} mm [{f['status']}]")
        
        self.results = quality_results
        return quality_results
    
    def analyze_bim(self) -> dict:
        """
        分析 BIM 模型
        
        Returns:
            dict: BIM 数据
        """
        print(f"\n{'='*50}")
        print("步骤4: BIM 模型分析")
        print(f"{'='*50}")
        
        bim_data = self.bim_processor.get_all_dimensions()
        
        print(f"\nBIM 模型信息:")
        print(f"  项目名称: {bim_data.get('project_name', 'N/A')}")
        print(f"  墙体数量: {len(bim_data.get('walls', []))}")
        print(f"  楼板数量: {len(bim_data.get('slabs', []))}")
        print(f"  房间数量: {len(bim_data.get('spaces', []))}")
        
        return bim_data
    
    def generate_report(self,
                        bim_data: dict,
                        output_path: str = None) -> dict:
        """
        生成验房报告
        
        Args:
            bim_data: BIM 模型数据
            output_path: 报告输出路径
            
        Returns:
            dict: 报告数据
        """
        print(f"\n{'='*50}")
        print("步骤5: 生成验房报告")
        print(f"{'='*50}")
        
        self.comparison_engine = ComparisonEngine()
        report = self.comparison_engine.process_quality_analysis(
            bim_data=bim_data,
            pointcloud_data=self.results
        )
        
        # 打印报告
        self.comparison_engine.print_full_report()
        
        # 导出 Excel
        if output_path:
            excel_path = output_path.replace('.json', '.xlsx')
            self.comparison_engine.export_full_report_excel(excel_path)
            
            # 导出 JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"✓ 已保存 JSON 报告: {output_path}")
        
        return report
    
    def run_full_inspection(self,
                            las_path: str,
                            ifc_path: str,
                            output_dir: str = './output') -> bool:
        """
        运行完整验房流程
        
        Args:
            las_path: 点云文件路径
            ifc_path: BIM 文件路径
            output_dir: 输出目录
            
        Returns:
            bool: 是否成功
        """
        print("\n" + "="*60)
        print("    BIM点云验房系统 - 开始验房")
        print("="*60)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 加载点云
        if not self.load_pointcloud(las_path):
            return False
        
        # 2. 加载 BIM
        if not self.load_bim(ifc_path):
            print("⚠ BIM 加载失败，继续进行点云分析...")
            bim_data = {}
        else:
            bim_data = self.analyze_bim()
        
        # 3. 分析点云
        quality_results = self.analyze_pointcloud()
        
        # 4. 生成报告
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(output_dir, f'验房报告_{timestamp}.json')
        
        report = self.generate_report(bim_data, report_path)
        
        print("\n" + "="*60)
        print("    验房完成!")
        print("="*60)
        
        return True


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BIM点云验房系统')
    parser.add_argument('--las', required=True, help='点云文件路径 (.las)')
    parser.add_argument('--ifc', required=False, help='BIM文件路径 (.ifc)')
    parser.add_argument('--output', default='./output', help='输出目录')
    
    args = parser.parse_args()
    
    app = BIMInspectionApp()
    
    if args.ifc:
        success = app.run_full_inspection(args.las, args.ifc, args.output)
    else:
        # 仅点云分析
        if app.load_pointcloud(args.las):
            app.analyze_pointcloud()
            success = True
        else:
            success = False
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())