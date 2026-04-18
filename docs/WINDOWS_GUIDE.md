# Windows 运行指南

## 一、安装 Python 环境

### 方法1：官方 Python（推荐新手）
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.10 或 3.11（**不要用 3.12+**，部分依赖可能不兼容）
3. 安装时**务必勾选**：
   - ✅ Add Python to PATH
   - ✅ Install pip

### 方法2：Miniconda（推荐进阶）
1. 访问 https://docs.conda.io/en/latest/miniconda.html
2. 下载 Windows 64-bit 版本
3. 安装完成后打开 **Anaconda Prompt**

```powershell
# 创建虚拟环境
conda create -n bim python=3.10
conda activate bim
```

---

## 二、获取项目代码

### 方法1：直接复制
将整个 `bim-inspection` 文件夹复制到 Windows，例如：
```
D:\Projects\bim-inspection\
```

### 方法2：Git 克隆（如果有远程仓库）
```powershell
cd D:\Projects
git clone <仓库地址> bim-inspection
cd bim-inspection
```

---

## 三、安装依赖

打开 **PowerShell** 或 **CMD**（Miniconda用户用 Anaconda Prompt）：

```powershell
# 进入项目目录
cd D:\Projects\bim-inspection

# 安装依赖（推荐使用国内镜像加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 依赖列表说明
| 包名 | 用途 |
|------|------|
| open3d | 点云处理与可视化 |
| laspy | LAS点云文件读取 |
| ifcopenshell | IFC/BIM文件解析 |
| PySide6 | GUI界面 |
| pandas | 数据处理 |
| pyvista | 3D可视化 |
| openpyxl | Excel导出 |

### 常见安装问题

**问题1：Open3D 安装失败**
```powershell
# 尝试指定版本
pip install open3d==0.17.0
```

**问题2：PySide6 安装慢**
```powershell
# 使用清华镜像
pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**问题3：ifcopenshell 安装失败**
```powershell
# 尝试 conda 安装
conda install -c conda-forge ifcopenshell
```

---

## 四、运行程序

### 运行 GUI 界面
```powershell
cd D:\Projects\bim-inspection
python src/gui.py
```

### 运行命令行测试
```powershell
# 测试环境
python tests/test_env.py

# 测试点云模块
python tests/test_pointcloud.py

# 测试 BIM 模块
python tests/test_bim.py
```

---

## 五、使用流程

1. **启动程序**
   ```powershell
   python src/gui.py
   ```

2. **导入数据**
   - 点击「导入点云」选择 `.las` 文件
   - 点击「导入BIM」选择 `.ifc` 文件

3. **设置参数**
   - 设置偏差阈值（默认已填）
   - 选择检测项

4. **执行检测**
   - 点击「开始检测」

5. **查看结果**
   - 结果表格中显示偏差
   - 点击「导出报告」生成 Excel

---

## 六、数据准备

### 点云数据 (.las)
- 使用激光扫描仪获取
- 常见设备：Faro、Leica、RIEGL
- 导出时选择 LAS 1.2 或 1.4 格式

### BIM 模型 (.ifc)
- Revit 导出：文件 → 导出 → IFC
- 确保导出时包含：
  - 墙体 (IfcWall)
  - 楼板 (IfcSlab)
  - 房间 (IfcSpace)

### Revit 转 IFC 步骤
1. 打开 Revit 模型
2. 文件 → 导出 → IFC
3. 选择 IFC 2x3 或 IFC 4
4. 勾选「导出房间」「导出墙体」
5. 保存 `.ifc` 文件

---

## 七、质量检测标准

| 检测项 | 允许偏差 | 备注 |
|--------|---------|------|
| 楼层净高 | ±10mm | 设计标高 |
| 开间尺寸 | ±15mm | |
| 进深尺寸 | ±15mm | |
| 墙面垂直度 | ≤5mm/m | 每米高度 |
| 墙面平整度 | ≤8mm/2m | 2m靠尺 |

---

## 八、常见问题

### Q: 运行报错 "DLL load failed"
A: 安装 Visual C++ Redistributable
- 下载：https://aka.ms/vs/17/release/vc_redist.x64.exe

### Q: Open3D 窗口无法显示
A: 确保显卡驱动已更新，或尝试：
```powershell
pip install open3d==0.16.0
```

### Q: 中文乱码
A: 确保文件编码为 UTF-8，在代码开头添加：
```python
# -*- coding: utf-8 -*-
```

### Q: IFC 文件读取失败
A: 确认 IFC 版本，部分旧版 IFC 2x 需要转换：
```powershell
pip install IfcConvert
IfcConvert input.ifc output.ifc
```

---

## 九、快捷命令（可选）

创建启动脚本 `run.bat`：
```batch
@echo off
cd /d D:\Projects\bim-inspection
call conda activate bim
python src/gui.py
pause
```

双击 `run.bat` 即可启动程序。

---

## 联系支持

如遇问题，请提供以下信息：
1. Python 版本：`python --version`
2. 系统版本：Windows 10/11
3. 错误截图或日志