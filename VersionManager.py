# VersionManager.py
import wx
import requests
import json
import sys
import os
from packaging import version



class VersionManager:
    def __init__(self):
        self.current_version = "1.0.0"  # 当前版本
        self.update_url = "https://your-api.com/version/check"  # 版本检查API
        self.download_url = "https://your-server.com/download/"  # 更新包下载地址

    def check_update(self):
        """检查更新"""
        try:
            # 从服务器获取版本信息
            response = requests.get(self.update_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get('latest_version')
                update_info = data.get('update_info', '')
                force_update = data.get('force_update', False)

                if version.parse(latest_version) > version.parse(self.current_version):
                    return {
                        'has_update': True,
                        'latest_version': latest_version,
                        'current_version': self.current_version,
                        'update_info': update_info,
                        'force_update': force_update,
                        'download_url': data.get('download_url', self.download_url)
                    }

            return {'has_update': False}

        except Exception as e:
            print(f"版本检查失败: {e}")
            return {'has_update': False, 'error': str(e)}


class UpdateDialog(wx.Dialog):
    def __init__(self, parent, update_info):
        super(UpdateDialog, self).__init__(parent, title="发现新版本", size=(400, 300))
        self.update_info = update_info
        self.InitUI()
        self.Centre()

    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 版本信息
        version_text = f"当前版本: {self.update_info['current_version']}\n最新版本: {self.update_info['latest_version']}"
        version_label = wx.StaticText(panel, label=version_text)
        vbox.Add(version_label, flag=wx.ALL, border=10)

        # 更新内容
        update_label = wx.StaticText(panel, label="更新内容:")
        vbox.Add(update_label, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        update_content = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                     value=self.update_info['update_info'])
        vbox.Add(update_content, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        # 按钮区域
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        if not self.update_info.get('force_update', False):
            skip_btn = wx.Button(panel, label="稍后提醒")
            skip_btn.Bind(wx.EVT_BUTTON, self.OnSkip)
            btn_sizer.Add(skip_btn)

        update_btn = wx.Button(panel, label="立即更新")
        update_btn.Bind(wx.EVT_BUTTON, self.OnUpdate)
        btn_sizer.Add(update_btn, flag=wx.LEFT, border=5)

        vbox.Add(btn_sizer, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=10)

        panel.SetSizer(vbox)

    def OnSkip(self, event):
        self.EndModal(wx.ID_CANCEL)

    def OnUpdate(self, event):
        self.EndModal(wx.ID_OK)


class AutoUpdater:
    def __init__(self, main_window):
        self.main_window = main_window
        self.version_manager = VersionManager()

    def check_and_update(self, auto_check=False):
        """检查并处理更新"""
        # 显示检查更新对话框
        if not auto_check:
            dlg = wx.ProgressDialog("检查更新", "正在检查更新...", parent=self.main_window)
            dlg.Pulse()

        update_info = self.version_manager.check_update()

        if not auto_check:
            dlg.Destroy()

        if update_info.get('has_update'):
            self.show_update_dialog(update_info)
        elif not auto_check:
            wx.MessageBox("当前已是最新版本！", "提示", wx.OK | wx.ICON_INFORMATION)

    def show_update_dialog(self, update_info):
        """显示更新对话框"""
        dlg = UpdateDialog(self.main_window, update_info)
        result = dlg.ShowModal()

        if result == wx.ID_OK:
            self.download_and_update(update_info)
        dlg.Destroy()

    def download_and_update(self, update_info):
        """下载并更新"""
        # 实现下载逻辑
        download_url = update_info.get('download_url')
        wx.MessageBox(f"开始下载新版本: {update_info['latest_version']}", "更新", wx.OK)

        # 这里可以添加实际的下载逻辑
        # 例如使用urllib或requests下载更新包