from __future__ import annotations

import gc

import pytest


def _drain_qt_teardown() -> None:
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    QApplication.closeAllWindows()
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            continue

    for _ in range(2):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # PySide/qfluentwidgets keep Property/QMetaObject descriptor graphs alive
    # until interpreter shutdown. Freeze the post-test heap after draining Qt's
    # deferred deletes so CPython does not report them as uncollectable garbage.
    _drain_qt_teardown()
    gc.collect()
    gc.freeze()