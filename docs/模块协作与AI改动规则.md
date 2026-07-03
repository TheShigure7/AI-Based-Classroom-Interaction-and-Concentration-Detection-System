# 模块协作与AI改动规则

## 1. 当前重构后的模块边界

### 主流程
- `backend/app/preview_camera.py`
- 责任：
  - 读取视频帧
  - 运行双线程调度
  - 组织 detector / pose / tracker / analysis 的调用顺序
  - 不直接写具体动作规则

### 摄像头输入
- `backend/app/services/camera/capture.py`
- 责任：
  - 打开视频源
  - 读取帧
  - 释放资源

### 目标检测
- `backend/app/services/detection/yolo_detector.py`
- 责任：
  - 加载 YOLO 模型
  - 输出 `person` / `cell phone` 检测结果
  - 维护 `DetectionResult`

### 姿态估计
- `backend/app/services/pose/mediapipe_estimator.py`
- 责任：
  - 加载 MediaPipe Pose 模型
  - 对单个学生框输出关键点
  - 不负责判断举手、低头、玩手机

### 跟踪
- `backend/app/services/tracking/student_tracker.py`
- 责任：
  - 维护匿名学生跟踪对象
  - 给检测框分配稳定对象
  - 保存学生的时序状态

### 行为分析
- `backend/app/services/analysis/behavior_rules.py`
- 责任：
  - 纯规则函数
  - 放阈值、几何判断、关键点规则

- `backend/app/services/analysis/hand_raise_analyzer.py`
- 责任：
  - 只封装举手判断

- `backend/app/services/analysis/phone_use_analyzer.py`
- 责任：
  - 只封装手机风险判断

- `backend/app/services/analysis/attention_analyzer.py`
- 责任：
  - 低头判断入口
  - 专注度更新
  - 全班专注度汇总

- `backend/app/services/analysis/behavior_engine.py`
- 责任：
  - 聚合多个动作分析器
  - 统一输出单个学生的动作状态
  - 是新增动作接入的主入口

## 2. 先冻结的接口

这些接口先不要改签名，内部实现可以优化。

### 摄像头
- `CameraService.open()`
- `CameraService.read_frame() -> np.ndarray`
- `CameraService.release()`

### 检测
- `YoloDetector.detect_targets(frame) -> list[DetectionResult]`
- `DetectionResult` 字段：
  - `label`
  - `confidence`
  - `bbox`
  - `track_id`
  - `attention_score`
  - `hand_raised`
  - `head_down`
  - `phone_risk`

### 姿态
- `MediaPipePoseEstimator.estimate_person_pose(frame, bbox) -> PoseEstimate | None`
- `PoseEstimate.landmarks`

### 跟踪
- `StudentTracker.update(person_bboxes) -> dict[int, TrackedStudent]`
- `TrackedStudent` 字段：
  - `track_id`
  - `bbox`
  - `attention_score`
  - `missed_frames`
  - `hand_raised`
  - `head_down`
  - `phone_risk`

### 行为分析
- `HandRaiseAnalyzer.analyze(landmarks) -> bool`
- `AttentionAnalyzer.is_head_down(landmarks) -> bool`
- `PhoneUseAnalyzer.is_phone_risk(person_bbox, phone_bbox, head_down) -> bool`
- `AttentionAnalyzer.update_attention_score(student) -> int`
- `AttentionAnalyzer.summarize(students) -> AttentionSummary`
- `BehaviorEngine.analyze_person(person_detection, phone_detections, pose_estimate) -> BehaviorState`

## 3. 每个人允许改哪些文件

### A. 性能优化负责人
- 可改：
  - `backend/app/preview_camera.py`
  - `backend/app/services/camera/capture.py`
  - `backend/app/services/tracking/student_tracker.py`
- 可新增：
  - `backend/app/services/pipeline/` 下的新文件
  - 性能统计辅助文件
- 不要改：
  - `analysis/` 里的业务规则
  - `DetectionResult` / `TrackedStudent` 已冻结字段名

### B. 检测和识别效果负责人
- 可改：
  - `backend/app/services/detection/yolo_detector.py`
  - `backend/app/services/pose/mediapipe_estimator.py`
  - `backend/app/services/preprocess/frame_processor.py`
  - `backend/app/services/analysis/behavior_rules.py`
- 可新增：
  - 新的预处理或模型适配文件
- 不要改：
  - 双线程主流程
  - 专注度评分规则
  - `preview_camera.py` 里的线程共享结构

### C. 动作和评分负责人
- 可改：
  - `backend/app/services/analysis/behavior_engine.py`
  - `backend/app/services/analysis/attention_analyzer.py`
  - `backend/app/services/analysis/*.py`
  - `backend/app/services/detection/yolo_detector.py` 中与显示状态直接相关的轻量部分
- 可新增：
  - `backend/app/services/analysis/` 下新的动作分析器
- 不要改：
  - 摄像头取流
  - 跟踪器匹配逻辑
  - YOLO / MediaPipe 模型加载接口签名

## 4. 新增动作应该怎么加

以“睡觉检测”为例。

### 第一步
- 新增文件：
  - `backend/app/services/analysis/sleeping_analyzer.py`

### 第二步
- 在文件内提供统一入口：

```python
class SleepingAnalyzer:
    def analyze(self, landmarks: list[object]) -> bool:
        ...
```

### 第三步
- 如果有共用几何规则，写到：
  - `backend/app/services/analysis/behavior_rules.py`

### 第四步
- 在：
  - `backend/app/services/analysis/behavior_engine.py`
  中接入这个动作

### 第五步
- 如果动作会影响分数，再改：
  - `backend/app/services/analysis/attention_analyzer.py`

### 第六步
- 如果动作需要显示文字或颜色，再改：
  - `backend/app/services/detection/yolo_detector.py`
  或后续专门的渲染模块

## 5. 开发时必须遵守的规则

1. 不要三个人同时改 `backend/app/preview_camera.py`
2. 不要随意改冻结接口的参数和返回值
3. 不要随意改 `DetectionResult` 和 `TrackedStudent` 已有字段名
4. 新增动作优先放到 `analysis/`，不要直接塞进主流程
5. 规则阈值尽量集中放到 `behavior_rules.py`
6. 如果一定要改接口，先发群里确认，再统一改调用方

## 6. 发给 AI 之前的限制提示词

下面这些话可以直接复制给 AI。

### 6.1 性能优化负责人给 AI 的提示词

```text
你只能修改以下文件：
- backend/app/preview_camera.py
- backend/app/services/camera/capture.py
- backend/app/services/tracking/student_tracker.py

你可以新增：
- backend/app/services/pipeline/ 下的新文件

你不能修改：
- backend/app/services/analysis/ 下的业务规则文件
- backend/app/services/detection/yolo_detector.py 的 DetectionResult 字段名
- backend/app/services/pose/mediapipe_estimator.py 的对外方法签名

要求：
1. 保持现有双线程主流程可以运行
2. 不要修改这些接口签名：
   - CameraService.read_frame()
   - StudentTracker.update(...)
   - YoloDetector.detect_targets(...)
3. 只做性能优化、线程优化、队列优化、缓冲优化
4. 如果需要新增文件，只能加在 services/pipeline/
5. 修改前先说明准备改哪些文件，修改后说明性能优化点
```

### 6.2 检测和识别效果负责人给 AI 的提示词

```text
你只能修改以下文件：
- backend/app/services/detection/yolo_detector.py
- backend/app/services/pose/mediapipe_estimator.py
- backend/app/services/preprocess/frame_processor.py
- backend/app/services/analysis/behavior_rules.py

你可以新增与检测预处理相关的辅助文件。

你不能修改：
- backend/app/preview_camera.py
- backend/app/services/tracking/student_tracker.py
- backend/app/services/analysis/attention_analyzer.py 的评分逻辑

要求：
1. 保持这些接口签名不变：
   - YoloDetector.detect_targets(frame)
   - MediaPipePoseEstimator.estimate_person_pose(frame, bbox)
2. 重点优化检测准确率、阈值、ROI、预处理、姿态稳定性
3. 不要改双线程结构
4. 修改前先列出要改的文件和原因
5. 修改后说明会影响哪些检测效果
```

### 6.3 动作和评分负责人给 AI 的提示词

```text
你只能修改以下文件：
- backend/app/services/analysis/behavior_engine.py
- backend/app/services/analysis/attention_analyzer.py
- backend/app/services/analysis/behavior_rules.py
- backend/app/services/analysis/*.py

你可以新增：
- backend/app/services/analysis/ 下的新动作分析器文件

你不能修改：
- backend/app/services/camera/capture.py
- backend/app/services/tracking/student_tracker.py
- backend/app/services/pose/mediapipe_estimator.py 的对外方法签名
- backend/app/preview_camera.py，除非只是接入已经新增的统一分析器接口

要求：
1. 新增动作时，优先新增 analyzer 文件，不要把规则直接写进 preview_camera.py
2. 保持这些接口兼容：
   - HandRaiseAnalyzer.analyze(...)
   - AttentionAnalyzer.update_attention_score(...)
   - BehaviorEngine.analyze_person(...)
3. 如果新增动作会影响分数，需要同时说明评分修改依据
4. 修改前先说明新增动作放在哪个文件
5. 修改后说明如何接入 behavior_engine
```
