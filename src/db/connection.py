import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

load_dotenv()

_in_docker = os.path.exists("/.dockerenv")
if _in_docker:
    _url = os.getenv("DATABASE_URL", "postgresql+asyncpg://bsbeacon:bsbeacon@db:5432/bsbeacon")
else:
    _url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL", "postgresql+asyncpg://bsbeacon:bsbeacon@localhost:5432/bsbeacon")

engine = create_async_engine(_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
