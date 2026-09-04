"""Declarative base for persistent models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by all SQLAlchemy models."""
