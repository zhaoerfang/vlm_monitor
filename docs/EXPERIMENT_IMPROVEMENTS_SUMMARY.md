# VLM监控系统实验改进总结

## 改进概述

根据用户反馈，我们对VLM监控系统的实验日志和文件组织进行了三项重要改进：

1. **实验日志按帧范围排序** - 便于调试分析
2. **视频文件组织优化** - MP4文件移入对应的details文件夹
3. **实验目录分类管理** - 按test1, test2...格式统一管理

## 改进详情

### 1. 实验日志排序优化

**问题**：`experiment_log.json`中的`inference_log`字段记录顺序混乱，不便于调试分析。

**解决方案**：
- 修改`AsyncVideoProcessor._save_experiment_log()`方法
- 按`original_frame_range[0]`（起始帧号）对推理日志进行排序
- 添加排序状态日志输出

**代码变更**：
```python
def _save_experiment_log(self):
    # 按original_frame_range排序inference_log，方便调试
    sorted_experiment_log = sorted(
        self.experiment_log, 
        key=lambda x: x.get('video_info', {}).get('original_frame_range', [0, 0])[0]
    )
    
    # 使用排序后的日志
    'inference_log': sorted_experiment_log
```

**效果验证**：
- 排序前：[58, 1, 115, 172, 229]
- 排序后：[1, 58, 115, 172, 229]

### 2. 视频文件组织优化

**问题**：`sampled_video_*.mp4`文件散落在实验目录外层，与对应的`*_details`文件夹分离。

**解决方案**：
- 修改`AsyncVideoProcessor._save_video_details()`方法
- 自动将MP4文件移动到对应的details文件夹内
- 更新所有相关路径引用

**代码变更**：
```python
def _save_video_details(self, sampled_frames, video_path, creation_time):
    # 将视频文件移动到details文件夹内
    new_video_path = os.path.join(details_dir, os.path.basename(video_path))
    if os.path.exists(video_path) and video_path != new_video_path:
        import shutil
        shutil.move(video_path, new_video_path)
        logger.debug(f"视频文件已移动到: {new_video_path}")
    
    return {'video_path': new_video_path}  # 返回新路径
```

**文件组织效果**：
```
test8/
├── experiment_log.json
├── sampled_video_1748483106978_details/
│   ├── sampled_video_1748483106978.mp4  ← 移入文件夹
│   ├── video_details.json
│   └── frame_*.jpg (15个帧文件)
└── ...
```

### 3. 实验目录分类管理

**问题**：实验文件使用`experiment_YYYYMMDD_HHMMSS`格式，目录混乱难以管理。

**解决方案**：
- 修改测试脚本支持`test1`, `test2`...格式
- 自动检测现有test目录编号，分配下一个可用编号
- 创建整理工具批量转换现有目录

**代码变更**：
```python
# 创建实验目录 - 支持test编号分类
import glob
existing_tests = glob.glob("tmp/test*")
if existing_tests:
    test_numbers = []
    for test_dir in existing_tests:
        try:
            test_num = int(test_dir.split('test')[-1])
            test_numbers.append(test_num)
        except ValueError:
            continue
    next_test_num = max(test_numbers) + 1 if test_numbers else 1
else:
    next_test_num = 1

experiment_dir = Path(f"tmp/test{next_test_num}")
```

## 整理工具

创建了`tools/organize_experiment_directories.py`工具脚本，可以：

1. **批量重命名**：`experiment_*` → `test*`
2. **日志排序**：自动排序现有实验日志
3. **文件整理**：移动MP4文件到details文件夹
4. **状态报告**：显示整理前后的目录状态

### 使用方法

```bash
python tools/organize_experiment_directories.py
```

### 整理效果

**整理前**：
```
tmp/
├── experiment_20250527_123651/
├── experiment_20250528_165553/
├── experiment_20250529_094434/
└── ...
```

**整理后**：
```
tmp/
├── test1/  (原experiment_20250527_123651)
├── test2/  (原experiment_20250528_165553)
├── test8/  (原experiment_20250529_094434)
└── ...
```

## 测试验证

### 功能测试

创建了`tests/test_experiment_improvements.py`测试脚本，验证：

1. **排序功能**：inference_log按帧范围正确排序
2. **文件组织**：MP4文件正确移入details文件夹
3. **目录分类**：test编号逻辑正确工作

**测试结果**：
```
🎯 总体测试: ✅ 全部通过
  1. 实验功能改进: ✅ 通过
  2. 目录分类功能: ✅ 通过
```

### 实际应用验证

对现有8个实验目录进行整理：

- **重命名成功**：8个experiment_*目录 → test1-test8
- **日志排序**：2个目录的日志重新排序
- **文件移动**：13个MP4文件移入对应details文件夹

## 配置文件支持

所有改进都与现有的`config.json`配置系统兼容：

```json
{
  "video_processing": {
    "target_video_duration": 3.0,
    "frames_per_second": 5,
    "target_frames_per_video": 15
  },
  "vlm": {
    "max_concurrent_inferences": 3,
    "model": "qwen-vl-max-latest"
  },
  "testing": {
    "n_frames_default": 50,
    "result_timeout": 180
  }
}
```

## 向后兼容性

所有改进都保持向后兼容：

1. **现有代码**：无需修改即可使用新功能
2. **现有数据**：通过整理工具可无损升级
3. **API接口**：保持不变，只是内部优化

## 总结

通过这三项改进，VLM监控系统的实验管理变得更加：

- **有序**：日志按时间顺序排列，便于分析
- **整洁**：文件组织清晰，相关文件集中管理
- **规范**：统一的目录命名，便于批量操作

这些改进显著提升了系统的可维护性和用户体验，为后续的开发和调试工作奠定了良好基础。 