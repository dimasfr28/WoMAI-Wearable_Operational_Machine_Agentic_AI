from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# Menggunakan NullPool agar kompatibel dengan Supabase Transaction Pooler (port 6543, IPv4)
engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
