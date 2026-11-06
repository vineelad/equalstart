"""Visitor-local saved plans over a shared, server-side usage ledger."""
from copy import deepcopy
import os

from equalstart.storage import Store


def public_demo():
    return os.getenv("EQUALSTART_PUBLIC", "").lower() in {"1", "true"}


class SessionStore(Store):
    """Only public source receipts and budget metadata reach the shared database.

    Instantiate once per Streamlit session, never in cache_resource.
    Saved plans deliberately expire when that session is lost.
    """

    def __init__(self, path=None):
        super().__init__(path)
        self._saved = {}
        self._plans = {}

    def save(self, opportunity_id):
        self._saved.setdefault(opportunity_id, [])

    def saved(self):
        return deepcopy(self._saved)

    def tasks(self, opportunity_id, completed):
        if opportunity_id in self._saved:
            self._saved[opportunity_id] = list(completed)

    def remove(self, opportunity_id):
        self._saved.pop(opportunity_id, None)
        self._plans.pop(opportunity_id, None)

    def save_plan(self, opportunity_id, tasks):
        self.save(opportunity_id)
        self._plans[opportunity_id] = deepcopy(tasks)

    def plan(self, opportunity_id):
        return deepcopy(self._plans.get(opportunity_id))

    def clear_saved(self):
        self._saved.clear()
        self._plans.clear()
