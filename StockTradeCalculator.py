"""Stock Trade Profit Calculator. AYANYEMI WURAOLUWA 3154816
This program calculates the profit or loss from a stock trade based on historical prices from the already supplied csv file.
"""

import csv 
import sys
from bisect import bisect_right #Helps with finding positions in the already sorted csv file
from datetime import date, datetime, timedelta 
from decimal import Decimal, InvalidOperation # For decimal calculations
from dataclasses import dataclass # Creating classes
from pathlib import Path #File directory interactions


from PyQt6.QtCore import QDate, QPointF, QRectF, Qt #Dates, floating point and constants for the GUI
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextCharFormat # Painting used for the chart and calendar
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent # Used find the styling (.qss file) and csv file
COLORS = { # Color palette for the chart and some gui elements
    "background": "#1e1018",
    "text": "#f7ebf0",
    "muted": "#bf9da9",
    "border": "#513745",
    "primary": "#fa95bf",
    "gain": "#68dba0",
    "loss": "#f16c70",
}


@dataclass(frozen=True) # A single price point in the historical data from the csv file. Frozen = True means the object is immutable after creation for safety
class Price:
    date: date
    price: Decimal


@dataclass(frozen=True) # The group of results for every calculation done
class Trade:
    buy: Price
    sell: Price
    cost: Decimal
    value: Decimal
    profit: Decimal
    percent: Decimal


def parse_date(value): #Reading the dates from the csv file, accepts - and / separators, removes whitespace, parses day-first format, returns a functional date.
    return datetime.strptime(value.strip().replace("-", "/"), "%d/%m/%Y").date()


def load_data(csv_path): # Reads the csv file and returns a dictionary of positive stock and their historical prices. Error handling (valueError)is available if the csv is not formatted correctly or contains no usable data.
    data = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or reader.fieldnames[0] != "Date": #The first column of the CSV must be a Date column, the rest are stock names
            raise ValueError("The first column of the CSV must be a Date column.")
        names = reader.fieldnames[1:]
        if not names:
            raise ValueError("The CSV contains no stock columns.")

        for line, row in enumerate(reader, start=2): # Parsing the date per row, starts at line 2 because line 1 is the header. 
            try:
                day = parse_date(row.get("Date", ""))
            except ValueError as error:
                raise ValueError(
                    f"Invalid date on CSV line {line}. Expected day/month/year."
                ) from error
            
            for name in names: # Iterates through the positive stock names and parses the price for each stock on that date. If the price is invalid or negative, it is skipped.
                raw = (row.get(name) or "").strip().replace(",", "")
                if not raw:
                    continue
                try:
                    price = Decimal(raw)
                except InvalidOperation as error:
                    raise ValueError(
                        f"Invalid price for {name} on CSV line {line}."
                    ) from error
                if price.is_finite() and price > 0:
                    data.setdefault(name, {})[day] = price

    result = { # The result is a sorted list of stock names and their historical prices, sorted by date, with error handling in place. 
        name: [Price(day, price) for day, price in sorted(rows.items())]
        for name, rows in data.items() if rows #Bisect_Right uses this list
    }
    if not result:
        raise ValueError("The CSV contains no usable stock data.")
    return result


def price_on(series, day): # Binary Search for the latest price on or before the selected day.
    index = bisect_right([point.date for point in series], day) - 1
    if index < 0:
        raise ValueError("No price is available on or before the selected date.")
    return series[index]


def calculate(series, quantity, buy_date, sell_date): # Calculate cost, sell value, profit &loss and the percentage difference. Error handling in place for invalid quantity, sell date before buy date and dates outside the available price history in the new sorted list.
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1: # Validate the quantity input, rejects non-integer, boolean and negative values.
        raise ValueError("Enter a positive whole number greater than 0.")
    # Validating the sell date is on or after the buy date, and that both dates are within the available price history.
    if sell_date < buy_date:
        raise ValueError("The sell date must be on or after the purchase date.")
    if not series or buy_date < series[0].date or sell_date > series[-1].date:
        raise ValueError("Choose dates within the available price history.")

# Actual arithmetic calculations for the stock trade
    buy, sell = price_on(series, buy_date), price_on(series, sell_date)
    cost, value = buy.price * quantity, sell.price * quantity
    profit = value - cost
    return Trade(buy, sell, cost, value, profit, profit / cost * 100)


def compare(data, quantity, buy_date, sell_date): # Rank these trade assets by percentage return (in descending order), skipping unavailable date ranges.
    rows = []
    for name, series in data.items():
        try:
            rows.append((name, calculate(series, quantity, buy_date, sell_date)))
        except ValueError:
            continue
    return sorted(rows, key=lambda row: row[1].percent, reverse=True)

def money(value): # Currency formatting (the currency sign comes before the numbers), with commas as >= thousands separators, two decimal places, and a minus sign for negative values.
    return ("-" if value < 0 else "") + f"${abs(value):,.2f}"

def display_name(name): # Readable name for the stock, replacing the underscores with spaces.
    return name.replace("_", " ")

def qdate(day):# Converts the Python format date to a QDate for usability
    return QDate(day.year, day.month, day.day)


class Stat(QFrame): # The card on which all the results are displayed. The 3 elements (title, value, subtext) are vertically stacked
    def __init__(self, title):
        super().__init__()
        self.setObjectName("stat")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        self.title = QLabel(title)
        self.title.setObjectName("statTitle")
        self.value = QLabel("—")
        self.value.setObjectName("value")
        self.sub = QLabel("")
        self.sub.setWordWrap(True)
        self.sub.setObjectName("statSub")
        for widget in (self.title, self.value, self.sub):
            layout.addWidget(widget)

    def set_result(self, title, value, sub, tone=None): # Updates the card with the new results, and applies a color to the value if specified (gain/loss)
        self.title.setText(title)
        self.value.setText(value)
        self.value.setObjectName(tone or "value")
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)
        self.sub.setText(sub)


class PriceChart(QWidget): # A custom-painted historical trade chart with trade markers and price tooltips.
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.setAccessibleName("Historical stock price chart")
        self.series = []
        self.trade = None
        self.positions = []

    def set_data(self, series, trade): # Triggers new styling of the chart when there is new data to display. Also updates the accessible description for screen readers to describe the new data.
        self.series = series 
        self.trade = trade 
        self.setAccessibleDescription("Historical prices; Bought and Sold mark the trade dates.")
        self.update()

    def paintEvent(self, event): # Paints the chart, axes, gridlines, price points, and trade markers. Uses the COLORS palette for styling.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing) # Anti-aliasing for smoother lines and shapes
        plot = QRectF( 90, 42, max(1, self.width() - 140), max(1, self.height() - 100) )
        painter.fillRect(self.rect(), QColor(COLORS["background"]))
        if not self.series: # If there is no data to show,a message prompts the user to choose valid details.
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Choose valid trade details to view prices.",)
            return

        low = min(float(point.price) for point in self.series) # Calculates the lowest and highest prices in the series to determine the y-axis range for the chart. Padding ensures the chart is visually clear and not cramped at each edge.
        high = max(float(point.price) for point in self.series)
        padding = (high - low) * 0.12 or max(high * 0.05, 1)
        low, high = low - padding, high + padding
        first, last = self.series[0].date, self.series[-1].date # Calculates the total number of days in the series to determine the x-axis range for the chart. Ensures that there is at least one day to avoid division by zero errors.
        days = max((last - first).days, 1)
        self.positions = [
            (QPointF(plot.left() + (point.date - first).days / days * plot.width(), plot.bottom()- (float(point.price) - low) / (high - low) * plot.height(), ), point, )
            for point in self.series
        ]

        for index in range(5): # Draws horizontal grid lines and labels for the y-axis, representing price levels. The lines are drwan with dashes and the labels are aligned to the right side of the chart.
            y = plot.top() + index / 4 * plot.height()
            painter.setPen(QPen(QColor(COLORS["border"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(QRectF(0, y - 10, 82, 20),Qt.AlignmentFlag.AlignRight,money(high - index / 4 * (high - low)),)
        for index in range(4): # Draws vertical grid lines and labels for the x-axis, representing dates. The lines are drawn with dashes and the labels are centered below the chart.
            day = first + timedelta(days=round(days * index / 3))
            x = plot.left() + index / 3 * plot.width()
            painter.drawText(QRectF(x - 55, plot.bottom() + 14, 110, 22),Qt.AlignmentFlag.AlignCenter,day.strftime("%d %b %Y"),)

        line = QPainterPath(self.positions[0][0]) # Draws the line connecting the price points on the chart, using the positions calculation. line is drawn with a primary color 
        for position, _ in self.positions[1:]:
            line.lineTo(position)
        painter.setPen(QPen(QColor(COLORS["primary"]), 2))
        painter.drawPath(line)

        if self.trade: # Drawing the symbols for the buy and sell points on the chart, gain and loss have different colors. If buy and sell are on the same day, only one symbol is drawn with a combined label.
            same_day = self.trade.buy.date == self.trade.sell.date
            markers = [
                (self.trade.buy,"Bought / Sold" if same_day else "Bought", COLORS["text"], )
            ]
            if not same_day:
                markers.append(
                    ( self.trade.sell, "Sold",COLORS["gain"] if self.trade.profit >= 0 else COLORS["loss"],)
                )
            for point, text, color in markers: # The tooltip is a filled dot with a label above it.
                for position, price in self.positions:
                    if price.date == point.date:
                        painter.setPen(QPen(QColor(color), 1))
                        painter.setBrush(QColor(color))
                        painter.drawEllipse(position, 5, 5)
                        label_x = max(plot.left(),min(position.x() - 48, plot.right() - 100),)
                        painter.drawText(QRectF(label_x, position.y() - 30, 100, 22),Qt.AlignmentFlag.AlignCenter, text,)
                        break

    def mouseMoveEvent(self, event): # When the mouse hovers over the chart, a tooltip with the date and price of the nearest price point is displayed.
        if self.positions:
            _, point = min(self.positions,key=lambda row: abs(row[0].x() - event.position().x()),)
            QToolTip.showText(event.globalPosition().toPoint(),f"{point.date:%d %b %Y}: {money(point.price)}",self, QRectF(self.positions[0][0], self.positions[-1][0]).toRect(),)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event): # The tooltip is hidden/ disappears when the mouse leaves the chart area.
        QToolTip.hideText()
        super().leaveEvent(event)


'''Provides the following functionalities have been provided:

    - Allows the selection of the stock to be purchased
    - Allows the selection of the quantity to be purchased
    - Allows the selection of the purchase date
    - Displays the purchase total
    - Allows the selection of the sell date
    - Displays the sell total
    - Displays the profit total
    '''
class StockTradeProfitCalculator(QDialog): # This is the main window that controls the calculations itself, the controls are connected to one update method.
    def __init__(self):
        super().__init__()
        csv_path = ROOT / "Stock_Market_Dataset.csv" # Loads csv data
        try:
            self.data = load_data(csv_path) # setting up the dictionary of Stocks
        except (OSError, csv.Error, ValueError) as error: # Error handling for the CSV file, if it cannot be opened or read, a critical message box is displayed to the user with instructions to put the CSV file beside the StockTradeCalculator.py file.
            QMessageBox.critical(self,"Could not load stock information",f"Read Stock_Market_Dataset.csv file beside StockTradeCalculator.py.\n\n{error}", )
            raise SystemExit(1) from error
        self.setWindowTitle("Stock Trade Profit Calculator") # Windows setup
        self.resize(1080, 860)
        self.setMinimumSize(720, 600)
        self.setStyleSheet((ROOT / "styles.qss").read_text(encoding="utf-8"))
        self._updating = False # This prevents recursive signal loopswhen updating the UI
        self.result = None
        self.comparison_rows = []
        self._build_view()
        self._connect_signals()
        self.reset()

    def _build_view(self): # Building the GUI layout, ensures that it can fit on different screens, cause there is a scrollable area. Ease of navigation has been considered
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        brand = QLabel("▲ Stocktrade") # Headers
        brand.setObjectName("brand")
        layout.addWidget(brand)
        title = QLabel("Stock Trade Profit Calculator")
        title.setObjectName("heading")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.history = QLabel()
        self.history.setObjectName("muted")
        layout.addWidget(self.history)

        grid = QGridLayout() # The grid layout is used to arrange the input controls (stock selection, quantity, purchase date, sell date) in a structured manner. Each control has an associated label and tooltip for user guidance. The grid layout allows for a clean and organized presentation of the input fields, making it easier for users to interact with the application.
        grid.setHorizontalSpacing(18)
        self.stock = QComboBox()
        for name in self.data:
            self.stock.addItem(display_name(name), name)
        self.quantity = QSpinBox() # Integer input has enough range, up to a billion. The commas are factored into display for readability. Keyboard input is not tracked till the user leaves the field.
        self.quantity.setRange(1, 1_000_000_000)
        self.quantity.setGroupSeparatorShown(True)
        self.quantity.setKeyboardTracking(False)
        self.buy_date, self.sell_date = QDateEdit(), QDateEdit() # Date selectors with popup calendars
        for editor in (self.buy_date, self.sell_date):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd MMM yyyy")
            editor.setKeyboardTracking(False)

        fields = [ # In form of a two column layout, the labels and controls are arranged in pairs.
            ("Stock", self.stock, "Choose a stock, crypto or commodity."),
            ("Quantity",self.quantity,"Enter a whole number of units, at least 1.",),
            ("Purchase date",self.buy_date,"Closed market days use the previous available trading day.",),
            ("Sell date",self.sell_date,"Choose a day on or after purchase; closed days use the previous trading day. Selecting a year only navigates the calendar, so click a day to apply it.", ),
        ]
        for index, (name, widget, tip) in enumerate(fields): # The labels are created with an information icon (ⓘ) that provides details about the corresponding field when hovered over.
            label = QLabel(name + "  ⓘ")
            label.setObjectName("fieldLabel")
            label.setToolTip(tip)
            label.setBuddy(widget)
            widget.setToolTip(tip)
            widget.setAccessibleName(name)
            row, column = divmod(index, 2)
            grid.addWidget(label, row * 2, column)
            grid.addWidget(widget, row * 2 + 1, column)
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        range_grid = QGridLayout() # The range buttons are created to allow users to quickly set the purchase date relative to the sell date. The reset button restores the default settings
        self.range_buttons = {}
        ranges = [
            ("1 week", 7),("2 weeks", 14),("1 month", 30),("6 months", 182),("1 year", 365),("All time", None),
        ]
        for index, (name, days) in enumerate(ranges):
            button = QPushButton(name)
            button.setToolTip("Set purchase date relative to the sell date."
            if days
                else "Use the earliest available purchase date."
            )
            button.clicked.connect(lambda checked=False, duration=days: self.apply_range(duration) )
            range_grid.addWidget(button, 1 + index // 3, index % 3)
            self.range_buttons[name] = button
        self.reset_button = QPushButton("↺ Reset")
        self.reset_button.setObjectName("reset")
        self.reset_button.setToolTip("Restore Amazon, 10 units and the latest two weeks." )
        range_grid.addWidget(self.reset_button, 3, 0, 1, 3)
        layout.addLayout(range_grid)

        self.error = QLabel() # The error label is used to display validation messages when the user inputs invalid data or selects dates outside the available price history.
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.setAccessibleName("Trade validation message")
        self.error.hide()
        layout.addWidget(self.error)

        stats = QHBoxLayout() # Three result cards are produced to display the purchase total, sell total, and profit/loss.
        self.cost = Stat("Purchase total")
        self.sale = Stat("Sell total")
        self.profit = Stat("Profit")
        for stat in (self.cost, self.sale, self.profit):
            stats.addWidget(stat, 1)
        layout.addLayout(stats)

        self.tabs = QTabWidget() # The tab widget is used to switch between the price chart and the comparison table. The price chart displays the historical prices for the selected stock, while the comparison table ranks all stocks by percentage change for the selected quantity and date range.
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.chart = PriceChart()
        self.tabs.addTab(self.chart, "Price chart")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Stock", "Change", "Profit / Loss", "Price dates used"]
        )
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setMinimumHeight(330)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAccessibleName("All stocks ranked by percentage change")
        self.table.setToolTip(
            "Select a row to calculate that stock using your current quantity and dates."
        )
        self.tabs.addTab(self.table, "Compare all stocks")
        layout.addWidget(self.tabs)
        layout.addStretch()

    def _connect_signals(self): # Connects the signals from the input controls to the appropriate methods that handle the updates to the UI. 
        self.stock.currentIndexChanged.connect(self.stock_changed)
        self.quantity.valueChanged.connect(self.update_ui)
        self.quantity.lineEdit().textEdited.connect(self.update_ui)
        self.buy_date.dateChanged.connect(self.update_ui)
        self.sell_date.dateChanged.connect(self.update_ui)
        self.reset_button.clicked.connect(self.reset)
        self.table.cellClicked.connect(self.select_comparison)
        self.table.cellActivated.connect(self.select_comparison)
        for editor in (self.buy_date, self.sell_date):
            editor.calendarWidget().currentPageChanged.connect(
                lambda year, month, date_editor=editor:
                    self._refresh_calendar_availability(date_editor)
            )

    def _refresh_calendar_availability(self, editor):
        calendar = editor.calendarWidget()
        first_of_month = QDate(calendar.yearShown(), calendar.monthShown(), 1)
        first_day_of_week = calendar.firstDayOfWeek().value
        offset = (first_of_month.dayOfWeek() - first_day_of_week) % 7
        first_visible_day = first_of_month.addDays(-offset)

        unavailable = QTextCharFormat()
        unavailable.setForeground(QColor("#806d77"))
        unavailable.setBackground(QColor("#281b23"))

        for index in range(42):
            day = first_visible_day.addDays(index)
            calendar.setDateTextFormat(
                day,
                unavailable
                if day < calendar.minimumDate() or day > calendar.maximumDate()
                else QTextCharFormat(),
            )

    def reset(self): # Rests the UI to the default state, with Amazon selected, 10 units, and the latest two weeks of data.
        self._updating = True
        name = "Amazon" if "Amazon" in self.data else next(iter(self.data)) # Checks if 'Amazon' exists
        self.stock.setCurrentIndex(self.stock.findData(name))
        series = self.data[name]
        first, last = series[0].date, series[-1].date
        for editor in (self.buy_date, self.sell_date):
            editor.setDateRange(qdate(first), qdate(last))
        self.sell_date.setDate(qdate(last))
        self.buy_date.setDate(qdate(max(first, last - timedelta(days=14))))
        self.quantity.setValue(10)
        self.quantity.lineEdit().setText("10")
        self._updating = False
        self.update_ui()

    def stock_changed(self): # When the stock changes, the existing dates are adjusted to fit the new stock's history and the date-editor ranges are updated.
        if self._updating:
            return
        self._updating = True
        series = self.data[self.stock.currentData()]
        first, last = series[0].date, series[-1].date
        buy = max(first, min(last, self.buy_date.date().toPyDate()))
        sell = max(buy, min(last, self.sell_date.date().toPyDate()))
        for editor in (self.buy_date, self.sell_date):
            editor.setDateRange(qdate(first), qdate(last))
        self.buy_date.setDate(qdate(buy))
        self.sell_date.setDate(qdate(sell))
        self._updating = False
        self.update_ui()

    def apply_range(self, days): # When a range button is clicked, the purchase date is set relative to the sell date.
        first = self.data[self.stock.currentData()][0].date
        sell = self.sell_date.date().toPyDate()
        buy = max(first, sell - timedelta(days=days)) if days is not None else first
        self.buy_date.setDate(qdate(buy))

    def select_comparison(self, row, column): # Clicking a comparison row switches the stock selector to that stock.
        if 0 <= row < len(self.comparison_rows):
            self.stock.setCurrentIndex(self.stock.findData(self.comparison_rows[row][0]) )

    def update_ui(self, *_): # Updates the UI when control values are changed.  Also gets called when the app initializes
        if self._updating:
            return
        self._updating = True
        try:
            series = self.data[self.stock.currentData()]
            first, last = series[0].date, series[-1].date
            buy = self.buy_date.date().toPyDate()
            sell = self.sell_date.date().toPyDate()
            self.buy_date.setDateRange(qdate(first), qdate(sell))
            self.sell_date.setDateRange(qdate(buy), qdate(last))
            self._refresh_calendar_availability(self.buy_date)
            self._refresh_calendar_availability(self.sell_date)
            self.history.setText( # Ensures that there is no empty text situation, and that the user is aware of the available date range for the selected stock.
                f"Historical prices from {first:%d %b %Y} to {last:%d %b %Y}." )
            if not self.quantity.lineEdit().text().strip():
                raise ValueError("Enter a whole-number quantity of at least 1.")

            quantity = self.quantity.value()
            self.result = calculate(series, quantity, buy, sell) # Calculates the trade results based on the selected stock, quantity, and dates. Error handling and validation is handled by valueError exceptions.
            result = self.result
            self.error.hide()
            self.cost.set_result( "Purchase total",money(result.cost),f"{quantity:,} × {money(result.buy.price)} on {result.buy.date:%d %b %Y}", )
            self.sale.set_result("Sell total",money(result.value),f"{quantity:,} × {money(result.sell.price)} on {result.sell.date:%d %b %Y}",)
            gain = result.profit >= 0
            self.profit.set_result("Profit" if gain else "Loss",("▲ " if gain else "▼ ") + money(result.profit),f"{result.percent:+.2f}%","gain" if gain else "loss",)
            visible = [# The chart displays a range of historical prices around the selected buy and sell dates, with a 30-day buffer on either side.
                point
                for point in series
                if buy - timedelta(days=30)
                <= point.date
                <= sell + timedelta(days=30)
            ]
            self.chart.set_data(visible, result)

            self.comparison_rows = compare(self.data, quantity, buy, sell) # Rebuilds the comparison table and selects the current stock's row.
            self.table.setRowCount(len(self.comparison_rows))
            for row, (name, trade) in enumerate(self.comparison_rows):
                gain = trade.profit >= 0
                values = [
                    display_name(name),
                    ("▲ " if gain else "▼ ") + f"{trade.percent:+.2f}%",money(trade.profit),f"{trade.buy.date:%d %b %Y} → {trade.sell.date:%d %b %Y}", ]
                for column, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    if column in (1, 2):
                        item.setForeground(
                            QColor(COLORS["gain" if gain else "loss"])
                        )
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                    self.table.setItem(row, column, item)
                if name == self.stock.currentData():
                    self.table.selectRow(row)
        except ValueError as error: # show inline error, reset cards and chart, and always release the _updating's guarding.
            self.result = None
            self.error.setText(str(error))
            self.error.show()
            for stat in (self.cost, self.sale, self.profit):
                stat.set_result(stat.title.text(), "—", "")
            self.chart.set_data([], None)
            self.table.setRowCount(0)
            self.comparison_rows = []
        finally:
            self._updating = False


def main(): # Main function
    app = QApplication(sys.argv)
    app.setApplicationName("Stock Trade Profit Calculator")
    try:
        window = StockTradeProfitCalculator()
    except (OSError, ValueError) as error:
        QMessageBox.critical(
            None,"Could not open the calculator",f"{error}\n\nKeep styles.qss beside StockTradeCalculator.py.",
        )
        return 1
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
