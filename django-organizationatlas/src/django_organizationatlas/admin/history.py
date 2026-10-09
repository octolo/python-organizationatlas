"""Use simple-history's admin page."""

from simple_history.admin import SimpleHistoryAdmin


def with_history(admin_base):
    """Put SimpleHistoryAdmin ahead of admin_base so its history page wins."""

    class HistoryAdmin(SimpleHistoryAdmin, admin_base):
        pass

    HistoryAdmin.__name__ = f"{admin_base.__name__}WithHistory"
    return HistoryAdmin
