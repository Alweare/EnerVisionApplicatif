from fastapi import APIRouter, Depends

from core.security import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/v1", tags=["Auth"])


@router.get(
    "/me",
    summary="Identité de l'utilisateur authentifié",
    description=(
        "Retourne l'identité extraite de l'access token Keycloak transmis. "
        "Sert notamment à vérifier depuis le frontend que le token est bien "
        "accepté par l'API."
    ),
)
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return user
