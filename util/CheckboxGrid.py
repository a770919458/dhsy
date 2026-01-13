import wx
import wx.grid as gridlib


class CheckboxRenderer(gridlib.GridCellRenderer):
    def __init__(self):
        super(CheckboxRenderer, self).__init__()
        self.size = wx.Size(16, 16)  # 复选框大小

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        # 设置背景色
        if isSelected:
            dc.SetBrush(wx.Brush(wx.Colour(200, 220, 255)))
        else:
            dc.SetBrush(wx.Brush(attr.GetBackgroundColour()))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        # 绘制复选框
        value = grid.GetCellValue(row, col)
        checked = value == "1"

        # 计算复选框位置（居中）
        checkbox_rect = wx.Rect(
            rect.x + (rect.width - self.size.width) // 2,
            rect.y + (rect.height - self.size.height) // 2,
            self.size.width,
            self.size.height
        )

        # 绘制复选框边框
        dc.SetPen(wx.Pen(wx.BLACK, 1))
        dc.SetBrush(wx.Brush(wx.WHITE))
        dc.DrawRectangle(checkbox_rect)

        # 如果选中，绘制勾选标记
        if checked:
            dc.SetPen(wx.Pen(wx.BLUE, 2))
            dc.DrawLine(checkbox_rect.x + 3, checkbox_rect.y + 7,
                        checkbox_rect.x + 6, checkbox_rect.y + 10)
            dc.DrawLine(checkbox_rect.x + 6, checkbox_rect.y + 10,
                        checkbox_rect.x + 12, checkbox_rect.y + 4)

    def GetBestSize(self, grid, attr, dc, row, col):
        return self.size

    def Clone(self):
        return CheckboxRenderer()


class CheckboxGrid(gridlib.Grid):
    def __init__(self, parent):
        super(CheckboxGrid, self).__init__(parent)
        self.checkbox_column = 0  # 第一列为复选框列
        self.selected_rows = set()  # 存储选中的行
        self.checkbox_renderer = CheckboxRenderer()

    def CreateGrid(self, num_rows, num_cols, selmode=gridlib.Grid.SelectCells):
        # 调用父类方法创建网格，但额外增加一列用于复选框
        result = super(CheckboxGrid, self).CreateGrid(num_rows, num_cols + 1, selmode)
        if result:
            # 设置第一列为复选框列
            self.SetColLabelValue(0, "选择")
            self.SetColSize(0, 60)  # 设置复选框列宽度

            # 设置其他列标题
            headers = ["窗口", "角色名字", "种族", "等级", "状态", "运行任务", "队伍信息", "角色银两"]
            for col, header in enumerate(headers):
                self.SetColLabelValue(col + 1, header)
                self.SetColSize(col + 1, 110)

            # 绑定点击事件
            self.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.OnCellLeftClick)
            self.Bind(gridlib.EVT_GRID_LABEL_LEFT_CLICK, self.OnLabelLeftClick)

            # 设置网格属性
            self.EnableEditing(False)
            self.SetSelectionMode(gridlib.Grid.GridSelectRows)
        return result

    def OnCellLeftClick(self, event):
        """处理单元格点击事件"""
        row, col = event.GetRow(), event.GetCol()

        # 如果点击的是复选框列（第一列）
        if col == self.checkbox_column:
            # 切换复选框状态
            current_value = self.GetCellValue(row, col)
            new_value = "0" if current_value == "1" else "1"
            self.SetCellValue(row, col, new_value)

            # 更新选择集合
            if new_value == "1":
                self.selected_rows.add(row)
            else:
                self.selected_rows.discard(row)

            # 更新行外观
            self.UpdateRowAppearance(row)
            self.ForceRefresh()  # 强制刷新显示

        event.Skip()

    def OnLabelLeftClick(self, event):
        """处理列标签点击事件（全选/取消全选）"""
        rows = self.GetNumberRows()
        if len(self.selected_rows) == rows:
            # 取消全选
            for row in range(rows):
                self.SetCellValue(row, self.checkbox_column, "0")
                if row in self.selected_rows:
                    self.selected_rows.remove(row)
        else:
            # 全选
            for row in range(rows):
                self.SetCellValue(row, self.checkbox_column, "1")
                self.selected_rows.add(row)

        self.UpdateRowAppearanceAll()

    def ToggleRowSelection(self, row):
        """切换单行选择状态"""
        if row in self.selected_rows:
            self.selected_rows.remove(row)
            self.SetCellValue(row, self.checkbox_column, "")  # 清空复选框
        else:
            self.selected_rows.add(row)
            self.SetCellValue(row, self.checkbox_column, "✓")  # 显示勾选标记

        # 更新单元格背景色以提供视觉反馈
        self.UpdateRowAppearance(row)

    def ToggleSelectAll(self):
        """全选/取消全选"""
        rows = self.GetNumberRows()

        if len(self.selected_rows) == rows:
            # 取消全选
            self.selected_rows.clear()
            for row in range(rows):
                self.SetCellValue(row, self.checkbox_column, "")
                self.UpdateRowAppearance(row)
        else:
            # 全选
            self.selected_rows = set(range(rows))
            for row in range(rows):
                self.SetCellValue(row, self.checkbox_column, "✓")
                self.UpdateRowAppearance(row)

    def UpdateRowAppearance(self, row):
        """更新行的外观"""
        is_selected = row in self.selected_rows
        color = wx.Colour(240, 245, 255) if is_selected else wx.WHITE

        for col in range(self.GetNumberCols()):
            self.SetCellBackgroundColour(row, col, color)

        self.ForceRefresh()

    def UpdateRowAppearanceAll(self):
        """更新所有行外观"""
        for row in range(self.GetNumberRows()):
            self.UpdateRowAppearance(row)
        self.ForceRefresh()

    def GetSelectedRows(self):
        """获取选中的行索引列表"""
        return sorted(list(self.selected_rows))

    def SelectAll(self):
        """全选"""
        self.ToggleSelectAll()

    def ClearSelection(self):
        """清空选择"""
        self.selected_rows.clear()
        rows = self.GetNumberRows()
        for row in range(rows):
            self.SetCellValue(row, self.checkbox_column, "")
            self.UpdateRowAppearance(row)