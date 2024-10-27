from PyQt6 import QtWidgets


class Page4Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Page4Widget, self).__init__(parent)

        # 创建按钮和布局
        self.layout = QtWidgets.QVBoxLayout(self)
        self.button = QtWidgets.QPushButton("Page 4 Button")
        self.layout.addWidget(self.button)
