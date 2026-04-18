"""
BIM点云验房系统 - GUI完整版
包含手动配准控制点界面
"""

import sys
import os
import numpy as np
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QTextEdit, QGroupBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSplitter, QTabWidget, QComboBox, QDoubleSpinBox,
    QCheckBox, QFrame, QDialog, QListWidget, QListWidgetItem,
    QSpinBox, QSlider, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QPen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pointcloud import PointCloudProcessor
from bim_model import BIMProcessor
from comparison import ComparisonEngine
from visualization import DeviationVisualizer
import laspy
import ifcopenshell
import ifcopenshell.util.element
import open3d as o3d


class ControlPointsDialog(QDialog):
    """手动配准控制点选择对话框"""
    
    points_updated = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动配准 - 控制点选择")
        self.setGeometry(200, 200, 800, 600)
        
        self.bim_points = []  # BIM控制点
        self.pcd_points = []  # 点云控制点
        self.pairs = []       # 配对
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 说明
        info_label = QLabel(
            "使用说明:\n"
            "1. 在下方输入BIM模型和点云中对应控制点的坐标\n"
            "2. 建议选择3-4个明显特征点（如墙角、门框角点）\n"
            "3. 点击'计算配准变换'生成变换矩阵"
        )
        info_label.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        layout.addWidget(info_label)
        
        # 控制点表格
        points_group = QGroupBox("控制点对")
        points_layout = QGridLayout(points_group)
        
        # 表头
        points_layout.addWidget(QLabel("序号"), 0, 0)
        points_layout.addWidget(QLabel("BIM坐标 (X, Y, Z)"), 0, 1)
        points_layout.addWidget(QLabel("点云坐标 (X, Y, Z)"), 0, 2)
        points_layout.addWidget(QLabel("操作"), 0, 3)
        
        # 4个控制点输入
        self.bim_inputs = []
        self.pcd_inputs = []
        
        for i in range(4):
            # 序号
            points_layout.addWidget(QLabel(f"点{i+1}"), i+1, 0)
            
            # BIM坐标输入
            bim_row = QHBoxLayout()
            bim_x = QDoubleSpinBox()
            bim_x.setRange(-1000, 1000)
            bim_x.setDecimals(3)
            bim_y = QDoubleSpinBox()
            bim_y.setRange(-1000, 1000)
            bim_y.setDecimals(3)
            bim_z = QDoubleSpinBox()
            bim_z.setRange(-1000, 1000)
            bim_z.setDecimals(3)
            bim_row.addWidget(QLabel("X:"))
            bim_row.addWidget(bim_x)
            bim_row.addWidget(QLabel("Y:"))
            bim_row.addWidget(bim_y)
            bim_row.addWidget(QLabel("Z:"))
            bim_row.addWidget(bim_z)
            
            bim_container = QWidget()
            bim_container.setLayout(bim_row)
            points_layout.addWidget(bim_container, i+1, 1)
            self.bim_inputs.append((bim_x, bim_y, bim_z))
            
            # 点云坐标输入
            pcd_row = QHBoxLayout()
            pcd_x = QDoubleSpinBox()
            pcd_x.setRange(-1000, 1000)
            pcd_x.setDecimals(3)
            pcd_y = QDoubleSpinBox()
            pcd_y.setRange(-1000, 1000)
            pcd_y.setDecimals(3)
            pcd_z = QDoubleSpinBox()
            pcd_z.setRange(-1000, 1000)
            pcd_z.setDecimals(3)
            pcd_row.addWidget(QLabel("X:"))
            pcd_row.addWidget(pcd_x)
            pcd_row.addWidget(QLabel("Y:"))
            pcd_row.addWidget(pcd_y)
            pcd_row.addWidget(QLabel("Z:"))
            pcd_row.addWidget(pcd_z)
            
            pcd_container = QWidget()
            pcd_container.setLayout(pcd_row)
            points_layout.addWidget(pcd_container, i+1, 2)
            self.pcd_inputs.append((pcd_x, pcd_y, pcd_z))
            
            # 清除按钮
            clear_btn = QPushButton("清除")
            clear_btn.setFixedWidth(60)
            clear_btn.clicked.connect(lambda checked, idx=i: self.clear_point(idx))
            points_layout.addWidget(clear_btn, i+1, 3)
        
        layout.addWidget(points_group)
        
        # 常用控制点模板
        template_group = QGroupBox("常用控制点模板（点击自动填充）")
        template_layout = QHBoxLayout(template_group)
        
        template_btn1 = QPushButton("墙角点模板")
        template_btn1.clicked.connect(self.fill_template_corners)
        template_layout.addWidget(template_btn1)
        
        template_btn2 = QPushButton("中心点模板")
        template_btn2.clicked.connect(self.fill_template_center)
        template_layout.addWidget(template_btn2)
        
        layout.addWidget(template_group)
        
        # 变换矩阵显示
        matrix_group = QGroupBox("计算结果")
        matrix_layout = QVBoxLayout(matrix_group)
        
        self.matrix_text = QTextEdit()
        self.matrix_text.setReadOnly(True)
        self.matrix_text.setMaximumHeight(150)
        self.matrix_text.setFont(QFont("Courier New", 10))
        matrix_layout.addWidget(self.matrix_text)
        
        layout.addWidget(matrix_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        calc_btn = QPushButton("计算配准变换")
        calc_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        calc_btn.clicked.connect(self.calculate_transform)
        btn_layout.addWidget(calc_btn)
        
        apply_btn = QPushButton("应用变换")
        apply_btn.clicked.connect(self.apply_transform)
        btn_layout.addWidget(apply_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def clear_point(self, idx):
        """清除指定控制点"""
        for spin in self.bim_inputs[idx]:
            spin.setValue(0)
        for spin in self.pcd_inputs[idx]:
            spin.setValue(0)
    
    def fill_template_corners(self):
        """填充墙角模板（示例值）"""
        # BIM墙角点（单位：米）
        templates = [
            [(0.42, 2.99, 0), (-1.6, -3.8, -5.6)],    # 墙角1
            [(-3.64, 2.93, 0), (0, 5, -5.6)],         # 墙角2
            [(-3.58, -2.42, 0), (0, 0, -5.6)],        # 墙角3
            [(0.30, 2.93, 0), (17, 33, -5.6)],        # 墙角4
        ]
        
        for i, (bim_pt, pcd_pt) in enumerate(templates[:4]):
            self.bim_inputs[i][0].setValue(bim_pt[0])
            self.bim_inputs[i][1].setValue(bim_pt[1])
            self.bim_inputs[i][2].setValue(bim_pt[2])
            self.pcd_inputs[i][0].setValue(pcd_pt[0])
            self.pcd_inputs[i][1].setValue(pcd_pt[1])
            self.pcd_inputs[i][2].setValue(pcd_pt[2])
    
    def fill_template_center(self):
        """填充中心点模板"""
        # 使用中心点配准
        bim_center = (-1.62, 1.76, 0)  # BIM中心
        pcd_center = (7.9, 14.7, -5.6)  # 点云中心
        
        self.bim_inputs[0][0].setValue(bim_center[0])
        self.bim_inputs[0][1].setValue(bim_center[1])
        self.bim_inputs[0][2].setValue(bim_center[2])
        self.pcd_inputs[0][0].setValue(pcd_center[0])
        self.pcd_inputs[0][1].setValue(pcd_center[1])
        self.pcd_inputs[0][2].setValue(pcd_center[2])
    
    def get_control_points(self):
        """获取有效的控制点对"""
        pairs = []
        for i in range(4):
            bim_pt = [self.bim_inputs[i][j].value() for j in range(3)]
            pcd_pt = [self.pcd_inputs[i][j].value() for j in range(3)]
            
            # 检查是否有效（不全为0）
            if any(v != 0 for v in bim_pt) or any(v != 0 for v in pcd_pt):
                pairs.append({
                    'bim': np.array(bim_pt),
                    'pcd': np.array(pcd_pt)
                })
        
        return pairs
    
    def calculate_transform(self):
        """计算配准变换矩阵"""
        pairs = self.get_control_points()
        
        if len(pairs) < 3:
            QMessageBox.warning(self, "警告", "请至少输入3个控制点对")
            return
        
        # 提取坐标
        bim_pts = np.array([p['bim'] for p in pairs])
        pcd_pts = np.array([p['pcd'] for p in pairs])
        
        # 计算变换矩阵（使用最小二乘）
        # 方法：计算平移 + 旋转
        
        # 1. 计算中心点
        bim_center = np.mean(bim_pts, axis=0)
        pcd_center = np.mean(pcd_pts, axis=0)
        
        # 2. 去中心化
        bim_centered = bim_pts - bim_center
        pcd_centered = pcd_pts - pcd_center
        
        # 3. 计算旋转矩阵（使用SVD）
        H = bim_centered.T @ pcd_centered
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        
        # 确保是有效旋转矩阵
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T
        
        # 4. 计算平移
        t = pcd_center - R @ bim_center
        
        # 5. 构建4x4变换矩阵
        transform = np.eye(4)
        transform[:3, :3] = R
        transform[:3, 3] = t
        
        # 显示结果
        self.matrix_text.clear()
        self.matrix_text.append(f"控制点数量: {len(pairs)}")
        self.matrix_text.append(f"\n变换矩阵 (4x4):")
        self.matrix_text.append(str(transform))
        self.matrix_text.append(f"\n平移向量: ({t[0]:.3f}, {t[1]:.3f}, {t[2]:.3f})")
        
        # 计算配准误差
        errors = []
        for i, pair in enumerate(pairs):
            bim_h = np.append(pair['bim'], 1)
            transformed = transform @ bim_h
            error = np.linalg.norm(transformed[:3] - pair['pcd'])
            errors.append(error)
            self.matrix_text.append(f"点{i+1}误差: {error*1000:.2f} mm")
        
        avg_error = np.mean(errors)
        self.matrix_text.append(f"\n平均配准误差: {avg_error*1000:.2f} mm")
        
        self.transform_matrix = transform
        self.points_updated.emit(pairs)
    
    def apply_transform(self):
        """应用变换"""
        if hasattr(self, 'transform_matrix'):
            self.parent().set_alignment_transform(self.transform_matrix)
            QMessageBox.information(self, "完成", "变换矩阵已应用到主程序")
            self.close()
        else:
            QMessageBox.warning(self, "警告", "请先计算变换矩阵")


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.las_path = None
        self.ifc_path = None
        self.last_results = None
        self.alignment_transform = None
        self.pcd_processor = None
        self.bim_processor = None
        
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("房屋施工质量检测系统")
        self.setGeometry(100, 100, 1400, 900)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # === 文件选择区 ===
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        
        # 点云文件
        las_row = QHBoxLayout()
        self.las_label = QLabel("未选择点云文件 (.las/.laz)")
        self.las_label.setStyleSheet("color: gray;")
        las_btn = QPushButton("选择点云")
        las_btn.setFixedWidth(100)
        las_btn.clicked.connect(self.select_las_file)
        las_row.addWidget(QLabel("点云:"))
        las_row.addWidget(self.las_label, 1)
        las_row.addWidget(las_btn)
        file_layout.addLayout(las_row)
        
        # BIM文件
        ifc_row = QHBoxLayout()
        self.ifc_label = QLabel("未选择 (可选)")
        self.ifc_label.setStyleSheet("color: gray;")
        ifc_btn = QPushButton("选择BIM")
        ifc_btn.setFixedWidth(100)
        ifc_btn.clicked.connect(self.select_ifc_file)
        self.ifc_skip_cb = QCheckBox("仅点云分析")
        self.ifc_skip_cb.setChecked(False)
        ifc_row.addWidget(QLabel("BIM:"))
        ifc_row.addWidget(self.ifc_label, 1)
        ifc_row.addWidget(ifc_btn)
        ifc_row.addWidget(self.ifc_skip_cb)
        file_layout.addLayout(ifc_row)
        
        layout.addWidget(file_group)
        
        # === 配准控制区 ===
        align_group = QGroupBox("配准控制")
        align_layout = QHBoxLayout(align_group)
        
        manual_align_btn = QPushButton("手动配准（控制点）")
        manual_align_btn.setStyleSheet("background-color: #2196F3; color: white;")
        manual_align_btn.clicked.connect(self.open_control_points_dialog)
        align_layout.addWidget(manual_align_btn)
        
        auto_align_btn = QPushButton("自动配准（ICP）")
        auto_align_btn.clicked.connect(self.auto_align)
        align_layout.addWidget(auto_align_btn)
        
        self.align_status = QLabel("未配准")
        self.align_status.setStyleSheet("color: orange;")
        align_layout.addWidget(self.align_status)
        
        align_layout.addStretch()
        
        # 配准变换显示
        self.transform_label = QLabel("")
        align_layout.addWidget(self.transform_label)
        
        layout.addWidget(align_group)
        
        # === 参数设置区 ===
        params_group = QGroupBox("分析参数")
        params_layout = QHBoxLayout(params_group)
        
        params_layout.addWidget(QLabel("下采样:"))
        self.voxel_spin = QDoubleSpinBox()
        self.voxel_spin.setRange(0.005, 0.1)
        self.voxel_spin.setValue(0.02)
        self.voxel_spin.setSingleStep(0.005)
        self.voxel_spin.setDecimals(3)
        params_layout.addWidget(self.voxel_spin)
        params_layout.addWidget(QLabel("m"))
        
        params_layout.addWidget(QLabel("  平面阈值:"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.01, 0.1)
        self.threshold_spin.setValue(0.05)
        self.threshold_spin.setSingleStep(0.01)
        params_layout.addWidget(self.threshold_spin)
        params_layout.addWidget(QLabel("m"))
        
        params_layout.addStretch()
        layout.addWidget(params_group)
        
        # === 开始按钮 ===
        self.process_btn = QPushButton("▶ 开始验房分析")
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; padding: 12px;
                background-color: #4CAF50; color: white; border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #cccccc; }
        """)
        self.process_btn.clicked.connect(self.start_processing)
        layout.addWidget(self.process_btn)
        
        # === 进度条 ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(25)
        layout.addWidget(self.progress_bar)
        
        # === 结果显示区（Tab） ===
        self.result_tabs = QTabWidget()
        
        # Tab 1: 处理日志
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 10))
        log_layout.addWidget(self.log_text)
        self.result_tabs.addTab(log_tab, "处理日志")
        
        # Tab 2: 检测结果
        result_tab = QWidget()
        result_layout = QVBoxLayout(result_tab)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "检测项", "类别", "设计值", "实测值", "偏差(mm)", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        result_layout.addWidget(self.result_table)
        
        export_row = QHBoxLayout()
        self.export_excel_btn = QPushButton("导出 Excel")
        self.export_excel_btn.setEnabled(False)
        self.export_excel_btn.clicked.connect(self.export_excel)
        self.export_json_btn = QPushButton("导出 JSON")
        self.export_json_btn.setEnabled(False)
        self.export_json_btn.clicked.connect(self.export_json)
        export_row.addStretch()
        export_row.addWidget(self.export_excel_btn)
        export_row.addWidget(self.export_json_btn)
        result_layout.addLayout(export_row)
        
        self.result_tabs.addTab(result_tab, "检测结果")
        
        # Tab 3: 质量标准
        standards_tab = QWidget()
        standards_layout = QVBoxLayout(standards_tab)
        standards_text = QTextEdit()
        standards_text.setReadOnly(True)
        standards_text.setHtml("""
<h2>房屋施工质量检测标准</h2>
<table border="1" style="border-collapse: collapse; width: 100%;">
<tr style="background-color: #f0f0f0;">
    <th>检测项</th><th>允许偏差</th><th>判定标准</th>
</tr>
<tr><td>楼层净高</td><td>±10 mm</td><td>合格≤10mm | 警告≤20mm | 超差>20mm</td></tr>
<tr><td>开间尺寸</td><td>±15 mm</td><td>合格≤15mm | 警告≤30mm | 超差>30mm</td></tr>
<tr><td>进深尺寸</td><td>±15 mm</td><td>合格≤15mm | 警告≤30mm | 超差>30mm</td></tr>
<tr><td>墙面垂直度</td><td>≤5 mm/m</td><td>合格≤5mm/m | 警告≤10mm/m | 超差>10mm/m</td></tr>
<tr><td>墙面平整度</td><td>≤8 mm</td><td>合格≤8mm | 警告≤16mm | 超差>16mm</td></tr>
</table>
        """)
        standards_layout.addWidget(standards_text)
        self.result_tabs.addTab(standards_tab, "质量标准")
        
        # Tab 4: 3D可视化
        viz_tab = QWidget()
        viz_layout = QVBoxLayout(viz_tab)
        
        # 可视化按钮
        viz_btn_row = QHBoxLayout()
        
        gen_heatmap_btn = QPushButton("生成偏差热力图")
        gen_heatmap_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px;")
        gen_heatmap_btn.clicked.connect(self.generate_heatmaps)
        viz_btn_row.addWidget(gen_heatmap_btn)
        
        gen_3d_btn = QPushButton("生成3D交互场景")
        gen_3d_btn.setStyleSheet("background-color: #9C27B0; color: white; padding: 8px;")
        gen_3d_btn.clicked.connect(self.generate_3d_scene)
        viz_btn_row.addWidget(gen_3d_btn)
        
        open_output_btn = QPushButton("打开输出目录")
        open_output_btn.clicked.connect(self.open_output_dir)
        viz_btn_row.addWidget(open_output_btn)
        
        viz_btn_row.addStretch()
        viz_layout.addLayout(viz_btn_row)
        
        # 可视化预览区域
        self.viz_preview = QTextEdit()
        self.viz_preview.setReadOnly(True)
        self.viz_preview.setHtml("""
<h2>3D可视化标注</h2>
<p>点击上方按钮生成可视化结果：</p>
<ul>
<li><b>偏差热力图</b> - 用颜色显示墙面平整度偏差分布</li>
<li><b>3D交互场景</b> - 可旋转查看的点云+BIM叠加视图</li>
<li><b>汇总对比图</b> - 所有墙体质量对比柱状图</li>
</ul>
<p>颜色含义：</p>
<ul>
<li>🟢 <span style="color:green">绿色</span> - 合格（偏差 ≤ 8mm）</li>
<li>🟡 <span style="color:#FFA500">黄色</span> - 警告（8-16mm）</li>
<li>🔴 <span style="color:red">红色</span> - 超差（> 16mm）</li>
</ul>
        """)
        viz_layout.addWidget(self.viz_preview)
        
        self.result_tabs.addTab(viz_tab, "3D可视化")
        
        layout.addWidget(self.result_tabs, 1)
        
        self.statusBar().showMessage("请选择点云文件开始验房")
    
    def select_las_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云文件", "",
            "LAS Files (*.las *.laz);;All Files (*)"
        )
        if file_path:
            self.las_path = file_path
            self.las_label.setText(os.path.basename(file_path))
            self.las_label.setStyleSheet("color: green;")
            self.log("✓ 已选择点云: " + os.path.basename(file_path))
            self.check_ready()
    
    def select_ifc_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择BIM文件", "",
            "IFC Files (*.ifc);;All Files (*)"
        )
        if file_path:
            self.ifc_path = file_path
            self.ifc_label.setText(os.path.basename(file_path))
            self.ifc_label.setStyleSheet("color: green;")
            self.log("✓ 已选择BIM: " + os.path.basename(file_path))
    
    def check_ready(self):
        if self.las_path:
            self.process_btn.setEnabled(True)
    
    def log(self, message):
        self.log_text.append(message)
    
    def open_control_points_dialog(self):
        """打开控制点选择对话框"""
        if not self.las_path or not self.ifc_path:
            QMessageBox.warning(self, "警告", "请先选择点云和BIM文件")
            return
        
        # 显示文件信息帮助用户选择控制点
        self.log("\n正在加载文件信息...")
        
        # 点云范围
        las = laspy.read(self.las_path)
        pts = np.vstack([las.x, las.y, las.z]).transpose()
        pcd_min = np.min(pts, axis=0)
        pcd_max = np.max(pts, axis=0)
        pcd_center = np.mean(pts, axis=0)
        
        self.log(f"点云范围: ({pcd_min[0]:.1f}, {pcd_min[1]:.1f}, {pcd_min[2]:.1f}) ~ ({pcd_max[0]:.1f}, {pcd_max[1]:.1f}, {pcd_max[2]:.1f})")
        self.log(f"点云中心: ({pcd_center[0]:.2f}, {pcd_center[1]:.2f}, {pcd_center[2]:.2f})")
        
        # BIM墙体位置
        ifc = ifcopenshell.open(self.ifc_path)
        walls = ifc.by_type('IfcWall')
        scale = 0.001
        
        self.log(f"\nBIM墙体位置:")
        for wall in walls:
            if hasattr(wall, 'ObjectPlacement'):
                try:
                    loc = wall.ObjectPlacement.RelativePlacement.Location
                    pos = np.array(list(loc.Coordinates)) * scale
                    self.log(f"  {wall.Name}: ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")
                except: pass
        
        # 打开对话框
        dialog = ControlPointsDialog(self)
        dialog.exec()
    
    def set_alignment_transform(self, transform):
        """设置配准变换矩阵"""
        self.alignment_transform = transform
        self.align_status.setText("已配准 ✓")
        self.align_status.setStyleSheet("color: green;")
        
        t = transform[:3, 3]
        self.transform_label.setText(f"平移: ({t[0]:.2f}, {t[1]:.2f}, {t[2]:.2f})")
        self.log(f"\n✓ 配准变换已设置")
    
    def auto_align(self):
        """自动配准"""
        if not self.las_path or not self.ifc_path:
            QMessageBox.warning(self, "警告", "请先选择点云和BIM文件")
            return
        
        self.log("\n自动配准...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        # 简单的中心点对齐
        las = laspy.read(self.las_path)
        pts = np.vstack([las.x, las.y, las.z]).transpose()
        pcd_center = np.mean(pts, axis=0)
        
        ifc = ifcopenshell.open(self.ifc_path)
        walls = ifc.by_type('IfcWall')
        scale = 0.001
        
        bim_positions = []
        for wall in walls:
            if hasattr(wall, 'ObjectPlacement'):
                try:
                    loc = wall.ObjectPlacement.RelativePlacement.Location
                    pos = np.array(list(loc.Coordinates)) * scale
                    bim_positions.append(pos)
                except: pass
        
        if bim_positions:
            bim_center = np.mean(bim_positions, axis=0)
            
            # 构建变换矩阵（仅平移）
            t = pcd_center - bim_center
            transform = np.eye(4)
            transform[:3, 3] = t
            
            self.set_alignment_transform(transform)
            self.log(f"✓ 中心点对齐完成")
        else:
            self.log("✗ 无法提取BIM位置")
        
        self.progress_bar.setVisible(False)
    
    def start_processing(self):
        """开始验房分析"""
        if not self.las_path:
            QMessageBox.warning(self, "警告", "请先选择点云文件")
            return
        
        self.process_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_table.setRowCount(0)
        
        self.log("\n" + "="*50)
        self.log(f"验房开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*50)
        
        # 简化处理（直接分析）
        try:
            self.run_analysis()
        except Exception as e:
            self.log(f"✗ 错误: {e}")
            QMessageBox.critical(self, "错误", str(e))
        
        self.process_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
    
    def run_analysis(self):
        """运行分析"""
        import open3d as o3d
        
        self.progress_bar.setValue(10)
        self.log("\n【1】加载点云...")
        
        las = laspy.read(self.las_path)
        pts = np.vstack([las.x, las.y, las.z]).transpose()
        
        self.log(f"  点数: {len(pts):,}")
        
        self.progress_bar.setValue(20)
        self.log("\n【2】预处理...")
        
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        pcd_down = pcd.voxel_down_sample(voxel_size=self.voxel_spin.value())
        pts_down = np.asarray(pcd_down.points)
        
        self.log(f"  下采样后: {len(pts_down):,} 点")
        
        self.progress_bar.setValue(40)
        self.log("\n【3】平面分割...")
        
        # 地面
        z_min = np.min(pts_down[:,2])
        ground_mask = pts_down[:,2] < z_min + 0.3
        ground_pts = pts_down[ground_mask]
        ground_z = np.mean(ground_pts[:,2])
        
        self.log(f"  地面高度: {ground_z:.3f} m")
        
        # 楼板
        mid_mask = (pts_down[:,2] > ground_z + 2.5) & (pts_down[:,2] < ground_z + 4.0)
        mid_pts = pts_down[mid_mask]
        
        if len(mid_pts) > 5000:
            mid_pcd = o3d.geometry.PointCloud()
            mid_pcd.points = o3d.utility.Vector3dVector(mid_pts)
            sp, si = mid_pcd.segment_plane(self.threshold_spin.value(), 3, 1000)
            slab_pts = np.asarray(mid_pcd.select_by_index(si).points)
            slab_z = np.mean(slab_pts[:,2])
            
            measured_height = slab_z - ground_z
            self.log(f"  楼板高度: {slab_z:.3f} m")
            self.log(f"  实测净高: {measured_height:.3f} m")
        else:
            measured_height = None
            self.log("  未检测到楼板")
        
        self.progress_bar.setValue(60)
        self.log("\n【4】墙面检测...")
        
        # 墙面检测
        above_mask = pts_down[:,2] > ground_z + 0.5
        above_pts = pts_down[above_mask]
        
        wall_pcd = o3d.geometry.PointCloud()
        wall_pcd.points = o3d.utility.Vector3dVector(above_pts)
        
        fp, fi = wall_pcd.segment_plane(self.threshold_spin.value(), 3, 1000)
        remaining = wall_pcd
        if abs(fp[2]) > 0.5:
            remaining = wall_pcd.select_by_index(fi, invert=True)
        
        walls = []
        wid = 0
        while len(remaining.points) > 3000 and wid < 6:
            plane, inliers = remaining.segment_plane(self.threshold_spin.value(), 3, 1000)
            if len(inliers) < 3000: break
            
            seg = remaining.select_by_index(inliers)
            remaining = remaining.select_by_index(inliers, invert=True)
            
            if abs(plane[2]) < 0.15:
                wpts = np.asarray(seg.points)
                a,b,c,d = plane
                norm = np.sqrt(a*a+b*b+c*c)
                dists = np.abs(a*wpts[:,0]+b*wpts[:,1]+c*wpts[:,2]+d)/norm
                minc = np.min(wpts, axis=0)
                maxc = np.max(wpts, axis=0)
                
                walls.append({
                    'id': wid,
                    'length': max(maxc[0]-minc[0], maxc[1]-minc[1]),
                    'height': maxc[2]-minc[2],
                    'center': np.mean(wpts, axis=0),
                    'normal': [a,b,c],
                    'flat_p95': np.percentile(dists,95)*1000,
                    'flat_mean': np.mean(dists)*1000,
                    'verticality': abs(c)*1000
                })
                wid += 1
        
        self.log(f"  检测到 {len(walls)} 面墙")
        
        self.progress_bar.setValue(80)
        self.log("\n【5】生成报告...")
        
        # 显示结果
        self.display_results(walls, measured_height)
        
        self.progress_bar.setValue(100)
        self.log("\n✓ 检测完成!")
        
        self.export_excel_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        self.result_tabs.setCurrentIndex(1)
        
        self.last_results = {'walls': walls, 'height': measured_height}
    
    def display_results(self, walls, measured_height):
        """显示检测结果"""
        rows = []
        
        # 楼层净高
        if measured_height:
            rows.append(['楼层净高', '净高', '-', f'{measured_height:.3f}m', '-', '需对比设计值'])
        
        # 墙面
        for w in walls:
            v_ok = w['verticality'] < 5
            f_ok = w['flat_p95'] < 8
            
            rows.append([
                f'墙{w["id"]} 垂直度',
                '墙面质量',
                '-',
                f'{w["verticality"]:.2f} mm/m',
                f'{w["verticality"]:.2f}',
                '✓合格' if v_ok else '✗超差'
            ])
            
            rows.append([
                f'墙{w["id"]} 平整度',
                '墙面质量',
                '8mm',
                f'{w["flat_p95"]:.1f} mm',
                f'{w["flat_p95"]:.1f}',
                '✓合格' if f_ok else ('⚠警告' if w['flat_p95'] < 16 else '✗超差')
            ])
        
        self.result_table.setRowCount(len(rows))
        
        status_colors = {
            '✓合格': QColor('#4CAF50'),
            '⚠警告': QColor('#FF9800'),
            '✗超差': QColor('#F44336'),
            '需对比设计值': QColor('#9E9E9E')
        }
        
        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                
                if col_idx == 5:  # 状态列
                    color = status_colors.get(value, QColor('gray'))
                    item.setForeground(color)
                
                self.result_table.setItem(row_idx, col_idx, item)
    
    def export_excel(self):
        """导出Excel"""
        if not self.last_results:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出Excel",
            f"验房报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Excel Files (*.xlsx)"
        )
        
        if file_path:
            try:
                import pandas as pd
                
                data = []
                for w in self.last_results['walls']:
                    data.append({
                        '检测项': f'墙{w["id"]} 垂直度',
                        '实测值': w['verticality'],
                        '单位': 'mm/m',
                        '状态': '合格' if w['verticality'] < 5 else '超差'
                    })
                    data.append({
                        '检测项': f'墙{w["id"]} 平整度',
                        '实测值': w['flat_p95'],
                        '单位': 'mm',
                        '状态': '合格' if w['flat_p95'] < 8 else '超差'
                    })
                
                if self.last_results['height']:
                    data.append({
                        '检测项': '楼层净高',
                        '实测值': self.last_results['height'],
                        '单位': 'm',
                        '状态': '待对比'
                    })
                
                df = pd.DataFrame(data)
                df.to_excel(file_path, index=False)
                self.log(f"✓ 已导出: {file_path}")
                
            except Exception as e:
                self.log(f"✗ 导出失败: {e}")
    
    def export_json(self):
        """导出JSON"""
        if not self.last_results:
            return
        
        import json
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出JSON",
            f"验房报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json)"
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.last_results, f, indent=2, ensure_ascii=False)
            self.log(f"✓ 已导出: {file_path}")
    
    def generate_heatmaps(self):
        """生成偏差热力图"""
        if not self.las_path or not self.last_results:
            QMessageBox.warning(self, "警告", "请先完成验房分析")
            return
        
        self.log("\n生成偏差热力图...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            viz = DeviationVisualizer()
            
            # 准备墙面数据
            walls_for_viz = []
            for w in self.last_results.get('walls', []):
                if 'points' in w:
                    walls_for_viz.append(w)
            
            # 生成可视化
            results = viz.create_summary_visualization(walls_for_viz, 'output')
            
            # 显示结果
            self.viz_preview.clear()
            self.viz_preview.append(f"已生成 {len(results['heatmaps'])} 张热力图:\n")
            for hm in results['heatmaps']:
                self.viz_preview.append(f"  • {hm['wall']}: {hm['path']}\n")
            
            self.viz_preview.append(f"\n汇总图: {results['summary_chart']}\n")
            
            stats = results['statistics']
            self.viz_preview.append(f"\n统计结果:\n")
            self.viz_preview.append(f"  平整度: 合格{stats['flatness_ok']} 警告{stats['flatness_warning']} 超差{stats['flatness_error']}\n")
            self.viz_preview.append(f"  垂直度: 合格{stats['verticality_ok']} 警告{stats['verticality_warning']} 超差{stats['verticality_error']}\n")
            
            self.log("✓ 热力图生成完成")
            
        except Exception as e:
            self.log(f"✗ 生成失败: {e}")
            QMessageBox.critical(self, "错误", str(e))
        
        self.progress_bar.setVisible(False)
    
    def generate_3d_scene(self):
        """生成3D交互场景"""
        if not self.las_path or not self.last_results:
            QMessageBox.warning(self, "警告", "请先完成验房分析")
            return
        
        self.log("\n生成3D交互场景...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            viz = DeviationVisualizer()
            
            walls_for_viz = self.last_results.get('walls', [])
            
            html_path = viz.generate_3d_scene(
                self.las_path,
                walls_for_viz,
                'output/3d_scene.html'
            )
            
            if html_path:
                self.viz_preview.clear()
                self.viz_preview.append(f"✓ 3D交互场景已生成:\n\n")
                self.viz_preview.append(f"文件路径: {html_path}\n\n")
                self.viz_preview.append("可在浏览器中打开查看，支持:\n")
                self.viz_preview.append("  • 360度旋转查看\n")
                self.viz_preview.append("  • 缩放和平移\n")
                self.viz_preview.append("  • 点击查看点云偏差\n")
                
                self.log(f"✓ 3D场景生成完成: {html_path}")
            else:
                self.viz_preview.append("提示: 需安装 plotly 库\npip install plotly")
                self.log("需要安装 plotly")
            
        except Exception as e:
            self.log(f"✗ 生成失败: {e}")
            QMessageBox.critical(self, "错误", str(e))
        
        self.progress_bar.setVisible(False)
    
    def open_output_dir(self):
        """打开输出目录"""
        import subprocess
        
        output_dir = os.path.join(os.path.dirname(self.las_path) if self.las_path else '.', 'output')
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Linux
        subprocess.run(['xdg-open', output_dir])
        self.log(f"打开目录: {output_dir}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()