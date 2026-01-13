import win32api
import win32gui
import win32con
import win32process
import psutil
import pyautogui
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.controls import uiawrapper, win32_controls
from typing import List, Dict, Optional, Tuple
import time
import logging
import os

logger = logging.getLogger(__name__)


class WindowManager:
    """
    Windows窗口管理器
    使用pywinauto替换airtest的所有功能 - 修复后台点击问题
    """

    def __init__(self):
        self.app = None
        self.connected_window = None
        self.background_mode = True  # 默认启用后台模式
        self.last_mouse_pos = None
        self.process_id = None

    def list_all_windows(self) -> List[Dict]:
        """
        列出所有可见窗口（使用win32gui实现）
        """
        windows = []

        def enum_callback(hwnd, window_list):
            """枚举窗口的回调函数"""
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if title:  # 只处理有标题的窗口
                        class_name = win32gui.GetClassName(hwnd)
                        rect = win32gui.GetWindowRect(hwnd)

                        # 获取进程信息
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        process_name = "Unknown"
                        try:
                            process = psutil.Process(pid)
                            process_name = process.name()
                        except:
                            pass

                        window_info = {
                            'hwnd': hwnd,
                            'title': title,
                            'class_name': class_name,
                            'rect': rect,
                            'left': rect[0],
                            'top': rect[1],
                            'right': rect[2],
                            'bottom': rect[3],
                            'width': rect[2] - rect[0],
                            'height': rect[3] - rect[1],
                            'pid': pid,
                            'process_name': process_name,
                            'is_visible': win32gui.IsWindowVisible(hwnd),
                            'is_minimized': win32gui.IsIconic(hwnd)
                        }
                        window_list.append(window_info)

                except Exception as e:
                    pass
            return True

        # 枚举所有窗口
        win32gui.EnumWindows(enum_callback, windows)
        return windows

    def find_window(self, keyword: str, exact_match: bool = False) -> List[Dict]:
        """
        根据关键词查找窗口

        Args:
            keyword: 搜索关键词
            exact_match: 是否精确匹配
        """
        all_windows = self.list_all_windows()
        matched_windows = []

        for window in all_windows:
            title = window['title']
            class_name = window['class_name']
            process_name = window['process_name']

            if exact_match:
                if (keyword == title or
                        keyword == class_name or
                        keyword == process_name):
                    matched_windows.append(window)
            else:
                keyword_lower = keyword.lower()
                if (keyword_lower in title.lower() or
                        keyword_lower in class_name.lower() or
                        keyword_lower in process_name.lower()):
                    matched_windows.append(window)

        return matched_windows

    def connect_to_window(self, window_hwnd: int) -> bool:
        """
        使用pywinauto连接到指定窗口句柄
        """
        try:
            # 先断开现有连接
            if self.app:
                try:
                    self.app.kill()
                except:
                    pass
                self.app = None

            # 获取进程ID
            _, pid = win32process.GetWindowThreadProcessId(window_hwnd)
            self.process_id = pid

            # 连接到现有进程
            self.app = Application(backend="uia").connect(process=pid)

            # 获取窗口对象
            window = self.app.window(handle=window_hwnd)

            # 确保窗口可用
            if not window.exists():
                raise Exception("窗口不存在或不可用")

            # 更新连接窗口信息
            self.connected_window = self.get_window_info(window_hwnd)
            self.connected_window['pywinauto_window'] = window

            print(f"成功连接到窗口: {self.connected_window['title']} (PID: {pid})")
            return True

        except Exception as e:
            print(f"连接窗口失败: {e}")
            logger.error(f"连接窗口失败: {e}", exc_info=True)

            # 清理资源
            self.app = None
            self.connected_window = None
            self.process_id = None

            return False

    def connect_by_title(self, title_pattern: str) -> bool:
        """
        通过标题模式连接窗口
        """
        windows = self.find_window(title_pattern)
        if windows:
            # 优先选择可见且非最小化的窗口
            for window in windows:
                if window['is_visible'] and not window['is_minimized']:
                    return self.connect_to_window(window['hwnd'])
            # 如果没有合适的，连接第一个
            return self.connect_to_window(windows[0]['hwnd'])
        return False

    def connect_by_process(self, process_name: str) -> bool:
        """
        通过进程名连接应用程序
        """
        try:
            # 连接到进程
            self.app = Application(backend="uia").connect(path=process_name)

            # 获取主窗口
            window = self.app.top_window()
            hwnd = window.handle

            self.connected_window = self.get_window_info(hwnd)
            self.connected_window['pywinauto_window'] = window
            self.process_id = self.connected_window['pid']

            print(f"成功连接到进程: {process_name}")
            return True

        except Exception as e:
            print(f"连接进程失败: {e}")
            return False

    def get_window_info(self, hwnd: int) -> Optional[Dict]:
        """
        获取指定窗口句柄的详细信息
        """
        try:
            if not win32gui.IsWindow(hwnd):
                return None

            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            rect = win32gui.GetWindowRect(hwnd)

            # 获取进程信息
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = "Unknown"
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except:
                pass

            return {
                'hwnd': hwnd,
                'title': title,
                'class_name': class_name,
                'rect': rect,
                'left': rect[0],
                'top': rect[1],
                'right': rect[2],
                'bottom': rect[3],
                'width': rect[2] - rect[0],
                'height': rect[3] - rect[1],
                'pid': pid,
                'process_name': process_name,
                'is_visible': win32gui.IsWindowVisible(hwnd),
                'is_minimized': win32gui.IsIconic(hwnd)
            }
        except Exception as e:
            print(f"获取窗口信息失败: {e}")
            return None

    def get_window_title(self, hwnd: int) -> str:
        """获取窗口标题"""
        return win32gui.GetWindowText(hwnd)

    def get_window_class_name(self, hwnd: int) -> str:
        """获取窗口类名"""
        return win32gui.GetClassName(hwnd)

    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取窗口矩形区域 (left, top, right, bottom)"""
        return win32gui.GetWindowRect(hwnd)

    def bring_to_front(self, hwnd: int) -> bool:
        """
        将窗口置于前台
        """
        try:
            if not win32gui.IsWindow(hwnd):
                return False

            # 恢复窗口（如果最小化）
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)

            # 将窗口设为最顶层
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            time.sleep(0.1)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

            return True

        except Exception as e:
            print(f"置顶窗口失败: {e}")
            return False

    def resize_window(self, hwnd: int, width: int, height: int,
                      x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """
        调整窗口尺寸
        """
        try:
            if not win32gui.IsWindow(hwnd):
                return False

            # 获取当前位置
            left, top, _, _ = win32gui.GetWindowRect(hwnd)

            # 使用指定位置或当前位置
            if x is None:
                x = left
            if y is None:
                y = top

            # 调整窗口大小
            win32gui.MoveWindow(hwnd, x, y, width, height, True)
            return True

        except Exception as e:
            print(f"调整窗口大小失败: {e}")
            return False

    def get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """
        获取客户区矩形
        """
        try:
            return win32gui.GetClientRect(hwnd)
        except:
            return win32gui.GetWindowRect(hwnd)

    def enable_background_mode(self, enable: bool = True):
        """启用后台模式，不移动真实光标"""
        self.background_mode = enable
        if enable:
            # 保存当前鼠标位置，操作后恢复
            self.last_mouse_pos = pyautogui.position()

    def _safe_background_click(self, x: int, y: int, duration: float = 0.1) -> bool:
        """
        安全的后台点击实现 - 修复卡住问题
        使用win32api直接发送鼠标消息，避免pywinauto的click_input卡住
        """
        try:
            if not self.connected_window:
                return False

            hwnd = self.connected_window['hwnd']

            # 保存原始鼠标位置
            original_pos = pyautogui.position()

            # 方法1: 使用win32api发送鼠标消息（最稳定的后台点击）
            # 将坐标转换为窗口客户区坐标
            client_point = win32api.MAKELONG(x, y)

            # 发送鼠标移动消息
            win32api.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, client_point)
            time.sleep(0.05)

            # 发送鼠标左键按下消息
            win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, client_point)
            time.sleep(duration)

            # 发送鼠标左键释放消息
            win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, client_point)

            # 恢复鼠标位置
            if self.last_mouse_pos:
                pyautogui.moveTo(self.last_mouse_pos[0], self.last_mouse_pos[1])
            else:
                pyautogui.moveTo(original_pos[0], original_pos[1])

            print(f"安全后台点击位置: ({x}, {y})")
            return True

        except Exception as e:
            print(f"安全后台点击失败: {e}")
            # 尝试恢复鼠标位置
            try:
                pyautogui.moveTo(original_pos[0], original_pos[1])
            except:
                pass
            return False

    def _pywinauto_click(self, x: int, y: int, duration: float = 0.1) -> bool:
        """使用pywinauto实现点击 - 修复版本"""
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return False

            window = self.connected_window['pywinauto_window']

            if self.background_mode:
                # 后台模式：使用安全的后台点击方法
                return self._safe_background_click(x, y, duration)
            else:
                # 前台模式：使用pywinauto的点击方法
                # 先确保窗口可见
                if not window.is_visible():
                    self.bring_to_front(self.connected_window['hwnd'])

                # 使用更安全的点击方式
                window.set_focus()
                time.sleep(0.1)

                # 使用click_input但设置较短的超时
                try:
                    window.click_input(coords=(x, y), absolute=False)
                    print(f"pywinauto前台点击位置: ({x}, {y})")
                    return True
                except Exception as e:
                    print(f"pywinauto点击失败，使用备用方法: {e}")
                    # 备用方法：使用win32api
                    return self._safe_background_click(x, y, duration)

        except Exception as e:
            print(f"点击失败: {e}")
            return False

    def _pywinauto_input_text(self, text_: str) -> bool:
        """使用pywinauto输入文本"""
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return False

            window = self.connected_window['pywinauto_window']

            # 先设置焦点
            window.set_focus()
            time.sleep(0.1)

            # 输入文本
            window.type_keys(text_)
            print(f"输入文本: {text_}")
            return True

        except Exception as e:
            print(f"输入文本失败: {e}")
            return False

    def _pywinauto_key_event(self, key: str) -> bool:
        """使用pywinauto发送按键事件"""
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return False

            window = self.connected_window['pywinauto_window']

            # 设置焦点
            window.set_focus()
            time.sleep(0.1)

            # 发送按键
            window.type_keys(key)
            print(f"按键: {key}")
            return True

        except Exception as e:
            print(f"按键失败: {e}")
            return False

    # ============ pywinauto 操作方法 ============

    def crop_image_by_region(self, image_path: str, region: Tuple[int, int, int, int],
                             save_path: str = None) -> Optional[str]:
        """
        根据指定区域坐标截取图片的一部分

        Args:
            image_path: 原始图片路径
            region: 截取区域 (left, top, right, bottom)
            save_path: 保存路径，如果为None则生成临时文件

        Returns:
            截取后的图片路径，失败返回None
        """
        try:
            from PIL import Image

            # 打开原始图片
            with Image.open(image_path) as img:
                # 提取区域坐标
                left, top, right, bottom = region

                # 确保坐标有效
                width, height = img.size
                left = max(0, min(left, width - 1))
                top = max(0, min(top, height - 1))
                right = max(left + 1, min(right, width))
                bottom = max(top + 1, min(bottom, height))

                # 截取图片
                cropped_img = img.crop((left, top, right, bottom))

                # 保存图片
                if save_path:
                    cropped_img.save(save_path)
                else:
                    # 生成临时文件名
                    import tempfile
                    _, temp_file = tempfile.mkstemp(suffix='.png')
                    cropped_img.save(temp_file)
                    save_path = temp_file

                print(f"图片截取成功: {save_path}")
                return save_path

        except Exception as e:
            print(f"图片截取失败: {e}")
            return None

    def screenshot(self, filename: str = None) -> Optional[str]:
        """
        截取窗口截图 - 使用pyautogui实现
        """
        if not self.connected_window:
            print("未连接到任何窗口")
            return None

        try:
            # 获取窗口区域
            rect = self.connected_window['rect']
            left, top, right, bottom = rect

            width = right - left
            height = bottom - top

            # 确保尺寸有效
            if width <= 0 or height <= 0:
                print("窗口尺寸无效")
                return None

            # 截取区域
            screenshot = pyautogui.screenshot(region=(left, top, width, height))

            if filename:
                screenshot.save(filename)
                print(f"截图已保存: {filename}")
                return filename
            else:
                # 生成临时文件名
                temp_file = f"temp_screenshot_{int(time.time())}.png"
                screenshot.save(temp_file)
                return temp_file

        except Exception as e:
            print(f"截图失败: {e}")
            return None

    def click(self, x: int, y: int, duration: float = 0.1) -> bool:
        """
        在窗口内点击指定位置 - 使用修复后的方法
        """
        return self._safe_background_click(x, y, duration)

    def click_element(self, element_name: str, exact_match: bool = True) -> bool:
        """
        点击指定元素 - 修复版本
        """
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return False

            window = self.connected_window['pywinauto_window']

            # 查找元素
            try:
                if exact_match:
                    element = window.child_window(title=element_name, found_index=0)
                else:
                    element = window.child_window(title_re=element_name, found_index=0)
            except ElementNotFoundError:
                print(f"未找到元素: {element_name}")
                return False

            if element.exists():
                try:
                    # 获取元素位置并点击
                    rect = element.rectangle()
                    center_x = (rect.left + rect.right) // 2
                    center_y = (rect.top + rect.bottom) // 2

                    # 转换为窗口相对坐标
                    win_rect = self.connected_window['rect']
                    relative_x = center_x - win_rect[0]
                    relative_y = center_y - win_rect[1]

                    return self.click(relative_x, relative_y)

                except Exception as e:
                    print(f"点击元素坐标失败: {e}")
                    return False
            else:
                print(f"元素不存在: {element_name}")
                return False

        except Exception as e:
            print(f"点击元素失败: {e}")
            return False

    def input_text(self, text_: str) -> bool:
        """
        输入文本 - 使用pywinauto
        """
        return self._pywinauto_input_text(text_)

    def key_event(self, key: str) -> bool:
        """
        发送按键事件 - 使用pywinauto
        """
        return self._pywinauto_key_event(key)

    def get_element_info(self, element_name: str) -> Optional[Dict]:
        """
        获取元素信息
        """
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return None

            window = self.connected_window['pywinauto_window']

            # 尝试查找元素
            try:
                element = window.child_window(title=element_name, found_index=0)
                if element.exists():
                    rect = element.rectangle()
                    return {
                        'name': element_name,
                        'class_name': element.element_info.class_name,
                        'rect': (rect.left, rect.top, rect.right, rect.bottom),
                        'is_visible': element.is_visible(),
                        'is_enabled': element.is_enabled()
                    }
            except ElementNotFoundError:
                pass

            return None

        except Exception as e:
            print(f"获取元素信息失败: {e}")
            return None

    def wait_element_exists(self, element_name: str, timeout: int = 10) -> bool:
        """
        等待元素出现
        """
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return False

            window = self.connected_window['pywinauto_window']

            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    element = window.child_window(title=element_name, found_index=0)
                    if element.exists() and element.is_visible():
                        return True
                except ElementNotFoundError:
                    pass
                time.sleep(0.5)

            return False

        except Exception as e:
            print(f"等待元素失败: {e}")
            return False

    def list_all_elements(self) -> List[Dict]:
        """
        列出所有子元素
        """
        try:
            if not self.connected_window or 'pywinauto_window' not in self.connected_window:
                return []

            window = self.connected_window['pywinauto_window']
            elements = []

            # 获取所有子元素
            try:
                children = window.descendants()
                for child in children:
                    try:
                        info = child.element_info
                        rect = child.rectangle()
                        elements.append({
                            'name': info.name,
                            'class_name': info.class_name,
                            'rect': (rect.left, rect.top, rect.right, rect.bottom),
                            'is_visible': child.is_visible(),
                            'is_enabled': child.is_enabled()
                        })
                    except:
                        continue
            except Exception as e:
                print(f"获取子元素列表时出错: {e}")

            return elements

        except Exception as e:
            print(f"获取元素列表失败: {e}")
            return []

    def swipe(self, start_pos: tuple, end_pos: tuple, duration: float = 1.0) -> bool:
        """
        滑动操作 - 使用安全的后台实现
        """
        try:
            if not self.connected_window:
                return False

            hwnd = self.connected_window['hwnd']
            start_x, start_y = start_pos
            end_x, end_y = end_pos

            # 使用win32api模拟滑动
            start_point = win32api.MAKELONG(start_x, start_y)
            end_point = win32api.MAKELONG(end_x, end_y)

            # 发送鼠标按下消息
            win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, start_point)
            time.sleep(0.1)

            # 发送鼠标移动消息（模拟滑动）
            steps = max(3, int(duration * 5))
            for i in range(1, steps + 1):
                progress = i / steps
                current_x = int(start_x + (end_x - start_x) * progress)
                current_y = int(start_y + (end_y - start_y) * progress)
                current_point = win32api.MAKELONG(current_x, current_y)
                win32api.SendMessage(hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, current_point)
                time.sleep(duration / steps)

            # 发送鼠标释放消息
            win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, end_point)

            print(f"后台滑动: 从 {start_pos} 到 {end_pos}")
            return True

        except Exception as e:
            print(f"滑动失败: {e}")
            return False

    def disconnect(self):
        """
        断开连接
        """
        try:
            if self.app:
                self.app.kill()
        except:
            pass

        self.app = None
        self.connected_window = None
        self.process_id = None
        print("已断开窗口连接")

    def print_window_info(self, window_info: Dict = None):
        """
        打印窗口信息
        """
        if window_info is None and self.connected_window:
            window_info = self.connected_window
        elif window_info is None:
            print("没有窗口信息")
            return

        print(f"\n=== 窗口信息 ===")
        print(f"标题: {window_info['title']}")
        print(f"句柄: {window_info['hwnd']}")
        print(f"类名: {window_info['class_name']}")
        print(f"位置: ({window_info['left']}, {window_info['top']})")
        print(f"尺寸: {window_info['width']}x{window_info['height']}")
        print(f"进程ID: {window_info['pid']}")
        print(f"进程名: {window_info['process_name']}")
        print(f"可见: {window_info['is_visible']}")
        print(f"最小化: {window_info['is_minimized']}")


# 测试函数
def test_background_click():
    """测试后台点击功能"""
    manager = WindowManager()

    # 查找记事本窗口
    notepad_windows = manager.find_window("记事本")
    if notepad_windows:
        window = notepad_windows[0]
        print(f"找到记事本窗口: {window['title']}")

        if manager.connect_to_window(window['hwnd']):
            manager.enable_background_mode(True)

            # 测试点击
            print("测试后台点击...")
            success = manager.click(100, 100)
            print(f"点击结果: {'成功' if success else '失败'}")

            # 测试输入文本
            print("测试输入文本...")
            success = manager.input_text("Hello World!")
            print(f"输入结果: {'成功' if success else '失败'}")

            manager.disconnect()
    else:
        print("未找到记事本窗口")


if __name__ == "__main__":
    # 运行测试
    test_background_click()