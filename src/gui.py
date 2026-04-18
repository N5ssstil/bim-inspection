"""
BIM 点云验房系统 - GUI (更新版)
基于 PySide6 的桌面应用，支持完整验房流程
"""

import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QTextEdit, QGroupBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSplitter, QTabWidget, QComboBox, QDoubleSpinBox,
    QCheckBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import BIMInspectionApp


class InspectionThread(QThread):
    """验房处理线程"""
    progress = Signal(str)
    log = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, las_path, ifc_path=None, params=None):
        super().__init__()
        self.las_path = las_path
        self.ifc_path = ifc_path
        self.params = params or {}

    def run(self):
        try:
            app = BIMInspectionApp()
            
            # 1. 加载点云
            self.progress.emit("10%")
            self.log.emit(f"\n【步骤1】加载点云文件...")
            if not app.load_pointcloud(self.las_path):
                raise Exception("点云文件加载失败")
            self.log.emit(f"✓ 点云加载成功: {app.pointcloud_processor.points.shape[0]} 个点")
            
            # 2. 加载BIM（可选）
            self.progress.emit("20%")
            if self.ifc_path:
                self.log.emit(f"\n【步骤2】加载BIM模型...")
                if app.load_bim(self.ifc_path):
                    bim_data = app.analyze_bim()
                else:
                    self.log.emit("⚠ BIM加载失败，仅进行点云分析")
                    bim_data = {}
            else:
                self.log.emit("\n【步骤2】跳过BIM加载")
                bim_data = {}
            
            # 3. 点云预处理
            self.progress.emit("30%")
            self.log.emit(f"\n【步骤3】点云预处理...")
            voxel_size = self.params.get('voxel_size', 0.01)
            app.pointcloud_processor.preprocess(voxel_size=voxel_size)
            self.log.emit(f"✓ 下采样完成，当前点数: {len(app.pointcloud_processor.pcd.points)}")
            
            # 4. 平面分割
            self.progress.emit("50%")
            self.log.emit(f"\n【步骤4】平面分割...")
            distance_threshold = self.params.get('distance_threshold', 0.02)
            planes = app.pointcloud_processor.segment_planes(distance_threshold=distance_threshold)
            self.log.emit(f"✓ 检测到 {len(planes)} 个平面")
            
            # 5. 平面分类
            self.progress.emit("60%")
            self.log.emit(f"\n【步骤5】平面分类...")
            classified = app.pointcloud_processor.classify_planes(planes)
            self.log.emit(f"✓ 地面: {'找到' if classified.get('floor') else '未找到'}")
            self.log.emit(f"✓ 天花板: {'找到' if classified.get('ceiling') else '未找到'}")
            self.log.emit(f"✓ 墙面: {len(classified.get('walls', []))} 面")
            
            # 6. 质量分析
            self.progress.emit("70%")
            self.log.emit(f"\n【步骤6】质量分析...")
            quality_results = app.pointcloud_processor.full_quality_analysis(classified)
            
            # 显示分析结果
            if quality_results.get('floor_height'):
                self.log.emit(f"  楼层净高: {quality_results['floor_height']:.3f} m")
            if quality_results.get('span'):
                self.log.emit(f"  开间尺寸: {quality_results['span']:.3f} m")
            if quality_results.get('depth'):
                self.log.emit(f"  进深尺寸: {quality_results['depth']:.3f} m")
            
            for v in quality_results.get('wall_verticality', []):
                self.log.emit(f"  墙{v['wall_id']} 垂直度: {v['deviation_mm_per_m']:.2f} mm/m [{v['status']}]")
            for f in quality_results.get('wall_flatness', []):
                self.log.emit(f"  墙{f['wall_id']} 平整度: {f['max_deviation_mm']:.2f} mm [{f['status']}]")
            
            # 7. 生成报告
            self.progress.emit("90%")
            self.log.emit(f"\n【步骤7】生成验房报告...")
            app.comparison_engine = app.comparison_engine or app._create_comparison_engine()
            report = app.comparison_engine.process_quality_analysis(bim_data, quality_results)
            
            self.progress.emit("100%")
            self.log.emit("\n✓ 验房完成!")
            
            self.finished.emit({
                'quality_results': quality_results,
                'bim_data': bim_data,
                'report': report,
                'engine': app.comparison_engine
            })
            
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.las_path = None
        self.ifc_path = None
        self.last_results = None
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
        self.las_label = QLabel("未选择点云文件 (.las)")
        self.las_label.setStyleSheet("color: gray; font-size: 12px;")
        las_btn = QPushButton("选择点云")
        las_btn.setFixedWidth(100)
        las_btn.clicked.connect(self.select_las_file)
        las_row.addWidget(QLabel("点云:"))
        las_row.addWidget(self.las_label, 1)
        las_row.addWidget(las_btn)
        file_layout.addLayout(las_row)

        # BIM文件（可选）
        ifc_row = QHBoxLayout()
        self.ifc_label = QLabel("未选择 (可选)")
        self.ifc_label.setStyleSheet("color: gray; font-size: 12px;")
        ifc_btn = QPushButton("选择BIM")
        ifc_btn.setFixedWidth(100)
        ifc_btn.clicked.connect(self.select_ifc_file)
        self.ifc_skip_cb = QCheckBox("不对比BIM")
        self.ifc_skip_cb.setChecked(True)
        ifc_row.addWidget(QLabel("BIM:"))
        ifc_row.addWidget(self.ifc_label, 1)
        ifc_row.addWidget(ifc_btn)
        ifc_row.addWidget(self.ifc_skip_cb)
        file_layout.addLayout(ifc_row)

        layout.addWidget(file_group)

        # === 参数设置区 ===
        params_group = QGroupBox("分析参数")
        params_layout = QHBoxLayout(params_group)

        # 体素尺寸
        params_layout.addWidget(QLabel("下采样精度:"))
        self.voxel_spin = QDoubleSpinBox()
        self.voxel_spin.setRange(0.001, 0.1)
        self.voxel_spin.setValue(0.01)
        self.voxel_spin.setSingleStep(0.005)
        self.voxel_spin.setDecimals(3)
        params_layout.addWidget(self.voxel_spin)
        params_layout.addWidget(QLabel("m"))

        params_layout.addWidget(QLabel("  |  "))

        # 平面分割阈值
        params_layout.addWidget(QLabel("平面分割阈值:"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.01, 0.1)
        self.threshold_spin.setValue(0.02)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setDecimals(2)
        params_layout.addWidget(self.threshold_spin)
        params_layout.addWidget(QLabel("m"))

        params_layout.addStretch()
        layout.addWidget(params_group)

        # === 开始按钮 ===
        self.process_btn = QPushButton("▶ 开始验房分析")
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 12px;
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.process_btn.clicked.connect(self.start_processing)
        layout.addWidget(self.process_btn)

        # === 进度条 ===
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(25)
        self.status_label = QLabel("")
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.status_label)
        layout.addLayout(progress_row)

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
        
        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "检测项", "类别", "设计值", "实测值", "偏差(mm)", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        result_layout.addWidget(self.result_table)
        
        # 导出按钮
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
<tr>
    <td>楼层净高</td><td>±10 mm</td><td>合格: ≤10mm | 警告: ≤20mm | 超差: >20mm</td>
</tr>
<tr>
    <td>开间尺寸</td><td>±15 mm</td><td>合格: ≤15mm | 警告: ≤30mm | 超差: >30mm</td>
</tr>
<tr>
    <td>进深尺寸</td><td>±15 mm</td><td>合格: ≤15mm | 警告: ≤30mm | 超差: >30mm</td>
</tr>
<tr>
    <td>墙面垂直度</td><td>≤5 mm/m</td><td>合格: ≤5mm/m | 警告: ≤10mm/m | 超差: >10mm/m</td>
</tr>
<tr>
    <td>墙面平整度</td><td>≤8 mm</td><td>合格: ≤8mm | 警告: ≤16mm | 超差: >16mm</td>
</tr>
</table>
<p style="margin-top: 20px;">
<b>说明：</b><br>
• 垂直度检测：测量墙面法向量与铅垂线的夹角偏差<br>
• 平整度检测：测量墙面点云到拟合平面的最大距离偏差<br>
• 开间/进深：测量相互平行的墙体间距
</p>
        """)
        standards_layout.addWidget(standards_text)
        self.result_tabs.addTab(standards_tab, "质量标准")

        layout.addWidget(self.result_tabs, 1)

        # 状态栏
        self.statusBar().showMessage("请选择点云文件开始验房")

    def select_las_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云文件", "",
            "LAS Files (*.las *.laz);;All Files (*)"
        )
        if file_path:
            self.las_path = file_path
            self.las_label.setText(os.path.basename(file_path))
            self.las_label.setStyleSheet("color: green; font-size: 12px;")
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
            self.ifc_label.setStyleSheet("color: green; font-size: 12px;")
            self.ifc_skip_cb.setChecked(False)
            self.log("✓ 已选择BIM: " + os.path.basename(file_path))

    def check_ready(self):
        if self.las_path:
            self.process_btn.setEnabled(True)

    def log(self, message):
        self.log_text.append(message)

    def start_processing(self):
        if not self.las_path:
            QMessageBox.warning(self, "警告", "请先选择点云文件")
            return

        # 禁用按钮
        self.process_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_table.setRowCount(0)

        self.log("\n" + "="*50)
        self.log(f"验房开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*50)

        # 准备参数
        params = {
            'voxel_size': self.voxel_spin.value(),
            'distance_threshold': self.threshold_spin.value()
        }

        # 判断是否使用BIM
        ifc_path = None if self.ifc_skip_cb.isChecked() else self.ifc_path

        # 启动线程
        self.thread = InspectionThread(self.las_path, ifc_path, params)
        self.thread.progress.connect(self.on_progress)
        self.thread.log.connect(self.log)
        self.thread.finished.connect(self.on_finished)
        self.thread.error.connect(self.on_error)
        self.thread.start()

    def on_progress(self, percent):
        self.progress_bar.setValue(int(percent.replace('%', '')))
        self.statusBar().showMessage(f"处理中... {percent}")

    def on_finished(self, result):
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.last_results = result

        self.log("\n" + "="*50)
        self.log("验房完成!")
        self.log("="*50)

        # 显示结果
        self.display_results(result)

        # 启用导出
        self.export_excel_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)

        self.statusBar().showMessage("验房完成")
        self.result_tabs.setCurrentIndex(1)  # 切换到结果页

    def on_error(self, error):
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.log(f"\n✗ 错误: {error}")
        QMessageBox.critical(self, "错误", error)
        self.statusBar().showMessage("验房失败")

    def display_results(self, result):
        report = result.get('report', {})
        details = report.get('details', [])
        
        self.result_table.setRowCount(len(details))

        status_colors = {
            'ok': QColor('#4CAF50'),
            'warning': QColor('#FF9800'),
            'error': QColor('#F44336')
        }

        for row, detail in enumerate(details):
            # 检测项
            self.result_table.setItem(row, 0, QTableWidgetItem(detail['name']))
            # 类别
            self.result_table.setItem(row, 1, QTableWidgetItem(detail['category']))
            # 设计值
            bim_val = detail.get('bim_value', '-')
            if isinstance(bim_val, float):
                self.result_table.setItem(row, 2, QTableWidgetItem(f"{bim_val:.3f} m"))
            else:
                self.result_table.setItem(row, 2, QTableWidgetItem(str(bim_val)))
            # 实测值
            measured = detail['measured_value']
            unit = 'mm' if detail['category'] in ['墙面垂直度', '墙面平整度'] else 'm'
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{measured:.3f} {unit}"))
            # 偏差
            self.result_table.setItem(row, 4, QTableWidgetItem(f"{detail['deviation_mm']:.1f} mm"))
            # 状态
            status_item = QTableWidgetItem(detail['status'].upper())
            status_item.setBackground(status_colors.get(detail['status'], QColor('gray')))
            self.result_table.setItem(row, 5, status_item)

        # 显示汇总
        summary = report.get('summary', {})
        self.log(f"\n【检测汇总】")
        self.log(f"  总检测项: {summary.get('total', 0)}")
        self.log(f"  ✓ 合格: {summary.get('ok', 0)}")
        self.log(f"  ⚠ 警告: {summary.get('warning', 0)}")
        self.log(f"  ✗ 超差: {summary.get('error', 0)}")

    def export_excel(self):
        if not self.last_results:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出Excel", 
            f"验房报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Excel Files (*.xlsx)"
        )
        
        if file_path:
            engine = self.last_results.get('engine')
            if engine:
                engine.export_full_report_excel(file_path)
                self.log(f"✓ 已导出Excel: {file_path}")

    def export_json(self):
        if not self.last_results:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出JSON",
            f"验房报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json)"
        )
        
        if file_path:
            import json
            report = self.last_results.get('report', {})
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.log(f"✓ 已导出JSON: {file_path}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()