from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from ..core import security

router = APIRouter()

# For skeleton: hardcoded demo users, one per role. The role travels in the
# token so the customer app, the merchant app and admin tools share one login
# endpoint without seeing each other's routes.
_DEMO_USERS = {
    "demo": {"hashed_password": security.get_password_hash("demo123"), "role": "merchant"},
    "client": {"hashed_password": security.get_password_hash("client123"), "role": "customer"},
    "admin": {"hashed_password": security.get_password_hash("admin123"), "role": "admin"},
}


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = _DEMO_USERS.get(form_data.username)
    if not user or not security.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = security.create_access_token({"sub": form_data.username, "role": user["role"]})
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}
