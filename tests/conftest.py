"""
Test-only workaround for a bug in Streamlit 1.32's AppTest:
for a selectbox that uses format_func, AppTest looks for the raw value
among the *displayed* labels and crashes. When that happens we fall back
to the index Streamlit itself reported. The app code is not affected.
"""

from streamlit.testing.v1.element_tree import Selectbox


def _index(self):
    if self.value is None:
        return None
    if len(self.options) == 0:
        return 0
    text = str(self.value)
    return self.options.index(text) if text in self.options else self.proto.default


Selectbox.index = property(_index)
