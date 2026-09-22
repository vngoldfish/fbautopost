import os
import sys
import re
import random
import time
import pytest
from pathlib import Path

# Set up paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
EXTENSION_DIR = PROJECT_ROOT / "extension-auth-helper"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configuration defaults matching production specifications
DEFAULT_SYNC_TOKEN = os.environ.get("SYNC_TOKEN", "fbauto_secret_token_prod_2026")
DEFAULT_PROJECT_KEY = os.environ.get("PROJECT_KEY_DEFAULT", "taikhoan1")
BACKEND_HOST = os.environ.get("HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("PORT", 19823))
LIVE_BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# Specification Domain Constants
REACTION_WEIGHTS = {
    "LIKE": 0.60,
    "LOVE": 0.25,
    "HAHA": 0.10,
    "WOW": 0.03,
    "CARE": 0.02,
    "SAD": 0.0,
    "ANGRY": 0.0,
}

REACTION_FB_IDS = {
    "LIKE": "1635855486666999",
    "LOVE": "1635855606666987",
    "HAHA": "1635855726666975",
    "WOW": "1635855846666963",
    "CARE": "2269550756598811",
}

CHECKPOINT_ERROR_CODES = {
    190: "logged_out",
    368: "restricted",
    1357004: "checkpoint",
    1357001: "checkpoint",
}

GRAPHQL_DOC_IDS = {
    "post": ["27508435028820023", "27248647231502311", "6362241860538186"],
    "comment": ["27829190080054105", "5384620808298758", "5765399230164627"],
    "react": ["27646120298312844"],
}

SCROLL_PHYSICS = {
    "step_min_px": 220,
    "step_max_px": 750,
    "step_duration_min_ms": 300,
    "step_duration_max_ms": 700,
    "sub_steps_min": 8,
    "sub_steps_max": 15,
    "reverse_scroll_probability": 0.15,
    "reverse_scroll_min_px": -350,
    "reverse_scroll_max_px": -150,
    "dwell_short_min_ms": 800,
    "dwell_short_max_ms": 2200,
    "dwell_media_min_ms": 3500,
    "dwell_media_max_ms": 9000,
    "dwell_long_min_ms": 10000,
    "dwell_long_max_ms": 22000,
}

def bezier_easing(t: float) -> float:
    """Cubic Bezier curve approximation S(t) = 3*t^2 - 2*t^3 for t in [0, 1]."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 3 * (t ** 2) - 2 * (t ** 3)

def parse_spintax(template: str) -> str:
    """Recursively resolves spintax {A|B|C} into a randomized single string."""
    pattern = re.compile(r"\{([^{}]+)\}")
    while pattern.search(template):
        template = pattern.sub(lambda m: random.choice(m.group(1).split("|")), template)
    return template

def expand_all_spintax_permutations(template: str) -> list[str]:
    """Expands all possible variations of spintax for testing."""
    pattern = re.compile(r"\{([^{}]+)\}")
    match = pattern.search(template)
    if not match:
        return [template]
    
    options = match.group(1).split("|")
    prefix = template[:match.start()]
    suffix = template[match.end():]
    
    results = []
    for opt in options:
        for rest in expand_all_spintax_permutations(prefix + opt + suffix):
            if rest not in results:
                results.append(rest)
    return results


class E2EClient:
    """Opaque-box HTTP client for FB Auto Post backend.
    
    Operates against a live backend server if available, or falls back to
    FastAPI TestClient. Supports full headers, authentication tokens,
    and multi-tenant project keys.
    """
    def __init__(self, base_url: str = None, default_token: str = DEFAULT_SYNC_TOKEN, default_project: str = DEFAULT_PROJECT_KEY):
        self.default_token = default_token
        self.default_project = default_project
        self.base_url = base_url or os.environ.get("BACKEND_URL", LIVE_BACKEND_URL)
        self.is_live = False
        self._test_client = None
        self._init_client()

    def _init_client(self):
        import requests
        try:
            r = requests.get(f"{self.base_url}/health", timeout=0.5)
            if r.status_code == 200:
                self.is_live = True
                self.session = requests.Session()
                return
        except Exception:
            pass

        # Fallback to in-process FastAPI TestClient
        self.is_live = False
        try:
            # Try app.main then main
            try:
                from app.main import app
            except ImportError:
                from main import app
            from fastapi.testclient import TestClient
            self._test_client = TestClient(app)
        except Exception as e:
            self._test_client = None
            self._load_error = str(e)

    def _prepare_headers(self, headers: dict = None) -> dict:
        merged = {}
        if self.default_token is not None:
            merged["X-Sync-Token"] = self.default_token
        if self.default_project is not None:
            merged["X-Project-Key"] = self.default_project

        if headers:
            for k, v in headers.items():
                if v is None:
                    # Explicit removal of header
                    merged.pop(k, None)
                    # Also remove case variations
                    for key in list(merged.keys()):
                        if key.lower() == k.lower():
                            del merged[key]
                else:
                    merged[k] = v
        return merged

    def request(self, method: str, path: str, **kwargs):
        headers = self._prepare_headers(kwargs.pop("headers", None))
        
        if self.is_live:
            url = f"{self.base_url}{path}"
            return self.session.request(method, url, headers=headers, **kwargs)
        elif self._test_client:
            return self._test_client.request(method, path, headers=headers, **kwargs)
        else:
            raise RuntimeError(f"Cannot initialize E2E test client: {getattr(self, '_load_error', 'No client')}")

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def options(self, path: str, **kwargs):
        return self.request("OPTIONS", path, **kwargs)


@pytest.fixture(scope="session")
def client():
    """Provides an authenticated E2E test client."""
    return E2EClient()


@pytest.fixture(scope="session")
def unauth_client():
    """Provides an unauthenticated client with no X-Sync-Token."""
    return E2EClient(default_token=None)


@pytest.fixture
def unique_worker_id():
    """Generates unique node identifier for test isolation."""
    return f"node_test_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


@pytest.fixture
def unique_task_id():
    """Generates unique task identifier for test isolation."""
    return f"task_test_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


@pytest.fixture
def unique_account_id():
    """Generates unique account identifier for test isolation."""
    return f"acc_test_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
