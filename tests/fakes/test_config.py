"""
test_config.py

Test-environment settings shared by the whole test_mode stack (OrthoASession,
OrthoADataParse, FakeOrthoAdl) — kept separate from fake_orthoadl.py so that module
only ever deals with impersonating OrthoAdl, not with paths owned by other layers.

CONFIG is in-memory, per-process configuration: tests set fail_connect / fail_downloads
on it before constructing an OrthoASession(test_mode=True) or OrthoADataParse(test_mode=True);
the autouse fixture in conftest.py resets it after every test so failures never leak
between tests.

Note: OrthoASession uses the real users_db.json even in test_mode (no separate test path)
— see the get_users_list-related tests for the consequence this has on cache isolation.
"""

from dataclasses import dataclass, field


@dataclass
class FakeOrthoAdlConfig:
    fail_connect: Exception | None = None
    fail_downloads: dict = field(default_factory=dict)

    def reset(self) -> None:
        self.fail_connect = None
        self.fail_downloads = {}


CONFIG = FakeOrthoAdlConfig()
