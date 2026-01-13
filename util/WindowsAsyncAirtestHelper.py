# utils/WindowsAsyncAirtestHelper.py
import asyncio
import concurrent.futures
import sys
import os
import time
from typing import Optional, Tuple, List, Callable, Any, Dict, Union
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum

from util.EasyOCRTool import EasyOCRTool
from util.WindowManager import WindowManager

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
    POCO = "poco"  # POCO元素
    BOTH = "both"  # 两者都尝试
    PRIORITY_IMAGE = "priority_image"  # 优先图片
    PRIORITY_POCO = "priority_poco"  # 优先POCO


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


class Template:
    """模拟Airtest的Template类"""

    def __init__(self, filename, threshold=0.8, region=None):
        self.filename = filename
        self.threshold = threshold
        self.region = region


class WindowsAsyncAirtestHelper:
    """
    Windows窗口异步助手类
    基于WindowManager实现，不依赖Airtest
    """

    def __init__(self, window_keyword: str = None, window_handle: int = None, max_workers: int = 5,
                 use_thread_pool: bool = True, background_mode: bool = True):
        """
        初始化Windows窗口助手

        Args:
            window_keyword: 窗口关键词（标题、类名、进程名）
            window_handle: 窗口句柄（如果已知）
            max_workers: 线程池最大工作线程数
            use_thread_pool: 是否使用线程池处理阻塞操作
            background_mode: 是否启用后台模式
        """
        self.window_keyword = window_keyword
        self.window_handle = window_handle
        self.window_manager = WindowManager()
        self.device = None
        self.is_connected = False
        self.window_info = None
        self.background_mode = background_mode

        # 异步相关
        self.max_workers = max_workers
        self.use_thread_pool = use_thread_pool
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="windows_async_"
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
        # 获取脚本所在目录 (dhhj/scripts/)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # 获取项目根目录 (dhhj/)
        self.project_root = os.path.dirname(self.script_dir)
        # 图片目录 (dhhj/images/)
        self.images_dir = os.path.join(self.project_root, "images")

        # 设置工作目录到项目根目录
        os.chdir(self.project_root)
        # 添加项目根目录到Python路径
        sys.path.insert(0, self.project_root)

        logger.info(f"项目根目录: {self.project_root}")
        logger.info(f"脚本目录: {self.script_dir}")
        logger.info(f"图片目录: {self.images_dir}")
        logger.info(f"工作目录: {os.getcwd()}")

    def _init_event_loop(self):
        """初始化事件循环"""
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    async def find_and_connect_window_async(self,
                                            window_keyword: str = None,
                                            exact_match: bool = False) -> bool:
        """
        异步查找并连接窗口
        """
        if window_keyword is None:
            window_keyword = self.window_keyword

        if not window_keyword:
            raise ValueError("必须提供窗口关键词")

        try:
            # 在线程池中执行窗口查找
            windows = await self.run_in_threadpool(
                self.window_manager.find_window,
                window_keyword,
                exact_match
            )

            if not windows:
                logger.error(f"未找到匹配的窗口: {window_keyword}")
                return False

            # 优先选择可见且非最小化的窗口
            target_window = None
            for window in windows:
                if window['is_visible'] and not window['is_minimized']:
                    target_window = window
                    break

            # 如果没有合适的，选择第一个
            if not target_window:
                target_window = windows[0]

            self.window_handle = target_window['hwnd']
            self.window_info = target_window

            logger.info(f"找到窗口: {target_window['title']} (PID: {target_window['pid']})")

            # 连接到窗口
            return await self.connect_to_window_async(self.window_handle)

        except Exception as e:
            logger.error(f"查找并连接窗口失败: {e}", exc_info=True)
            return False

    async def connect_to_window_async(self, window_handle: int) -> bool:
        """
        异步连接到指定窗口句柄
        """
        try:
            # 确保窗口存在且可见
            window_info = await self.run_in_threadpool(
                self.window_manager.get_window_info,
                window_handle
            )

            if not window_info:
                logger.error(f"窗口不存在或不可用: {window_handle}")
                return False

            if not window_info['is_visible']:
                logger.warning(f"窗口不可见，尝试激活: {window_info['title']}")
                # 尝试激活窗口
                success = await self.run_in_threadpool(
                    self.window_manager.bring_to_front,
                    window_handle
                )
                if not success:
                    logger.warning(f"激活窗口失败: {window_info['title']}")

            # 在线程池中执行连接操作
            success = await self.run_in_threadpool(
                self.window_manager.connect_to_window,
                window_handle
            )

            if success:
                self.device = self.window_manager
                self.is_connected = True
                self.window_info = self.window_manager.connected_window

                # 启用后台模式
                if hasattr(self, 'background_mode') and self.background_mode:
                    await self.run_in_threadpool(
                        self.window_manager.enable_background_mode,
                        True
                    )

                logger.info(f"成功连接到窗口: {self.window_info['title']}")
                return True
            else:
                logger.error(f"连接窗口失败: {window_handle}")
                return False

        except Exception as e:
            logger.error(f"连接窗口异常: {e}", exc_info=True)
            return False

    async def connect_by_title_async(self, title_pattern: str) -> bool:
        """
        异步通过标题模式连接窗口
        """
        try:
            success = await self.run_in_threadpool(
                self.window_manager.connect_by_title,
                title_pattern
            )

            if success:
                self.device = self.window_manager
                self.is_connected = True
                self.window_info = self.window_manager.connected_window
                logger.info(f"通过标题连接成功: {self.window_info['title']}")
                return True
            return False

        except Exception as e:
            logger.error(f"通过标题连接失败: {e}")
            return False

    async def bring_window_to_front_async(self, window_handle: int = None) -> bool:
        """
        异步将窗口置于前台
        """
        if window_handle is None:
            if self.window_handle:
                window_handle = self.window_handle
            else:
                logger.error("未指定窗口句柄")
                return False

        try:
            success = await self.run_in_threadpool(
                self.window_manager.bring_to_front,
                window_handle
            )

            if success:
                logger.info(f"窗口已置于前台: {window_handle}")
                return True
            return False

        except Exception as e:
            logger.error(f"置顶窗口失败: {e}")
            return False

    async def resize_window_async(self,
                                  width: int,
                                  height: int,
                                  x: Optional[int] = None,
                                  y: Optional[int] = None,
                                  window_handle: int = None) -> bool:
        """
        异步调整窗口尺寸
        """
        if window_handle is None:
            if self.window_handle:
                window_handle = self.window_handle
            else:
                logger.error("未指定窗口句柄")
                return False

        try:
            success = await self.run_in_threadpool(
                self.window_manager.resize_window,
                window_handle, width, height, x, y
            )

            if success:
                logger.info(f"窗口尺寸已调整: {width}x{height}")
                return True
            return False

        except Exception as e:
            logger.error(f"调整窗口尺寸失败: {e}")
            return False

    async def list_all_windows_async(self) -> List[Dict]:
        """
        异步列出所有可见窗口
        """
        try:
            windows = await self.run_in_threadpool(
                self.window_manager.list_all_windows
            )
            logger.info(f"找到 {len(windows)} 个窗口")
            return windows
        except Exception as e:
            logger.error(f"列出窗口失败: {e}")
            return []

    async def find_windows_async(self,
                                 keyword: str,
                                 exact_match: bool = False) -> List[Dict]:
        """
        异步查找窗口
        """
        try:
            windows = await self.run_in_threadpool(
                self.window_manager.find_window,
                keyword, exact_match
            )
            logger.info(f"找到 {len(windows)} 个匹配窗口")
            return windows
        except Exception as e:
            logger.error(f"查找窗口失败: {e}")
            return []

    async def run_in_threadpool(self, func: Callable, *args, **kwargs) -> Any:
        """
        在线程池中运行阻塞函数
        """
        if not self.use_thread_pool:
            return func(*args, **kwargs)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.thread_pool,
            lambda: func(*args, **kwargs)
        )

    # ============ 图片识别和操作功能 ============

    async def wait_element_async(self,
                                 target: Union[str, Path, Template],
                                 config: WaitConfig = None,
                                 strategy: MatchStrategy = MatchStrategy.IMAGE) -> bool:
        """
        异步等待元素出现（基于图片识别）
        """
        if config is None:
            config = WaitConfig()

        start_time = time.time()
        result = False

        while time.time() - start_time < config.timeout:
            try:
                if isinstance(target, (str, Path, Template)):
                    result = await self.exists_image_async(target)
                    if result:
                        break

                await asyncio.sleep(config.interval)

            except Exception as e:
                logger.debug(f"等待元素时出错: {e}")

        if not result and config.raise_error:
            if config.screenshot_on_fail:
                await self.take_screenshot_async("wait_element_failed.png")
            raise TimeoutError(f"等待元素超时: {target}")

        return result

    async def exists_image_async(self,
                                 image_path: Union[str, Path, Template],
                                 threshold: float = 0.8) -> Optional[Tuple[float, float]]:
        """
        异步检查图片是否存在（使用OpenCV模板匹配）
        """
        if not self.is_connected:
            logger.error("未连接到窗口")
            return None

        try:
            # 获取截图
            screenshot_path = await self.take_screenshot_async("temp_check.png")

            # 使用EasyOCRTool进行图片匹配
            result = await self.run_in_threadpool(
                self._image_match,
                str(image_path) if isinstance(image_path, (str, Path)) else image_path.filename,
                str(screenshot_path),
                threshold
            )

            # 删除临时截图
            try:
                os.remove(screenshot_path)
            except:
                pass

            return result

        except Exception as e:
            logger.error(f"检查图片存在时出错: {e}")
            return None

    def _image_match(self, template_path: str, screenshot_path: str, threshold: float) -> Optional[Tuple[float, float]]:
        """
        使用OpenCV进行模板匹配
        """
        try:
            import cv2
            import numpy as np

            # 读取图片
            template = cv2.imread(template_path, 0)
            screenshot = cv2.imread(screenshot_path, 0)

            if template is None or screenshot is None:
                return None

            # 模板匹配
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                # 返回中心坐标
                h, w = template.shape
                x = max_loc[0] + w // 2
                y = max_loc[1] + h // 2
                return (x, y)

            return None

        except Exception as e:
            logger.error(f"图片匹配失败: {e}")
            return None

    async def touch_async(self,
                          target: Union[Tuple[float, float], str, Path, Template],
                          wait_before: float = 0,
                          wait_after: float = 0) -> bool:
        """
        异步点击操作
        """
        if not self.is_connected:
            logger.error("未连接到窗口")
            return False

        if wait_before > 0:
            await asyncio.sleep(wait_before)

        try:
            if isinstance(target, tuple) and len(target) == 2:
                # 坐标点击
                success = await self.run_in_threadpool(
                    self.window_manager.click,
                    int(target[0]), int(target[1])
                )
                result = success

            elif isinstance(target, (str, Path, Template)):
                # 图片点击
                pos = await self.exists_image_async(target)
                if pos:
                    success = await self.run_in_threadpool(
                        self.window_manager.click,
                        int(pos[0]), int(pos[1])
                    )
                    result = success
                else:
                    result = False
            else:
                logger.error(f"不支持的点击目标类型: {type(target)}")
                result = False

        except Exception as e:
            logger.error(f"点击操作失败: {e}")
            result = False

        if wait_after > 0:
            await asyncio.sleep(wait_after)

        return result

    async def swipe_find_element_async(self,
                                       target: Union[str, Path, Template],
                                       search_config: SearchConfig = None,
                                       wait_config: WaitConfig = None) -> Optional[Any]:
        """
        异步滑动查找元素
        """
        if not self.is_connected:
            logger.error("未连接到窗口")
            return None

        if search_config is None:
            search_config = SearchConfig()

        if wait_config is None:
            wait_config = WaitConfig()

        logger.info(f"开始滑动查找元素: {target}")
        found = await self.wait_element_async(target, wait_config)
        if found:
            logger.info("直接找到元素，无需滑动")
            return await self._get_element_position_async(target)

        # 滑动查找
        screen_width, screen_height = await self.get_screen_size_async()
        logger.info(f"窗口尺寸: {screen_width}x{screen_height}")

        for swipe_count in range(search_config.max_swipes):
            logger.info(f"第 {swipe_count + 1} 次滑动，方向: {search_config.direction}")

            # 执行滑动
            if not await self.swipe_in_direction_async(search_config.direction,
                                                       search_config.swipe_duration,
                                                       search_config.swipe_steps):
                logger.warning(f"第 {swipe_count + 1} 次滑动失败")
                continue

            await asyncio.sleep(search_config.wait_between_swipes)

            # 查找元素
            element = await self._find_element_in_current_screen_async(target, search_config)
            if element is not None:
                logger.info(f"第 {swipe_count + 1} 次滑动后找到元素")
                return element

            # 截图记录
            if swipe_count % 3 == 0:
                await self.take_screenshot_async(f"swipe_find_{swipe_count}.png")

        logger.warning(f"滑动 {search_config.max_swipes} 次后未找到元素")
        if wait_config.screenshot_on_fail:
            await self.take_screenshot_async("swipe_find_failed.png")

        if wait_config.raise_error:
            raise TimeoutError(f"滑动查找元素超时: {target}")

        return None

    async def swipe_in_direction_async(self,
                                       direction: SearchDirection,
                                       duration: float = 0.5,
                                       steps: int = 1) -> bool:
        """
        异步向指定方向滑动
        """
        if not self.is_connected:
            return False

        screen_width, screen_height = await self.get_screen_size_async()

        # 计算滑动起点和终点
        if direction == SearchDirection.UP:
            start = (screen_width // 2, int(screen_height * 0.8))
            end = (screen_width // 2, int(screen_height * 0.2))
        elif direction == SearchDirection.DOWN:
            start = (screen_width // 2, int(screen_height * 0.2))
            end = (screen_width // 2, int(screen_height * 0.8))
        elif direction == SearchDirection.LEFT:
            start = (int(screen_width * 0.8), screen_height // 2)
            end = (int(screen_width * 0.2), screen_height // 2)
        elif direction == SearchDirection.RIGHT:
            start = (int(screen_width * 0.2), screen_height // 2)
            end = (int(screen_width * 0.8), screen_height // 2)
        else:
            raise ValueError(f"不支持的滑动方向: {direction}")

        try:
            success = await self.run_in_threadpool(
                self.window_manager.swipe,
                start, end, duration
            )
            logger.debug(f"滑动成功: {direction.value}")
            return success
        except Exception as e:
            logger.error(f"滑动失败: {e}")
            return False

    async def _find_element_in_current_screen_async(self,
                                                    target: Any,
                                                    search_config: SearchConfig) -> Optional[Any]:
        """在当前屏幕中查找元素"""
        if isinstance(target, (str, Path, Template)):
            return await self.exists_image_async(target, search_config.match_threshold)
        return None

    async def _get_element_position_async(self, target: Any) -> Optional[Any]:
        """获取元素位置"""
        if isinstance(target, (str, Path, Template)):
            return await self.exists_image_async(target)
        return None

    async def get_screen_size_async(self) -> Tuple[int, int]:
        """异步获取窗口尺寸"""
        if not self.is_connected:
            return 1920, 1080  # 默认值

        try:
            if self.window_info:
                return self.window_info['width'], self.window_info['height']
            else:
                # 获取客户区尺寸
                rect = await self.run_in_threadpool(
                    self.window_manager.get_client_rect,
                    self.window_handle
                )
                if rect:
                    return rect[2] - rect[0], rect[3] - rect[1]
                return 1920, 1080
        except Exception as e:
            logger.error(f"获取窗口尺寸失败: {e}")
            return 1920, 1080

    async def click_avatar_by_relative_position_async(self, avatar_type="self", offset_x=0, offset_y=0,
                                                      region_expand=20):
        """
        基于相对位置点击头像 - 针对古风游戏界面优化
        """
        try:
            # 获取当前屏幕分辨率
            width, height = await self.get_screen_size_async()

            # 以1280x720为基准分辨率计算
            base_width, base_height = 1280, 720

            if avatar_type == "self":
                # 自己头像位置 - 通常在右上角功能图标下方
                base_x, base_y = 1080, 100
            else:
                logger.error(f"不支持的avatar_type: {avatar_type}")
                return False

            # 计算实际坐标（按比例缩放）
            scale_x = width / base_width
            scale_y = height / base_height

            actual_x = int(base_x * scale_x) + offset_x
            actual_y = int(base_y * scale_y) + offset_y

            logger.info(
                f"计算坐标: ({actual_x}, {actual_y}), 分辨率: {width}x{height}, 缩放: {scale_x:.2f}x{scale_y:.2f}")

            # 添加安全边界检查
            if actual_x < 0 or actual_x > width or actual_y < 0 or actual_y > height:
                logger.warning(f"坐标超出屏幕范围: ({actual_x}, {actual_y})，自动调整")
                actual_x = max(0, min(actual_x, width - 1))
                actual_y = max(0, min(actual_y, height - 1))

            # 点击
            success = await self.run_in_threadpool(
                self.window_manager.click,
                actual_x, actual_y
            )

            if not success:
                logger.warning(f"直接点击失败")
            return success

        except Exception as e:
            logger.error(f"相对坐标点击失败: {e}")
            return False

    async def find_area_text(self, region: Tuple[int, int, int, int]):
        """识别固定区域的文字内容"""
        try:
            # 查找目标位置
            path = await self.take_screenshot_async()
            if not path:
                return None


            # 使用EasyOCRTool进行OCR识别
            result = await self.run_in_threadpool(
                EasyOCRTool.recognize_numeric_code,
                image_path=path,
                code_pattern=r'.+',
                min_length=2,
                max_length=10,
                confidence_threshold=0.6,
                region=region
            )

            # 清理临时文件
            try:
                os.remove(path)
            except:
                pass

            return result.get('code') if result else None

        except Exception as e:
            logger.error(f"区域文字识别失败: {e}")
            return None

    async def take_screenshot_async(self, filename: str = None) -> Path:
        """
        异步截图
        """
        if filename is None:
            timestamp = int(time.time() * 1000)
            filename = f"window_screenshot_{timestamp}.png"

        filepath = self.screenshots_dir / filename

        try:
            success = await self.run_in_threadpool(
                self.window_manager.screenshot,
                str(filepath)
            )
            if success:
                logger.info(f"窗口截图已保存: {filepath}")
            else:
                logger.warning(f"窗口截图保存失败: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"截图失败: {e}")
            filepath.touch()
            return filepath

    async def input_text_async(self,
                               text: str,
                               target: Union[Tuple[float, float], str, Path, Template] = None,
                               clear_first: bool = True) -> bool:
        """
        异步输入文本
        """
        if not self.is_connected:
            return False

        try:
            # 如果有目标，先点击目标
            if target:
                await self.touch_async(target)
                await asyncio.sleep(0.5)

            # 输入文本
            if clear_first:
                await self.run_in_threadpool(
                    self.window_manager.key_event,
                    "{VK_BACK}"
                )

            success = await self.run_in_threadpool(
                self.window_manager.input_text,
                text
            )
            return success

        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False

    async def key_event_async(self, key: str) -> bool:
        """
        异步发送按键事件
        """
        if not self.is_connected:
            return False

        try:
            success = await self.run_in_threadpool(
                self.window_manager.key_event,
                key
            )
            return success
        except Exception as e:
            logger.error(f"发送按键失败: {e}")
            return False

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

        # 断开窗口连接
        if self.window_manager:
            await self.run_in_threadpool(self.window_manager.disconnect)

        logger.info("WindowsAsyncAirtestHelper已关闭")


# 增强的Windows窗口助手
class EnhancedWindowsAsyncAirtestHelper(WindowsAsyncAirtestHelper):
    """增强的Windows窗口异步助手"""

    def __init__(self, window_keyword: str = None, window_handle: int = None, max_workers: int = 5,
                 use_thread_pool: bool = True, background_mode: bool = True):
        super().__init__(window_keyword, window_handle, max_workers, use_thread_pool, background_mode)

    async def robust_connect_async(self,
                                   keywords: List[str],
                                   max_retries: int = 3,
                                   retry_delay: float = 2.0) -> bool:
        """
        健壮的连接方法，包含重试机制
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"连接尝试 {attempt + 1}/{max_retries}")

                for keyword in keywords:
                    logger.info(f"尝试关键词: {keyword}")

                    # 查找窗口
                    windows = await self.find_windows_async(keyword, False)
                    if not windows:
                        continue

                    # 尝试连接每个匹配的窗口
                    for i, window in enumerate(windows):
                        logger.info(f"尝试连接窗口 {i + 1}: {window['title']}")

                        # 确保窗口可见
                        if not window['is_visible']:
                            await self.bring_window_to_front_async(window['hwnd'])
                            await asyncio.sleep(1.0)  # 等待窗口激活

                        # 连接窗口
                        if await self.connect_to_window_async(window['hwnd']):
                            logger.info(f"连接成功: {window['title']}")
                            return True

                # 如果所有关键词都失败，等待后重试
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(f"连接尝试 {attempt + 1} 失败: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        logger.error(f"所有 {max_retries} 次连接尝试都失败了")
        return False

    async def smart_connect_async(self,
                                  keywords: List[str],
                                  exact_match: bool = False) -> bool:
        """
        智能连接窗口，尝试多个关键词
        """
        for keyword in keywords:
            logger.info(f"尝试连接窗口: {keyword}")
            windows = await self.find_windows_async(keyword, exact_match)

            if windows:
                for window in windows:
                    logger.info(f"尝试连接: {window['title']}")
                    if await self.connect_to_window_async(window['hwnd']):
                        logger.info(f"成功连接: {window['title']}")
                        return True

        logger.error("所有关键词尝试连接失败")
        return False

    async def wait_and_click_async(self,
                                   target: Union[str, Path, Template],
                                   wait_config: WaitConfig = None,
                                   click_config: Dict = None) -> bool:
        """
        等待元素出现后点击
        """
        if wait_config is None:
            wait_config = WaitConfig()

        if click_config is None:
            click_config = {}

        # 等待元素
        found = await self.wait_element_async(target, wait_config)
        if not found:
            return False

        # 点击元素
        return await self.touch_async(target, **click_config)

    async def find_and_click_in_region_async(self,
                                             primary_target: Union[str, Path, Template],
                                             secondary_target: Union[str, Path, Template],
                                             primary_threshold: float = 0.8,
                                             secondary_threshold: float = 0.7,
                                             search_region_expand: int = 50,
                                             wait_config: WaitConfig = None,
                                             max_retries: int = 3) -> bool:
        """
        在第一个图片匹配区域内查找并点击第二个图片按钮
        """
        if wait_config is None:
            wait_config = WaitConfig(timeout=10.0, interval=0.5)

        for attempt in range(max_retries):
            logger.info(f"第 {attempt + 1} 次尝试查找主目标")

            try:
                # 查找主目标
                primary_pos = await self.wait_element_async(
                    primary_target,
                    config=wait_config
                )

                if not primary_pos:
                    continue

                logger.info(f"找到主目标，位置: {primary_pos}")

                # 在主目标区域搜索次级目标
                if isinstance(primary_pos, tuple) and len(primary_pos) == 2:
                    primary_x, primary_y = primary_pos
                    search_region = (
                        max(0, primary_x - search_region_expand),
                        max(0, primary_y - search_region_expand),
                        min((await self.get_screen_size_async())[0], primary_x + search_region_expand),
                        min((await self.get_screen_size_async())[1], primary_y + search_region_expand)
                    )
                else:
                    search_region = None

                # 搜索次级目标
                secondary_found = await self._find_image_in_region_async(
                    secondary_target,
                    search_region,
                    secondary_threshold
                )

                if secondary_found:
                    success = await self.touch_async(secondary_found)
                    if success:
                        return True

            except Exception as e:
                logger.error(f"第 {attempt + 1} 次尝试出错: {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)

        return False

    async def _find_image_in_region_async(self,
                                          image_target: Union[str, Path, Template],
                                          search_region: Tuple[int, int, int, int] = None,
                                          threshold: float = 0.7) -> Optional[Tuple[float, float]]:
        """在指定区域内查找图片"""
        try:
            # 获取截图
            screenshot_path = await self.take_screenshot_async("temp_region_check.png")

            # 如果有区域限制，先裁剪截图
            if search_region:
                import cv2
                screenshot = cv2.imread(str(screenshot_path))
                cropped = screenshot[search_region[1]:search_region[3], search_region[0]:search_region[2]]
                cv2.imwrite(str(screenshot_path), cropped)

            # 进行图片匹配
            result = await self.run_in_threadpool(
                self._image_match,
                str(image_target) if isinstance(image_target, (str, Path)) else image_target.filename,
                str(screenshot_path),
                threshold
            )

            # 调整坐标（如果是在区域内查找）
            if result and search_region:
                result = (result[0] + search_region[0], result[1] + search_region[1])

            # 清理临时文件
            try:
                os.remove(screenshot_path)
            except:
                pass

            return result

        except Exception as e:
            logger.error(f"区域图片查找失败: {e}")
            return None


# 使用示例
async def main():
    """使用示例"""
    # 创建助手实例
    helper = EnhancedWindowsAsyncAirtestHelper()

    try:
        # 1. 智能连接窗口
        keywords = ["大话西游", "梦幻西游", "游戏", "Player"]
        if await helper.smart_connect_async(keywords):
            print("窗口连接成功")

            # 2. 将窗口置于前台
            await helper.bring_window_to_front_async()

            # 3. 调整窗口大小
            await helper.resize_window_async(1280, 720)

            # 4. 等待并点击元素
            await helper.wait_and_click_async(
                target="start_button.png",
                wait_config=WaitConfig(timeout=10),
                click_config={"wait_before": 0.5, "wait_after": 1.0}
            )

            # 5. 输入文本
            await helper.input_text_async("Hello World!")

            # 6. 滑动查找
            element = await helper.swipe_find_element_async(
                target="target_element.png",
                search_config=SearchConfig(max_swipes=5)
            )

            if element:
                await helper.touch_async(element)

        else:
            print("窗口连接失败")

    except Exception as e:
        logger.error(f"主程序出错: {e}")
        await helper.take_screenshot_async("error.png")
    finally:
        await helper.close()


if __name__ == "__main__":
    asyncio.run(main())