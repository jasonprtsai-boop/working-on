def socket_auth(role: str = "admin") -> dict:
    from backend.utils.auth import create_jwt

    return {"token": create_jwt(role)}
