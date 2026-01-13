# utils/AsyncADBHelper.py
import asyncio
import concurrent.futures
import sys
import os
import time
import logging
from typing import Optional, Tuple, List, Callable, Any, Dict, Union, Coroutine
from pathlib import Path
from functools import wraps
from dataclasses import dataclass
from enum import Enum


# 导入自定义模块
from util.adb_utils import LeidianADB
from util.EasyOCRTool import EasyOCRTool

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SearchDirection(Enum):
    """滑动搜索方向"""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class MatchStrategy(Enum):
    """匹配策略"""
    IMAGE = "image"  # 图片匹配
    OCR = "ocr"  # OCR文字识别
    BOTH = "both"  # 两者都尝试
    PRIORITY_IMAGE = "priority_image"  # 优先图片
    PRIORITY_OCR = "priority_ocr"  # 优先OCR


@dataclass
class SearchConfig:
    """搜索配置"""
    direction: SearchDirection = SearchDirection.DOWN
    swipe_duration: float = 0.5
    swipe_steps: int = 1
    max_swipes: int = 10
    wait_between_swipes: float = 0.5
    match_threshold: float = 0.8
    retry_times: int = 3


@dataclass
class WaitConfig:
    """等待配置"""
    timeout: float = 30.0
    interval: float = 0.5
    raise_error: bool = True
    screenshot_on_fail: bool = True
    retry_on_fail: bool = True


@dataclass
class MatchResult:
    """匹配结果"""
    success: bool
    position: Optional[Tuple[int, int]] = None
    confidence: float = 0.0
    bbox: Optional[Tuple[int, int, int, int]] = None
    text: Optional[str] = None
    error: Optional[str] = None


class AsyncADBHelper:
    """
    异步ADB助手类
    使用adb_utils和EasyOCRTool替代Airtest功能
    """

    def __init__(self,
                 emulator_port: int = 5555,
                 ld_console_path: Optional[str] = None,
                 max_workers: int = 5,
                 use_thread_pool: bool = True):
        """
        初始化异步助手

        Args:
            emulator_port: 模拟器端口
            ld_console_path: 雷电控制台路径
            max_workers: 线程池最大工作线程数
            use_thread_pool: 是否使用线程池处理阻塞操作
        """
        self.emulator_port = emulator_port
        self.ld_console_path = ld_console_path

        # 初始化ADB工具（同步方式）
        self.adb = LeidianADB(emulator_port=emulator_port, ld_console_path=ld_console_path)

        # 初始化OCR工具（同步方式）
        self.ocr = EasyOCRTool(lang=['ch_sim', 'en'], gpu=False)

        # 异步相关
        self.max_workers = max_workers
        self.use_thread_pool = use_thread_pool
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="adb_async_"
        )

        # 事件循环
        self.loop = None
        self._init_event_loop()

        # 状态跟踪
        self.active_tasks = set()
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)

        # 设置项目路径
        self._setup_project_paths()

    def _setup_project_paths(self):
        """设置项目路径"""
        # 获取脚本所在目录
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # 获取项目根目录
        self.project_root = os.path.dirname(self.script_dir)
        # 图片目录
        self.images_dir = os.path.join(self.project_root, "images")

        # 设置工作目录到项目根目录
        os.chdir(self.project_root)
        # 添加项目根目录到Python路径
        sys.path.insert(0, self.project_root)

        logger.info(f"项目根目录: {self.project_root}")
        logger.info(f"脚本目录: {self.script_dir}")
        logger.info(f"图片目录: {self.images_dir}")

    def _init_event_loop(self):
        """初始化事件循环"""
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    def connect_sync(self) -> bool:
        """同步连接设备（供同步代码使用）"""
        return self._connect_sync()

    def _connect_sync(self):
        """同步连接设备"""
        try:
            self._is_connected = self.adb.connect()
            if self._is_connected:
                logger.info(f"设备连接成功: 127.0.0.1:{self.emulator_port}")
            else:
                logger.error(f"设备连接失败: 127.0.0.1:{self.emulator_port}")
        except Exception as e:
            logger.error(f"设备连接异常: {e}")
            self._is_connected = False

        return self._is_connected

    async def connect_device_async(self) -> bool:
        """异步连接设备"""
        try:
            success = await self.run_in_threadpool(self.adb.connect)
            if success:
                logger.info(f"设备连接成功: 127.0.0.1:{self.emulator_port}")
            else:
                logger.error(f"设备连接失败: 127.0.0.1:{self.emulator_port}")
            return success
        except Exception as e:
            logger.error(f"设备连接异常: {e}")
            return False

    async def run_in_threadpool(self, func: Callable, *args, **kwargs) -> Any:
        """
        在线程池中运行阻塞函数

        Args:
            func: 要执行的函数
            *args, **kwargs: 函数参数

        Returns:
            函数执行结果
        """
        if not self.use_thread_pool:
            return func(*args, **kwargs)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.thread_pool,
            lambda: func(*args, **kwargs)
        )

    async def wait_element_async(self,
                                 target: Union[str, Path],
                                 config: WaitConfig = None,
                                 strategy: MatchStrategy = MatchStrategy.BOTH) -> bool:
        """
        异步等待元素出现（修正策略判断逻辑）
        """
        if config is None:
            config = WaitConfig()

        await self.ensure_connected()

        start_time = time.time()
        result = False

        # 根据target类型自动判断策略
        target_str = str(target)
        is_image_file = target_str.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))

        while time.time() - start_time < config.timeout:
            try:
                # 如果是指定策略或自动判断为图片，尝试图片匹配
                should_try_image = (
                        strategy in [MatchStrategy.IMAGE, MatchStrategy.BOTH, MatchStrategy.PRIORITY_IMAGE] or
                        (strategy == MatchStrategy.BOTH and is_image_file) or
                        (strategy == MatchStrategy.PRIORITY_IMAGE and is_image_file)
                )

                # 如果是指定策略或自动判断为文字，尝试文字匹配
                should_try_text = (
                        strategy in [MatchStrategy.OCR, MatchStrategy.BOTH, MatchStrategy.PRIORITY_OCR] or
                        (strategy == MatchStrategy.BOTH and not is_image_file) or
                        (strategy == MatchStrategy.PRIORITY_OCR and not is_image_file)
                )

                # 根据优先级决定执行顺序
                if strategy == MatchStrategy.PRIORITY_IMAGE:
                    # 优先图片匹配
                    if should_try_image:
                        result_obj = await self.exists_image_async(target)
                        result = result_obj.success
                        if result:
                            break

                    if should_try_text and not result:
                        result_obj = await self.exists_text_async(target)
                        result = result_obj.success
                        if result:
                            break

                elif strategy == MatchStrategy.PRIORITY_OCR:
                    # 优先文字匹配
                    if should_try_text:
                        result_obj = await self.exists_text_async(target)
                        result = result_obj.success
                        if result:
                            break

                    if should_try_image and not result:
                        result_obj = await self.exists_image_async(target)
                        result = result_obj.success
                        if result:
                            break

                else:
                    # BOTH 或 IMAGE/OCR 策略，同时尝试
                    if should_try_image:
                        result_obj = await self.exists_image_async(target)
                        result = result_obj.success
                        if result:
                            break

                    if should_try_text and not result:
                        result_obj = await self.exists_text_async(target)
                        result = result_obj.success
                        if result:
                            break

                if result:
                    break

            except Exception as e:
                logger.debug(f"等待元素时出错: {e}")

            await asyncio.sleep(config.interval)

        if not result and config.raise_error:
            if config.screenshot_on_fail:
                await self.take_screenshot_async("wait_element_failed.png")
            raise TimeoutError(f"等待元素超时: {target}")

        return result

    async def exists_image_async(self,
                                 image_path: Union[str, Path],
                                 threshold: float = 0.8) -> MatchResult:
        """
        异步检查图片是否存在（使用特征匹配）

        Args:
            image_path: 图片路径
            threshold: 匹配阈值

        Returns:
            MatchResult: 匹配结果
        """
        try:
            # 先截图
            screenshot_path = await self.take_screenshot_async("temp_screenshot.png")

            # 使用特征匹配
            result, _, _ = await self.run_in_threadpool(
                self.ocr.feature_match,
                str(image_path),
                str(screenshot_path),
                method="akaze",  # 优先使用AKAZE（抗干扰更强）
                match_ratio=threshold,
                min_matches=8,
                enhance_contrast=True,  # 增强对比度
                denoise=True,  # 降噪
                scale_ratios=[0.8, 1.0, 1.2]  # 多尺度匹配
            )

            if result and result.get('match_success', False):
                return MatchResult(
                    success=True,
                    position=result['center'],
                    confidence=result['confidence'],
                    bbox=result['bbox']
                )
            else:
                return MatchResult(success=False, confidence=0.0)

        except Exception as e:
            logger.error(f"检查图片存在时出错: {e}")
            return MatchResult(success=False, error=str(e))

    async def exists_text_async(self,
                                text: str,
                                confidence_threshold: float = 0.5) -> MatchResult:
        """
        异步检查文字是否存在

        Args:
            text: 要查找的文字
            confidence_threshold: 置信度阈值

        Returns:
            MatchResult: 匹配结果
        """
        try:
            # 先截图
            screenshot_path = await self.take_screenshot_async("temp_screenshot.png")

            # 使用OCR搜索文字
            matches = await self.run_in_threadpool(
                self.ocr.search_text,
                str(screenshot_path),
                text,
                confidence_threshold
            )

            if matches:
                best_match = matches[0]  # 取置信度最高的匹配
                return MatchResult(
                    success=True,
                    position=best_match['center'],
                    confidence=best_match['confidence'],
                    bbox=best_match['bbox'],
                    text=best_match['text']
                )
            else:
                return MatchResult(success=False, confidence=0.0)

        except Exception as e:
            logger.error(f"检查文字存在时出错: {e}")
            return MatchResult(success=False, error=str(e))

    async def touch_async(self,
                          target: Union[Tuple[float, float], str, Path, MatchResult],
                          wait_before: float = 0,
                          wait_after: float = 0) -> bool:
        """
        异步点击操作

        Args:
            target: 点击目标（坐标、图片路径、文字或MatchResult）
            wait_before: 点击前等待时间
            wait_after: 点击后等待时间

        Returns:
            是否点击成功
        """
        if wait_before > 0:
            await asyncio.sleep(wait_before)

        try:
            position = None

            # 处理不同类型的target
            if isinstance(target, tuple) and len(target) == 2:
                # 直接坐标
                position = target

            elif isinstance(target, (str, Path)):
                # 图片路径或文字
                result = await self.wait_element_async(str(target))
                if hasattr(result, 'position') and result.position:
                    position = result.position
                elif isinstance(result, bool) and result:
                    # 如果是bool True，尝试获取元素位置
                    if isinstance(target, Path) or (
                            isinstance(target, str) and target.endswith(('.png', '.jpg', '.jpeg'))):
                        img_result = await self.exists_image_async(str(target))
                        position = img_result.position if img_result.success else None
                    else:
                        text_result = await self.exists_text_async(str(target))
                        position = text_result.position if text_result.success else None

            elif isinstance(target, MatchResult) and target.success:
                # MatchResult对象
                position = target.position

            if position:
                x, y = int(position[0]), int(position[1])
                success = await self.run_in_threadpool(self.adb.safe_tap, x, y)

                if wait_after > 0:
                    await asyncio.sleep(wait_after)

                return success
            else:
                logger.error(f"无法确定点击位置: {target}")
                return False

        except Exception as e:
            logger.error(f"点击操作失败: {e}")
            return False

    async def swipe_find_element_async(self,
                                       target: Union[str, Path],
                                       search_config: SearchConfig = None,
                                       wait_config: WaitConfig = None) -> Optional[MatchResult]:
        """
        异步滑动查找元素

        Args:
            target: 目标元素（图片路径或文字）
            search_config: 搜索配置
            wait_config: 等待配置

        Returns:
            找到的元素匹配结果
        """
        if search_config is None:
            search_config = SearchConfig()

        if wait_config is None:
            wait_config = WaitConfig()

        # 先尝试直接等待
        logger.info(f"开始滑动查找元素: {target}")
        found = await self.wait_element_async(target, wait_config)
        if found:
            logger.info("直接找到元素，无需滑动")
            # 返回具体的匹配结果
            if isinstance(target, Path) or (isinstance(target, str) and target.endswith(('.png', '.jpg', '.jpeg'))):
                return await self.exists_image_async(str(target))
            else:
                return await self.exists_text_async(str(target))

        # 滑动查找
        screen_width, screen_height = await self.get_screen_size_async()
        logger.info(f"屏幕尺寸: {screen_width}x{screen_height}")

        for swipe_count in range(search_config.max_swipes):
            logger.info(f"第 {swipe_count + 1} 次滑动，方向: {search_config.direction}")

            # 执行滑动
            if not await self.swipe_in_direction_async(search_config.direction,
                                                       search_config.swipe_duration):
                logger.warning(f"第 {swipe_count + 1} 次滑动失败")
                continue

            # 等待滑动动画完成
            await asyncio.sleep(search_config.wait_between_swipes)

            # 查找元素
            element = await self._find_element_in_current_screen_async(target, search_config)
            if element is not None and element.success:
                logger.info(f"第 {swipe_count + 1} 次滑动后找到元素")
                return element

            # 截图记录
            if swipe_count % 3 == 0:  # 每3次滑动截图一次
                await self.take_screenshot_async(f"swipe_find_{swipe_count}.png")

        logger.warning(f"滑动 {search_config.max_swipes} 次后未找到元素")
        if wait_config.screenshot_on_fail:
            await self.take_screenshot_async("swipe_find_failed.png")

        if wait_config.raise_error:
            raise TimeoutError(f"滑动查找元素超时: {target}")

        return None

    async def swipe_in_direction_async(self,
                                       direction: SearchDirection,
                                       duration: float = 0.5) -> bool:
        """
        异步向指定方向滑动

        Args:
            direction: 滑动方向
            duration: 滑动持续时间（秒）

        Returns:
            是否滑动成功
        """
        screen_width, screen_height = await self.get_screen_size_async()

        # 计算滑动起点和终点（转换为像素坐标）
        if direction == SearchDirection.UP:
            start_x, start_y = screen_width // 2, int(screen_height * 0.8)
            end_x, end_y = screen_width // 2, int(screen_height * 0.2)
        elif direction == SearchDirection.DOWN:
            start_x, start_y = screen_width // 2, int(screen_height * 0.2)
            end_x, end_y = screen_width // 2, int(screen_height * 0.8)
        elif direction == SearchDirection.LEFT:
            start_x, start_y = int(screen_width * 0.8), screen_height // 2
            end_x, end_y = int(screen_width * 0.2), screen_height // 2
        elif direction == SearchDirection.RIGHT:
            start_x, start_y = int(screen_width * 0.2), screen_height // 2
            end_x, end_y = int(screen_width * 0.8), screen_height // 2
        else:
            raise ValueError(f"不支持的滑动方向: {direction}")

        try:
            # 转换为毫秒
            duration_ms = int(duration * 1000)
            success = await self.run_in_threadpool(
                self.adb.safe_swipe,
                start_x, start_y, end_x, end_y, duration_ms
            )
            logger.debug(f"滑动成功: {direction.value}")
            return success
        except Exception as e:
            logger.error(f"滑动失败: {e}")
            return False

    async def _find_element_in_current_screen_async(self,
                                                    target: Any,
                                                    search_config: SearchConfig) -> Optional[MatchResult]:
        """在当前屏幕中查找元素"""
        try:
            if isinstance(target, (str, Path)):
                target_str = str(target)
                if target_str.endswith(('.png', '.jpg', '.jpeg')):
                    # 图片匹配
                    return await self.exists_image_async(target_str, search_config.match_threshold)
                else:
                    # 文字匹配
                    return await self.exists_text_async(target_str, search_config.match_threshold)
            return None
        except Exception as e:
            logger.error(f"查找元素失败: {e}")
            return None

    async def get_screen_size_async(self) -> Tuple[int, int]:
        """异步获取屏幕尺寸"""
        try:
            resolution = await self.run_in_threadpool(self.adb.get_screen_resolution)
            if resolution:
                return resolution
            else:
                # 默认返回常见分辨率
                return 1080, 1920
        except Exception as e:
            logger.error(f"获取屏幕尺寸失败: {e}")
            return 1080, 1920  # 默认值

    async def take_screenshot_async(self, filename: str = None) -> Path | str:
        """
        异步截图

        Args:
            filename: 截图文件名

        Returns:
            截图文件路径
        """
        if filename is None:
            filename = f"screenshot.png"

        filepath =  filename

        try:
            screenshot_path = await self.run_in_threadpool(self.adb.capture_screen, str(filepath))
            if screenshot_path and os.path.exists(screenshot_path):
                logger.info(f"截图已保存: {screenshot_path}")
                return Path(screenshot_path)
            else:
                # 创建空文件作为占位
                filepath.touch()
                return filepath
        except Exception as e:
            logger.error(f"截图失败: {e}")
            filepath.touch()
            return filepath

    async def input_text_async(self,
                               text: str,
                               target_position: Optional[Tuple[float, float]] = None) -> bool:
        """
        异步输入文本

        Args:
            text: 要输入的文本
            target_position: 目标位置（可选，如果提供会先点击）

        Returns:
            是否输入成功
        """
        try:
            # 如果有目标位置，先点击
            if target_position:
                await self.touch_async(target_position)
                await asyncio.sleep(0.5)

            # 使用ADB输入文本
            success = await self.run_in_threadpool(self.adb.input_text, text)
            return success

        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False

    async def long_press_async(self,
                               target: Union[Tuple[float, float], str, Path, MatchResult],
                               duration: float = 1.0) -> bool:
        """
        异步长按操作

        Args:
            target: 长按目标
            duration: 长按时间（秒）

        Returns:
            是否长按成功
        """
        try:
            position = None

            # 获取位置
            if isinstance(target, tuple) and len(target) == 2:
                position = target
            elif isinstance(target, (str, Path)):
                result = await self.wait_element_async(str(target))
                if hasattr(result, 'position') and result.position:
                    position = result.position
                elif isinstance(result, MatchResult) and result.success:
                    position = result.position

            if position:
                x, y = int(position[0]), int(position[1])
                success = await self.run_in_threadpool(self.adb.long_press, x, y, duration)
                return success
            else:
                logger.error(f"无法确定长按位置: {target}")
                return False

        except Exception as e:
            logger.error(f"长按操作失败: {e}")
            return False

    async def key_event_async(self, keycode: int) -> bool:
        """
        异步按键事件

        Args:
            keycode: 按键代码

        Returns:
            是否执行成功
        """
        try:
            success = await self.run_in_threadpool(self.adb.key_event, keycode)
            return success
        except Exception as e:
            logger.error(f"按键事件失败: {e}")
            return False

    async def wake_up_async(self) -> bool:
        """异步唤醒屏幕"""
        try:
            success = await self.run_in_threadpool(self.adb.wake_up)
            return success
        except Exception as e:
            logger.error(f"唤醒屏幕失败: {e}")
            return False

    async def get_foreground_app_async(self) -> Optional[str]:
        """异步获取前台应用包名"""
        try:
            app = await self.run_in_threadpool(self.adb.get_foreground_app)
            return app
        except Exception as e:
            logger.error(f"获取前台应用失败: {e}")
            return None

    # 以下方法需要额外实现，因为adb_utils和EasyOCRTool中可能没有直接对应功能

    async def find_and_click_in_region_async(self,
                                             primary_target: Union[str, Path],
                                             secondary_target: Union[str, Path],
                                             primary_threshold: float = 0.8,
                                             secondary_threshold: float = 0.7,
                                             search_region_expand: int = 50,
                                             wait_config: WaitConfig = None,
                                             max_retries: int = 3) -> bool:
        """
        在第一个图片匹配区域内查找并点击第二个图片

        Args:
            primary_target: 主目标图片
            secondary_target: 次级目标图片
            primary_threshold: 主目标匹配阈值
            secondary_threshold: 次级目标匹配阈值
            search_region_expand: 搜索区域扩展像素
            wait_config: 等待配置
            max_retries: 最大重试次数

        Returns:
            bool: 是否成功找到并点击
        """
        if wait_config is None:
            wait_config = WaitConfig(timeout=10.0, interval=0.5)

        for attempt in range(max_retries):
            logger.info(f"第 {attempt + 1} 次尝试查找主目标: {primary_target}")

            try:
                # 1. 等待并查找主目标图片
                primary_result = await self.wait_element_async(
                    primary_target,
                    config=wait_config,
                    strategy=MatchStrategy.IMAGE
                )

                if not primary_result:
                    logger.warning(f"第 {attempt + 1} 次尝试未找到主目标")
                    continue

                # 获取主目标位置
                primary_pos_result = await self.exists_image_async(str(primary_target), primary_threshold)
                if not primary_pos_result.success:
                    continue

                logger.info(f"找到主目标，位置: {primary_pos_result.position}")

                # 2. 创建搜索区域
                primary_x, primary_y = primary_pos_result.position
                screen_width, screen_height = await self.get_screen_size_async()

                search_region = (
                    max(0, int(primary_x) - search_region_expand),
                    max(0, int(primary_y) - search_region_expand),
                    min(screen_width, int(primary_x) + search_region_expand),
                    min(screen_height, int(primary_y) + search_region_expand)
                )

                # 3. 在指定区域内搜索次级目标
                secondary_found = await self._find_image_in_region_async(
                    str(secondary_target),
                    search_region,
                    secondary_threshold
                )

                if secondary_found and secondary_found.success:
                    logger.info(f"在区域内找到次级目标，准备点击: {secondary_found.position}")
                    # 4. 点击次级目标
                    success = await self.touch_async(secondary_found)
                    if success:
                        logger.info("次级目标点击成功")
                        return True
                    else:
                        logger.warning("次级目标点击失败")
                else:
                    logger.warning("在区域内未找到次级目标")

            except Exception as e:
                logger.error(f"第 {attempt + 1} 次尝试出错: {e}")

            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)

        logger.error(f"经过 {max_retries} 次尝试仍未完成操作")
        return False

    async def _find_image_in_region_async(self,
                                          image_path: str,
                                          search_region: Tuple[int, int, int, int],
                                          threshold: float = 0.7) -> Optional[MatchResult]:
        """
        在指定区域内查找图片

        Args:
            image_path: 图片路径
            search_region: 搜索区域 (x1, y1, x2, y2)
            threshold: 匹配阈值

        Returns:
            匹配结果
        """
        try:
            # 先截图
            screenshot_path = await self.take_screenshot_async("temp_region_screenshot.png")

            # 使用区域特征匹配
            result, _, _ = await self.run_in_threadpool(
                self.ocr.feature_match_in_region,
                image_path,
                str(screenshot_path),
                search_region,
                match_ratio=threshold,
                min_matches=5
            )

            if result and result.get('match_success', False):
                return MatchResult(
                    success=True,
                    position=result['center'],
                    confidence=result['confidence'],
                    bbox=result['bbox']
                )
            else:
                return MatchResult(success=False, confidence=0.0)

        except Exception as e:
            logger.error(f"区域图片查找失败: {e}")
            return MatchResult(success=False, error=str(e))

    async def extract_text_from_region_async(self,
                                             region: Tuple[int, int, int, int],
                                             confidence_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        从指定区域提取文字

        Args:
            region: 区域坐标 (x1, y1, x2, y2)
            confidence_threshold: 置信度阈值

        Returns:
            提取的文字结果列表
        """
        try:
            # 截图
            screenshot_path = await self.take_screenshot_async("temp_extract_screenshot.png")

            # 区域文字识别
            results = await self.run_in_threadpool(
                self.ocr.recognize_text_in_region,
                str(screenshot_path),
                region,
                confidence_threshold
            )

            return results

        except Exception as e:
            logger.error(f"区域文字提取失败: {e}")
            return []

    async def find_number_in_region_async(self,
                                          region: Tuple[int, int, int, int],
                                          number_pattern: str = r'\d+',
                                          min_length: int = 1,
                                          max_length: int = 20,
                                          confidence_threshold: float = 0.5) -> Optional[str]:
        """
        在指定区域查找数字

        Args:
            region: 区域坐标
            number_pattern: 数字正则表达式
            min_length: 最小长度
            max_length: 最大长度
            confidence_threshold: 置信度阈值

        Returns:
            找到的数字字符串
        """
        try:
            # 截图
            screenshot_path = await self.take_screenshot_async("temp_number_screenshot.png")

            # 提取数字
            numbers = await self.run_in_threadpool(
                self.ocr.extract_numbers,
                str(screenshot_path),
                region,
                number_pattern,
                min_length,
                max_length,
                confidence_threshold
            )

            if numbers:
                return numbers[0].get('number')
            return None

        except Exception as e:
            logger.error(f"数字查找失败: {e}")
            return None

    async def batch_wait_elements_async(self,
                                        elements: List[Dict],
                                        timeout_per_element: float = 10.0) -> Dict:
        """
        批量等待多个元素（并行）

        Args:
            elements: 元素列表，每个元素是包含target和config的字典
            timeout_per_element: 每个元素的超时时间

        Returns:
            结果字典
        """
        tasks = []
        for elem in elements:
            target = elem.get('target')
            config = elem.get('config', WaitConfig(timeout=timeout_per_element))
            strategy = elem.get('strategy', MatchStrategy.BOTH)
            task = self.wait_element_async(target, config, strategy)
            tasks.append(task)

        # 并行执行所有等待任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict = {}
        for i, (elem, result) in enumerate(zip(elements, results)):
            elem_name = elem.get('name', f'element_{i}')
            if isinstance(result, Exception):
                result_dict[elem_name] = {'success': False, 'error': str(result)}
            else:
                result_dict[elem_name] = {'success': result, 'found': result}

        return result_dict

    async def perform_swipe_until_found_async(self,
                                              swipe_action: Callable,
                                              check_condition: Callable,
                                              max_attempts: int = 10,
                                              wait_between: float = 1.0) -> bool:
        """
        执行滑动直到满足条件

        Args:
            swipe_action: 滑动动作函数
            check_condition: 检查条件函数
            max_attempts: 最大尝试次数
            wait_between: 滑动间隔

        Returns:
            是否找到
        """
        for attempt in range(max_attempts):
            logger.info(f"第 {attempt + 1} 次尝试")

            # 执行滑动
            if asyncio.iscoroutinefunction(swipe_action):
                await swipe_action()
            else:
                await self.run_in_threadpool(swipe_action)

            # 等待动画
            await asyncio.sleep(wait_between)

            # 检查条件
            if asyncio.iscoroutinefunction(check_condition):
                found = await check_condition()
            else:
                found = await self.run_in_threadpool(check_condition)

            if found:
                logger.info(f"第 {attempt + 1} 次尝试后找到目标")
                return True

        logger.warning(f"尝试 {max_attempts} 次后未找到目标")
        return False

    async def retry_operation_async(self,
                                    operation: Callable,
                                    max_retries: int = 3,
                                    retry_delay: float = 1.0,
                                    operation_args: tuple = None,
                                    operation_kwargs: dict = None) -> Any:
        """
        重试操作

        Args:
            operation: 操作函数
            max_retries: 最大重试次数
            retry_delay: 重试延迟
            operation_args: 操作参数
            operation_kwargs: 操作关键字参数
        """
        if operation_args is None:
            operation_args = ()
        if operation_kwargs is None:
            operation_kwargs = {}

        last_exception = None
        for attempt in range(max_retries):
            try:
                if asyncio.iscoroutinefunction(operation):
                    return await operation(*operation_args, **operation_kwargs)
                else:
                    return await self.run_in_threadpool(operation, *operation_args, **operation_kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"操作第 {attempt + 1} 次失败: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        raise last_exception or Exception("操作失败")

    async def wait_and_perform_async(self,
                                     target: Any,
                                     action: Callable,
                                     wait_config: WaitConfig = None,
                                     action_args: tuple = None,
                                     action_kwargs: dict = None) -> bool:
        """
        等待元素后执行操作

        Args:
            target: 目标元素
            action: 要执行的操作函数
            wait_config: 等待配置
            action_args: 操作参数
            action_kwargs: 操作关键字参数
        """
        if wait_config is None:
            wait_config = WaitConfig()

        if action_args is None:
            action_args = ()
        if action_kwargs is None:
            action_kwargs = {}

        # 等待元素
        found = await self.wait_element_async(target, wait_config)
        if not found:
            return False

        # 执行操作
        try:
            if asyncio.iscoroutinefunction(action):
                await action(*action_args, **action_kwargs)
            else:
                await self.run_in_threadpool(action, *action_args, **action_kwargs)
            return True
        except Exception as e:
            logger.error(f"执行操作失败: {e}")
            return False

    async def find_element_by_swipe_with_callback_async(self,
                                                        target: Any,
                                                        on_each_swipe: Callable = None,
                                                        search_config: SearchConfig = None) -> Optional[MatchResult]:
        """
        带回调的滑动查找

        Args:
            target: 目标元素
            on_each_swipe: 每次滑动后的回调函数
            search_config: 搜索配置
        """
        if search_config is None:
            search_config = SearchConfig()

        for swipe_count in range(search_config.max_swipes):
            # 执行滑动
            await self.swipe_in_direction_async(
                search_config.direction,
                search_config.swipe_duration
            )

            await asyncio.sleep(search_config.wait_between_swipes)

            # 执行回调
            if on_each_swipe:
                if asyncio.iscoroutinefunction(on_each_swipe):
                    await on_each_swipe(swipe_count)
                else:
                    await self.run_in_threadpool(on_each_swipe, swipe_count)

            # 检查元素
            element = await self._find_element_in_current_screen_async(target, search_config)
            if element and element.success:
                logger.info(f"滑动 {swipe_count + 1} 次后找到元素")
                return element

        return None

    async def click_avatar_in_region_async(self, avatar_type="self", center_x=0, center_y=0, search_radius=50):
        """
        在坐标周围区域搜索并点击头像

        Args:
            avatar_type: 头像类型 ("self", "teammate", "role")
            center_x: 中心点X坐标
            center_y: 中心点Y坐标
            search_radius: 搜索半径
        """
        try:
            # 获取屏幕大小
            width, height = await self.get_screen_size_async()

            # 计算搜索区域
            search_region = (
                max(0, center_x - search_radius),
                max(0, center_y - search_radius),
                min(width, center_x + search_radius),
                min(height, center_y + search_radius)
            )

            logger.info(f"在区域 {search_region} 中搜索{avatar_type}头像")

            # 不同头像类型的模板图片
            avatar_templates = {
                "self": [
                    "avatars/self_avatar_small.png",
                    "avatars/self_avatar_frame.png",
                    "avatars/player_icon.png"
                ],
                "teammate": [
                    "avatars/teammate_avatar_small.png",
                    "avatars/team_icon.png"
                ],
                "role": [
                    "avatars/role_avatar.png",
                    "avatars/character_icon.png"
                ]
            }

            if avatar_type not in avatar_templates:
                return False

            # 尝试不同的头像模板
            for template in avatar_templates[avatar_type]:
                template_path = os.path.join(self.images_dir, template)
                if not os.path.exists(template_path):
                    continue

                avatar_result = await self._find_image_in_region_async(
                    template_path,
                    search_region,
                    threshold=0.7
                )

                if avatar_result and avatar_result.success:
                    x, y = avatar_result.position
                    logger.info(f"找到{avatar_type}头像，位置: ({x}, {y})")
                    return await self.touch_async(avatar_result)

            # 如果没找到，尝试扩大搜索范围
            if search_radius < 100:  # 最大搜索半径
                logger.info(f"扩大搜索范围到半径{search_radius + 30}")
                return await self.click_avatar_in_region_async(
                    avatar_type=avatar_type,
                    center_x=center_x,
                    center_y=center_y,
                    search_radius=search_radius + 30
                )

            logger.warning(f"在半径{search_radius}内未找到{avatar_type}头像")
            return False

        except Exception as e:
            logger.error(f"区域搜索失败: {e}")
            return False

    async def find_number_area(self, target_image: str,
                               number_region_offset: Tuple[int, int, int, int] = (-320, -10, -20, 30)):
        """
        识别固定部分并提取数字

        Args:
            target_image: 目标图片路径
            number_region_offset: 数字区域偏移量 (x1_offset, y1_offset, x2_offset, y2_offset)

        Returns:
            提取的数字文本
        """
        try:
            # 1. 识别目标图片
            target_result = await self.wait_element_async(target_image)
            if not target_result:
                return None

            # 获取目标位置
            pos_result = await self.exists_image_async(target_image)
            if not pos_result.success:
                return None

            target_x, target_y = pos_result.position

            # 2. 计算数字区域
            x1 = target_x + number_region_offset[0]
            y1 = target_y + number_region_offset[1]
            x2 = target_x + number_region_offset[2]
            y2 = target_y + number_region_offset[3]

            number_region = (max(0, x1), max(0, y1), x2, y2)

            # 3. 提取数字
            number = await self.find_number_in_region_async(number_region)
            return number

        except Exception as e:
            logger.error(f"数字区域识别失败: {e}")
            return None

    async def find_text_area(self, target_image: str,
                             text_region_offset: Tuple[int, int, int, int] = (-60, -60, 300, 0)):
        """
        识别固定部分并提取文本

        Args:
            target_image: 目标图片路径
            text_region_offset: 文本区域偏移量

        Returns:
            提取的文本
        """
        try:
            # 1. 识别目标图片
            target_result = await self.wait_element_async(target_image)
            if not target_result:
                return None

            # 获取目标位置
            pos_result = await self.exists_image_async(target_image)
            if not pos_result.success:
                return None

            target_x, target_y = pos_result.position

            # 2. 计算文本区域
            x1 = target_x + text_region_offset[0]
            y1 = target_y + text_region_offset[1]
            x2 = target_x + text_region_offset[2]
            y2 = target_y + text_region_offset[3]

            text_region = (max(0, x1), max(0, y1), x2, y2)

            # 3. 提取文本
            texts = await self.extract_text_from_region_async(text_region)
            if texts:
                return texts[0].get('text')
            return None

        except Exception as e:
            logger.error(f"文本区域识别失败: {e}")
            return None

    async def run_async_task(self, coro, timeout: float = None) -> Any:
        """
        运行异步任务并跟踪

        Args:
            coro: 协程
            timeout: 超时时间

        Returns:
            任务结果
        """
        task = asyncio.create_task(coro)
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

        try:
            if timeout:
                return await asyncio.wait_for(task, timeout)
            return await task
        except asyncio.TimeoutError:
            logger.error(f"任务超时: {coro}")
            task.cancel()
            raise
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            raise

    async def close(self):
        """关闭资源"""
        # 取消所有活跃任务
        for task in self.active_tasks:
            if not task.done():
                task.cancel()

        # 等待任务完成
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        # 关闭线程池
        if self.thread_pool:
            self.thread_pool.shutdown(wait=False)

        # 断开ADB连接
        try:
            await self.run_in_threadpool(self.adb.disconnect)
        except:
            pass

        logger.info("AsyncADBHelper已关闭")

        # 装饰器：将同步方法转换为异步

    def async_wrapper(func):
        """将同步方法包装为异步方法"""

        @wraps(func)
        async def async_func(*args, **kwargs):
            self = args[0] if args else None
            if self and hasattr(self, 'run_in_threadpool'):
                return await self.run_in_threadpool(func, *args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        return async_func

        # 增强的异步助手类

class EnhancedAsyncADBHelper(AsyncADBHelper):
    """增强的异步助手，提供更多便捷方法"""

    def __init__(self, emulator_port: int = 5555, ld_console_path: Optional[str] = None, max_workers: int = 5):
        super().__init__(emulator_port=emulator_port, ld_console_path=ld_console_path, max_workers=max_workers)

    async def smart_wait_and_click_async(self,
                                         target: Union[str, Path],
                                         wait_config: WaitConfig = None,
                                         click_delay: float = 0.5) -> bool:
        """
        智能等待并点击（自动选择最佳匹配策略）

        Args:
            target: 目标元素
            wait_config: 等待配置
            click_delay: 点击后延迟

        Returns:
            是否成功
        """
        if wait_config is None:
            wait_config = WaitConfig(timeout=15.0)

        # 自动判断目标类型
        target_str = str(target)
        if target_str.endswith(('.png', '.jpg', '.jpeg')):
            strategy = MatchStrategy.IMAGE
        else:
            strategy = MatchStrategy.OCR

        # 等待元素
        found = await self.wait_element_async(target, wait_config, strategy)
        if not found:
            return False

        # 点击
        success = await self.touch_async(target)
        if success and click_delay > 0:
            await asyncio.sleep(click_delay)

        return success

    async def multi_strategy_find_async(self,
                                        target: str,
                                        strategies: List[MatchStrategy] = None,
                                        wait_config: WaitConfig = None) -> Optional[MatchResult]:
        """
        多策略查找元素

        Args:
            target: 目标元素
            strategies: 策略列表
            wait_config: 等待配置

        Returns:
            匹配结果
        """
        if strategies is None:
            strategies = [MatchStrategy.IMAGE, MatchStrategy.OCR]

        if wait_config is None:
            wait_config = WaitConfig(timeout=10.0)

        for strategy in strategies:
            logger.info(f"尝试使用策略: {strategy}")
            result = await self.wait_element_async(target, wait_config, strategy)

            if result:
                # 获取详细的匹配结果
                if strategy == MatchStrategy.IMAGE:
                    return await self.exists_image_async(target)
                else:
                    return await self.exists_text_async(target)

        return None

    async def conditional_swipe_async(self,
                                      condition_check: Callable,
                                      swipe_action: Callable,
                                      max_swipes: int = 5,
                                      check_interval: float = 1.0) -> bool:
        """
        条件滑动：满足条件时停止滑动

        Args:
            condition_check: 条件检查函数
            swipe_action: 滑动动作函数
            max_swipes: 最大滑动次数
            check_interval: 检查间隔

        Returns:
            是否满足条件
        """
        for i in range(max_swipes):
            # 检查条件
            if asyncio.iscoroutinefunction(condition_check):
                condition_met = await condition_check()
            else:
                condition_met = await self.run_in_threadpool(condition_check)

            if condition_met:
                logger.info(f"滑动 {i} 次后条件满足")
                return True

            # 执行滑动
            if asyncio.iscoroutinefunction(swipe_action):
                await swipe_action()
            else:
                await self.run_in_threadpool(swipe_action)

            await asyncio.sleep(check_interval)

        logger.warning(f"滑动 {max_swipes} 次后条件仍未满足")
        return False

# 使用示例
async def main():
    """使用示例"""
    # 创建助手实例
    helper = EnhancedAsyncADBHelper(emulator_port=5555)

    try:
        # 连接设备
        await helper.connect_device_async()

        # 示例1: 智能等待并点击
        await helper.smart_wait_and_click_async("login_button.png")

        # 示例2: 多策略查找
        result = await helper.multi_strategy_find_async(
            "用户名称",
            strategies=[MatchStrategy.OCR, MatchStrategy.IMAGE]
        )

        if result and result.success:
            await helper.touch_async(result)

        # 示例3: 条件滑动
        async def check_login_success():
            return await helper.exists_text_async("登录成功", confidence_threshold=0.7)

        success = await helper.conditional_swipe_async(
            condition_check=check_login_success,
            swipe_action=lambda: helper.swipe_in_direction_async(SearchDirection.DOWN),
            max_swipes=3
        )

        # 示例4: 批量操作
        elements_to_wait = [
            {'target': 'button1.png', 'name': '按钮1', 'strategy': MatchStrategy.IMAGE},
            {'target': '文本内容', 'name': '文本1', 'strategy': MatchStrategy.OCR},
            {'target': 'icon.png', 'name': '图标', 'strategy': MatchStrategy.IMAGE}
        ]

        results = await helper.batch_wait_elements_async(elements_to_wait)
        print(f"批量等待结果: {results}")

    except Exception as e:
        logger.error(f"主程序出错: {e}")
        await helper.take_screenshot_async("error_final.png")
    finally:
        await helper.close()

if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())