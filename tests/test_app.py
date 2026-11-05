"""Exercise the whole Streamlit script with a UI double; no server or API calls."""
import contextlib
import os
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class UI(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.sidebar = self
        self.callbacks, self.tables, self.charts, self.messages = {}, [], [], []

    def number_input(self, label, *, key, value, **kwargs):
        self.session_state.setdefault(key, value)

    def text_input(self, label, *, key, **kwargs):
        self.session_state.setdefault(key, "")

    def radio(self, label, values, *, key):
        self.session_state.setdefault(key, values[0])

    def button(self, label, on_click=None, args=(), **kwargs):
        self.callbacks[label] = (on_click, args)

    def click(self, label):
        callback, args = self.callbacks[label]
        callback(*args)

    def dataframe(self, table):
        self.tables.append(table)

    def bar_chart(self, table):
        self.charts.append(table)

    def columns(self, number):
        return [self] * number

    def expander(self, *args, **kwargs):
        return contextlib.nullcontext()

    def stop(self):
        raise RuntimeError("UI stopped")

    def __getattr__(self, name):
        def output(*args, **kwargs):
            self.messages.extend(str(arg) for arg in args)
        return output


class AppTests(unittest.TestCase):
    def test_full_dry_run_page_propose_approve_and_completion(self):
        ui = UI()
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": ui}), patch.dict(os.environ, {}, clear=True), \
                patch("tanda_round.load_wallets", return_value={}):
            runpy.run_path(str(app))
            self.assertEqual(ui.tables[0].loc["Ana", "Predicted on-time"], "89.8%")
            self.assertEqual(ui.tables[0].loc["Ana", "90% interval"], "71%–99%")
            self.assertAlmostEqual(ui.charts[0].loc["Ana", "Predicted on-time (%)"], 89.8)
            self.assertTrue(any("PayPal evidence" in text for text in ui.messages))
            for _ in range(6):
                ui.click("Propose next round")
                runpy.run_path(str(app))
                ui.click("I approve: run this round")
                runpy.run_path(str(app))
            self.assertTrue(ui.session_state["session"].complete)
            self.assertTrue(any("All 6 rounds are done" in text for text in ui.messages))


if __name__ == "__main__":
    unittest.main()
