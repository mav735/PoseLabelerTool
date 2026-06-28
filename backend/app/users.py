import datetime
from sqlalchemy import select
from app.models import User


def get_or_create_user(session, username: str) -> User:
    user = session.execute(select(User).where(User.username == username)).scalars().first()
    if user is None:
        user = User(username=username)
        session.add(user)
    else:
        user.last_seen = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    return user
