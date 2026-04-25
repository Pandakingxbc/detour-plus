# DETOUR-Plus Demo 录制脚本

> 录制时长建议: 3-5分钟
> 分辨率建议: 1920x1080, 30fps

## 准备工作

```bash
# 1. 确保环境激活
conda activate detour

# 2. 确保在项目目录
cd /home/yangz/Agent/detour

# 3. 确保API密钥已配置
cat .env  # 验证 NEMOTRON_API_KEY 已设置
```

---

## 第一部分: 项目概述 (30秒)

**画外音/字幕:**
> "DETOUR-Plus 是一个基于多智能体的卫星碰撞规避系统，扩展了原版DETOUR项目，增加了多机动轨迹规划能力。"

**展示内容:**
1. 打开 README_YANGZ.md，展示架构图
2. 快速滚动展示关键特性

---

## 第二部分: 多机动优化器演示 (1分钟)

**终端命令:**

```bash
# 运行多机动优化器独立测试
python -c "
from engine.maneuver.multi_impulse import test_multi_impulse_optimizer
test_multi_impulse_optimizer()
"
```

**预期输出:**
```
=== Multi-Impulse Optimizer Test ===
Satellite: ISS (ZARYA) at altitude ~420 km

Conjunction 1: COSMOS 2251 DEB - TCA in 2.0h, miss=350m
Conjunction 2: FENGYUN 1C DEB - TCA in 4.0h, miss=800m
Conjunction 3: IRIDIUM 33 DEB - TCA in 8.0h, miss=2500m

Fuel budget: 10.0 kg
Target miss distance: 1000.0 m
...
Optimized sequence: N maneuvers
Total fuel: X.XX kg
Safety rating: safe/caution
```

**画外音:**
> "多机动优化器可以同时处理多个威胁，在燃料约束下规划最优的规避序列。"

---

## 第三部分: 完整Agent流水线演示 (2分钟)

### 3.1 标准模式 (5-agent)

```bash
python -m agents.run --demo "Scan for threats to ISS and plan avoidance"
```

**展示要点:**
- Scout Agent 扫描威胁
- Analyst Agent 评估风险
- Planner Agent 设计规避机动
- Safety Agent 验证安全性
- Ops Brief Agent 生成报告

### 3.2 战略模式 (6-agent + 多机动)

```bash
python -m agents.run --mode strategic --demo "ISS faces 3 critical conjunctions. Plan optimal multi-maneuver sequence with 10kg fuel budget."
```

**画外音:**
> "战略模式增加了Strategist Agent，能够处理多威胁场景，同时检测二次交会和轨道谐振风险。"

---

## 第四部分: 轨道谐振分析 (30秒)

```bash
python -c "
from engine.maneuver.harmonic_analysis import detect_orbital_resonance, OrbitalElements
import math

# ISS轨道参数
iss = OrbitalElements(
    semi_major_axis_m=6.798e6,
    eccentricity=0.0002,
    inclination_rad=math.radians(51.6),
    raan_rad=0, arg_perigee_rad=0, true_anomaly_rad=0
)

# 假设的碎片轨道 (1:1 共轨)
debris = OrbitalElements(
    semi_major_axis_m=6.798e6,  # 相同半长轴
    eccentricity=0.001,
    inclination_rad=math.radians(51.5),
    raan_rad=0.1, arg_perigee_rad=0, true_anomaly_rad=0.05
)

result = detect_orbital_resonance(iss, debris)
print(f'共振检测: {result.resonance_ratio}')
print(f'警告级别: {result.warning_level}')
print(f'描述: {result.description}')
"
```

**画外音:**
> "谐振分析模块可以检测潜在的轨道共振，预警可能导致周期性接近的危险轨道配置。"

---

## 第五部分: 前端可视化 (可选, 30秒)

```bash
# 启动完整系统
./run.sh
```

**展示内容:**
- 打开浏览器 http://localhost:3000
- 展示3D地球和卫星轨道可视化
- 展示碰撞威胁标记

---

## 录制技巧

1. **终端设置:**
   - 字体大小: 16px+
   - 背景: 深色主题
   - 清屏后再开始: `clear`

2. **录制工具推荐:**
   - OBS Studio (免费)
   - Kazam (Linux)
   - asciinema (终端录制，可转GIF)

3. **后期编辑:**
   - 加速等待部分 (API调用)
   - 添加字幕解释关键输出
   - 添加背景音乐 (可选)

---

## 快速录制命令 (asciinema)

```bash
# 安装 asciinema
pip install asciinema

# 录制终端会话
asciinema rec demo.cast

# 转换为 GIF (需要 agg)
# pip install asciinema-agg
agg demo.cast demo.gif
```

---

## GitHub 上传检查清单

- [ ] README_YANGZ.md 已更新
- [ ] .gitignore 包含敏感文件 (.env, __pycache__, node_modules)
- [ ] Demo GIF/视频已生成
- [ ] 代码无API密钥泄露
- [ ] License 文件存在

---

## 示例命令汇总

```bash
# 1. 激活环境
conda activate detour

# 2. 测试多机动优化器
python -c "from engine.maneuver.multi_impulse import test_multi_impulse_optimizer; test_multi_impulse_optimizer()"

# 3. 运行标准流水线
python -m agents.run --demo "Scan threats to ISS"

# 4. 运行战略模式
python -m agents.run --mode strategic --demo "Multi-maneuver planning"

# 5. 启动完整系统 (前后端)
./run.sh
```
