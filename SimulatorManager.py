import win32api
import win32con
import win32gui
import win32process
import psutil
import re
from typing import List, Dict, Optional, Tuple, Any

from util.adb_utils import LeidianADB


class SimulatorManager:
    """
    窗口管理器类
    用于获取窗口句柄和相关信息
    """

    # 相关的窗口类名和进程名
    LD_PLAYER_CLASS_NAMES = [
        "LDPlayerMainFrame",
        "Qt5154QWindowIcon",
        "Qt5154QWindowOwnDCIcon"
    ]

    LD_PROCESS_NAMES = [
        "LdVBoxHeadless.exe",
        "dnplayer.exe",
        "LdVBoxSVC.exe"
    ]

    def __init__(self):
        self.simulators = []

    def find_all_simulators(self, title: str = "大话西游手游") -> List[Dict]:
        """
        查找所有窗口

        Returns:
            List[Dict]: 窗口信息列表，每个元素包含句柄、标题、PID等信息
        """
        self.simulators = []

        # 方法1：通过窗口类名查找
        self._find_by_class_name()

        # 方法2：通过进程名查找
        # self._find_by_process_name()

        # 方法3：通过窗口标题模糊匹配
        # self._find_by_title_pattern(title)

        # 去重处理
        self._remove_duplicates()

        return self.simulators

    def _find_by_class_name(self):
        """通过窗口类名查找"""
        for class_name in self.LD_PLAYER_CLASS_NAMES:
            try:
                win32gui.EnumWindows(self._enum_windows_by_class, class_name)
            except Exception as e:
                print(f"通过类名 {class_name} 查找时出错: {e}")

    def _find_by_process_name(self):
        """通过进程名查找"""
        try:
            for process in psutil.process_iter(['pid', 'name']):
                if process.info['name'] and any(proc_name.lower() in process.info['name'].lower()
                                                for proc_name in self.LD_PROCESS_NAMES):
                    self._get_window_by_pid(process.info['pid'])
        except Exception as e:
            print(f"通过进程名查找时出错: {e}")

    def _find_by_title_pattern(self, title: str):
        """通过窗口标题模式查找"""
        try:
            win32gui.EnumWindows(self._enum_windows_by_title, title)
        except Exception as e:
            print(f"通过标题模式查找时出错: {e}")

    def _enum_windows_by_class(self, hwnd: int, class_name: str) -> bool:
        """枚举窗口回调函数 - 按类名"""
        if win32gui.IsWindowVisible(hwnd):
            current_class = win32gui.GetClassName(hwnd)
            if class_name == current_class:
                self._add_simulator_info(hwnd)
        return True

    def _enum_windows_by_title(self, hwnd: int, pattern: str) -> bool:
        """枚举窗口回调函数 - 按标题模式"""
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and re.match(pattern, title):
                self._add_simulator_info(hwnd)
        return True

    def _get_window_by_pid(self, pid: int):
        """通过PID获取窗口句柄"""

        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)

        for hwnd in hwnds:
            self._add_simulator_info(hwnd)

    def _find_window_by_handle(self, hwnd: int) -> Dict[str, Any]:
        """
        通过句柄查找窗口信息

        Args:
            hwnd: 窗口句柄

        Returns:
            窗口信息字典
        """
        try:
            if not win32gui.IsWindow(hwnd):
                return None

            # 获取窗口信息
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            is_visible = win32gui.IsWindowVisible(hwnd)
            is_minimized = win32gui.IsIconic(hwnd)

            # 检查窗口是否激活（通过获取前景窗口）
            foreground_hwnd = win32gui.GetForegroundWindow()
            is_active = (foreground_hwnd == hwnd)

            return {
                'hwnd': hwnd,
                'title': title,
                'class_name': class_name,
                'left': left,
                'top': top,
                'right': right,
                'bottom': bottom,
                'width': right - left,
                'height': bottom - top,
                'is_visible': is_visible,
                'is_minimized': is_minimized,
                'is_active': is_active
            }
        except Exception as e:
            print(f"获取窗口信息失败: {e}")
            return None

    def _add_simulator_info(self, hwnd: int):
        """添加窗口信息到列表"""
        try:
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if "电脑桌面版" in title:
                return
            # 获取进程ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # 获取窗口位置和大小
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top

            # 获取进程信息
            process_name = "Unknown"
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except:
                pass

            adb = LeidianADB()
            rect = win32gui.GetWindowRect(hwnd)

            # 获取进程信息
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            simulator_info = {
                'handle': hwnd,
                'hwnd': hwnd,
                'port': adb.get_port_from_handle(title),
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
                'position': (left, top),
                'size': (width, height),
                'is_visible': win32gui.IsWindowVisible(hwnd),
                'is_enabled': win32gui.IsWindowEnabled(hwnd)
            }

            # 检查是否已存在相同的句柄
            if not any(sim['handle'] == hwnd for sim in self.simulators):
                self.simulators.append(simulator_info)

        except Exception as e:
            print(f"添加窗口信息时出错 (句柄: {hwnd}): {e}")

    def _remove_duplicates(self):
        """去除重复的窗口信息"""
        unique_simulators = []
        seen_handles = set()

        for sim in self.simulators:
            if sim['handle'] not in seen_handles:
                seen_handles.add(sim['handle'])
                unique_simulators.append(sim)

        self.simulators = unique_simulators

    def get_simulator_by_index(self, index: int) -> Optional[Dict]:
        """通过索引获取窗口信息"""
        if 0 <= index < len(self.simulators):
            return self.simulators[index]
        return None

    def get_simulator_by_handle(self, handle: int) -> Optional[Dict]:
        """通过句柄获取窗口信息"""
        for sim in self.simulators:
            if sim['handle'] == handle:
                return sim
        return None

    def get_simulator_by_title(self, title_pattern: str) -> List[Dict]:
        """通过标题模式获取窗口信息"""
        import re
        result = []
        for sim in self.simulators:
            if re.search(title_pattern, sim['title'], re.IGNORECASE):
                result.append(sim)
        return result

    def get_simulator_count(self) -> int:
        """获取找到的窗口数量"""
        return len(self.simulators)

    def print_simulator_info(self):
        """打印所有窗口信息（用于调试）"""
        print(f"\n找到 {len(self.simulators)} 个:")
        print("-" * 80)

        for i, sim in enumerate(self.simulators):
            print(f"窗口 #{i + 1}:")
            print(f"  句柄: {sim['handle']}")
            print(f"  标题: {sim['title']}")
            print(f"  类名: {sim['class_name']}")
            print(f"  进程ID: {sim['pid']}")
            print(f"  进程名: {sim['process_name']}")
            print(f"  位置: {sim['position']}")
            print(f"  大小: {sim['size']}")
            print(f"  可见: {sim['is_visible']}")
            print(f"  可用: {sim['is_enabled']}")
            print("-" * 40)

    def bring_to_front(self, handle: int) -> bool:
        """将指定句柄的窗口置于前台"""
        try:
            # 先恢复窗口（如果最小化）
            if win32gui.IsIconic(handle):
                win32gui.ShowWindow(handle, 9)  # SW_RESTORE

            # 将窗口置顶
            win32gui.SetForegroundWindow(handle)
            return True
        except Exception as e:
            print(f"置顶窗口失败 (句柄: {handle}): {e}")
            return False

    def get_window_screenshot_info(self, handle: int) -> Optional[Dict]:
        """获取窗口截图所需的信息"""
        try:
            # 获取窗口位置和大小
            left, top, right, bottom = win32gui.GetWindowRect(handle)

            # 获取客户区位置和大小
            client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(handle)
            client_left, client_top = win32gui.ClientToScreen(handle, (client_left, client_top))

            return {
                'window_rect': (left, top, right, bottom),
                'client_rect': (client_left, client_top, client_right, client_bottom),
                'window_width': right - left,
                'window_height': bottom - top,
                'client_width': client_right,
                'client_height': client_bottom
            }
        except Exception as e:
            print(f"获取窗口截图信息失败 (句柄: {handle}): {e}")
            return None

    def resize_window(self, handle: int, width: int, height: int,
                      x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """
        调整窗口尺寸和位置

        Args:
            handle: 窗口句柄
            width: 新的宽度
            height: 新的高度
            x: 新的X坐标（可选，不设置则保持当前位置）
            y: 新的Y坐标（可选，不设置则保持当前位置）

        Returns:
            bool: 操作是否成功
        """
        try:
            # 检查窗口句柄是否有效
            if not win32gui.IsWindow(handle):
                print(f"无效的窗口句柄: {handle}")
                return False

            # 获取当前窗口位置和样式
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            current_width = right - left
            current_height = bottom - top

            # 如果未指定位置，则使用当前位置
            if x is None:
                x = left
            if y is None:
                y = top

            print(f"调整窗口尺寸: {current_width}x{current_height} -> {width}x{height}")
            print(f"窗口位置: ({x}, {y})")

            # 设置窗口位置和大小
            # SWP_NOZORDER: 保持当前Z顺序
            # SWP_SHOWWINDOW: 显示窗口
            result = win32gui.SetWindowPos(handle, win32con.HWND_TOP, x, y, width, height,
                                           win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW)

            if result:
                print("窗口尺寸调整成功!")
                return True
            else:
                print("窗口尺寸调整失败!")
                return False

        except Exception as e:
            print(f"调整窗口尺寸失败 (句柄: {handle}): {e}")
            return False

    def resize_window_to_standard(self, handle: int, standard: str = "1024x768") -> bool:
        """
        调整窗口到标准尺寸

        Args:
            handle: 窗口句柄
            standard: 标准尺寸，格式为 "宽度x高度"，如 "800x600", "1024x768", "1280x720"

        Returns:
            bool: 操作是否成功
        """
        try:
            # 解析标准尺寸
            if "x" in standard:
                width, height = map(int, standard.split("x"))
            else:
                # 默认使用1024x768
                width, height = 1024, 768

            return self.resize_window(handle, width, height)

        except Exception as e:
            print(f"调整到标准尺寸失败 (句柄: {handle}): {e}")
            return False

    def center_window(self, handle: int, width: Optional[int] = None, height: Optional[int] = None) -> bool:
        """
        将窗口居中显示

        Args:
            handle: 窗口句柄
            width: 窗口宽度（可选，不设置则使用当前宽度）
            height: 窗口高度（可选，不设置则使用当前高度）

        Returns:
            bool: 操作是否成功
        """
        try:
            # 获取屏幕尺寸
            screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

            # 获取当前窗口尺寸
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            current_width = right - left
            current_height = bottom - top

            # 使用指定尺寸或当前尺寸
            target_width = width if width is not None else current_width
            target_height = height if height is not None else current_height

            # 计算居中位置
            x = (screen_width - target_width) // 2
            y = (screen_height - target_height) // 2

            print(f"将窗口居中显示: {target_width}x{target_height} 位置: ({x}, {y})")

            return self.resize_window(handle, target_width, target_height, x, y)

        except Exception as e:
            print(f"窗口居中失败 (句柄: {handle}): {e}")
            return False


# 使用示例
if __name__ == "__main__":
    # 创建窗口管理器实例
    manager = SimulatorManager()

    # 查找所有
    simulators = manager.find_all_simulators()

    # 打印找到的窗口信息
    manager.print_simulator_info()

    # 示例：操作第一个找到的窗口
    if simulators:
        first_sim = simulators[0]
        print(f"\n操作第一个窗口: {first_sim['title']}")

        # 置顶窗口
        success = manager.bring_to_front(first_sim['handle'])
        if success:
            print("窗口置顶成功!")

        # 获取截图信息
        screenshot_info = manager.get_window_screenshot_info(first_sim['handle'])
        if screenshot_info:
            print(f"窗口尺寸: {screenshot_info['window_width']}x{screenshot_info['window_height']}")