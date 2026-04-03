from __future__ import annotations

import pytest


pytestmark = pytest.mark.skip(
    reason="Localization is covered in frontend/src/i18n/index.test.ts and frontend/src/app/App.test.tsx."
)


def test_localization_is_verified_in_frontend_suite() -> None:
    pass
