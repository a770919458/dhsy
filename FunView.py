import asyncio

import wx
import wx.lib.agw.flatnotebook as fnb
import wx.lib.scrolledpanel as scrolled
import VersionManager
from SimulatorManager import SimulatorManager
from game.DailyTasks import DailyTasks
from util.MouseController import MouseController
from util.WindowManager import WindowManager


class MainWindow(wx.Frame):
    def __init__(self):
        self._add_log_message = None
        self.window_list = None
        self.log_text = None
        self.buttons = None
        self.simulators = None
        self.version_manager = VersionManager.VersionManager()

        self.window_manager = WindowManager()   # 创建窗口实例
        self.game_instances = {}
        # 使用新的鼠标控制器
        self.mouse_controller = MouseController()
        super(MainWindow, self).__init__(None, title=f"游戏辅助工具 版本：{self.version_manager.current_version}",
                                         size=(1000, 800))
        self.Centre()
        self.InitUI()

    def InitUI(self):
        # 创建主面板
        panel = wx.Panel(self)

        # 创建主垂直布局
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. 顶部公告栏
        notice_sizer = self.CreateNoticeBar(panel)
        main_sizer.Add(notice_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 2. 模式选择和控制区域
        control_sizer = self.CreateControlArea(panel)
        main_sizer.Add(control_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 3. 中间主要内容区域（窗口列表 - 占用100%宽度）
        content_sizer = self.CreateContentArea(panel)
        main_sizer.Add(content_sizer, 1, flag=wx.EXPAND | wx.ALL, border=5)

        # 4. 底部区域（功能标签页+运行日志）
        bottom_sizer = self.CreateBottomArea(panel)
        main_sizer.Add(bottom_sizer, 1, flag=wx.EXPAND | wx.ALL, border=5)

        panel.SetSizer(main_sizer)
        # 绑定窗口大小改变事件
        self.Bind(wx.EVT_SIZE, self.on_size)

    def CreateNoticeBar(self, panel):
        """创建顶部公告栏"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 公告文本
        notice_text = "公告:请更新到11.32，否则后面无法正常更新。加盾后远程使用Ctrl键+F12显示出来"
        notice = wx.StaticText(panel, label=notice_text)
        notice.SetForegroundColour(wx.Colour(255, 0, 0))  # 红色文字
        notice.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        sizer.Add(notice, 1, flag=wx.ALIGN_CENTER_VERTICAL)

        return sizer

    def CreateControlArea(self, panel):
        """创建控制区域"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 控制按钮
        btn_names = ["获取窗口", "全选窗口","启动任务", "暂停勾选", "恢复勾选", "结束勾选", "全部结束"
            # , "窗口禁鼠", "恢复鼠标"
                     ]

        btn_sizer = wx.WrapSizer(wx.HORIZONTAL)

        self.buttons = {}  # 保存按钮引用，便于后续操作

        for name in btn_names:
            btn = wx.Button(panel, label=name, size=(100, 25))
            btn_sizer.Add(btn, flag=wx.ALL, border=2)
            self.buttons[name] = btn  # 保存按钮引用

        # 绑定按钮事件
        self.BindButtonEvents()

        sizer.Add(btn_sizer, flag=wx.ALIGN_CENTER_VERTICAL)

        return sizer

    def CreateContentArea(self, panel):
        """创建主要内容区域 - 修正版本"""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 添加标题
        title_label = wx.StaticText(panel, label="窗口列表")
        title_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title_label, 0, wx.ALL, 5)

        # 创建可滚动的窗口列表面板
        scrolled_panel = scrolled.ScrolledPanel(panel)
        scrolled_panel.SetupScrolling(scroll_x=True, scroll_y=True)
        scrolled_panel.SetScrollRate(10, 10)

        # 创建窗口列表表格 - 将 scrolled_panel 作为 parent
        self.window_list = self.CreateWindowList(scrolled_panel)  # ✅ parent 是 scrolled_panel

        # 设置 scrolled_panel 的 sizer
        list_sizer = wx.BoxSizer(wx.VERTICAL)
        list_sizer.Add(self.window_list, 1, flag=wx.EXPAND)  # ✅ 将 grid 添加到 sizer
        scrolled_panel.SetSizer(list_sizer)  # ✅ 将 sizer 设置给 scrolled_panel

        # 设置 scrolled_panel 的最小尺寸
        scrolled_panel.SetMinSize((-1, 200))

        # 重要：在添加内容后重新设置滚动区域
        scrolled_panel.SetupScrolling()

        sizer.Add(scrolled_panel, 1, flag=wx.EXPAND)

        return sizer

    def CreateFunctionPage(self, parent):
        """创建功能开关页面 - 添加滚动条"""
        # 使用ScrolledPanel作为功能页面的容器
        scrolled_panel = scrolled.ScrolledPanel(parent)
        scrolled_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        scrolled_panel.SetScrollRate(10, 10)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # 模式选择
        mode_group = wx.StaticBox(scrolled_panel, label="模式选择")
        mode_sizer = wx.StaticBoxSizer(mode_group, wx.HORIZONTAL)
        self_lead = wx.CheckBox(scrolled_panel, label="自己带队")
        follow_team = wx.CheckBox(scrolled_panel, label="跟随队伍")
        mode_sizer.Add(self_lead, flag=wx.RIGHT, border=10)
        mode_sizer.Add(follow_team)
        sizer.Add(mode_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 功能选择
        func_group = wx.StaticBox(scrolled_panel, label="功能选择")
        func_sizer = wx.StaticBoxSizer(func_group, wx.VERTICAL)

        funcs1 = ["本机组队", "副本任务", "组队任务", "单人任务", "五环任务", "跑200环"]
        funcs2 = ["科举殿试", "领灵气果", "领活跃度", "领取邮件", "抓任务宠", "帮派入定"]
        funcs3 = ["物品上架", "注销离线", "换号单人"]

        grid_sizer = wx.FlexGridSizer(3, 6, 5, 5)
        for func in funcs1 + funcs2 + funcs3:
            cb = wx.CheckBox(scrolled_panel, label=func)
            grid_sizer.Add(cb, flag=wx.EXPAND)

        func_sizer.Add(grid_sizer, flag=wx.EXPAND)
        sizer.Add(func_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 无限挂机
        hang_group = wx.StaticBox(scrolled_panel, label="无限挂机")
        hang_sizer = wx.StaticBoxSizer(hang_group, wx.VERTICAL)

        hang_funcs = ["北俱冰原", "无限抓鬼", "无限天庭", "无限修罗", "无限入定", "原地挂机"]
        hang_grid = wx.WrapSizer(wx.HORIZONTAL)
        for func in hang_funcs:
            cb = wx.CheckBox(scrolled_panel, label=func)
            hang_grid.Add(cb, flag=wx.RIGHT, border=10)

        hang_sizer.Add(hang_grid, flag=wx.EXPAND)
        sizer.Add(hang_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 其它功能
        other_group = wx.StaticBox(scrolled_panel, label="其它功能")
        other_sizer = wx.StaticBoxSizer(other_group, wx.VERTICAL)

        other_funcs = ["多宝秒货", "挂万兽园", "便捷喊话", "抢星助手", "截图反馈", "测试功能"]
        other_grid = wx.WrapSizer(wx.HORIZONTAL)
        for func in other_funcs:
            cb = wx.CheckBox(scrolled_panel, label=func)
            other_grid.Add(cb, flag=wx.RIGHT, border=10)

        other_sizer.Add(other_grid, flag=wx.EXPAND)
        sizer.Add(other_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        # 配置区域
        config_sizer = wx.BoxSizer(wx.HORIZONTAL)
        start_btn = wx.Button(scrolled_panel, label="一键起号", size=(80, 25))
        config_label = wx.StaticText(scrolled_panel, label="配置名")
        config_combo = wx.ComboBox(scrolled_panel, value="配置1", choices=["配置1", "配置2", "配置3"])
        save_btn = wx.Button(scrolled_panel, label="保存", size=(60, 25))
        load_btn = wx.Button(scrolled_panel, label="读取", size=(60, 25))
        clear_btn = wx.Button(scrolled_panel, label="清空", size=(60, 25))

        config_sizer.Add(start_btn, flag=wx.RIGHT, border=5)
        config_sizer.Add(config_label, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
        config_sizer.Add(config_combo, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
        config_sizer.Add(save_btn, flag=wx.RIGHT, border=5)
        config_sizer.Add(load_btn, flag=wx.RIGHT, border=5)
        config_sizer.Add(clear_btn)

        sizer.Add(config_sizer, flag=wx.ALIGN_CENTER | wx.TOP, border=10)

        # 添加一些空白空间，确保内容足够多时可以滚动
        sizer.AddSpacer(20)

        scrolled_panel.SetSizer(sizer)
        scrolled_panel.SetAutoLayout(True)
        scrolled_panel.SetupScrolling()

        return scrolled_panel

    def CreateWindowList(self, parent):
        """使用 ListCtrl 创建带复选框的窗口列表"""
        # 创建 ListCtrl 并启用复选框
        list_ctrl = wx.ListCtrl(parent,
                                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES)

        # 启用复选框功能
        list_ctrl.EnableCheckBoxes(enable=True)

        # 添加列（第一列会自动显示复选框）
        list_ctrl.AppendColumn("选择", width=60)
        list_ctrl.AppendColumn("窗口", width=80)
        list_ctrl.AppendColumn("角色名字", width=120)
        list_ctrl.AppendColumn("种族", width=80)
        list_ctrl.AppendColumn("等级", width=60)
        list_ctrl.AppendColumn("状态", width=80)
        list_ctrl.AppendColumn("运行任务", width=100)
        list_ctrl.AppendColumn("队伍信息", width=100)
        list_ctrl.AppendColumn("角色银两", width=100)

        # 绑定复选框状态改变事件
        list_ctrl.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_item_checked)
        list_ctrl.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_item_unchecked)

        # 保存为实例变量以便后续操作
        self.window_list = list_ctrl

        # 初始自动调整列宽
        wx.CallAfter(self.auto_adjust_list_columns, list_ctrl)

        return list_ctrl

    def auto_adjust_list_columns(self, list_ctrl):
        """自动调整 ListCtrl 列宽以铺满可用空间"""
        try:
            # 获取 ListCtrl 的宽度（减去滚动条宽度）
            list_width = list_ctrl.GetSize().width - 20  # 减去滚动条的大致宽度

            # 如果无法获取有效宽度，使用默认值
            if list_width <= 0:
                list_width = 800  # 默认宽度

            # 定义各列的权重比例（根据重要性分配）
            column_weights = [
                0.06,  # 选择列：6%
                0.10,  # 窗口：10%
                0.18,  # 角色名字：18%
                0.10,  # 种族：10%
                0.08,  # 等级：8%
                0.10,  # 状态：10%
                0.14,  # 运行任务：14%
                0.12,  # 队伍信息：12%
                0.12  # 角色银两：12%
            ]

            # 计算各列宽度
            total_weight = sum(column_weights)
            for col, weight in enumerate(column_weights):
                col_width = int(list_width * weight / total_weight)
                # 设置最小和最大宽度限制
                col_width = max(col_width, 50)  # 最小宽度50px
                col_width = min(col_width, 300)  # 最大宽度300px
                list_ctrl.SetColumnWidth(col, col_width)

        except Exception as e:
            print(f"自动调整列宽时出错: {e}")
            # 设置默认列宽作为备选方案
            self.set_default_column_widths(list_ctrl)

    def set_default_column_widths(self, list_ctrl):
        """设置默认列宽"""
        default_widths = [60, 80, 120, 80, 60, 80, 100, 100, 100]
        for col, width in enumerate(default_widths):
            if col < list_ctrl.GetColumnCount():
                list_ctrl.SetColumnWidth(col, width)

    def on_size(self, event):
        """窗口大小改变时自动调整列宽"""
        if hasattr(self, 'window_list') and self.window_list:
            self.auto_adjust_list_columns(self.window_list)
        event.Skip()

    def on_item_checked(self, event):
        """项目被选中时的处理"""
        item_index = event.GetIndex()
        self.add_log_message(f"选中了第 {item_index + 1} 个窗口")
        event.Skip()

    def on_item_unchecked(self, event):
        """项目取消选中时的处理"""
        item_index = event.GetIndex()
        self.add_log_message(f"取消选中第 {item_index + 1} 个窗口")
        event.Skip()

    def select_all_windows(self):
        """全选窗口"""
        if hasattr(self, 'window_list'):
            list_ctrl = self.window_list
            item_count = list_ctrl.GetItemCount()

            for i in range(item_count):
                list_ctrl.CheckItem(i, True)

    def clear_selection(self):
        """清空选择"""
        if hasattr(self, 'window_list'):
            list_ctrl = self.window_list
            item_count = list_ctrl.GetItemCount()

            for i in range(item_count):
                list_ctrl.CheckItem(i, False)


    def CreateBottomArea(self, panel):
        """创建底部区域 - 为功能标签页和日志添加滚动条"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 左侧：功能标签页（占40%宽度）- 使用ScrolledPanel包装
        left_panel = wx.Panel(panel)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        # 创建扁平标签页
        notebook = fnb.FlatNotebook(left_panel, agwStyle=fnb.FNB_NO_X_BUTTON | fnb.FNB_NO_NAV_BUTTONS)

        # 功能开关标签页（已经内置滚动条）
        func_page = self.CreateFunctionPage(notebook)
        notebook.AddPage(func_page, "功能开关")

        # 任务设置标签页 - 也添加滚动条
        task_scrolled_panel = scrolled.ScrolledPanel(notebook)
        task_scrolled_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        task_scrolled_panel.SetScrollRate(10, 10)

        task_sizer = wx.BoxSizer(wx.VERTICAL)

        # 添加任务设置内容
        task_groups = [
            ("日常任务", ["师门任务", "帮派任务", "剧情任务", "活动任务"]),
            ("挂机设置", ["自动战斗", "自动补血", "自动补蓝", "自动修理"]),
            ("系统设置", ["性能优化", "界面设置", "快捷键", "通知设置"])
        ]

        for group_name, tasks in task_groups:
            group_box = wx.StaticBox(task_scrolled_panel, label=group_name)
            group_sizer = wx.StaticBoxSizer(group_box, wx.VERTICAL)

            for task in tasks:
                cb = wx.CheckBox(task_scrolled_panel, label=task)
                group_sizer.Add(cb, 0, wx.ALL, 2)

            task_sizer.Add(group_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 添加更多内容确保可以滚动
        for i in range(10):
            label = wx.StaticText(task_scrolled_panel, label=f"额外设置项 {i + 1}")
            text_ctrl = wx.TextCtrl(task_scrolled_panel, value=f"设置值{i + 1}")
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            h_sizer.Add(label, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
            h_sizer.Add(text_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
            task_sizer.Add(h_sizer, 0, wx.EXPAND | wx.ALL, 2)

        task_scrolled_panel.SetSizer(task_sizer)
        task_scrolled_panel.SetupScrolling()
        notebook.AddPage(task_scrolled_panel, "任务设置")

        left_sizer.Add(notebook, 1, flag=wx.EXPAND)
        left_panel.SetSizer(left_sizer)

        # 右侧：运行日志（占70%宽度）- 使用ScrolledPanel
        right_panel = wx.Panel(panel)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        # 运行日志标题和控件
        log_label = wx.StaticText(right_panel, label="运行日志")
        self.log_text = wx.TextCtrl(right_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.VSCROLL | wx.HSCROLL)# 保存为实例属性
        self.log_text.SetBackgroundColour(wx.Colour(0, 0, 0))
        self.log_text.SetForegroundColour(wx.Colour(0, 255, 0))

        right_sizer.Add(log_label, 0, flag=wx.BOTTOM, border=5)
        right_sizer.Add(self.log_text, 1, flag=wx.EXPAND)

        right_panel.SetSizer(right_sizer)

        sizer.Add(left_panel, 5, flag=wx.EXPAND | wx.RIGHT, border=5)
        sizer.Add(right_panel, 5, flag=wx.EXPAND)

        return sizer

    def BindButtonEvents(self):
        """绑定所有按钮的点击事件"""
        # 获取窗口按钮
        if "获取窗口" in self.buttons:
            self.buttons["获取窗口"].Bind(wx.EVT_BUTTON, self.on_get_windows)

        # 全选窗口按钮
        if "全选窗口" in self.buttons:
            self.buttons["全选窗口"].Bind(wx.EVT_BUTTON, self.on_select_all_windows)

        # 启动任务按钮
        if "启动任务" in self.buttons:
            self.buttons["启动任务"].Bind(wx.EVT_BUTTON, self.on_start_tasks)

        # 暂停勾选按钮
        if "暂停勾选" in self.buttons:
            self.buttons["暂停勾选"].Bind(wx.EVT_BUTTON, self.on_pause_selection)

        # 恢复勾选按钮
        if "恢复勾选" in self.buttons:
            self.buttons["恢复勾选"].Bind(wx.EVT_BUTTON, self.on_resume_selection)

        # 结束勾选按钮
        if "结束勾选" in self.buttons:
            self.buttons["结束勾选"].Bind(wx.EVT_BUTTON, self.on_stop_selection)

        # 全部结束按钮
        if "全部结束" in self.buttons:
            self.buttons["全部结束"].Bind(wx.EVT_BUTTON, self.on_stop_all)

    def on_get_windows(self, event):
        """获取窗口按钮点击事件"""
        print("on_get_windows 函数被调用")  # 调试信息
        self.add_log_message("正在查找窗口...")
        try:
            # 显示查找进度
            progress_dialog = wx.ProgressDialog(
                "查找窗口",
                "正在查找雷电模拟器窗口...",
                maximum=100,
                parent=self,
                style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
            )

            # 查找所有游戏窗口
            simulators = self.window_manager.find_window(keyword="大话西游手游", exact_match=True)
            # 没有则查找模拟器
            if not simulators:
                sm = SimulatorManager()
                simulators += sm.find_all_simulators("雷电模拟器")
            progress_dialog.Update(100, "查找完成")
            progress_dialog.Destroy()

            if simulators:
                # 更新窗口列表表格
                self.update_window_list(simulators)

                # 显示找到的窗口数量
                #wx.MessageBox(f"成功找到 {len(simulators)} 个雷电模拟器窗口", "提示", wx.OK | wx.ICON_INFORMATION)

                # 在日志中记录
                self.add_log_message(f"成功获取 {len(simulators)} 个窗口")
            else:
                wx.MessageBox("未找到任何雷电模拟器窗口", "警告", wx.OK | wx.ICON_WARNING)
                self.add_log_message("未找到任何雷电模拟器窗口")

        except Exception as e:
            wx.MessageBox(f"获取窗口时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"获取窗口出错: {str(e)}")

    def on_select_all_windows(self, event):
        """全选窗口按钮点击事件"""
        try:
            if hasattr(self, 'window_list'):
                self.select_all_windows()
                item_count = self.window_list.GetItemCount()
                # wx.MessageBox(f"已全选 {item_count} 个窗口", "提示", wx.OK | wx.ICON_INFORMATION)
                self.add_log_message(f"全选 {item_count} 个窗口")
            else:
                wx.MessageBox("请先获取窗口", "提示", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"全选窗口时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"全选窗口出错: {str(e)}")

    def on_start_tasks(self, event):
        """启动任务按钮点击事件"""
        # 多线程启动游戏
        # self.start_games_threaded(event)

        # self._start_games_single_thread()

        #开始执行任务
        dailyTasks = DailyTasks()
        selected_windows = self.get_selected_windows()
        # 创建新的事件循环运行异步函数
        async def run_async():
            await dailyTasks.start_task(selected_windows)

        # 在新的事件循环中运行
        asyncio.run(run_async())

    def _update_progress_ui(self, current: int, message: str):
        """更新UI进度（线程安全）"""
        if hasattr(self, 'progress_dialog'):
            wx.CallAfter(self.progress_dialog.Update, current, message)
        else:
            # 创建进度对话框
            wx.CallAfter(self._create_progress_dialog, len(self.get_selected_windows()))

    def _add_log_message_ui(self, message: str):
        """添加日志消息（线程安全）"""
        wx.CallAfter(self.add_log_message, message)

    def _create_progress_dialog(self, total: int):
        """创建进度对话框"""
        self.progress_dialog = wx.ProgressDialog(
            "多线程启动游戏",
            f"正在启动 0/{total} 个窗口...",
            maximum=total,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
        )

    def stop_launch_process(self):
        """停止启动过程"""
        if hasattr(self, 'launcher'):
            self.launcher.stop_event.set()
            self.add_log_message("[停止] 启动过程已停止")

    def on_pause_selection(self, event):
        """暂停勾选按钮点击事件"""
        try:
            # 这里添加暂停勾选的逻辑
            self.add_log_message("暂停窗口勾选")
            wx.MessageBox("已暂停窗口勾选", "提示", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(f"暂停勾选时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"暂停勾选出错: {str(e)}")

    def on_resume_selection(self, event):
        """恢复勾选按钮点击事件"""
        try:
            # 这里添加恢复勾选的逻辑
            self.add_log_message("恢复窗口勾选")
            wx.MessageBox("已恢复窗口勾选", "提示", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(f"恢复勾选时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"恢复勾选出错: {str(e)}")

    def on_stop_selection(self, event):
        """结束勾选按钮点击事件"""
        try:
            # 获取选中的窗口
            selected_windows = self.get_selected_windows()

            if selected_windows:
                result = wx.MessageBox(
                    f"确定要结束 {len(selected_windows)} 个选中窗口的任务吗？",
                    "确认",
                    wx.YES_NO | wx.ICON_QUESTION
                )

                if result == wx.YES:
                    # 模拟结束选中窗口任务
                    for window_info in selected_windows:
                        self.add_log_message(f"结束任务: {window_info['title']}")

                    wx.MessageBox(f"已结束 {len(selected_windows)} 个窗口的任务", "提示", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("请先选择要结束任务的窗口", "提示", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(f"结束勾选时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"结束勾选出错: {str(e)}")

    def on_stop_all(self, event):
        """全部结束按钮点击事件"""
        try:
            if hasattr(self, 'window_grid'):
                rows = self.window_grid.GetNumberRows()
                if rows > 0:
                    result = wx.MessageBox(
                        f"确定要结束所有 {rows} 个窗口的任务吗？",
                        "确认",
                        wx.YES_NO | wx.ICON_QUESTION
                    )

                    if result == wx.YES:
                        # 模拟结束所有窗口任务
                        for row in range(rows):
                            window_title = self.window_grid.GetCellValue(row, 1)
                            self.add_log_message(f"结束所有任务: {window_title}")

                        wx.MessageBox(f"已结束所有 {rows} 个窗口的任务", "提示", wx.OK | wx.ICON_INFORMATION)
                else:
                    wx.MessageBox("没有运行中的窗口任务", "提示", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("没有运行中的窗口任务", "提示", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(f"全部结束时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            self.add_log_message(f"全部结束出错: {str(e)}")

    def get_selected_windows(self):
        """获取选中的窗口信息"""
        selected_windows = []
        if hasattr(self, 'window_list') and hasattr(self, 'simulators'):
            list_ctrl = self.window_list
            item_count = list_ctrl.GetItemCount()

            for i in range(item_count):
                if list_ctrl.IsItemChecked(i):
                    if i < len(self.simulators):
                        window_info = self.simulators[i]
                        # 确保包含 hwnd 字段
                        if 'handle' in window_info:
                            window_info['hwnd'] = window_info['handle']
                        elif 'hwnd' not in window_info:
                            # 如果 SimulatorManager 返回的字段名不是 'hwnd'，尝试其他常见字段名
                            for key in ['handle', 'hwnd', 'window_handle', 'window']:
                                if key in window_info:
                                    window_info['hwnd'] = window_info[key]
                                    break
                        selected_windows.append(self.simulators[i])


        return selected_windows

    def update_window_list(self, simulators):
        """更新窗口列表表格"""
        self.simulators = simulators

        if not hasattr(self, 'window_list'):
            return

        list_ctrl = self.window_list
        list_ctrl.DeleteAllItems()  # 清空所有项目

        # 添加新数据
        for i, sim in reversed(list(enumerate(simulators))):
            index = list_ctrl.InsertItem(i, "")  # 插入新行，空文本
            list_ctrl.SetItem(index, 1, sim.get('title', '未知'))
            list_ctrl.SetItem(index, 2, "未知")
            list_ctrl.SetItem(index, 3, "未知")
            list_ctrl.SetItem(index, 4, "未知")
            list_ctrl.SetItem(index, 5, "就绪")
            list_ctrl.SetItem(index, 6, "无")
            list_ctrl.SetItem(index, 7, "无")
            list_ctrl.SetItem(index, 8, "未知")

            # 默认不选中
            list_ctrl.CheckItem(index, False)
            # 数据更新后重新调整列宽
            wx.CallAfter(self.auto_adjust_list_columns, list_ctrl)

    def add_log_message(self, message):
        """添加日志消息"""
        if hasattr(self, 'log_text'):
            import datetime
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.AppendText(f"[{timestamp}] {message}\n")


    def OnExit(self, event):
        """退出程序"""
        self.Close()