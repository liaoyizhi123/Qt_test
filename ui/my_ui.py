# Form implementation generated from reading ui file 'my_ui.ui'
#
# Created by: PyQt6 UI code generator 6.4.2
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(814, 608)
        MainWindow.setStyleSheet("QFame{\n"
                                 "    border: none; /*将所有边框设置为无*/\n"
                                 "    background-color:#00000000;\n"
                                 "}\n"
                                 "#base_widget{ /*baseWidget*/\n"
                                 "    background-color: #f9f9f9;\n"
                                 "}\n"
                                 "#top_frame{ /*顶边栏*/\n"
                                 "    background-color: #f9f9f9;\n"
                                 "}\n"
                                 "#left_frame{\n"
                                 "    background-color: #f9f9f9;\n"
                                 "}\n"
                                 "#page_1{ /*stackedWidget*/\n"
                                 "    background-color: #282c34;\n"
                                 "}\n"
                                 "#page_2{ /*stackedWidget*/\n"
                                 "    background-color: lightgreen;\n"
                                 "}\n"
                                 "#page_3{ /*stackedWidget*/\n"
                                 "    background-color: #708cf1;\n"
                                 "}\n"
                                 "#page_4{ /*stackedWidget*/\n"
                                 "    background-color: #ffa135;\n"
                                 "}\n"
                                 "\n"
                                 "QLabel{\n"
                                 "    border: none; /*将所有边框设置为无*/\n"
                                 "    background-color:#00000000; /*所有的QLabel背景色为透明*/\n"
                                 "    color:#dfdfdf;\n"
                                 "}\n"
                                 "QPushButton{\n"
                                 "    border: none; /*将所有边框设置为无*/\n"
                                 "    /*color:#000000008*/ /*所有的QPushButton文字色为透明*/\n"
                                 "}\n"
                                 "QPushButton:hover {\n"
                                 "    background-color: #ececec; /*所有的QPushButton鼠标覆盖*/\n"
                                 "}\n"
                                 "QPushButton:pressed {\n"
                                 "    /*background-color: #9db6f9;*/ /*所有的QPushButton鼠标点击*/\n"
                                 "}\n"
                                 "QPushButton[spread=\"true\"] { /*当自定义特性spread=\"true\"*/\n"
                                 "    color: #dfdfdf;\n"
                                 "}\n"
                                 "#left_center QPushButton[selected=\"true\"] { /*当自定义特性selected=\"true\"*/\n"
                                 "    background-color: #282c34;\n"
                                 "    /*border: none; 先将所有边框设置为无*/\n"
                                 "    border-left: 3px solid qlineargradient(spread:pad, x1:0, y1:0.523, x2:0.971, y2:0.528682, stop:0.0511364 rgba(0, 255, 0, 255), stop:0.511364 rgba(0, 208, 0, 255), stop:0.988636 rgba(0, 179, 0, 255)); /*将左侧的边框单独显示为渐变色*/\n"
                                 "}\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "\n"
                                 "")
        self.base_widget = QtWidgets.QWidget(parent=MainWindow)
        self.base_widget.setObjectName("base_widget")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.base_widget)
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.app_frame = QtWidgets.QFrame(parent=self.base_widget)
        self.app_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.app_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.app_frame.setObjectName("app_frame")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.app_frame)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.top_frame = QtWidgets.QFrame(parent=self.app_frame)
        self.top_frame.setMinimumSize(QtCore.QSize(0, 50))
        self.top_frame.setMaximumSize(QtCore.QSize(16777215, 50))
        self.top_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_frame.setObjectName("top_frame")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.top_frame)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.top_left = QtWidgets.QFrame(parent=self.top_frame)
        self.top_left.setMinimumSize(QtCore.QSize(30, 30))
        self.top_left.setMaximumSize(QtCore.QSize(30, 30))
        self.top_left.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_left.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_left.setObjectName("top_left")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.top_left)
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.logo_image = QtWidgets.QLabel(parent=self.top_left)
        self.logo_image.setText("")
        self.logo_image.setPixmap(QtGui.QPixmap("../resources/icons/store.png"))
        self.logo_image.setScaledContents(True)
        self.logo_image.setObjectName("logo_image")
        self.verticalLayout_4.addWidget(self.logo_image)
        self.horizontalLayout.addWidget(self.top_left, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.top_center = QtWidgets.QFrame(parent=self.top_frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.top_center.sizePolicy().hasHeightForWidth())
        self.top_center.setSizePolicy(sizePolicy)
        self.top_center.setMinimumSize(QtCore.QSize(0, 50))
        self.top_center.setMaximumSize(QtCore.QSize(16777215, 50))
        self.top_center.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_center.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_center.setObjectName("top_center")
        self.verticalLayout_5 = QtWidgets.QVBoxLayout(self.top_center)
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.proj_title = QtWidgets.QLabel(parent=self.top_center)
        self.proj_title.setObjectName("proj_title")
        self.verticalLayout_5.addWidget(self.proj_title)
        self.horizontalLayout.addWidget(self.top_center)
        self.top_right = QtWidgets.QFrame(parent=self.top_frame)
        self.top_right.setMinimumSize(QtCore.QSize(200, 50))
        self.top_right.setMaximumSize(QtCore.QSize(200, 50))
        self.top_right.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.top_right.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.top_right.setObjectName("top_right")
        self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.top_right)
        self.verticalLayout_6.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_6.setSpacing(0)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.proj_date = QtWidgets.QLabel(parent=self.top_right)
        self.proj_date.setObjectName("proj_date")
        self.verticalLayout_6.addWidget(self.proj_date)
        self.horizontalLayout.addWidget(self.top_right, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        self.verticalLayout_2.addWidget(self.top_frame)
        self.content_box = QtWidgets.QFrame(parent=self.app_frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                           QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.content_box.sizePolicy().hasHeightForWidth())
        self.content_box.setSizePolicy(sizePolicy)
        self.content_box.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.content_box.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.content_box.setObjectName("content_box")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.content_box)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.left_frame = QtWidgets.QFrame(parent=self.content_box)
        self.left_frame.setMinimumSize(QtCore.QSize(0, 0))
        self.left_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_frame.setObjectName("left_frame")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.left_frame)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.left_top = QtWidgets.QFrame(parent=self.left_frame)
        self.left_top.setMinimumSize(QtCore.QSize(50, 50))
        self.left_top.setMaximumSize(QtCore.QSize(16777215, 50))
        self.left_top.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_top.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_top.setObjectName("left_top")
        self.verticalLayout_7 = QtWidgets.QVBoxLayout(self.left_top)
        self.verticalLayout_7.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_7.setSpacing(0)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.btn_left_toggle = QtWidgets.QPushButton(parent=self.left_top)
        self.btn_left_toggle.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_left_toggle.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_left_toggle.setText("")
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("../resources/icons/cat.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_left_toggle.setIcon(icon)
        self.btn_left_toggle.setIconSize(QtCore.QSize(32, 32))
        self.btn_left_toggle.setAutoRepeatInterval(100)
        self.btn_left_toggle.setObjectName("btn_left_toggle")
        self.verticalLayout_7.addWidget(self.btn_left_toggle)
        self.verticalLayout.addWidget(self.left_top)
        self.left_center = QtWidgets.QFrame(parent=self.left_frame)
        self.left_center.setMinimumSize(QtCore.QSize(50, 0))
        self.left_center.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_center.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_center.setObjectName("left_center")
        self.verticalLayout_8 = QtWidgets.QVBoxLayout(self.left_center)
        self.verticalLayout_8.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_8.setSpacing(0)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.btn_lef_home = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_home.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_home.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_home.setText("")
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap("../resources/icons/note.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_home.setIcon(icon1)
        self.btn_lef_home.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_home.setObjectName("btn_lef_home")
        self.verticalLayout_8.addWidget(self.btn_lef_home)
        self.btn_lef_new = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_new.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_new.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_new.setText("")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap("../resources/icons/media.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_new.setIcon(icon2)
        self.btn_lef_new.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_new.setObjectName("btn_lef_new")
        self.verticalLayout_8.addWidget(self.btn_lef_new)
        self.btn_lef_save = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_save.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_save.setMaximumSize(QtCore.QSize(16777215, 50))
        icon3 = QtGui.QIcon()
        icon3.addPixmap(QtGui.QPixmap("../resources/icons/flower.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_save.setIcon(icon3)
        self.btn_lef_save.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_save.setObjectName("btn_lef_save")
        self.verticalLayout_8.addWidget(self.btn_lef_save)
        self.btn_lef_exit = QtWidgets.QPushButton(parent=self.left_center)
        self.btn_lef_exit.setMinimumSize(QtCore.QSize(0, 50))
        self.btn_lef_exit.setMaximumSize(QtCore.QSize(16777215, 50))
        self.btn_lef_exit.setText("")
        icon4 = QtGui.QIcon()
        icon4.addPixmap(QtGui.QPixmap("../resources/icons/like.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.btn_lef_exit.setIcon(icon4)
        self.btn_lef_exit.setIconSize(QtCore.QSize(32, 32))
        self.btn_lef_exit.setObjectName("btn_lef_exit")
        self.verticalLayout_8.addWidget(self.btn_lef_exit)
        self.verticalLayout.addWidget(self.left_center, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.left_bottom = QtWidgets.QFrame(parent=self.left_frame)
        self.left_bottom.setMinimumSize(QtCore.QSize(50, 50))
        self.left_bottom.setMaximumSize(QtCore.QSize(16777215, 50))
        self.left_bottom.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.left_bottom.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.left_bottom.setObjectName("left_bottom")
        self.verticalLayout.addWidget(self.left_bottom)
        self.horizontalLayout_2.addWidget(self.left_frame)
        self.main_content = QtWidgets.QFrame(parent=self.content_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.main_content.sizePolicy().hasHeightForWidth())
        self.main_content.setSizePolicy(sizePolicy)
        self.main_content.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.main_content.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.main_content.setObjectName("main_content")
        self.verticalLayout_9 = QtWidgets.QVBoxLayout(self.main_content)
        self.verticalLayout_9.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_9.setSpacing(0)
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.stackedWidget = QtWidgets.QStackedWidget(parent=self.main_content)
        self.stackedWidget.setObjectName("stackedWidget")
        self.page_1 = QtWidgets.QWidget()
        self.page_1.setObjectName("page_1")
        self.stackedWidget.addWidget(self.page_1)
        self.page_3 = QtWidgets.QWidget()
        self.page_3.setObjectName("page_3")
        self.stackedWidget.addWidget(self.page_3)
        self.page_4 = QtWidgets.QWidget()
        self.page_4.setObjectName("page_4")
        self.stackedWidget.addWidget(self.page_4)
        self.page_2 = QtWidgets.QWidget()
        self.page_2.setObjectName("page_2")
        self.stackedWidget.addWidget(self.page_2)
        self.verticalLayout_9.addWidget(self.stackedWidget)
        self.horizontalLayout_2.addWidget(self.main_content)
        self.verticalLayout_2.addWidget(self.content_box)
        self.verticalLayout_3.addWidget(self.app_frame)
        MainWindow.setCentralWidget(self.base_widget)

        self.retranslateUi(MainWindow)
        self.stackedWidget.setCurrentIndex(3)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.proj_title.setText(_translate("MainWindow", "Title"))
        self.proj_date.setText(_translate("MainWindow", "Date"))