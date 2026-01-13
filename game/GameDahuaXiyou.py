# game_dahua_xiyou.py
import traceback
from time import sleep

import cv2
import numpy as np
import time
from typing import Optional, Tuple, List, Dict
from util.EasyOCRTool import EasyOCRTool
from util.ADBAppManager import ADBAppManager
import uiautomator2 as u2


class DaHuaXiYouGame:
    def __init__(self, adb_manager: ADBAppManager, hwnd: int, ocr_lang: str = 'ch_sim'):
        """
        大话西游游戏操作类 - 使用统一的ADB管理器

        Args:
            adb_manager (ADBAppManager): ADB管理器实例
            hwnd (int): 窗口句柄
            ocr_lang (str): OCR识别语言
        """
        self.d = None
        self.game_activity = None
        self.app_name = "大话西游"
        self.adb_manager = adb_manager
        self.hwnd = hwnd
        self.ocr_tool = EasyOCRTool(lang=ocr_lang)
        self.game_package = "com.netease.dhxy"

        # 初始化屏幕信息
        self.screen_width = 0
        self.screen_height = 0
        self._initialize_screen_info()

    def _initialize_screen_info(self) -> bool:
        """
        初始化屏幕信息

        Returns:
            bool: 是否成功
        """
        try:
            resolution = self.adb_manager.get_screen_resolution(self.hwnd)
            if resolution:
                self.screen_width, self.screen_height = resolution
                print(f"[初始化] 句柄 {self.hwnd} 屏幕分辨率: {self.screen_width}x{self.screen_height}")
                return True
            else:
                print(f"[警告] 句柄 {self.hwnd} 无法获取分辨率，使用默认值")
                self.screen_width, self.screen_height = 1920, 1080
                return False
        except Exception as e:
            print(f"[错误] 句柄 {self.hwnd} 初始化屏幕信息失败: {e}")
            self.screen_width, self.screen_height = 1920, 1080
            return False

    def get_screenshot(self, save_debug: bool = False) -> Optional[np.ndarray]:
        """
        获取游戏截图

        Args:
            save_debug (bool): 是否保存调试截图

        Returns:
            Optional[np.ndarray]: 截图图像
        """
        try:
            img = self.d.screenshot()
            if save_debug:
                save_path = f"screenshot_hwnd_{self.hwnd}_{int(time.time())}.png"
                if save_path and img:
                    cv2.imwrite(save_path, img)
                    print(f"[成功] 句柄 {self.hwnd} 截图已保存: {save_path}")

            return img
        except Exception as e:
            print(f"[错误] 句柄 {self.hwnd} 获取截图失败: {e}")
            return None

    def find_text_position(self, target_text: str, confidence_threshold: float = 0.7,
                           region: Tuple[int, int, int, int] = None) -> Optional[Tuple[int, int, int, int]]:
        """
        在游戏界面中查找指定文本

        Args:
            target_text (str): 要查找的文本
            confidence_threshold (float): 置信度阈值
            region (Tuple[int, int, int, int]): 搜索区域

        Returns:
            Optional[Tuple[int, int, int, int]]: 文本坐标框
        """
        img = self.get_screenshot()
        if img is None:
            return None

        # 如果指定了区域，则裁剪图片
        if region is not None:
            x1, y1, x2, y2 = region
            img = img[y1:y2, x1:x2]

        # 使用OCR查找文本
        box = self.ocr_tool.find_text_position(img, target_text, threshold=confidence_threshold)

        if box:
            # 转换坐标回全屏
            if region is not None:
                x1, y1, _, _ = region
                box = (box[0] + x1, box[1] + y1, box[2] + x1, box[3] + y1)

            print(f"[成功] 句柄 {self.hwnd} 找到文本 '{target_text}': {box}")
            return box

        print(f"[失败] 句柄 {self.hwnd} 未找到文本 '{target_text}'")
        return None

    def find_text_center_point(self, target_text: str, confidence: float = 0.7,
                               region: Tuple[int, int, int, int] = None) -> Optional[Tuple[int, int]]:
        """
        查找文本中心点

        Args:
            target_text (str): 目标文本
            confidence (float): 置信度阈值
            region (Tuple[int, int, int, int]): 搜索区域

        Returns:
            Optional[Tuple[int, int]]: 中心点坐标
        """
        box = self.find_text_position(target_text, confidence, region)
        if box:
            x1, y1, x2, y2 = box
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            return (cx, cy)
        return None

    def click_at_position(self, box: Tuple[int, int, int, int]) -> bool:
        """
        点击坐标框中心点

        Args:
            box (Tuple[int, int, int, int]): 坐标框

        Returns:
            bool: 是否成功
        """
        try:
            x1, y1, x2, y2 = box
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            return self.click_at_point(cx, cy)
        except Exception as e:
            print(f"[错误] 句柄 {self.hwnd} 点击坐标框失败: {e}")
            return False

    def click_at_point(self, x: int, y: int) -> bool:
        """
        点击指定坐标

        Args:
            x (int): X坐标
            y (int): Y坐标

        Returns:
            bool: 是否成功
        """
        return self.adb_manager.click_position(self.hwnd, x, y)

    def find_and_click_text(self, target_text: str, confidence_threshold: float = 0.7) -> bool:
        """
        查找文本并点击

        Args:
            target_text (str): 目标文本
            confidence_threshold (float): 置信度阈值

        Returns:
            bool: 是否成功
        """
        box = self.find_text_position(target_text, confidence_threshold)
        if box is None:
            return False
        return self.click_at_position(box)

    def launch_game(self, window_info: dict):
        """
        启动大话西游游戏

        Returns:
            bool: 是否成功
        """
        try:
            url = f"127.0.0.1:{window_info['adb_port']}"
            self.d = u2.connect(url)  # 连接雷电实例
            out = self.d.shell(f'pidof {self.game_package}').output
            if out.strip():
                print("大话西游当前在运行")
            else:
                self.d.app_start(self.game_package)  # 启动包名
            # 登录游戏
            # self.login_game()

        except Exception as e:
            traceback.print_exc()  # 打印完整的 traceback 信息到控制台
            print(f"[错误] 句柄 {self.hwnd} 启动游戏失败: {e}")
            return False

    def login_game(self):
        """
        登录游戏
        :return:
        """
        sleep(2)
        box = self.find_text_center_point("开始游戏", 0.6)     #查找开始游戏按钮坐标
        print("正在查找登陆游戏按钮")
        if box:
            point_x, point_y = box
            x, y = np.int32(point_x), np.int32(point_y)
            self.d.click(int(x), int(y))
            return

        self.login_game()

    def main_tasks(self):
        """
        主线任务
        :return:
        """
        pass

    def get_user_info(self):
        """
        获取用户信息
        :return:
        """
        pass

    def close_game(self) -> bool:
        """
        关闭游戏

        Returns:
            bool: 是否成功
        """
        return self.adb_manager.stop_app(self.hwnd, self.game_package)

    def is_game_running(self) -> bool:
        """
        检查游戏是否运行

        Returns:
            bool: 是否运行
        """
        try:
            # 通过检查游戏进程来判断
            result = self.adb_manager._run_adb_command(self.hwnd, ['shell', 'pidof', self.game_package])
            return result is not None and result.strip() != ""
        except Exception as e:
            print(f"[错误] 句柄 {self.hwnd} 检查游戏运行状态失败: {e}")
            return False

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300) -> bool:
        """
        滑动操作

        Args:
            start_x, start_y: 起始坐标
            end_x, end_y: 结束坐标
            duration: 滑动时间

        Returns:
            bool: 是否成功
        """
        return self.adb_manager.swipe(self.hwnd, start_x, start_y, end_x, end_y, duration)

    def input_text(self, text: str) -> bool:
        """
        输入文本

        Args:
            text (str): 要输入的文本

        Returns:
            bool: 是否成功
        """
        return self.adb_manager.input_text(self.hwnd, text)

    def get_current_activity(self) -> Optional[str]:
        """
        获取当前活动

        Returns:
            Optional[str]: 活动名称
        """
        return self.adb_manager._get_current_activity_by_dumpsys(self.hwnd)


# 使用示例
if __name__ == "__main__":
    # 创建ADB管理器
    adb_manager = ADBAppManager()

    # 假设有一个窗口句柄（需要从MainWindow获取）
    test_hwnd = 123456  # 替换为实际句柄
    test_port = 5555  # 替换为实际端口

    # 连接到模拟器
    if adb_manager.connect_to_simulator(test_hwnd, test_port):
        # 创建游戏对象
        game = DaHuaXiYouGame(adb_manager, test_hwnd)

        # 测试功能
        resolution = game.adb_manager.get_screen_resolution(test_hwnd)
        print(f"分辨率: {resolution}")

        # 查找并点击文本
        game.find_and_click_text("大话西游")

        # 断开连接
        adb_manager.disconnect(test_hwnd)
