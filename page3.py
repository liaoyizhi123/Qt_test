import random
import string
from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox, QHBoxLayout
)

class Page3Widget(QWidget):
    def __init__(self, parent=None):
        super(Page3Widget, self).__init__(parent)
        # Enable keyboard focus
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        # Default parameters
        self.n = 2
        self.trials = 20
        self.delay = 2.0  # seconds

        # State
        self.sequence = []
        self.current_index = 0
        self.correct_count = 0
        self.response_allowed = False

        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Settings
        self.settings_widget = QWidget()
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        form_layout = QFormLayout()
        form_layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.n_spin = QSpinBox(); self.n_spin.setRange(1, 10); self.n_spin.setValue(self.n)
        self.trials_spin = QSpinBox(); self.trials_spin.setRange(1, 100); self.trials_spin.setValue(self.trials)
        self.delay_spin = QDoubleSpinBox(); self.delay_spin.setRange(0.1, 10.0); self.delay_spin.setSingleStep(0.1); self.delay_spin.setValue(self.delay)
        form_layout.addRow("N value:", self.n_spin)
        form_layout.addRow("Trials:", self.trials_spin)
        form_layout.addRow("Delay (s):", self.delay_spin)
        self.start_button = QPushButton("Start N-Back")
        self.start_button.clicked.connect(self.start_experiment)
        settings_layout.addLayout(form_layout)
        settings_layout.addWidget(self.start_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.settings_widget)

        # Summary
        self.summary_widget = QWidget()
        summary_layout = QFormLayout(self.summary_widget)
        summary_layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.n_display_label = QLabel(); self.trials_display_label = QLabel(); self.delay_display_label = QLabel()
        summary_layout.addRow("N value:", self.n_display_label)
        summary_layout.addRow("Trials:", self.trials_display_label)
        summary_layout.addRow("Delay (s):", self.delay_display_label)
        self.summary_widget.hide()
        self.main_layout.addWidget(self.summary_widget)

        # Stimulus
        self.stimulus_label = QLabel("")
        font = self.stimulus_label.font(); font.setPointSize(48)
        self.stimulus_label.setFont(font)
        self.stimulus_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stimulus_label.hide()
        self.main_layout.addWidget(self.stimulus_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # Buttons
        self.button_container = QWidget(); self.button_container.setMinimumHeight(80)
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.yes_button = QPushButton("Yes"); self.no_button = QPushButton("No")
        self.yes_button.setCheckable(True); self.no_button.setCheckable(True)
        btn_ss = (
            "QPushButton { background-color: #4caf50; color: white; border: none; padding: 10px; }"
            "QPushButton:checked { background-color: #388e3c; }"
            "QPushButton:disabled { background-color: gray; }"
        )
        self.yes_button.setStyleSheet(btn_ss); self.no_button.setStyleSheet(btn_ss)
        self.yes_button.clicked.connect(lambda: self.record_response(True))
        self.no_button.clicked.connect(lambda: self.record_response(False))
        self.yes_button.hide(); self.no_button.hide()
        self.button_layout.addWidget(self.yes_button); self.button_layout.addWidget(self.no_button)
        self.main_layout.addWidget(self.button_container)

        # Feedback
        self.feedback_label = QLabel("")
        fb_font = self.feedback_label.font(); fb_font.setPointSize(18)
        self.feedback_label.setFont(fb_font)
        self.feedback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setFixedHeight(24)
        self.feedback_label.hide()
        self.main_layout.addWidget(self.feedback_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.isAutoRepeat():
            return
        if self.response_allowed and self.current_index >= self.n and self.current_index < self.trials:
            if event.key() == QtCore.Qt.Key.Key_Left and self.yes_button.isEnabled():
                self.response_allowed = False
                self.yes_button.click()
                event.accept()
                return
            if event.key() == QtCore.Qt.Key.Key_Right and self.no_button.isEnabled():
                self.response_allowed = False
                self.no_button.click()
                event.accept()
                return
        super().keyPressEvent(event)

    def enable_response(self):
        self.response_allowed = True
        self.yes_button.setEnabled(True)
        self.no_button.setEnabled(True)

    def start_experiment(self):
        self.n = self.n_spin.value(); self.trials = self.trials_spin.value(); self.delay = self.delay_spin.value()
        self.settings_widget.hide()
        self.n_display_label.setText(str(self.n)); self.trials_display_label.setText(str(self.trials)); self.delay_display_label.setText(str(self.delay))
        self.summary_widget.show()
        self.sequence = [random.choice(string.ascii_uppercase) for _ in range(self.trials)]
        self.current_index = 0; self.correct_count = 0
        self.show_next_stimulus(); self.setFocus()

    def show_next_stimulus(self):
        # Reset for each trial
        self.response_allowed = False
        self.yes_button.setChecked(False); self.no_button.setChecked(False)
        self.yes_button.setEnabled(False); self.no_button.setEnabled(False)
        self.feedback_label.hide()
        if self.current_index >= self.trials:
            return self.end_experiment()
        self.stimulus_label.setText(self.sequence[self.current_index]); self.stimulus_label.show()
        if self.current_index >= self.n:
            self.yes_button.show(); self.no_button.show()
            # enable in next event loop to clear buffered keys
            QtCore.QTimer.singleShot(0, self.enable_response)
        else:
            QtCore.QTimer.singleShot(int(self.delay * 1000), self.advance_trial)

    def record_response(self, user_says_match: bool):
        correct = (self.sequence[self.current_index] == self.sequence[self.current_index - self.n])
        if user_says_match == correct:
            self.stimulus_label.setStyleSheet("color: #4caf50;")
            self.correct_count += 1
        else:
            self.stimulus_label.setStyleSheet("color: #f44336;")
        self.yes_button.setChecked(user_says_match); self.no_button.setChecked(not user_says_match)
        self.yes_button.setEnabled(False); self.no_button.setEnabled(False)
        QtCore.QTimer.singleShot(int(self.delay * 1000), self.advance_trial)

    def advance_trial(self):
        self.stimulus_label.setStyleSheet("color: black;")
        self.current_index += 1
        self.show_next_stimulus()

    def end_experiment(self):
        self.stimulus_label.hide(); self.yes_button.hide(); self.no_button.hide(); self.summary_widget.hide()
        total = max(0, self.trials - self.n)
        msg = QMessageBox(self); msg.setWindowTitle("N-Back Results"); msg.setText(f"Your score: {self.correct_count} / {total}"); msg.exec()
        self.settings_widget.show(); self.stimulus_label.clear()

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = Page3Widget(); w.show(); sys.exit(app.exec())
