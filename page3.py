from PyQt6 import QtWidgets


class Page3Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Page3Widget, self).__init__(parent)

        # 创建按钮和布局
        self.layout = QtWidgets.QVBoxLayout(self)
        self.button = QtWidgets.QPushButton("Page 3 Button")
        self.layout.addWidget(self.button)
