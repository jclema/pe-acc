from datetime import UTC, datetime, timedelta

import jwt
import pytest


def test_pyjwt_preserves_options_between_verification_modes() -> None:
    key = "dependency-regression-test-key-32-bytes"
    token = jwt.encode(
        {"exp": datetime.now(UTC) - timedelta(minutes=1)}, key, algorithm="HS256"
    )
    options = {"verify_signature": False}

    jwt.decode(token, options=options)
    assert options == {"verify_signature": False}

    options["verify_signature"] = True
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, key, algorithms=["HS256"], options=options)
