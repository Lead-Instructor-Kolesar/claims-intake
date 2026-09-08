from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# THE ASSIGNMENT DOES NOT CALL FOR ANY DATABASING YET, BUT I IMPLEMENTED IT IN THE PREVIOUS ASSIGNMENT
# AND I AM KEEPING IT AS LEGACY CODE (INSTRUCTOR KOLESAR SAID IT WAS OK)
DATABASE_URL = "sqlite:///./tasks.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
