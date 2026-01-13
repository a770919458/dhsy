# MouseController.py
import ctypes
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Set, Tuple
import win32con
import win32gui
import win32api
import threading
from typing import Set

import win32process




class MouseController:
    def __init__(self):
        self.lock = threading.Lock()
        self._user32 = ctypes.windll.user32

    def _is_valid_window(self, hwnd: int) -> bool:
        """
        检查窗口句柄是否有效

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 窗口是否有效
        """
        try:
            if not hwnd or hwnd == 0:
                return False

            # 检查窗口是否存在
            if not win32gui.IsWindow(hwnd):
                return False

            # 检查窗口是否可见
            if not win32gui.IsWindowVisible(hwnd):
                return False

            # 检查窗口是否启用
            if not win32gui.IsWindowEnabled(hwnd):
                return False

            # 获取窗口标题，排除无效窗口
            title = win32gui.GetWindowText(hwnd)
            if not title and not self._is_system_window(hwnd):
                return False

            return True

        except Exception as e:
            print(f"检查窗口有效性时出错: {e}")
            return False

    def _is_system_window(self, hwnd: int) -> bool:
        """
        检查是否是系统窗口

        Args:
            hwnd: 窗口句柄

        Returns:
            bool: 是否是系统窗口
        """
        try:
            # 获取窗口类名
            class_name = win32gui.GetClassName(hwnd)

            # 常见的系统窗口类名
            system_classes = {
                'Progman', 'Shell_TrayWnd', 'Button', 'Static', 'Edit',
                'ListBox', 'ComboBox', 'ScrollBar', 'MDIClient'
            }

            return class_name in system_classes

        except:
            return False

    def _get_window_info(self, hwnd: int) -> dict:
        """
        获取窗口详细信息

        Args:
            hwnd: 窗口句柄

        Returns:
            dict: 窗口信息
        """
        try:
            info = {
                'hwnd': hwnd,
                'title': win32gui.GetWindowText(hwnd),
                'class_name': win32gui.GetClassName(hwnd),
                'visible': win32gui.IsWindowVisible(hwnd),
                'enabled': win32gui.IsWindowEnabled(hwnd),
                'rect': win32gui.GetWindowRect(hwnd)
            }

            # 获取进程信息
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                info['pid'] = pid
                info['process_name'] = self._get_process_name(pid)
            except:
                info['pid'] = None
                info['process_name'] = 'Unknown'

            return info
        except Exception as e:
            print(f"获取窗口信息失败: {e}")
            return {'hwnd': hwnd, 'error': str(e)}

    def _get_process_name(self, pid: int) -> str:
        """
        获取进程名称

        Args:
            pid: 进程ID

        Returns:
            str: 进程名称
        """
        try:
            if not pid:
                return "Unknown"

            process = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, pid)
            if process:
                name = win32process.GetModuleFileNameEx(process, 0)
                win32api.CloseHandle(process)
                return name
            return "Unknown"
        except:
            return "Unknown"

    def validate_window_for_mouse_control(self, hwnd: int) -> tuple:
        """
        验证窗口是否适合进行鼠标控制

        Args:
            hwnd: 窗口句柄

        Returns:
            tuple: (是否有效, 错误信息)
        """
        if not self._is_valid_window(hwnd):
            return False, "无效的窗口句柄"

        # 检查窗口是否支持鼠标控制
        try:
            info = self._get_window_info(hwnd)

            # 排除系统窗口
            if self._is_system_window(hwnd):
                return False, "系统窗口不支持鼠标控制"

            # 检查窗口大小
            rect = info['rect']
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width < 10 or height < 10:
                return False, "窗口尺寸过小"

            return True, "窗口验证通过"

        except Exception as e:
            return False, f"窗口验证失败: {str(e)}"

