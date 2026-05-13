# Phase 27 Task 1: 曲线渲染自动降采样（LTTB）

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 27`

## 目标

为 matplotlib 预览渲染引入 LTTB（Largest Triangle Three Buckets）降采样算法，超过 10k 点时自动降采样使渲染时间 <100ms，同时保持视觉形状。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `processing/downsample.py` | **新建**：LTTB 算法实现 |
| `ui/widgets/matplotlib_preview.py` | 集成降采样到渲染路径 |

## LTTB 算法实现

```python
# processing/downsample.py
from __future__ import annotations
from typing import Tuple
import numpy as np


def downsample_lttb(
    x: np.ndarray,
    y: np.ndarray,
    max_points: int = 10000,
) -> Tuple[np.ndarray, np.ndarray]:
    """LTTB（Largest Triangle Three Buckets）降采样。
    
    在保持视觉形状的前提下将数据点减少到 max_points 个。
    算法复杂度 O(n)，适合实时渲染。
    
    Args:
        x, y: 输入数据（已按 x 排序）。
        max_points: 目标点数。
    
    Returns:
        (x_down, y_down) 降采样后的数据。
    
    Reference:
        Sveinn Steinarsson. 2013.
        "Downsampling Time Series for Visual Representation."
    """
    n = len(x)
    if n <= max_points:
        return x, y
    
    # 桶数
    bucket_size = (n - 2) / (max_points - 2)
    
    # 结果数组（第一个点和最后一个点总是保留）
    idxs = [0]
    
    # 每个桶的平均位置
    a = 0
    for i in range(1, max_points - 1):
        # 当前桶的范围
        bucket_start = int(round((i - 1) * bucket_size) + 1)
        bucket_end = int(round(i * bucket_size) + 1)
        
        # 桶内平均值（用于计算三角形面积）
        avg_x = np.mean(x[bucket_start:bucket_end])
        avg_y = np.mean(y[bucket_start:bucket_end])
        
        # 在桶内找使三角形面积最大的点
        a_start = a
        a_end = bucket_start
        
        tri_area = np.abs(
            (x[a_start] - avg_x) * (y[a_end] - avg_y)
            - (x[a_start] - avg_x) * (y[a_end] - avg_y)
        )
        
        max_area = -1
        max_idx = bucket_start
        
        for j in range(bucket_start, bucket_end):
            area = abs(
                (x[a] - x[j]) * (y[bucket_end if bucket_end < n else n-1] - y[a])
                - (x[a] - x[bucket_end if bucket_end < n else n-1]) * (y[a] - y[j])
            )
            if area > max_area:
                max_area = area
                max_idx = j
        
        idxs.append(max_idx)
        a = max_idx
    
    idxs.append(n - 1)
    return x[idxs], y[idxs]


def should_downsample(n_points: int, max_points: int = 10000) -> bool:
    """判断是否需要降采样。"""
    return n_points > max_points
```

## 集成到 matplotlib_preview

```python
# ui/widgets/matplotlib_preview.py
from processing.downsample import downsample_lttb, should_downsample

def _render_curve(self, ax, x, y, **kwargs):
    """渲染单条曲线，自动降采样。"""
    if should_downsample(len(x)):
        x, y = downsample_lttb(np.array(x), np.array(y))
    ax.plot(x, y, **kwargs)
```

## 单元测试

```python
class TestDownsample(unittest.TestCase):
    def test_small_data_unchanged(self):
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([4.0, 5.0, 6.0])
        xd, yd = downsample_lttb(x, y, max_points=100)
        np.testing.assert_array_equal(x, xd)
    
    def test_large_data_reduced(self):
        x = np.arange(1000, dtype=float)
        y = np.sin(x / 100 * 2 * np.pi)
        xd, yd = downsample_lttb(x, y, max_points=50)
        self.assertLessEqual(len(xd), 50)
    
    def test_first_and_last_preserved(self):
        x = np.arange(100, dtype=float)
        y = np.random.rand(100)
        xd, yd = downsample_lttb(x, y, max_points=10)
        self.assertEqual(xd[0], x[0])
        self.assertEqual(xd[-1], x[-1])
```

## 验证清单

- [ ] 100k 点的曲线渲染时间 < 100ms
- [ ] 降采样前后的曲线视觉形状无明显差异
- [ ] 小数据（<10k 点）不触发降采样
- [ ] 测试通过

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
