from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt6.QtCore import Qt


class T9Dialog(QDialog):
    def __init__(self, parent=None, initial_text=""):
        super().__init__(parent)
        self.setWindowTitle("Ввод текста")
        self.setModal(True)  # Блокирует главное окно
        self.setFixedSize(400, 350)  # Фиксированный размер (под экран велокомпа)

        # Основной вертикальный слой
        layout = QVBoxLayout()

        # 1. Поле вывода вводимого текста
        self.input_field = QLineEdit(initial_text)
        self.input_field.setReadOnly(True)
        self.input_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_field.setStyleSheet(
            "font-size: 24px; padding: 10px; background-color: #222; color: #0f0; border: 1px solid #555; border-radius: 5px;")
        layout.addWidget(self.input_field)

        # 2. Сетка кнопок (T9 - 3x4)
        buttons = [
            ('1', ''), ('2', 'ABC'), ('3', 'DEF'),
            ('4', 'GHI'), ('5', 'JKL'), ('6', 'MNO'),
            ('7', 'PQRS'), ('8', 'TUV'), ('9', 'WXYZ'),
            ('*', ''), ('0', 'SPACE'), ('#', 'BACKSPACE')
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
                        "font-size: 18px; font-weight: bold; border-radius: 10px; background-color: #333; color: white;")
                    btn.clicked.connect(self.create_button_handler(num, letters))
                    row.addWidget(btn)
            grid_layout.addLayout(row)
        layout.addLayout(grid_layout)

        # 3. Кнопка подтверждения и отмены
        bottom_row = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet("background-color: #a00; color: white; border-radius: 10px; padding: 10px;")
        btn_cancel.clicked.connect(self.reject)  # Закрывает диалог с кодом 0

        btn_ok = QPushButton("Готово")
        btn_ok.setStyleSheet("background-color: #0a0; color: white; border-radius: 10px; padding: 10px;")
        btn_ok.clicked.connect(self.accept)  # Закрывает диалог с кодом 1

        bottom_row.addWidget(btn_cancel)
        bottom_row.addWidget(btn_ok)
        layout.addLayout(bottom_row)

        self.setLayout(layout)

        # Логика T9: Храним текущий набираемый текст
        self.current_text = initial_text
        self.last_pressed = None
        self.last_pressed_time = 0

    def create_button_handler(self, number, letters):
        """Создает функцию для обработки нажатия конкретной кнопки"""

        def handler():
            if number == '0':  # Пробел
                self.current_text += " "
                self.input_field.setText(self.current_text)
            elif number == '#':  # Backspace
                self.current_text = self.current_text[:-1]
                self.input_field.setText(self.current_text)
            elif letters:
                # Простейшая логика: добавляем букву. Для полноценного T9 нужно больше логики.
                self.current_text += letters[0]  # Для примера берем первую букву
                self.input_field.setText(self.current_text)

        return handler

    def get_text(self):
        """Возвращает введенный текст"""
        return self.current_text