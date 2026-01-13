# adb_app_manager.py
import subprocess
import re
import time
import traceback
import winreg
from typing import List, Dict, Optional, Tuple, Union
import cv2
import numpy as np
import os

from uiautomator2 import Device


class ADBAppManager:
    def __init__(self, adb_path:str = None):
        """
        ADB应用管理工具类 - 统一管理所有ADB操作
        """
        self.adb_path = adb_path or self._find_adb_path()
        self.connected_ports = {}  # 端口到句柄的映射 {port: hwnd}
        self.hwnd_to_port = {}  # 句柄到端口的映射 {hwnd: port}
        self.adb_available = self._check_adb_availability()

    def get_port_from_handle(self, window_info: dict) -> Optional[int]:
        """
        根据窗口句柄获取雷电模拟器的ADB端口号

        Args:
            hwnd (int): 窗口句柄

        Returns:
            Optional[int]: 端口号，如果无法获取返回None
            :param window_info:
        """
        try:
            # 方法1: 从窗口标题提取端口号
            window_title = window_info['title']
            print(f"[端口检测] 窗口标题: {window_title}")

            # 雷电模拟器窗口标题格式通常为: "雷电模拟器" 或 "雷电模拟器-1" 或包含端口信息
            port = self._extract_port_from_title(window_title)
            if port is not None:
                print(f"[端口检测] 从标题提取端口: {port}")
                return port

            print(f"[端口检测] 无法确定句柄 { window_info['hwnd']} 的端口")
            return None

        except Exception as e:
            print(f"[端口检测] 获取端口失败: {e}")
            return None

    def _extract_port_from_title(self, title: str) -> Optional[int]:
        """
        从窗口标题提取端口号

        雷电模拟器窗口标题可能包含的模式:
        - "雷电模拟器" -> 端口 5555
        - "雷电模拟器-1" -> 端口 5555
        - "雷电模拟器-2" -> 端口 5557
        - "LDPlayer" -> 端口 5555
        - "LDPlayer1" -> 端口 5555
        - "LDPlayer2" -> 端口 5557
        - 包含"5555"等数字 -> 直接提取
        """
        if not title:
            return None

        title_lower = title.lower()

        # 直接查找端口号
        port_match = re.search(r'(\d{4,5})', title)
        if port_match:
            port = int(port_match.group(1))
            if 5555 <= port <= 5580:  # 雷电常用端口范围
                return port

        # 根据雷电模拟器编号映射端口
        if "雷电模拟器" in title or "ldplayer" in title_lower:
            # 查找模拟器编号
            index_match = re.search(r'[_-]?(\d+)', title)
            if index_match:
                index = int(index_match.group(1))
                # 雷电模拟器端口映射: 索引1->5555, 索引2->5557, 索引3->5559, 等等
                return 5555 + (index) * 2
            else:
                # 默认第一个模拟器
                return 5555

        return None

    def _get_ldplayer_installation_path(self) -> Optional[str]:
        """
        获取雷电模拟器的安装目录

        Returns:
            Optional[str]: 雷电模拟器安装路径，如果找不到返回None
        """
        try:

            # 检查进程获取路径（如果雷电模拟器正在运行）

            import psutil
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info['name'] and 'dnplayer' in proc.info['name'].lower():
                    exe_path = proc.info['exe']
                    if exe_path:
                        install_dir = os.path.dirname(os.path.dirname(exe_path))
                        if os.path.exists(install_dir):
                            return install_dir

            return None

        except Exception as e:
            print(f"[警告] 获取雷电模拟器安装路径失败: {e}")
            return None

    def _get_ldplayer_adb_path(self) -> Optional[str]:
        """
        获取雷电模拟器的ADB路径

        Returns:
            Optional[str]: 雷电模拟器ADB路径，如果找不到返回None
        """
        try:
            # 获取雷电模拟器安装目录
            ld_path = self._get_ldplayer_installation_path()
            if not ld_path:
                return None

            # 雷电模拟器可能的ADB路径
            possible_adb_paths = [
                os.path.join(ld_path, "adb.exe"),  # 主目录下的adb
                os.path.join(ld_path, "LDPlayer", "adb.exe"),  # 子目录
                os.path.join(ld_path, "vms", "adb.exe"),  # vms目录
            ]

            # 检查不同版本的雷电模拟器
            for version in ["9.0", "5.0"]:
                possible_adb_paths.append(os.path.join(ld_path, f"LDPlayer{version}", "adb.exe"))

            for adb_path in possible_adb_paths:
                if os.path.exists(adb_path):
                    print(f"[成功] 找到雷电模拟器ADB: {adb_path}")
                    return adb_path

            # 如果没找到具体的adb.exe，但找到了雷电目录，尝试查找其他可能的位置
            for root, dirs, files in os.walk(ld_path):
                if "adb.exe" in files:
                    full_path = os.path.join(root, "adb.exe")
                    print(f"[成功] 在子目录找到ADB: {full_path}")
                    return full_path

            return None

        except Exception as e:
            print(f"[警告] 获取雷电模拟器ADB路径失败: {e}")
            return None

    def _find_adb_path(self) -> str:
        """
        尝试自动查找ADB路径

        Returns:
            str: ADB路径，如果找不到返回 'adb'
        """
        # 首先尝试雷电模拟器的ADB
        ld_adb_path = self._get_ldplayer_adb_path()
        if ld_adb_path:

            return ld_adb_path

        print("[警告] 未找到ADB，将使用系统PATH中的adb命令")
        return 'adb'  # 默认返回'adb'，让系统在PATH中查找

    def _check_adb_availability(self) -> bool:
        """
        检查ADB是否可用

        Returns:
            bool: ADB是否可用
        """
        try:
            # 如果指定了具体路径但文件不存在
            if self.adb_path != 'adb' and not os.path.exists(self.adb_path):
                print(f"[错误] ADB文件不存在: {self.adb_path}")
                return False

            result = subprocess.run([self.adb_path, '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"[成功] ADB可用: {self.adb_path}")
                # 显示ADB版本信息
                version_line = result.stdout.split('\n')[0] if result.stdout else "未知版本"
                print(f"[信息] ADB版本: {version_line}")
                return True
            else:
                print(f"[警告] ADB检查失败: {result.stderr}")
                return False
        except FileNotFoundError:
            print(f"[错误] 找不到ADB可执行文件: {self.adb_path}")
            print("[提示] 请执行以下操作之一：")
            print("1. 安装Android SDK Platform-Tools并添加到PATH")
            print("2. 安装雷电模拟器或其他安卓模拟器")
            print("3. 手动指定adb_path参数")
            return False
        except subprocess.TimeoutExpired:
            print("[错误] ADB版本检查超时")
            return False
        except Exception as e:
            print(f"[错误] ADB检查异常: {e}")
            return False

    def _safe_run_command(self, command: List[str], timeout: int = 10) -> Optional[subprocess.CompletedProcess]:
        """
        安全执行命令 - 修复subprocess调用问题
        """
        try:
            print(f"[调试] 执行命令: {command}")

            # 确保所有路径参数被正确引用（特别是包含空格的路径）
            if self.adb_path != 'adb' and any(' ' in arg for arg in command):
                # 对于包含空格的路径，使用shell=True并正确转义
                shell_command = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in command])
                print(f"[调试] Shell命令: {shell_command}")
                result = subprocess.run(
                    shell_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',  # 明确指定UTF-8编码
                    errors='ignore',  # 忽略无法解码的字符
                    timeout=timeout
                )
            else:
                # 普通执行
                result = subprocess.run(
                    command,
                    shell=False,  # 明确设置为False
                    capture_output=True,
                    text=True,
                    encoding='utf-8',  # 明确指定UTF-8编码
                    errors='ignore',  # 忽略无法解码的字符
                    timeout=timeout
                )

            if result.returncode != 0:
                print(f"[命令错误] 返回码: {result.returncode}")
                if result.stderr:
                    print(f"[命令错误] 错误输出: {result.stderr}")

            return result

        except FileNotFoundError as e:
            traceback.print_exc()  # 打印完整的 traceback 信息到控制台
            print(f"[错误] 文件未找到: {e}")
            print(f"[错误] 命令: {command}")
            return None
        except subprocess.TimeoutExpired:
            traceback.print_exc()  # 打印完整的 traceback 信息到控制台
            print(f"[错误] 命令超时: {command}")
            return None
        except Exception as e:
            traceback.print_exc()  # 打印完整的 traceback 信息到控制台
            print(f"[错误] 命令执行异常: {e}")
            print(f"[错误] 命令: {command}")
            return None

    def connect_to_simulator(self, hwnd: int, adb_port: int = 5555) -> bool:
        """
        连接到模拟器 - 修复版本
        """
        if not self.adb_available:
            print(f"[错误] ADB不可用")
            return False

        try:
            # 构建命令列表（不是字符串）
            if self.adb_path == 'adb':
                connect_cmd = ['adb', 'connect', f'127.0.0.1:{adb_port}']
            else:
                connect_cmd = [self.adb_path, 'connect', f'127.0.0.1:{adb_port}']

            print(f"[连接] 尝试连接句柄 {hwnd} 到端口 {adb_port}")
            print(f"[连接] 使用ADB路径: {self.adb_path}")

            result = self._safe_run_command(connect_cmd, timeout=15)

            if result is None:
                print("[连接] 命令执行失败")
                return False

            print(f"[连接] 命令输出: {result.stdout}")
            if result.stderr:
                print(f"[连接] 错误输出: {result.stderr}")

            if 'connected' in result.stdout or 'already' in result.stdout:
                print(f"[成功] 句柄 {hwnd} 连接到端口 {adb_port}")
                self.connected_ports[adb_port] = hwnd
                self.hwnd_to_port[hwnd] = adb_port

                # 验证连接
                if self._verify_connection(hwnd):
                    print(f"[成功] 连接验证通过")
                    return True
                else:
                    print(f"[警告] 连接验证失败")
                    self.disconnect(hwnd)
                    return False
            else:
                print(f"[错误] 连接失败")
                return False

        except Exception as e:
            print(f"[错误] 连接异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _verify_connection(self, hwnd: int) -> bool:
        """验证连接"""
        try:
            result = self._run_adb_command(hwnd, ['shell', 'echo', 'test'], timeout=5)
            return result is not None and 'test' in result
        except:
            return False

    def _run_adb_command(self, hwnd: int, command: List[str], timeout: int = 10) -> Optional[str]:
        """执行ADB命令"""
        if not self.adb_available or hwnd not in self.hwnd_to_port:
            print(f"[错误] ADB不可用或句柄未连接: {hwnd}")
            return None

        adb_port = self.hwnd_to_port[hwnd]

        # 构建完整命令
        if self.adb_path == 'adb':
            full_cmd = ['adb', '-s', f'127.0.0.1:{adb_port}'] + command
        else:
            full_cmd = [self.adb_path, '-s', f'127.0.0.1:{adb_port}'] + command

        print(f"[ADB命令] 句柄 {hwnd} 端口 {adb_port}: {' '.join(full_cmd)}")

        result = self._safe_run_command(full_cmd, timeout)
        if result and result.returncode == 0:
            return result.stdout.strip()

        if result and result.stderr:
            print(f"[ADB错误] 错误输出: {result.stderr}")

        return None

    def click_position(self, hwnd: int, x: int, y: int) -> bool:
        """
        在指定句柄的模拟器上点击坐标

        Args:
            hwnd (int): 窗口句柄
            x (int): X坐标
            y (int): Y坐标

        Returns:
            bool: 是否成功
        """
        try:
            result = self._run_adb_command(hwnd, ['shell', 'input', 'tap', str(x), str(y)])
            if result is not None:
                print(f"[成功] 句柄 {hwnd} 点击坐标: ({x}, {y})")
                time.sleep(0.5)  # 点击后延迟
                return True
            return False
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 点击失败: {e}")
            return False

    def swipe(self, hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300) -> bool:
        """
        在指定句柄的模拟器上滑动

        Args:
            hwnd (int): 窗口句柄
            start_x, start_y: 起始坐标
            end_x, end_y: 结束坐标
            duration: 滑动持续时间(ms)

        Returns:
            bool: 是否成功
        """
        try:
            result = self._run_adb_command(hwnd, [
                'shell', 'input', 'swipe',
                str(start_x), str(start_y),
                str(end_x), str(end_y),
                str(duration)
            ])
            return result is not None
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 滑动失败: {e}")
            return False

    def input_text(self, hwnd: int, text: str) -> bool:
        """
        在指定句柄的模拟器上输入文本

        Args:
            hwnd (int): 窗口句柄
            text (str): 要输入的文本

        Returns:
            bool: 是否成功
        """
        try:
            # 转义特殊字符
            text = text.replace(' ', '%s').replace('"', '\\"')
            result = self._run_adb_command(hwnd, ['shell', 'input', 'text', text])
            return result is not None
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 输入文本失败: {e}")
            return False

    def get_screen_resolution(self, hwnd: int) -> Optional[Tuple[int, int]]:
        """
        获取指定句柄的模拟器分辨率

        Args:
            hwnd (int): 窗口句柄

        Returns:
            Optional[Tuple[int, int]]: (宽度, 高度)
        """
        try:
            result = self._run_adb_command(hwnd, ['shell', 'wm', 'size'])
            if result:
                match = re.search(r'(\d+)x(\d+)', result)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
                    return (width, height)
            return None
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 获取分辨率失败: {e}")
            return None

    def get_app_list(self, hwnd: int, _package_name:str, show_system_apps: bool = False) -> List[Dict[str, str]]:
        """
        获取应用列表

        Args:
            show_system_apps (bool): 是否显示系统应用

        Returns:
            List[Dict[str, str]]: 应用信息列表
            :param show_system_apps:
            :param hwnd:
            :param _package_name:
        """
        try:
            # 获取所有包名
            cmd = ['shell', 'pm', 'list', 'packages']
            if show_system_apps:
                cmd.append('-a')  # 显示所有应用（包括系统应用）

            result = self._run_adb_command(hwnd, cmd)
            if not result:
                return []

            # 解析包名
            packages = []
            for line in result.split('\n'):
                if line.startswith('package:'):
                    package_name = line.replace('package:', '').strip()
                    packages.append(package_name)
                    if _package_name in package_name:
                        packages = []
                        packages.append(_package_name)
                        return packages

            print(f"[成功] 找到 {len(packages)} 个应用")
            return packages

        except Exception as e:
            traceback.print_exc()  # 打印完整的 traceback 信息到控制台
            print(f"[错误] 获取应用列表失败: {e}")
            return []

    def get_app_list_with_details(self, hwnd: int, package_name: str, show_system_apps: bool = False) -> List[Dict[str, str]]:
        """
        获取应用列表（包含详细信息）

        Args:
            show_system_apps (bool): 是否显示系统应用

        Returns:
            List[Dict[str, str]]: 应用详细信息列表
            :param package_name:
            :param show_system_apps:
            :param hwnd:
        """
        try:
            # 获取所有包名
            packages = self.get_app_list(hwnd, package_name, show_system_apps)
            if not packages:
                return []

            apps_with_details = []

            for package_name in packages:
                # 获取应用详细信息
                app_info = self.get_app_info(package_name)
                if app_info:
                    apps_with_details.append(app_info)

            return apps_with_details

        except Exception as e:
            print(f"[错误] 获取应用详情失败: {e}")
            return []

    def get_app_info(self, package_name: str, hwnd: int) -> Optional[Dict[str, str]]:
        """
        获取指定应用的详细信息

        Args:
            package_name (str): 包名

        Returns:
            Optional[Dict[str, str]]: 应用信息字典
            :param package_name:
            :param hwnd:
        """
        try:
            # 获取应用基本信息
            cmd = ['shell', 'dumpsys', 'package', package_name]
            result = self._run_adb_command(hwnd, cmd)
            if not result:
                return None

            app_info = {'package_name': package_name}

            # 解析应用信息
            lines = result.split('\n')
            for line in lines:
                line = line.strip()

                # 应用名称
                if 'versionName=' in line:
                    version_match = re.search(r'versionName=([^\s]+)', line)
                    if version_match:
                        app_info['version_name'] = version_match.group(1)

                # 版本代码
                if 'versionCode=' in line:
                    code_match = re.search(r'versionCode=([^\s]+)', line)
                    if code_match:
                        app_info['version_code'] = code_match.group(1)

                # 应用标签（名称）
                if 'android:label=' in line:
                    label_match = re.search(r'android:label="([^"]+)"', line)
                    if label_match:
                        app_info['app_name'] = label_match.group(1)

                # 主Activity
                if 'android.intent.action.MAIN:' in line:
                    main_match = re.search(r'([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', line)
                    if main_match:
                        app_info['main_activity'] = main_match.group(1)

            # 如果没有找到应用名称，尝试其他方法
            if 'app_name' not in app_info:
                # 使用pm命令获取应用标签
                # 使用原始字符串前缀 r
                label_cmd = [
            'adb', '-s', f'127.0.0.1:{self.hwnd_to_port}',
            'shell', 'dumpsys', 'package', package_name, '|', 'grep', '-A', '5', 'MAIN'
        ]
                label_result = self._run_adb_command(hwnd, label_cmd)
                if label_result:
                    label_match = re.search(r'labelRes=0x[0-9a-fA-F]+\s+nonLocalizedLabel=null\s+label=([^\n]+)',
                                            label_result)
                    if label_match:
                        app_info['app_name'] = label_match.group(1).strip()

            return app_info

        except Exception as e:
            print(f"[错误] 获取应用信息失败 {package_name}: {e}")
            return None


    def get_installed_apps_by_keyword(self, keyword: str, hwnd: int, package_name:str, show_system_apps: bool = False) -> List[Dict[str, str]]:
        """
        根据关键词搜索已安装的应用

        Args:
            keyword (str): 搜索关键词
            show_system_apps (bool): 是否包含系统应用

        Returns:
            List[Dict[str, str]]: 匹配的应用列表
            :param show_system_apps:
            :param keyword:
            :param hwnd:
            :param package_name:
        """
        try:
            all_apps = self.get_app_list_with_details(hwnd,package_name, show_system_apps)
            matched_apps = []

            for app in all_apps:
                # 在包名和应用名称中搜索
                if (keyword.lower() in app.get('package_name', '').lower() or
                        keyword.lower() in app.get('app_name', '').lower()):
                    matched_apps.append(app)

            print(f"[成功] 找到 {len(matched_apps)} 个匹配 '{keyword}' 的应用")
            return matched_apps

        except Exception as e:
            print(f"[错误] 搜索应用失败: {e}")
            return []

    def get_running_apps(self) -> List[Dict[str, str]]:
        """
        获取正在运行的应用

        Returns:
            List[Dict[str, str]]: 运行中的应用列表
        """
        try:
            # 获取正在运行的应用
            cmd = ['shell', 'ps']
            result = self._run_adb_command(cmd)
            if not result:
                return []

            running_apps = []
            lines = result.split('\n')

            for line in lines:
                # 解析进程信息
                parts = line.split()
                if len(parts) >= 9:
                    user, pid, ppid, vsize, rss, wchan, pc, state, name = parts[:9]
                    if name and '.' in name:  # 可能是应用包名
                        running_apps.append({
                            'package_name': name,
                            'pid': pid,
                            'user': user,
                            'state': state
                        })

            print(f"[成功] 找到 {len(running_apps)} 个运行中的应用")
            return running_apps

        except Exception as e:
            print(f"[错误] 获取运行中的应用失败: {e}")
            return []

    def launch_app(self, hwnd: int, package_name: str) -> bool:
        """
        在指定句柄的模拟器上启动应用

        Args:
            hwnd (int): 窗口句柄
            package_name (str): 包名

        Returns:
            bool: 是否成功
        """
        try:
            cmd = [
                'shell', 'am', 'start',
                '-a', 'android.intent.action.MAIN',
                '-c', 'android.intent.category.LAUNCHER',
                package_name
            ]
            result = self._run_adb_command(hwnd, cmd)
            return result is not None and 'Error' not in result
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 启动应用失败: {e}")
            return False

    def stop_app(self, hwnd: int, package_name: str) -> bool:
        """
        在指定句柄的模拟器上停止应用

        Args:
            hwnd (int): 窗口句柄
            package_name (str): 包名

        Returns:
            bool: 是否成功
        """
        try:
            result = self._run_adb_command(hwnd, ['shell', 'am', 'force-stop', package_name])
            return result is not None
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 停止应用失败: {e}")
            return False

    # def get_current_activity(self, hwnd: int) -> Optional[str]:
    #     """
    #     获取指定句柄的模拟器当前活动
    #
    #     Args:
    #         hwnd (int): 窗口句柄
    #
    #     Returns:
    #         Optional[str]: 当前活动名称
    #     """
    #     try:
    #         result = self._run_adb_command(hwnd, ['shell', 'dumpsys', 'activity', 'activities', '|', 'grep',
    #                                               'mResumedActivity'])
    #         if result:
    #             match = re.search(r'([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', result)
    #             if match:
    #                 return match.group(1)
    #         return None
    #     except Exception as e:
    #         print(f"[错误] 句柄 {hwnd} 获取当前活动失败: {e}")
    #         return None

    def disconnect(self, hwnd: int) -> bool:
        """
        断开指定句柄的ADB连接

        Args:
            hwnd (int): 窗口句柄

        Returns:
            bool: 是否成功断开
        """
        try:
            if hwnd in self.hwnd_to_port:
                port = self.hwnd_to_port[hwnd]
                result = subprocess.run(['adb', 'disconnect', f'127.0.0.1:{port}'],
                                        capture_output=True, text=True)

                # 清理映射
                if port in self.connected_ports:
                    del self.connected_ports[port]
                del self.hwnd_to_port[hwnd]

                return 'disconnected' in result.stdout
            return False
        except Exception as e:
            print(f"[错误] 句柄 {hwnd} 断开连接失败: {e}")
            return False

    def disconnect_all(self) -> bool:
        """
        断开所有ADB连接

        Returns:
            bool: 是否成功
        """
        try:
            hwnds = list(self.hwnd_to_port.keys())
            success = True
            for hwnd in hwnds:
                if not self.disconnect(hwnd):
                    success = False
            return success
        except Exception as e:
            print(f"[错误] 断开所有连接失败: {e}")
            return False

    def get_current_activity(self, hwnd: int) -> Optional[str]:
        """
        获取当前前台Activity

        Args:
            hwnd (int): 窗口句柄

        Returns:
            Optional[str]: 当前Activity名称，格式为"包名/活动名"
        """
        try:
            if hwnd not in self.hwnd_to_port:
                print(f"[错误] 句柄 {hwnd} 未连接")
                return None

            port = self.hwnd_to_port[hwnd]

            # 方法1: 使用dumpsys activity（最可靠）
            activity = self._get_current_activity_by_dumpsys(hwnd)
            if activity:
                return activity

            # 方法2: 使用logcat（备选）
            activity = self._get_current_activity_by_logcat(hwnd)
            if activity:
                return activity

            # 方法3: 使用am命令（备选）
            activity = self._get_current_activity_by_am(hwnd)
            if activity:
                return activity

            print("[错误] 所有方法都无法获取当前Activity")
            return None

        except Exception as e:
            print(f"[错误] 获取当前Activity失败: {e}")
            return None

    def _get_current_activity_by_dumpsys(self, hwnd: int) -> Optional[str]:
        """
        使用dumpsys activity获取当前Activity（最可靠的方法）
        """
        try:
            port = self.hwnd_to_port[hwnd]

            # 方法1.1: 查找mResumedActivity
            cmd1 = [
                self.adb_path, '-s', f'127.0.0.1:{port}',
                'shell', 'dumpsys', 'activity', 'activities',
                '|', 'grep', '-E', 'mResumedActivity|mFocusedActivity'
            ]

            result = self._safe_run_command(cmd1)
            print(result)
            if result and result.stdout:
                lines = result.stdout.split('\n')

                for line in lines:
                    # 解析格式: mResumedActivity: ActivityRecord{... com.netease.dhxy/.MainActivity}
                    match = re.search(r'([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', line)
                    if match:
                        activity = match.group(1)
                        print(f"[Dumpsys] 找到当前Activity: {activity}")
                        return activity

            # 方法1.2: 查找顶层Activity
            cmd2 = [
                self.adb_path, '-s', f'127.0.0.1:{port}',
                'shell', 'dumpsys', 'activity', '|', 'grep', '-A', '5', 'top-activity'
            ]

            result = self._safe_run_command(cmd2)
            if result and result.stdout:
                lines = result.stdout.split('\n')
                print(result)
                for line in lines:
                    if 'top-activity' in line:
                        match = re.search(r'([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', line)
                        if match:
                            activity = match.group(1)
                            print(f"[Dumpsys] 找到顶层Activity: {activity}")
                            return activity

            return None

        except Exception as e:
            print(f"[错误] dumpsys获取Activity失败: {e}")
            return None

    def _get_current_activity_by_logcat(self, hwnd: int) -> Optional[str]:
        """
        使用logcat获取当前Activity
        """
        try:
            port = self.hwnd_to_port[hwnd]

            # 清空旧日志
            clear_cmd = [self.adb_path, '-s', f'127.0.0.1:{port}', 'shell', 'logcat', '-c']
            self._safe_run_command(clear_cmd)

            # 获取最近的Activity切换日志
            cmd = [
                self.adb_path, '-s', f'127.0.0.1:{port}',
                'shell', 'logcat', '-d', '-s', 'ActivityManager',
                '|', 'grep', '-E', 'Displayed|Focused|Resumed', '|', 'tail', '-5'
            ]

            result = self._safe_run_command(cmd)
            if result and result.stdout:
                lines = result.stdout.split('\n')
                # 从最新的日志开始查找
                for line in reversed(lines):
                    if any(keyword in line for keyword in ['Displayed', 'Focused', 'Resumed']):
                        match = re.search(r'([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', line)
                        if match:
                            activity = match.group(1)
                            print(f"[Logcat] 找到Activity: {activity}")
                            return activity

            return None

        except Exception as e:
            print(f"[错误] logcat获取Activity失败: {e}")
            return None

    def _get_current_activity_by_am(self, hwnd: int) -> Optional[str]:
        """
        使用am命令获取当前Activity
        """
        try:
            port = self.hwnd_to_port[hwnd]

            # 方法3.1: 使用am stack list
            cmd1 = [
                self.adb_path, '-s', f'127.0.0.1:{port}',
                'shell', 'am', 'stack', 'list'
            ]

            result = self._safe_run_command(cmd1)
            if result and result.stdout:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'taskId=' in line and 'topActivity=' in line:
                        match = re.search(r'topActivity=([a-zA-Z0-9._]+/[a-zA-Z0-9._]+)', line)
                        if match:
                            activity = match.group(1)
                            print(f"[AM] 找到顶层Activity: {activity}")
                            return activity

            # 方法3.2: 使用am命令的其他方式
            cmd2 = [
                self.adb_path, '-s', f'127.0.0.1:{port}',
                'shell', 'am', 'get-current-activity'
            ]

            result = self._safe_run_command(cmd2)
            if result and result.stdout:
                activity = result.stdout.strip()
                if activity and '/' in activity:
                    print(f"[AM] 找到当前Activity: {activity}")
                    return activity

            return None

        except Exception as e:
            print(f"[错误] am命令获取Activity失败: {e}")
            return None

    def get_current_activity_with_details(self, hwnd: int) -> Optional[Dict[str, str]]:
        """
        获取当前Activity的详细信息

        Args:
            hwnd (int): 窗口句柄

        Returns:
            Optional[Dict[str, str]]: Activity详细信息
        """
        try:
            activity = self.get_current_activity(hwnd)
            if not activity:
                return None

            # 解析包名和活动名
            if '/' in activity:
                package_name, activity_name = activity.split('/', 1)
            else:
                package_name = activity
                activity_name = "未知"

            # 获取应用信息
            app_info = self.get_app_info(hwnd, package_name)

            activity_info = {
                'full_activity': activity,
                'package_name': package_name,
                'activity_name': activity_name,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if app_info:
                activity_info.update(app_info)

            return activity_info

        except Exception as e:
            print(f"[错误] 获取Activity详情失败: {e}")
            return None

    def monitor_activity_changes(self, hwnd: int, duration: int = 30, interval: float = 1.0) -> List[
        Dict[str, str]]:
        """
        监控Activity变化

        Args:
            hwnd (int): 窗口句柄
            duration (int): 监控时长(秒)
            interval (float): 检查间隔(秒)

        Returns:
            List[Dict[str, str]]: Activity变化历史
        """
        activity_history = []
        last_activity = None
        start_time = time.time()

        print(f"[监控] 开始监控Activity变化，时长: {duration}秒")

        try:
            while time.time() - start_time < duration:
                current_activity = self.get_current_activity_with_details(hwnd)

                if current_activity and current_activity['full_activity'] != last_activity:
                    print(f"[监控] Activity变化: {last_activity} -> {current_activity['full_activity']}")
                    activity_history.append(current_activity)
                    last_activity = current_activity['full_activity']

                time.sleep(interval)

            print(f"[监控] 监控结束，共检测到 {len(activity_history)} 次Activity变化")
            return activity_history

        except Exception as e:
            print(f"[错误] Activity监控失败: {e}")
            return activity_history

    def wait_for_activity(self, hwnd: int, target_activity: str, timeout: int = 30) -> bool:
        """
        等待特定Activity出现

        Args:
            hwnd (int): 窗口句柄
            target_activity (str): 目标Activity名称
            timeout (int): 超时时间(秒)

        Returns:
            bool: 是否等到目标Activity
        """
        start_time = time.time()

        print(f"[等待] 等待Activity: {target_activity}，超时: {timeout}秒")

        try:
            while time.time() - start_time < timeout:
                current_activity = self.get_current_activity(hwnd)

                if current_activity:
                    print(f"[等待] 当前Activity: {current_activity}")

                    # 支持精确匹配和模糊匹配
                    if current_activity == target_activity or target_activity in current_activity:
                        print(f"[成功] 等到目标Activity: {target_activity}")
                        return True

                time.sleep(1)  # 每秒检查一次

            print(f"[超时] 未等到目标Activity: {target_activity}")
            return False

        except Exception as e:
            print(f"[错误] 等待Activity失败: {e}")
            return False

    def is_activity_running(self, hwnd: int, target_activity: str) -> bool:
        """
        检查指定Activity是否正在运行

        Args:
            hwnd (int): 窗口句柄
            target_activity (str): 目标Activity名称

        Returns:
            bool: Activity是否正在运行
        """
        try:
            current_activity = self.get_current_activity(hwnd)
            if current_activity:
                return current_activity == target_activity or target_activity in current_activity
            return False

        except Exception as e:
            print(f"[错误] 检查Activity运行状态失败: {e}")
            return False