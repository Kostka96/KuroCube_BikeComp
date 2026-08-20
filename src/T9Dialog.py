from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt6.QtCore import Qt, QTimer
import time


class T9Dialog(QDialog):
    T9_MAP = {
        '1': ".,?!",
        '2': "ABC",
        '3': "DEF",
        '4': "GHI",
        '5': "JKL",
        '6': "MNO",
        '7': "PQRS",
        '8': "TUV",
        '9': "WXYZ",
        '*': "case",       # переключение регистра
        '0': " ",          # пробел
        '#': "backspace"   # удаление
    }

    def __init__(self, parent=None, initial_text=""):
        super().__init__(parent)
        self.setWindowTitle("Ввод текста")
        self.setModal(True)
        self.setFixedSize(400, 350)

        layout = QVBoxLayout()

        # Поле ввода
        self.input_field = QLineEdit(initial_text)
        self.input_field.setReadOnly(True)
        self.input_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_field.setStyleSheet(
            "font-size: 24px; padding: 10px; background-color: #222; color: #0f0; border: 1px solid #555; border-radius: 5px;"
        )
        layout.addWidget(self.input_field)

        # T9 сетка
        buttons = [
            ('1', '.,?!'), ('2', 'ABC'), ('3', 'DEF'),
            ('4', 'GHI'), ('5', 'JKL'), ('6', 'MNO'),
            ('7', 'PQRS'), ('8', 'TUV'), ('9', 'WXYZ'),
            ('*', 'ABC/abc'), ('0', 'SPACE'), ('#', 'BACK')
        ]

        grid_layout = QVBoxLayout()
        for i in range(0, len(buttons), 3):
            row = QHBoxLayout()
            for j in range(3):
                idx = i + j
                if idx < len(buttons):
                    num, letters = buttons[idx]
                    btn = QPushButton(f"{num}\n{letters}")
                    btn.setFixedSize(80, 60)
                    btn.setStyleSheet(
                        "font-size: 18px; font-weight: bold; border-radius: 10px; background-color: #333; color: white;"
                    )
                    btn.clicked.connect(self.handle_key(num))
                    row.addWidget(btn)
            grid_layout.addLayout(row)

        layout.addLayout(grid_layout)

        # Кнопки OK/Cancel
        bottom_row = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet("background-color: #a00; color: white; border-radius: 10px; padding: 10px;")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Готово")
        btn_ok.setStyleSheet("background-color: #0a0; color: white; border-radius: 10px; padding: 10px;")
        btn_ok.clicked.connect(self.accept)

        bottom_row.addWidget(btn_cancel)
        bottom_row.addWidget(btn_ok)
        layout.addLayout(bottom_row)

        self.setLayout(layout)

        # Логика T9
        self.current_text = initial_text
        self.last_key = None
        self.last_time = 0
        self.case_upper = True  # переключение регистра

    def handle_key(self, key):
        def handler():
            now = time.time()

            # BACKSPACE
            if key == '#':
                self.current_text = self.current_text[:-1]
                self.update_field()
                self.last_key = None
                return

            # SPACE
            if key == '0':
                self.current_text += " "
                self.update_field()
                self.last_key = None
                return

            # CASE SWITCH
            if key == '*':
                self.case_upper = not self.case_upper
                self.last_key = None
                return

            letters = self.T9_MAP.get(key, "")
            if not letters:
                return

            # Если нажата та же кнопка в течение 1 секунды → переключаем букву
            if self.last_key == key and (now - self.last_time) < 1.0:
                # заменяем последний символ
                last_char = self.current_text[-1] if self.current_text else ""
                idx = letters.find(last_char.upper())
                if idx != -1:
                    idx = (idx + 1) % len(letters)
                    new_char = letters[idx]
                    if not self.case_upper:
                        new_char = new_char.lower()
                    self.current_text = self.current_text[:-1] + new_char
                    self.update_field()
            else:
                # новая буква
                new_char = letters[0]
                if not self.case_upper:
                    new_char = new_char.lower()
                self.current_text += new_char
                self.update_field()

            self.last_key = key
            self.last_time = now

        return handler

    def update_field(self):
        self.input_field.setText(self.current_text)

    def get_text(self):
        return self.current_text
