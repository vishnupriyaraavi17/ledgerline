from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.x Declarative Base for LedgerLine entities.
    Financial models will inherit from this base in subsequent tasks.
    """
    pass
