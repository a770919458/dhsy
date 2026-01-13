import wx
import FunView

class LoginDialog(wx.Dialog):
    def __init__(self, parent, title="登录"):
        super(LoginDialog, self).__init__(parent, title=title, size=(300, 200))
        self.InitUI()
        self.Centre()
        
    def InitUI(self):
        panel = wx.Panel(self)
        
        # 创建垂直布局盒子
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 用户名输入区域
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        username_label = wx.StaticText(panel, label="用户名:")
        self.username_text = wx.TextCtrl(panel, style=wx.TE_LEFT, value="admin")
        hbox1.Add(username_label, flag=wx.RIGHT, border=8)
        hbox1.Add(self.username_text, proportion=1)
        vbox.Add(hbox1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10, proportion=1)
        
        # 密码输入区域
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        password_label = wx.StaticText(panel, label="密    码:")
        self.password_text = wx.TextCtrl(panel, style=wx.TE_PASSWORD, value="123456")
        hbox2.Add(password_label, flag=wx.RIGHT, border=8)
        hbox2.Add(self.password_text, proportion=1)
        vbox.Add(hbox2, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10, proportion=1)
        
        # 按钮区域
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        register_btn = wx.Button(panel, label="注册")
        login_btn = wx.Button(panel, label="登录")
        hbox3.Add(register_btn)
        hbox3.Add(login_btn, flag=wx.LEFT, border=5)
        vbox.Add(hbox3, flag=wx.ALIGN_CENTER|wx.TOP|wx.BOTTOM, border=10, proportion=1)
        
        # 绑定按钮事件
        register_btn.Bind(wx.EVT_BUTTON, self.OnRegister)
        login_btn.Bind(wx.EVT_BUTTON, self.OnLogin)
        
        panel.SetSizer(vbox)
        
    def OnRegister(self, event):
        # 这里可以添加注册逻辑
        username = self.username_text.GetValue()
        password = self.password_text.GetValue()
        wx.MessageBox(f"注册功能\n用户名: {username}\n密码: {password}", "注册")
        
    def OnLogin(self, event):
        # 这里可以添加登录验证逻辑
        username = self.username_text.GetValue()
        password = self.password_text.GetValue()
        
        # 简单的验证示例
        if not username or not password:
            wx.MessageBox("请输入用户名和密码!", "错误", wx.OK | wx.ICON_ERROR)
            return
            
        # 这里应该是实际的登录验证逻辑
        if username == "admin" and password == "123456":
            # wx.MessageBox("登录成功!", "成功", wx.OK | wx.ICON_INFORMATION)
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("用户名或密码错误!", "错误", wx.OK | wx.ICON_ERROR)

class MainApp(wx.App):
    def OnInit(self):
        # 创建登录对话框
        dlg = LoginDialog(None)
        result = dlg.ShowModal()
        
        if result == wx.ID_OK:
            # 登录成功，显示主窗口
            frame = FunView.MainWindow()
            frame.Show()
            return True
        else:
            # 登录取消或失败，退出应用
            return False

if __name__ == "__main__":
    app = MainApp()
    app.MainLoop()