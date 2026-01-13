# utils/ClickRecorder.py
import os
import sys
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from typing import List, Dict, Tuple, Optional, Union
import logging

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from util.WindowManager import WindowManager

logger = logging.getLogger(__name__)


class ClickRecorder:
    """
    点击位置记录器
    在截图上标记点击位置，方便调试和验证
    """

    def __init__(self, output_dir: str = "click_records", window_manager: WindowManager = None):
        """
        初始化点击记录器

        Args:
            output_dir: 输出目录
            window_manager: WindowManager实例
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.window_manager = window_manager or WindowManager()
        self.click_history = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 颜色定义
        self.colors = {
            'click': (0, 255, 0),  # 绿色 - 普通点击
            'test': (255, 255, 0),  # 黄色 - 测试点击
            'error': (0, 0, 255),  # 红色 - 错误位置
            'success': (0, 255, 0),  # 绿色 - 成功点击
            'expected': (255, 165, 0)  # 橙色 - 期望位置
        }

        # 标记样式
        self.marker_size = 20
        self.line_thickness = 2

    def mark_click_on_screenshot(self,
                                 image_path: Union[str, Path],
                                 click_points: List[Tuple[int, int, str]],
                                 save_path: Optional[Union[str, Path]] = None,
                                 show_info: bool = True) -> str:
        """
        在截图上标记点击位置

        Args:
            image_path: 原始截图路径
            click_points: 点击点列表 [(x, y, type), ...]
            save_path: 保存路径，如果为None则自动生成
            show_info: 是否显示坐标信息

        Returns:
            标记后的图片路径
        """
        try:
            # 读取图片
            if isinstance(image_path, (str, Path)):
                img = cv2.imread(str(image_path))
            else:
                # 如果是numpy数组
                img = image_path.copy()

            if img is None:
                logger.error(f"无法读取图片: {image_path}")
                return ""

            height, width = img.shape[:2]

            # 在图片上标记每个点击点
            for i, (x, y, click_type) in enumerate(click_points):
                color = self.colors.get(click_type, self.colors['click'])

                # 绘制十字标记
                cv2.line(img, (x - self.marker_size, y), (x + self.marker_size, y),
                         color, self.line_thickness)
                cv2.line(img, (x, y - self.marker_size), (x, y + self.marker_size),
                         color, self.line_thickness)

                # 绘制外圈圆
                cv2.circle(img, (x, y), self.marker_size + 5, color, 1)

                # 显示坐标和序号
                if show_info:
                    text = f"{i + 1}:({x},{y})"
                    # 文本背景
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    text_size = cv2.getTextSize(text, font, 0.5, 1)[0]

                    # 文本位置（避免超出边界）
                    text_x = x - text_size[0] // 2
                    text_y = y - self.marker_size - 20

                    # 调整位置如果超出边界
                    if text_y < 20:
                        text_y = y + self.marker_size + 30
                    if text_x < 10:
                        text_x = 10
                    elif text_x + text_size[0] > width - 10:
                        text_x = width - text_size[0] - 10

                    # 绘制文本背景
                    cv2.rectangle(img,
                                  (text_x - 5, text_y - 20),
                                  (text_x + text_size[0] + 5, text_y + 5),
                                  (0, 0, 0), -1)

                    # 绘制文本
                    cv2.putText(img, text, (text_x, text_y),
                                font, 0.5, (255, 255, 255), 1)

            # 绘制点击统计
            if show_info and click_points:
                self._draw_stats_info(img, click_points)

            # 保存图片
            if save_path is None:
                timestamp = datetime.now().strftime("%H%M%S_%f")[:-3]
                save_path = self.output_dir / f"click_marked_{timestamp}.png"
            else:
                save_path = Path(save_path)

            cv2.imwrite(str(save_path), img)
            logger.info(f"标记后的图片已保存: {save_path}")

            return str(save_path)

        except Exception as e:
            logger.error(f"标记点击位置失败: {e}", exc_info=True)
            return ""

    def _draw_stats_info(self, img: np.ndarray, click_points: List[tuple]):
        """在图片上绘制统计信息"""
        height, width = img.shape[:2]

        # 统计点击类型
        click_stats = {}
        for _, _, click_type in click_points:
            click_stats[click_type] = click_stats.get(click_type, 0) + 1

        # 绘制统计信息框
        info_texts = [
            f"总点击: {len(click_points)}",
            f"时间: {datetime.now().strftime('%H:%M:%S')}",
        ]

        for click_type, count in click_stats.items():
            info_texts.append(f"{click_type}: {count}")

        # 绘制背景框
        font = cv2.FONT_HERSHEY_SIMPLEX
        max_text_width = 0
        text_height = 0

        for text in info_texts:
            text_size = cv2.getTextSize(text, font, 0.5, 1)[0]
            max_text_width = max(max_text_width, text_size[0])
            text_height = max(text_height, text_size[1])

        box_width = max_text_width + 20
        box_height = len(info_texts) * (text_height + 5) + 20

        # 位置：右下角
        box_x = width - box_width - 20
        box_y = 20

        cv2.rectangle(img,
                      (box_x, box_y),
                      (box_x + box_width, box_y + box_height),
                      (0, 0, 0), -1)
        cv2.rectangle(img,
                      (box_x, box_y),
                      (box_x + box_width, box_y + box_height),
                      (255, 255, 255), 1)

        # 绘制文本
        for i, text in enumerate(info_texts):
            y = box_y + 20 + i * (text_height + 5)
            cv2.putText(img, text, (box_x + 10, y),
                        font, 0.5, (255, 255, 255), 1)

    def record_click(self,
                     x: int,
                     y: int,
                     click_type: str = "click",
                     description: str = "",
                     screenshot_before: bool = True,
                     screenshot_after: bool = True) -> Dict:
        """
        记录点击操作

        Args:
            x, y: 点击坐标
            click_type: 点击类型
            description: 描述
            screenshot_before: 是否点击前截图
            screenshot_after: 是否点击后截图

        Returns:
            点击记录字典
        """
        click_id = len(self.click_history) + 1
        timestamp = datetime.now()

        # 截图
        before_path = ""
        after_path = ""

        if screenshot_before and self.window_manager.connected_window:
            before_path = self._take_screenshot(f"click_{click_id}_before.png")

        # 记录点击
        click_record = {
            'id': click_id,
            'timestamp': timestamp.isoformat(),
            'x': x,
            'y': y,
            'type': click_type,
            'description': description,
            'screenshot_before': before_path,
            'screenshot_after': ""  # 稍后填充
        }

        self.click_history.append(click_record)

        # 如果有点击后截图
        if screenshot_after and self.window_manager.connected_window:
            after_path = self._take_screenshot(f"click_{click_id}_after.png")
            click_record['screenshot_after'] = after_path

        # 标记点击位置
        if before_path and os.path.exists(before_path):
            marked_path = self.mark_click_on_screenshot(
                before_path,
                [(x, y, click_type)],
                f"click_{click_id}_marked.png"
            )
            click_record['marked_screenshot'] = marked_path

        logger.info(f"记录点击 #{click_id}: ({x}, {y}) - {description}")
        return click_record

    def _take_screenshot(self, filename: str) -> str:
        """截图"""
        try:
            screenshot_path = str(self.output_dir / filename)
            success = self.window_manager.screenshot(screenshot_path)
            if success:
                return screenshot_path
        except Exception as e:
            logger.error(f"截图失败: {e}")
        return ""

    def save_click_report(self, report_name: str = None) -> str:
        """
        保存点击记录报告

        Args:
            report_name: 报告文件名

        Returns:
            报告文件路径
        """
        if report_name is None:
            report_name = f"click_report_{self.session_id}"

        report_path = self.output_dir / f"{report_name}.json"

        # 准备报告数据
        report_data = {
            'session_id': self.session_id,
            'start_time': self.session_id.replace('_', ' '),
            'end_time': datetime.now().strftime("%Y%m%d_%H%M%S").replace('_', ' '),
            'total_clicks': len(self.click_history),
            'clicks': self.click_history
        }

        # 保存JSON
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"点击报告已保存: {report_path}")
        return str(report_path)

    def create_click_analysis_image(self, image_path: Union[str, Path],
                                    expected_points: List[Tuple[int, int, str]] = None) -> str:
        """
        创建点击分析图，对比期望点击和实际点击

        Args:
            image_path: 基础图片路径
            expected_points: 期望的点击点 [(x, y, description), ...]

        Returns:
            分析图路径
        """
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                logger.error(f"无法读取图片: {image_path}")
                return ""

            height, width = img.shape[:2]

            # 绘制实际点击
            actual_points = [(record['x'], record['y'], 'actual')
                             for record in self.click_history]

            # 绘制期望点击
            if expected_points:
                for x, y, desc in expected_points:
                    # 绘制期望位置（虚线圆圈）
                    cv2.circle(img, (x, y), 15, self.colors['expected'], 1, cv2.LINE_AA)

                    # 绘制描述文本
                    if desc:
                        cv2.putText(img, desc, (x + 20, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['expected'], 1)

            # 绘制连接线（如果有点击历史）
            if len(self.click_history) > 1:
                for i in range(len(self.click_history) - 1):
                    x1, y1 = self.click_history[i]['x'], self.click_history[i]['y']
                    x2, y2 = self.click_history[i + 1]['x'], self.click_history[i + 1]['y']

                    # 绘制连接线
                    cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 1, cv2.LINE_AA)

                    # 计算距离
                    distance = int(np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
                    mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2

                    # 绘制距离文本
                    cv2.putText(img, f"{distance}px", (mid_x, mid_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # 保存分析图
            analysis_path = self.output_dir / f"click_analysis_{self.session_id}.png"
            cv2.imwrite(str(analysis_path), img)

            logger.info(f"点击分析图已保存: {analysis_path}")
            return str(analysis_path)

        except Exception as e:
            logger.error(f"创建分析图失败: {e}", exc_info=True)
            return ""


class AvatarClickRecorder(ClickRecorder):
    """
    针对头像点击的特殊记录器
    根据大话西游游戏界面优化
    """

    def __init__(self, window_manager: WindowManager = None):
        """初始化头像点击记录器"""
        super().__init__("avatar_click_records", window_manager)

        # 大话西游特定坐标
        self.avatar_positions = {
            'self_avatar': (1180, 150),  # 自己头像（1280x720基准）
            'team_avatar1': (1000, 200),  # 队友1
            'team_avatar2': (1000, 300),  # 队友2
            'enemy_avatar1': (400, 200),  # 敌人1
            'enemy_avatar2': (400, 300),  # 敌人2
        }

    def record_avatar_click(self,
                            avatar_type: str = "self",
                            offset_x: int = 0,
                            offset_y: int = 0,
                            base_resolution: Tuple[int, int] = (1280, 720)) -> Dict:
        """
        记录头像点击

        Args:
            avatar_type: 头像类型
            offset_x, offset_y: 偏移量
            base_resolution: 基准分辨率

        Returns:
            点击记录
        """
        # 获取当前窗口尺寸
        if not self.window_manager.connected_window:
            logger.error("未连接到窗口")
            return {}

        current_width = self.window_manager.connected_window['width']
        current_height = self.window_manager.connected_window['height']

        # 计算缩放比例
        scale_x = current_width / base_resolution[0]
        scale_y = current_height / base_resolution[1]

        # 获取基础坐标
        if avatar_type in self.avatar_positions:
            base_x, base_y = self.avatar_positions[avatar_type]
        else:
            base_x, base_y = self.avatar_positions['self_avatar']

        # 计算实际坐标
        actual_x = int(base_x * scale_x) + offset_x
        actual_y = int(base_y * scale_y) + offset_y

        # 边界检查
        actual_x = max(0, min(actual_x, current_width - 1))
        actual_y = max(0, min(actual_y, current_height - 1))

        # 记录点击
        description = f"头像点击: {avatar_type}, 偏移: ({offset_x}, {offset_y})"
        return self.record_click(actual_x, actual_y, "avatar_click", description)


# 测试工具
def test_click_recorder():
    """测试点击记录器"""
    recorder = ClickRecorder()

    # 测试数据
    test_image = np.zeros((500, 500, 3), dtype=np.uint8)
    test_image[:] = (50, 50, 50)  # 灰色背景

    # 添加一些测试点击点
    click_points = [
        (100, 100, "test"),
        (200, 200, "click"),
        (300, 300, "success"),
        (400, 100, "error"),
        (100, 400, "expected"),
    ]

    # 标记点击
    marked_path = recorder.mark_click_on_screenshot(
        test_image,
        click_points,
        "test_marked.png"
    )

    print(f"测试图片已保存: {marked_path}")

    # 记录一些点击
    for i, (x, y, click_type) in enumerate(click_points):
        recorder.record_click(x, y, click_type, f"测试点击 {i + 1}")

    # 保存报告
    report_path = recorder.save_click_report("test_report")
    print(f"测试报告已保存: {report_path}")


# 使用示例
async def example_usage():
    """使用示例"""
    from util.WindowsAsyncAirtestHelper import EnhancedWindowsAsyncAirtestHelper
    import asyncio

    # 创建助手
    helper = EnhancedWindowsAsyncAirtestHelper()

    # 连接窗口
    if await helper.smart_connect_async(["大话西游"]):
        # 创建记录器
        recorder = AvatarClickRecorder(helper.window_manager)

        print("开始记录点击测试...")

        # 测试不同位置的点击
        test_cases = [
            ("自己头像", 0, 0),
            ("向右偏移", 20, 0),
            ("向下偏移", 0, 20),
            ("组合偏移", 10, 10),
        ]

        for avatar_type, offset_x, offset_y in test_cases:
            print(f"\n测试: {avatar_type}")

            # 截图前
            before_screenshot = await helper.take_screenshot_async("before_test.png")

            # 记录点击
            click_record = recorder.record_avatar_click(
                avatar_type="self",
                offset_x=offset_x,
                offset_y=offset_y
            )

            # 执行实际点击
            success = await helper.click_avatar_by_relative_position_async(
                avatar_type="self",
                offset_x=offset_x,
                offset_y=offset_y
            )

            # 截图后
            after_screenshot = await helper.take_screenshot_async("after_test.png")

            print(f"  点击坐标: ({click_record['x']}, {click_record['y']})")
            print(f"  点击结果: {'✅ 成功' if success else '❌ 失败'}")

            # 标记点击位置
            if click_record.get('screenshot_before'):
                recorder.mark_click_on_screenshot(
                    click_record['screenshot_before'],
                    [(click_record['x'], click_record['y'], 'test')],
                    f"marked_{avatar_type}.png"
                )

        # 保存报告
        recorder.save_click_report("avatar_click_test")
        print("\n测试完成，报告已保存")

        # 创建分析图
        if recorder.click_history and recorder.click_history[0].get('screenshot_before'):
            recorder.create_click_analysis_image(
                recorder.click_history[0]['screenshot_before']
            )

    await helper.close()


if __name__ == "__main__":
    # 运行测试
    test_click_recorder()

    # 如果需要运行示例
    # asyncio.run(example_usage())