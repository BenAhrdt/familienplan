from app.models.entities import Role
from app.schemas.core import UserOut


def test_pending_user_internal_email_is_not_exposed_or_rejected():
    user = UserOut(
        id=7,
        username="pending-example",
        display_name="Ohne E-Mail",
        email="pending-example@familienplan.invalid",
        role=Role.VIEWER,
        color="#3BA4E5",
        is_pending=True,
    )

    assert user.email is None
