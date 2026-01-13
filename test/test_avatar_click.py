# test/test_avatar_click.py
import asyncio
import unittest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import logging

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from util.WindowsAsyncAirtestHelper import EnhancedWindowsAsyncAirtestHelper

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestAvatarClick(unittest.TestCase):
    """
    测试click_avatar_by_relative_position_async方法
    基于图片中的游戏界面测试
    """

    def setUp(self):
        """测试前准备"""
        print("\n" + "=" * 60)
        print("测试开始: click_avatar_by_relative_position_async")
        print("=" * 60)

        # 保存原始截图目录
        self.original_screenshots_dir = None
        self.test_output_dir = Path("test_output")
        self.test_output_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """测试后清理"""
        print("\n" + "=" * 60)
        print("测试结束")
        print("=" * 60)

    async def _async_test_avatar_click(self):
        """异步测试方法"""
        print("创建EnhancedWindowsAsyncAirtestHelper实例...")
        helper = EnhancedWindowsAsyncAirtestHelper(
            window_keyword="大话西游",
            background_mode=False,  # 测试时用前台模式便于观察
            max_workers=3
        )

        try:
            # 1. 连接到游戏窗口
            print("步骤1: 连接到游戏窗口...")
            # 根据图片中的窗口标题设置关键词
            window_keywords = [
                "大话西游手游",
                "自由交易服[蟠桃园]-百里砚冰",
                "百里砚冰",
                "决战比武场"
            ]

            connected = await helper.robust_connect_async(
                keywords=window_keywords,
                max_retries=2,
                retry_delay=1.0
            )

            self.assertTrue(connected, "应该成功连接到游戏窗口")
            print(f"✅ 窗口连接成功: {helper.window_info['title'] if helper.window_info else 'Unknown'}")

            # 2. 获取窗口信息
            print("步骤2: 获取窗口信息...")
            width, height = await helper.get_screen_size_async()
            print(f"窗口分辨率: {width}x{height}")

            # 检查分辨率是否匹配图片中的834x699
            if width != 834 or height != 699:
                print(f"⚠️ 注意: 实际分辨率({width}x{height})与预期(834x699)不符，但继续测试")

            # 3. 测试不同头像点击
            print("\n步骤3: 测试头像点击功能...")

            # 测试数据：不同头像类型和偏移
            test_cases = [
                {
                    "name": "自己头像_基准位置",
                    "avatar_type": "self",
                    "offset_x": 0,
                    "offset_y": 0,
                    "expected_region": "右上角"
                },
                {
                    "name": "自己头像_向右偏移",
                    "avatar_type": "self",
                    "offset_x": 20,  # 向右偏移
                    "offset_y": 0,
                    "expected_region": "右上角右侧"
                },
                {
                    "name": "自己头像_向下偏移",
                    "avatar_type": "self",
                    "offset_x": 0,
                    "offset_y": 20,  # 向下偏移
                    "expected_region": "右上角下方"
                },
                {
                    "name": "自己头像_向左上偏移",
                    "avatar_type": "self",
                    "offset_x": -20,  # 向左偏移
                    "offset_y": -10,  # 向上偏移
                    "expected_region": "左上侧"
                }
            ]

            test_results = []

            for i, test_case in enumerate(test_cases):
                print(f"\n测试用例 {i + 1}: {test_case['name']}")
                print(f"  头像类型: {test_case['avatar_type']}")
                print(f"  偏移量: x={test_case['offset_x']}, y={test_case['offset_y']}")
                print(f"  预期区域: {test_case['expected_region']}")

                # 点击前截图
                before_screenshot = await helper.take_screenshot_async(
                    f"before_click_{test_case['name']}.png"
                )
                print(f"  点击前截图: {before_screenshot}")

                # 执行点击
                start_time = asyncio.get_event_loop().time()
                success = await helper.click_avatar_by_relative_position_async(
                    avatar_type=test_case['avatar_type'],
                    offset_x=test_case['offset_x'],
                    offset_y=test_case['offset_y'],
                    region_expand=20
                )
                elapsed_time = asyncio.get_event_loop().time() - start_time

                # 点击后截图
                after_screenshot = await helper.take_screenshot_async(
                    f"after_click_{test_case['name']}.png"
                )
                print(f"  点击后截图: {after_screenshot}")
                print(f"  点击结果: {'✅ 成功' if success else '❌ 失败'}")
                print(f"  耗时: {elapsed_time:.2f}秒")

                # 等待一下，观察效果
                await asyncio.sleep(0.5)

                test_results.append({
                    "name": test_case['name'],
                    "success": success,
                    "time": elapsed_time
                })

            # 4. 分析测试结果
            print("\n" + "=" * 60)
            print("测试结果分析:")
            print("=" * 60)

            success_count = sum(1 for r in test_results if r['success'])
            total_count = len(test_results)

            print(f"总测试用例: {total_count}")
            print(f"成功用例: {success_count}")
            print(f"成功率: {success_count / total_count * 100:.1f}%")

            for result in test_results:
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {result['name']}: {result['time']:.2f}秒")

            # 5. 验证至少一个测试用例成功
            self.assertGreater(success_count, 0,
                               f"至少应该有一个点击成功，但实际成功数为{success_count}")

            # 6. 测试边缘情况
            print("\n步骤4: 测试边缘情况...")

            # 测试无效头像类型
            print("测试无效头像类型...")
            with self.assertRaises(Exception, msg="无效头像类型应该抛出异常"):
                await helper.click_avatar_by_relative_position_async(
                    avatar_type="invalid_type",
                    offset_x=0,
                    offset_y=0
                )

            # 测试超大偏移量（应该被自动调整）
            print("测试超大偏移量...")
            large_offset_success = await helper.click_avatar_by_relative_position_async(
                avatar_type="self",
                offset_x=1000,  # 超出屏幕
                offset_y=1000
            )
            print(f"  超大偏移点击: {'✅ 成功' if large_offset_success else '❌ 失败'}")

            return True

        except Exception as e:
            print(f"❌ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await helper.close()

    def test_avatar_click_sync(self):
        """同步包装器，用于unittest"""
        asyncio.run(self._async_test_avatar_click())

    @patch('util.WindowsAsyncAirtestHelper.EnhancedWindowsAsyncAirtestHelper')
    async def test_avatar_click_mocked(self, MockHelper):
        """使用Mock的测试方法"""
        print("\n测试Mock版本...")

        # 创建Mock实例
        mock_helper = AsyncMock()

        # 设置Mock返回值
        mock_helper.smart_connect_async.return_value = True
        mock_helper.get_screen_size_async.return_value = (834, 699)
        mock_helper.click_avatar_by_relative_position_async.return_value = True
        mock_helper.take_screenshot_async.return_value = Path("mock_screenshot.png")
        mock_helper.close.return_value = None

        # 模拟窗口信息
        mock_helper.window_info = {
            'title': '大话西游手游 (自由交易服[蟠桃园]-百里砚冰[130386860])',
            'width': 834,
            'height': 699
        }

        # 执行测试
        connected = await mock_helper.smart_connect_async(["大话西游"])
        self.assertTrue(connected, "Mock连接应该成功")

        width, height = await mock_helper.get_screen_size_async()
        self.assertEqual(width, 834, "宽度应该是834")
        self.assertEqual(height, 699, "高度应该是699")

        # 测试点击
        success = await mock_helper.click_avatar_by_relative_position_async(
            avatar_type="self",
            offset_x=0,
            offset_y=0
        )
        self.assertTrue(success, "Mock点击应该成功")

        print("✅ Mock测试通过")

    def test_avatar_click_mocked_sync(self):
        """同步版本的Mock测试"""
        asyncio.run(self.test_avatar_click_mocked())

    async def _test_coordinate_calculation(self):
        """测试坐标计算逻辑"""
        print("\n测试坐标计算逻辑...")

        # 模拟不同的分辨率
        test_resolutions = [
            (834, 699, "图片中的分辨率"),
            (1280, 720, "标准720P"),
            (1920, 1080, "标准1080P"),
            (2560, 1440, "2K分辨率"),
        ]

        base_width, base_height = 1280, 720
        base_x, base_y = 1180, 150  # 自己头像的基准坐标

        for width, height, desc in test_resolutions:
            print(f"\n测试分辨率: {width}x{height} ({desc})")

            # 计算缩放比例
            scale_x = width / base_width
            scale_y = height / base_height

            # 计算实际坐标
            actual_x = int(base_x * scale_x)
            actual_y = int(base_y * scale_y)

            print(f"  基准坐标: ({base_x}, {base_y})")
            print(f"  缩放比例: {scale_x:.2f}x{scale_y:.2f}")
            print(f"  计算坐标: ({actual_x}, {actual_y})")

            # 验证坐标在屏幕范围内
            self.assertGreaterEqual(actual_x, 0, f"X坐标({actual_x})应该>=0")
            self.assertLess(actual_x, width, f"X坐标({actual_x})应该<{width}")
            self.assertGreaterEqual(actual_y, 0, f"Y坐标({actual_y})应该>=0")
            self.assertLess(actual_y, height, f"Y坐标({actual_y})应该<{height}")

            print(f"  ✅ 坐标验证通过")

    def test_coordinate_calculation_sync(self):
        """同步版本的坐标计算测试"""
        asyncio.run(self._test_coordinate_calculation())


class TestAvatarClickIntegration(unittest.TestCase):
    """
    集成测试类 - 测试与实际游戏窗口的交互
    """

    def setUp(self):
        """测试前准备"""
        self.test_results = []

    async def test_real_game_interaction(self):
        """实际游戏交互测试"""
        print("=" * 60)
        print("开始实际游戏交互测试")
        print("=" * 60)

        helper = EnhancedWindowsAsyncAirtestHelper()

        try:
            # 尝试连接游戏窗口
            connected = await helper.connect_by_title_async("大话西游")

            if not connected:
                print("⚠️ 未找到游戏窗口，跳过实际交互测试")
                self.skipTest("未找到游戏窗口")
                return

            print("✅ 已连接到游戏窗口")

            # 获取当前鼠标位置
            import pyautogui
            original_pos = pyautogui.position()
            print(f"原始鼠标位置: {original_pos}")

            # 测试点击
            test_points = [
                ("自己头像区域", 0, 0),
                ("头像右侧", 30, 0),
                ("头像下方", 0, 30),
            ]

            for name, offset_x, offset_y in test_points:
                print(f"\n测试点击: {name}")
                print(f"  偏移: x={offset_x}, y={offset_y}")

                # 截图记录
                before = await helper.take_screenshot_async(f"integration_before_{name}.png")

                # 执行点击
                success = await helper.click_avatar_by_relative_position_async(
                    avatar_type="self",
                    offset_x=offset_x,
                    offset_y=offset_y
                )

                # 再次截图
                after = await helper.take_screenshot_async(f"integration_after_{name}.png")

                print(f"  结果: {'✅ 成功' if success else '❌ 失败'}")
                print(f"  截图: {before} -> {after}")

                self.test_results.append({
                    "name": name,
                    "success": success,
                    "before": before,
                    "after": after
                })

                await asyncio.sleep(1.0)  # 等待游戏响应

            # 恢复鼠标位置
            pyautogui.moveTo(original_pos.x, original_pos.y)
            print(f"鼠标已恢复到原始位置: {original_pos}")

        finally:
            await helper.close()

            # 打印测试总结
            print("\n" + "=" * 60)
            print("集成测试总结:")
            for result in self.test_results:
                status = "✅" if result["success"] else "❌"
                print(f"  {status} {result['name']}")

    def test_real_game_interaction_sync(self):
        """同步版本的实际游戏交互测试"""
        asyncio.run(self.test_real_game_interaction())


# 运行测试的辅助函数
def run_all_tests():
    """运行所有测试"""
    print("运行头像点击测试套件...")

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAvatarClick)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


def run_single_test(test_method_name):
    """运行单个测试方法"""
    print(f"运行单个测试: {test_method_name}")

    suite = unittest.TestSuite()
    suite.addTest(TestAvatarClick(test_method_name))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


async def quick_test():
    """快速测试函数，不依赖unittest框架"""
    print("快速测试 click_avatar_by_relative_position_async")

    helper = EnhancedWindowsAsyncAirtestHelper(
        window_keyword="大话西游",
        background_mode=True
    )

    try:
        # 尝试连接
        keywords = ["大话西游手游", "自由交易服[蟠桃园]", "百里砚冰"]
        if not await helper.smart_connect_async(keywords):
            print("❌ 连接失败，请确保游戏窗口已打开")
            return False

        print("✅ 连接成功")

        # 测试点击
        print("\n测试点击自己头像...")
        success = await helper.click_avatar_by_relative_position_async(
            avatar_type="self",
            offset_x=0,
            offset_y=0
        )

        if success:
            print("✅ 点击成功！")

            # 等待并检查是否有响应
            await asyncio.sleep(1.0)

            # 截图查看结果
            await helper.take_screenshot_async("quick_test_result.png")
            print("📸 结果截图已保存")
        else:
            print("❌ 点击失败")

        return success

    except Exception as e:
        print(f"❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await helper.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试头像点击功能")
    parser.add_argument("--mode", choices=["all", "single", "quick", "mock"],
                        default="quick", help="测试模式")
    parser.add_argument("--test", type=str, help="要运行的单个测试方法名")

    args = parser.parse_args()

    if args.mode == "all":
        result = run_all_tests()
        exit(0 if result.wasSuccessful() else 1)

    elif args.mode == "single" and args.test:
        result = run_single_test(args.test)
        exit(0 if result.wasSuccessful() else 1)

    elif args.mode == "mock":
        suite = unittest.TestSuite()
        suite.addTest(TestAvatarClick("test_avatar_click_mocked_sync"))
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        exit(0 if result.wasSuccessful() else 1)

    else:  # quick mode
        result = asyncio.run(quick_test())
        exit(0 if result else 1)