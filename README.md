# BIM 点云验房系统

对比 BIM 模型和点云扫描数据，自动检测房间尺寸偏差。

## 功能

- 房间标高对比
- 墙体尺寸对比
- 偏差可视化

## 数据格式

- BIM模型: .rvt (Revit) 或 .ifc
- 点云数据: .las 格式

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python src/main.py
```